import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "web_app"
for path in (str(ROOT), str(WEB_APP)):
    if path not in sys.path:
        sys.path.insert(0, path)

from config_web import Config  # noqa: E402
from platform_catalog import PLATFORM_CATALOG, SUPPORTED_PLATFORM_IDS  # noqa: E402


class PlatformCatalogTests(unittest.TestCase):
    def test_desktop_config_and_collectors_match_catalog(self):
        catalog_ids = [item["id"] for item in PLATFORM_CATALOG]
        self.assertEqual(catalog_ids, [item["id"] for item in Config.SUPPORTED_PLATFORMS])
        self.assertEqual(set(catalog_ids), set(SUPPORTED_PLATFORM_IDS))
        for platform_id in catalog_ids:
            self.assertTrue((ROOT / "platforms" / f"{platform_id}.py").is_file(), platform_id)

    def test_cloud_platform_catalog_matches_desktop(self):
        source = (ROOT / "server" / "geo.allgood.cn" / "api" / "platforms.php").read_text(encoding="utf-8")
        catalog_body = source.split("return [", 1)[1].split("];", 1)[0]
        cloud_ids = re.findall(r"^\s*'([a-z0-9_]+)'\s*=>\s*\[", catalog_body, flags=re.MULTILINE)
        self.assertEqual([item["id"] for item in PLATFORM_CATALOG], cloud_ids)


if __name__ == "__main__":
    unittest.main()
