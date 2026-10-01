"""Measurement data. Stream times are integer nanoseconds since the stream started."""

from collections import deque
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class DeviceInfo:
    name: str
    vout_rate_hz: int
    edge_clock_hz: int


@dataclass(frozen=True)
class ToneBurst:
    frequency_hz: int = 40_000
    cycles: int = 32

    def __post_init__(self):
        if not isinstance(self.frequency_hz, int) or not 40_000 <= self.frequency_hz <= 1_000_000:
            raise ValueError("Frequency must be an integer between 40000 and 1000000 Hz")
        if not isinstance(self.cycles, int) or not 1 <= self.cycles <= 255:
            raise ValueError("Cycle count must be an integer between 1 and 255")


def _read_only(values, dtype):
    array = np.array(values, dtype=dtype, copy=True)
    array.flags.writeable = False
    return array


@dataclass(frozen=True)
class VoutBlock:
    """Consecutive VOUT samples."""
    times_ns: NDArray[np.int64]
    volts: NDArray[np.float64]

    def __post_init__(self):
        object.__setattr__(self, "times_ns", _read_only(self.times_ns, np.int64))
        object.__setattr__(self, "volts", _read_only(self.volts, np.float64))


@dataclass(frozen=True)
class EdgeBlock:
    """Consecutive OUT3 edges; levels[i] is the level after edge i."""
    times_ns: NDArray[np.int64]
    levels: NDArray[np.bool_]

    def __post_init__(self):
        object.__setattr__(self, "times_ns", _read_only(self.times_ns, np.int64))
        object.__setattr__(self, "levels", _read_only(self.levels, np.bool_))


def _concatenate(blocks, field, dtype):
    return np.concatenate([getattr(block, field) for block in blocks]) if blocks else np.empty(0, dtype)


class StreamHistory:
    """The most recent span of a VOUT and OUT3 stream."""

    def __init__(self, span_s=2.0):
        self.span_ns = int(span_s * 1e9)
        self.clear()

    def clear(self):
        self.vout_blocks = deque()
        self.edge_blocks = deque()
        self.latest_ns = 0

    def add(self, block: VoutBlock | EdgeBlock):
        if not len(block.times_ns):
            return
        (self.vout_blocks if isinstance(block, VoutBlock) else self.edge_blocks).append(block)
        self.latest_ns = max(self.latest_ns, int(block.times_ns[-1]))
        oldest_ns = self.latest_ns - self.span_ns
        for blocks in (self.vout_blocks, self.edge_blocks):
            while blocks and blocks[0].times_ns[-1] < oldest_ns:
                blocks.popleft()

    def vout(self, start_ns, end_ns):
        """Times and volts of the samples within [start_ns, end_ns]."""
        times = _concatenate(self.vout_blocks, "times_ns", np.int64)
        volts = _concatenate(self.vout_blocks, "volts", np.float64)
        inside = (times >= start_ns) & (times <= end_ns)
        return times[inside], volts[inside]

    def out3(self, start_ns, end_ns):
        """Edges within [start_ns, end_ns] and the level before them, or None if unknown."""
        times = _concatenate(self.edge_blocks, "times_ns", np.int64)
        levels = _concatenate(self.edge_blocks, "levels", np.bool_)
        before = np.searchsorted(times, start_ns)
        after = np.searchsorted(times, end_ns, side="right")
        initial = bool(levels[before - 1]) if before else None
        return times[before:after], levels[before:after], initial

    def out3_frequency(self, start_ns, end_ns):
        """Frequency between consecutive rising edges within [start_ns, end_ns], timed at the later edge.

        Each edge block holds one uninterrupted recording, so periods are only measured within a block.
        """
        times, hertz = [], []
        for block in self.edge_blocks:
            rising = block.times_ns[block.levels]
            times.append(rising[1:])
            hertz.append(1e9 / np.diff(rising))
        if not times:
            return np.empty(0, np.int64), np.empty(0)
        times, hertz = np.concatenate(times), np.concatenate(hertz)
        inside = (times >= start_ns) & (times <= end_ns)
        return times[inside], hertz[inside]
