"""Unit tests for config loading and validation. Runtime: stdlib unittest."""

import json
import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import main  # noqa: E402


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix=".test-tmp-", dir=TEST_ROOT)
        self.config_path = os.path.join(self.temp_dir.name, "config.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_raw(self, payload):
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def test_missing_file_is_created_with_defaults(self):
        config, warnings = main.load_config(self.config_path)
        self.assertEqual(warnings, [])
        self.assertEqual(config, main.DEFAULT_CONFIG)
        self.assertTrue(os.path.isfile(self.config_path))
        with open(self.config_path, "r", encoding="utf-8") as handle:
            saved = json.load(handle)
        self.assertEqual(saved, main.DEFAULT_CONFIG)

    def test_valid_custom_config_is_loaded(self):
        raw = {
            "interval_ms": 100,
            "jitter_ms": 10,
            "only_in_game": False,
            "exit_hotkey": "Shift+F9",
            "trigger_mode": "passthrough",
            "game_process": "OtherGame.exe",
            "debug_log": True,
        }
        self.write_raw(raw)
        config, warnings = main.load_config(self.config_path)
        self.assertEqual(warnings, [])
        self.assertEqual(config, raw)

    def test_interval_invalid_values_fall_back(self):
        for bad_value in (4, 501, True, 25.0, "25"):
            with self.subTest(value=bad_value):
                self.write_raw({"interval_ms": bad_value})
                config, warnings = main.load_config(self.config_path)
                self.assertEqual(config["interval_ms"], 25)
                self.assertTrue(any("interval_ms" in warning for warning in warnings))

    def test_jitter_invalid_values_fall_back(self):
        for bad_value in (-1, 101, False, 2.5):
            with self.subTest(value=bad_value):
                self.write_raw({"jitter_ms": bad_value})
                config, warnings = main.load_config(self.config_path)
                self.assertEqual(config["jitter_ms"], 5)
                self.assertTrue(any("jitter_ms" in warning for warning in warnings))

    def test_boolean_fields_require_real_booleans(self):
        self.write_raw({"only_in_game": "false", "debug_log": 1})
        config, warnings = main.load_config(self.config_path)
        self.assertTrue(config["only_in_game"])
        self.assertFalse(config["debug_log"])
        self.assertTrue(any("only_in_game" in warning for warning in warnings))
        self.assertTrue(any("debug_log" in warning for warning in warnings))

    def test_invalid_mode_process_and_hotkey_fall_back(self):
        self.write_raw(
            {
                "trigger_mode": "sometimes",
                "game_process": "   ",
                "exit_hotkey": "Ctrl+Alt+NotAKey",
            }
        )
        config, warnings = main.load_config(self.config_path)
        self.assertEqual(config["trigger_mode"], "intercept")
        self.assertEqual(config["game_process"], "ROB RUN.exe")
        self.assertEqual(config["exit_hotkey"], "Ctrl+Alt+F8")
        joined = "\n".join(warnings)
        self.assertIn("trigger_mode", joined)
        self.assertIn("game_process", joined)
        self.assertIn("exit_hotkey", joined)

    def test_corrupt_json_falls_back_without_overwriting(self):
        with open(self.config_path, "w", encoding="utf-8") as handle:
            handle.write("{ this is not json")
        config, warnings = main.load_config(self.config_path)
        self.assertEqual(config, main.DEFAULT_CONFIG)
        self.assertTrue(warnings)
        with open(self.config_path, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "{ this is not json")

    def test_non_object_json_falls_back(self):
        self.write_raw([1, 2, 3])
        config, warnings = main.load_config(self.config_path)
        self.assertEqual(config, main.DEFAULT_CONFIG)
        self.assertTrue(any("obiect JSON" in warning for warning in warnings))

    def test_missing_keys_use_defaults(self):
        self.write_raw({})
        config, warnings = main.load_config(self.config_path)
        self.assertEqual(config, main.DEFAULT_CONFIG)
        self.assertEqual(len(warnings), 7)

    def test_unknown_keys_are_ignored(self):
        raw = dict(main.DEFAULT_CONFIG)
        raw["future_option"] = "ignored"
        self.write_raw(raw)
        config, warnings = main.load_config(self.config_path)
        self.assertEqual(warnings, [])
        self.assertNotIn("future_option", config)

    def test_utf8_bom_config_is_accepted(self):
        raw = dict(main.DEFAULT_CONFIG)
        raw["only_in_game"] = False
        with open(self.config_path, "w", encoding="utf-8-sig") as handle:
            json.dump(raw, handle)
        config, warnings = main.load_config(self.config_path)
        self.assertEqual(warnings, [])
        self.assertFalse(config["only_in_game"])

    def test_parse_hotkey(self):
        modifiers, vk = main.parse_hotkey(" ctrl + ALT + f8 ")
        self.assertEqual(set(modifiers), {"ctrl", "alt"})
        self.assertEqual(vk, 0x77)
        self.assertIsNone(main.parse_hotkey("Ctrl+Alt"))
        self.assertIsNone(main.parse_hotkey("Ctrl+Alt+F25"))
        self.assertIsNone(main.parse_hotkey("Banana"))
        self.assertIsNone(main.parse_hotkey(""))
        shift_q = main.parse_hotkey("Shift+Q")
        self.assertIsNotNone(shift_q)
        self.assertEqual(shift_q[1], ord("Q"))

    def test_interval_boundaries_are_valid(self):
        for value in (5, 500):
            with self.subTest(value=value):
                raw = dict(main.DEFAULT_CONFIG)
                raw["interval_ms"] = value
                self.write_raw(raw)
                config, warnings = main.load_config(self.config_path)
                self.assertEqual(warnings, [])
                self.assertEqual(config["interval_ms"], value)

    def test_jitter_boundaries_are_valid(self):
        for value in (0, 100):
            with self.subTest(value=value):
                raw = dict(main.DEFAULT_CONFIG)
                raw["jitter_ms"] = value
                self.write_raw(raw)
                config, warnings = main.load_config(self.config_path)
                self.assertEqual(warnings, [])
                self.assertEqual(config["jitter_ms"], value)


if __name__ == "__main__":
    unittest.main()
