"""Settings persistence and validation tests."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from pcb_analyzer.settings import DEFAULTS, load_settings, save_settings  # noqa: E402


class TestSettings(unittest.TestCase):
    def test_atomic_save_and_reload(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "config", "settings.json")
            values = dict(DEFAULTS, application_name="BenchLab", ollama_model="qwen2.5")
            save_settings(values, path)
            self.assertEqual(load_settings(path)["application_name"], "BenchLab")
            self.assertEqual(load_settings(path)["ollama_model"], "qwen2.5")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_corrupt_file_uses_safe_defaults_and_unknown_fields_are_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "settings.json")
            with open(path, "w", encoding="utf-8") as stream:
                json.dump({"application_name": "Desk", "api_key": "secret"}, stream)
            loaded = load_settings(path)
            self.assertEqual(loaded["application_name"], "Desk")
            self.assertNotIn("api_key", loaded)
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("broken")
            self.assertEqual(load_settings(path), DEFAULTS)

    def test_rejects_unknown_theme(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                save_settings(dict(DEFAULTS, theme="solarized"), os.path.join(root, "s.json"))


if __name__ == "__main__":
    unittest.main()
