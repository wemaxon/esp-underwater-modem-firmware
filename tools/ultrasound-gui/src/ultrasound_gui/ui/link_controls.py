import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from ..modem import fec
from ..modem.bfsk import BfskSettings
from ..modem.fec import CodingSettings
from ..modem.framing import FramingSettings
from ..modem.link import LinkSettings
from ..session import ConnectionState, SessionStatus

FILE_TYPES = [("Link settings", "*.json"), ("All files", "*.*")]


def _depth_text(depth):
    return str(depth) if depth else "Off"


class LinkControls(ttk.Frame):
    """The link settings both ends must share, and sending a message as one frame."""

    def __init__(self, master, send, settings_changed):
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.settings_changed = settings_changed
        self.variables = {}
        modulation = self._section("Modulation: BFSK", 0)
        self._spinbox(modulation, "center_hz", "Centre (Hz)", 100)
        self._spinbox(modulation, "shift_hz", "Shift (Hz)", 100)
        self._spinbox(modulation, "symbol_ms", "Symbol length (ms)", 1)
        coding = self._section("Coding", 1)
        self._choice(coding, "rate", "Code rate", list(fec.PUNCTURING))
        self._choice(coding, "interleaver", "Interleaver depth", [_depth_text(depth) for depth in fec.INTERLEAVER_DEPTHS])
        framing = self._section("Framing", 2)
        self._spinbox(framing, "preamble_bits", "Preamble (bits)", 2)
        self._spinbox(framing, "max_payload", "Maximum payload (bytes)", 1)

        files = ttk.Frame(self)
        files.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        files.columnconfigure((0, 1), weight=1)
        ttk.Button(files, text="Load...", command=self._load).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(files, text="Save...", command=self._save).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        ttk.Label(files, text="Both ends need the same link settings.").grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        sending = ttk.LabelFrame(self, text="Send", padding=8)
        sending.grid(row=4, column=0, sticky="ew")
        sending.columnconfigure(0, weight=1)
        self.message = tk.StringVar(value="Hello")
        ttk.Entry(sending, textvariable=self.message).grid(row=0, column=0, sticky="ew")
        self.frame_text = tk.StringVar()
        ttk.Label(sending, textvariable=self.frame_text, wraplength=240).grid(row=1, column=0, sticky="w", pady=6)
        self.send_button = ttk.Button(sending, text="Send frame", command=send)
        self.send_button.grid(row=2, column=0, sticky="ew")

        self.set_settings(LinkSettings())
        for variable in self.variables.values():
            variable.trace_add("write", lambda *args: self._changed())
        self.message.trace_add("write", lambda *args: self._describe_frame())
        self._describe_frame()

    def _section(self, title, row):
        section = ttk.LabelFrame(self, text=title, padding=8)
        section.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        section.columnconfigure(1, weight=1)
        return section

    def _field(self, section, name, label):
        row = len(section.grid_slaves(column=0))
        ttk.Label(section, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        self.variables[name] = tk.StringVar()
        return row

    def _spinbox(self, section, name, label, increment):
        row = self._field(section, name, label)
        ttk.Spinbox(section, textvariable=self.variables[name], from_=0, to=1_000_000, increment=increment,
                    width=10).grid(row=row, column=1, sticky="ew", pady=2)

    def _choice(self, section, name, label, values):
        row = self._field(section, name, label)
        ttk.Combobox(section, textvariable=self.variables[name], values=values, state="readonly",
                     width=8).grid(row=row, column=1, sticky="ew", pady=2)

    def settings(self):
        """The settings as entered; raises ValueError if they are invalid."""
        value = {name: variable.get() for name, variable in self.variables.items()}
        return LinkSettings(
            BfskSettings(int(value["center_hz"]), int(value["shift_hz"]), float(value["symbol_ms"])),
            CodingSettings(value["rate"], 0 if value["interleaver"] == "Off" else int(value["interleaver"])),
            FramingSettings(int(value["preamble_bits"]), int(value["max_payload"])),
        )

    def set_settings(self, link: LinkSettings):
        values = {
            "center_hz": link.modulation.center_hz, "shift_hz": link.modulation.shift_hz,
            "symbol_ms": f"{link.modulation.symbol_ms:g}",
            "rate": link.coding.rate, "interleaver": _depth_text(link.coding.interleaver),
            "preamble_bits": link.framing.preamble_bits, "max_payload": link.framing.max_payload,
        }
        for name, value in values.items():
            self.variables[name].set(str(value))

    def load_file(self, path):
        """Raises OSError or ValueError."""
        self.set_settings(LinkSettings.from_json(Path(path).read_text(encoding="utf-8")))

    def save_file(self, path):
        """Raises OSError or ValueError."""
        text = self.settings().to_json()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")

    def _load(self):
        path = filedialog.askopenfilename(parent=self, title="Load link settings", filetypes=FILE_TYPES)
        if path:
            try:
                self.load_file(path)
            except (OSError, ValueError) as exc:
                self.show_error(f"Could not load {path}: {exc}")

    def _save(self):
        path = filedialog.asksaveasfilename(parent=self, title="Save link settings", filetypes=FILE_TYPES,
                                            defaultextension=".json")
        if path:
            try:
                self.save_file(path)
            except (OSError, ValueError) as exc:
                self.show_error(f"Could not save {path}: {exc}")

    def payload(self):
        return self.message.get().encode("utf-8")

    def _changed(self):
        self._describe_frame()
        self.settings_changed()

    def _describe_frame(self):
        try:
            link = self.settings()
        except ValueError as exc:
            self.frame_text.set(str(exc))
            return
        size = len(self.payload())
        if not 1 <= size <= link.framing.max_payload:
            self.frame_text.set(f"{size} bytes; a frame carries 1 to {link.framing.max_payload}")
            return
        duration_s = link.frame_duration_s(size)
        self.frame_text.set(f"{size} bytes in {link.frame_length_bits(size)} symbols, {duration_s:.2f} s "
                            f"({8 * size / duration_s:.0f} bit/s net)")

    def show_error(self, message):
        self.frame_text.set(message)

    def set_status(self, status: SessionStatus):
        ready = status.connection == ConnectionState.CONNECTED and not status.transmitting
        self.send_button.configure(state="normal" if ready else "disabled")
