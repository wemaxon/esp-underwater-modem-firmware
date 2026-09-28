from dataclasses import replace
import tkinter as tk
from tkinter import ttk

from ..transport import discover_devices, open_device
from ..session import AcquisitionState, ConnectionState, Session, SessionStatus
from .controls import AcquisitionControls, ConnectionBar, TransmitControls
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
        sidebar = ttk.Frame(body)
        sidebar.grid(row=0, column=1, sticky="ns", padx=(6, 10), pady=(0, 8))
        sidebar.columnconfigure(0, weight=1)
        self.acquisition = AcquisitionControls(sidebar, self.run_acquisition, self.stop_acquisition, self.update_graph_window)
        self.acquisition.grid(row=0, column=0, sticky="ew")
        self.transmission = TransmitControls(sidebar, self.transmit)
        self.transmission.grid(row=1, column=0, sticky="ew", pady=(12, 0))
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
        self.acquisition.set_status(status)
        self.transmission.set_status(status)
        self.message.set(status.error or f"{status.device_name} | {status.captures_received} captures received")
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

    def update_graph_window(self):
        try:
            self.plot.set_window_ms(self.acquisition.graph_window_ms())
        except (ValueError, tk.TclError) as exc:
            self.message.set(str(exc))
            self.footer.configure(foreground="#b33b35")
            return False
        self.render_status(self.status)
        return True

    def run_acquisition(self):
        if self.closing or self.session is None or self.status.connection != ConnectionState.CONNECTED:
            return
        if self.status.acquisition not in (AcquisitionState.STOPPED, AcquisitionState.COMPLETE):
            return
        if not self.update_graph_window():
            return
        self.plot.clear()
        self.render_status(replace(self.status, acquisition=AcquisitionState.STARTING))
        self.session.start_acquisition(self.acquisition.mode.get() == "Continuous")

    def stop_acquisition(self):
        if self.session is not None:
            self.render_status(replace(self.status, acquisition=AcquisitionState.STOPPING))
            self.session.stop_acquisition()

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
        frame = self.session.frames.take()
        if frame is not None:
            self.plot.show(frame)

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
