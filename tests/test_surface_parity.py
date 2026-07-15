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
            "reference_analysis",
            "reference_domains",
            "reference_trends",
            "geo_coverage",
            "export_geo",
            "export_screenshots_zip",
            "remote_status",
        }
        self.assertTrue(expected <= actions, expected - actions)

    def test_cloud_reference_analysis_has_lazy_ui_and_api_renderers(self):
        source = (ROOT / "server" / "geo.allgood.cn" / "dashboard" / "index.php").read_text(encoding="utf-8")
        expected_markers = {
            'id="reference-analysis"',
            'id="referenceRanking"',
            'id="referenceTrend"',
            "function loadReferenceAnalysis()",
            "function renderReferenceRanking(data)",
            "function renderReferenceTrend(data)",
            "IntersectionObserver",
        }
        missing = {marker for marker in expected_markers if marker not in source}
        self.assertFalse(missing, missing)

    def test_cloud_connection_status_exposes_worker_progress(self):
        dashboard = (ROOT / "server" / "geo.allgood.cn" / "dashboard" / "index.php").read_text(encoding="utf-8")
        api = (ROOT / "server" / "geo.allgood.cn" / "api" / "dashboard" / "index.php").read_text(encoding="utf-8")
        for marker in ("workerStateLabel", "后台任务", "sync_backlog", "pending_remote_tasks"):
            self.assertIn(marker, dashboard)
        for marker in ("worker_state", "running_tasks", "local_pending_tasks", "sync_backlog"):
            self.assertIn(marker, api)

    def test_cloud_sync_is_non_destructive_unless_explicitly_requested(self):
        client = (ROOT / "web_app" / "cloud_sync.py").read_text(encoding="utf-8")
        server = (ROOT / "server" / "geo.allgood.cn" / "api" / "sync" / "index.php").read_text(encoding="utf-8")
        self.assertIn('"sync_mode": "merge"', client)
        self.assertIn('"prune_install": False', client)
        self.assertIn("$pruneInstall = !empty($data['prune_install']);", server)
        self.assertIn("if ($pruneInstall) {", server)

    def test_public_site_keeps_stable_desktop_download_links(self):
        for relative_path in ("index.html", "tools/index.html"):
            source = (ROOT / "server" / "geo.allgood.cn" / relative_path).read_text(encoding="utf-8")
            self.assertIn("/downloads/GEO-SOP-Setup-dev.exe", source)
            self.assertIn("/downloads/GEO-SOP-macOS-dev.dmg", source)


if __name__ == "__main__":
    unittest.main()
