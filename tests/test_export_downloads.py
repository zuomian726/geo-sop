import io
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "web_app"
EXPORT_TEST_DATA_DIR = tempfile.mkdtemp(prefix="geo-sop-export-tests-")
os.environ["GEO_DESKTOP_MODE"] = "1"
os.environ["GEO_DATA_DIR"] = EXPORT_TEST_DATA_DIR
for path in (str(ROOT), str(WEB_APP)):
    if path not in sys.path:
        sys.path.insert(0, path)

import app as web_app  # noqa: E402
from models import CollectionResult, MonitorTask, User, db  # noqa: E402


class ExportDownloadTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(EXPORT_TEST_DATA_DIR, ignore_errors=True)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        web_app.app.config.update(
            TESTING=True,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        self.context = web_app.app.app_context()
        self.context.push()
        db.create_all()

        self.user = User(username="export-user", email="export@example.com", password_hash="test")
        db.session.add(self.user)
        db.session.flush()
        self.task = MonitorTask(
            user_id=self.user.id,
            name="Export regression",
            brand_name="GEO-SOP",
            brand_keywords='["GEO-SOP"]',
            competitor_brands="[]",
            questions='["How visible is GEO-SOP?"]',
            platforms='["doubao"]',
            screenshot_config="{}",
            schedule_type="manual",
            schedule_config="{}",
            status="completed",
        )
        db.session.add(self.task)
        db.session.commit()

        self.screenshot = Path(self.temp_dir.name) / "relative-evidence.png"
        Image.new("RGB", (320, 180), color=(71, 95, 255)).save(self.screenshot)
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
        self.temp_dir.cleanup()

    def add_result(self, question="How visible is GEO-SOP?"):
        result = CollectionResult(
            task_id=self.task.id,
            question=question,
            platform="doubao",
            answer="GEO-SOP is visible and recommended.",
            references='[{"title":"GEO guide","url":"https://example.com/geo"}]',
            screenshot_path="answers/doubao/relative-evidence.png",
            has_brand_exposure=True,
            exposed_keywords='["GEO-SOP"]',
        )
        db.session.add(result)
        db.session.commit()
        return result

    def test_excel_export_embeds_resolved_relative_screenshot(self):
        self.add_result()
        with patch.object(web_app, "_resolve_screenshot_path", return_value=str(self.screenshot)):
            response = self.client.get(f"/api/tasks/{self.task.id}/export")

        self.assertEqual(200, response.status_code)
        self.assertIn("application/vnd.openxmlformats-officedocument", response.content_type)
        self.assertIn("attachment", response.headers.get("Content-Disposition", ""))
        workbook = load_workbook(io.BytesIO(response.data))
        worksheet = workbook["采集结果"]
        self.assertEqual(1, len(worksheet._images))
        self.assertEqual("豆包", worksheet["A2"].value)
        self.assertEqual("是", worksheet["F2"].value)

    def test_screenshot_zip_uses_unique_names_for_duplicate_questions(self):
        first = self.add_result(question="Duplicate question")
        second = self.add_result(question="Duplicate question")
        with patch.object(web_app, "_resolve_screenshot_path", return_value=str(self.screenshot)):
            response = self.client.get(f"/api/tasks/{self.task.id}/export-screenshots-zip")

        self.assertEqual(200, response.status_code)
        self.assertEqual("application/zip", response.content_type)
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            names = archive.namelist()
            self.assertEqual(2, len(names))
            self.assertEqual(2, len(set(names)))
            self.assertTrue(any(f"_{first.id}_" in name for name in names))
            self.assertTrue(any(f"_{second.id}_" in name for name in names))

    def test_screenshot_zip_reports_missing_files_instead_of_empty_success(self):
        self.add_result(question="Missing screenshot")
        with patch.object(web_app, "_resolve_screenshot_path", return_value=None):
            response = self.client.get(f"/api/tasks/{self.task.id}/export-screenshots-zip")

        self.assertEqual(404, response.status_code)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertIn("截图文件已丢失", payload["message"])


if __name__ == "__main__":
    unittest.main()
