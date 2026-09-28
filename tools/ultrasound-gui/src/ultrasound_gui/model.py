from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class DeviceInfo:
    name: str
    tick_hz: int
    max_edges: int


@dataclass(frozen=True)
class ToneBurst:
    frequency_hz: int = 40_000
    cycles: int = 32

    def __post_init__(self):
        if not isinstance(self.frequency_hz, int) or not 40_000 <= self.frequency_hz <= 1_000_000:
            raise ValueError("Frequency must be an integer between 40000 and 1000000 Hz")
        if not isinstance(self.cycles, int) or not 1 <= self.cycles <= 255:
            raise ValueError("Cycle count must be an integer between 1 and 255")


@dataclass(frozen=True)
class Capture:
    tick_hz: int
    duration_ticks: int
    initial_high: bool
    edges: NDArray[np.uint32]

    def __post_init__(self):
        edges = np.array(self.edges, dtype=np.uint32, copy=True)
        if self.tick_hz <= 0 or self.duration_ticks <= 0 or edges.ndim != 1:
            raise ValueError("Invalid capture timing")
        if len(edges) and (edges[0] == 0 or edges[-1] >= self.duration_ticks or np.any(edges[1:] <= edges[:-1])):
            raise ValueError("Capture edges must increase within the capture duration")
        edges.flags.writeable = False
        object.__setattr__(self, "edges", edges)

    def steps(self):
        ticks = np.concatenate(([0], self.edges, [self.duration_ticks]))
        levels = (np.arange(len(self.edges) + 1) % 2) ^ int(self.initial_high)
        return ticks * (1000 / self.tick_hz), np.append(levels, levels[-1])

    def frequency(self):
        rising = self.edges[int(self.initial_high)::2].astype(np.float64)
        return rising[1:] * (1000 / self.tick_hz), self.tick_hz / np.diff(rising) / 1000
