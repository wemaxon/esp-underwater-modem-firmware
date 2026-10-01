"""Decodes frames produced by the firmware's TinyFrame interface code (test/host).

Build the host tests first; the location can be overridden with FIRMWARE_HOST_TEST_DIR.
"""

import os
from pathlib import Path
import subprocess
import unittest

import numpy as np

import support
from ultrasound_gui.tf_protocol import (
    LOG, OK, OUT3_EDGES, OVERFLOW, STREAM_END, STREAM_START, VOUT_SAMPLES, Decoder,
    decode_edges, decode_log, decode_result, decode_vout,
)

BUILD = Path(os.environ.get("FIRMWARE_HOST_TEST_DIR", support.REPOSITORY / "build" / "host"))
EXECUTABLE = next((path for path in (BUILD / "test_tf_protocol.exe", BUILD / "test_tf_protocol") if path.is_file()), None)


@unittest.skipIf(EXECUTABLE is None, f"C host tests not built in {BUILD}")
class InteropTests(unittest.TestCase):
    def test_python_decodes_c_frames(self):
        output = subprocess.run([str(EXECUTABLE), "--frames"], check=True, capture_output=True, text=True).stdout
        decoder = Decoder()
        packets = [packet for line in output.split() for packet in decoder.feed(bytes.fromhex(line))]
        self.assertEqual([(packet.message_type, packet.frame_id) for packet in packets], [
            (STREAM_START, 5), (VOUT_SAMPLES, 0x8000), (OUT3_EDGES, 0x8001), (STREAM_END, 0x8002), (LOG, 0x8000),
        ])
        self.assertEqual(decode_result(packets[0].payload), OK)
        vout = decode_vout(packets[1].payload, support.INFO)
        np.testing.assert_array_equal(vout.times_ns, [1000, 51_000])
        np.testing.assert_allclose(vout.volts, [1.234, 3.3])
        edges = decode_edges(packets[2].payload, support.INFO)
        np.testing.assert_array_equal(edges.times_ns, [1000, 1100, 1300])
        np.testing.assert_array_equal(edges.levels, [True, False, True])
        self.assertEqual(decode_result(packets[3].payload), OVERFLOW)
        self.assertEqual(decode_log(packets[4].payload), "x" * 255)


if __name__ == "__main__":
    unittest.main()
