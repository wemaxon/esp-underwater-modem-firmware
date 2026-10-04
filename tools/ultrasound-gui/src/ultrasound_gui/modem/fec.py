"""Forward error correction: the K=7 convolutional code (generators 171, 133 octal)
at rate 1/2, or punctured to 2/3 or 3/4, decoded with soft-decision Viterbi, and a
block interleaver against bursts.

Each block is terminated with K - 1 zero bits, so the decoder ends in state 0.
Soft values are positive for a 1 and negative for a 0; their size is the confidence.
Punctured code bits are not sent and decode as 0, unknown.
"""

from dataclasses import dataclass

import numpy as np

CONSTRAINT_LENGTH = 7
GENERATORS = (0o171, 0o133)
TAIL_BITS = CONSTRAINT_LENGTH - 1
PUNCTURING = {                  # code bits sent, in pairs per data bit (171, 133); None sends the data uncoded
    "Off": None,
    "1/2": (1, 1),
    "2/3": (1, 1, 0, 1),
    "3/4": (1, 1, 0, 1, 1, 0),
}
INTERLEAVER_DEPTHS = (0, 4, 8, 16, 32)

_STATES = 1 << TAIL_BITS
_PARITY = np.array([bin(value).count("1") & 1 for value in range(1 << CONSTRAINT_LENGTH)], np.uint8)


@dataclass(frozen=True)
class CodingSettings:
    rate: str = "1/2"
    interleaver: int = 16       # columns the code is written in by rows and sent by; 0 sends it in order

    def __post_init__(self):
        if self.rate not in PUNCTURING:
            raise ValueError(f"Code rate must be one of {', '.join(PUNCTURING)}")
        if self.interleaver not in INTERLEAVER_DEPTHS:
            raise ValueError(f"Interleaver depth must be one of {', '.join(map(str, INTERLEAVER_DEPTHS))}")


def _sent(coding: CodingSettings, data_bits):
    """Which code bits of a terminated block are sent."""
    return np.resize(np.array(PUNCTURING[coding.rate], bool), len(GENERATORS) * (data_bits + TAIL_BITS))


def coded_length(data_bits, coding: CodingSettings):
    return data_bits if PUNCTURING[coding.rate] is None else int(_sent(coding, data_bits).sum())


def _outputs(registers):
    """Code bits for registers holding the newest input bit in the top bit."""
    return np.stack([_PARITY[registers & generator] for generator in GENERATORS], axis=-1)


def _convolve(bits):
    state, registers = 0, []
    for bit in np.concatenate((np.asarray(bits, np.uint8), np.zeros(TAIL_BITS, np.uint8))):
        register = (int(bit) << TAIL_BITS) | state
        registers.append(register)
        state = register >> 1
    return _outputs(np.array(registers, np.int64)).reshape(-1)


# Every state is reached from two registers, which differ in their oldest bit.
_NEXT = np.arange(_STATES)
_REGISTERS = np.stack([(_NEXT << 1) | oldest for oldest in (0, 1)])         # [oldest bit, next state]
_PREVIOUS = _REGISTERS & (_STATES - 1)
_SIGNS = 2.0 * _outputs(_REGISTERS) - 1                                     # [oldest bit, next state, code bit]


def _viterbi(soft):
    """Most likely data bits for the soft values of all code bits of a terminated block."""
    pairs = np.asarray(soft, float).reshape(-1, len(GENERATORS))
    metric = np.full(_STATES, -np.inf)
    metric[0] = 0.0
    choices = np.empty((len(pairs), _STATES), np.uint8)
    for step, pair in enumerate(pairs):
        candidates = metric[_PREVIOUS] + _SIGNS @ pair
        choices[step] = candidates[1] > candidates[0]
        metric = candidates.max(axis=0)
    state, bits = 0, np.empty(len(pairs), np.uint8)
    for step in range(len(pairs) - 1, -1, -1):
        bits[step] = state >> (TAIL_BITS - 1)
        state = _PREVIOUS[choices[step, state], state]
    return bits[:-TAIL_BITS]


def _order(length, columns):
    """Channel order: the code written into rows of columns, read by columns."""
    if columns <= 1:
        return np.arange(length)
    return np.argsort(np.arange(length) % columns, kind="stable")


def encode(bits, coding: CodingSettings):
    """Channel bits for one block of data bits."""
    bits = np.asarray(bits, np.uint8)
    coded = bits if PUNCTURING[coding.rate] is None else _convolve(bits)[_sent(coding, len(bits))]
    return coded[_order(len(coded), coding.interleaver)]


def decode(soft, data_bits, coding: CodingSettings):
    """Most likely data bits for the soft values of one block's channel bits."""
    soft = np.asarray(soft, float)
    coded = np.empty_like(soft)
    coded[_order(len(soft), coding.interleaver)] = soft
    if PUNCTURING[coding.rate] is None:
        return (coded > 0).astype(np.uint8)
    sent = _sent(coding, data_bits)
    full = np.zeros(len(sent))
    full[sent] = coded
    return _viterbi(full)
