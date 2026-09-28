"""Decodes frames produced by the firmware's TinyFrame interface code (test/host).

Build the host tests first; the location can be overridden with FIRMWARE_HOST_TEST_DIR.
"""

import os
from pathlib import Path
import subprocess
import unittest

import numpy as np

import support
from ultrasound_gui.model import DeviceInfo
from ultrasound_gui.tf_protocol import CANCELLED, CAPTURE, LOG, Decoder, Packet, decode_capture, decode_log

BUILD = Path(os.environ.get("FIRMWARE_HOST_TEST_DIR", support.REPOSITORY / "build" / "host"))
EXECUTABLE = next((path for path in (BUILD / "test_tf_protocol.exe", BUILD / "test_tf_protocol") if path.is_file()), None)


@unittest.skipIf(EXECUTABLE is None, f"C host tests not built in {BUILD}")
class InteropTests(unittest.TestCase):
    def test_python_decodes_c_frames(self):
        output = subprocess.run([str(EXECUTABLE), "--frames"], check=True, capture_output=True, text=True).stdout
        decoder = Decoder()
        packets = [packet for line in output.split() for packet in decoder.feed(bytes.fromhex(line))]
        self.assertEqual(packets, [
            Packet(CAPTURE, 5, support.capture_payload()),
            Packet(CAPTURE, 0x7FFF, bytes([CANCELLED])),
            Packet(LOG, 0x8000, b"hello\n"),
            Packet(LOG, 0x8001, b"x" * 255),
        ])
        capture = decode_capture(packets[0].payload, DeviceInfo("C firmware", 1_000_000, 1023))
        np.testing.assert_array_equal(capture.edges, [100, 200, 300, 400])
        self.assertEqual(decode_log(packets[3].payload), "x" * 255)


if __name__ == "__main__":
    unittest.main()
