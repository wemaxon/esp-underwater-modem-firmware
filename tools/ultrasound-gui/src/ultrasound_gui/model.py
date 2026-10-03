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
    transmit_clock_hz: int


@dataclass(frozen=True)
class Tone:
    """Part of a transmit waveform: whole cycles of one frequency. Waveforms play tones back to back."""
    frequency_hz: int = 40_000
    cycles: int = 32

    MIN_HZ = 10_000         # the chip ends a burst if IO2 does not toggle for 64 us
    MAX_HZ = 1_000_000

    def __post_init__(self):
        if not isinstance(self.frequency_hz, int) or not self.MIN_HZ <= self.frequency_hz <= self.MAX_HZ:
            raise ValueError(f"Frequency must be an integer between {self.MIN_HZ} and {self.MAX_HZ} Hz")
        if not isinstance(self.cycles, int) or not 1 <= self.cycles < 2**32:
            raise ValueError("Cycle count must be a positive integer")

    def played_hz(self, transmit_clock_hz):
        """The frequency as the device plays it: whole half periods of its transmit clock."""
        half_period = (transmit_clock_hz + self.frequency_hz) // (2 * self.frequency_hz)
        return transmit_clock_hz / (2 * half_period)

    @property
    def duration_s(self):
        """Nominal duration; the played one differs by the frequency rounding."""
        return self.cycles / self.frequency_hz


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


def _overlapping(blocks, start_ns, end_ns):
    return [block for block in blocks if block.times_ns[-1] >= start_ns and block.times_ns[0] <= end_ns]


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

    @property
    def earliest_ns(self):
        """Time of the oldest VOUT sample, or None without samples."""
        return int(self.vout_blocks[0].times_ns[0]) if self.vout_blocks else None

    def add(self, block: VoutBlock | EdgeBlock):
        if not len(block.times_ns):
            return
        (self.vout_blocks if isinstance(block, VoutBlock) else self.edge_blocks).append(block)
        self.latest_ns = max(self.latest_ns, int(block.times_ns[-1]))
        oldest_ns = self.latest_ns - self.span_ns
        for blocks in (self.vout_blocks, self.edge_blocks):
            while blocks and blocks[0].times_ns[-1] < oldest_ns:
                blocks.popleft()

    def set_span(self, span_s):
        self.span_ns = int(span_s * 1e9)

    def vout(self, start_ns, end_ns):
        """Times and volts of the samples within [start_ns, end_ns]."""
        blocks = _overlapping(self.vout_blocks, start_ns, end_ns)
        times = _concatenate(blocks, "times_ns", np.int64)
        volts = _concatenate(blocks, "volts", np.float64)
        inside = (times >= start_ns) & (times <= end_ns)
        return times[inside], volts[inside]

    def out3(self, start_ns, end_ns):
        """Edges within [start_ns, end_ns] and the level before them, or None if unknown."""
        earlier = [block for block in self.edge_blocks if block.times_ns[0] < start_ns]
        blocks = earlier[-1:] + _overlapping([b for b in self.edge_blocks if b.times_ns[0] >= start_ns], start_ns, end_ns)
        times = _concatenate(blocks, "times_ns", np.int64)
        levels = _concatenate(blocks, "levels", np.bool_)
        before = np.searchsorted(times, start_ns)
        after = np.searchsorted(times, end_ns, side="right")
        initial = bool(levels[before - 1]) if before else None
        return times[before:after], levels[before:after], initial

    def out3_frequency(self, start_ns, end_ns):
        """Frequency between consecutive rising edges within [start_ns, end_ns], timed at the later edge.

        Each edge block holds one uninterrupted recording, so periods are only measured within a block.
        """
        times, hertz = [], []
        for block in _overlapping(self.edge_blocks, start_ns, end_ns):
            rising = block.times_ns[block.levels]
            times.append(rising[1:])
            hertz.append(1e9 / np.diff(rising))
        if not times:
            return np.empty(0, np.int64), np.empty(0)
        times, hertz = np.concatenate(times), np.concatenate(hertz)
        inside = (times >= start_ns) & (times <= end_ns)
        return times[inside], hertz[inside]
