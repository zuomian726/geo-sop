import atexit
import json
import os
import shutil
import sys
import tempfile
import unittest
import requests
from pathlib import Path
from unittest.mock import Mock, call, patch
from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "web_app"
AI_TEST_DATA_DIR = tempfile.mkdtemp(prefix="geo-sop-ai-tests-")
atexit.register(shutil.rmtree, AI_TEST_DATA_DIR, ignore_errors=True)
os.environ["GEO_DESKTOP_MODE"] = "1"
os.environ["GEO_DATA_DIR"] = AI_TEST_DATA_DIR
os.environ["GEO_CLOUD_SYNC_ENABLED"] = "0"
for path in (str(ROOT), str(WEB_APP)):
    if path not in sys.path:
        sys.path.insert(0, path)

import app as web_app  # noqa: E402
import cloud_sync  # noqa: E402
from models import SentimentConfig, User, db, ensure_local_sync_schema  # noqa: E402


class AiInsightPersistenceTests(unittest.TestCase):
    def setUp(self):
        web_app.app.config.update(TESTING=True, SQLALCHEMY_TRACK_MODIFICATIONS=False)
        self.context = web_app.app.app_context()
        self.context.push()
        db.create_all()
        self.user = User(username="insight-user", email="insight@example.com", password_hash="test")
        db.session.add(self.user)
        db.session.flush()
        self.config = SentimentConfig(
            user_id=self.user.id,
            name="Default AI",
            enable_ai_sentiment=True,
            ai_api_url="https://api.example.com",
            ai_api_key="local-secret-key",
            ai_model_name="example-model",
            is_default=True,
        )
        db.session.add(self.config)
        db.session.commit()
        self.client = web_app.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.user.id)
            session["_fresh"] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.session.remove()
        db.engine.dispose()
        self.context.pop()

    def test_ai_analysis_is_persisted_and_returned_after_refresh(self):
        insight = {
            "summary": "品牌可见度有提升空间",
            "observations": ["平台覆盖不足"],
            "actions": ["补充官网 FAQ"],
            "risks": ["样本量偏小"],
            "experiments": ["测试品牌对比问题"],
        }
        ai_response = Mock()
        ai_response.raise_for_status.return_value = None
        ai_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(insight, ensure_ascii=False)}}]
        }

        with patch("requests.post", return_value=ai_response):
            response = self.client.post("/api/insights/ai-analysis")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual(insight, payload["analysis"])
        self.assertTrue(payload["generated_at"])

        db.session.expire_all()
        stored = db.session.get(SentimentConfig, self.config.id)
        self.assertEqual(insight, json.loads(stored.latest_insight))
        self.assertIsNotNone(stored.latest_insight_generated_at)

        overview = self.client.get("/api/insights/overview").get_json()["data"]
        self.assertEqual(insight, overview["latest_insight"])
        self.assertTrue(overview["latest_insight_generated_at"])

    def test_ai_analysis_timeout_returns_promptly_with_fallback(self):
        with patch("requests.post", side_effect=requests.exceptions.Timeout("provider stalled")):
            response = self.client.post("/api/insights/ai-analysis")

        self.assertEqual(504, response.status_code)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertIn("响应超时", payload["message"])
        self.assertIn("fallback", payload)
        self.assertNotIn("provider stalled", response.get_data(as_text=True))

    def test_cloud_payload_syncs_insight_but_never_api_key_by_default(self):
        insight = {"summary": "可同步分析", "actions": ["执行动作"]}
        self.config.latest_insight = json.dumps(insight, ensure_ascii=False)
        self.config.latest_insight_generated_at = web_app.now_cst()
        db.session.commit()

        with patch.dict(os.environ, {"GEO_CLOUD_SYNC_KEYS": "0"}):
            payload = cloud_sync._config_payload(self.config)

        self.assertIsNone(payload["ai_api_key"])
        self.assertEqual(insight, payload["latest_insight"])
        self.assertTrue(payload["latest_insight_generated_at"])

    def test_sentiment_config_api_never_returns_saved_api_key(self):
        response = self.client.get("/api/sentiment/configs")

        self.assertEqual(200, response.status_code)
        config = response.get_json()["configs"][0]
        self.assertIsNone(config["ai_api_key"])
        self.assertTrue(config["api_key_configured"])
        self.assertNotIn("local-secret-key", response.get_data(as_text=True))

    def test_sentiment_api_key_is_encrypted_in_local_database(self):
        raw_value = db.session.execute(
            text("SELECT ai_api_key FROM sentiment_configs WHERE id=:id"),
            {"id": self.config.id},
        ).scalar_one()

        self.assertTrue(raw_value.startswith("enc:v1:"))
        self.assertNotIn("local-secret-key", raw_value)
        self.assertEqual("local-secret-key", self.config.ai_api_key)

    def test_legacy_plaintext_api_key_is_migrated_on_startup(self):
        db.session.execute(
            text("UPDATE sentiment_configs SET ai_api_key=:value WHERE id=:id"),
            {"value": "legacy-plaintext-key", "id": self.config.id},
        )
        db.session.commit()

        ensure_local_sync_schema()
        db.session.expire_all()
        raw_value = db.session.execute(
            text("SELECT ai_api_key FROM sentiment_configs WHERE id=:id"),
            {"id": self.config.id},
        ).scalar_one()

        self.assertTrue(raw_value.startswith("enc:v1:"))
        self.assertNotIn("legacy-plaintext-key", raw_value)
        self.assertEqual("legacy-plaintext-key", db.session.get(SentimentConfig, self.config.id).ai_api_key)

    def test_sentiment_config_update_keeps_saved_key_when_input_is_blank(self):
        response = self.client.put(
            f"/api/sentiment/configs/{self.config.id}",
            json={
                "name": "Updated AI",
                "enable_ai_sentiment": True,
                "ai_api_key": "",
            },
        )

        self.assertEqual(200, response.status_code)
        db.session.expire_all()
        stored = db.session.get(SentimentConfig, self.config.id)
        self.assertEqual("local-secret-key", stored.ai_api_key)
        self.assertEqual("Updated AI", stored.name)
        self.assertNotIn("local-secret-key", response.get_data(as_text=True))

    def test_restored_config_keeps_cloud_identity_when_resynced(self):
        self.config.cloud_source_install_id = "original-device"
        self.config.cloud_source_local_id = 42
        self.config.latest_insight = json.dumps({"summary": "新设备生成的分析"}, ensure_ascii=False)
        db.session.commit()

        workspace = cloud_sync.build_workspace_payload(self.user.id)

        self.assertEqual(1, len(workspace["sentiment_configs"]))
        payload = workspace["sentiment_configs"][0]
        self.assertEqual("original-device", payload["_sync_install_id"])
        self.assertEqual(42, payload["_sync_local_id"])
        self.assertIsNone(payload["ai_api_key"])

    def test_current_user_uses_local_cloud_snapshot_for_fast_first_paint(self):
        worker = {
            "started": True,
            "online": True,
            "runtime": {"worker_state": "ready"},
        }
        with (
            patch.object(web_app, "sync_status", return_value={"enabled": True}) as status,
            patch("remote_worker.start_remote_task_worker", return_value=False) as ensure_worker,
            patch("remote_worker.worker_health", return_value=worker),
        ):
            response = self.client.get("/api/current-user")

        self.assertEqual(200, response.status_code)
        status.assert_called_once_with(self.user.id, include_remote=False)
        ensure_worker.assert_called_once_with(web_app.app)
        self.assertEqual(worker, response.get_json()["cloud_sync"]["worker"])

    def test_cloud_status_refresh_reads_remote_state_and_worker_health(self):
        worker = {
            "started": True,
            "online": True,
            "runtime": {"worker_state": "queued", "pending_remote_tasks": 2},
        }
        with (
            patch.object(
                web_app,
                "sync_status",
                return_value={"enabled": True, "last_synced_at": "2026-07-16 00:00:00"},
            ) as status,
            patch("remote_worker.start_remote_task_worker", return_value=True) as ensure_worker,
            patch("remote_worker.worker_health", return_value=worker),
        ):
            response = self.client.get("/api/cloud-sync/status")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            [
                call(self.user.id, include_remote=False),
                call(self.user.id, include_remote=True),
            ],
            status.call_args_list,
        )
        ensure_worker.assert_called_once_with(web_app.app)
        payload = response.get_json()["cloud_sync"]
        self.assertEqual("2026-07-16 00:00:00", payload["last_synced_at"])
        self.assertEqual(2, payload["worker"]["runtime"]["pending_remote_tasks"])

    def test_worker_watchdog_runs_before_remote_status_failure(self):
        with (
            patch.object(web_app, "sync_status", side_effect=RuntimeError("cloud unavailable")),
            patch("remote_worker.start_remote_task_worker", return_value=True) as ensure_worker,
            patch("remote_worker.worker_health", return_value={"started": True}),
            patch.object(web_app.logger, "exception"),
        ):
            response = self.client.get("/api/cloud-sync/status")

        self.assertEqual(200, response.status_code)
        ensure_worker.assert_called_once_with(web_app.app)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertTrue(payload["cloud_sync"]["worker"]["degraded"])

    def test_remote_status_failure_keeps_local_worker_state(self):
        worker = {"started": True, "online": True, "degraded": False}
        with (
            patch.object(
                web_app,
                "sync_status",
                side_effect=[{"enabled": True}, RuntimeError("request timed out")],
            ),
            patch("remote_worker.start_remote_task_worker", return_value=False),
            patch("remote_worker.worker_health", return_value=worker),
        ):
            response = self.client.get("/api/cloud-sync/status")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()["cloud_sync"]
        self.assertEqual(worker, payload["worker"])
        self.assertIn("自动重试", payload["error"])

    def test_reconnect_wakes_worker_without_waiting_for_network(self):
        worker = {"started": True, "online": False, "degraded": False}
        with (
            patch.object(web_app, "cloud_sync_enabled", return_value=True),
            patch.object(web_app, "sync_status", return_value={"enabled": True}),
            patch("remote_worker.start_remote_task_worker", return_value=False),
            patch("remote_worker.worker_health", return_value=worker),
            patch("remote_worker.wake_remote_task_worker", return_value=False) as wake,
        ):
            response = self.client.post("/api/cloud-sync/reconnect")

        self.assertEqual(200, response.status_code)
        wake.assert_called_once_with(web_app.app)
        self.assertTrue(response.get_json()["success"])

    def test_desktop_logout_reports_offline_and_clears_cloud_token(self):
        with (
            patch.object(web_app, "report_client_heartbeat") as heartbeat,
            patch.object(web_app, "revoke_cloud_token") as revoke_token,
            patch.object(web_app, "clear_cloud_account") as clear_account,
        ):
            response = self.client.get("/logout")

        self.assertEqual(302, response.status_code)
        self.assertTrue(response.headers["Location"].endswith("/login"))
        heartbeat.assert_called_once_with(self.user.id, "offline", "用户已在本机退出 GEO-SOP")
        revoke_token.assert_called_once_with()
        clear_account.assert_called_once_with()

    def test_create_user_cli_validates_password_and_never_bootstraps_admin(self):
        runner = web_app.app.test_cli_runner()
        weak = runner.invoke(
            args=["create-user", "--username", "cli-user", "--email", "cli@example.com", "--password", "short"]
        )
        self.assertNotEqual(0, weak.exit_code)
        self.assertIsNone(User.query.filter_by(username="cli-user").first())
        self.assertIsNone(User.query.filter_by(username="admin").first())

        created = runner.invoke(
            args=[
                "create-user",
                "--username",
                "cli-user",
                "--email",
                "cli@example.com",
                "--password",
                "cli-test-password",
            ]
        )
        self.assertEqual(0, created.exit_code, created.output)
        self.assertIsNotNone(User.query.filter_by(username="cli-user").first())

    def test_required_desktop_login_forces_cloud_and_does_not_store_cloud_password(self):
        cloud_response = Mock(status_code=200)
        cloud_response.json.return_value = {
            "success": True,
            "token": "cloud-token",
            "cloud_sync_url": "https://geo.allgood.cn/api",
            "user": {"username": "cloud-user", "email": "cloud-user@geo.allgood.cn"},
        }
        with (
            patch.dict(
                web_app.app.config,
                {
                    "DESKTOP_MODE": True,
                    "REQUIRE_LOGIN": True,
                    "CLOUD_SYNC_ENABLED": False,
                    "CLOUD_SYNC_TOKEN": "",
                },
            ),
            patch.dict(
                os.environ,
                {"GEO_CLOUD_SYNC_ENABLED": "0", "GEO_CLOUD_SYNC_TOKEN": ""},
            ),
            patch.object(web_app.requests, "post", return_value=cloud_response) as cloud_login,
            patch.object(web_app, "save_cloud_account"),
            patch.object(web_app, "_queue_cloud_workspace_merge", return_value={"queued": True}),
            patch.object(web_app, "_queue_cloud_sync"),
            patch("remote_worker.wake_remote_task_worker"),
        ):
            response = self.client.post(
                "/login",
                json={"username": "cloud-user", "password": "cloud-password", "cloud_login": False},
            )

        self.assertEqual(200, response.status_code)
        cloud_login.assert_called_once()
        stored = User.query.filter_by(username="cloud-user").one()
        self.assertFalse(stored.check_password("cloud-password"))

    def test_cloud_login_network_errors_are_actionable_and_do_not_leak_details(self):
        with (
            patch.dict(web_app.app.config, {"DESKTOP_MODE": True, "REQUIRE_LOGIN": True}),
            patch.object(
                web_app.requests,
                "post",
                side_effect=requests.exceptions.ConnectionError("private-host.example refused secret-path"),
            ),
        ):
            response = self.client.post(
                "/login",
                json={"username": "cloud-user", "password": "cloud-password"},
            )

        self.assertEqual(503, response.status_code)
        body = response.get_data(as_text=True)
        self.assertIn("检查网络", response.get_json()["message"])
        self.assertNotIn("private-host", body)
        self.assertNotIn("secret-path", body)

    def test_required_desktop_registration_uses_the_shared_cloud_account(self):
        with patch.dict(web_app.app.config, {"DESKTOP_MODE": True, "REQUIRE_LOGIN": True}):
            get_response = self.client.get("/register")
            post_response = self.client.post(
                "/register",
                json={"username": "local-only", "password": "password123"},
            )

        self.assertEqual(302, get_response.status_code)
        self.assertEqual("https://geo.allgood.cn/register/", get_response.headers["Location"])
        self.assertEqual(409, post_response.status_code)
        self.assertEqual("https://geo.allgood.cn/register/", post_response.get_json()["register_url"])


if __name__ == "__main__":
    unittest.main()
