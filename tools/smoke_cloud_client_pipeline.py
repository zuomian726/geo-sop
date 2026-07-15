#!/usr/bin/env python3
"""Exercise the production desktop/cloud contract with disposable accounts."""

from __future__ import annotations

import argparse
import io
import json
import secrets
import shlex
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from urllib.parse import urljoin

import requests


PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415408d763f8ffff3f0005fe02fea73581650000000049454e44ae426082"
)

CLEANUP_PHP = r"""<?php
declare(strict_types=1);
require 'api/common.php';
$username = trim((string)getenv('GEO_ACCEPTANCE_USER'));
if (!preg_match('/^geo_e2e_[a-f0-9]{10}$/', $username)) {
    fwrite(STDERR, "refusing to clean a non-acceptance account\n");
    exit(2);
}
$pdo = geo_pdo();
$stmt = $pdo->prepare('SELECT id FROM geo_cloud_users WHERE username=? LIMIT 1');
$stmt->execute([$username]);
$userId = (int)($stmt->fetchColumn() ?: 0);
if ($userId <= 0) {
    echo "already-clean\n";
    exit(0);
}
$paths = [];
if ((int)$pdo->query("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='geo_sync_assets'")->fetchColumn() > 0) {
    $assetStmt = $pdo->prepare('SELECT storage_path FROM geo_sync_assets WHERE cloud_user_id=?');
    $assetStmt->execute([$userId]);
    $paths = array_values(array_filter(array_map('strval', $assetStmt->fetchAll(PDO::FETCH_COLUMN) ?: [])));
}
$tables = [
    'geo_sync_assets', 'geo_sync_stats_snapshots', 'geo_sync_results',
    'geo_sync_manuscripts', 'geo_sync_sentiment_configs', 'geo_sync_tasks',
    'geo_sync_users', 'geo_sync_runs', 'geo_desktop_clients', 'geo_remote_tasks',
    'geo_cloud_tokens',
];
$pdo->beginTransaction();
try {
    foreach ($tables as $table) {
        $exists = $pdo->prepare('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=?');
        $exists->execute([$table]);
        if ((int)$exists->fetchColumn() <= 0) continue;
        $delete = $pdo->prepare("DELETE FROM {$table} WHERE cloud_user_id=?");
        $delete->execute([$userId]);
    }
    $pdo->prepare('DELETE FROM geo_cloud_users WHERE id=?')->execute([$userId]);
    $pdo->commit();
} catch (Throwable $e) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    throw $e;
}
$storageRoot = realpath(geo_storage_path('cloud-assets')) ?: geo_storage_path('cloud-assets');
foreach ($paths as $path) {
    $real = realpath($path);
    if ($real && strpos($real, rtrim($storageRoot, '/') . '/') === 0) @unlink($real);
}
echo "cleaned\n";
"""


class AcceptanceError(RuntimeError):
    pass


