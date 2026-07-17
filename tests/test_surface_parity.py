import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SurfaceParityTests(unittest.TestCase):
    def test_v1_release_metadata_is_canonical_and_stable(self):
        version = (ROOT / "version.py").read_text(encoding="utf-8")
        notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
        self.assertIn('APP_VERSION = "1.0.0"', version)
        self.assertIn('APP_CHANNEL = "stable"', version)
        self.assertIn("## v1.0.0 - 2026-07-17", notes)
        for relative_path in ("index.html", "tools/index.html"):
            source = (ROOT / "server" / "geo.allgood.cn" / relative_path).read_text(encoding="utf-8")
            self.assertIn('id="release-badge">v1.0.0</span>', source)
            self.assertIn('"softwareVersion": "v1.0.0"', source)
            self.assertNotIn("v0.3.43-dev", source)

    def test_installer_build_is_manual_while_pushes_only_run_tests(self):
        installer_workflow = (ROOT / ".github" / "workflows" / "build-windows-installer.yml").read_text(
            encoding="utf-8"
        )
        test_workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", installer_workflow)
        self.assertNotIn("  push:", installer_workflow)
        self.assertIn("  push:", test_workflow)
        self.assertIn("python -m unittest discover -s tests -v", test_workflow)

    def test_desktop_packages_use_runtime_asset_allowlists(self):
        windows = (ROOT / "build_windows_exe.bat").read_text(encoding="utf-8")
        macos = (ROOT / "build_macos_app.sh").read_text(encoding="utf-8")
        spec = (ROOT / "GEO-SOP.spec").read_text(encoding="utf-8")

        for source in (windows, macos, spec):
            self.assertNotIn("reference_sentiment", source)
            self.assertNotIn("'tools'", source)
        self.assertNotIn('--add-data "web_app;web_app"', windows)
        self.assertNotIn('--add-data "web_app:web_app"', macos)
        self.assertIn('web_app\\templates;web_app\\templates', windows)
        self.assertIn('web_app/templates:web_app/templates', macos)

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
        for marker in (
            'id="resultDetailModal"',
            "openResultDetail(this.dataset.installId,this.dataset.localId)",
            "完整回答",
            "品牌命中",
            "引用来源（",
            "查看截图留证",
        ):
            self.assertIn(marker, cloud)

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
        self.assertIn("客户端离线且版本过旧", source)
        self.assertIn("online_outdated_clients", source)
        self.assertIn("if ($outdated) $outdatedClients++", source)

    def test_geo_coverage_filters_and_deep_link_match_across_surfaces(self):
        app = (ROOT / "web_app" / "app.py").read_text(encoding="utf-8")
        desktop = (ROOT / "web_app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        cloud = (ROOT / "server" / "geo.allgood.cn" / "api" / "dashboard" / "index.php").read_text(encoding="utf-8")
        self.assertIn("def _geo_manuscript_task_ids(", app)
        self.assertIn("def _apply_geo_date_range(", app)
        self.assertGreaterEqual(app.count("_apply_geo_date_range(query, start_date, end_date)"), 2)
        self.assertIn("geoFilter.start_date", desktop)
        self.assertIn("geoFilter.end_date", desktop)
        self.assertIn('placeholder="全部平台" clearable', desktop)
        self.assertIn("'geo': 'geo_analysis'", desktop)
        self.assertIn("'geo-coverage': 'geo_analysis'", desktop)
        self.assertIn("window.addEventListener('hashchange', this.hashChangeHandler)", desktop)
        self.assertIn("window.removeEventListener('hashchange', this.hashChangeHandler)", desktop)
        self.assertIn("article-id:", cloud)
        cloud_dashboard = (ROOT / "server" / "geo.allgood.cn" / "dashboard" / "index.php").read_text(encoding="utf-8")
        self.assertIn("geoStart.value = referenceDateValue(30)", cloud_dashboard)
        self.assertIn("geoEnd.value = referenceDateValue(0)", cloud_dashboard)
        smoke = (ROOT / "tools" / "smoke_desktop_ui.py").read_text(encoding="utf-8")
        self.assertIn('page.goto(url + "#geo"', smoke)
        self.assertIn('has_text="GEO稿件被引用分析"', smoke)
        self.assertIn('get_by_role("combobox", name="开始日期"', smoke)
        self.assertIn('get_by_role("combobox", name="结束日期"', smoke)

    def test_cloud_reference_analysis_has_lazy_ui_and_api_renderers(self):
        source = (ROOT / "server" / "geo.allgood.cn" / "dashboard" / "index.php").read_text(encoding="utf-8")
        expected_markers = {
            'id="reference-analysis"',
            'href="#reference-ranking"',
            'href="#reference-trends"',
            'id="reference-ranking"',
            'id="reference-trends"',
            'id="referenceRanking"',
            'id="referenceTrend"',
            "function loadReferenceAnalysis()",
            "function renderReferenceRanking(data)",
            "function renderReferenceTrend(data)",
            "IntersectionObserver",
            "function openDashboardTarget(id, updateHistory)",
            "target.closest('[data-collapsible]')",
            "target.scrollIntoView({block: 'start', behavior: 'smooth'})",
            "function setActiveDashboardNav(id)",
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

    def test_cloud_app_launch_feedback_is_non_blocking_and_actionable(self):
        dashboard = (ROOT / "server" / "geo.allgood.cn" / "dashboard" / "index.php").read_text(encoding="utf-8")
        for marker in (
            'id="appLaunchNotice"',
            "visibilitychange",
            "window.addEventListener('blur', onBlur",
            "geo-sop://open?target=",
            "没有检测到桌面应用",
            "retryLocalApp",
            "/#download",
        ):
            self.assertIn(marker, dashboard)
        self.assertNotIn("alert('如果本机 App 没有自动打开", dashboard)

    def test_desktop_protocol_targets_open_the_requested_workflow(self):
        launcher = (ROOT / "desktop_app.py").read_text(encoding="utf-8")
        dashboard = (ROOT / "web_app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        mac_build = (ROOT / "build_macos_app.sh").read_text(encoding="utf-8")
        windows_installer = (ROOT / "installer" / "windows" / "GEO-SOP.iss").read_text(encoding="utf-8")
        self.assertIn('/dashboard?open=platform-login', launcher)
        self.assertIn('/dashboard?open=ai-settings#sentiment_settings', launcher)
        self.assertIn('/dashboard?open=collection-settings', launcher)
        self.assertIn('/dashboard?open=browser-settings', launcher)
        self.assertIn("applyStartupAction()", dashboard)
        self.assertIn("action === 'platform-login'", dashboard)
        self.assertIn("action === 'collection-settings'", dashboard)
        self.assertIn("action === 'browser-settings'", dashboard)
        self.assertIn("this.showLimitSettings()", dashboard)
        self.assertIn("this.showBrowserSettings()", dashboard)
        smoke = (ROOT / "tools" / "smoke_desktop_ui.py").read_text(encoding="utf-8")
        self.assertIn('?open=collection-settings', smoke)
        self.assertIn('?open=browser-settings', smoke)
        self.assertIn('"CFBundleURLSchemes": ["geo-sop"]', mac_build)
        self.assertIn('Software\\Classes\\geo-sop', windows_installer)

    def test_cloud_sync_is_non_destructive_unless_explicitly_requested(self):
        client = (ROOT / "web_app" / "cloud_sync.py").read_text(encoding="utf-8")
        server = (ROOT / "server" / "geo.allgood.cn" / "api" / "sync" / "index.php").read_text(encoding="utf-8")
        self.assertIn('"sync_mode": "merge"', client)
        self.assertIn('"prune_install": False', client)
        self.assertIn("$pruneInstall = !empty($data['prune_install']);", server)
        self.assertIn("if ($pruneInstall) {", server)
        self.assertIn("cloud_user_is_demo($pdo, $cloudUserId)", server)
        self.assertNotIn("$cloudUserId === 16", server)

    def test_desktop_cloud_status_is_live_and_does_not_block_first_paint(self):
        app = (ROOT / "web_app" / "app.py").read_text(encoding="utf-8")
        worker = (ROOT / "web_app" / "remote_worker.py").read_text(encoding="utf-8")
        dashboard = (ROOT / "web_app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("include_remote=False", app)
        self.assertIn("def worker_health(", worker)
        self.assertIn("last_success_at", worker)
        self.assertIn("loadCloudSyncStatus", dashboard)
        self.assertIn("cloudStatusTimer", dashboard)
        self.assertIn("reconnectCloudSync", dashboard)
        self.assertIn("/api/cloud-sync/reconnect", app)
        self.assertIn("def wake_remote_task_worker(", worker)
        self.assertIn("error: response.data.cloud_sync?.error || ''", dashboard)
        self.assertIn("geo-sop-wordmark.png", dashboard)

    def test_empty_desktop_dashboard_prioritizes_first_run_actions(self):
        dashboard = (ROOT / "web_app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('v-if="!hasCollectedResults"', dashboard)
        self.assertIn("建立第一组可对比的 GEO 基线", dashboard)
        self.assertIn("hasCollectedResults()", dashboard)
        self.assertIn("disposeInsightCharts()", dashboard)

    def test_v1_task_dialog_only_exposes_manual_collection(self):
        dashboard = (ROOT / "web_app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        app_source = (ROOT / "web_app" / "app.py").read_text(encoding="utf-8")
        self.assertNotIn('<el-radio label="daily">', dashboard)
        self.assertNotIn('<el-radio label="weekly">', dashboard)
        self.assertIn("schedule_type: 'manual'", dashboard)
        self.assertIn("def _normalize_manual_task_payload", app_source)
        self.assertIn("'schedule_type': 'manual'", app_source)

    def test_desktop_login_uses_shared_cloud_account_and_password_manager_fields(self):
        app_source = (ROOT / "web_app" / "app.py").read_text(encoding="utf-8")
        login = (ROOT / "web_app" / "templates" / "login.html").read_text(encoding="utf-8")
        self.assertIn("requires_cloud_account", app_source)
        self.assertIn("cloud_login = requires_cloud_account or", app_source)
        self.assertIn('autocomplete="username"', login)
        self.assertIn('autocomplete="current-password"', login)
        self.assertIn("geo-sop-last-account", login)
        self.assertNotIn("云端账号登录失败: {str(e)}", app_source)

    def test_desktop_minimum_window_uses_compact_toolbar_and_single_dashboard_load(self):
        dashboard = (ROOT / "web_app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        base = (ROOT / "web_app" / "templates" / "base.html").read_text(encoding="utf-8")
        mounted = dashboard.split("async mounted() {", 1)[1].split("beforeUnmount() {", 1)[0]
        self.assertNotIn("this.loadInsightsOverview()", mounted)
        self.assertNotIn("this.loadInsightScorecard()", mounted)
        self.assertNotIn("this.loadAnalysisData()", mounted)
        self.assertNotIn("this.loadTrendDomains()", mounted)
        self.assertNotIn("this.loadTrendData()", mounted)
        self.assertNotIn("this.loadGeoCoverageData()", mounted)
        self.assertIn("this.handleTabClick({ name: this.activeTab })", mounted)
        self.assertIn("analysisLoaded", dashboard)
        self.assertIn("trendLoaded", dashboard)
        self.assertIn("geoCoverageLoaded", dashboard)
        self.assertIn("tab?.props?.name", dashboard)
        self.assertIn("header-actions", dashboard)
        self.assertIn("header-action-label secondary", dashboard)
        self.assertIn("<switch-button />", dashboard)
        self.assertIn("platform-login-dialog", dashboard)
        self.assertIn("ElMessageBox, ElNotification", base)
        self.assertNotIn('prop="url" label="登录地址"', dashboard)
        self.assertIn("首次登录只需三步", dashboard)

    def test_long_desktop_forms_scroll_inside_the_minimum_window(self):
        dashboard = (ROOT / "web_app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        self.assertGreaterEqual(dashboard.count('class="scrollable-form-dialog"'), 2)
        self.assertIn("max-height: calc(100vh - 32px)", dashboard)
        self.assertIn(".scrollable-form-dialog .el-dialog__body", dashboard)
        self.assertIn("overflow-y: auto", dashboard)

    def test_desktop_cli_does_not_ship_a_default_admin_password(self):
        app_source = (ROOT / "web_app" / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("def create_admin", app_source)
        self.assertNotIn("set_password('admin')", app_source)
        self.assertIn("@app.cli.command('create-user')", app_source)
        self.assertIn("hide_input=True, confirmation_prompt=True", app_source)

    def test_public_site_keeps_stable_desktop_download_links(self):
        styles = (ROOT / "server" / "geo.allgood.cn" / "public" / "assets" / "styles.css").read_text(encoding="utf-8")
        for relative_path in ("index.html", "tools/index.html"):
            source = (ROOT / "server" / "geo.allgood.cn" / relative_path).read_text(encoding="utf-8")
            self.assertIn("/downloads/GEO-SOP-Setup.exe", source)
            self.assertIn("/downloads/GEO-SOP-macOS.dmg", source)
            self.assertIn("/downloads/GEO-SOP-macOS-Intel.dmg", source)
            self.assertNotIn('href="/downloads/GEO-SOP-Setup-dev.exe"', source)
            self.assertIn("if (release.channel === 'stable')", source)
            self.assertIn('id="release-security-title"', source)
            self.assertIn('id="release-security-copy"', source)
            self.assertIn('id="release-windows-signing"', source)
            self.assertIn("Authenticode-signed installer with bundled runtime", source)
            self.assertIn("gatekeeper.hidden = true", source)
            self.assertIn('<h4>v1.0</h4>', source)
            self.assertNotIn('Try the v0.3 workspace', source)
        roadmap_styles = styles[styles.index(".tool-roadmap-grid {"):styles.index(".tool-roadmap-grid article {")]
        detail_styles = styles[styles.index(".tool-roadmap-detail-grid {"):styles.index(".tool-roadmap-detail-grid article {")]
        self.assertIn("repeat(2, minmax(0, 1fr))", roadmap_styles)
        self.assertIn("repeat(2, minmax(0, 1fr))", detail_styles)

    def test_macos_release_builds_are_architecture_specific(self):
        build_script = (ROOT / "build_macos_app.sh").read_text(encoding="utf-8")
        smoke_script = (ROOT / "tools" / "smoke_macos_dmg.sh").read_text(encoding="utf-8")
        self.assertIn('GEO_MACOS_ARCH', build_script)
        self.assertIn('macOS-Apple-Silicon', build_script)
        self.assertIn('macOS-Intel', build_script)
        self.assertIn('lipo -archs', build_script)
        self.assertIn('verify_macos_bundle.py', build_script)
        self.assertIn('cn.allgood.geosop', build_script)
        self.assertIn('APPLE_DEVELOPER_ID', build_script)
        self.assertIn('APPLE_NOTARY_PROFILE', build_script)
        self.assertIn('notarytool submit', build_script)
        self.assertIn('GEO_REQUIRE_LOGIN=1', smoke_script)
        self.assertIn('GEO_REQUIRE_LOGIN=0', smoke_script)
        self.assertIn('登录 GEO-SOP', smoke_script)
        self.assertNotIn('$base_url/register', smoke_script)

        manifest = json.loads((ROOT / "server" / "geo.allgood.cn" / "update.json").read_text(encoding="utf-8"))
        self.assertIn("macos", manifest["downloads"])
        self.assertIn("macos_intel", manifest["downloads"])

    def test_windows_release_installs_native_runtime_and_supports_chinese(self):
        workflow = (ROOT / ".github" / "workflows" / "build-windows-installer.yml").read_text(encoding="utf-8")
        installer = (ROOT / "installer" / "windows" / "GEO-SOP.iss").read_text(encoding="utf-8")
        exe_build = (ROOT / "build_windows_exe.bat").read_text(encoding="utf-8")
        installer_build = (ROOT / "build_windows_installer.bat").read_text(encoding="utf-8")
        self.assertIn("Smoke test installer install and uninstall", workflow)
        self.assertIn("GEO_REQUIRE_LOGIN = \"1\"", workflow)
        self.assertIn("GEO_REQUIRE_LOGIN = \"0\"", workflow)
        self.assertIn("A clean Windows installation did not require", workflow)
        self.assertIn("Installed application did not require the shared cloud account login", workflow)
        self.assertIn("Installed executable lost its Authenticode signature", workflow)
        self.assertIn("Uninstaller left the geo-sop protocol registration behind", workflow)
        self.assertIn("geo-sop\\shell\\open\\command", workflow)
        self.assertIn("ms-playwright", workflow)
        self.assertIn("does not match version.py", workflow)
        self.assertIn("from version import APP_VERSION", exe_build)
        self.assertIn("from version import APP_VERSION", installer_build)
        self.assertIn("#error MyAppVersion must be provided", installer)
        self.assertNotIn("0.3.44-dev", exe_build + installer_build + installer)

    def test_stable_release_is_signed_and_manifest_is_published_last(self):
        workflow = (ROOT / ".github" / "workflows" / "build-windows-installer.yml").read_text(encoding="utf-8")
        installer = (ROOT / "installer" / "windows" / "GEO-SOP.iss").read_text(encoding="utf-8")
        publisher = (ROOT / "tools" / "publish_stable_release.py").read_text(encoding="utf-8")
        self.assertIn("Get-AuthenticodeSignature", workflow)
        self.assertIn("GEO-SOP-Windows-signature.json", workflow)
        self.assertIn("def verify_macos(", publisher)
        self.assertIn('"xcrun", "stapler", "validate"', publisher)
        self.assertIn('ROOT / "tools" / "smoke_macos_dmg.sh"', publisher)
        self.assertIn('verify_macos(inputs["macos"], "arm64", version)', publisher)
        self.assertIn('verify_macos(inputs["macos_intel"], "x86_64", version)', publisher)
        self.assertIn("def verify_windows_evidence(", publisher)
        self.assertIn("Refusing to publish from a dirty Git worktree", publisher)
        alias_move = publisher.index("/downloads/." + "' + alias + '" + ".new")
        manifest_move = publisher.index("/.update.json.new")
        self.assertLess(alias_move, manifest_move)
        self.assertIn("update.json was switched last", publisher)
        self.assertIn("WINDOWS_SIGNING_CERT_BASE64", workflow)
        self.assertIn("signtool sign", workflow)
        self.assertIn("signtool verify", workflow)
        self.assertIn("ChineseSimplified.isl", installer)
        self.assertIn("PrivilegesRequired=lowest", installer)
        installer_build = (ROOT / "build_windows_installer.bat").read_text(encoding="utf-8")
        self.assertIn('GEO_RELEASE_CHANNEL%"=="stable', installer_build)
        self.assertIn('WINDOWS_SIGNING_READY', installer_build)
        mac_build = (ROOT / "build_macos_app.sh").read_text(encoding="utf-8")
        self.assertIn('if [ "${RELEASE_CHANNEL}" = "stable" ]; then', mac_build)
        self.assertIn("此正式版已使用 Apple Developer ID 签名并通过 Apple 公证", mac_build)
        self.assertIn("请只从 https://geo.allgood.cn 下载正式安装包", mac_build)

    def test_desktop_periodically_checks_for_updates_without_duplicate_notices(self):
        dashboard = (ROOT / "web_app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("updateCheckTimer: null", dashboard)
        self.assertIn("notifiedUpdateVersion: ''", dashboard)
        self.assertIn("setInterval(() => this.checkForUpdates(), 30 * 60 * 1000)", dashboard)
        self.assertIn("async checkForUpdates()", dashboard)
        self.assertIn("this.notifiedUpdateVersion === version", dashboard)
        self.assertIn("clearInterval(this.updateCheckTimer)", dashboard)
        updater = (ROOT / "web_app" / "app.py").read_text(encoding="utf-8")
        self.assertIn("def _verify_stable_update_signature", updater)
        self.assertIn("Get-AuthenticodeSignature", updater)
        self.assertIn("['xcrun', 'stapler', 'validate', path]", updater)

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
        self.assertIn("demo_json($references)", seed)
        self.assertIn("reference_items", seed)
        self.assertIn("$pdo->rollBack()", seed)
        self.assertIn("define('GEO_SYNC_SCHEMA_ONLY', true)", seed)
        self.assertIn("geo_sync_ensure_schema($pdo)", seed)
        self.assertIn("define('GEO_ASSETS_SCHEMA_ONLY', true)", seed)
        self.assertIn("geo_assets_ensure_schema($pdo)", seed)
        self.assertIn("define('GEO_REMOTE_SCHEMA_ONLY', true)", seed)
        self.assertIn("geo_remote_ensure_schema($pdo)", seed)

        sync = (ROOT / "server" / "geo.allgood.cn" / "api" / "sync" / "index.php").read_text(encoding="utf-8")
        self.assertIn("function geo_sync_ensure_schema(PDO $pdo)", sync)
        self.assertIn("if ($geoSyncSchemaOnly) {", sync)
        self.assertNotIn("function ensure_schema(PDO $pdo)", sync)
        assets = (ROOT / "server" / "geo.allgood.cn" / "api" / "sync" / "assets" / "index.php").read_text(encoding="utf-8")
        self.assertIn("GEO_ASSETS_SCHEMA_ONLY", assets)
        self.assertIn("if ($geoAssetsSchemaOnly) {", assets)
        remote = (ROOT / "server" / "geo.allgood.cn" / "api" / "remote-tasks" / "index.php").read_text(encoding="utf-8")
        self.assertIn("GEO_REMOTE_SCHEMA_ONLY", remote)
        self.assertIn("if ($geoRemoteSchemaOnly) {", remote)

        landing = (ROOT / "server" / "geo.allgood.cn" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<article><strong>6</strong><span data-en="Demo tasks"', landing)
        self.assertIn('<article><strong>144</strong><span data-en="Synthetic answers"', landing)
        self.assertIn('<article><strong>4</strong><span data-en="GEO files"', landing)

    def test_demo_actions_explain_read_only_mode_without_opening_local_app(self):
        dashboard = (ROOT / "server" / "geo.allgood.cn" / "dashboard" / "index.php").read_text(encoding="utf-8")
        for marker in (
            "var isDemoMode =",
            "function showDemoRestriction(action)",
            "function requestLocalApp(target, action)",
            "if (isDemoMode)",
            "在线 Demo 不会连接你的本机账户、浏览器或桌面 App",
            "onclick=\"showDemoRestriction('创建任务')\"",
            'data-demo-restricted="true"',
            'aria-label="创建任务，Demo 中仅展示，点击查看说明"',
        ):
            self.assertIn(marker, dashboard)
        self.assertNotIn('onclick="openLocalApp(', dashboard)
        self.assertNotIn('disabled title="Demo 为只读模式"', dashboard)

    def test_cloud_header_has_a_compact_desktop_breakpoint(self):
        dashboard = (ROOT / "server" / "geo.allgood.cn" / "dashboard" / "index.php").read_text(encoding="utf-8")
        self.assertIn("@media(max-width:1200px)", dashboard)
        self.assertIn("current-account", dashboard)
        self.assertIn("header-full-label", dashboard)
        self.assertIn("header-compact-label", dashboard)
        self.assertIn("white-space:nowrap", dashboard)
        self.assertIn(".side-stack{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}", dashboard)
        self.assertIn(".side-stack{display:contents}", dashboard)
        self.assertIn("grid-template-columns:minmax(0,1.55fr) minmax(250px,.72fr) minmax(250px,.72fr)", dashboard)
        self.assertNotIn(".hero-panel{min-height:300px}", dashboard)

    def test_cloud_default_date_filters_use_browser_local_date(self):
        dashboard = (ROOT / "server" / "geo.allgood.cn" / "dashboard" / "index.php").read_text(encoding="utf-8")
        self.assertIn("function localDateValue(date)", dashboard)
        self.assertIn("date.getFullYear()", dashboard)
        self.assertIn("date.getMonth() + 1", dashboard)
        self.assertIn("date.getDate()", dashboard)
        self.assertIn("return localDateValue(date);", dashboard)
        self.assertNotIn("return date.toISOString().slice(0, 10);", dashboard)

    def test_cloud_large_result_queries_use_compact_summaries(self):
        sync = (ROOT / "server" / "geo.allgood.cn" / "api" / "sync" / "index.php").read_text(encoding="utf-8")
        api = (ROOT / "server" / "geo.allgood.cn" / "api" / "dashboard" / "index.php").read_text(encoding="utf-8")
        migration = (ROOT / "server" / "geo.allgood.cn" / "migrations" / "20260715_result_summaries.php").read_text(encoding="utf-8")
        incremental = (ROOT / "server" / "geo.allgood.cn" / "migrations" / "20260716_reference_items.php").read_text(encoding="utf-8")
        for source in (sync, migration):
            self.assertIn("reference_items", source)
        self.assertIn('(reference_items IS NULL OR reference_items="")', incremental)
        self.assertIn("$pdo->beginTransaction()", incremental)
        self.assertIn("SELECT reference_items,result_at", api)
        self.assertIn("geo_dashboard_compact_refs", api)
        self.assertIn("array_chunk(array_values($uniquePairs), 200)", api)
        self.assertIn("function geo_dashboard_stream_rows(PDO $pdo)", api)
        self.assertIn("Pdo\\\\Mysql::ATTR_USE_BUFFERED_QUERY", api)
        self.assertIn("PHP_VERSION_ID >= 80500", api)
        self.assertGreaterEqual(api.count("geo_dashboard_stream_rows($pdo);"), 3)
        self.assertNotIn("SELECT payload,result_at FROM geo_sync_results", api)
        self.assertIn("SELECT install_id,local_id,platform,question,local_created_at,synced_at FROM geo_sync_results", api)

    def test_ai_analysis_can_be_cancelled_and_has_bounded_timeouts(self):
        dashboard = (ROOT / "web_app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        app = (ROOT / "web_app" / "app.py").read_text(encoding="utf-8")
        self.assertIn("aiAnalysisController: null", dashboard)
        self.assertIn("cancelAiInsightAnalysis()", dashboard)
        self.assertIn("signal: controller.signal", dashboard)
        self.assertIn("timeout: 65000", dashboard)
        self.assertIn("timeout=(10, 50)", app)
        self.assertIn("except requests.exceptions.Timeout", app)

    def test_dashboard_exports_are_offline_and_desktop_path_aware(self):
        dashboard = (ROOT / "web_app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        app = (ROOT / "web_app" / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("cdn.sheetjs.com", dashboard)
        self.assertIn("downloadDashboardFile(url, fallbackFilename)", dashboard)
        self.assertIn("save_to_downloads", dashboard)
        self.assertIn("/api/analysis/references/export", dashboard)
        self.assertIn("def export_reference_analysis", app)
        self.assertGreaterEqual(app.count("_maybe_save_desktop_download("), 4)

    def test_result_rankings_only_use_explicit_brand_matches(self):
        results = (ROOT / "web_app" / "templates" / "results.html").read_text(encoding="utf-8")
        self.assertIn("明确排名均值", results)
        self.assertNotIn("minHospitalRank", results)
        self.assertNotIn("有曝光但未明确排名", results)
        self.assertNotIn("avgRank = 1", results)
        self.assertTrue((ROOT / "METRICS.md").is_file())


if __name__ == "__main__":
    unittest.main()
