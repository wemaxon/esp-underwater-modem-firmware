"""Packet framing, shared by all modulations.

A frame is, bit by bit and most significant bit first:

    preamble   alternating 1, 0, ... for level and timing acquisition
    sync word  16 bits, marks the frame start
    header     payload length in bytes (8 bits), coded
    body       payload, then CRC-16/CCITT-FALSE over length and payload, coded

Header and body are separate coded blocks (see fec), so the receiver learns the
body length before decoding it.
"""

from dataclasses import dataclass

import numpy as np

from . import fec
from .fec import CodingSettings

SYNC_WORD = 0x2DD4
SYNC_BITS = 16
LENGTH_BITS = 8
CRC_BITS = 16
MAX_PAYLOAD = 255


@dataclass(frozen=True)
class FramingSettings:
    preamble_bits: int = 16
    max_payload: int = 32           # longer frames are rejected as false syncs

    def __post_init__(self):
        if not 4 <= self.preamble_bits <= 256 or self.preamble_bits % 2:
            raise ValueError("Preamble must be an even number of 4 to 256 bits")
        if not 1 <= self.max_payload <= MAX_PAYLOAD:
            raise ValueError(f"Maximum payload must be 1 to {MAX_PAYLOAD} bytes")


def crc16(data: bytes):
    """CRC-16/CCITT-FALSE: polynomial 0x1021, initial value 0xFFFF."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def to_bits(data: bytes):
    return np.unpackbits(np.frombuffer(data, np.uint8))


def from_bits(bits):
    return np.packbits(np.asarray(bits, np.uint8)).tobytes()


def preamble(length):
    return (np.arange(length) % 2 == 0).astype(np.uint8)


def sync_bits():
    return to_bits(SYNC_WORD.to_bytes(2, "big"))


def header_bits(coding: CodingSettings):
    return fec.coded_length(LENGTH_BITS, coding)


def body_bits(payload_bytes, coding: CodingSettings):
    return fec.coded_length(8 * payload_bytes + CRC_BITS, coding)


def frame_bits(payload: bytes, framing: FramingSettings, coding: CodingSettings):
    if not 1 <= len(payload) <= framing.max_payload:
        raise ValueError(f"The message must have 1 to {framing.max_payload} bytes, the maximum payload")
    crc = crc16(bytes([len(payload)]) + payload)
    return np.concatenate((preamble(framing.preamble_bits), sync_bits(),
                           fec.encode(to_bits(bytes([len(payload)])), coding),
                           fec.encode(to_bits(payload + crc.to_bytes(2, "big")), coding)))


def frame_length_bits(payload_bytes, framing: FramingSettings, coding: CodingSettings):
    return framing.preamble_bits + SYNC_BITS + header_bits(coding) + body_bits(payload_bytes, coding)


def decode_length(soft, coding: CodingSettings):
    """Payload length from the soft values of the header."""
    return from_bits(fec.decode(soft, LENGTH_BITS, coding))[0]


def decode_body(soft, length, coding: CodingSettings):
    """Payload and CRC status from the soft values of the body."""
    body = from_bits(fec.decode(soft, 8 * length + CRC_BITS, coding))
    payload, crc = body[:length], int.from_bytes(body[length:], "big")
    return payload, crc16(bytes([length]) + payload) == crc
