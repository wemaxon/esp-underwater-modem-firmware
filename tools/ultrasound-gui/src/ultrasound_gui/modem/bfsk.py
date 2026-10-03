"""Binary frequency-shift keying.

A 1 is sent at centre + shift and a 0 at centre - shift, with continuous phase.
The receiver measures the OUT3 frequency between rising zero crossings, maps it
onto [-1, 1] (space to mark tone) and averages it over the middle of each symbol.
"""

from dataclasses import dataclass

import numpy as np

from ..model import StreamHistory, Tone
from . import framing

STEPS_PER_SYMBOL = 8        # discriminator resolution
SYNC_THRESHOLD = 0.6        # normalized correlation with preamble and sync word


@dataclass(frozen=True)
class BfskSettings:
    center_hz: int = 40_000
    shift_hz: int = 1_000
    symbol_ms: float = 10.0
    preamble_bits: int = 16
    max_payload: int = 32           # longer frames are rejected as false syncs

    def __post_init__(self):
        if not 0 < self.shift_hz < self.center_hz:
            raise ValueError("Shift must be positive and below the centre frequency")
        if self.center_hz - self.shift_hz < Tone.MIN_HZ or self.center_hz + self.shift_hz > Tone.MAX_HZ:
            raise ValueError(f"Tones must lie between {Tone.MIN_HZ} and {Tone.MAX_HZ} Hz")
        if not 1 <= self.symbol_ms <= 1000:
            raise ValueError("Symbol length must be between 1 and 1000 ms")
        if not 4 <= self.preamble_bits <= 256 or self.preamble_bits % 2:
            raise ValueError("Preamble must be an even number of 4 to 256 bits")
        if not 1 <= self.max_payload <= framing.MAX_PAYLOAD:
            raise ValueError(f"Maximum payload must be 1 to {framing.MAX_PAYLOAD} bytes")

    @property
    def symbol_ns(self):
        return round(self.symbol_ms * 1e6)

    def tone_hz(self, bit):
        return self.center_hz + self.shift_hz if bit else self.center_hz - self.shift_hz

    def frame_duration_s(self, payload_bytes):
        return framing.frame_length_bits(payload_bytes, self.preamble_bits) * self.symbol_ms / 1000


@dataclass(frozen=True)
class DecodedFrame:
    start_ns: int
    payload: bytes
    crc_ok: bool
    quality: float          # sync correlation, 1.0 for a perfect match


def modulate(bits, settings: BfskSettings, transmit_clock_hz):
    """Tones for the bits; runs of equal bits become one tone. Cycle counts follow the
    frequencies as the device plays them, so symbol boundaries stay on time."""
    bits = np.asarray(bits, np.uint8)
    run_ends = np.append(np.flatnonzero(np.diff(bits)) + 1, len(bits))
    tones, played_s = [], 0.0
    symbol_s = settings.symbol_ms / 1000
    for end in run_ends:
        tone = Tone(settings.tone_hz(bits[end - 1]), 1)
        hertz = tone.played_hz(transmit_clock_hz)
        cycles = max(1, round((end * symbol_s - played_s) * hertz))
        played_s += cycles / hertz
        tones.append(Tone(tone.frequency_hz, cycles))
    return tones


def discriminator(history: StreamHistory, settings: BfskSettings, start_ns, end_ns):
    """Mean frequency deviation per step of symbol / STEPS_PER_SYMBOL: +1 at the mark
    tone, -1 at the space tone, 0 where no zero crossings near the tones were seen."""
    step_ns = settings.symbol_ns // STEPS_PER_SYMBOL
    steps = max(0, (end_ns - start_ns) // step_ns)
    times, levels, _ = history.out3(start_ns, end_ns)
    rising = times[levels]
    deviation = np.zeros(steps)
    if len(rising) < 2 or not steps:
        return deviation
    offsets = (1e9 / np.diff(rising) - settings.center_hz) / settings.shift_hz
    index = (rising[1:] - start_ns) // step_ns
    valid = (np.abs(offsets) <= 2) & (index >= 0) & (index < steps)     # near the tones only
    sums = np.bincount(index[valid], np.clip(offsets[valid], -1, 1), steps)
    counts = np.bincount(index[valid], minlength=steps)
    np.divide(sums, counts, out=deviation, where=counts > 0)
    return deviation


class _Incomplete(Exception):
    """The frame extends past the received data."""


def _read_frame(deviation, start, settings: BfskSettings):
    """Payload, CRC status and end step of the frame whose preamble starts at step start,
    or None if the length is implausible."""
    s = STEPS_PER_SYMBOL

    def symbols(first, count):
        begin = start + first * s
        if begin + count * s > len(deviation):
            raise _Incomplete
        window = deviation[begin:begin + count * s].reshape(count, s)
        return window[:, s // 4:3 * s // 4].mean(axis=1)

    offset = symbols(0, settings.preamble_bits).mean()      # alternating preamble averages to zero
    header = settings.preamble_bits + framing.SYNC_BITS
    length = framing.from_bits(symbols(header, framing.LENGTH_BITS) - offset > 0)[0]
    if not 1 <= length <= settings.max_payload:
        return None
    body_bits = framing.LENGTH_BITS + 8 * length
    bits = symbols(header, body_bits + framing.CRC_BITS) - offset > 0
    body = framing.from_bits(bits[:body_bits])
    crc_ok = framing.crc16(body) == int.from_bytes(framing.from_bits(bits[body_bits:]), "big")
    return body[1:], crc_ok, start + (header + body_bits + framing.CRC_BITS) * s


def decode(history: StreamHistory, settings: BfskSettings, start_ns, end_ns):
    """Frames that start within [start_ns, end_ns] and are complete.

    Returns them with the time where the next search should start: before a frame
    still being received, or where a sync could not yet be recognized.
    """
    step_ns = settings.symbol_ns // STEPS_PER_SYMBOL
    deviation = discriminator(history, settings, start_ns, end_ns)
    template = np.repeat(2.0 * np.concatenate((framing.preamble(settings.preamble_bits), framing.sync_bits())) - 1,
                         STEPS_PER_SYMBOL)
    if len(deviation) < len(template):
        return [], start_ns
    score = np.correlate(deviation, template, "valid") / len(template)
    resume = len(score)                 # a sync starting later is not fully received yet
    frames, position = [], 0
    candidates = np.flatnonzero(score >= SYNC_THRESHOLD)
    while len(candidates := candidates[candidates >= position]):
        group = candidates[candidates <= candidates[0] + STEPS_PER_SYMBOL]
        best = group[np.argmax(score[group])]
        try:
            frame = _read_frame(deviation, best, settings)
        except _Incomplete:
            resume = min(resume, best)
            break
        if frame is None:
            position = best + STEPS_PER_SYMBOL
            continue
        payload, crc_ok, end = frame
        frames.append(DecodedFrame(start_ns + int(best) * step_ns, payload, crc_ok, float(score[best])))
        position = end
        resume = max(resume, end)
    return frames, start_ns + int(resume) * step_ns
