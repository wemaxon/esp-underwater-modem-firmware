import tkinter as tk
from tkinter import ttk

WHEEL_WIDGETS = ("TCombobox", "TSpinbox")      # use the wheel for their values, not for scrolling


def _wheel(event):
    """Scrolls the ScrollableFrame under the pointer, if any."""
    widget = event.widget
    if not isinstance(widget, tk.Misc) or widget.winfo_class() in WHEEL_WIDGETS:
        return
    while widget is not None and not isinstance(widget, ScrollableFrame):
        widget = widget.master
    if widget is not None:
        widget.scroll(-1 if event.delta > 0 else 1)


class ScrollableFrame(ttk.Frame):
    """Holds content that scrolls vertically when it does not fit; the scrollbar shows only then.
    Put the content into .content."""

    def __init__(self, master, padding=0):
        super().__init__(master)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        background = ttk.Style(self).lookup("TFrame", "background")
        self.canvas = tk.Canvas(self, height=1, highlightthickness=0, borderwidth=0, background=background)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.content = ttk.Frame(self.canvas, padding=padding)
        self.content.columnconfigure(0, weight=1)
        self.window = self.canvas.create_window(0, 0, window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda event: self._fit())
        self.canvas.bind("<Configure>", lambda event: self._fit())
        if not self.bind_all("<MouseWheel>"):
            self.bind_all("<MouseWheel>", _wheel)

    def _fit(self):
        """Matches the canvas width to the content and shows the scrollbar if the content is taller."""
        width, height = self.content.winfo_reqwidth(), self.content.winfo_reqheight()
        if int(self.canvas.cget("width")) != width:
            self.canvas.configure(width=width)
        self.canvas.itemconfigure(self.window, width=max(width, self.canvas.winfo_width()))
        self.canvas.configure(scrollregion=(0, 0, width, height))
        if height > self.canvas.winfo_height():
            self.scrollbar.grid(row=0, column=1, sticky="ns")
        else:
            self.scrollbar.grid_remove()
            self.canvas.yview_moveto(0)

    def scroll(self, units):
        if self.scrollbar.winfo_ismapped():
            self.canvas.yview_scroll(units, "units")
