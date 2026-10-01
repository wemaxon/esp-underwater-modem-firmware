import unittest

import support  # noqa: F401  (import path setup)
from ultrasound_gui.tf_protocol import DEVICE_ERROR, OK, ProtocolError, decode_config
from ultrasound_gui.tuss_config import BPF_CENTER_KHZ, RECEIVER_SETTINGS, TRANSMITTER_SETTINGS, TussConfig

RESET = TussConfig((0x00, 0x00, 0x00, 0x00, 0x07, 0x94, 0x20, 0x00))
SETTING = {setting.label: setting for setting in RECEIVER_SETTINGS + TRANSMITTER_SETTINGS}


def text(config, label):
    return SETTING[label].text(config.get(SETTING[label]))


class TussConfigTests(unittest.TestCase):
    def test_reads_fields_of_the_reset_configuration(self):
        self.assertEqual(text(RESET, "Band-pass centre"), "40.64 kHz")
        self.assertEqual(text(RESET, "LNA gain"), "15 V/V")
        self.assertEqual(text(RESET, "Echo threshold"), "0.68 V")
        self.assertEqual(text(RESET, "Zero-crossing hysteresis"), "230 mV")
        self.assertEqual(text(RESET, "Zero-crossing stage"), "Stage 2")
        self.assertEqual(text(RESET, "OUT3 only during echo"), "Off")
        self.assertEqual(text(RESET, "VDRV voltage"), "5 V")
        self.assertEqual(text(RESET, "VDRV charging current"), "10 mA")
        self.assertEqual(text(RESET, "Output stage"), "Full bridge")

    def test_changing_a_field_keeps_the_other_bits(self):
        config = RESET.with_value(SETTING["OUT3 only during echo"], 1).with_value(SETTING["Zero-crossing hysteresis"], 7)
        self.assertEqual(config.registers[5], 0x94 | 0x40 | 0x07)
        config = config.with_value(SETTING["VDRV voltage"], 7).with_value(SETTING["VDRV charging current"], 1)
        self.assertEqual(config.registers[6], 0x20 | 0x10 | 0x07)      # VDRV_HI_Z kept
        self.assertEqual(config.with_value(SETTING["Output stage"], 1).registers[7], 0x80)
        self.assertEqual(bytes(config), bytes([0, 0, 0, 0, 0x07, 0xD7, 0x37, 0]))

    def test_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            RESET.with_value(SETTING["Band-pass centre"], len(BPF_CENTER_KHZ))
        with self.assertRaises(ValueError):
            TussConfig((0, 0, 0))
        with self.assertRaises(ValueError):
            TussConfig((0, 0, 0, 0, 0, 0, 0, 256))

    def test_undocumented_values_are_shown_raw(self):
        self.assertEqual(SETTING["Band-pass centre"].text(0x30), "Raw 0x30")


class ConfigResponseTests(unittest.TestCase):
    def test_decodes_the_device_configuration(self):
        self.assertEqual(decode_config(bytes([OK]) + bytes(RESET)), (OK, RESET))
        self.assertEqual(decode_config(bytes([DEVICE_ERROR])), (DEVICE_ERROR, None))
        for payload in (b"", bytes([OK]), bytes([OK]) + bytes(RESET) + b"\0", bytes([DEVICE_ERROR, 0])):
            with self.subTest(payload=payload.hex()), self.assertRaises(ProtocolError):
                decode_config(payload)


if __name__ == "__main__":
    unittest.main()
