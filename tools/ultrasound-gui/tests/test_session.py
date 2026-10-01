from struct import pack
import unittest

from support import wait_until
from ultrasound_gui.afe import SETTINGS
from ultrasound_gui.model import EdgeBlock, ToneBurst, VoutBlock
from ultrasound_gui.session import AcquisitionState, ConnectionState, Session
from ultrasound_gui.simulator import SimulatedDevice
from ultrasound_gui.tf_protocol import DEVICE_ERROR, OVERFLOW, STREAM_END, TRANSMIT, VOUT_SAMPLES, Packet


class ScriptedDevice(SimulatedDevice):
    """Simulator with optional scripted replies."""

    def __init__(self, transmit_result=None, silent_stream_start=False, end_stream_with=None):
        super().__init__()
        self.transmit_result = transmit_result
        self.silent_stream_start = silent_stream_start
        self.end_stream_with = end_stream_with

    def _stream_start(self, packet):
        if self.silent_stream_start:
            return
        super()._stream_start(packet)
        if self.end_stream_with is not None:
            self.stream_start = None
            self._event(STREAM_END, bytes([self.end_stream_with]))

    def _transmit(self, packet):
        if self.transmit_result is None:
            super()._transmit(packet)
        else:
            self._respond(packet, bytes([self.transmit_result]))


class LeftoverStreamDevice(SimulatedDevice):
    """Still streaming from a previous session when the host connects."""

    def __init__(self):
        super().__init__()
        self._event(VOUT_SAMPLES, pack("<QHH", 0, 1, 100))


class SessionTests(unittest.TestCase):
    def connect(self, device=None, timeout=3.0):
        device = device or SimulatedDevice()
        session = Session(lambda: device, timeout=timeout)
        session.open()
        self.addCleanup(self.close, session)
        wait_until(lambda: session.status.connection == ConnectionState.CONNECTED)
        return session

    def close(self, session):
        session.close()
        session.thread.join(2)
        self.assertFalse(session.thread.is_alive())

    def test_connects_and_forwards_device_logs(self):
        session = self.connect()
        self.assertEqual(session.status.device_name, SimulatedDevice.NAME)
        wait_until(lambda: session.logs.qsize() > 0)
        self.assertIn("Device connected", "".join(session.take_logs()))

    def test_reads_and_applies_the_receiver_configuration(self):
        device = SimulatedDevice()
        session = self.connect(device)
        wait_until(lambda: session.status.afe is not None)
        hysteresis = next(setting for setting in SETTINGS if setting.label == "Zero-crossing hysteresis")
        session.apply_afe(session.status.afe.with_value(hysteresis, 7))
        wait_until(lambda: session.status.afe.get(hysteresis) == 7)
        self.assertEqual(device.afe_registers[5] & 0x07, 7)
        self.assertEqual(session.status.error, "")

    def test_stream_delivers_vout_and_out3_until_stopped(self):
        session = self.connect()
        session.start_stream()
        wait_until(lambda: session.status.acquisition == AcquisitionState.STREAMING)
        blocks = []
        wait_until(lambda: blocks.extend(session.take_blocks()) or
                   {type(block) for block in blocks} == {VoutBlock, EdgeBlock}, timeout=3)
        session.stop_stream()
        wait_until(lambda: session.status.acquisition == AcquisitionState.STOPPED)
        self.assertEqual(session.status.error, "")
        self.assertEqual(session.status.connection, ConnectionState.CONNECTED)

    def test_device_ending_the_stream_is_reported(self):
        session = self.connect(ScriptedDevice(end_stream_with=OVERFLOW))
        session.start_stream()
        wait_until(lambda: session.status.error != "")
        self.assertIn("buffer overflow", session.status.error)
        self.assertEqual(session.status.acquisition, AcquisitionState.STOPPED)
        self.assertEqual(session.status.connection, ConnectionState.CONNECTED)

    def test_leftover_stream_data_is_ignored_while_connecting(self):
        session = self.connect(LeftoverStreamDevice())
        self.assertEqual(session.take_blocks(), [])
        self.assertEqual(session.status.error, "")

    def test_transmit_during_stream(self):
        session = self.connect()
        session.start_stream()
        session.transmit(ToneBurst())
        wait_until(lambda: session.status.transmit_message == "Complete")
        self.assertEqual(session.status.acquisition, AcquisitionState.STREAMING)

    def test_transmit_failure_keeps_connection(self):
        session = self.connect(ScriptedDevice(transmit_result=DEVICE_ERROR))
        session.transmit(ToneBurst())
        wait_until(lambda: session.status.transmit_message == "Device error")
        self.assertFalse(session.status.transmitting)
        self.assertEqual(session.status.connection, ConnectionState.CONNECTED)

    def test_close_stops_the_stream(self):
        device = SimulatedDevice()
        session = self.connect(device)
        session.start_stream()
        wait_until(lambda: session.status.acquisition == AcquisitionState.STREAMING)
        session.close()
        self.assertTrue(session.done.wait(1))
        self.assertIsNone(device.stream_start)
        self.assertEqual(session.status.error, "")

    def test_close_waits_for_transmission(self):
        session = self.connect()
        session.transmit(ToneBurst())
        wait_until(lambda: session.status.transmitting)
        session.close()
        self.assertTrue(session.done.wait(1))
        self.assertEqual(session.status.transmit_message, "Complete")

    def test_unanswered_request_disconnects_with_error(self):
        session = self.connect(ScriptedDevice(silent_stream_start=True), timeout=0.2)
        session.start_stream()
        self.assertTrue(session.done.wait(2))
        self.assertEqual(session.status.connection, ConnectionState.DISCONNECTED)
        self.assertEqual(session.status.error, "Device response timed out")

    def test_commands_before_connection_are_ignored(self):
        session = Session(SimulatedDevice)
        session.start_stream()
        session.transmit(ToneBurst())
        session.open()
        self.addCleanup(self.close, session)
        wait_until(lambda: session.status.connection == ConnectionState.CONNECTED)
        self.assertEqual(session.status.acquisition, AcquisitionState.STOPPED)
        self.assertFalse(session.status.transmitting)

    def test_events_need_a_device_frame_id(self):
        session = Session(SimulatedDevice)
        with self.assertRaises(ValueError):
            session._receive(Packet(STREAM_END, 7, b"\x00"))
        with self.assertRaises(ValueError):
            session._receive(Packet(TRANSMIT, 7, b"\x00"))     # response nobody asked for


if __name__ == "__main__":
    unittest.main()
