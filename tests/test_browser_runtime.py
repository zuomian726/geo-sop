import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "web_app"
for path in (str(ROOT), str(WEB_APP)):
    if path not in sys.path:
        sys.path.insert(0, path)

import browser_utils  # noqa: E402
import browser_config  # noqa: E402


class BrowserRuntimeTests(unittest.TestCase):
    def test_browser_config_is_saved_in_user_data_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            user_data = root / "user-data"
            legacy_path = root / "installed-app" / "browser_config.json"

            with (
                patch.object(browser_config, "app_data_dir", return_value=str(user_data)),
                patch.object(browser_config, "LEGACY_CONFIG_FILE", legacy_path),
            ):
                browser_config.save_browser_config("  C:\\Browser\\chrome.exe  ")
                saved = browser_config.load_browser_config()

            self.assertEqual("C:\\Browser\\chrome.exe", saved["browser_path"])
            self.assertTrue((user_data / "browser_config.json").is_file())
            self.assertFalse(legacy_path.exists())

    def test_legacy_browser_config_is_migrated_without_modifying_installation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            user_data = root / "user-data"
            legacy_path = root / "installed-app" / "browser_config.json"
            legacy_path.parent.mkdir(parents=True)
            legacy_contents = '{"browser_path":"D:\\\\Chrome\\\\chrome.exe","candidates":[]}'
            legacy_path.write_text(legacy_contents, encoding="utf-8")

            with (
                patch.object(browser_config, "app_data_dir", return_value=str(user_data)),
                patch.object(browser_config, "LEGACY_CONFIG_FILE", legacy_path),
            ):
                loaded = browser_config.load_browser_config()

            self.assertEqual("D:\\Chrome\\chrome.exe", loaded["browser_path"])
            self.assertEqual(legacy_contents, legacy_path.read_text(encoding="utf-8"))
            migrated = json.loads((user_data / "browser_config.json").read_text(encoding="utf-8"))
            self.assertEqual(loaded, migrated)

    def test_invalid_user_config_falls_back_to_legacy_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            user_data = root / "user-data"
            user_data.mkdir()
            (user_data / "browser_config.json").write_text("not-json", encoding="utf-8")
            legacy_path = root / "legacy-browser-config.json"
            legacy_path.write_text('{"browser_path":"/Applications/Chrome","candidates":[]}', encoding="utf-8")

            with (
                patch.object(browser_config, "app_data_dir", return_value=str(user_data)),
                patch.object(browser_config, "LEGACY_CONFIG_FILE", legacy_path),
            ):
                loaded = browser_config.load_browser_config()

            self.assertEqual("/Applications/Chrome", loaded["browser_path"])

    def test_system_browser_keeps_priority_over_bundled_chromium(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            system_browser = root / "Google Chrome"
            system_browser.write_bytes(b"system")
            bundled = root / "browsers" / "chromium-1223" / "chrome-win64" / "chrome.exe"
            bundled.parent.mkdir(parents=True)
            bundled.write_bytes(b"bundled")

            with (
                patch.object(browser_utils, "get_browser_candidates", return_value=[str(system_browser)]),
                patch.dict(os.environ, {"PLAYWRIGHT_BROWSERS_PATH": str(root / "browsers")}),
            ):
                browser_type, executable = browser_utils.find_browser()

        self.assertEqual("chrome", browser_type)
        self.assertEqual(str(system_browser), executable)

    def test_bundled_chromium_is_used_when_system_browser_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "browsers"
            bundled = root / "chromium-1223" / "chrome-win64" / "chrome.exe"
            bundled.parent.mkdir(parents=True)
            bundled.write_bytes(b"bundled")

            with (
                patch.object(browser_utils, "get_browser_candidates", return_value=[]),
                patch.dict(os.environ, {"PLAYWRIGHT_BROWSERS_PATH": str(root)}),
            ):
                browser_type, executable = browser_utils.find_browser()

        self.assertEqual("chrome", browser_type)
        self.assertEqual(str(bundled), executable)

    def test_supported_collectors_use_shared_browser_resolution(self):
        collector_source = (WEB_APP / "collector.py").read_text(encoding="utf-8")
        self.assertNotIn("platform_id == 'yiyan'", collector_source)
        self.assertIn("USE_CUSTOM_BROWSER", collector_source)

    def test_pinned_playwright_uses_compatible_windows_install_command(self):
        requirements = (ROOT / "requirements-desktop.txt").read_text(encoding="utf-8")
        build_script = (ROOT / "build_windows_exe.bat").read_text(encoding="utf-8")
        self.assertIn("playwright==1.44.0", requirements)
        self.assertIn("python -m playwright install chromium", build_script)
        self.assertNotIn("--no-shell", build_script)


if __name__ == "__main__":
    unittest.main()
