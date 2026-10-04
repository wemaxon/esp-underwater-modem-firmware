from dataclasses import replace
from time import monotonic
import tkinter as tk
from tkinter import ttk

from ..model import StreamHistory
from ..modem import bfsk
from ..tf_protocol import MAX_TONES
from ..trigger import LevelTrigger, SingleShot
from ..transport import discover_devices, open_device
from ..session import AcquisitionState, ConnectionState, Session, SessionStatus
from .controls import AcquisitionControls, ConfigurationControls, ConnectionBar, TransmitControls
from .link_controls import LinkControls
from .log_console import LogConsole
from .plot import ScopePlot
from .received_frames import ReceivedFrames
from .scrollable import ScrollableFrame


class Application(tk.Tk):
    REFRESH_MS = 33
    DECODE_INTERVAL_S = 0.25

    def __init__(self, discover=discover_devices, device_factory=open_device, link_file=None):
        """link_file keeps the link settings between runs; None starts with the defaults."""
        super().__init__()
        self.title("Underwater Modem Toolbox")
        self.geometry("1250x780")
        self.minsize(950, 620)
        self.discover = discover
        self.device_factory = device_factory
        self.link_file = link_file
        self.session = None
        self.status = SessionStatus()
        self.closing = False
        self.history = StreamHistory(span_s=AcquisitionControls.MAX_WINDOW_MS / 1000)
        self.single = None          # single shot waiting for its trigger or window
        self.held_ns = None         # trigger time of the single shot on display
        self.decode_from_ns = 0     # where the next frame search starts
        self.next_decode = 0.0
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
        scope, device, link = (self.sidebar_tab(sidebar, title) for title in ("Scope", "Device", "Link"))
        self.acquisition = AcquisitionControls(scope, self.run_acquisition, self.stop_acquisition, self.force_trigger, self.update_view)
        self.acquisition.grid(row=0, column=0, sticky="ew")
        self.transmission = TransmitControls(scope, self.transmit)
        self.transmission.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.configuration = ConfigurationControls(device, self.apply_configuration)
        self.configuration.grid(row=0, column=0, sticky="ew")
        self.link = LinkControls(link, self.send_frame, self.update_history_span)
        self.link.grid(row=0, column=0, sticky="ew")
        self.outputs = ttk.Notebook(panes)
        panes.add(self.outputs, weight=1)
        self.console = LogConsole(self.outputs)
        self.outputs.add(self.console, text="Device log")
        self.received = ReceivedFrames(self.outputs, self.show_frame_count)
        self.outputs.add(self.received, text="Received frames")
        self.load_link_file()
        self.footer = ttk.Label(self, textvariable=self.message, padding=(10, 6), anchor="w")
        self.footer.grid(row=2, column=0, sticky="ew")
        self.bind("<Configure>", self.resize_footer)
        self.render_status(self.status)
        self.refresh_devices()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(self.REFRESH_MS, self.poll)

    @staticmethod
    def sidebar_tab(sidebar, title):
        """A tab whose content scrolls when the window is too low for it."""
        tab = ScrollableFrame(sidebar, padding=(0, 8, 6, 0))
        sidebar.add(tab, text=title)
        return tab.content

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
        self.link.set_status(status)
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
        self.update_history_span()
        self.decode_from_ns = 0
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

    def update_history_span(self):
        """Keeps enough of the stream for the plot window and the longest frame being decoded."""
        try:
            link = self.link.settings()
        except ValueError:
            return
        frame_s = link.frame_duration_s(link.framing.max_payload)
        self.history.set_span(max(AcquisitionControls.MAX_WINDOW_MS / 1000, 2 * frame_s + 1))

    def load_link_file(self):
        if self.link_file is None or not self.link_file.exists():
            return
        try:
            self.link.load_file(self.link_file)
        except (OSError, ValueError) as exc:
            self.message.set(f"Could not load the last link settings: {exc}")

    def save_link_file(self):
        if self.link_file is None:
            return
        try:
            self.link.save_file(self.link_file)
        except (OSError, ValueError):
            pass                # invalid entries are not kept

    def show_frame_count(self, count):
        self.outputs.tab(self.received, text=f"Received frames ({count})" if count else "Received frames")

    def send_frame(self):
        if self.closing or self.session is None or self.session.info is None or self.status.transmitting:
            return
        try:
            link = self.link.settings()
            tones = bfsk.modulate(link.frame_bits(self.link.payload()), link.modulation, self.session.info.transmit_clock_hz)
            if len(tones) > MAX_TONES:
                raise ValueError(f"The frame needs {len(tones)} tones; one transmission holds {MAX_TONES}")
        except ValueError as exc:
            self.link.show_error(str(exc))
            return
        self.render_status(replace(self.status, transmitting=True, transmit_message="Transmitting"))
        self.session.transmit(tones)

    def decode_stream(self):
        """Searches the stream for new frames, at most every DECODE_INTERVAL_S."""
        if not self.received.decoding.get() or monotonic() < self.next_decode or self.history.earliest_ns is None:
            return
        if self.session is None or self.session.info is None:
            return
        self.next_decode = monotonic() + self.DECODE_INTERVAL_S
        try:
            link = self.link.settings()
        except ValueError:
            return
        start_ns = max(self.decode_from_ns, self.history.earliest_ns)
        frames, self.decode_from_ns = bfsk.decode(self.history, link, self.session.info.transmit_clock_hz,
                                                  start_ns, self.history.latest_ns)
        self.received.add_frames(frames)

    def apply_configuration(self):
        if self.session is not None and self.configuration.device_config is not None:
            self.session.apply_config(self.configuration.edited_config())

    def transmit(self):
        if self.closing or self.session is None or self.status.connection != ConnectionState.CONNECTED or self.status.transmitting:
            return
        try:
            tone = self.transmission.tone()
        except (ValueError, tk.TclError) as exc:
            self.transmission.state_text.set(str(exc))
            return
        self.render_status(replace(self.status, transmitting=True, transmit_message="Transmitting"))
        self.session.transmit([tone])

    def drain_session(self):
        self.console.append(self.session.take_logs())
        status = self.session.statuses.take()
        if status is not None:
            self.render_status(status)
        blocks = self.session.take_blocks()
        for block in blocks:
            self.history.add(block)
        if blocks:
            self.decode_stream()
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
        if not self.closing:
            self.save_link_file()
        self.closing = True
        self.disconnect()
