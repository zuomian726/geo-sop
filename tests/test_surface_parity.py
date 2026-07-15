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

    def test_desktop_cloud_status_is_live_and_does_not_block_first_paint(self):
        app = (ROOT / "web_app" / "app.py").read_text(encoding="utf-8")
        worker = (ROOT / "web_app" / "remote_worker.py").read_text(encoding="utf-8")
        dashboard = (ROOT / "web_app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("include_remote=False", app)
        self.assertIn("def worker_health(", worker)
        self.assertIn("last_success_at", worker)
        self.assertIn("loadCloudSyncStatus", dashboard)
        self.assertIn("cloudStatusTimer", dashboard)
        self.assertIn("geo-sop-wordmark.png", dashboard)

    def test_desktop_minimum_window_uses_compact_toolbar_and_single_dashboard_load(self):
        dashboard = (ROOT / "web_app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        mounted = dashboard.split("async mounted() {", 1)[1].split("beforeUnmount() {", 1)[0]
        self.assertNotIn("this.loadInsightsOverview()", mounted)
        self.assertNotIn("this.loadInsightScorecard()", mounted)
        self.assertIn("header-actions", dashboard)
        self.assertIn("header-action-label secondary", dashboard)
        self.assertIn("<switch-button />", dashboard)
        self.assertIn("platform-login-dialog", dashboard)
        self.assertNotIn('prop="url" label="登录地址"', dashboard)
        self.assertIn("首次登录只需三步", dashboard)

    def test_public_site_keeps_stable_desktop_download_links(self):
        for relative_path in ("index.html", "tools/index.html"):
            source = (ROOT / "server" / "geo.allgood.cn" / relative_path).read_text(encoding="utf-8")
            self.assertIn("/downloads/GEO-SOP-Setup-dev.exe", source)
            self.assertIn("/downloads/GEO-SOP-macOS-dev.dmg", source)

    def test_demo_seed_is_account_safe_and_matches_public_sample_counts(self):
        seed = (ROOT / "server" / "geo.allgood.cn" / "demo" / "seed.php").read_text(encoding="utf-8")
        self.assertIn("PHP_SAPI !== 'cli'", seed)
        self.assertIn("WHERE username=?", seed)
        self.assertNotIn("str_starts_with", seed)
        self.assertNotIn("cloud_user_id=16", seed)
        self.assertIn("DEMO_EXPECTED_TASKS = 6", seed)
        self.assertIn("DEMO_EXPECTED_RESULTS = 144", seed)
        self.assertIn("DEMO_EXPECTED_MANUSCRIPTS = 4", seed)
        self.assertIn("demo_json($domains)", seed)
        self.assertIn("$pdo->rollBack()", seed)

        landing = (ROOT / "server" / "geo.allgood.cn" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<article><strong>6</strong><span data-en="Demo tasks"', landing)
        self.assertIn('<article><strong>144</strong><span data-en="Synthetic answers"', landing)
        self.assertIn('<article><strong>4</strong><span data-en="GEO files"', landing)

    def test_cloud_header_has_a_compact_desktop_breakpoint(self):
        dashboard = (ROOT / "server" / "geo.allgood.cn" / "dashboard" / "index.php").read_text(encoding="utf-8")
        self.assertIn("@media(max-width:1200px)", dashboard)
        self.assertIn("current-account", dashboard)
        self.assertIn("header-full-label", dashboard)
        self.assertIn("header-compact-label", dashboard)
        self.assertIn("white-space:nowrap", dashboard)
        self.assertIn(".side-stack{grid-template-columns:repeat(2,minmax(0,1fr))}", dashboard)

    def test_cloud_default_date_filters_use_browser_local_date(self):
        dashboard = (ROOT / "server" / "geo.allgood.cn" / "dashboard" / "index.php").read_text(encoding="utf-8")
        self.assertIn("function localDateValue(date)", dashboard)
        self.assertIn("date.getFullYear()", dashboard)
        self.assertIn("date.getMonth() + 1", dashboard)
        self.assertIn("date.getDate()", dashboard)
        self.assertIn("return localDateValue(date);", dashboard)
        self.assertNotIn("return date.toISOString().slice(0, 10);", dashboard)


if __name__ == "__main__":
    unittest.main()
