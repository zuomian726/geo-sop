"""
Cloud API sync for GEO-SOP.

The local SQLite database remains the source of truth. The desktop app only
talks to one HTTPS API URL with a bearer token; MySQL credentials stay on the
server.
"""
from __future__ import annotations

import json
import os
import platform
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


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    for suffix in ("+08:00", "Z"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    text = text.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _json_text(value, default):
    if value is None:
        value = default
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _source_key(row: dict) -> tuple[str, int]:
    return (str(row.get("source_install_id") or row.get("install_id") or ""), int(row.get("source_local_id") or row.get("local_id") or 0))


def _task_cloud_source(task: MonitorTask) -> tuple[str, int] | None:
    try:
        config = json.loads(task.schedule_config or "{}")
    except Exception:
        config = {}
    install_id = str(config.get("cloud_source_install_id") or "")
    local_id = int(config.get("cloud_source_local_id") or 0)
    return (install_id, local_id) if install_id and local_id else None


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


def restore_workspace_from_cloud(user_id: int, only_if_empty: bool = True) -> dict:
    """Restore cloud mirrored history into an empty local desktop workspace."""
    if not cloud_sync_enabled():
        return {"enabled": False, "restored": False, "message": "cloud api sync is disabled"}

    user = db.session.get(User, int(user_id))
    if not user:
        raise ValueError(f"user {user_id} not found")

    local_counts = {
        "tasks": MonitorTask.query.filter_by(user_id=user.id).count(),
        "manuscripts": GeoManuscript.query.filter_by(user_id=user.id).count(),
        "sentiment_configs": SentimentConfig.query.filter_by(user_id=user.id).count(),
    }
    if only_if_empty and any(local_counts.values()):
        return {"enabled": True, "restored": False, "skipped": "local workspace is not empty", "local_counts": local_counts}

    query = urlencode({"user_key": _user_key(user)})
    response = requests.get(
        f"{cloud_sync_url()}/sync/restore/?{query}",
        headers=_headers(),
        timeout=45,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"cloud restore failed: HTTP {response.status_code} {response.text[:500]}")

    data = response.json()
    if not data.get("success"):
        raise RuntimeError(f"cloud restore failed: {data}")

    workspace = data.get("workspace") or {}
    tasks = workspace.get("tasks") if isinstance(workspace.get("tasks"), list) else []
    results = workspace.get("results") if isinstance(workspace.get("results"), list) else []
    manuscripts = workspace.get("manuscripts") if isinstance(workspace.get("manuscripts"), list) else []
    configs = workspace.get("sentiment_configs") if isinstance(workspace.get("sentiment_configs"), list) else []

    if not any([tasks, results, manuscripts, configs]):
        return {"enabled": True, "restored": False, "cloud_counts": data.get("counts") or {}}

    task_map: dict[tuple[str, int], int] = {}
    config_map: dict[tuple[str, int], int] = {}
    restored_counts = {"tasks": 0, "results": 0, "manuscripts": 0, "sentiment_configs": 0}

    for row in configs:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        source = _source_key(row)
        if not source[0] or not source[1]:
            continue
        existing = SentimentConfig.query.filter_by(user_id=user.id, name=payload.get("name") or "默认配置").first()
        if existing:
            config_map[source] = existing.id
            continue
        config = SentimentConfig(
            user_id=user.id,
            name=payload.get("name") or "默认配置",
            positive_words=_json_text(payload.get("positive_words"), []),
            negative_words=_json_text(payload.get("negative_words"), []),
            enable_ai_sentiment=bool(payload.get("enable_ai_sentiment")),
            ai_platform=payload.get("ai_platform"),
            ai_api_url=payload.get("ai_api_url"),
            ai_api_key=payload.get("ai_api_key"),
            ai_model_name=payload.get("ai_model_name"),
            ai_prompt=payload.get("ai_prompt"),
            is_default=bool(payload.get("is_default")),
            created_at=_parse_dt(payload.get("created_at")) or datetime.now(),
            updated_at=_parse_dt(payload.get("updated_at")) or datetime.now(),
        )
        db.session.add(config)
        db.session.flush()
        config_map[source] = config.id
        restored_counts["sentiment_configs"] += 1

    for row in tasks:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        source = _source_key(row)
        if not source[0] or not source[1]:
            continue
        existing = None
        for task in MonitorTask.query.filter_by(user_id=user.id).all():
            if _task_cloud_source(task) == source:
                existing = task
                break
        if existing:
            task_map[source] = existing.id
            continue
        schedule_config = payload.get("schedule_config") if isinstance(payload.get("schedule_config"), dict) else {}
        schedule_config["cloud_source_install_id"] = source[0]
        schedule_config["cloud_source_local_id"] = source[1]
        old_config_id = payload.get("sentiment_config_id")
        mapped_config_id = None
        if old_config_id:
            mapped_config_id = config_map.get((source[0], int(old_config_id)))
        task = MonitorTask(
            user_id=user.id,
            name=payload.get("name") or f"恢复任务 {source[1]}",
            brand_name=payload.get("brand_name"),
            brand_keywords=_json_text(payload.get("brand_keywords"), []),
            competitor_brands=_json_text(payload.get("competitor_brands"), []),
            questions=_json_text(payload.get("questions"), []),
            platforms=_json_text(payload.get("platforms"), []),
            screenshot_config=_json_text(payload.get("screenshot_config"), {}),
            collection_interval=int(payload.get("collection_interval") or 20),
            max_parallel_platforms=int(payload.get("max_parallel_platforms") or 3),
            schedule_type=payload.get("schedule_type") or "manual",
            schedule_config=json.dumps(schedule_config, ensure_ascii=False),
            schedule_enabled=bool(payload.get("schedule_enabled")),
            sentiment_config_id=mapped_config_id,
            status=payload.get("status") or "completed",
            last_run_at=_parse_dt(payload.get("last_run_at")),
            created_at=_parse_dt(payload.get("created_at")) or datetime.now(),
            updated_at=_parse_dt(payload.get("updated_at")) or datetime.now(),
        )
        db.session.add(task)
        db.session.flush()
        task_map[source] = task.id
        restored_counts["tasks"] += 1

    for row in results:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        task_source = (str(row.get("source_install_id") or row.get("install_id") or ""), int(row.get("source_task_local_id") or payload.get("local_task_id") or payload.get("task_id") or 0))
        local_task_id = task_map.get(task_source)
        if not local_task_id:
            continue
        result = CollectionResult(
            task_id=local_task_id,
            question=payload.get("question") or "",
            platform=payload.get("platform") or "",
            answer=payload.get("answer"),
            references=_json_text(payload.get("references"), []),
            screenshot_path=payload.get("screenshot_path"),
            has_brand_exposure=bool(payload.get("has_brand_exposure")),
            exposed_keywords=_json_text(payload.get("exposed_keywords"), []),
            ai_sentiment_result=_json_text(payload.get("ai_sentiment_result"), None) if payload.get("ai_sentiment_result") is not None else None,
            ai_sentiment_updated_at=_parse_dt(payload.get("ai_sentiment_updated_at")),
            rankings=_json_text(payload.get("rankings"), []),
            created_at=_parse_dt(payload.get("created_at")) or datetime.now(),
        )
        db.session.add(result)
        restored_counts["results"] += 1

    for row in manuscripts:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        source_install = str(row.get("source_install_id") or row.get("install_id") or "")
        mapped_task_id = None
        if payload.get("task_id"):
            mapped_task_id = task_map.get((source_install, int(payload.get("task_id"))))
        mapped_task_ids = []
        for task_id in payload.get("task_ids") or []:
            mapped = task_map.get((source_install, int(task_id)))
            if mapped:
                mapped_task_ids.append(mapped)
        manuscript = GeoManuscript(
            user_id=user.id,
            task_id=mapped_task_id,
            task_ids=json.dumps(mapped_task_ids, ensure_ascii=False),
            title=payload.get("title") or "恢复稿件",
            url=payload.get("url") or "",
            created_at=_parse_dt(payload.get("created_at")) or datetime.now(),
        )
        db.session.add(manuscript)
        restored_counts["manuscripts"] += 1

    db.session.commit()
    return {"enabled": True, "restored": True, "counts": restored_counts, "cloud_counts": data.get("counts") or {}}


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
    return str(remote_task_id_for_task(task) or "") == str(remote_task_id)


def remote_task_id_for_task(task: MonitorTask) -> int | None:
    try:
        config = json.loads(task.schedule_config or "{}")
    except Exception:
        config = {}
    try:
        remote_id = int(config.get("remote_task_id") or 0)
    except Exception:
        remote_id = 0
    return remote_id or None


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

    if created or skipped:
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


def report_client_heartbeat(user_id: int, status: str = "online", message: str = "") -> dict:
    if not cloud_sync_enabled():
        return {"enabled": False, "message": "cloud api sync is disabled"}

    user = db.session.get(User, int(user_id))
    if not user:
        raise ValueError(f"user {user_id} not found")

    payload = {
        "install_id": get_install_id(),
        "user_key": _user_key(user),
        "status": status,
        "message": message,
        "desktop": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
    }
    response = requests.post(
        f"{cloud_sync_url()}/remote-tasks/heartbeat/",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_headers(),
        timeout=20,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"remote heartbeat failed: HTTP {response.status_code} {response.text[:500]}")
    return response.json()


def report_remote_task_status(
    user_id: int,
    remote_task_id: int,
    local_task_id: int | None,
    status: str,
    message: str = "",
    extra: dict | None = None,
) -> dict:
    if not cloud_sync_enabled():
        return {"enabled": False, "message": "cloud api sync is disabled"}

    user = db.session.get(User, int(user_id))
    if not user:
        raise ValueError(f"user {user_id} not found")

    payload = {
        "install_id": get_install_id(),
        "user_key": _user_key(user),
        "remote_task_id": int(remote_task_id),
        "local_task_id": int(local_task_id) if local_task_id else None,
        "status": status,
        "message": message,
        "extra": extra or {},
    }
    response = requests.post(
        f"{cloud_sync_url()}/remote-tasks/status/",
        data=json.dumps(payload, ensure_ascii=False, default=_dt).encode("utf-8"),
        headers=_headers(),
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"remote task status failed: HTTP {response.status_code} {response.text[:500]}")
    return response.json()
