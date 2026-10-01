import unittest

import numpy as np

import support  # noqa: F401  (import path setup)
from ultrasound_gui.model import StreamHistory, VoutBlock
from ultrasound_gui.trigger import DATA_LATENCY_NS, LevelTrigger, SingleShot

PERIOD_NS = 50_000


def history_with(volts):
    history = StreamHistory()
    history.add(VoutBlock(PERIOD_NS * np.arange(len(volts)), volts))
    return history


class LevelTriggerTests(unittest.TestCase):
    def test_rising_crossing_is_interpolated(self):
        times = PERIOD_NS * np.arange(4)
        self.assertEqual(LevelTrigger(1.0).find(times, np.array([0.5, 0.5, 1.5, 1.5])), 75_000)

    def test_needs_to_be_below_the_hysteresis_first(self):
        trigger = LevelTrigger(1.0, hysteresis_v=0.1)
        times = PERIOD_NS * np.arange(6)
        self.assertIsNone(trigger.find(times, np.array([1.2, 0.95, 1.2, 0.95, 1.2, 1.2])))
        self.assertEqual(trigger.find(times, np.array([1.2, 0.95, 1.2, 0.8, 1.2, 1.2])), 4 * PERIOD_NS - 25_000)

    def test_no_crossing(self):
        times = PERIOD_NS * np.arange(3)
        self.assertIsNone(LevelTrigger(1.0).find(times, np.array([0.1, 0.2, 0.3])))
        self.assertIsNone(LevelTrigger(1.0).find(times[:0], np.array([])))


class SingleShotTests(unittest.TestCase):
    def test_completes_once_the_window_after_the_trigger_arrived(self):
        volts = np.where(np.arange(4000) >= 1000, 2.0, 0.2)      # rises at 50 ms
        shot = SingleShot(LevelTrigger(1.0), pre_ns=10_000_000, post_ns=40_000_000)
        early = history_with(volts[:1100])
        self.assertIsNone(shot.update(early))
        self.assertTrue(shot.triggered)
        late = history_with(volts)
        self.assertEqual(shot.update(late), shot.trigger_ns)
        self.assertGreaterEqual(late.latest_ns, shot.trigger_ns + 40_000_000 + DATA_LATENCY_NS)
        self.assertAlmostEqual(shot.trigger_ns, 1000 * PERIOD_NS, delta=PERIOD_NS)

    def test_ignores_crossings_without_pre_trigger_data(self):
        volts = np.where(np.arange(400) >= 10, 2.0, 0.2)         # rises at 0.5 ms
        shot = SingleShot(LevelTrigger(1.0), pre_ns=10_000_000, post_ns=1_000_000)
        self.assertIsNone(shot.update(history_with(volts)))
        self.assertFalse(shot.triggered)

    def test_force_triggers_at_the_newest_data(self):
        history = history_with(np.full(100, 0.2))
        shot = SingleShot(LevelTrigger(1.0), pre_ns=0, post_ns=0)
        shot.force(history)
        self.assertEqual(shot.trigger_ns, history.latest_ns)


if __name__ == "__main__":
    unittest.main()