def endpoint(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def expect_json(response: requests.Response, expected: int = 200) -> dict:
    try:
        payload = response.json()
    except Exception as exc:
        raise AcceptanceError(f"{response.request.method} {response.url}: invalid JSON HTTP {response.status_code}") from exc
    if response.status_code != expected:
        raise AcceptanceError(
            f"{response.request.method} {response.url}: expected HTTP {expected}, got {response.status_code}: "
            f"{str(payload)[:300]}"
        )
    return payload


def register_and_login(base_url: str, username: str, password: str) -> tuple[requests.Session, dict]:
    session = requests.Session()
    response = session.post(
        endpoint(base_url, "/register/"),
        data={"username": username, "password": password},
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
        timeout=(5, 20),
    )
    registration = expect_json(response)
    if not registration.get("success"):
        raise AcceptanceError(f"registration failed: {registration}")

    response = session.post(
        endpoint(base_url, "/api/auth/login/"),
        json={"account": username, "password": password, "device_name": "GEO-SOP production acceptance"},
        timeout=(5, 20),
    )
    login = expect_json(response)
    if not login.get("success") or not login.get("token"):
        raise AcceptanceError(f"desktop login failed: {login}")
    return session, login


def cleanup_account(ssh_host: str, server_root: str, username: str) -> None:
    remote = f"cd {shlex.quote(server_root)} && GEO_ACCEPTANCE_USER={shlex.quote(username)} php"
    result = subprocess.run(
        ["ssh", ssh_host, remote],
        input=CLEANUP_PHP,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise AcceptanceError(f"cleanup failed for {username}: {(result.stderr or result.stdout).strip()[:300]}")


def run_pipeline(base_url: str, ssh_host: str, server_root: str, keep: bool = False) -> None:
    suffix = secrets.token_hex(5)
    usernames = [f"geo_e2e_{suffix}", f"geo_e2e_{secrets.token_hex(5)}"]
    password = secrets.token_urlsafe(24)
    created: list[str] = []
    started = time.monotonic()
    install_id = f"acceptance-{suffix}"
    user_key = f"{usernames[0]}@geo.allgood.cn"
    headers: dict[str, str] = {}

    try:
        _session_a, login_a = register_and_login(base_url, usernames[0], password)
        created.append(usernames[0])
        _session_b, login_b = register_and_login(base_url, usernames[1], password)
        created.append(usernames[1])
        headers = {"Authorization": f"Bearer {login_a['token']}"}
        headers_b = {"Authorization": f"Bearer {login_b['token']}"}
        print("[1/8] disposable registration and desktop login passed")

        heartbeat = expect_json(
            requests.post(
                endpoint(base_url, "/api/remote-tasks/heartbeat/"),
                headers=headers,
                json={
                    "install_id": install_id,
                    "user_key": user_key,
                    "status": "online",
                    "message": "production acceptance client online",
                    "desktop": {"app_version": "0.3.38-dev", "platform": "acceptance", "python": sys.version.split()[0]},
                    "runtime": {
                        "worker_state": "ready",
                        "running_tasks": 0,
                        "pending_remote_tasks": 0,
                        "sync_backlog": 0,
                        "poll_seconds": 10,
                    },
                },
                timeout=(5, 10),
            )
        )
        if not heartbeat.get("success"):
            raise AcceptanceError(f"heartbeat failed: {heartbeat}")
        print("[2/8] authenticated client heartbeat passed")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        article_url = f"https://example.com/geo-sop-acceptance-{suffix}"
        workspace = {
            "install_id": install_id,
            "user_key": user_key,
            "sync_mode": "merge",
            "prune_install": False,
            "user": {"id": 1, "username": usernames[0], "email": user_key, "created_at": now},
            "tasks": [
                {
                    "local_id": 101,
                    "name": "GEO-SOP acceptance task",
                    "brand_name": "GEO-SOP Acceptance",
                    "brand_keywords": ["GEO-SOP Acceptance"],
                    "competitor_brands": [],
                    "questions": ["How visible is the acceptance brand?"],
                    "platforms": ["doubao"],
                    "status": "completed",
                    "created_at": now,
                    "updated_at": now,
                }
            ],
            "results": [
                {
                    "local_id": 201,
                    "local_task_id": 101,
                    "task_id": 101,
                    "platform": "doubao",
                    "question": "How visible is the acceptance brand?",
                    "answer": "GEO-SOP Acceptance is visible in this synthetic production acceptance answer.",
                    "has_brand_exposure": True,
                    "exposed_keywords": ["GEO-SOP Acceptance"],
                    "references": [{"title": "Acceptance article", "url": article_url}],
                    "created_at": now,
                }
            ],
            "manuscripts": [
                {
                    "local_id": 301,
                    "task_id": 101,
                    "task_ids": [101],
                    "title": "GEO-SOP acceptance article",
                    "url": article_url,
                    "created_at": now,
                }
            ],
            "sentiment_configs": [
                {
                    "local_id": 401,
                    "name": "Acceptance sentiment",
                    "positive_words": ["visible"],
                    "negative_words": ["missing"],
                    "is_default": True,
                    "ai_api_key": None,
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        }
        synced = expect_json(
            requests.post(endpoint(base_url, "/api/sync/"), headers=headers, json=workspace, timeout=(5, 30))
        )
        if synced.get("counts") != {"users": 1, "tasks": 1, "results": 1, "manuscripts": 1, "sentiment_configs": 1}:
            raise AcceptanceError(f"unexpected sync counts: {synced}")
        status = expect_json(
            requests.get(
                endpoint(base_url, "/api/sync/status/"),
                headers=headers,
                params={"install_id": install_id, "user_key": user_key},
                timeout=(5, 15),
            )
        )
        if status.get("cloud_sync", {}).get("last_status") != "success":
            raise AcceptanceError(f"sync status did not persist: {status}")
        restored = expect_json(
            requests.get(endpoint(base_url, "/api/sync/restore/"), headers=headers, params={"limit": 100}, timeout=(5, 20))
        )
        if restored.get("counts") != {"tasks": 1, "results": 1, "manuscripts": 1, "sentiment_configs": 1}:
            raise AcceptanceError(f"restore did not return the complete workspace: {restored.get('counts')}")
        print("[3/8] workspace upload, status and history restore passed")

        stats = expect_json(
            requests.post(
                endpoint(base_url, "/api/sync/assets/"),
                headers=headers,
                json={"kind": "stats", "payload": {"install_id": install_id, "user_key": user_key, "results": 1}},
                timeout=(5, 15),
            )
        )
        if not stats.get("success"):
            raise AcceptanceError(f"stats upload failed: {stats}")
        metadata = {
            "kind": "screenshot",
            "install_id": install_id,
            "user_key": user_key,
            "local_result_id": 201,
            "local_task_id": 101,
            "platform": "doubao",
            "question": "How visible is the acceptance brand?",
        }
        uploaded = expect_json(
            requests.post(
                endpoint(base_url, "/api/sync/assets/"),
                headers=headers,
                data={"metadata": json.dumps(metadata)},
                files={"file": ("acceptance.png", PNG_1X1, "image/png")},
                timeout=(5, 20),
            )
        )
        screenshot_url = uploaded.get("url")
        if not screenshot_url or requests.get(screenshot_url, timeout=(5, 15)).status_code != 200:
            raise AcceptanceError(f"uploaded screenshot is not publicly readable: {uploaded}")
        print("[4/8] statistics and screenshot upload passed")

        def dashboard(action: str, **params) -> dict:
            return expect_json(
                requests.get(
                    endpoint(base_url, "/api/dashboard/"),
                    headers=headers,
                    params={"action": action, **params},
                    timeout=(5, 30),
                )
            )

        overview = dashboard("overview")
        if overview.get("metrics", {}).get("results") != 1 or overview.get("metrics", {}).get("screenshots") != 1:
            raise AcceptanceError(f"dashboard metrics mismatch: {overview.get('metrics')}")
        tasks = dashboard("tasks")
        results = dashboard("results", limit=20)
        detail = dashboard("result", install_id=install_id, local_id=201)
        references = dashboard("reference_analysis")
        coverage = dashboard("geo_coverage")
        if len(tasks.get("tasks", [])) != 1 or results.get("total") != 1:
            raise AcceptanceError("dashboard task/result queries did not return synced data")
        if detail.get("result", {}).get("screenshot_url") != screenshot_url:
            raise AcceptanceError("dashboard result did not resolve its uploaded screenshot")
        if references.get("total_references") != 1 or coverage.get("cited_urls") != 1:
            raise AcceptanceError("reference and GEO manuscript analysis did not match synced data")
        print("[5/8] cloud dashboard metrics, detail and GEO analysis passed")

        remote_payload = {
            "name": "GEO-SOP remote acceptance task",
            "brand_name": "GEO-SOP Acceptance",
            "brand_keywords": ["GEO-SOP Acceptance"],
            "competitor_brands": [],
            "questions": ["Run the remote acceptance task"],
            "platforms": ["doubao"],
            "screenshot_config": {"doubao": True},
            "collection_interval": 5,
            "max_parallel_platforms": 1,
        }
        created_task = expect_json(
            requests.post(endpoint(base_url, "/api/remote-tasks/"), headers=headers, json={"payload": remote_payload}, timeout=(5, 15))
        )
        remote_id = int(created_task.get("id") or 0)
        claimed = expect_json(
            requests.get(
                endpoint(base_url, "/api/remote-tasks/"),
                headers=headers,
                params={"install_id": install_id, "user_key": user_key},
                timeout=(5, 15),
            )
        )
        if remote_id <= 0 or [item.get("id") for item in claimed.get("tasks", [])] != [remote_id]:
            raise AcceptanceError(f"remote task was not claimed by the client: {claimed}")
        expect_json(
            requests.post(
                endpoint(base_url, "/api/remote-tasks/ack/"),
                headers=headers,
                json={"install_id": install_id, "user_key": user_key, "imported": [{"remote_task_id": remote_id, "local_task_id": 901}]},
                timeout=(5, 15),
            )
        )
        for remote_status in ("queued", "running", "completed"):
            expect_json(
                requests.post(
                    endpoint(base_url, "/api/remote-tasks/status/"),
                    headers=headers,
                    json={
                        "remote_task_id": remote_id,
                        "local_task_id": 901,
                        "install_id": install_id,
                        "user_key": user_key,
                        "status": remote_status,
                        "message": f"acceptance {remote_status}",
                    },
                    timeout=(5, 15),
                )
            )
        remote_status = dashboard("remote_status")
        remote_row = next((row for row in remote_status.get("tasks", []) if row.get("id") == remote_id), None)
        if not remote_row or remote_row.get("status") != "completed" or remote_status.get("summary", {}).get("online_clients") != 1:
            raise AcceptanceError(f"remote lifecycle did not reach the cloud dashboard: {remote_status}")
        print("[6/8] cloud-created task claim, import and completion passed")

        other_detail = requests.get(
            endpoint(base_url, "/api/dashboard/"),
            headers=headers_b,
            params={"action": "result", "install_id": install_id, "local_id": 201},
            timeout=(5, 15),
        )
        expect_json(other_detail, 404)
        other_remote = requests.post(
            endpoint(base_url, "/api/remote-tasks/status/"),
            headers=headers_b,
            json={"remote_task_id": remote_id, "install_id": install_id, "status": "completed"},
            timeout=(5, 15),
        )
        expect_json(other_remote, 404)
        print("[7/8] cross-account data and command isolation passed")

        export_geo = requests.get(
            endpoint(base_url, "/api/dashboard/"), headers=headers, params={"action": "export_geo"}, timeout=(5, 60)
        )
        if export_geo.status_code != 200 or not export_geo.content.startswith(b"PK"):
            raise AcceptanceError(f"GEO export failed: HTTP {export_geo.status_code}")
        export_images = requests.get(
            endpoint(base_url, "/api/dashboard/"),
            headers=headers,
            params={"action": "export_screenshots_zip"},
            timeout=(5, 60),
        )
        if export_images.status_code != 200 or not export_images.content.startswith(b"PK"):
            raise AcceptanceError(f"screenshot export failed: HTTP {export_images.status_code}")
        with zipfile.ZipFile(io.BytesIO(export_images.content)) as archive:
            if not any(name.lower().endswith(".png") for name in archive.namelist()):
                raise AcceptanceError("screenshot ZIP does not contain the uploaded evidence image")
        print("[8/8] GEO workbook and screenshot ZIP exports passed")
    finally:
        if keep:
            if created:
                print("Acceptance accounts kept for inspection: " + ", ".join(created))
        else:
            cleanup_errors = []
            for username in reversed(created):
                try:
                    cleanup_account(ssh_host, server_root, username)
                except Exception as exc:
                    cleanup_errors.append(str(exc))
            if cleanup_errors:
                raise AcceptanceError("; ".join(cleanup_errors))

    print(f"Production desktop/cloud acceptance passed in {time.monotonic() - started:.1f}s; test data cleaned")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://geo.allgood.cn")
    parser.add_argument("--cleanup-ssh", default="server93")
    parser.add_argument("--server-root", default="/www/wwwroot/geo.allgood.cn")
    parser.add_argument("--keep", action="store_true", help="Keep disposable accounts for debugging")
    args = parser.parse_args()
    run_pipeline(args.base_url, args.cleanup_ssh, args.server_root, args.keep)


if __name__ == "__main__":
    main()
