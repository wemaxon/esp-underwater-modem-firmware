import unittest

import support  # noqa: F401  (import path setup)
from ultrasound_gui.afe import BPF_CENTER_KHZ, SETTINGS, AfeConfig
from ultrasound_gui.tf_protocol import DEVICE_ERROR, OK, ProtocolError, decode_afe

RESET = AfeConfig((0x00, 0x00, 0x00, 0x00, 0x07, 0x94))
SETTING = {setting.label: setting for setting in SETTINGS}


class AfeConfigTests(unittest.TestCase):
    def test_reads_fields_of_the_reset_configuration(self):
        self.assertEqual(SETTING["Band-pass centre"].text(RESET.get(SETTING["Band-pass centre"])), "40.64 kHz")
        self.assertEqual(SETTING["LNA gain"].text(RESET.get(SETTING["LNA gain"])), "15 V/V")
        self.assertEqual(SETTING["Echo threshold"].text(RESET.get(SETTING["Echo threshold"])), "0.68 V")
        self.assertEqual(SETTING["Zero-crossing hysteresis"].text(RESET.get(SETTING["Zero-crossing hysteresis"])), "230 mV")
        self.assertEqual(SETTING["Zero-crossing stage"].text(RESET.get(SETTING["Zero-crossing stage"])), "Stage 2")
        self.assertEqual(RESET.get(SETTING["OUT3 only during echo"]), 0)

    def test_changing_a_field_keeps_the_other_bits(self):
        config = RESET.with_value(SETTING["OUT3 only during echo"], 1).with_value(SETTING["Zero-crossing hysteresis"], 7)
        self.assertEqual(config.registers[5], 0x94 | 0x40 | 0x07)
        self.assertEqual(config.with_value(SETTING["Band-pass Q"], 2).registers[1], 0x20)
        self.assertEqual(bytes(config), bytes([0, 0, 0, 0, 0x07, 0xD7]))

    def test_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            RESET.with_value(SETTING["Band-pass centre"], len(BPF_CENTER_KHZ))
        with self.assertRaises(ValueError):
            AfeConfig((0, 0, 0))
        with self.assertRaises(ValueError):
            AfeConfig((0, 0, 0, 0, 0, 256))

    def test_undocumented_values_are_shown_raw(self):
        self.assertEqual(SETTING["Band-pass centre"].text(0x30), "Raw 0x30")


class AfeResponseTests(unittest.TestCase):
    def test_decodes_the_device_configuration(self):
        self.assertEqual(decode_afe(bytes([OK]) + bytes(RESET)), (OK, RESET))
        self.assertEqual(decode_afe(bytes([DEVICE_ERROR])), (DEVICE_ERROR, None))
        for payload in (b"", bytes([OK]), bytes([OK]) + bytes(RESET) + b"\0", bytes([DEVICE_ERROR, 0])):
            with self.subTest(payload=payload.hex()), self.assertRaises(ProtocolError):
                decode_afe(payload)


if __name__ == "__main__":
    unittest.main()
