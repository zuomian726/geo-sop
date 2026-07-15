import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "web_app"
os.environ.setdefault("GEO_DESKTOP_MODE", "1")
for path in (str(ROOT), str(WEB_APP)):
    if path not in sys.path:
        sys.path.insert(0, path)

import app as web_app  # noqa: E402


class UpdateCheckTests(unittest.TestCase):
    @staticmethod
    def _response(manifest):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = manifest
        return response

    @staticmethod
    def _manifest():
        return {
            "version": "0.3.19-dev",
            "channel": "desktop-dev",
            "released_at": "2026-07-15T18:15:00+08:00",
            "notes": ["startup fix"],
            "downloads": {
                "macos": {
                    "name": "GEO-SOP-macOS-dev.dmg",
                    "version": "0.3.19-dev",
                    "url": "https://geo.allgood.cn/downloads/GEO-SOP-macOS-dev.dmg",
                    "size": "166 MB",
                },
                "windows": {
                    "name": "GEO-SOP-Setup-dev.exe",
                    "version": "0.3.19-dev",
                    "url": "https://geo.allgood.cn/downloads/GEO-SOP-Setup-dev.exe",
                    "size": "185 MB",
                },
            },
        }

    def test_older_windows_client_receives_native_installer_update(self):
        with (
            patch.object(web_app, "app_info", return_value={"version": "0.3.17-dev"}),
            patch.object(web_app.platform, "system", return_value="Windows"),
            patch.object(web_app.requests, "get", return_value=self._response(self._manifest())),
        ):
            update = web_app._check_latest_update()

        self.assertTrue(update["has_update"])
        self.assertEqual("0.3.19-dev", update["latest_version"])
        self.assertEqual("windows", update["platform"])
        self.assertEqual("GEO-SOP-Setup-dev.exe", update["download_name"])
        self.assertEqual("https://geo.allgood.cn/downloads/GEO-SOP-Setup-dev.exe", update["download_url"])

    def test_current_macos_client_does_not_show_false_update(self):
        with (
            patch.object(web_app, "app_info", return_value={"version": "0.3.19-dev"}),
            patch.object(web_app.platform, "system", return_value="Darwin"),
            patch.object(web_app.requests, "get", return_value=self._response(self._manifest())),
        ):
            update = web_app._check_latest_update()

        self.assertFalse(update["has_update"])
        self.assertEqual("macos", update["platform"])
        self.assertEqual("GEO-SOP-macOS-dev.dmg", update["download_name"])

    def test_update_service_failure_keeps_dashboard_available(self):
        with (
            patch.object(web_app, "app_info", return_value={"version": "0.3.19-dev"}),
            patch.object(web_app.requests, "get", side_effect=TimeoutError("manifest timeout")),
        ):
            update = web_app._check_latest_update()

        self.assertFalse(update["has_update"])
        self.assertEqual("0.3.19-dev", update["current_version"])
        self.assertIn("manifest timeout", update["error"])


if __name__ == "__main__":
    unittest.main()
