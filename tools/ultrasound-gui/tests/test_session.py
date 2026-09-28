import unittest

import support
from support import wait_until
from ultrasound_gui.model import ToneBurst
from ultrasound_gui.tf_protocol import BUSY, CAPTURE, OVERFLOW, TIMEOUT, TRANSMIT, Packet
from ultrasound_gui.session import AcquisitionState, ConnectionState, Session
from ultrasound_gui.simulator import SimulatedDevice


class ScriptedDevice(SimulatedDevice):
    """Simulator whose capture and transmit replies can be replaced."""

    def __init__(self, capture_results=(), transmit_result=None, silent_capture=False):
        super().__init__()
        self.capture_results = list(capture_results)
        self.transmit_result = transmit_result
        self.silent_capture = silent_capture
        self.captures_requested = 0

    def _capture(self, packet):
        self.captures_requested += 1
        if self.capture_results:
            self.outbox.append(Packet(CAPTURE, packet.frame_id, bytes([self.capture_results.pop(0)])))
        else:
            super()._capture(packet)
            if self.silent_capture:
                self.capture_ready_at = float("inf")

    def _transmit(self, packet):
        if self.transmit_result is None:
            super()._transmit(packet)
        else:
            self.outbox.append(Packet(TRANSMIT, packet.frame_id, bytes([self.transmit_result])))


class SessionTests(unittest.TestCase):
    def open(self, device=None, timeout=3.0):
        device = device or SimulatedDevice()
        session = Session(lambda: device, timeout=timeout)
        session.open()
        self.addCleanup(self.close, session)
        return session, device

    def close(self, session):
        session.close()
        session.thread.join(2)
        self.assertFalse(session.thread.is_alive())

    def connect(self, device=None, timeout=3.0):
        session, device = self.open(device, timeout)
        wait_until(lambda: session.status.connection == ConnectionState.CONNECTED)
        return session, device

    def test_connects_and_forwards_device_logs(self):
        session, _ = self.connect()
        self.assertEqual(session.status.device_name, SimulatedDevice.NAME)
        wait_until(lambda: session.logs.qsize() > 0)
        self.assertIn("Device connected", "".join(session.take_logs()))

    def test_single_capture_completes(self):
        session, device = self.connect()
        session.start_acquisition(False)
        wait_until(lambda: session.status.acquisition == AcquisitionState.COMPLETE)
        self.assertEqual(session.status.captures_received, 1)
        self.assertEqual(len(session.frames.take().edges), 66)
        self.assertEqual(device.capture_request, None)

    def test_continuous_capture_repeats_until_stopped(self):
        session, _ = self.connect()
        session.start_acquisition(True)
        wait_until(lambda: session.status.captures_received >= 2)
        session.stop_acquisition()
        wait_until(lambda: session.status.acquisition == AcquisitionState.STOPPED)
        self.assertEqual(session.status.error, "")
        self.assertEqual(session.status.connection, ConnectionState.CONNECTED)

    def test_stop_cancels_pending_capture(self):
        session, device = self.connect(ScriptedDevice(silent_capture=True))
        session.start_acquisition(False)
        wait_until(lambda: session.status.acquisition == AcquisitionState.CAPTURING)
        session.stop_acquisition()
        wait_until(lambda: session.status.acquisition == AcquisitionState.STOPPED)
        self.assertEqual(session.status.error, "")

    def test_continuous_capture_rearms_after_device_timeout(self):
        session, device = self.connect(ScriptedDevice(capture_results=[TIMEOUT]))
        session.start_acquisition(True)
        wait_until(lambda: session.status.captures_received >= 1)
        self.assertGreaterEqual(device.captures_requested, 2)
        self.assertEqual(session.status.error, "")

    def test_capture_failure_is_reported_without_disconnecting(self):
        session, _ = self.connect(ScriptedDevice(capture_results=[OVERFLOW]))
        session.start_acquisition(True)
        wait_until(lambda: session.status.error != "")
        self.assertEqual(session.status.error, "Capture buffer overflow")
        self.assertEqual(session.status.acquisition, AcquisitionState.STOPPED)
        self.assertEqual(session.status.connection, ConnectionState.CONNECTED)

    def test_transmit_during_continuous_capture(self):
        session, _ = self.connect()
        session.start_acquisition(True)
        session.transmit(ToneBurst())
        wait_until(lambda: session.status.transmit_message == "Complete")
        wait_until(lambda: session.status.captures_received >= 2)
        self.assertEqual(session.status.acquisition, AcquisitionState.CAPTURING)

    def test_transmit_rejection_keeps_connection(self):
        session, _ = self.connect(ScriptedDevice(transmit_result=BUSY))
        session.transmit(ToneBurst())
        wait_until(lambda: session.status.transmit_message == "Device busy")
        self.assertFalse(session.status.transmitting)
        self.assertEqual(session.status.connection, ConnectionState.CONNECTED)

    def test_close_waits_for_transmission(self):
        session, _ = self.connect()
        session.transmit(ToneBurst())
        wait_until(lambda: session.status.transmitting)
        session.close()
        self.assertTrue(session.done.wait(1))
        self.assertEqual(session.status.transmit_message, "Complete")
        self.assertEqual(session.status.connection, ConnectionState.DISCONNECTED)

    def test_close_stops_pending_capture(self):
        session, device = self.connect(ScriptedDevice(silent_capture=True))
        session.start_acquisition(True)
        wait_until(lambda: session.status.acquisition == AcquisitionState.CAPTURING)
        session.close()
        self.assertTrue(session.done.wait(1))
        self.assertEqual(session.status.error, "")

    def test_unanswered_request_disconnects_with_error(self):
        session, _ = self.connect(ScriptedDevice(silent_capture=True), timeout=0.2)
        session.start_acquisition(False)
        self.assertTrue(session.done.wait(2))
        self.assertEqual(session.status.connection, ConnectionState.DISCONNECTED)
        self.assertEqual(session.status.error, "Device response timed out")

    def test_commands_before_connection_are_ignored(self):
        session = Session(SimulatedDevice)
        session.start_acquisition(False)
        session.transmit(ToneBurst())
        session.open()
        self.addCleanup(self.close, session)
        wait_until(lambda: session.status.connection == ConnectionState.CONNECTED)
        self.assertEqual(session.status.acquisition, AcquisitionState.STOPPED)
        self.assertFalse(session.status.transmitting)


if __name__ == "__main__":
    unittest.main()
