from dataclasses import dataclass

import serial
from serial.tools import list_ports

from .tf_protocol import Decoder, encode
from .simulator import SimulatedDevice


@dataclass(frozen=True)
class DevicePort:
    label: str
    port: str | None        # None selects the simulator


def discover_devices():
    ports = [DevicePort(f"{port.device} - {port.description}", port.device) for port in sorted(list_ports.comports())]
    return [*ports, DevicePort("Demo OUT3", None)]


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


def open_device(device: DevicePort):
    return SimulatedDevice() if device.port is None else SerialDevice(device.port)
