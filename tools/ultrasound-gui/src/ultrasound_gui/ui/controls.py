from dataclasses import dataclass
from math import isfinite
import tkinter as tk
from tkinter import ttk

from ..model import ToneBurst
from ..session import AcquisitionState, ConnectionState, SessionStatus
from ..tuss_config import RECEIVER_SETTINGS, TRANSMITTER_SETTINGS


class ConnectionBar(ttk.Frame):
    def __init__(self, master, refresh, connect, disconnect):
        super().__init__(master, padding=(10, 8))
        self.columnconfigure(1, weight=1)
        self.selection = tk.StringVar()
        self.status = tk.StringVar(value="Disconnected")
        ttk.Label(self, text="Device").grid(row=0, column=0, padx=(0, 8))
        self.picker = ttk.Combobox(self, textvariable=self.selection, state="readonly")
        self.picker.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.refresh = ttk.Button(self, text="Refresh", command=refresh)
        self.refresh.grid(row=0, column=2, padx=(0, 8))
        self.connect = ttk.Button(self, text="Connect", command=connect)
        self.connect.grid(row=0, column=3, padx=(0, 8))
        self.disconnect = ttk.Button(self, text="Disconnect", command=disconnect)
        self.disconnect.grid(row=0, column=4, padx=(0, 16))
        ttk.Label(self, textvariable=self.status, width=16, anchor="e").grid(row=0, column=5, sticky="e")
        self.devices = []

    def set_devices(self, devices):
        selected = self.selected_device()
        self.devices = devices
        self.picker.configure(values=[device.label for device in devices])
        if selected in devices:
            self.picker.current(devices.index(selected))
        elif devices:
            self.picker.current(0)
        else:
            self.selection.set("")

    def selected_device(self):
        index = self.picker.current()
        return self.devices[index] if 0 <= index < len(self.devices) else None

    def set_status(self, status: SessionStatus):
        idle = status.connection == ConnectionState.DISCONNECTED
        self.status.set(status.connection.value)
        self.picker.configure(state="readonly" if idle else "disabled")
        self.refresh.configure(state="normal" if idle else "disabled")
        self.connect.configure(state="normal" if idle and self.devices else "disabled")
        self.disconnect.configure(state="normal" if status.connection in (ConnectionState.CONNECTING, ConnectionState.CONNECTED) else "disabled")


@dataclass(frozen=True)
class AcquisitionSettings:
    single: bool            # Single shot; otherwise Roll
    window_ms: float
    pre_trigger_ms: float
    trigger_v: float


class AcquisitionControls(ttk.LabelFrame):
    MODES = ("Roll", "Single")
    MAX_WINDOW_MS = 2000.0
    MAX_TRIGGER_V = 3.3

    def __init__(self, master, run, stop, force, view_changed):
        super().__init__(master, text="Acquisition", padding=12)
        self.columnconfigure(0, weight=1)
        self.mode = tk.StringVar(value="Roll")
        self.window_ms = tk.StringVar(value="100")
        self.pre_trigger_ms = tk.StringVar(value="10")
        self.trigger_v = tk.StringVar(value="1.0")
        self.state_text = tk.StringVar(value="Stopped")
        ttk.Label(self, textvariable=self.state_text).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.mode_input = ttk.Combobox(self, textvariable=self.mode, values=self.MODES, state="readonly", width=18)
        self.mode_input.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.mode_input.bind("<<ComboboxSelected>>", lambda event: view_changed())
        self.window_input = self._spinbox("Window (ms)", self.window_ms, 1, self.MAX_WINDOW_MS, 10, view_changed, row=2)
        self.pre_trigger_input = self._spinbox("Pre-trigger (ms)", self.pre_trigger_ms, 0, self.MAX_WINDOW_MS, 1, view_changed, row=4)
        self.trigger_input = self._spinbox("Trigger level, VOUT rising (V)", self.trigger_v, 0, self.MAX_TRIGGER_V, 0.05, view_changed, row=6)
        self.run_button = ttk.Button(self, text="Run", command=run)
        self.run_button.grid(row=8, column=0, sticky="ew", pady=(0, 6))
        self.stop_button = ttk.Button(self, text="Stop", command=stop)
        self.stop_button.grid(row=9, column=0, sticky="ew", pady=(0, 6))
        self.force_button = ttk.Button(self, text="Force trigger", command=force)
        self.force_button.grid(row=10, column=0, sticky="ew")

    def _spinbox(self, label, variable, low, high, increment, changed, row):
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w")
        spinbox = ttk.Spinbox(self, textvariable=variable, from_=low, to=high, increment=increment, command=changed, width=18)
        spinbox.grid(row=row + 1, column=0, sticky="ew", pady=(2, 8))
        spinbox.bind("<Return>", lambda event: changed())
        spinbox.bind("<FocusOut>", lambda event: changed())
        return spinbox

    def settings(self):
        window_ms = float(self.window_ms.get())
        pre_trigger_ms = float(self.pre_trigger_ms.get())
        trigger_v = float(self.trigger_v.get())
        if not isfinite(window_ms) or not 1 <= window_ms <= self.MAX_WINDOW_MS:
            raise ValueError(f"Window must be between 1 and {self.MAX_WINDOW_MS:g} ms")
        if not isfinite(pre_trigger_ms) or not 0 <= pre_trigger_ms < window_ms:
            raise ValueError("Pre-trigger time must be at least 0 and shorter than the window")
        if not isfinite(trigger_v) or not 0 < trigger_v < self.MAX_TRIGGER_V:
            raise ValueError(f"Trigger level must be between 0 and {self.MAX_TRIGGER_V:g} V")
        return AcquisitionSettings(self.mode.get() == "Single", window_ms, pre_trigger_ms, trigger_v)

    def set_status(self, status: SessionStatus, single_state=None, armed=False):
        """single_state describes a single shot in progress or held; armed allows forcing its trigger."""
        ready = status.connection == ConnectionState.CONNECTED
        running = status.acquisition in (AcquisitionState.STARTING, AcquisitionState.STREAMING)
        stopped = status.acquisition == AcquisitionState.STOPPED
        self.state_text.set(single_state or status.acquisition.value)
        trigger_settings = "normal" if stopped else "disabled"
        self.mode_input.configure(state="readonly" if stopped else "disabled")
        self.pre_trigger_input.configure(state=trigger_settings)
        self.trigger_input.configure(state=trigger_settings)
        self.run_button.configure(state="normal" if ready and stopped else "disabled")
        self.stop_button.configure(state="normal" if ready and running else "disabled")
        self.force_button.configure(state="normal" if ready and running and armed else "disabled")


