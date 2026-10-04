"""The settings both ends of a link must share: modulation, coding and framing.

They are not sent over the air, so both GUIs load the same settings file.
"""

import json
from dataclasses import asdict, dataclass, field

from . import framing
from .bfsk import BfskSettings
from .fec import CodingSettings
from .framing import FramingSettings


@dataclass(frozen=True)
class LinkSettings:
    modulation: BfskSettings = field(default_factory=BfskSettings)
    coding: CodingSettings = field(default_factory=CodingSettings)
    framing: FramingSettings = field(default_factory=FramingSettings)

    def frame_bits(self, payload: bytes):
        return framing.frame_bits(payload, self.framing, self.coding)

    def frame_length_bits(self, payload_bytes):
        return framing.frame_length_bits(payload_bytes, self.framing, self.coding)

    def frame_duration_s(self, payload_bytes):
        return self.frame_length_bits(payload_bytes) * self.modulation.symbol_ms / 1000

    def to_json(self):
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text):
        """Raises ValueError for anything but valid settings."""
        try:
            data = json.loads(text)
            return cls(BfskSettings(**data["modulation"]), CodingSettings(**data["coding"]),
                       FramingSettings(**data["framing"]))
        except (TypeError, KeyError) as exc:
            raise ValueError(f"Not a link settings file: {exc}") from exc
