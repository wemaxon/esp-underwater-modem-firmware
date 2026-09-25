from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


class LivePlot(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.figure = Figure(figsize=(8, 5), dpi=100, layout="constrained")
        self.axes = self.figure.add_subplot()
        self.axes.set(xlabel="Time (ms)", ylabel="Amplitude (a.u.)", xlim=(0, 2), ylim=(-1.1, 1.1))
        self.axes.grid(True, alpha=0.25)
        self.line, = self.axes.plot([], [], linewidth=1)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self.canvas.draw()

    def update_frame(self, frame):
        self.line.set_data(frame.time_ms, frame.amplitude)
        self.canvas.draw_idle()

    def clear(self):
        self.line.set_data([], [])
        self.canvas.draw_idle()
