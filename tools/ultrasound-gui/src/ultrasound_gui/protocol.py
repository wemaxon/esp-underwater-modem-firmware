from dataclasses import dataclass
from struct import Struct
from time import monotonic

import numpy as np

from ._vendor.ponyframe.TinyFrame import TF, TinyFrame
from .model import Capture, DeviceInfo


GET_DEVICE_INFO = 1
CAPTURE = 2
STOP = 3
TRANSMIT = 4
VERSION = 4
OK, INVALID_REQUEST, BUSY, TIMEOUT, CANCELLED, OVERFLOW, DEVICE_ERROR = range(7)
RESULT_NAMES = ("OK", "Invalid request", "Device busy", "Operation timed out", "Capture cancelled", "Capture buffer overflow", "Device error")
_INFO = Struct("<BIH")
_CAPTURE = Struct("<BBIH")
_TONE = Struct("<IH")


def encode_tone(tone):
    return _TONE.pack(tone.frequency_hz, tone.cycles)


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


def decode_info(payload):
    if len(payload) <= _INFO.size:
        raise ProtocolError("Invalid device information")
    version, tick_hz, max_edges = _INFO.unpack_from(payload)
    if version != VERSION:
        raise ProtocolError(f"Device protocol version {version}; expected {VERSION}. Update the firmware and GUI together.")
    if not tick_hz or not max_edges or max_edges > (65535 - _CAPTURE.size) // 4:
        raise ProtocolError("Invalid device capture limits")
    return DeviceInfo(payload[_INFO.size:].decode("utf-8"), tick_hz, max_edges)


def decode_capture(payload, info):
    if len(payload) < _CAPTURE.size:
        raise ProtocolError("Truncated capture")
    result, initial, duration, count = _CAPTURE.unpack_from(payload)
    if result != OK or initial > 1 or count > info.max_edges or len(payload) != _CAPTURE.size + 4 * count:
        raise ProtocolError("Invalid capture payload")
    return Capture(info.tick_hz, duration, bool(initial), np.frombuffer(payload, "<u4", count, _CAPTURE.size))


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
