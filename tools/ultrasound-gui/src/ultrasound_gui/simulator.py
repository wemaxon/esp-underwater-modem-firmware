"""In-process stand-in for the firmware, speaking the same TinyFrame USB protocol.

While streaming it produces, in real time, a VOUT noise floor and a 40 kHz
burst of BURST_S every BURST_PERIOD_S, with zero-crossing edges on OUT3.
"""

from struct import pack
from time import monotonic, sleep

import numpy as np

from .tf_protocol import (
    DEVICE_FRAME_ID, GET_CONFIG, GET_DEVICE_INFO, LOG, OK, OUT3_EDGES, SET_CONFIG, STREAM_START,
    STREAM_STOP, TRANSMIT, VERSION, VOUT_SAMPLES, Packet,
)


class SimulatedDevice:
    NAME = "Demo"
    VOUT_RATE_HZ = 20_000
    EDGE_CLOCK_HZ = 10_000_000
    VOUT_BLOCK = 256
    BURST_PERIOD_S = 0.2
    BURST_S = 0.02
    BURST_HZ = 40_000
    TRANSMIT_DELAY_S = 0.05

    def __init__(self):
        self.outbox = []
        self.event_id = DEVICE_FRAME_ID
        self.stream_start = None
        self.samples_sent = 0
        self.bursts_sent = 0
        self.transmit_request = None
        self.transmit_ready_at = 0.0
        self.random = np.random.default_rng(1)
        self.config_registers = bytes([0x00, 0x00, 0x00, 0x00, 0x07, 0x94, 0x20, 0x00])  # reset values, zero crossing on

    def send(self, packet):
        handlers = {
            GET_DEVICE_INFO: self._device_info,
            STREAM_START: self._stream_start,
            STREAM_STOP: self._stream_stop,
            TRANSMIT: self._transmit,
            GET_CONFIG: self._config,
            SET_CONFIG: self._config,
        }
        handlers[packet.message_type](packet)

    def read(self):
        sleep(0.005)
        now = monotonic()
        if self.transmit_request and now >= self.transmit_ready_at:
            self._respond(self.transmit_request, bytes([OK]))
            self.transmit_request = None
            self._event(LOG, b"I (0) DEMO: Tone burst complete\n")
        if self.stream_start is not None:
            self._stream_until(round((now - self.stream_start) * 1e9))
        packets, self.outbox = self.outbox, []
        return packets

    def close(self):
        self.stream_start = None
        self.transmit_request = None

    def _respond(self, request, payload):
        self.outbox.append(Packet(request.message_type, request.frame_id, payload))

    def _event(self, message_type, payload):
        self.outbox.append(Packet(message_type, self.event_id, payload))
        self.event_id = DEVICE_FRAME_ID | ((self.event_id + 1) & 0x7FFF)

    def _device_info(self, packet):
        self._respond(packet, pack("<BII", VERSION, self.VOUT_RATE_HZ, self.EDGE_CLOCK_HZ) + self.NAME.encode())
        self._event(LOG, b"I (0) DEMO: Device connected\n")

    def _stream_start(self, packet):
        if self.stream_start is None:
            self.stream_start = monotonic()
            self.samples_sent = 0
            self.bursts_sent = 0
        self._respond(packet, bytes([OK]))

    def _stream_stop(self, packet):
        self.stream_start = None
        self._respond(packet, bytes([OK]))

    def _transmit(self, packet):
        self.transmit_request = packet
        self.transmit_ready_at = monotonic() + self.TRANSMIT_DELAY_S

    def _config(self, packet):
        if packet.message_type == SET_CONFIG:
            self.config_registers = packet.payload
            self._event(LOG, f"I (0) DEMO: Configuration applied: {packet.payload.hex()}\n".encode())
        self._respond(packet, bytes([OK]) + self.config_registers)

    def _stream_until(self, now_ns):
        period_ns = 1_000_000_000 // self.VOUT_RATE_HZ
        while (self.samples_sent + self.VOUT_BLOCK) * period_ns <= now_ns:
            times_s = (self.samples_sent + np.arange(self.VOUT_BLOCK)) * period_ns / 1e9
            millivolts = np.clip(1000 * self._vout(times_s), 0, 3300).astype("<u2")
            self._event(VOUT_SAMPLES, pack("<QH", self.samples_sent * period_ns, self.VOUT_BLOCK) + millivolts.tobytes())
            self.samples_sent += self.VOUT_BLOCK
        while (self.bursts_sent * self.BURST_PERIOD_S + self.BURST_S) * 1e9 <= now_ns:
            self._event(OUT3_EDGES, self._burst_edges(self.bursts_sent * self.BURST_PERIOD_S))
            self.bursts_sent += 1

    def _vout(self, times_s):
        """Noise floor plus the envelope of each burst: 1 ms rise, 2 ms decay."""
        since_start = np.mod(times_s, self.BURST_PERIOD_S)
        rise = 1 - np.exp(-since_start / 0.001)
        decay = np.exp(-np.clip(since_start - self.BURST_S, 0, None) / 0.002)
        envelope = np.where(since_start < self.BURST_S, rise, rise * decay)
        return 0.3 + 1.5 * envelope + self.random.normal(0, 0.01, len(times_s))

    def _burst_edges(self, start_s):
        half_period_ticks = self.EDGE_CLOCK_HZ // (2 * self.BURST_HZ)
        count = round(self.BURST_S * 2 * self.BURST_HZ)
        intervals = np.full(count - 1, half_period_ticks, dtype="<u2")
        return pack("<QBH", round(start_s * 1e9), 1, count) + intervals.tobytes()
