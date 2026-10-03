"""Packet framing, shared by all modulations.

A frame is, bit by bit and most significant bit first:

    preamble   alternating 1, 0, ... for level and timing acquisition
    sync word  16 bits, marks the frame start
    length     8 bits, payload size in bytes
    payload    length bytes
    CRC        16 bits, CRC-16/CCITT-FALSE over length and payload
"""

import numpy as np

SYNC_WORD = 0x2DD4
SYNC_BITS = 16
LENGTH_BITS = 8
CRC_BITS = 16
MAX_PAYLOAD = 255


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


def frame_bits(payload: bytes, preamble_bits):
    if not 1 <= len(payload) <= MAX_PAYLOAD:
        raise ValueError(f"Payload must have 1 to {MAX_PAYLOAD} bytes")
    body = bytes([len(payload)]) + payload
    return np.concatenate((preamble(preamble_bits), sync_bits(), to_bits(body + crc16(body).to_bytes(2, "big"))))


def frame_length_bits(payload_bytes, preamble_bits):
    return preamble_bits + SYNC_BITS + LENGTH_BITS + 8 * payload_bytes + CRC_BITS
