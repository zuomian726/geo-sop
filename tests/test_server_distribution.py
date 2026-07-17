import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server" / "geo.allgood.cn"


class ServerDistributionTests(unittest.TestCase):
    def test_cloud_distribution_contains_active_entrypoints_and_assets(self):
        required = {
            "api/common.php",
            "api/auth/login/index.php",
            "api/auth/logout/index.php",
            "api/dashboard/index.php",
            "api/remote-tasks/index.php",
            "api/sync/index.php",
            "dashboard/index.php",
            "login/index.php",
            "register/index.php",
            "demo/index.php",
            "public/assets/styles.css",
            "public/assets/site.js",
            "storage/sync_config.example.php",
        }
        missing = {relative for relative in required if not (SERVER / relative).is_file()}
        self.assertFalse(missing, missing)

    def test_dashboard_query_inputs_have_bounded_limits_and_valid_dates(self):
        source = (SERVER / "api" / "dashboard" / "index.php").read_text(encoding="utf-8")
        self.assertIn("min(500, $limit)", source)
        self.assertIn("min(100000, (int)($_GET['offset']", source)
        self.assertIn("geo_dashboard_text_param('keyword', 120)", source)
        self.assertIn("checkdate($month, $day, $year)", source)
        self.assertNotIn("$offset = max(0, (int)($_GET['offset']", source)

    def test_remote_task_status_payload_is_bounded_and_excludes_client_extras(self):
        source = (SERVER / "api" / "remote-tasks" / "index.php").read_text(encoding="utf-8")
        self.assertIn("mb_substr(trim((string)($data['message']", source)
        self.assertIn("$statusPayload = [", source)
        self.assertNotIn("$payload = json_encode($data", source)
        self.assertIn("$heartbeatPayload = [", source)
        self.assertIn("'sync_backlog' => max(0, min(10000", source)

    def test_php_sources_do_not_hardcode_the_production_document_root(self):
        offenders = []
        for path in SERVER.rglob("*.php"):
            if "/www/wwwroot/geo.allgood.cn" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(SERVER)))
        self.assertFalse(offenders, offenders)

    def test_server_source_has_no_default_account_or_literal_database_secret(self):
        sources = "\n".join(path.read_text(encoding="utf-8") for path in SERVER.rglob("*.php"))
        self.assertNotIn("watson@geo.allgood.cn", sources)
        self.assertNotIn("password_hash('watson'", sources)
        literal_secret = re.compile(r"['\"](?:db_pass|aliyun_sms_secret|wechat_appsecret)['\"]\s*=>\s*['\"][^'\"]{8,}['\"]")
        self.assertIsNone(literal_secret.search(sources))

    def test_server_errors_use_request_ids_without_exposing_exception_details(self):
        common = (SERVER / "api" / "common.php").read_text(encoding="utf-8")
        self.assertIn("function geo_internal_error", common)
        self.assertIn("'request_id' => $requestId", common)
        for relative in (
            "api/dashboard/index.php",
            "api/sync/index.php",
            "api/sync/restore/index.php",
            "api/sync/assets/index.php",
            "api/remote-tasks/index.php",
        ):
            source = (SERVER / relative).read_text(encoding="utf-8")
            self.assertIn("geo_internal_error(", source, relative)
            self.assertNotIn("'error' => $e->getMessage()", source, relative)

    def test_private_config_is_environment_backed_and_optional_logins_are_disabled(self):
        example = (SERVER / "storage" / "sync_config.example.php").read_text(encoding="utf-8")
        common = (SERVER / "api" / "common.php").read_text(encoding="utf-8")
        for key in ("GEO_DB_PASSWORD", "GEO_LEGACY_SYNC_TOKEN", "GEO_SYNC_CONFIG"):
            self.assertIn(key, example if key != "GEO_SYNC_CONFIG" else common)
        self.assertIn("'sms_enabled' => false", example)
        self.assertIn("'wechat_enabled' => false", example)
        self.assertIn("!empty($c['wechat_enabled'])", common)
        self.assertIn("!empty($c['sms_enabled'])", common)

    def test_web_sessions_are_hardened_and_default_account_bootstrap_is_empty(self):
        common = (SERVER / "api" / "common.php").read_text(encoding="utf-8")
        self.assertIn("session.use_strict_mode", common)
        self.assertIn("'httponly' => true", common)
        self.assertIn("'samesite' => 'Lax'", common)
        bootstrap = common.split("function geo_bootstrap", 1)[1].split("function geo_current_web_user", 1)[0]
        self.assertNotIn("INSERT INTO", bootstrap)

    def test_desktop_device_tokens_expire_and_can_be_revoked(self):
        common = (SERVER / "api" / "common.php").read_text(encoding="utf-8")
        login = (SERVER / "api" / "auth" / "login" / "index.php").read_text(encoding="utf-8")
        logout = (SERVER / "api" / "auth" / "logout" / "index.php").read_text(encoding="utf-8")
        self.assertIn("expires_at DATETIME", common)
        self.assertIn("t.expires_at>?", common)
        self.assertNotIn("SELECT * FROM geo_cloud_users WHERE api_token_hash", common)
        self.assertIn("30 * 86400", login)
        self.assertIn("expires_at_epoch", login)
        self.assertIn("revoked_at=?", logout)
        sync = (SERVER / "api" / "sync" / "index.php").read_text(encoding="utf-8")
        token_lookup = sync.split("function cloud_user_id_for_token", 1)[1].split("function cloud_user_is_demo", 1)[0]
        self.assertIn("expires_at>?", token_lookup)
        self.assertEqual(1, token_lookup.count("api_token_hash"))

    def test_web_mutations_use_csrf_tokens_and_logins_are_rate_limited(self):
        common = (SERVER / "api" / "common.php").read_text(encoding="utf-8")
        self.assertIn("function geo_csrf_token()", common)
        self.assertIn("function geo_require_csrf", common)
        self.assertIn("CREATE TABLE IF NOT EXISTS geo_auth_events", common)
        self.assertIn("function geo_login_rate_limited", common)

        for relative in ("login/index.php", "register/index.php", "dashboard/index.php"):
            source = (SERVER / relative).read_text(encoding="utf-8")
            self.assertIn("geo_require_csrf(", source, relative)
            self.assertIn('name="csrf_token"', source, relative)

        api_login = (SERVER / "api" / "auth" / "login" / "index.php").read_text(encoding="utf-8")
        self.assertIn("geo_login_rate_limited($pdo, $account)", api_login)
        self.assertIn("geo_record_login_attempt($pdo, $account, false)", api_login)

    def test_public_asset_references_are_in_the_distribution(self):
        missing = set()
        for relative in ("index.html", "tools/index.html", "login/index.php", "register/index.php"):
            source = (SERVER / relative).read_text(encoding="utf-8")
            for asset in re.findall(r"(?:src|href)=[\"'](/public/assets/[^\"'?]+)", source):
                if not (SERVER / asset.lstrip("/")).is_file():
                    missing.add(asset)
        self.assertFalse(missing, missing)

    def test_demo_has_query_export_and_read_only_smoke_coverage(self):
        smoke = (ROOT / "tools" / "smoke_cloud_site.py").read_text(encoding="utf-8")
        for marker in ("action=overview", "action=export_geo", "action=remote_status", "不能创建或修改任务"):
            self.assertIn(marker, smoke)
        self.assertIn('name="csrf_token"', smoke)
        self.assertIn('"csrf_token": csrf_match.group(1).decode()', smoke)

        pipeline = (ROOT / "tools" / "smoke_cloud_client_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("registration page did not provide a CSRF token", pipeline)
        self.assertIn('"csrf_token": csrf_match.group(1)', pipeline)
        self.assertIn('runpy.run_path(str(ROOT / "version.py"))', pipeline)
        self.assertNotIn('"app_version": "0.3.', pipeline)

    def test_demo_entry_is_one_click_and_read_only_identity_is_centralized(self):
        common = (SERVER / "api" / "common.php").read_text(encoding="utf-8")
        landing = (SERVER / "demo" / "index.php").read_text(encoding="utf-8")
        login = (SERVER / "login" / "index.php").read_text(encoding="utf-8")
        self.assertIn("function geo_demo_username()", common)
        self.assertIn("function geo_is_demo_user($user)", common)
        self.assertIn('name="demo_login" value="1"', landing)
        self.assertIn("一键进入在线 Demo", landing)
        self.assertIn("$demoLogin ? geo_is_demo_user($user)", login)
        self.assertIn("一键进入 Demo 工作台", login)
        for relative in (
            "api/dashboard/index.php",
            "api/remote-tasks/index.php",
            "api/sync/assets/index.php",
            "dashboard/index.php",
        ):
            source = (SERVER / relative).read_text(encoding="utf-8")
            self.assertIn("geo_is_demo_user(", source, relative)

    def test_hot_api_schema_changes_are_versioned_and_locked(self):
        common = (SERVER / "api" / "common.php").read_text(encoding="utf-8")
        self.assertIn("function geo_run_schema_migration", common)
        self.assertIn("geo_schema_versions", common)
        self.assertIn("GET_LOCK(?, 15)", common)
        self.assertIn("RELEASE_LOCK(?)", common)
        self.assertIn("geo_run_schema_migration($pdo, 'core'", common)

        components = {
            "api/sync/index.php": "sync_workspace",
            "api/sync/assets/index.php": "sync_assets",
            "api/remote-tasks/index.php": "remote_tasks",
        }
        for relative, component in components.items():
            source = (SERVER / relative).read_text(encoding="utf-8")
            self.assertIn(f"geo_run_schema_migration($pdo, '{component}'", source, relative)

    def test_screenshot_upload_updates_result_metrics_and_dedupes_per_result(self):
        source = (SERVER / "api" / "sync" / "assets" / "index.php").read_text(encoding="utf-8")
        self.assertIn("cloud_user_id, install_id, local_result_id, kind, sha256", source)
        self.assertIn("function geo_assets_mark_result_screenshot", source)
        self.assertIn("UPDATE geo_sync_results SET has_screenshot=1", source)

    def test_screenshot_upload_and_download_enforce_account_and_file_boundaries(self):
        upload = (SERVER / "api" / "sync" / "assets" / "index.php").read_text(encoding="utf-8")
        dashboard = (SERVER / "api" / "dashboard" / "index.php").read_text(encoding="utf-8")
        nginx = (SERVER / "deploy" / "nginx" / "geo.allgood.cn.conf").read_text(encoding="utf-8")

        for marker in (
            "CONTENT_LENGTH",
            "UPLOAD_ERR_OK",
            "getimagesize($tmp)",
            "geo_assets_require_result",
            '"/api/dashboard/?action=asset&asset_id={$assetId}"',
            "file is not a supported screenshot image",
            "unset($payload['original_path'], $payload['user_key'])",
        ):
            self.assertIn(marker, upload)
        self.assertNotIn('$_FILES[\'file\'][\'type\']', upload)
        self.assertIn("WHERE id=? AND cloud_user_id=?", dashboard)
        self.assertIn("Cache-Control: private, no-store", dashboard)
        self.assertIn("/api/dashboard/?action=asset&asset_id=", dashboard)
        self.assertIn("if ($isDemoUser) $allowedRoots[]", dashboard)
        self.assertIn("Content-Security-Policy: sandbox", dashboard)
        self.assertIn("location ^~ /storage/cloud-assets/", nginx)
        self.assertLess(nginx.index("location ^~ /storage/cloud-assets/"), nginx.rindex("}"))

        pipeline = (ROOT / "tools" / "smoke_cloud_client_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("owner_asset.status_code != 200", pipeline)
        self.assertIn("anonymous_asset.status_code not in {401, 403}", pipeline)
        self.assertIn("other_asset.status_code not in {403, 404}", pipeline)
        self.assertNotIn("uploaded screenshot is not publicly readable", pipeline)

    def test_nginx_preserves_json_404_responses_for_api_routes(self):
        source = (SERVER / "deploy" / "nginx" / "geo.allgood.cn.conf").read_text(encoding="utf-8")
        web_location = source.index("location / {")
        php_include = source.index("include enable-php-82.conf")
        self.assertLess(web_location, php_include)
        self.assertEqual(1, source.count("error_page 404 /404.html;"))
        self.assertIn("error_page 404 /404.html;", source[web_location:php_include])

    def test_geo_coverage_uses_install_and_domain_candidate_buckets(self):
        source = (SERVER / "api" / "dashboard" / "index.php").read_text(encoding="utf-8")
        coverage = source[source.index("if ($action === 'geo_coverage')"):source.index("if ($action === 'tasks')")]
        self.assertIn("$manuscriptMatchKeys", coverage)
        self.assertIn("$bucketKey = (string)$result['install_id'] . '|' . $refDomain", coverage)
        self.assertIn("geo_dashboard_url_keys_match", coverage)
        self.assertNotIn("array_keys($manuscripts)", coverage)


if __name__ == "__main__":
    unittest.main()
