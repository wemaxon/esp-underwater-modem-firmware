"""TUSS4470 receiver and transmitter settings on top of the configuration register block.

The device exchanges the registers as raw values in REGISTERS order (README
"CONFIG"); field meanings follow datasheet SLDS251A, section 7.6. Bits the
firmware relies on are not exposed here and are kept by the device.
"""

from dataclasses import dataclass

REGISTERS = (
    "BPF_CONFIG_1", "BPF_CONFIG_2", "DEV_CTRL_1", "DEV_CTRL_2", "ECHO_INT_CONFIG", "ZC_CONFIG", "VDRV_CTRL", "BURST_PULSE",
)

BPF_CENTER_KHZ = (
    40.64, 44.05, 45.6, 48.86, 50.58, 52.96, 56.75, 60.11, 62.95, 66.68, 71.44, 74.81, 79.24, 82.03, 86.89, 92.04,
    97.49, 103.27, 109.4, 114.54, 121.33, 128.52, 134.58, 142.55, 151.01, 159.94, 167.48, 177.41, 185.77, 196.78,
    206.05, 218.26, 228.54, 244.89, 256.43, 271.63, 284.43, 301.28, 319.13, 338.14, 353.97, 374.95, 397.16, 408.17,
    420.7, 455.63, 472.03, 500.0,
)


@dataclass(frozen=True)
class Setting:
    """A field of one register; choices[value] describes each field value."""
    label: str
    register: int
    shift: int
    width: int
    choices: tuple[str, ...]

    @property
    def mask(self):
        return ((1 << self.width) - 1) << self.shift

    def text(self, value):
        return self.choices[value] if value < len(self.choices) else f"Raw 0x{value:X}"


RECEIVER_SETTINGS = (
    Setting("Band-pass centre", 0, 0, 6, tuple(f"{khz:g} kHz" for khz in BPF_CENTER_KHZ)),
    Setting("Band-pass Q", 1, 4, 2, ("4", "5", "2", "3")),
    Setting("LNA gain", 3, 0, 2, ("15 V/V", "10 V/V", "20 V/V", "12.5 V/V")),
    Setting("Echo comparator", 4, 4, 1, ("Off", "On")),
    Setting("Echo threshold", 4, 0, 4, tuple(f"{0.4 + 0.04 * n:.2f} V" for n in range(16))),
    Setting("OUT3 only during echo", 5, 6, 1, ("Off", "On")),
    Setting("Zero-crossing stage", 5, 3, 2, tuple(f"Stage {n}" for n in range(4))),
    Setting("Zero-crossing hysteresis", 5, 0, 3, tuple(f"{30 + 50 * n} mV" for n in range(8))),
)

TRANSMITTER_SETTINGS = (
    Setting("VDRV voltage", 6, 0, 4, tuple(f"{5 + n} V" for n in range(16))),
    Setting("VDRV charging current", 6, 4, 1, ("10 mA", "20 mA")),
    Setting("Output stage", 7, 7, 1, ("Full bridge", "Half bridge")),
)


@dataclass(frozen=True)
class TussConfig:
    registers: tuple[int, ...]

    def __post_init__(self):
        registers = tuple(self.registers)
        if len(registers) != len(REGISTERS) or any(not 0 <= value <= 0xFF for value in registers):
            raise ValueError(f"TUSS4470 configuration needs {len(REGISTERS)} register values of 0 to 255")
        object.__setattr__(self, "registers", registers)

    def get(self, setting: Setting):
        return (self.registers[setting.register] & setting.mask) >> setting.shift

    def with_value(self, setting: Setting, value):
        if not 0 <= value < len(setting.choices):
            raise ValueError(f"{setting.label}: invalid value {value}")
        registers = list(self.registers)
        registers[setting.register] = (registers[setting.register] & ~setting.mask) | (value << setting.shift)
        return TussConfig(tuple(registers))

    def __bytes__(self):
        return bytes(self.registers)
