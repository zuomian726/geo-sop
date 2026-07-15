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


if __name__ == "__main__":
    unittest.main()
