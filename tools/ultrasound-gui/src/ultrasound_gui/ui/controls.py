from math import isfinite
import tkinter as tk
from tkinter import ttk

from ..model import ToneBurst
from ..session import AcquisitionState, ConnectionState, SessionStatus


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


class AcquisitionControls(ttk.LabelFrame):
    def __init__(self, master, run, stop, window_changed):
        super().__init__(master, text="Acquisition", padding=12)
        self.columnconfigure(0, weight=1)
        self.mode = tk.StringVar(value="Continuous")
        self.window_ms = tk.StringVar(value="20")
        self.state_text = tk.StringVar(value="Stopped")
        ttk.Label(self, textvariable=self.state_text).grid(row=0, column=0, sticky="w", pady=(0, 12))
        ttk.Label(self, text="Mode").grid(row=1, column=0, sticky="w")
        self.mode_input = ttk.Combobox(self, textvariable=self.mode, values=["Continuous", "Single"], state="readonly", width=18)
        self.mode_input.grid(row=2, column=0, sticky="ew", pady=(4, 12))
        ttk.Label(self, text="Graph window (ms)").grid(row=3, column=0, sticky="w")
        self.window_input = ttk.Spinbox(self, textvariable=self.window_ms, from_=0.1, to=10000, increment=1, command=window_changed, width=18)
        self.window_input.grid(row=4, column=0, sticky="ew", pady=(4, 12))
        self.window_input.bind("<Return>", lambda event: window_changed())
        self.window_input.bind("<FocusOut>", lambda event: window_changed())
        self.run_button = ttk.Button(self, text="Run", command=run)
        self.run_button.grid(row=5, column=0, sticky="ew", pady=(0, 6))
        self.stop_button = ttk.Button(self, text="Stop", command=stop)
        self.stop_button.grid(row=6, column=0, sticky="ew")

    def graph_window_ms(self):
        value = float(self.window_ms.get())
        if not isfinite(value) or not 0.1 <= value <= 10000:
            raise ValueError("Graph window must be between 0.1 and 10000 ms")
        return value

    def set_status(self, status: SessionStatus):
        ready = status.connection == ConnectionState.CONNECTED
        idle = status.acquisition in (AcquisitionState.STOPPED, AcquisitionState.COMPLETE)
        self.state_text.set(status.acquisition.value)
        self.mode_input.configure(state="readonly" if idle else "disabled")
        self.run_button.configure(state="normal" if ready and idle else "disabled")
        self.stop_button.configure(state="normal" if ready and status.acquisition in (AcquisitionState.STARTING, AcquisitionState.CAPTURING) else "disabled")


class TransmitControls(ttk.LabelFrame):
    def __init__(self, master, transmit):
        super().__init__(master, text="Tone burst", padding=12)
        self.columnconfigure(0, weight=1)
        self.frequency_hz = tk.StringVar(value="40000")
        self.cycles = tk.StringVar(value="32")
        self.state_text = tk.StringVar(value="Idle")
        ttk.Label(self, text="Frequency (Hz)").grid(row=0, column=0, sticky="w")
        self.frequency_input = ttk.Spinbox(self, textvariable=self.frequency_hz, from_=40000, to=1000000, increment=1000, width=18)
        self.frequency_input.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        ttk.Label(self, text="Cycles").grid(row=2, column=0, sticky="w")
        self.cycles_input = ttk.Spinbox(self, textvariable=self.cycles, from_=1, to=255, increment=1, width=18)
        self.cycles_input.grid(row=3, column=0, sticky="ew", pady=(4, 12))
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
