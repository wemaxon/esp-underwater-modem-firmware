"""Binary frequency-shift keying.

A 1 is sent at centre + shift and a 0 at centre - shift, with continuous phase.
The receiver correlates the OUT3 square wave with both tones over one symbol
(a noncoherent matched filter) and compares their energies. A small bank of
frequency offsets covers Doppler shift; the sync search picks one per frame.
"""

from dataclasses import dataclass

import numpy as np

from ..model import StreamHistory, Tone
from . import framing

STEPS_PER_SYMBOL = 8        # timing resolution of the sync search
SYNC_THRESHOLD = 0.15       # correlation with preamble and sync word; noise alone stays below 0.1


@dataclass(frozen=True)
class BfskSettings:
    center_hz: int = 40_000
    shift_hz: int = 1_000
    symbol_ms: float = 10.0

    def __post_init__(self):
        if not 0 < self.shift_hz < self.center_hz:
            raise ValueError("Shift must be positive and below the centre frequency")
        if self.center_hz - self.shift_hz < Tone.MIN_HZ or self.center_hz + self.shift_hz > Tone.MAX_HZ:
            raise ValueError(f"Tones must lie between {Tone.MIN_HZ} and {Tone.MAX_HZ} Hz")
        if not 1 <= self.symbol_ms <= 1000:
            raise ValueError("Symbol length must be between 1 and 1000 ms")
        if self.shift_hz * self.symbol_ms < 500:
            raise ValueError("Tones must be at least 1 / symbol length apart: shift x symbol length >= 500 Hz ms")

    @property
    def symbol_ns(self):
        return round(self.symbol_ms * 1e6)

    @property
    def offset_bins(self):
        """Frequency offsets searched, in units of half the symbol rate, up to half the shift."""
        limit = min(STEPS_PER_SYMBOL - 1, int(self.shift_hz * self.symbol_ms / 1000))
        return np.arange(-limit, limit + 1)

    def tone_hz(self, bit):
        return self.center_hz + self.shift_hz if bit else self.center_hz - self.shift_hz

    def played_hz(self, bit, transmit_clock_hz):
        """The tone as the device plays it, which the receiver correlates with."""
        return Tone(self.tone_hz(bit), 1).played_hz(transmit_clock_hz)


@dataclass(frozen=True)
class DecodedFrame:
    start_ns: int
    payload: bytes
    crc_ok: bool
    quality: float          # sync correlation, 1.0 for a perfect match
    offset_hz: float        # received minus nominal tone frequency


def modulate(bits, settings: BfskSettings, transmit_clock_hz):
    """Tones for the bits; runs of equal bits become one tone. Cycle counts follow the
    frequencies as the device plays them, so symbol boundaries stay on time."""
    bits = np.asarray(bits, np.uint8)
    run_ends = np.append(np.flatnonzero(np.diff(bits)) + 1, len(bits))
    tones, played_s = [], 0.0
    symbol_s = settings.symbol_ms / 1000
    for end in run_ends:
        hertz = settings.played_hz(bits[end - 1], transmit_clock_hz)
        cycles = max(1, round((end * symbol_s - played_s) * hertz))
        played_s += cycles / hertz
        tones.append(Tone(settings.tone_hz(bits[end - 1]), cycles))
    return tones


def _tone_correlations(history: StreamHistory, frequencies, start_ns, steps, step_ns):
    """Correlation of the OUT3 square wave (+-1) with exp(-j 2 pi f t) per step and frequency.

    The square wave is constant between edges, so each piece integrates exactly.
    """
    times, levels, initial = history.out3(start_ns, start_ns + steps * step_ns)
    boundaries = np.union1d(times, start_ns + step_ns * np.arange(steps + 1, dtype=np.int64))
    level_after = np.concatenate(([0.0 if initial is None else 2.0 * initial - 1], 2.0 * levels - 1))
    level = level_after[np.searchsorted(times, boundaries[:-1], side="right")]
    seconds = (boundaries - start_ns) / 1e9
    step = (boundaries[:-1] - start_ns) // step_ns
    result = np.empty((len(frequencies), steps), complex)
    for row, frequency_hz in enumerate(frequencies):
        omega = 2 * np.pi * frequency_hz
        phasor = np.exp(-1j * omega * seconds)
        pieces = level * (phasor[:-1] - phasor[1:]) / (1j * omega)
        result[row] = np.bincount(step, pieces.real, steps) + 1j * np.bincount(step, pieces.imag, steps)
    return result


