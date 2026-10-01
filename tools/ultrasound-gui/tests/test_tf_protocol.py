from struct import pack
import unittest
from unittest import mock

import numpy as np

from support import INFO
from ultrasound_gui import tf_protocol
from ultrasound_gui.model import DeviceInfo, ToneBurst
from ultrasound_gui.tf_protocol import (
    GET_DEVICE_INFO, LOG, OUT3_EDGES, STREAM_STOP, VERSION, VOUT_SAMPLES, Decoder, Packet, ProtocolError,
    decode_edges, decode_info, decode_log, decode_result, decode_vout, encode, encode_tone,
)

VOUT = pack("<QHHH", 1000, 2, 1234, 3300)
EDGES = pack("<QBHHH", 1000, 1, 3, 1, 2)


class FramingTests(unittest.TestCase):
    def test_round_trip(self):
        packets = [Packet(GET_DEVICE_INFO, 1), Packet(VOUT_SAMPLES, 0x8000, VOUT), Packet(LOG, 0xFFFF, b"x" * 255)]
        stream = b"".join(encode(packet) for packet in packets)
        self.assertEqual(Decoder().feed(stream), packets)

    def test_frames_split_across_reads(self):
        data = encode(Packet(OUT3_EDGES, 0x8001, EDGES))
        decoder = Decoder()
        self.assertEqual(decoder.feed(data[:5]), [])
        self.assertEqual(decoder.feed(data[5:]), [Packet(OUT3_EDGES, 0x8001, EDGES)])

    def test_stale_partial_frame_is_discarded(self):
        data = encode(Packet(STREAM_STOP, 9, b"\0"))
        decoder = Decoder(timeout=0.5)
        with mock.patch.object(tf_protocol, "monotonic", return_value=100.0):
            decoder.feed(data[:4])
        with mock.patch.object(tf_protocol, "monotonic", return_value=101.0):
            self.assertEqual(decoder.feed(data), [Packet(STREAM_STOP, 9, b"\0")])


class PayloadTests(unittest.TestCase):
    def test_tone(self):
        self.assertEqual(encode_tone(ToneBurst(40_000, 32)), bytes.fromhex("409c00002000"))

    def test_device_info(self):
        self.assertEqual(decode_info(pack("<BII", VERSION, 20_000, 10_000_000) + b"Dev"), DeviceInfo("Dev", 20_000, 10_000_000))
        for payload in (
            pack("<BII", VERSION - 1, 20_000, 10_000_000) + b"Dev",
            pack("<BII", VERSION, 0, 10_000_000) + b"Dev",
            pack("<BII", VERSION, 20_000, 3) + b"Dev",
            pack("<BII", VERSION, 20_000, 10_000_000),
        ):
            with self.subTest(payload=payload.hex()), self.assertRaises(ProtocolError):
                decode_info(payload)

    def test_vout_samples(self):
        block = decode_vout(VOUT, INFO)
        np.testing.assert_array_equal(block.times_ns, [1000, 51_000])
        np.testing.assert_allclose(block.volts, [1.234, 3.3])
        for payload in (VOUT[:9], VOUT[:-1], VOUT + b"\0", pack("<QH", 0, 0)):
            with self.subTest(payload=payload.hex()), self.assertRaises(ProtocolError):
                decode_vout(payload, INFO)

    def test_out3_edges(self):
        block = decode_edges(EDGES, INFO)
        np.testing.assert_array_equal(block.times_ns, [1000, 1100, 1300])
        np.testing.assert_array_equal(block.levels, [True, False, True])
        single = decode_edges(pack("<QBH", 5, 0, 1), INFO)
        np.testing.assert_array_equal(single.times_ns, [5])
        self.assertFalse(single.levels[0])
        for payload in (EDGES[:10], EDGES[:-1], pack("<QBH", 0, 2, 1), pack("<QBH", 0, 1, 0), pack("<QBHH", 0, 1, 2, 0)):
            with self.subTest(payload=payload.hex()), self.assertRaises(ProtocolError):
                decode_edges(payload, INFO)

    def test_result(self):
        self.assertEqual(decode_result(b"\x03"), 3)
        for payload in (b"", b"\x00\x00", b"\x05"):
            with self.subTest(payload=payload.hex()), self.assertRaises(ProtocolError):
                decode_result(payload)

    def test_log_strips_terminal_colors(self):
        self.assertEqual(decode_log(b"\x1b[0;32mI (1) TAG: ok\x1b[0m\n"), "I (1) TAG: ok\n")
        for payload in (b"", b"x" * 256):
            with self.assertRaises(ProtocolError):
                decode_log(payload)


if __name__ == "__main__":
    unittest.main()
