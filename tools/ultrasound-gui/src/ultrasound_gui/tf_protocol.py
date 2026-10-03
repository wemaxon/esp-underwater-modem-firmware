"""TinyFrame USB interface to the firmware (README "USB interface protocol")."""

from dataclasses import dataclass
import re
from struct import Struct
from time import monotonic

import numpy as np

from ._vendor.ponyframe.TinyFrame import TF, TinyFrame
from .tuss_config import REGISTERS, TussConfig
from .model import DeviceInfo, EdgeBlock, Tone, VoutBlock

VERSION = 9
(GET_DEVICE_INFO, STREAM_START, STREAM_STOP, TRANSMIT, LOG, VOUT_SAMPLES, OUT3_EDGES, STREAM_END,
 GET_CONFIG, SET_CONFIG) = range(1, 11)
EVENTS = frozenset((LOG, VOUT_SAMPLES, OUT3_EDGES, STREAM_END))
DEVICE_FRAME_ID = 0x8000        # set in the frame ID of every device event
OK, INVALID_REQUEST, TIMEOUT, OVERFLOW, DEVICE_ERROR, BUSY = range(6)
RESULT_NAMES = ("OK", "Invalid request", "Operation timed out", "Data lost: device buffer overflow", "Device error",
                "Device busy")
MAX_TONES = 512                 # tones per TRANSMIT waveform
_INFO = Struct("<BIII")
_VOUT = Struct("<QH")
_EDGES = Struct("<QBH")
_TONE = Struct("<II")
_TERMINAL_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Packet:
    message_type: int
    frame_id: int
    payload: bytes = b""


def _tinyframe():
    framing = TinyFrame(peer=0)
    framing.ID_BYTES = 2
    framing.LEN_BYTES = 2
    framing.TYPE_BYTES = 1
    framing.CKSUM_TYPE = "crc32"
    framing.USE_SOF_BYTE = True
    framing.SOF_BYTE = 1
    return framing


def encode(packet: Packet):
    if len(packet.payload) > 65535:
        raise ProtocolError("TinyFrame payload exceeds 65535 bytes")
    framing, output = _tinyframe(), []
    framing.write = output.append
    framing.send(packet.message_type, packet.payload, packet.frame_id)
    return bytes(output[0])


class Decoder:
    def __init__(self, timeout=0.5):
        self.framing = _tinyframe()
        self.framing.add_fallback_listener(self._receive)
        self.timeout = timeout
        self.last_data = monotonic()
        self.packets = []

    def _receive(self, _, message):
        self.packets.append(Packet(message.type, message.id, bytes(message.data)))
        return TF.STAY

    def feed(self, data):
        now = monotonic()
        if now - self.last_data > self.timeout:
            self.framing.reset_parser()
        if data:
            self.last_data = now
        self.packets = []
        self.framing.accept(data)
        return self.packets


def encode_waveform(tones: list[Tone]):
    if not 1 <= len(tones) <= MAX_TONES:
        raise ProtocolError(f"A waveform needs 1 to {MAX_TONES} tones")
    return b"".join(_TONE.pack(tone.frequency_hz, tone.cycles) for tone in tones)


def decode_result(payload):
    if len(payload) != 1 or payload[0] >= len(RESULT_NAMES):
        raise ProtocolError("Invalid result")
    return payload[0]


def decode_config(payload):
    """Result and, if it is OK, the device's TUSS4470 configuration."""
    result = decode_result(payload[:1])
    if result != OK:
        if len(payload) != 1:
            raise ProtocolError("Invalid configuration response")
        return result, None
    if len(payload) != 1 + len(REGISTERS):
        raise ProtocolError("Invalid configuration")
    return result, TussConfig(tuple(payload[1:]))


def decode_log(payload):
    if not 1 <= len(payload) <= 255:
        raise ProtocolError("Invalid log payload")
    return _TERMINAL_ESCAPE.sub("", payload.decode("utf-8", errors="replace"))


def decode_info(payload):
    if len(payload) <= _INFO.size:
        raise ProtocolError("Invalid device information")
    version, vout_rate_hz, edge_clock_hz, transmit_clock_hz = _INFO.unpack_from(payload)
    if version != VERSION:
        raise ProtocolError(f"Device protocol version {version}; expected {VERSION}. Update the firmware and GUI together.")
    if not vout_rate_hz or not edge_clock_hz or 1_000_000_000 % vout_rate_hz or 1_000_000_000 % edge_clock_hz:
        raise ProtocolError("Invalid device sample rates")
    if transmit_clock_hz < 2 * Tone.MAX_HZ:
        raise ProtocolError("Invalid device transmit clock")
    return DeviceInfo(payload[_INFO.size:].decode("utf-8"), vout_rate_hz, edge_clock_hz, transmit_clock_hz)


def decode_vout(payload, info: DeviceInfo):
    if len(payload) < _VOUT.size:
        raise ProtocolError("Truncated VOUT samples")
    first_ns, count = _VOUT.unpack_from(payload)
    if not count or len(payload) != _VOUT.size + 2 * count:
        raise ProtocolError("Invalid VOUT samples")
    millivolts = np.frombuffer(payload, "<u2", count, _VOUT.size)
    period_ns = 1_000_000_000 // info.vout_rate_hz
    return VoutBlock(first_ns + period_ns * np.arange(count, dtype=np.int64), millivolts / 1000)


def decode_edges(payload, info: DeviceInfo):
    if len(payload) < _EDGES.size:
        raise ProtocolError("Truncated OUT3 edges")
    first_ns, level, count = _EDGES.unpack_from(payload)
    if not count or level > 1 or len(payload) != _EDGES.size + 2 * (count - 1):
        raise ProtocolError("Invalid OUT3 edges")
    intervals = np.frombuffer(payload, "<u2", count - 1, _EDGES.size).astype(np.int64)
    if np.any(intervals == 0):
        raise ProtocolError("OUT3 edges must be strictly increasing")
    ns_per_tick = 1_000_000_000 // info.edge_clock_hz
    times = first_ns + ns_per_tick * np.concatenate(([0], np.cumsum(intervals)))
    levels = (np.arange(count) % 2 == 0) == bool(level)    # edges alternate, starting with level
    return EdgeBlock(times, levels)
