import tkinter as tk
from tkinter import ttk

from ..modem.bfsk import DecodedFrame


def _printable(payload: bytes):
    """The payload as text, with control characters escaped."""
    text = payload.decode("utf-8", errors="replace")
    return "".join(char if char.isprintable() else f"\\x{ord(char):02x}" for char in text)


class ReceivedFrames(ttk.Frame):
    """The frames decoded from the stream, one row each."""

    COLUMNS = (("time", "Time (s)", 80), ("crc", "CRC", 70), ("quality", "q", 50),
               ("offset", "Offset (Hz)", 80), ("bytes", "Bytes", 50), ("payload", "Payload", 400))

    def __init__(self, master, count_changed):
        super().__init__(master, padding=4)
        self.count_changed = count_changed
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        toolbar.columnconfigure(0, weight=1)
        self.decoding = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text="Decode while streaming", variable=self.decoding).grid(row=0, column=0, sticky="w")
        ttk.Button(toolbar, text="Clear", command=self.clear).grid(row=0, column=1)
        self.table = ttk.Treeview(self, columns=[name for name, _, _ in self.COLUMNS], show="headings", height=5)
        for name, heading, width in self.COLUMNS:
            self.table.heading(name, text=heading)
            self.table.column(name, width=width, stretch=name == "payload",
                              anchor="w" if name in ("crc", "payload") else "e")
        self.table.tag_configure("error", foreground="#b33b35")
        self.table.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.table.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scrollbar.set)

    def rows(self):
        return [self.table.item(item, "values") for item in self.table.get_children()]

    def add_frames(self, frames: list[DecodedFrame]):
        if not frames:
            return
        for frame in frames:
            item = self.table.insert("", "end", tags=() if frame.crc_ok else ("error",), values=(
                f"{frame.start_ns / 1e9:.3f}", "OK" if frame.crc_ok else "Error", f"{frame.quality:.2f}",
                f"{frame.offset_hz:+.0f}", len(frame.payload), _printable(frame.payload)))
        self.table.see(item)
        self.count_changed(len(self.table.get_children()))

    def clear(self):
        self.table.delete(*self.table.get_children())
        self.count_changed(0)
