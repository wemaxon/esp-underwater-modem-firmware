import unittest

import numpy as np

import support  # noqa: F401  (import path setup)
from ultrasound_gui.model import Capture, ToneBurst


class CaptureTests(unittest.TestCase):
    def test_steps_alternate_from_initial_level(self):
        capture = Capture(1_000_000, 1000, True, np.array([100, 300]))
        times, levels = capture.steps()
        np.testing.assert_allclose(times, [0, 0.1, 0.3, 1.0])
        np.testing.assert_array_equal(levels, [1, 0, 1, 1])

    def test_frequency_from_rising_edges(self):
        capture = Capture(1_000_000, 1000, False, np.arange(12, 800, 12))
        _, kilohertz = capture.frequency()
        np.testing.assert_allclose(kilohertz, 1_000_000 / 24 / 1000)

    def test_edges_are_read_only_copies(self):
        edges = np.array([10, 20], dtype=np.uint32)
        capture = Capture(1_000_000, 100, False, edges)
        edges[0] = 99
        self.assertEqual(capture.edges[0], 10)
        self.assertFalse(capture.edges.flags.writeable)

    def test_rejects_invalid_timing(self):
        for duration, edges in ((0, []), (100, [0]), (100, [100]), (100, [20, 10])):
            with self.subTest(duration=duration, edges=edges), self.assertRaises(ValueError):
                Capture(1_000_000, duration, False, np.array(edges, dtype=np.uint32))


class ToneBurstTests(unittest.TestCase):
    def test_limits(self):
        ToneBurst(40_000, 1)
        ToneBurst(1_000_000, 255)
        for frequency, cycles in ((39_999, 1), (1_000_001, 1), (40_000, 0), (40_000, 256), (40_000.0, 1)):
            with self.subTest(frequency=frequency, cycles=cycles), self.assertRaises(ValueError):
                ToneBurst(frequency, cycles)


if __name__ == "__main__":
    unittest.main()
