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


class BrowserRuntimeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
