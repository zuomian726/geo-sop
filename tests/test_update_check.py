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
            "minimum_supported_version": "0.3.0-dev",
            "force": False,
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
                    "sha256": "abc123",
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
        self.assertFalse(update["required"])
        self.assertEqual("abc123", update["download_sha256"])

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

    def test_client_below_minimum_supported_version_requires_update(self):
        manifest = self._manifest()
        manifest["minimum_supported_version"] = "0.3.18-dev"
        with (
            patch.object(web_app, "app_info", return_value={"version": "0.3.17-dev"}),
            patch.object(web_app.platform, "system", return_value="Windows"),
            patch.object(web_app.requests, "get", return_value=self._response(manifest)),
        ):
            update = web_app._check_latest_update()

        self.assertTrue(update["has_update"])
        self.assertTrue(update["below_minimum"])
        self.assertTrue(update["required"])

    def test_force_flag_only_applies_when_an_update_exists(self):
        manifest = self._manifest()
        manifest["force"] = True
        with (
            patch.object(web_app, "app_info", return_value={"version": "0.3.19-dev"}),
            patch.object(web_app.platform, "system", return_value="Windows"),
            patch.object(web_app.requests, "get", return_value=self._response(manifest)),
        ):
            update = web_app._check_latest_update()

        self.assertFalse(update["has_update"])
        self.assertFalse(update["required"])

    def test_stable_release_is_newer_than_dev_release(self):
        self.assertGreater(web_app._version_key("0.4.0"), web_app._version_key("0.4.0-dev"))
        self.assertGreater(web_app._version_key("0.4.0-rc1"), web_app._version_key("0.4.0-beta2"))
        self.assertGreater(web_app._version_key("0.4.0-beta2"), web_app._version_key("0.4.0-beta1"))

    def test_update_download_opens_official_https_url(self):
        update = {
            "has_update": True,
            "update_url": "https://geo.allgood.cn/update.json",
            "download_url": "https://geo.allgood.cn/downloads/GEO-SOP-Setup-dev.exe",
        }
        with patch.object(web_app.webbrowser, "open", return_value=True) as open_browser:
            url = web_app._open_update_download(update)

        self.assertEqual(update["download_url"], url)
        open_browser.assert_called_once_with(update["download_url"], new=2)

    def test_update_download_rejects_cross_domain_package(self):
        update = {
            "has_update": True,
            "update_url": "https://geo.allgood.cn/update.json",
            "download_url": "https://example.com/fake.exe",
        }
        with self.assertRaisesRegex(ValueError, "官方更新服务器"):
            web_app._open_update_download(update)


if __name__ == "__main__":
    unittest.main()
