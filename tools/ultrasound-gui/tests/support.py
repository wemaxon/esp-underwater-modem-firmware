"""Shared test setup: makes the GUI package importable and provides helpers."""

from pathlib import Path
from struct import pack
import sys
import time

SOURCE = Path(__file__).resolve().parents[1] / "src"
REPOSITORY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SOURCE))


def capture_payload(edges=(100, 200, 300, 400), duration=1000, initial=0):
    return pack(f"<BBIH{len(edges)}I", 0, initial, duration, len(edges), *edges)


def wait_until(predicate, timeout=2.0, message="Timed out waiting for condition"):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError(message)
        time.sleep(0.002)
