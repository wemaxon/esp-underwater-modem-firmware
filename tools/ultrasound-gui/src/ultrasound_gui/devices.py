from dataclasses import dataclass
from struct import pack
from time import monotonic, sleep

import numpy as np
import serial
from serial.tools import list_ports

from .protocol import CAPTURE, CANCELLED, GET_DEVICE_INFO, LOG, OK, STOP, TRANSMIT, VERSION, Decoder, Packet, encode


@dataclass(frozen=True)
class DevicePort:
    label: str
    port: str | None


def discover_devices():
    return [*(DevicePort(f"{port.device} - {port.description}", port.device) for port in sorted(list_ports.comports())), DevicePort("Demo OUT3", None)]


class SerialDevice:
    def __init__(self, port):
        self.port = serial.Serial(port, 115200, timeout=0.02, write_timeout=0.2)
        self.port.reset_input_buffer()
        self.decoder = Decoder()

    def send(self, packet):
        data = encode(packet)
        if self.port.write(data) != len(data):
            raise OSError("Incomplete USB command write")

    def read(self):
        return self.decoder.feed(self.port.read(max(1, min(self.port.in_waiting, 65_536))))

    def close(self):
        self.port.close()


class DemoDevice:
    def __init__(self):
        self.messages = []
        self.pending = None
        self.tx_pending = None
        self.log_id = 0x8000

    def _log(self, message):
        self.messages.append(Packet(LOG, self.log_id, message.encode("utf-8")))
        self.log_id = 0x8000 | ((self.log_id + 1) & 0x7fff)

    def send(self, packet):
        if packet.message_type == GET_DEVICE_INFO:
            self.messages.append(Packet(GET_DEVICE_INFO, packet.frame_id, pack("<BIH", VERSION, 1_000_000, 1023) + b"Demo OUT3"))
            self._log("I (0) DEMO: Device connected\n")
        elif packet.message_type == CAPTURE:
            self.pending = packet
            self.ready_at = monotonic() + 0.1
        elif packet.message_type == TRANSMIT:
            self.tx_pending = packet
            self.tx_ready_at = monotonic() + 0.05
        elif packet.message_type == STOP:
            if self.pending:
                self.messages.append(Packet(CAPTURE, self.pending.frame_id, bytes([CANCELLED])))
                self.pending = None
            self.messages.append(Packet(STOP, packet.frame_id, bytes([OK])))

    def read(self):
        sleep(0.005)
        if self.tx_pending and monotonic() >= self.tx_ready_at:
            self.messages.append(Packet(TRANSMIT, self.tx_pending.frame_id, bytes([OK])))
            self.tx_pending = None
            self._log("I (0) DEMO: Tone burst complete\n")
        if self.pending and monotonic() >= self.ready_at:
            edges = np.arange(12, 800, 12, dtype="<u4")
            payload = pack("<BBIH", OK, 0, 1000, len(edges)) + edges.tobytes()
            self.messages.append(Packet(CAPTURE, self.pending.frame_id, payload))
            self.pending = None
        messages, self.messages = self.messages, []
        return messages

    def close(self):
        self.pending = None
        self.tx_pending = None


def open_device(info):
    return DemoDevice() if info.port is None else SerialDevice(info.port)
