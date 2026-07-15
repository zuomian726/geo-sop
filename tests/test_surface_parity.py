import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SurfaceParityTests(unittest.TestCase):
    def test_cloud_dashboard_keeps_desktop_core_modules(self):
        desktop = (ROOT / "web_app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        cloud = (ROOT / "server" / "geo.allgood.cn" / "dashboard" / "index.php").read_text(encoding="utf-8")

        desktop_labels = set(re.findall(r'<el-tab-pane\s+name="[^"]+"\s+label="([^"]+)"', desktop))
        cloud_labels = set(re.findall(r'<a[^>]+href="#[^"]+"[^>]*>([^<]+)</a>', cloud))
        expected = {
            "数据看板",
            "任务管理",
            "引用参考源分析",
            "引用参考源走势图",
            "GEO稿件被引用分析",
            "智慧舆情设置",
        }

        self.assertTrue(expected <= desktop_labels, expected - desktop_labels)
        self.assertTrue(expected <= cloud_labels, expected - cloud_labels)

    def test_cloud_api_keeps_query_export_and_remote_status_contract(self):
        source = (ROOT / "server" / "geo.allgood.cn" / "api" / "dashboard" / "index.php").read_text(encoding="utf-8")
        actions = set(re.findall(r"\$action === '([a-z_]+)'", source))
        expected = {
            "overview",
            "tasks",
            "results",
            "result",
            "references",
            "geo_coverage",
            "export_geo",
            "export_screenshots_zip",
            "remote_status",
        }
        self.assertTrue(expected <= actions, expected - actions)

    def test_public_site_keeps_stable_desktop_download_links(self):
        for relative_path in ("index.html", "tools/index.html"):
            source = (ROOT / "server" / "geo.allgood.cn" / relative_path).read_text(encoding="utf-8")
            self.assertIn("/downloads/GEO-SOP-Setup-dev.exe", source)
            self.assertIn("/downloads/GEO-SOP-macOS-dev.dmg", source)


if __name__ == "__main__":
    unittest.main()
