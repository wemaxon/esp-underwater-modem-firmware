from dataclasses import replace
import tkinter as tk
from tkinter import ttk

from ..model import StreamHistory
from ..trigger import LevelTrigger, SingleShot
from ..transport import discover_devices, open_device
from ..session import AcquisitionState, ConnectionState, Session, SessionStatus
from .controls import AcquisitionControls, ConfigurationControls, ConnectionBar, TransmitControls
from .plot import ScopePlot
from .log_console import LogConsole


class Application(tk.Tk):
    REFRESH_MS = 33

    def __init__(self, discover=discover_devices, device_factory=open_device):
        super().__init__()
        self.title("Underwater Modem Toolbox")
        self.geometry("1250x780")
        self.minsize(950, 620)
        self.discover = discover
        self.device_factory = device_factory
        self.session = None
        self.status = SessionStatus()
        self.closing = False
        self.history = StreamHistory(span_s=AcquisitionControls.MAX_WINDOW_MS / 1000)
        self.single = None          # single shot waiting for its trigger or window
        self.held_ns = None         # trigger time of the single shot on display
        self.message = tk.StringVar()
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.connection = ConnectionBar(self, self.refresh_devices, self.connect, self.disconnect)
        self.connection.grid(row=0, column=0, sticky="ew")
        panes = ttk.Panedwindow(self, orient="vertical")
        panes.grid(row=1, column=0, sticky="nsew")
        body = ttk.Frame(panes)
        panes.add(body, weight=4)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.plot = ScopePlot(body)
        self.plot.grid(row=0, column=0, sticky="nsew")
        sidebar = ttk.Notebook(body)
        sidebar.grid(row=0, column=1, sticky="ns", padx=(6, 10), pady=(0, 8))
        measure = ttk.Frame(sidebar, padding=(0, 8, 0, 0))
        measure.columnconfigure(0, weight=1)
        sidebar.add(measure, text="Measure")
        self.acquisition = AcquisitionControls(measure, self.run_acquisition, self.stop_acquisition, self.force_trigger, self.update_view)
        self.acquisition.grid(row=0, column=0, sticky="ew")
        self.transmission = TransmitControls(measure, self.transmit)
        self.transmission.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.configuration = ConfigurationControls(sidebar, self.apply_configuration)
        sidebar.add(self.configuration, text="Configuration", padding=(0, 8, 0, 0))
        self.console = LogConsole(panes)
        panes.add(self.console, weight=1)
        self.footer = ttk.Label(self, textvariable=self.message, padding=(10, 6), anchor="w")
        self.footer.grid(row=2, column=0, sticky="ew")
        self.bind("<Configure>", self.resize_footer)
        self.render_status(self.status)
        self.refresh_devices()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(self.REFRESH_MS, self.poll)

    def resize_footer(self, event):
        if event.widget is self:
            self.footer.configure(wraplength=max(1, event.width - 20))

    def refresh_devices(self):
        if self.session is not None:
            return
        try:
            self.connection.set_devices(self.discover())
            self.connection.set_status(self.status)
        except OSError as exc:
            self.message.set(str(exc))

    def render_status(self, status):
        self.status = status
        self.connection.set_status(status)
        if status.acquisition == AcquisitionState.STOPPED:
            self.single = None      # a stream that ended cannot complete a single shot
        self.acquisition.set_status(status, self.single_state(), armed=self.single is not None and not self.single.triggered)
        self.configuration.set_status(status)
        self.transmission.set_status(status)
        self.message.set(status.error or status.device_name)
        self.footer.configure(foreground="#b33b35" if status.error else "")

    def connect(self):
        device = self.connection.selected_device()
        if self.session is not None or device is None or self.closing:
            return
        self.session = Session(lambda: self.device_factory(device))
        self.console.append([f"\n--- Connecting to {device.label} ---\n"])
        self.render_status(SessionStatus(connection=ConnectionState.CONNECTING))
        self.session.open()

    def disconnect(self):
        if self.session is not None:
            self.render_status(replace(self.status, connection=ConnectionState.DISCONNECTING))
            self.session.close()

    def single_state(self):
        if self.single is not None:
            return "Triggered" if self.single.triggered else "Waiting for trigger"
        return "Captured" if self.held_ns is not None and self.status.acquisition == AcquisitionState.STOPPED else None

    def read_settings(self):
        try:
            return self.acquisition.settings()
        except (ValueError, tk.TclError) as exc:
            self.message.set(str(exc))
            self.footer.configure(foreground="#b33b35")
            return None

    def update_view(self):
        """Applies the window settings: to the held single shot, or as a rolling view."""
        settings = self.read_settings()
        if settings is None:
            return
        if self.held_ns is not None:
            self.plot.set_view(settings.window_ms, settings.pre_trigger_ms)
            self.plot.show(self.history, self.held_ns)
        else:
            self.plot.set_view(settings.window_ms, settings.window_ms)
            self.plot.show(self.history, self.history.latest_ns)
        self.render_status(self.status)

    def run_acquisition(self):
        if self.closing or self.session is None or self.status.connection != ConnectionState.CONNECTED:
            return
        settings = self.read_settings()
        if self.status.acquisition != AcquisitionState.STOPPED or settings is None:
            return
        self.history.clear()
        self.held_ns = None
        self.single = None
        if settings.single:
            pre_ns = round(settings.pre_trigger_ms * 1e6)
            post_ns = round(settings.window_ms * 1e6) - pre_ns
            self.single = SingleShot(LevelTrigger(settings.trigger_v), pre_ns, post_ns)
        self.plot.reset()
        self.plot.set_trigger_level(settings.trigger_v if settings.single else None)
        self.plot.set_view(settings.window_ms, settings.window_ms)
        self.render_status(replace(self.status, acquisition=AcquisitionState.STARTING))
        self.session.start_stream()

    def stop_acquisition(self):
        if self.session is not None:
            self.single = None
            self.render_status(replace(self.status, acquisition=AcquisitionState.STOPPING))
            self.session.stop_stream()

    def force_trigger(self):
        if self.single is not None:
            self.single.force(self.history)
            self.render_status(self.status)

    def show_stream(self):
        """Rolls the view while streaming; holds the window of a completed single shot."""
        if self.held_ns is not None:
            return
        if self.single is not None:
            trigger_ns = self.single.update(self.history)
            if trigger_ns is not None:
                self.held_ns = trigger_ns
                self.single = None
                self.update_view()
                self.stop_acquisition()
                return
        self.plot.show(self.history, self.history.latest_ns)

    def apply_configuration(self):
        if self.session is not None and self.configuration.device_config is not None:
            self.session.apply_config(self.configuration.edited_config())

    def transmit(self):
        if self.closing or self.session is None or self.status.connection != ConnectionState.CONNECTED or self.status.transmitting:
            return
        try:
            tone = self.transmission.settings()
        except (ValueError, tk.TclError) as exc:
            self.transmission.state_text.set(str(exc))
            return
        self.render_status(replace(self.status, transmitting=True, transmit_message="Transmitting"))
        self.session.transmit(tone)

    def drain_session(self):
        self.console.append(self.session.take_logs())
        status = self.session.statuses.take()
        if status is not None:
            self.render_status(status)
        blocks = self.session.take_blocks()
        for block in blocks:
            self.history.add(block)
        if blocks:
            was_triggered = self.single is not None and self.single.triggered
            self.show_stream()
            if self.single is not None and self.single.triggered != was_triggered:
                self.render_status(self.status)

    def poll(self):
        if self.session is not None:
            finished = self.session.done.is_set()
            self.drain_session()
            if finished:
                self.session.thread.join()
                self.drain_session()
                self.session = None
        if self.closing and self.session is None:
            self.after_idle(self.destroy)
            return
        self.after(self.REFRESH_MS, self.poll)

    def close(self):
        self.closing = True
        self.disconnect()
