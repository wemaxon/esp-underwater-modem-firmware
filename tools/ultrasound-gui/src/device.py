from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import monotonic

import numpy as np
import serial
from serial.tools import list_ports


DEMO = "Demo (simulated signal)"
BAUD_RATE = 115200


@dataclass(frozen=True)
class DataFrame:
    time_ms: np.ndarray
    amplitude: np.ndarray


def devices():
    return {DEMO: None, **{
        f"{port.device} - {port.description}": port.device
        for port in sorted(list_ports.comports())
    }}


class DemoSource:
    def __init__(self):
        self.started = monotonic()
        self.time_ms = np.linspace(0, 2, 1000)

    def read(self):
        phase = monotonic() - self.started
        envelope = np.exp(-((self.time_ms - 0.8 - 0.2 * np.sin(phase)) / 0.3) ** 2)
        return DataFrame(self.time_ms, envelope * np.sin(2 * np.pi * 40 * self.time_ms + phase))

    def close(self):
        pass


class SerialSource:
    def __init__(self, port):
        self.port = serial.Serial(port, BAUD_RATE, timeout=0.1, write_timeout=0.1)

    def read(self):
        return None

    def close(self):
        self.port.close()


class Acquisition(Thread):
    def __init__(self, port, source_factory=None):
        super().__init__(name="ultrasound-acquisition", daemon=True)
        self.port = port
        self.source_factory = source_factory
        self.stop_requested = Event()
        self.events = Queue()
        self.DataFrames = Queue(maxsize=1)

    def stop(self):
        self.stop_requested.set()

    def latest_frame(self):
        try:
            return self.DataFrames.get_nowait()
        except Empty:
            return None

    def run(self):
        source = None
        try:
            source = (self.source_factory() if self.source_factory else
                      DemoSource() if self.port is None else SerialSource(self.port))
            self.events.put(("connected", None))
            while not self.stop_requested.is_set():
                DataFrame = source.read()
                if DataFrame is not None:
                    try:
                        self.DataFrames.put_nowait(DataFrame)
                    except Full:
                        self.latest_frame()
                        self.DataFrames.put_nowait(DataFrame)
                if self.stop_requested.wait(1 / 30):
                    break
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            if source is not None:
                try:
                    source.close()
                except Exception as exc:
                    self.events.put(("error", str(exc)))
            self.events.put(("stopped", None))