def soft_symbols(history: StreamHistory, settings: BfskSettings, transmit_clock_hz, start_ns, end_ns):
    """Soft decisions for a symbol starting at every step of symbol / STEPS_PER_SYMBOL,
    per searched frequency offset: mark minus space energy, relative to the most a symbol
    can reach (all of its steps adding up in phase in one tone). So +1 only for a clean
    mark tone at the searched offset, -1 for a clean space tone and near 0 for noise.

    Returns the decisions [offset, step] and the offsets in hertz.
    """
    s = STEPS_PER_SYMBOL
    step_ns = settings.symbol_ns // s
    steps = max(0, (end_ns - start_ns) // step_ns)
    bins = settings.offset_bins
    offsets_hz = bins / (2 * settings.symbol_ms / 1000)
    if steps < s:
        return np.zeros((len(bins), 0)), offsets_hz
    tones_hz = (settings.played_hz(1, transmit_clock_hz), settings.played_hz(0, transmit_clock_hz))
    chunks = _tone_correlations(history, tones_hz, start_ns, steps, step_ns)
    derotation = np.exp(-1j * np.pi * np.outer(bins, np.arange(s)) / s)     # offset k turns k pi / s per step
    windows = np.lib.stride_tricks.sliding_window_view(chunks, s, axis=1)
    energy = np.abs(np.einsum("tps,bs->btp", windows, derotation)) ** 2
    limit = s * (np.abs(windows) ** 2).sum(axis=(0, 2))
    return np.divide(energy[:, 0] - energy[:, 1], limit, out=np.zeros_like(energy[:, 0]), where=limit > 0), offsets_hz


class _Incomplete(Exception):
    """The frame extends past the received data."""


def _read_frame(soft, start, link):
    """Payload, CRC status and end step of the frame whose preamble starts at step start,
    or None if the length is implausible."""
    s = STEPS_PER_SYMBOL

    def symbols(first, count):
        index = start + s * (first + np.arange(count))
        if index[-1] >= len(soft):
            raise _Incomplete
        return soft[index]

    offset = symbols(0, link.framing.preamble_bits).mean()      # alternating preamble averages to zero
    header = link.framing.preamble_bits + framing.SYNC_BITS
    header_bits = framing.header_bits(link.coding)
    length = framing.decode_length(symbols(header, header_bits) - offset, link.coding)
    if not 1 <= length <= link.framing.max_payload:
        return None
    body = header + header_bits
    count = framing.body_bits(length, link.coding)
    payload, crc_ok = framing.decode_body(symbols(body, count) - offset, length, link.coding)
    return payload, crc_ok, start + (body + count) * s


def decode(history: StreamHistory, link, transmit_clock_hz, start_ns, end_ns):
    """Frames of the link (LinkSettings) that start within [start_ns, end_ns] and are complete.

    Returns them with the time where the next search should start: before a frame
    still being received, or where a sync could not yet be recognized.
    """
    s = STEPS_PER_SYMBOL
    step_ns = link.modulation.symbol_ns // s
    soft, offsets_hz = soft_symbols(history, link.modulation, transmit_clock_hz, start_ns, end_ns)
    template = 2.0 * np.concatenate((framing.preamble(link.framing.preamble_bits), framing.sync_bits())) - 1
    positions = soft.shape[1] - (len(template) - 1) * s
    if positions <= 0:
        return [], start_ns
    scores = sum(sign * soft[:, n * s:n * s + positions] for n, sign in enumerate(template)) / len(template)
    best_offset = np.argmax(scores, axis=0)
    score = scores[best_offset, np.arange(positions)]
    resume = positions                  # a sync starting later is not fully received yet
    span = len(template) * s            # partial matches of a sync lie within one template length of it
    frames, position = [], 0
    candidates = np.flatnonzero(score >= SYNC_THRESHOLD)
    while len(candidates := candidates[candidates >= position]):
        if candidates[0] + span > positions:        # the peak may still be ahead
            resume = min(resume, candidates[0])
            break
        group = candidates[candidates < candidates[0] + span]
        best = group[np.argmax(score[group])]
        try:
            frame = _read_frame(soft[best_offset[best]], best, link)
        except _Incomplete:
            resume = min(resume, best)
            break
        if frame is None:
            position = best + s
            continue
        payload, crc_ok, end = frame
        frames.append(DecodedFrame(start_ns + int(best) * step_ns, payload, crc_ok, float(score[best]),
                                   float(offsets_hz[best_offset[best]])))
        position = end
        resume = max(resume, end)
    return frames, start_ns + int(resume) * step_ns
