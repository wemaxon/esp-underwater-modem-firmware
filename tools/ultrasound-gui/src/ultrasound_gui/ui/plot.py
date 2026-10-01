from math import isfinite
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import numpy as np

from ..model import StreamHistory


class ScopePlot(ttk.Frame):
    """VOUT, OUT3 and the OUT3 frequency over a window of a stream.

    The window spans pre-trigger time before an origin and the rest after it;
    times are shown relative to the origin. A rolling view puts the origin at
    the newest data with the whole window before it.

    Axes are static while streaming, so frames are blitted: the axes are drawn
    once into a cached background and only the data lines are redrawn.
    """

    FREQUENCY_KHZ = (0.0, 100.0)    # default range; widened when data falls outside

    def __init__(self, master):
        super().__init__(master)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.window_ms = 100.0
        self.pre_ms = 100.0
        self.background = None
        self.figure = Figure(figsize=(8, 5), dpi=100, layout="constrained")
        self.vout_axes, self.out3_axes, self.frequency_axes = self.figure.subplots(3, sharex=True, height_ratios=[3, 1, 2])
        self.vout_axes.set(ylabel="VOUT (V)", ylim=(0, 3.4))
        self.out3_axes.set(ylabel="OUT3", ylim=(-0.2, 1.2), yticks=[0, 1])
        self.frequency_axes.set(xlabel="Time (ms)", ylabel="Frequency (kHz)", ylim=self.FREQUENCY_KHZ)
        self.vout_line, = self.vout_axes.plot([], [], linewidth=1, animated=True)
        self.trigger_line = self.vout_axes.axhline(0, color="#b33b35", linewidth=0.8, linestyle="--", visible=False)
        self.out3_line, = self.out3_axes.plot([], [], linewidth=1, drawstyle="steps-post", animated=True)
        self.frequency_line, = self.frequency_axes.plot([], [], linestyle="none", marker=".", markersize=2, animated=True)
        for axes in (self.vout_axes, self.out3_axes, self.frequency_axes):
            axes.grid(True, alpha=0.2)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew")
        self.canvas.mpl_connect("draw_event", self._on_full_draw)
        self.navigation = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        self.navigation.grid(row=0, column=0, sticky="ew")
        self.set_view(self.window_ms, self.pre_ms)

    def set_view(self, window_ms, pre_ms):
        if not (isfinite(window_ms) and isfinite(pre_ms) and window_ms > 0 and 0 <= pre_ms <= window_ms):
            raise ValueError("Window must be positive and pre-trigger time within it")
        self.window_ms, self.pre_ms = window_ms, pre_ms
        self.frequency_axes.set_xlim(-pre_ms, window_ms - pre_ms)
        self.navigation.update()
        self._redraw()

    def set_trigger_level(self, volts):
        """Shows the trigger level on the VOUT axes; None hides it."""
        self.trigger_line.set_visible(volts is not None)
        if volts is not None:
            self.trigger_line.set_ydata([volts, volts])
        self._redraw()

    def reset(self):
        """Clears the lines and restores the default frequency range."""
        for line in (self.vout_line, self.out3_line, self.frequency_line):
            line.set_data([], [])
        self.frequency_axes.set_ylim(self.FREQUENCY_KHZ)
        self._redraw()

    def show(self, history: StreamHistory, origin_ns):
        """Draws the window around origin_ns."""
        start_ns = origin_ns - round(self.pre_ms * 1e6)
        end_ns = start_ns + round(self.window_ms * 1e6)

        def to_ms(times_ns):
            return (times_ns - origin_ns) / 1e6

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
