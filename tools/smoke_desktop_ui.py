#!/usr/bin/env python3
"""Render the desktop workspace at release viewports and check critical UI states."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "web_app"
DATA_DIR = Path(tempfile.mkdtemp(prefix="geo-sop-ui-smoke-"))
os.environ.update(
    {
        "GEO_DESKTOP_MODE": "1",
        "GEO_REQUIRE_LOGIN": "0",
        "GEO_CLOUD_SYNC_ENABLED": "0",
        "GEO_DATA_DIR": str(DATA_DIR),
        "NODE_NO_WARNINGS": "1",
    }
)
for path in (str(ROOT), str(WEB_APP)):
    if path not in sys.path:
        sys.path.insert(0, path)

from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

from app import app  # noqa: E402
from models import MonitorTask, User, db  # noqa: E402


def seed_workspace() -> None:
    with app.app_context():
        db.create_all()
        user = User.query.filter_by(username="local").first()
        if not user:
            user = User(username="local", email="local@geo-sop.local")
            user.set_password("ui-smoke-only")
            db.session.add(user)
            db.session.flush()
        summary = {
            "expected": 4,
            "succeeded": 3,
            "failed": 1,
            "platforms": [
                {
                    "platform": "doubao",
                    "expected": 4,
                    "succeeded": 3,
                    "failed": 1,
                    "errors": [{"question": "测试问题", "message": "登录状态已失效"}],
                }
            ],
            "finished_at": "2026-07-16T16:00:00+08:00",
        }
        task = MonitorTask(
            user_id=user.id,
            name="V1.0 采集可靠性检查",
            brand_name="GEO-SOP",
            brand_keywords=json.dumps(["GEO-SOP"], ensure_ascii=False),
            competitor_brands="[]",
            questions=json.dumps(["测试问题"], ensure_ascii=False),
            platforms=json.dumps(["doubao"], ensure_ascii=False),
            screenshot_config=json.dumps({"doubao": True}),
            schedule_config=json.dumps({"last_run_summary": summary}, ensure_ascii=False),
            status="partial",
        )
        db.session.add(task)
        db.session.commit()


def run() -> None:
    seed_workspace()
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/dashboard"
    login_url = f"http://127.0.0.1:{server.server_port}/login"
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    screenshots = []
    try:
        with sync_playwright() as playwright:
            launch = {"headless": True}
            if chrome.exists():
                launch["executable_path"] = str(chrome)
            browser = playwright.chromium.launch(**launch)
            try:
                app.config["REQUIRE_LOGIN"] = True
                for width, height in ((1000, 700), (1440, 900)):
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.set_default_timeout(15_000)
                    errors = []
                    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                    page.goto(login_url, wait_until="domcontentloaded", timeout=30_000)
                    page.locator(".login-title", has_text="登录 GEO-SOP").wait_for(state="visible")
                    page.locator('input[autocomplete="username"]').wait_for(state="visible")
                    page.locator('input[autocomplete="current-password"]').wait_for(state="visible")
                    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                    assert overflow <= 1, f"login horizontal overflow at {width}x{height}: {overflow}px"
                    screenshot = Path(tempfile.gettempdir()) / f"geo-sop-v1-login-{width}x{height}.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                    screenshots.append(str(screenshot))
                    assert not errors, f"login console errors at {width}x{height}: {errors}"
                    page.close()

                app.config["REQUIRE_LOGIN"] = False
                for width, height in ((1000, 700), (1440, 900)):
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.set_default_timeout(15_000)
                    errors = []
                    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    page.locator(".el-tabs__item", has_text="任务管理").click()
                    warning = page.locator(".task-run-warning")
                    warning.wait_for(state="visible")
                    assert "本次成功 3 / 4 条" in warning.inner_text()
                    assert "登录状态已失效" in warning.inner_text()
                    status = page.locator(".task-card .el-tag").first
                    status.wait_for(state="visible")
                    assert "部分完成" in status.inner_text()
                    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                    assert overflow <= 1, f"horizontal overflow at {width}x{height}: {overflow}px"
                    screenshot = Path(tempfile.gettempdir()) / f"geo-sop-v1-dashboard-{width}x{height}.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                    screenshots.append(str(screenshot))
                    assert not errors, f"browser console errors at {width}x{height}: {errors}"
                    page.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        shutil.rmtree(DATA_DIR, ignore_errors=True)

    print(json.dumps({"success": True, "screenshots": screenshots}, ensure_ascii=False))


if __name__ == "__main__":
    run()
