from queue import Empty
import tkinter as tk
from tkinter import ttk

from device import Acquisition, devices
from plot import LivePlot


class Application(tk.Tk):
    REFRESH_MS = 33

    def __init__(self):
        super().__init__()
        self.title("Ultrasound GUI")
        self.geometry("1100x700")
        self.minsize(760, 420)
        self.worker = None
        self.closing = False
        self.state_name = "disconnected"
        self.device_map = {}
        self.selection = tk.StringVar()
        self.status = tk.StringVar(value="Disconnected")
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)
        ttk.Label(toolbar, text="Device").grid(row=0, column=0, padx=(0, 8))
        self.device_picker = ttk.Combobox(toolbar, textvariable=self.selection, state="readonly", width=28)
        self.device_picker.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.refresh_button = ttk.Button(toolbar, text="Refresh", command=self.refresh_devices)
        self.refresh_button.grid(row=0, column=2, padx=(0, 8))
        self.connect_button = ttk.Button(toolbar, text="Connect", command=self.connect)
        self.connect_button.grid(row=0, column=3, padx=(0, 8))
        self.disconnect_button = ttk.Button(toolbar, text="Disconnect", command=self.disconnect)
        self.disconnect_button.grid(row=0, column=4, padx=(0, 16))
        ttk.Label(toolbar, textvariable=self.status, anchor="e", width=32, wraplength=240).grid(row=0, column=5, sticky="e")

        self.plot = LivePlot(self)
        self.plot.grid(row=1, column=0, sticky="nsew")
        self.refresh_devices()
        self.set_state("disconnected")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(self.REFRESH_MS, self.poll)

    def set_state(self, state):
        self.state_name = state
        idle = state == "disconnected" and not self.closing
        self.device_picker.configure(state="readonly" if idle else "disabled")
        self.refresh_button.configure(state="normal" if idle else "disabled")
        self.connect_button.configure(state="normal" if idle and self.device_map else "disabled")
        self.disconnect_button.configure(state="normal" if state in ("connecting", "connected") and not self.closing else "disabled")

    def refresh_devices(self):
        if self.worker is not None:
            return
        try:
            self.device_map = devices()
        except Exception as exc:
            self.status.set(f"Device discovery failed: {exc}")
            return
        self.device_picker.configure(values=list(self.device_map))
        if self.selection.get() not in self.device_map:
            self.selection.set(next(iter(self.device_map), ""))
        self.set_state("disconnected")

    def connect(self):
        if self.closing or self.worker is not None or self.selection.get() not in self.device_map:
            return
        self.plot.clear()
        self.status.set("Connecting...")
        self.set_state("connecting")
        self.worker = Acquisition(self.device_map[self.selection.get()])
        self.worker.start()

    def disconnect(self):
        if self.worker is not None:
            self.set_state("disconnecting")
            self.status.set("Disconnecting...")
            self.worker.stop()

    def poll(self):
        if self.worker is not None:
            stopped = False
            while True:
                try:
                    event, detail = self.worker.events.get_nowait()
                except Empty:
                    break
                if event == "connected" and self.state_name == "connecting":
                    self.set_state("connected")
                    self.status.set("Connected - Demo" if self.worker.port is None else
                                    "Connected - Serial (no sample decoder)")
                elif event == "error":
                    self.status.set(f"Connection error: {detail}")
                elif event == "stopped":
                    stopped = True
            if self.state_name == "connected":
                frame = self.worker.latest_frame()
                if frame is not None:
                    self.plot.update_frame(frame)
            if stopped:
                if self.state_name == "disconnecting" and not self.status.get().startswith("Connection error:"):
                    self.status.set("Disconnected")
                self.worker = None
                self.set_state("disconnected")
        if self.closing and self.worker is None:
            self.destroy()
            return
        self.after(self.REFRESH_MS, self.poll)

    def close(self):
        self.closing = True
        self.disconnect()
        self.set_state(self.state_name)
