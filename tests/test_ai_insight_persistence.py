import atexit
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


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
from models import SentimentConfig, User, db  # noqa: E402


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
            patch("remote_worker.worker_health", return_value=worker),
        ):
            response = self.client.get("/api/current-user")

        self.assertEqual(200, response.status_code)
        status.assert_called_once_with(self.user.id, include_remote=False)
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
            patch("remote_worker.worker_health", return_value=worker),
        ):
            response = self.client.get("/api/cloud-sync/status")

        self.assertEqual(200, response.status_code)
        status.assert_called_once_with(self.user.id, include_remote=True)
        payload = response.get_json()["cloud_sync"]
        self.assertEqual("2026-07-16 00:00:00", payload["last_synced_at"])
        self.assertEqual(2, payload["worker"]["runtime"]["pending_remote_tasks"])


if __name__ == "__main__":
    unittest.main()
