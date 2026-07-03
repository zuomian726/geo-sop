"""
Cloud API sync for GEO-SOP.

The local SQLite database remains the source of truth. The desktop app only
talks to one HTTPS API URL with a bearer token; MySQL credentials stay on the
server.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import requests

from local_paths import app_data_dir
from models import CollectionResult, GeoManuscript, MonitorTask, SentimentConfig, User, db


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def cloud_account_path() -> Path:
    return Path(app_data_dir()) / "cloud_account.json"


def load_cloud_account() -> dict:
    path = cloud_account_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cloud_account(data: dict) -> None:
    path = cloud_account_path()
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def cloud_sync_url() -> str | None:
    account = load_cloud_account()
    url = account.get("cloud_sync_url") or os.environ.get("GEO_CLOUD_SYNC_URL") or os.environ.get("CLOUD_SYNC_URL")
    return url.rstrip("/") if url else None


def cloud_sync_token() -> str | None:
    account = load_cloud_account()
    return account.get("token") or os.environ.get("GEO_CLOUD_SYNC_TOKEN") or os.environ.get("CLOUD_SYNC_TOKEN")


def cloud_sync_enabled() -> bool:
    account = load_cloud_account()
    saved_account_enabled = bool(account.get("cloud_sync_url") and account.get("token"))
    env_enabled = _truthy(os.environ.get("GEO_CLOUD_SYNC_ENABLED"))
    return (saved_account_enabled or env_enabled) and bool(cloud_sync_url()) and bool(cloud_sync_token())


def should_sync_keys() -> bool:
    return _truthy(os.environ.get("GEO_CLOUD_SYNC_KEYS"))


def get_install_id() -> str:
    path = Path(app_data_dir()) / "cloud_install_id"
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    new_id = uuid.uuid4().hex
    path.write_text(new_id, encoding="utf-8")
    return new_id


def _dt(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def _user_key(user: User) -> str:
    return (user.email or user.username or f"user-{user.id}").strip().lower()


def _with_local_id(payload: dict) -> dict:
    payload = dict(payload)
    payload["local_id"] = payload.get("id")
    return payload


def _config_payload(config: SentimentConfig) -> dict:
    payload = _with_local_id(config.to_dict())
    if not should_sync_keys():
        payload["ai_api_key"] = None
    return payload


def build_workspace_payload(user_id: int) -> dict:
    user = db.session.get(User, int(user_id))
    if not user:
        raise ValueError(f"user {user_id} not found")

    tasks = MonitorTask.query.filter_by(user_id=user.id).order_by(MonitorTask.id.asc()).all()
    task_ids = [int(task.id) for task in tasks if task.id is not None]
    results = (
        CollectionResult.query.filter(CollectionResult.task_id.in_(task_ids)).order_by(CollectionResult.id.asc()).all()
        if task_ids
        else []
    )
    manuscripts = GeoManuscript.query.filter_by(user_id=user.id).order_by(GeoManuscript.id.asc()).all()
    configs = SentimentConfig.query.filter_by(user_id=user.id).order_by(SentimentConfig.id.asc()).all()

    user_payload = _with_local_id(user.to_dict())
    return {
        "schema_version": 1,
        "install_id": get_install_id(),
        "user_key": _user_key(user),
        "synced_from": "geo-sop-desktop",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": user_payload,
        "tasks": [_with_local_id(task.to_dict()) for task in tasks],
        "results": [
            {
                **_with_local_id(result.to_dict()),
                "local_task_id": result.task_id,
            }
            for result in results
        ],
        "manuscripts": [_with_local_id(manuscript.to_dict()) for manuscript in manuscripts],
        "sentiment_configs": [_config_payload(config) for config in configs],
    }


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {cloud_sync_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "GEO-SOP-Desktop-Sync/1.0",
    }


def sync_user_workspace(user_id: int) -> dict:
    if not cloud_sync_enabled():
        return {"enabled": False, "message": "cloud api sync is disabled"}

    payload = build_workspace_payload(user_id)
    response = requests.post(
        f"{cloud_sync_url()}/sync/",
        data=json.dumps(payload, ensure_ascii=False, default=_dt).encode("utf-8"),
        headers=_headers(),
        timeout=45,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"cloud sync failed: HTTP {response.status_code} {response.text[:500]}")

    data = response.json()
    if not data.get("success"):
        raise RuntimeError(f"cloud sync failed: {data}")
    data["enabled"] = True
    return data


def sync_status(user_id: int | None = None) -> dict:
    status = {
        "enabled": cloud_sync_enabled(),
        "api_configured": bool(cloud_sync_url()),
        "token_configured": bool(cloud_sync_token()),
        "install_id": get_install_id(),
        "sync_keys": should_sync_keys(),
    }
    if not cloud_sync_enabled() or not user_id:
        return status

    user = db.session.get(User, int(user_id))
    if not user:
        return status

    query = urlencode({"install_id": get_install_id(), "user_key": _user_key(user)})
    response = requests.get(
        f"{cloud_sync_url()}/sync/status/?{query}",
        headers=_headers(),
        timeout=20,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"cloud sync status failed: HTTP {response.status_code} {response.text[:500]}")

    data = response.json()
    if data.get("success") and isinstance(data.get("cloud_sync"), dict):
        status.update(data["cloud_sync"])
    return status


def _task_has_remote_id(task: MonitorTask, remote_task_id: int) -> bool:
    try:
        config = json.loads(task.schedule_config or "{}")
    except Exception:
        config = {}
    return str(config.get("remote_task_id")) == str(remote_task_id)


def pull_remote_tasks(user_id: int) -> dict:
    """Pull server-created tasks and create local pending tasks."""
    if not cloud_sync_enabled():
        return {"enabled": False, "message": "cloud api sync is disabled"}

    user = db.session.get(User, int(user_id))
    if not user:
        raise ValueError(f"user {user_id} not found")

    query = urlencode({"install_id": get_install_id(), "user_key": _user_key(user)})
    response = requests.get(
        f"{cloud_sync_url()}/remote-tasks/?{query}",
        headers=_headers(),
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"pull remote tasks failed: HTTP {response.status_code} {response.text[:500]}")

    data = response.json()
    if not data.get("success"):
        raise RuntimeError(f"pull remote tasks failed: {data}")

    created = []
    skipped = []
    existing_tasks = MonitorTask.query.filter_by(user_id=user.id).all()
    for item in data.get("tasks", []):
        remote_id = int(item.get("id") or 0)
        payload = item.get("payload") or {}
        if not remote_id or not isinstance(payload, dict):
            skipped.append({"remote_task_id": remote_id, "reason": "invalid payload"})
            continue
        if any(_task_has_remote_id(task, remote_id) for task in existing_tasks):
            skipped.append({"remote_task_id": remote_id, "reason": "already imported"})
            continue

        questions = payload.get("questions") or []
        platforms = payload.get("platforms") or []
        brand_keywords = payload.get("brand_keywords") or []
        if not questions or not platforms or not brand_keywords:
            skipped.append({"remote_task_id": remote_id, "reason": "missing required fields"})
            continue

        schedule_config = payload.get("schedule_config") if isinstance(payload.get("schedule_config"), dict) else {}
        schedule_config["remote_task_id"] = remote_id
        schedule_config["remote_created_at"] = item.get("created_at")

        task = MonitorTask(
            user_id=user.id,
            name=payload.get("name") or item.get("name") or f"远程任务 {remote_id}",
            brand_name=payload.get("brand_name", ""),
            brand_keywords=json.dumps(brand_keywords, ensure_ascii=False),
            competitor_brands=json.dumps(payload.get("competitor_brands", []), ensure_ascii=False),
            questions=json.dumps(questions, ensure_ascii=False),
            platforms=json.dumps(platforms, ensure_ascii=False),
            screenshot_config=json.dumps(payload.get("screenshot_config", {}), ensure_ascii=False),
            collection_interval=int(payload.get("collection_interval") or 20),
            max_parallel_platforms=int(payload.get("max_parallel_platforms") or 3),
            schedule_type=payload.get("schedule_type", "manual"),
            schedule_config=json.dumps(schedule_config, ensure_ascii=False),
            schedule_enabled=False,
            status="pending",
        )
        db.session.add(task)
        db.session.flush()
        existing_tasks.append(task)
        created.append({"remote_task_id": remote_id, "local_task_id": task.id, "name": task.name})

    db.session.commit()

    if created:
        ack_payload = {
            "install_id": get_install_id(),
            "user_key": _user_key(user),
            "imported": created,
            "skipped": skipped,
        }
        ack_response = requests.post(
            f"{cloud_sync_url()}/remote-tasks/ack/",
            data=json.dumps(ack_payload, ensure_ascii=False).encode("utf-8"),
            headers=_headers(),
            timeout=30,
        )
        if ack_response.status_code >= 400:
            raise RuntimeError(f"remote task ack failed: HTTP {ack_response.status_code} {ack_response.text[:500]}")

    return {
        "enabled": True,
        "created": created,
        "skipped": skipped,
        "available": len(data.get("tasks", [])),
    }
