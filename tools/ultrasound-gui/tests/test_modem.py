import unittest
from dataclasses import replace

import numpy as np

import support  # noqa: F401  (import path setup)
from ultrasound_gui.model import EdgeBlock, StreamHistory
from ultrasound_gui.modem import bfsk, fec, framing
from ultrasound_gui.modem.bfsk import BfskSettings
from ultrasound_gui.modem.fec import CodingSettings
from ultrasound_gui.modem.framing import FramingSettings
from ultrasound_gui.modem.link import LinkSettings

CLOCK_HZ = 20_000_000
LINK = LinkSettings(BfskSettings(symbol_ms=5.0), CodingSettings(), FramingSettings(preamble_bits=16, max_payload=16))


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


def frame_tones(payload, link=LINK):
    return bfsk.modulate(link.frame_bits(payload), link.modulation, CLOCK_HZ)


def body_start(payload_bytes, link=LINK):
    return link.frame_length_bits(payload_bytes) - framing.body_bits(payload_bytes, link.coding)


class FramingTests(unittest.TestCase):
    def test_crc_matches_the_standard_check_value(self):
        self.assertEqual(framing.crc16(b"123456789"), 0x29B1)

    def test_frame_layout(self):
        coding = CodingSettings()
        bits = framing.frame_bits(b"\xA5", FramingSettings(preamble_bits=4), coding)
        self.assertEqual(len(bits), framing.frame_length_bits(1, FramingSettings(preamble_bits=4), coding))
        self.assertEqual(bits[:4].tolist(), [1, 0, 1, 0])
        self.assertEqual(framing.from_bits(bits[4:20]), b"\x2D\xD4")
        header_end = 20 + framing.header_bits(coding)
        self.assertEqual(framing.decode_length(2.0 * bits[20:header_end] - 1, coding), 1)
        self.assertEqual(len(bits) - header_end, framing.body_bits(1, coding))
        self.assertEqual(framing.decode_body(2.0 * bits[header_end:] - 1, 1, coding), (b"\xA5", True))

    def test_rejects_payloads_outside_the_frame_size(self):
        for payload in (b"", bytes(17)):
            with self.subTest(size=len(payload)), self.assertRaises(ValueError):
                LINK.frame_bits(payload)

    def test_rejects_invalid_settings(self):
        for changes in ({"preamble_bits": 7}, {"max_payload": 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                FramingSettings(**changes)


class FecTests(unittest.TestCase):
    DATA = framing.to_bits(b"forward error correction")

    def roundtrip(self, coding, damage=lambda soft: soft):
        soft = damage(2.0 * fec.encode(self.DATA, coding) - 1)
        return fec.decode(soft, len(self.DATA), coding)

    def test_encodes_the_standard_code(self):
        """The impulse response is the generators' taps, newest first: 171 = 1111001, 133 = 1011011."""
        coded = fec.encode([1], CodingSettings(interleaver=0))
        self.assertEqual(coded.tolist(), [1, 1, 1, 0, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1])

    def test_rates_send_their_share_of_code_bits(self):
        for rate, data_per_coded in (("Off", 1), ("1/2", 1 / 2), ("2/3", 2 / 3), ("3/4", 3 / 4)):
            with self.subTest(rate=rate):
                coding = CodingSettings(rate=rate)
                coded = len(fec.encode(self.DATA, coding))
                self.assertEqual(coded, fec.coded_length(len(self.DATA), coding))
                tail = 0 if rate == "Off" else fec.TAIL_BITS
                self.assertAlmostEqual((len(self.DATA) + tail) / coded, data_per_coded, delta=0.01)
                np.testing.assert_array_equal(self.roundtrip(coding), self.DATA)

    def test_corrects_scattered_errors_and_weak_values(self):
        def damage(soft):
            soft[::12] *= -1                # every twelfth code bit wrong
            soft[5::12] *= 0.1              # others barely recognizable
            return soft
        np.testing.assert_array_equal(self.roundtrip(CodingSettings(interleaver=0), damage), self.DATA)

    def test_punctured_codes_still_correct_errors(self):
        def damage(soft):
            soft[::60] *= -1                # fewer than at rate 1/2: punctured codes correct less
            return soft
        for rate in ("2/3", "3/4"):
            with self.subTest(rate=rate):
                np.testing.assert_array_equal(self.roundtrip(CodingSettings(rate=rate), damage), self.DATA)

    def test_interleaving_spreads_bursts(self):
        def burst(soft):
            soft[40:50] *= -1               # ten consecutive channel bits wrong
            return soft
        np.testing.assert_array_equal(self.roundtrip(CodingSettings(interleaver=16), burst), self.DATA)
        self.assertFalse(np.array_equal(self.roundtrip(CodingSettings(interleaver=0), burst), self.DATA))

    def test_rejects_invalid_settings(self):
        for changes in ({"rate": "5/6"}, {"interleaver": 5}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                CodingSettings(**changes)


class LinkSettingsTests(unittest.TestCase):
    def test_round_trips_through_json(self):
        link = LinkSettings(BfskSettings(center_hz=45_000, symbol_ms=20.0), CodingSettings("3/4", 8), FramingSettings(32, 8))
        self.assertEqual(LinkSettings.from_json(link.to_json()), link)

    def test_rejects_invalid_files(self):
        valid = LinkSettings().to_json()
        for text in ("", "[]", valid.replace('"rate": "1/2"', '"rate": "1/9"'), valid.replace('"modulation"', '"other"')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                LinkSettings.from_json(text)

    def test_frame_duration_follows_the_code_rate(self):
        half = LINK.frame_duration_s(16)
        uncoded = replace(LINK, coding=CodingSettings(rate="Off")).frame_duration_s(16)
        self.assertGreater(half, 1.8 * uncoded)


class ModulationTests(unittest.TestCase):
    def test_runs_of_equal_bits_become_one_tone(self):
        tones = bfsk.modulate([1, 1, 0, 1, 1, 1], LINK.modulation, CLOCK_HZ)
        self.assertEqual([tone.frequency_hz for tone in tones], [41_000, 39_000, 41_000])

    def test_symbol_boundaries_stay_on_time(self):
        bits = LINK.frame_bits(bytes(range(16)))
        tones = bfsk.modulate(bits, LINK.modulation, CLOCK_HZ)
        played_s = sum(tone.cycles / tone.played_hz(CLOCK_HZ) for tone in tones)
        self.assertAlmostEqual(played_s, len(bits) * LINK.modulation.symbol_ms / 1000, delta=1 / 39_000)

    def test_rejects_invalid_settings(self):
        for changes in ({"shift_hz": 0}, {"center_hz": 12_000, "shift_hz": 3_000}, {"symbol_ms": 0.5},
                        {"shift_hz": 400, "symbol_ms": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                BfskSettings(**changes)


class DecoderTests(unittest.TestCase):
    def decode(self, history, start_ns=0, link=LINK):
        """Decodes up to a few symbols after the last edge, as if the stream went on silently."""
        return bfsk.decode(history, link, CLOCK_HZ, start_ns, history.latest_ns + 3 * link.modulation.symbol_ns)

    def test_decodes_a_clean_frame(self):
        start_ns = 37_000_000
        frames, resume_ns = self.decode(history_with(zero_crossings(frame_tones(b"Hello"), start_ns)))
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].payload, b"Hello")
        self.assertTrue(frames[0].crc_ok)
        self.assertAlmostEqual(frames[0].start_ns, start_ns, delta=LINK.modulation.symbol_ns / 4)
        self.assertGreater(frames[0].quality, 0.9)
        self.assertEqual(frames[0].offset_hz, 0)
        self.assertGreaterEqual(resume_ns, frames[0].start_ns)

    def test_decodes_with_every_coding(self):
        for rate in fec.PUNCTURING:
            for interleaver in (0, 32):
                with self.subTest(rate=rate, interleaver=interleaver):
                    link = replace(LINK, coding=CodingSettings(rate, interleaver))
                    frames, _ = self.decode(history_with(zero_crossings(frame_tones(b"Hello", link), 0)), link=link)
                    self.assertEqual([(frame.payload, frame.crc_ok) for frame in frames], [(b"Hello", True)])

    def test_decodes_despite_frequency_offset_and_noise(self):
        transmitter = replace(LINK, modulation=replace(LINK.modulation, center_hz=40_300))    # tones 300 Hz high
        signal = zero_crossings(frame_tones(b"\x00\xFFdata", transmitter), 50_000_000)
        end_ns = int(signal.times_ns[-1]) + 50_000_000
        history = history_with(noise(0, 49_000_000, 60_000), signal, noise(int(signal.times_ns[-1]) + 1_000_000, end_ns, 60_000, seed=3))
        frames, _ = self.decode(history)
        self.assertEqual([(frame.payload, frame.crc_ok, frame.offset_hz) for frame in frames], [(b"\x00\xFFdata", True, 300)])

    def test_corrects_wrong_symbols(self):
        bits = LINK.frame_bits(b"Hello")
        bits[body_start(5)::9] ^= 1         # every ninth body symbol wrong
        frames, _ = self.decode(history_with(zero_crossings(bfsk.modulate(bits, LINK.modulation, CLOCK_HZ), 0)))
        self.assertEqual([(frame.payload, frame.crc_ok) for frame in frames], [(b"Hello", True)])

    def test_finds_consecutive_frames(self):
        first = zero_crossings(frame_tones(b"one"), 10_000_000)
        second = zero_crossings(frame_tones(b"two"), int(first.times_ns[-1]) + 20_000_000)
        frames, _ = self.decode(history_with(first, second))
        self.assertEqual([frame.payload for frame in frames], [b"one", b"two"])

    def test_reports_a_corrupted_frame(self):
        bits = LINK.frame_bits(b"Hello")
        bits[body_start(5):] = fec.encode(framing.to_bits(b"Hello\x00\x00"), LINK.coding)     # wrong CRC
        frames, _ = self.decode(history_with(zero_crossings(bfsk.modulate(bits, LINK.modulation, CLOCK_HZ), 0)))
        self.assertEqual([(frame.payload, frame.crc_ok) for frame in frames], [(b"Hello", False)])

    def test_waits_for_a_frame_still_being_received(self):
        signal = zero_crossings(frame_tones(b"Hello"), 20_000_000)
        half = signal.times_ns[len(signal.times_ns) // 2]
        partial = history_with(EdgeBlock(signal.times_ns[signal.times_ns < half], signal.levels[signal.times_ns < half]))
        frames, resume_ns = self.decode(partial)
        self.assertEqual(frames, [])
        self.assertLessEqual(resume_ns, 20_000_000 + LINK.modulation.symbol_ns)
        frames, _ = self.decode(history_with(signal), resume_ns)
        self.assertEqual([frame.payload for frame in frames], [b"Hello"])

    def test_noise_alone_gives_no_frames(self):
        frames, resume_ns = self.decode(history_with(noise(0, 2_000_000_000, 60_000)))
        self.assertEqual(frames, [])
        self.assertGreater(resume_ns, 1_000_000_000)


if __name__ == "__main__":
    unittest.main()
