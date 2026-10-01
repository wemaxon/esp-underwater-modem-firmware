"""Shared test setup: makes the GUI package importable and provides helpers."""

from pathlib import Path
import sys
import time

SOURCE = Path(__file__).resolve().parents[1] / "src"
REPOSITORY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SOURCE))

from ultrasound_gui.model import DeviceInfo  # noqa: E402

INFO = DeviceInfo("Test", vout_rate_hz=20_000, edge_clock_hz=10_000_000)


def wait_until(predicate, timeout=2.0, message="Timed out waiting for condition"):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError(message)
        time.sleep(0.002)
