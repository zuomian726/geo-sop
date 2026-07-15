#!/usr/bin/env python3
"""Exercise the public GEO-SOP site and its read-only Demo workspace."""

from __future__ import annotations

import http.cookiejar
import json
import sys
import uuid
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


def request(opener, url: str, *, data: dict | None = None, headers: dict | None = None):
    body = urlencode(data or {}, doseq=True).encode() if data is not None else None
    req = Request(url, data=body, headers=headers or {})
    with opener.open(req, timeout=30) as response:
        return response.status, response.headers, response.read()


def json_request(opener, url: str):
    status, _, body = request(opener, url, headers={"Accept": "application/json"})
    payload = json.loads(body.decode("utf-8"))
    if status != 200 or payload.get("success") is not True:
        raise AssertionError((status, payload))
    return payload


def main(base_url: str) -> None:
    base_url = base_url.rstrip("/")
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    expected_pages = {
        "/": b"GEO-SOP",
        "/tools/": b"GEO-SOP",
        "/demo/": b"Online Demo",
        "/login/": b"GEO-SOP",
        "/register/": b"GEO-SOP",
    }
    for path, marker in expected_pages.items():
        status, _, body = request(opener, base_url + path)
        if status != 200 or marker not in body:
            raise AssertionError(f"public page failed: {path} status={status}")

    status, _, body = request(opener, base_url + "/update.json")
    manifest = json.loads(body.decode("utf-8"))
    if status != 200 or set(manifest.get("downloads", {})) != {"macos", "macos_intel", "windows"}:
        raise AssertionError("release manifest does not contain all desktop platforms")

    status, _, body = request(
        opener,
        base_url + "/login/?demo=1",
        data={"demo_login": "1"},
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    login = json.loads(body.decode("utf-8"))
    if status != 200 or login.get("success") is not True:
        raise AssertionError("One-click Demo login failed")

    status, _, dashboard = request(opener, base_url + "/dashboard/")
    if status != 200 or "在线 Demo 只读模式".encode("utf-8") not in dashboard:
        raise AssertionError("Demo dashboard did not enter read-only mode")

    overview = json_request(opener, base_url + "/api/dashboard/?action=overview")
    metrics = overview.get("metrics") or {}
    expected_metrics = {"tasks": 6, "results": 144, "platforms": 6}
    if any(int(metrics.get(key, -1)) != value for key, value in expected_metrics.items()):
        raise AssertionError(("unexpected Demo metrics", metrics))

    for action in ("references", "reference_analysis", "reference_domains", "reference_trends", "geo_coverage"):
        json_request(opener, base_url + f"/api/dashboard/?action={action}&limit=20")

    before = json_request(opener, base_url + "/api/dashboard/?action=remote_status")
    marker = "smoke-read-only-" + uuid.uuid4().hex
    status, _, body = request(
        opener,
        base_url + "/dashboard/",
        data={
            "name": marker,
            "brand_name": "Demo",
            "brand_keywords": "Demo",
            "questions": "This task must not be created",
            "platforms[]": "doubao",
        },
    )
    if status != 200 or "不能创建或修改任务".encode("utf-8") not in body:
        raise AssertionError("Demo task submission was not visibly blocked")
    after = json_request(opener, base_url + "/api/dashboard/?action=remote_status")
    if len(after.get("tasks") or []) != len(before.get("tasks") or []):
        raise AssertionError("Demo read-only check changed the remote task count")
    if marker.encode() in body:
        raise AssertionError("Demo task marker leaked into the dashboard")

    status, headers, export = request(opener, base_url + "/api/dashboard/?action=export_geo")
    if status != 200 or not export.startswith(b"PK") or len(export) < 1000:
        raise AssertionError("Demo GEO export is not a valid XLSX payload")
    if "spreadsheet" not in headers.get("Content-Type", ""):
        raise AssertionError("Demo GEO export has an unexpected content type")

    print(
        f"Cloud smoke test passed: release={manifest['version']} "
        f"tasks={metrics['tasks']} results={metrics['results']} platforms={metrics['platforms']}"
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "https://geo.allgood.cn")
