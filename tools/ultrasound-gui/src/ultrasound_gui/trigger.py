"""Oscilloscope-style triggering on a stream."""

from dataclasses import dataclass

import numpy as np

from .model import StreamHistory

# Stream data can arrive somewhat after the time it describes: OUT3 edges at the
# end of a signal are sent once the device's idle limit has passed, plus USB and
# polling latency. A single shot waits this much longer before it completes.
DATA_LATENCY_NS = 50_000_000


@dataclass(frozen=True)
class LevelTrigger:
    """Fires when VOUT rises through level_v after having been below level_v - hysteresis_v."""
    level_v: float
    hysteresis_v: float = 0.05

    def find(self, times_ns, volts):
        """Time of the first trigger in the samples, interpolated between samples, or None."""
        armed = np.flatnonzero(volts < self.level_v - self.hysteresis_v)
        if not len(armed):
            return None
        above = np.flatnonzero(volts[armed[0]:] >= self.level_v)
        if not len(above):
            return None
        i = armed[0] + above[0]
        fraction = (self.level_v - volts[i - 1]) / (volts[i] - volts[i - 1])
        return round(times_ns[i - 1] + fraction * (times_ns[i] - times_ns[i - 1]))


class SingleShot:
    """Waits for one trigger and reports it once the window around it has been received.

    The trigger is only searched where pre_ns of data before it exists.
    """

    def __init__(self, trigger: LevelTrigger, pre_ns, post_ns):
        self.trigger = trigger
        self.pre_ns = pre_ns
        self.post_ns = post_ns
        self.trigger_ns = None

    @property
    def triggered(self):
        return self.trigger_ns is not None

    def force(self, history: StreamHistory):
        """Triggers at the newest data."""
        if not self.triggered:
            self.trigger_ns = history.latest_ns

    def update(self, history: StreamHistory):
        """Returns the trigger time once the window after it is complete, else None."""
        if not self.triggered and history.earliest_ns is not None:
            times, volts = history.vout(history.earliest_ns + self.pre_ns, history.latest_ns)
            self.trigger_ns = self.trigger.find(times, volts)
        if self.triggered and history.latest_ns >= self.trigger_ns + self.post_ns + DATA_LATENCY_NS:
            return self.trigger_ns
        return None
