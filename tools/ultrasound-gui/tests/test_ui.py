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

    def test_configuration_panel_applies_edits(self):
        self.app.connect()
        wait_until(lambda: self.pump() or self.app.configuration.device_config is not None)
        choices = {setting.label: choice for setting, choice in self.app.configuration.choices.items()}
        self.assertEqual(choices["Zero-crossing hysteresis"].get(), "230 mV")
        self.assertEqual(choices["VDRV voltage"].get(), "5 V")
        choices["Zero-crossing hysteresis"].current(7)
        choices["Output stage"].current(1)
        self.app.apply_configuration()
        wait_until(lambda: self.pump() or self.app.configuration.device_config.registers[7] == 0x80)
        self.assertEqual(choices["Zero-crossing hysteresis"].get(), "380 mV")
        self.assertEqual(choices["Output stage"].get(), "Half bridge")

    def test_single_shot_holds_the_triggered_window(self):
        self.app.connect()
        wait_until(lambda: self.pump() or self.app.status.connection == ConnectionState.CONNECTED)
        self.app.acquisition.mode.set("Single")
        self.app.acquisition.window_ms.set("50")
        self.app.acquisition.pre_trigger_ms.set("5")
        self.app.acquisition.trigger_v.set("1.0")
        self.app.run_acquisition()
        wait_until(lambda: self.pump() or self.app.held_ns is not None, timeout=3)
        wait_until(lambda: self.pump() or self.app.status.acquisition == AcquisitionState.STOPPED)
        self.assertEqual(self.app.acquisition.state_text.get(), "Captured")
        times = self.app.plot.vout_line.get_xdata()
        self.assertLessEqual(times.min(), -4.9)          # pre-trigger data, in ms before the trigger
        self.assertGreaterEqual(times.max(), 44.9)


if __name__ == "__main__":
    unittest.main()
