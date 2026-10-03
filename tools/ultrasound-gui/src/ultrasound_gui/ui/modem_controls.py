import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from ..modem import framing
from ..modem.bfsk import BfskSettings, DecodedFrame
from ..session import ConnectionState, SessionStatus


class ModemControls(ttk.Frame):
    """BFSK settings, sending a message as one frame, and the frames decoded from the stream."""

    def __init__(self, master, send, settings_changed):
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.settings_changed = settings_changed
        defaults = BfskSettings()
        self.fields = {
            "center_hz": ("Centre (Hz)", tk.StringVar(value=str(defaults.center_hz)), 100),
            "shift_hz": ("Shift (Hz)", tk.StringVar(value=str(defaults.shift_hz)), 100),
            "symbol_ms": ("Symbol length (ms)", tk.StringVar(value=f"{defaults.symbol_ms:g}"), 1),
            "preamble_bits": ("Preamble (bits)", tk.StringVar(value=str(defaults.preamble_bits)), 2),
            "max_payload": ("Maximum payload (bytes)", tk.StringVar(value=str(defaults.max_payload)), 1),
        }
        settings = ttk.LabelFrame(self, text="BFSK", padding=12)
        settings.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        settings.columnconfigure(1, weight=1)
        for row, (label, variable, increment) in enumerate(self.fields.values()):
            ttk.Label(settings, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            ttk.Spinbox(settings, textvariable=variable, from_=0, to=1_000_000, increment=increment,
                        width=10).grid(row=row, column=1, sticky="ew", pady=2)

        sending = ttk.LabelFrame(self, text="Send", padding=12)
        sending.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        sending.columnconfigure(0, weight=1)
        self.message = tk.StringVar(value="Hello")
        ttk.Entry(sending, textvariable=self.message).grid(row=0, column=0, sticky="ew")
        self.frame_text = tk.StringVar()
        ttk.Label(sending, textvariable=self.frame_text, wraplength=240).grid(row=1, column=0, sticky="w", pady=(6, 6))
        self.send_button = ttk.Button(sending, text="Send frame", command=send)
        self.send_button.grid(row=2, column=0, sticky="ew")

        receiving = ttk.LabelFrame(self, text="Received", padding=12)
        receiving.grid(row=2, column=0, sticky="nsew")
        receiving.columnconfigure(0, weight=1)
        receiving.rowconfigure(1, weight=1)
        self.decoding = tk.BooleanVar(value=True)
        ttk.Checkbutton(receiving, text="Decode while streaming", variable=self.decoding).grid(row=0, column=0, sticky="w")
        self.frames = ScrolledText(receiving, height=8, width=32, wrap="word", state="disabled", font="TkFixedFont")
        self.frames.grid(row=1, column=0, sticky="nsew", pady=(6, 6))
        ttk.Button(receiving, text="Clear", command=self.clear_frames).grid(row=2, column=0, sticky="ew")
        for _, variable, _ in self.fields.values():
            variable.trace_add("write", lambda *args: self._changed())
        self.message.trace_add("write", lambda *args: self._describe_frame())
        self._describe_frame()

    def settings(self):
        """The settings as entered; raises ValueError if they are invalid."""
        values = {name: variable.get() for name, (_, variable, _) in self.fields.items()}
        return BfskSettings(
            center_hz=int(values["center_hz"]),
            shift_hz=int(values["shift_hz"]),
            symbol_ms=float(values["symbol_ms"]),
            preamble_bits=int(values["preamble_bits"]),
            max_payload=int(values["max_payload"]),
        )

    def payload(self):
        return self.message.get().encode("utf-8")

    def _changed(self):
        self._describe_frame()
        self.settings_changed()

    def _describe_frame(self):
        try:
            settings = self.settings()
        except ValueError as exc:
            self.frame_text.set(str(exc))
            return
        size = len(self.payload())
        bits = framing.frame_length_bits(size, settings.preamble_bits)
        text = f"{size} bytes, {bits} bits, {settings.frame_duration_s(size):.2f} s, {1000 / settings.symbol_ms:g} bit/s"
        if size > settings.max_payload:
            text += f" - exceeds the maximum payload of {settings.max_payload} bytes"
        self.frame_text.set(text)

    def show_error(self, message):
        self.frame_text.set(message)

    def set_status(self, status: SessionStatus):
        ready = status.connection == ConnectionState.CONNECTED and not status.transmitting
        self.send_button.configure(state="normal" if ready else "disabled")

    def add_frames(self, frames: list[DecodedFrame]):
        if not frames:
            return
        lines = []
        for frame in frames:
            check = "OK " if frame.crc_ok else "CRC error "
            text = frame.payload.decode("utf-8", errors="replace")
            lines.append(f"{frame.start_ns / 1e9:8.3f} s  {check} {len(frame.payload)} B  q={frame.quality:.2f}\n  {text}\n")
        self.frames.configure(state="normal")
        self.frames.insert("end", "".join(lines))
        self.frames.configure(state="disabled")
        self.frames.see("end")

    def clear_frames(self):
        self.frames.configure(state="normal")
        self.frames.delete("1.0", "end")
        self.frames.configure(state="disabled")
