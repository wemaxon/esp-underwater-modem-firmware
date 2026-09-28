from math import isfinite
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from ..model import Capture


class ScopePlot(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.frame = None
        self.window_ms = 20.0
        self.figure = Figure(figsize=(8, 5), dpi=100, layout="constrained")
        self.envelope_axes, self.digital_axes, self.frequency_axes = self.figure.subplots(3, sharex=True, height_ratios=[3, 1.3, 2])
        self.envelope_axes.set(ylabel="VOUT (V)", ylim=(0, 3.3), title="Received envelope")
        self.envelope_line, = self.envelope_axes.plot([], [], linewidth=1)
        self.envelope_axes.text(0.5, 0.5, "VOUT not captured", transform=self.envelope_axes.transAxes, ha="center", color="0.4")
        self.digital_axes.set(ylim=(-0.2, 2.3), yticks=[0.35, 1.65], yticklabels=["OUT4", "OUT3"])
        self.out4_line, = self.digital_axes.step([], [], where="post", linewidth=1)
        self.digital_axes.text(0.02, 0.35, "OUT4 not captured", transform=self.digital_axes.get_yaxis_transform(), va="center", color="0.4")
        self.frequency_axes.set(xlabel="Time within capture (ms)", ylabel="Frequency (kHz)")
        self.digital_line, = self.digital_axes.step([], [], where="post", linewidth=1)
        self.frequency_line, = self.frequency_axes.plot([], [], linewidth=1, marker=".", markersize=2)
        for axes in (self.envelope_axes, self.digital_axes, self.frequency_axes):
            axes.grid(True, alpha=0.2)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew")
        self.navigation = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        self.navigation.grid(row=0, column=0, sticky="ew")
        self.set_window_ms(self.window_ms)

    def show(self, capture: Capture):
        self.frame = capture
        times, levels = capture.steps()
        self.digital_line.set_data(times, 1.3 + 0.7 * levels)
        self.frequency_line.set_data(*capture.frequency())
        self.digital_axes.set_xlim(0, self.window_ms)
        self.frequency_axes.relim()
        self.frequency_axes.autoscale_view(scalex=False)
        self.navigation.update()
        self.canvas.draw_idle()

    def set_window_ms(self, milliseconds):
        if not isfinite(milliseconds) or not 0.1 <= milliseconds <= 10000:
            raise ValueError("Graph window must be between 0.1 and 10000 ms")
        self.window_ms = milliseconds
        self.digital_axes.set_xlim(0, milliseconds)
        self.navigation.update()
        self.canvas.draw_idle()

    def clear(self):
        self.frame = None
        self.digital_line.set_data([], [])
        self.frequency_line.set_data([], [])
        self.canvas.draw_idle()
