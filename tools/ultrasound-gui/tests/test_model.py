import unittest

import numpy as np

import support  # noqa: F401  (import path setup)
from ultrasound_gui.model import EdgeBlock, StreamHistory, ToneBurst, VoutBlock


def edges(start_ns, count, interval_ns, first_level=True):
    return EdgeBlock(start_ns + interval_ns * np.arange(count), (np.arange(count) % 2 == 0) == first_level)


class StreamHistoryTests(unittest.TestCase):
    def test_vout_window(self):
        history = StreamHistory()
        history.add(VoutBlock([0, 50_000, 100_000], [0.1, 0.2, 0.3]))
        history.add(VoutBlock([150_000, 200_000], [0.4, 0.5]))
        times, volts = history.vout(50_000, 150_000)
        np.testing.assert_array_equal(times, [50_000, 100_000, 150_000])
        np.testing.assert_allclose(volts, [0.2, 0.3, 0.4])
        self.assertEqual(history.latest_ns, 200_000)

    def test_out3_window_reports_level_before_it(self):
        history = StreamHistory()
        history.add(edges(1000, 4, 100))
        times, levels, initial = history.out3(1150, 2000)
        np.testing.assert_array_equal(times, [1200, 1300])
        np.testing.assert_array_equal(levels, [True, False])
        self.assertFalse(initial)
        self.assertIsNone(history.out3(0, 500)[2])

    def test_frequency_is_measured_within_blocks(self):
        history = StreamHistory()
        history.add(edges(0, 9, 12_500))                # 40 kHz
        history.add(edges(1_000_000, 5, 25_000))        # 20 kHz, after a gap
        times, hertz = history.out3_frequency(0, 2_000_000)
        np.testing.assert_allclose(hertz, [40_000] * 4 + [20_000] * 2)
        self.assertEqual(times[-1], 1_100_000)

    def test_old_data_is_dropped(self):
        history = StreamHistory(span_s=1.0)
        history.add(VoutBlock([0], [0.1]))
        history.add(edges(0, 2, 10))
        history.add(VoutBlock([2_000_000_000], [0.2]))
        self.assertEqual(len(history.vout(0, 3_000_000_000)[0]), 1)
        self.assertEqual(len(history.out3(0, 3_000_000_000)[0]), 0)
        history.clear()
        self.assertEqual(history.latest_ns, 0)

    def test_blocks_are_read_only(self):
        block = VoutBlock([0], [0.1])
        with self.assertRaises(ValueError):
            block.volts[0] = 1


class ToneBurstTests(unittest.TestCase):
    def test_limits(self):
        ToneBurst(40_000, 1)
        ToneBurst(1_000_000, 255)
        for frequency, cycles in ((39_999, 1), (1_000_001, 1), (40_000, 0), (40_000, 256), (40_000.0, 1)):
            with self.subTest(frequency=frequency, cycles=cycles), self.assertRaises(ValueError):
                ToneBurst(frequency, cycles)


if __name__ == "__main__":
    unittest.main()
