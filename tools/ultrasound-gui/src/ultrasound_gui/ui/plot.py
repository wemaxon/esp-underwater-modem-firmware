from math import isfinite
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import numpy as np

from ..model import StreamHistory


class ScopePlot(ttk.Frame):
    """Rolling view of the latest window of a stream: VOUT, OUT3 and the OUT3 frequency.

    Axes are static while streaming, so frames are blitted: the axes are drawn
    once into a cached background and only the data lines are redrawn.
    """

    FREQUENCY_KHZ = (0.0, 100.0)    # default range; widened when data falls outside

    def __init__(self, master):
        super().__init__(master)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.window_ms = 100.0
        self.background = None
        self.figure = Figure(figsize=(8, 5), dpi=100, layout="constrained")
        self.vout_axes, self.out3_axes, self.frequency_axes = self.figure.subplots(3, sharex=True, height_ratios=[3, 1, 2])
        self.vout_axes.set(ylabel="VOUT (V)", ylim=(0, 3.4))
        self.out3_axes.set(ylabel="OUT3", ylim=(-0.2, 1.2), yticks=[0, 1])
        self.frequency_axes.set(xlabel="Time (ms)", ylabel="Frequency (kHz)", ylim=self.FREQUENCY_KHZ)
        self.vout_line, = self.vout_axes.plot([], [], linewidth=1, animated=True)
        self.out3_line, = self.out3_axes.plot([], [], linewidth=1, drawstyle="steps-post", animated=True)
        self.frequency_line, = self.frequency_axes.plot([], [], linestyle="none", marker=".", markersize=2, animated=True)
        for axes in (self.vout_axes, self.out3_axes, self.frequency_axes):
            axes.grid(True, alpha=0.2)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew")
        self.canvas.mpl_connect("draw_event", self._on_full_draw)
        self.navigation = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        self.navigation.grid(row=0, column=0, sticky="ew")
        self.set_window_ms(self.window_ms)

    def set_window_ms(self, milliseconds):
        if not isfinite(milliseconds) or milliseconds <= 0:
            raise ValueError("Window must be a positive number of milliseconds")
        self.window_ms = milliseconds
        self.frequency_axes.set_xlim(-milliseconds, 0)
        self.navigation.update()
        self._redraw()

    def reset(self):
        """Clears the lines and restores the default frequency range."""
        for line in (self.vout_line, self.out3_line, self.frequency_line):
            line.set_data([], [])
        self.frequency_axes.set_ylim(self.FREQUENCY_KHZ)
        self._redraw()

    def show(self, history: StreamHistory):
        """Draws the window that ends at the newest data; times are relative to it."""
        end_ns = history.latest_ns
        start_ns = end_ns - round(self.window_ms * 1e6)

        def to_ms(times_ns):
            return (times_ns - end_ns) / 1e6

        times, volts = history.vout(start_ns, end_ns)
        self.vout_line.set_data(to_ms(times), volts)

        times, levels, initial = history.out3(start_ns, end_ns)
        if len(levels):
            initial = (not levels[0]) if initial is None else initial
            step_times = np.concatenate(([start_ns], times, [end_ns]))
            step_levels = np.concatenate(([initial], levels, levels[-1:])).astype(float)
            self.out3_line.set_data(to_ms(step_times), step_levels)
        else:
            self.out3_line.set_data([], [])

        times, hertz = history.out3_frequency(start_ns, end_ns)
        kilohertz = hertz / 1000
        self.frequency_line.set_data(to_ms(times), kilohertz)

        low, high = self.frequency_axes.get_ylim()
        if len(kilohertz) and (kilohertz.min() < low or kilohertz.max() > high):
            margin = 0.1 * (kilohertz.max() - kilohertz.min() or kilohertz.max() or 1)
            self.frequency_axes.set_ylim(min(low, kilohertz.min() - margin), max(high, kilohertz.max() + margin))
            self._redraw()
        elif self.background is not None:
            self.canvas.restore_region(self.background)
            self._draw_lines()
            self.canvas.blit(self.figure.bbox)

    def _redraw(self):
        """Full redraw after the axes changed; the cached background is stale until it completes."""
        self.background = None
        self.canvas.draw_idle()

    def _on_full_draw(self, event):
        self.background = self.canvas.copy_from_bbox(self.figure.bbox)
        self._draw_lines()

    def _draw_lines(self):
        for line in (self.vout_line, self.out3_line, self.frequency_line):
            self.figure.draw_artist(line)
