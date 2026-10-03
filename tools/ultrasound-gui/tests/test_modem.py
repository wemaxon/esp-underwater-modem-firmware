import unittest

import numpy as np

import support  # noqa: F401  (import path setup)
from ultrasound_gui.model import EdgeBlock, StreamHistory
from ultrasound_gui.modem import bfsk, framing
from ultrasound_gui.modem.bfsk import BfskSettings

CLOCK_HZ = 20_000_000
SETTINGS = BfskSettings(symbol_ms=5.0, preamble_bits=16, max_payload=16)


def zero_crossings(tones, start_ns):
    """OUT3 edges of the tones as the device plays them."""
    half_periods = np.concatenate([np.full(2 * tone.cycles, 1 / (2 * tone.played_hz(CLOCK_HZ))) for tone in tones])
    times = start_ns + np.round(np.concatenate(([0.0], np.cumsum(half_periods[:-1]))) * 1e9 / 100).astype(np.int64) * 100
    return EdgeBlock(times, np.arange(len(times)) % 2 == 0)


def noise(start_ns, end_ns, rate_hz, seed=2):
    """Random OUT3 chatter, like the zero-crossing comparator without a signal."""
    random = np.random.default_rng(seed)
    times = np.sort(random.integers(start_ns, end_ns, int((end_ns - start_ns) / 1e9 * rate_hz)))
    times = np.unique(times // 100) * 100
    return EdgeBlock(times, np.arange(len(times)) % 2 == 0)


def history_with(*blocks):
    history = StreamHistory(span_s=60)
    for block in sorted(blocks, key=lambda block: block.times_ns[0]):
        history.add(block)
    return history


def frame_tones(payload, settings=SETTINGS):
    return bfsk.modulate(framing.frame_bits(payload, settings.preamble_bits), settings, CLOCK_HZ)


class FramingTests(unittest.TestCase):
    def test_crc_matches_the_standard_check_value(self):
        self.assertEqual(framing.crc16(b"123456789"), 0x29B1)

    def test_frame_layout(self):
        bits = framing.frame_bits(b"\xA5", preamble_bits=4)
        self.assertEqual(len(bits), framing.frame_length_bits(1, 4))
        self.assertEqual(bits[:4].tolist(), [1, 0, 1, 0])
        self.assertEqual(framing.from_bits(bits[4:20]), b"\x2D\xD4")
        self.assertEqual(framing.from_bits(bits[20:36]), b"\x01\xA5")
        self.assertEqual(framing.from_bits(bits[36:]), framing.crc16(b"\x01\xA5").to_bytes(2, "big"))
        with self.assertRaises(ValueError):
            framing.frame_bits(b"", 4)


class ModulationTests(unittest.TestCase):
    def test_runs_of_equal_bits_become_one_tone(self):
        tones = bfsk.modulate([1, 1, 0, 1, 1, 1], SETTINGS, CLOCK_HZ)
        self.assertEqual([tone.frequency_hz for tone in tones], [41_000, 39_000, 41_000])

    def test_symbol_boundaries_stay_on_time(self):
        bits = framing.frame_bits(bytes(range(16)), SETTINGS.preamble_bits)
        tones = bfsk.modulate(bits, SETTINGS, CLOCK_HZ)
        played_s = sum(tone.cycles / tone.played_hz(CLOCK_HZ) for tone in tones)
        self.assertAlmostEqual(played_s, len(bits) * SETTINGS.symbol_ms / 1000, delta=1 / 39_000)

    def test_rejects_invalid_settings(self):
        for changes in ({"shift_hz": 0}, {"center_hz": 12_000, "shift_hz": 3_000}, {"symbol_ms": 0.5},
                        {"preamble_bits": 7}, {"max_payload": 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                BfskSettings(**changes)


class DecoderTests(unittest.TestCase):
    def decode(self, history, start_ns=0):
        """Decodes up to a few symbols after the last edge, as if the stream went on silently."""
        return bfsk.decode(history, SETTINGS, start_ns, history.latest_ns + 3 * SETTINGS.symbol_ns)

    def test_decodes_a_clean_frame(self):
        start_ns = 37_000_000
        frames, resume_ns = self.decode(history_with(zero_crossings(frame_tones(b"Hello"), start_ns)))
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].payload, b"Hello")
        self.assertTrue(frames[0].crc_ok)
        self.assertAlmostEqual(frames[0].start_ns, start_ns, delta=SETTINGS.symbol_ns / 4)
        self.assertGreater(frames[0].quality, 0.9)
        self.assertGreaterEqual(resume_ns, frames[0].start_ns)

    def test_decodes_despite_frequency_offset_and_noise(self):
        offset = BfskSettings(center_hz=40_300, symbol_ms=SETTINGS.symbol_ms, preamble_bits=SETTINGS.preamble_bits)
        signal = zero_crossings(frame_tones(b"\x00\xFFdata", offset), 50_000_000)    # transmitter tones 300 Hz high
        end_ns = int(signal.times_ns[-1]) + 50_000_000
        history = history_with(noise(0, 49_000_000, 60_000), signal, noise(int(signal.times_ns[-1]) + 1_000_000, end_ns, 60_000, seed=3))
        frames, _ = self.decode(history)
        self.assertEqual([(frame.payload, frame.crc_ok) for frame in frames], [(b"\x00\xFFdata", True)])

    def test_finds_consecutive_frames(self):
        first = zero_crossings(frame_tones(b"one"), 10_000_000)
        second = zero_crossings(frame_tones(b"two"), int(first.times_ns[-1]) + 20_000_000)
        frames, _ = self.decode(history_with(first, second))
        self.assertEqual([frame.payload for frame in frames], [b"one", b"two"])

    def test_reports_a_corrupted_frame(self):
        bits = framing.frame_bits(b"Hello", SETTINGS.preamble_bits)
        bits[-1] ^= 1
        frames, _ = self.decode(history_with(zero_crossings(bfsk.modulate(bits, SETTINGS, CLOCK_HZ), 0)))
        self.assertEqual(len(frames), 1)
        self.assertFalse(frames[0].crc_ok)

    def test_waits_for_a_frame_still_being_received(self):
        signal = zero_crossings(frame_tones(b"Hello"), 20_000_000)
        half = signal.times_ns[len(signal.times_ns) // 2]
        partial = history_with(EdgeBlock(signal.times_ns[signal.times_ns < half], signal.levels[signal.times_ns < half]))
        frames, resume_ns = self.decode(partial)
        self.assertEqual(frames, [])
        self.assertLessEqual(resume_ns, 20_000_000 + SETTINGS.symbol_ns)
        frames, _ = self.decode(history_with(signal), resume_ns)
        self.assertEqual([frame.payload for frame in frames], [b"Hello"])

    def test_noise_alone_gives_no_frames(self):
        frames, resume_ns = self.decode(history_with(noise(0, 2_000_000_000, 60_000)))
        self.assertEqual(frames, [])
        self.assertGreater(resume_ns, 1_000_000_000)


if __name__ == "__main__":
    unittest.main()
