from struct import pack
import unittest
from unittest import mock

import numpy as np

import support
from ultrasound_gui import tf_protocol
from ultrasound_gui.model import DeviceInfo, ToneBurst
from ultrasound_gui.tf_protocol import (
    CAPTURE, GET_DEVICE_INFO, LOG, STOP, VERSION, Decoder, Packet, ProtocolError,
    decode_capture, decode_info, decode_log, encode, encode_tone,
)

INFO = DeviceInfo("Test", 1_000_000, 1023)


class FramingTests(unittest.TestCase):
    def test_round_trip(self):
        packets = [Packet(GET_DEVICE_INFO, 1), Packet(CAPTURE, 0x7FFF, support.capture_payload()), Packet(LOG, 0x8000, b"x" * 255)]
        stream = b"".join(encode(packet) for packet in packets)
        self.assertEqual(Decoder().feed(stream), packets)

    def test_frames_split_across_reads(self):
        data = encode(Packet(CAPTURE, 3, support.capture_payload()))
        decoder = Decoder()
        self.assertEqual(decoder.feed(data[:5]), [])
        self.assertEqual(decoder.feed(data[5:]), [Packet(CAPTURE, 3, support.capture_payload())])

    def test_stale_partial_frame_is_discarded(self):
        data = encode(Packet(STOP, 9, b"\0"))
        decoder = Decoder(timeout=0.5)
        with mock.patch.object(tf_protocol, "monotonic", return_value=100.0):
            decoder.feed(data[:4])
        with mock.patch.object(tf_protocol, "monotonic", return_value=101.0):
            self.assertEqual(decoder.feed(data), [Packet(STOP, 9, b"\0")])


class PayloadTests(unittest.TestCase):
    def test_tone(self):
        self.assertEqual(encode_tone(ToneBurst(40_000, 32)), bytes.fromhex("409c00002000"))

    def test_device_info(self):
        info = decode_info(pack("<BIH", VERSION, 1_000_000, 1023) + b"Dev")
        self.assertEqual(info, DeviceInfo("Dev", 1_000_000, 1023))

    def test_device_info_rejects_other_versions_and_limits(self):
        for payload in (
            pack("<BIH", VERSION - 1, 1_000_000, 1023) + b"Dev",
            pack("<BIH", VERSION, 0, 1023) + b"Dev",
            pack("<BIH", VERSION, 1_000_000, 0) + b"Dev",
            pack("<BIH", VERSION, 1_000_000, 1023),
        ):
            with self.subTest(payload=payload.hex()), self.assertRaises(ProtocolError):
                decode_info(payload)

    def test_capture(self):
        capture = decode_capture(support.capture_payload(initial=1), INFO)
        self.assertTrue(capture.initial_high)
        self.assertEqual(capture.duration_ticks, 1000)
        np.testing.assert_array_equal(capture.edges, [100, 200, 300, 400])

    def test_capture_rejects_malformed_payloads(self):
        valid = support.capture_payload()
        for payload in (valid[:7], valid[:-1], valid + b"\0", b"\x01" + valid[1:], valid[:1] + b"\x02" + valid[2:]):
            with self.subTest(payload=payload.hex()), self.assertRaises(ProtocolError):
                decode_capture(payload, INFO)
        with self.assertRaises(ProtocolError):
            decode_capture(valid, DeviceInfo("Small", 1_000_000, 3))

    def test_log_strips_terminal_colors(self):
        self.assertEqual(decode_log(b"\x1b[0;32mI (1) TAG: ok\x1b[0m\n"), "I (1) TAG: ok\n")
        for payload in (b"", b"x" * 256):
            with self.assertRaises(ProtocolError):
                decode_log(payload)


if __name__ == "__main__":
    unittest.main()
