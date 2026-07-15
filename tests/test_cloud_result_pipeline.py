import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "web_app"
for path in (str(ROOT), str(WEB_APP)):
    if path not in sys.path:
        sys.path.insert(0, path)

import cloud_sync  # noqa: E402
import remote_worker  # noqa: E402
from models import CollectionResult, MonitorTask, User, db  # noqa: E402


class CloudPipelineTestCase(unittest.TestCase):
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

        self.user = User(username="pipeline-user", email="pipeline@example.com", password_hash="test")
        db.session.add(self.user)
        db.session.commit()

    def tearDown(self):
        remote_worker._running_task_ids.clear()
        db.session.remove()
        db.drop_all()
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        self.temp_dir.cleanup()

    def create_remote_task(self, remote_id=101):
        task = MonitorTask(
            user_id=self.user.id,
            name="Cloud collection",
            brand_name="GEO-SOP",
            brand_keywords='["GEO-SOP"]',
            competitor_brands="[]",
            questions='["How visible is GEO-SOP?"]',
            platforms='["doubao"]',
            screenshot_config="{}",
            collection_interval=5,
            max_parallel_platforms=1,
            schedule_type="manual",
            schedule_config=json.dumps({"remote_task_id": remote_id}),
            schedule_enabled=False,
            status="pending",
        )
        db.session.add(task)
        db.session.commit()
        return task

    @staticmethod
    def response(payload, status_code=200):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = payload
        response.text = json.dumps(payload, ensure_ascii=False)
        return response


class RemoteWorkerPipelineTests(CloudPipelineTestCase):
    def test_completed_remote_task_syncs_results_assets_and_status(self):
        task = self.create_remote_task(remote_id=101)

        def finish_collection(task_id, **_kwargs):
            local_task = db.session.get(MonitorTask, task_id)
            local_task.status = "completed"
            db.session.commit()

        collector = types.SimpleNamespace(run_collection=finish_collection)
        with (
            patch.dict(sys.modules, {"collector": collector}),
            patch.object(remote_worker, "report_remote_task_status", return_value={"success": True}) as report,
            patch.object(remote_worker, "sync_user_workspace", return_value={"success": True}) as sync,
            patch.object(remote_worker, "upload_workspace_assets", return_value={"enabled": True}) as upload,
        ):
            remote_worker._execute_remote_task(self.app, self.user.id, task.id, 101)

        statuses = [call.args[3] for call in report.call_args_list]
        self.assertEqual(["running", "completed"], statuses)
        sync.assert_called_once_with(self.user.id)
        upload.assert_called_once_with(self.user.id, task_ids=[task.id])
        db.session.expire_all()
        self.assertEqual("completed", db.session.get(MonitorTask, task.id).status)
        self.assertNotIn(task.id, remote_worker._running_task_ids)

    def test_collection_failure_is_persisted_synced_and_reported(self):
        task = self.create_remote_task(remote_id=102)
        collector = types.SimpleNamespace(run_collection=Mock(side_effect=RuntimeError("collector failed")))

        with (
            patch.dict(sys.modules, {"collector": collector}),
            patch.object(remote_worker.logger, "exception"),
            patch.object(remote_worker, "report_remote_task_status", return_value={"success": True}) as report,
            patch.object(remote_worker, "sync_user_workspace", return_value={"success": True}) as sync,
            patch.object(remote_worker, "upload_workspace_assets", return_value={"enabled": True}) as upload,
        ):
            remote_worker._execute_remote_task(self.app, self.user.id, task.id, 102)

        statuses = [call.args[3] for call in report.call_args_list]
        self.assertEqual(["running", "failed"], statuses)
        self.assertIn("collector failed", report.call_args_list[-1].args[4])
        sync.assert_called_once_with(self.user.id)
        upload.assert_not_called()
        db.session.expire_all()
        self.assertEqual("failed", db.session.get(MonitorTask, task.id).status)
        self.assertNotIn(task.id, remote_worker._running_task_ids)


class AssetUploadPipelineTests(CloudPipelineTestCase):
    def test_one_click_upload_sends_stats_and_screenshot_metadata(self):
        task = self.create_remote_task(remote_id=103)
        screenshot = Path(self.temp_dir.name) / "evidence.png"
        screenshot.write_bytes(b"GEO-SOP screenshot evidence")
        result = CollectionResult(
            task_id=task.id,
            question="How visible is GEO-SOP?",
            platform="doubao",
            answer="GEO-SOP is visible.",
            references="[]",
            screenshot_path="answers/evidence.png",
            has_brand_exposure=True,
            exposed_keywords='["GEO-SOP"]',
        )
        db.session.add(result)
        db.session.commit()

        stats_response = self.response({"success": True, "stats": {"id": 1}})
        file_response = self.response({"success": True, "size": screenshot.stat().st_size, "url": "https://cloud/evidence.png"})
        with (
            patch.object(cloud_sync, "cloud_sync_enabled", return_value=True),
            patch.object(cloud_sync, "cloud_sync_url", return_value="https://cloud.example/api"),
            patch.object(cloud_sync, "get_install_id", return_value="device-a"),
            patch.object(cloud_sync, "_headers", return_value={"Authorization": "Bearer test", "Content-Type": "application/json"}),
            patch.object(cloud_sync.requests, "post", side_effect=[stats_response, file_response]) as post,
        ):
            uploaded = cloud_sync.upload_workspace_assets(
                self.user.id,
                resolve_path=lambda _path: str(screenshot),
                task_ids=[task.id],
            )

        self.assertEqual(2, post.call_count)
        stats_payload = json.loads(post.call_args_list[0].kwargs["data"].decode("utf-8"))
        self.assertEqual(1, stats_payload["payload"]["counts"]["tasks"])
        self.assertEqual(1, stats_payload["payload"]["counts"]["results"])
        self.assertEqual(1, stats_payload["payload"]["counts"]["screenshots"])
        metadata = json.loads(post.call_args_list[1].kwargs["data"]["metadata"])
        self.assertEqual(result.id, metadata["local_result_id"])
        self.assertEqual(task.id, metadata["local_task_id"])
        self.assertEqual("doubao", metadata["platform"])
        self.assertEqual(1, uploaded["screenshots"]["uploaded"])
        self.assertEqual(screenshot.stat().st_size, uploaded["screenshots"]["bytes_uploaded"])

    def test_missing_screenshot_does_not_abort_stats_upload(self):
        task = self.create_remote_task(remote_id=104)
        db.session.add(CollectionResult(
            task_id=task.id,
            question="Missing evidence",
            platform="doubao",
            answer="Answer",
            references="[]",
            screenshot_path="answers/missing.png",
            has_brand_exposure=False,
        ))
        db.session.commit()

        with (
            patch.object(cloud_sync, "cloud_sync_enabled", return_value=True),
            patch.object(cloud_sync, "cloud_sync_url", return_value="https://cloud.example/api"),
            patch.object(cloud_sync, "get_install_id", return_value="device-a"),
            patch.object(cloud_sync, "_headers", return_value={"Authorization": "Bearer test", "Content-Type": "application/json"}),
            patch.object(cloud_sync.requests, "post", return_value=self.response({"success": True, "stats": {}})) as post,
        ):
            uploaded = cloud_sync.upload_workspace_assets(
                self.user.id,
                resolve_path=lambda _path: None,
                task_ids=[task.id],
            )

        self.assertEqual(1, post.call_count)
        self.assertEqual(1, uploaded["screenshots"]["missing"])
        self.assertEqual(0, uploaded["screenshots"]["failed"])


if __name__ == "__main__":
    unittest.main()
