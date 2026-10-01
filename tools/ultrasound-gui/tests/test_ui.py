import tkinter as tk
import unittest

from support import wait_until
from ultrasound_gui.session import AcquisitionState, ConnectionState
from ultrasound_gui.transport import DevicePort, open_device


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        try:
            from ultrasound_gui.ui.app import Application
            self.app = Application(discover=lambda: [DevicePort("Demo", None)], device_factory=open_device)
        except tk.TclError as exc:
            self.skipTest(f"Tk unavailable: {exc}")
        self.app.withdraw()

    def tearDown(self):
        self.app.close()        # disconnects, then destroys the window
        try:
            wait_until(lambda: self.pump() or not self.app.winfo_exists())
        except tk.TclError:
            pass

    def pump(self):
        self.app.update()
        return False

    def test_streamed_data_is_plotted_until_stopped(self):
        self.app.connect()
        wait_until(lambda: self.pump() or self.app.status.connection == ConnectionState.CONNECTED)
        self.app.run_acquisition()
        wait_until(lambda: self.pump() or len(self.app.plot.vout_line.get_xdata()) > 0, timeout=3)
        wait_until(lambda: self.pump() or len(self.app.plot.out3_line.get_xdata()) > 0, timeout=3)
        self.app.stop_acquisition()
        wait_until(lambda: self.pump() or self.app.status.acquisition == AcquisitionState.STOPPED)
        self.assertIn("Device connected", self.app.console.text.get("1.0", "end"))


if __name__ == "__main__":
    unittest.main()
