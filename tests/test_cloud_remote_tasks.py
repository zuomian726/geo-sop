import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "web_app"
for path in (str(ROOT), str(WEB_APP)):
    if path not in sys.path:
        sys.path.insert(0, path)

from cloud_sync import pull_remote_tasks  # noqa: E402
from models import MonitorTask, User, db  # noqa: E402


class RemoteTaskPullTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI=f"sqlite:///{Path(self.temp_dir.name) / 'test.db'}",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.user = User(username="cloud-user", email="cloud-user@example.com", password_hash="test")
        db.session.add(self.user)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        self.temp_dir.cleanup()

    @staticmethod
    def _response(payload, status_code=200):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = payload
        response.text = json.dumps(payload, ensure_ascii=False)
        return response

    def _run_pull(self, tasks):
        get_response = self._response({"success": True, "tasks": tasks})
        post_response = self._response({"success": True, "updated": []})
        with (
            patch("cloud_sync.cloud_sync_enabled", return_value=True),
            patch("cloud_sync.cloud_sync_url", return_value="https://cloud.example/api"),
            patch("cloud_sync.get_install_id", return_value="device-a"),
            patch("cloud_sync._headers", return_value={"Authorization": "Bearer test"}),
            patch("cloud_sync.requests.get", return_value=get_response),
            patch("cloud_sync.requests.post", return_value=post_response) as post,
        ):
            result = pull_remote_tasks(self.user.id)
        return result, post

    def test_existing_remote_task_is_acknowledged_with_local_id(self):
        task = MonitorTask(
            user_id=self.user.id,
            name="Existing",
            brand_keywords='["GEO-SOP"]',
            questions='["What is GEO-SOP?"]',
            platforms='["doubao"]',
            schedule_config='{"remote_task_id": 77}',
            status="pending",
        )
        db.session.add(task)
        db.session.commit()

        result, post = self._run_pull([{
            "id": 77,
            "name": "Existing",
            "payload": {
                "brand_keywords": ["GEO-SOP"],
                "questions": ["What is GEO-SOP?"],
                "platforms": ["doubao"],
            },
        }])

        self.assertEqual([], result["created"])
        self.assertEqual(task.id, result["skipped"][0]["local_task_id"])
        ack = json.loads(post.call_args.kwargs["data"].decode("utf-8"))
        self.assertEqual(task.id, ack["skipped"][0]["local_task_id"])
        self.assertEqual(1, MonitorTask.query.count())

    def test_claimed_task_is_created_once_and_acknowledged(self):
        remote = {
            "id": 88,
            "name": "Cloud task",
            "created_at": "2026-07-15 10:00:00",
            "payload": {
                "name": "Cloud task",
                "brand_name": "GEO-SOP",
                "brand_keywords": ["GEO-SOP"],
                "questions": ["How visible is GEO-SOP?"],
                "platforms": ["doubao"],
            },
        }

        result, post = self._run_pull([remote])

        self.assertEqual(1, len(result["created"]))
        local_task = MonitorTask.query.one()
        self.assertEqual(88, json.loads(local_task.schedule_config)["remote_task_id"])
        ack = json.loads(post.call_args.kwargs["data"].decode("utf-8"))
        self.assertEqual(local_task.id, ack["imported"][0]["local_task_id"])

    def test_unsupported_platform_is_skipped_and_acknowledged(self):
        result, post = self._run_pull([{
            "id": 99,
            "name": "Invalid platform task",
            "payload": {
                "brand_keywords": ["GEO-SOP"],
                "questions": ["How visible is GEO-SOP?"],
                "platforms": ["doubao", "not-a-real-platform"],
            },
        }])

        self.assertEqual([], result["created"])
        self.assertEqual(0, MonitorTask.query.count())
        self.assertIn("unsupported platforms", result["skipped"][0]["reason"])
        ack = json.loads(post.call_args.kwargs["data"].decode("utf-8"))
        self.assertEqual(99, ack["skipped"][0]["remote_task_id"])
        self.assertIn("not-a-real-platform", ack["skipped"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
