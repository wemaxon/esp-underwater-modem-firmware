"""In-process stand-in for the firmware, speaking the same TinyFrame USB protocol."""

from struct import pack
from time import monotonic, sleep

import numpy as np

from .tf_protocol import CANCELLED, CAPTURE, GET_DEVICE_INFO, LOG, OK, STOP, TRANSMIT, VERSION, Packet


class SimulatedDevice:
    NAME = "Demo OUT3"
    TICK_HZ = 1_000_000
    MAX_EDGES = 1023
    CAPTURE_DELAY = 0.1
    TRANSMIT_DELAY = 0.05

    def __init__(self):
        self.outbox = []
        self.capture_request = None
        self.capture_ready_at = 0.0
        self.transmit_request = None
        self.transmit_ready_at = 0.0
        self.log_id = 0x8000

    def send(self, packet):
        handlers = {GET_DEVICE_INFO: self._device_info, CAPTURE: self._capture, TRANSMIT: self._transmit, STOP: self._stop}
        handlers[packet.message_type](packet)

    def read(self):
        sleep(0.005)
        now = monotonic()
        if self.transmit_request and now >= self.transmit_ready_at:
            self.outbox.append(Packet(TRANSMIT, self.transmit_request.frame_id, bytes([OK])))
            self.transmit_request = None
            self._log("I (0) DEMO: Tone burst complete\n")
        if self.capture_request and now >= self.capture_ready_at:
            self.outbox.append(Packet(CAPTURE, self.capture_request.frame_id, self.capture_payload()))
            self.capture_request = None
        packets, self.outbox = self.outbox, []
        return packets

    def close(self):
        self.capture_request = None
        self.transmit_request = None

    def capture_payload(self):
        """A 40 kHz square wave, 1 ms long."""
        edges = np.arange(12, 800, 12, dtype="<u4")
        return pack("<BBIH", OK, 0, 1000, len(edges)) + edges.tobytes()

    def _device_info(self, packet):
        self.outbox.append(Packet(GET_DEVICE_INFO, packet.frame_id, pack("<BIH", VERSION, self.TICK_HZ, self.MAX_EDGES) + self.NAME.encode()))
        self._log("I (0) DEMO: Device connected\n")

    def _capture(self, packet):
        self.capture_request = packet
        self.capture_ready_at = monotonic() + self.CAPTURE_DELAY

    def _transmit(self, packet):
        self.transmit_request = packet
        self.transmit_ready_at = monotonic() + self.TRANSMIT_DELAY

    def _stop(self, packet):
        if self.capture_request:
            self.outbox.append(Packet(CAPTURE, self.capture_request.frame_id, bytes([CANCELLED])))
            self.capture_request = None
        self.outbox.append(Packet(STOP, packet.frame_id, bytes([OK])))

    def _log(self, message):
        self.outbox.append(Packet(LOG, self.log_id, message.encode("utf-8")))
        self.log_id = 0x8000 | ((self.log_id + 1) & 0x7FFF)
