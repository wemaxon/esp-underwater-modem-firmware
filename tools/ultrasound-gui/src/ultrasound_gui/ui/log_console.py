from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class LogConsole(ttk.LabelFrame):
    MAX_CHARS = 65_536

    def __init__(self, parent):
        super().__init__(parent, text="Device logs", padding=4)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.text = ScrolledText(self, height=7, wrap="word", state="disabled", font="TkFixedFont", undo=False)
        self.text.grid(row=0, column=0, sticky="nsew")

    def append(self, entries):
        content = "".join(entries)
        if not content:
            return
        follow = self.text.yview()[1] >= 0.999
        self.text.configure(state="normal")
        self.text.insert("end", content)
        excess = self.text.count("1.0", "end-1c", "chars")[0] - self.MAX_CHARS
        if excess > 0:
            self.text.delete("1.0", f"1.0+{excess}c")
        self.text.configure(state="disabled")
        if follow:
            self.text.see("end")
