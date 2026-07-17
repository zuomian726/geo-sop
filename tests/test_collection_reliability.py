import json
import os
import shutil
import sys
import tempfile
import unittest
import atexit
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "web_app"
TEST_DATA_DIR = tempfile.mkdtemp(prefix="geo-sop-collection-tests-")
atexit.register(shutil.rmtree, TEST_DATA_DIR, ignore_errors=True)
os.environ["GEO_DESKTOP_MODE"] = "1"
os.environ["GEO_DATA_DIR"] = TEST_DATA_DIR
os.environ["GEO_CLOUD_SYNC_ENABLED"] = "0"
for path in (str(ROOT), str(WEB_APP)):
    if path not in sys.path:
        sys.path.insert(0, path)

import app as web_app
import collector
from models import MonitorTask, User, db, recover_interrupted_tasks


class CollectionReliabilityTests(unittest.TestCase):
    def setUp(self):
        web_app.app.config.update(TESTING=True, SQLALCHEMY_TRACK_MODIFICATIONS=False)
        self.context = web_app.app.app_context()
        self.context.push()
        db.create_all()
        self.user = User(username="collector-user", email="collector@example.com", password_hash="test")
        db.session.add(self.user)
        db.session.flush()
        self.task = MonitorTask(
            user_id=self.user.id,
            name="Collection reliability",
            brand_name="GEO-SOP",
            brand_keywords=json.dumps(["GEO-SOP"]),
            competitor_brands="[]",
            questions=json.dumps(["Question one", "Question two"]),
            platforms=json.dumps(["doubao"]),
            screenshot_config=json.dumps({"doubao": True}),
            max_parallel_platforms=1,
            status="pending",
        )
        db.session.add(self.task)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.session.remove()
        db.engine.dispose()
        self.context.pop()

    def _run_with_summary(self, succeeded, failed):
        summary = {
            "platform": "doubao",
            "expected": 2,
            "succeeded": succeeded,
            "failed": failed,
            "errors": [] if not failed else [{"question": "Question two", "message": "login expired"}],
            "stopped": False,
        }
        with tempfile.TemporaryDirectory() as output_dir:
            with (
                patch.object(collector, "answers_dir", return_value=Path(output_dir)),
                patch.object(collector, "collect_platform", return_value=summary),
                patch("utils.reset_timestamp_dir"),
            ):
                collector.run_collection(self.task.id, min_interval=1, max_interval=1)
        db.session.expire_all()
        return db.session.get(MonitorTask, self.task.id)

    def test_collection_status_distinguishes_complete_partial_and_failed(self):
        task = self._run_with_summary(2, 0)
        self.assertEqual("completed", task.status)

        task = self._run_with_summary(1, 1)
        self.assertEqual("partial", task.status)
        self.assertEqual(1, task.to_dict()["last_run_summary"]["failed"])

        task = self._run_with_summary(0, 2)
        self.assertEqual("failed", task.status)

    def test_startup_recovers_tasks_interrupted_by_app_exit(self):
        self.task.status = "running"
        db.session.commit()

        recovered = recover_interrupted_tasks()

        self.assertEqual(1, recovered)
        db.session.expire_all()
        task = db.session.get(MonitorTask, self.task.id)
        self.assertEqual("failed", task.status)
        self.assertTrue(task.to_dict()["last_run_summary"]["interrupted"])
        self.assertIn("重新执行", task.to_dict()["last_run_summary"]["error"])


if __name__ == "__main__":
    unittest.main()
