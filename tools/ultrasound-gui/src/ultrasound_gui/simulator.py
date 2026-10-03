"""In-process stand-in for the firmware, speaking the same TinyFrame USB protocol.

It behaves like a device listening to its own transmitter: while streaming, a
transmitted waveform arrives PROPAGATION_S later as OUT3 zero crossings at the
frequencies the device plays, with a matching VOUT envelope over a noise floor.
"""

from struct import iter_unpack, pack
from time import monotonic, sleep

import numpy as np

from .tf_protocol import (
    BUSY, DEVICE_FRAME_ID, GET_CONFIG, GET_DEVICE_INFO, LOG, OK, OUT3_EDGES, SET_CONFIG, STREAM_START,
    STREAM_STOP, TRANSMIT, VERSION, VOUT_SAMPLES, Packet,
)


class SimulatedDevice:
    NAME = "Demo"
    VOUT_RATE_HZ = 20_000
    EDGE_CLOCK_HZ = 10_000_000
    TRANSMIT_CLOCK_HZ = 20_000_000
    VOUT_BLOCK = 256
    EDGE_BLOCK = 4096
    PROPAGATION_S = 0.002
    NOISE_FLOOR_V = 0.3
    SIGNAL_V = 1.5

    def __init__(self):
        self.outbox = []
        self.event_id = DEVICE_FRAME_ID
        self.stream_start = None
        self.samples_sent = 0
        self.transmit_request = None
        self.transmit_done_at = 0.0
        self.receptions = []            # (start_ns, end_ns) of received waveforms, stream time
        self.edge_times = np.empty(0, np.int64)
        self.edge_first_level = True
        self.edges_sent = 0
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
        if self.transmit_request and now >= self.transmit_done_at:
            self._respond(self.transmit_request, bytes([OK]))
            self.transmit_request = None
            self._event(LOG, b"I (0) DEMO: Transmission complete\n")
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
        info = pack("<BIII", VERSION, self.VOUT_RATE_HZ, self.EDGE_CLOCK_HZ, self.TRANSMIT_CLOCK_HZ)
        self._respond(packet, info + self.NAME.encode())
        self._event(LOG, b"I (0) DEMO: Device connected\n")

    def _stream_start(self, packet):
        if self.stream_start is None:
            self.stream_start = monotonic()
            self.samples_sent = 0
            self.receptions = []
            self.edge_times = np.empty(0, np.int64)
            self.edges_sent = 0
        self._respond(packet, bytes([OK]))

    def _stream_stop(self, packet):
        self.stream_start = None
        self._respond(packet, bytes([OK]))

    def _config(self, packet):
        if packet.message_type == SET_CONFIG:
            self.config_registers = packet.payload
            self._event(LOG, f"I (0) DEMO: Configuration applied: {packet.payload.hex()}\n".encode())
        self._respond(packet, bytes([OK]) + self.config_registers)

    def _transmit(self, packet):
        if self.transmit_request:
            self._respond(packet, bytes([BUSY]))
            return
        half_periods_s = []
        for frequency_hz, cycles in iter_unpack("<II", packet.payload):
            half_ticks = (self.TRANSMIT_CLOCK_HZ + frequency_hz) // (2 * frequency_hz)
            half_periods_s.append(np.full(2 * cycles, half_ticks / self.TRANSMIT_CLOCK_HZ))
        half_periods_s = np.concatenate(half_periods_s)
        self.transmit_request = packet
        self.transmit_done_at = monotonic() + half_periods_s.sum()
        if self.stream_start is not None:
            self._receive(monotonic() - self.stream_start + self.PROPAGATION_S, half_periods_s)

    def _receive(self, start_s, half_periods_s):
        """Queues the zero crossings of a waveform that starts arriving at start_s."""
        offsets_s = np.concatenate(([0.0], np.cumsum(half_periods_s[:-1])))
        tick_ns = 1_000_000_000 // self.EDGE_CLOCK_HZ
        times = np.round((start_s + offsets_s) * 1e9 / tick_ns).astype(np.int64) * tick_ns
        pending = self.edge_times[self.edges_sent:]
        self.edge_first_level = self.edge_first_level ^ bool(self.edges_sent % 2)
        self.edge_times, self.edges_sent = np.concatenate((pending, times)), 0
        self.receptions.append((round(start_s * 1e9), int(times[-1])))

    def _stream_until(self, now_ns):
        period_ns = 1_000_000_000 // self.VOUT_RATE_HZ
        while (self.samples_sent + self.VOUT_BLOCK) * period_ns <= now_ns:
            times_ns = (self.samples_sent + np.arange(self.VOUT_BLOCK)) * period_ns
            millivolts = np.clip(1000 * self._vout(times_ns), 0, 3300).astype("<u2")
            self._event(VOUT_SAMPLES, pack("<QH", int(times_ns[0]), self.VOUT_BLOCK) + millivolts.tobytes())
            self.samples_sent += self.VOUT_BLOCK
        arrived = int(np.searchsorted(self.edge_times, now_ns))
        tick_ns = 1_000_000_000 // self.EDGE_CLOCK_HZ
        while self.edges_sent < arrived:
            chunk = self.edge_times[self.edges_sent:min(arrived, self.edges_sent + self.EDGE_BLOCK)]
            intervals = np.diff(chunk) // tick_ns
            if np.any(intervals > 0xFFFF):          # a gap between receptions starts a new block
                chunk = chunk[:np.argmax(intervals > 0xFFFF) + 1]
                intervals = np.diff(chunk) // tick_ns
            level = self.edge_first_level ^ bool(self.edges_sent % 2)
            self._event(OUT3_EDGES, pack("<QBH", int(chunk[0]), level, len(chunk)) + intervals.astype("<u2").tobytes())
            self.edges_sent += len(chunk)

    def _vout(self, times_ns):
        """Noise floor plus the envelope of each reception: 1 ms rise, 2 ms decay."""
        envelope = np.zeros(len(times_ns))
        for start_ns, end_ns in self.receptions:
            since_start = np.clip((times_ns - start_ns) / 1e9, 0, None)
            after_end = np.clip((times_ns - end_ns) / 1e9, 0, None)
            envelope = np.maximum(envelope, (1 - np.exp(-since_start / 0.001)) * np.exp(-after_end / 0.002) * (times_ns >= start_ns))
        return self.NOISE_FLOOR_V + self.SIGNAL_V * envelope + self.random.normal(0, 0.01, len(times_ns))