class ConfigurationControls(ttk.Frame):
    """TUSS4470 receiver and transmitter settings. Shows the device's configuration; Apply sends the edits."""

    GROUPS = (("Receiver", RECEIVER_SETTINGS), ("Transmitter", TRANSMITTER_SETTINGS))

    def __init__(self, master, apply):
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.device_config = None
        self.choices = {}
        for row, (title, settings) in enumerate(self.GROUPS):
            group = ttk.LabelFrame(self, text=title, padding=12)
            group.grid(row=row, column=0, sticky="ew", pady=(0, 12))
            group.columnconfigure(1, weight=1)
            for index, setting in enumerate(settings):
                ttk.Label(group, text=setting.label).grid(row=index, column=0, sticky="w", padx=(0, 8), pady=2)
                choice = ttk.Combobox(group, values=setting.choices, state="disabled", width=12)
                choice.grid(row=index, column=1, sticky="ew", pady=2)
                self.choices[setting] = choice
        ttk.Label(self, text="VDRV must stay below VPWR - 0.1 V.", foreground="#666").grid(row=len(self.GROUPS), column=0, sticky="w")
        self.apply_button = ttk.Button(self, text="Apply", command=apply)
        self.apply_button.grid(row=len(self.GROUPS) + 1, column=0, sticky="ew", pady=(8, 0))

    def edited_config(self):
        config = self.device_config
        for setting, choice in self.choices.items():
            if choice.current() >= 0:
                config = config.with_value(setting, choice.current())
        return config

    def set_status(self, status: SessionStatus):
        ready = status.connection == ConnectionState.CONNECTED and status.config is not None
        if status.config is not None and status.config != self.device_config:
            self.device_config = status.config
            for setting, choice in self.choices.items():
                choice.set(setting.text(self.device_config.get(setting)))
        for choice in self.choices.values():
            choice.configure(state="readonly" if ready else "disabled")
        self.apply_button.configure(state="normal" if ready else "disabled")


class TransmitControls(ttk.LabelFrame):
    def __init__(self, master, transmit):
        super().__init__(master, text="Tone burst", padding=12)
        self.columnconfigure(0, weight=1)
        self.frequency_hz = tk.StringVar(value="40000")
        self.cycles = tk.StringVar(value="32")
        self.state_text = tk.StringVar(value="Idle")
        ttk.Label(self, text="Frequency (Hz)").grid(row=0, column=0, sticky="w")
        self.frequency_input = ttk.Spinbox(self, textvariable=self.frequency_hz, from_=40000, to=1000000, increment=1000, width=18)
        self.frequency_input.grid(row=1, column=0, sticky="ew", pady=(2, 8))
        ttk.Label(self, text="Cycles").grid(row=2, column=0, sticky="w")
        self.cycles_input = ttk.Spinbox(self, textvariable=self.cycles, from_=1, to=255, increment=1, width=18)
        self.cycles_input.grid(row=3, column=0, sticky="ew", pady=(2, 8))
        self.transmit_button = ttk.Button(self, text="Transmit", command=transmit)
        self.transmit_button.grid(row=4, column=0, sticky="ew")
        ttk.Label(self, textvariable=self.state_text, wraplength=180).grid(row=5, column=0, sticky="w", pady=(8, 0))

    def settings(self):
        return ToneBurst(int(self.frequency_hz.get()), int(self.cycles.get()))

    def set_status(self, status: SessionStatus):
        self.state_text.set(status.transmit_message)
        editable = "disabled" if status.transmitting else "normal"
        self.frequency_input.configure(state=editable)
        self.cycles_input.configure(state=editable)
        self.transmit_button.configure(state="normal" if status.connection == ConnectionState.CONNECTED and not status.transmitting else "disabled")
