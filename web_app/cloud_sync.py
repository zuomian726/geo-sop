"""
Cloud API sync for GEO-SOP.

The local SQLite database remains the source of truth. The desktop app only
talks to one HTTPS API URL with a bearer token; MySQL credentials stay on the
server.
"""
from __future__ import annotations

import json
import hashlib
import mimetypes
import os
import platform
import threading
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import requests

from local_paths import answers_dir, app_data_dir
from models import CollectionResult, GeoManuscript, MonitorTask, SentimentConfig, User, db, ensure_local_sync_schema
from platform_catalog import SUPPORTED_PLATFORM_IDS
from version import APP_VERSION


_cloud_merge_lock = threading.Lock()


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def cloud_account_path() -> Path:
    return Path(app_data_dir()) / "cloud_account.json"


def cloud_pull_state_path() -> Path:
    return Path(app_data_dir()) / "cloud_pull_state.json"


def load_cloud_account() -> dict:
    path = cloud_account_path()
    if not path.exists():
        return {}
    try:
        try:
            path.chmod(0o600)
        except OSError:
            pass
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cloud_account(data: dict) -> None:
    path = cloud_account_path()
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        tmp_path.chmod(0o600)
    except OSError:
        pass
    tmp_path.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def clear_cloud_account() -> None:
    """Remove the desktop cloud token while preserving local workspace data."""
    try:
        cloud_account_path().unlink(missing_ok=True)
    except TypeError:
        path = cloud_account_path()
        if path.exists():
            path.unlink()
    os.environ.pop("GEO_CLOUD_SYNC_TOKEN", None)
    os.environ.pop("CLOUD_SYNC_TOKEN", None)
    os.environ["GEO_CLOUD_SYNC_ENABLED"] = "0"


def _load_cloud_pull_state() -> dict:
    path = cloud_pull_state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cloud_pull_cursor(user_key: str, cursor: int, cursor_time: str = "") -> None:
    state = _load_cloud_pull_state()
    state[user_key] = {
        "result_cursor": max(0, int(cursor)),
        "result_cursor_time": str(cursor_time or ""),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    path = cloud_pull_state_path()
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _cloud_pull_cursor(user_key: str) -> tuple[int, str]:
    row = _load_cloud_pull_state().get(user_key) or {}
    try:
        return max(0, int(row.get("result_cursor") or 0)), str(row.get("result_cursor_time") or "")
    except Exception:
        return 0, ""


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


def _model_cloud_source(model) -> tuple[str, int] | None:
    install_id = str(getattr(model, "cloud_source_install_id", None) or "")
    local_id = int(getattr(model, "cloud_source_local_id", None) or 0)
    return (install_id, local_id) if install_id and local_id else None


def _normalized_datetime(value) -> str:
    parsed = _parse_dt(value)
    return parsed.strftime("%Y-%m-%d %H:%M:%S") if parsed else str(value or "").strip()


def _task_fingerprint(name, created_at) -> str:
    return f"{str(name or '').strip().casefold()}|{_normalized_datetime(created_at)}"


def _result_fingerprint(task_id, question, platform_name, created_at, answer) -> str:
    raw = "|".join([
        str(int(task_id or 0)),
        str(platform_name or "").strip().casefold(),
        str(question or "").strip(),
        _normalized_datetime(created_at),
        str(answer or "").strip(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _manuscript_fingerprint(title, url) -> str:
    raw = f"{str(title or '').strip().casefold()}|{str(url or '').strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _user_key(user: User) -> str:
    return (user.email or user.username or f"user-{user.id}").strip().lower()


def _with_local_id(payload: dict) -> dict:
    payload = dict(payload)
    payload["local_id"] = payload.get("id")
    return payload


def _config_payload(config: SentimentConfig) -> dict:
    payload = _with_local_id(config.to_dict())
    source = _model_cloud_source(config)
    if source:
        payload["_sync_install_id"] = source[0]
        payload["_sync_local_id"] = source[1]
    if not should_sync_keys():
        payload["ai_api_key"] = None
    return payload


def build_workspace_payload(user_id: int) -> dict:
    user = db.session.get(User, int(user_id))
    if not user:
        raise ValueError(f"user {user_id} not found")

    tasks = MonitorTask.query.filter_by(user_id=user.id).order_by(MonitorTask.id.asc()).all()
    task_ids = [int(task.id) for task in tasks if task.id is not None]
    all_results = (
        CollectionResult.query.filter(CollectionResult.task_id.in_(task_ids)).order_by(CollectionResult.id.asc()).all()
        if task_ids
        else []
    )
    # Cloud-imported rows already exist remotely. Re-uploading them under this
    # device's install_id creates cross-device duplicates.
    results = [result for result in all_results if not _model_cloud_source(result)]
    manuscripts = [
        manuscript for manuscript in GeoManuscript.query.filter_by(user_id=user.id).order_by(GeoManuscript.id.asc()).all()
        if not _model_cloud_source(manuscript)
    ]
    configs = SentimentConfig.query.filter_by(user_id=user.id).order_by(SentimentConfig.id.asc()).all()

    user_payload = _with_local_id(user.to_dict())
    return {
        "schema_version": 1,
        "sync_mode": "merge",
        "prune_install": False,
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


def resolve_local_screenshot_path(filepath: str | None) -> str | None:
    if not filepath:
        return None
    raw_path = str(filepath).replace("\\", "/")
    normalized = raw_path.lstrip("/")
    without_answers = normalized[len("answers/"):] if normalized.startswith("answers/") else normalized
    web_app_dir = Path(__file__).resolve().parent
    root_dir = web_app_dir.parent
    local_answers_dir = Path(answers_dir()).resolve()
    candidates = [
        Path(raw_path) if Path(raw_path).is_absolute() else None,
        Path(normalized),
        local_answers_dir / normalized,
        local_answers_dir / without_answers,
        web_app_dir / normalized,
        root_dir / normalized,
        web_app_dir / "answers" / without_answers,
        root_dir / "answers" / without_answers,
    ]
    allowed_roots = [local_answers_dir, (web_app_dir / "answers").resolve(), (root_dir / "answers").resolve()]
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            resolved = candidate.resolve()
            if resolved.is_file() and any(resolved == root or root in resolved.parents for root in allowed_roots):
                return str(resolved)
        except OSError:
            continue
    return None


def upload_workspace_assets(user_id: int, resolve_path=None, task_ids: list[int] | None = None) -> dict:
    """Upload local screenshot files and a stats snapshot for the signed-in user."""
    if not cloud_sync_enabled():
        return {"enabled": False, "message": "cloud api sync is disabled"}

    user = db.session.get(User, int(user_id))
    if not user:
        raise ValueError(f"user {user_id} not found")

    tasks = MonitorTask.query.filter_by(user_id=user.id).order_by(MonitorTask.id.asc()).all()
    all_task_ids = [int(task.id) for task in tasks if task.id is not None]
    results = (
        CollectionResult.query.filter(CollectionResult.task_id.in_(all_task_ids)).order_by(CollectionResult.id.asc()).all()
        if all_task_ids
        else []
    )
    total_results = len(results)
    exposed_results = sum(1 for result in results if result.has_brand_exposure)
    requested_task_ids = {int(task_id) for task_id in (task_ids or []) if task_id}
    screenshot_results = [
        result for result in results
        if result.screenshot_path and (not requested_task_ids or int(result.task_id) in requested_task_ids)
    ]
    resolve_path = resolve_path or resolve_local_screenshot_path

    stats_payload = {
        "install_id": get_install_id(),
        "user_key": _user_key(user),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "counts": {
            "tasks": len(tasks),
            "results": total_results,
            "brand_exposure_results": exposed_results,
            "screenshots": len(screenshot_results),
            "platforms": len({result.platform for result in results if result.platform}),
        },
    }
    stats_response = requests.post(
        f"{cloud_sync_url()}/sync/assets/",
        data=json.dumps({"kind": "stats", "payload": stats_payload}, ensure_ascii=False).encode("utf-8"),
        headers=_headers(),
        timeout=30,
    )
    if stats_response.status_code >= 400:
        raise RuntimeError(f"stats upload failed: HTTP {stats_response.status_code} {stats_response.text[:500]}")
    stats_data = stats_response.json()
    if not stats_data.get("success"):
        raise RuntimeError(f"stats upload failed: {stats_data}")

    uploaded = 0
    skipped = 0
    missing = 0
    failed = 0
    bytes_uploaded = 0
    errors = []

    for result in screenshot_results:
        path = resolve_path(result.screenshot_path)
        if not path:
            missing += 1
            continue
        file_path = Path(path)
        if not file_path.is_file():
            missing += 1
            continue

        metadata = {
            "kind": "screenshot",
            "install_id": get_install_id(),
            "user_key": _user_key(user),
            "local_result_id": result.id,
            "local_task_id": result.task_id,
            "platform": result.platform,
            "question": result.question,
            "created_at": _dt(result.created_at),
            "original_path": result.screenshot_path,
        }
        mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        try:
            with file_path.open("rb") as f:
                response = requests.post(
                    f"{cloud_sync_url()}/sync/assets/",
                    headers={k: v for k, v in _headers().items() if k.lower() != "content-type"},
                    data={"metadata": json.dumps(metadata, ensure_ascii=False)},
                    files={"file": (file_path.name, f, mime_type)},
                    timeout=60,
                )
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code} {response.text[:300]}")
            data = response.json()
            if not data.get("success"):
                raise RuntimeError(str(data))
            if data.get("deduped"):
                skipped += 1
            else:
                uploaded += 1
                bytes_uploaded += int(data.get("size") or 0)
        except Exception as exc:
            failed += 1
            if len(errors) < 5:
                errors.append({"result_id": result.id, "error": str(exc)})

    return {
        "enabled": True,
        "stats": stats_data.get("stats") or {},
        "screenshots": {
            "total": len(screenshot_results),
            "uploaded": uploaded,
            "skipped": skipped,
            "missing": missing,
            "failed": failed,
            "bytes_uploaded": bytes_uploaded,
            "errors": errors,
        },
    }


def restore_workspace_from_cloud(user_id: int, only_if_empty: bool = True) -> dict:
    if not _cloud_merge_lock.acquire(blocking=False):
        return {"enabled": True, "restored": False, "skipped": "cloud merge already running"}
    try:
        return _restore_workspace_from_cloud(user_id, only_if_empty=only_if_empty)
    finally:
        _cloud_merge_lock.release()


def _restore_workspace_from_cloud(user_id: int, only_if_empty: bool = True) -> dict:
    """Merge the cloud workspace into the local desktop database."""
    if not cloud_sync_enabled():
        return {"enabled": False, "restored": False, "message": "cloud api sync is disabled"}

    ensure_local_sync_schema()
    user = db.session.get(User, int(user_id))
    if not user:
        raise ValueError(f"user {user_id} not found")

    local_counts = {
        "tasks": MonitorTask.query.filter_by(user_id=user.id).count(),
        "results": CollectionResult.query.join(
            MonitorTask, CollectionResult.task_id == MonitorTask.id
        ).filter(MonitorTask.user_id == user.id).count(),
        "manuscripts": GeoManuscript.query.filter_by(user_id=user.id).count(),
        "sentiment_configs": SentimentConfig.query.filter_by(user_id=user.id).count(),
    }
    if only_if_empty and any(local_counts.values()):
        return {"enabled": True, "restored": False, "skipped": "local workspace is not empty", "local_counts": local_counts}

    user_key = _user_key(user)
    cursor, cursor_time = _cloud_pull_cursor(user_key)
    # A pull cursor can outlive the SQLite database across a reinstall or local
    # reset. An empty workspace must always bootstrap from the beginning so the
    # user's historical results are not silently skipped.
    if not any(local_counts.values()):
        cursor, cursor_time = 0, ""
    final_cursor = cursor
    final_cursor_time = cursor_time
    pages = 0
    tasks_by_source = {}
    results = []
    manuscripts_by_source = {}
    configs_by_source = {}
    cloud_counts = {"tasks": 0, "results": 0, "manuscripts": 0, "sentiment_configs": 0}

    while pages < 1000:
        query = urlencode({
            "user_key": user_key,
            "cursor": final_cursor,
            "cursor_time": final_cursor_time,
            "limit": 100,
            "include_metadata": 1 if pages == 0 else 0,
        })
        response = requests.get(
            f"{cloud_sync_url()}/sync/restore/?{query}",
            headers=_headers(),
            timeout=60,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"cloud restore failed: HTTP {response.status_code} {response.text[:500]}")
        data = response.json()
        if not data.get("success"):
            raise RuntimeError(f"cloud restore failed: {data}")

        workspace = data.get("workspace") or {}
        page_tasks = workspace.get("tasks") if isinstance(workspace.get("tasks"), list) else []
        page_results = workspace.get("results") if isinstance(workspace.get("results"), list) else []
        page_manuscripts = workspace.get("manuscripts") if isinstance(workspace.get("manuscripts"), list) else []
        page_configs = workspace.get("sentiment_configs") if isinstance(workspace.get("sentiment_configs"), list) else []
        for row in page_tasks:
            tasks_by_source[_source_key(row)] = row
        results.extend(page_results)
        for row in page_manuscripts:
            manuscripts_by_source[_source_key(row)] = row
        for row in page_configs:
            configs_by_source[_source_key(row)] = row

        counts = data.get("counts") or {}
        cloud_counts["tasks"] = max(cloud_counts["tasks"], int(counts.get("tasks") or 0))
        cloud_counts["results"] += int(counts.get("results") or 0)
        cloud_counts["manuscripts"] = max(cloud_counts["manuscripts"], int(counts.get("manuscripts") or 0))
        cloud_counts["sentiment_configs"] = max(cloud_counts["sentiment_configs"], int(counts.get("sentiment_configs") or 0))

        paging = data.get("paging") if isinstance(data.get("paging"), dict) else {}
        next_cursor = int(paging.get("next_cursor") or final_cursor)
        next_cursor_time = str(paging.get("next_cursor_time") or final_cursor_time)
        has_more = bool(paging.get("has_more"))
        pages += 1
        cursor_advanced = next_cursor_time > final_cursor_time or (
            next_cursor_time == final_cursor_time and next_cursor > final_cursor
        )
        if not cursor_advanced or not has_more:
            if cursor_advanced:
                final_cursor = next_cursor
                final_cursor_time = next_cursor_time
            break
        final_cursor = next_cursor
        final_cursor_time = next_cursor_time

    tasks = list(tasks_by_source.values())
    manuscripts = list(manuscripts_by_source.values())
    configs = list(configs_by_source.values())

    if not any([tasks, results, manuscripts, configs]):
        _save_cloud_pull_cursor(user_key, final_cursor, final_cursor_time)
        return {"enabled": True, "restored": False, "cloud_counts": cloud_counts, "pages": pages}

    install_id = get_install_id()
    task_map: dict[tuple[str, int], int] = {}
    task_fingerprints: dict[str, int] = {}
    config_map: dict[tuple[str, int], int] = {}
    added = {"tasks": 0, "results": 0, "manuscripts": 0, "sentiment_configs": 0}
    updated = {"tasks": 0, "results": 0, "manuscripts": 0, "sentiment_configs": 0}
    skipped = {"tasks": 0, "results": 0, "manuscripts": 0, "sentiment_configs": 0}

    local_tasks = MonitorTask.query.filter_by(user_id=user.id).all()
    for task in local_tasks:
        source = _task_cloud_source(task) or (install_id, int(task.id))
        task_map[source] = int(task.id)
        task_fingerprints[_task_fingerprint(task.name, task.created_at)] = int(task.id)

    local_configs = SentimentConfig.query.filter_by(user_id=user.id).all()
    configs_by_name = {(config.name or "").strip().casefold(): config for config in local_configs}
    for config in local_configs:
        source = _model_cloud_source(config) or (install_id, int(config.id))
        config_map[source] = int(config.id)

    for row in configs:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        source = (
            str(row.get("source_result_install_id") or row.get("source_install_id") or row.get("install_id") or ""),
            int(row.get("source_local_id") or row.get("local_id") or 0),
        )
        if not source[0] or not source[1]:
            continue
        name = payload.get("name") or "默认配置"
        existing_id = config_map.get(source)
        existing = db.session.get(SentimentConfig, existing_id) if existing_id else configs_by_name.get(name.strip().casefold())
        if existing:
            config_map[source] = existing.id
            if _model_cloud_source(existing):
                existing.positive_words = _json_text(payload.get("positive_words"), [])
                existing.negative_words = _json_text(payload.get("negative_words"), [])
                existing.enable_ai_sentiment = bool(payload.get("enable_ai_sentiment"))
                existing.ai_platform = payload.get("ai_platform")
                existing.ai_api_url = payload.get("ai_api_url")
                existing.ai_model_name = payload.get("ai_model_name")
                existing.ai_prompt = payload.get("ai_prompt")
                existing.latest_insight = _json_text(payload.get("latest_insight"), None) if payload.get("latest_insight") is not None else None
                existing.latest_insight_generated_at = _parse_dt(payload.get("latest_insight_generated_at"))
                existing.is_default = bool(payload.get("is_default"))
                updated["sentiment_configs"] += 1
            else:
                skipped["sentiment_configs"] += 1
            continue
        config = SentimentConfig(
            user_id=user.id,
            name=name,
            positive_words=_json_text(payload.get("positive_words"), []),
            negative_words=_json_text(payload.get("negative_words"), []),
            enable_ai_sentiment=bool(payload.get("enable_ai_sentiment")),
            ai_platform=payload.get("ai_platform"),
            ai_api_url=payload.get("ai_api_url"),
            ai_api_key=payload.get("ai_api_key"),
            ai_model_name=payload.get("ai_model_name"),
            ai_prompt=payload.get("ai_prompt"),
            latest_insight=_json_text(payload.get("latest_insight"), None) if payload.get("latest_insight") is not None else None,
            latest_insight_generated_at=_parse_dt(payload.get("latest_insight_generated_at")),
            is_default=bool(payload.get("is_default")),
            cloud_source_install_id=source[0],
            cloud_source_local_id=source[1],
            created_at=_parse_dt(payload.get("created_at")) or datetime.now(),
            updated_at=_parse_dt(payload.get("updated_at")) or datetime.now(),
        )
        db.session.add(config)
        db.session.flush()
        config_map[source] = config.id
        configs_by_name[name.strip().casefold()] = config
        added["sentiment_configs"] += 1

    for row in tasks:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        source = _source_key(row)
        if not source[0] or not source[1]:
            continue
        existing_id = task_map.get(source)
        if not existing_id:
            existing_id = task_fingerprints.get(_task_fingerprint(payload.get("name"), payload.get("created_at")))
        existing = db.session.get(MonitorTask, existing_id) if existing_id else None
        if existing:
            task_map[source] = existing.id
            if _task_cloud_source(existing):
                existing.name = payload.get("name") or existing.name
                existing.brand_name = payload.get("brand_name")
                existing.brand_keywords = _json_text(payload.get("brand_keywords"), [])
                existing.competitor_brands = _json_text(payload.get("competitor_brands"), [])
                existing.questions = _json_text(payload.get("questions"), [])
                existing.platforms = _json_text(payload.get("platforms"), [])
                existing.screenshot_config = _json_text(payload.get("screenshot_config"), {})
                existing.status = payload.get("status") or existing.status
                existing.last_run_at = _parse_dt(payload.get("last_run_at"))
                existing.updated_at = _parse_dt(payload.get("updated_at")) or existing.updated_at
                updated["tasks"] += 1
            else:
                skipped["tasks"] += 1
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
        task_fingerprints[_task_fingerprint(task.name, task.created_at)] = task.id
        added["tasks"] += 1

    local_task_ids = list({int(task_id) for task_id in task_map.values()})
    local_results = (
        CollectionResult.query.filter(CollectionResult.task_id.in_(local_task_ids)).all()
        if local_task_ids else []
    )
    result_sources: dict[tuple[str, int], CollectionResult] = {}
    result_fingerprints: dict[str, CollectionResult] = {}
    for result in local_results:
        source = _model_cloud_source(result) or (install_id, int(result.id))
        result_sources[source] = result
        result_fingerprints[_result_fingerprint(
            result.task_id, result.question, result.platform, result.created_at, result.answer
        )] = result

    for row in results:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        source = (
            str(row.get("source_result_install_id") or row.get("source_install_id") or row.get("install_id") or ""),
            int(row.get("source_local_id") or row.get("local_id") or 0),
        )
        task_source = (
            str(row.get("source_install_id") or row.get("install_id") or ""),
            int(row.get("source_task_local_id") or payload.get("local_task_id") or payload.get("task_id") or 0),
        )
        local_task_id = task_map.get(task_source)
        if not local_task_id or not source[0] or not source[1]:
            continue
        fingerprint = _result_fingerprint(
            local_task_id,
            payload.get("question"),
            payload.get("platform"),
            payload.get("created_at"),
            payload.get("answer"),
        )
        existing = result_sources.get(source) or result_fingerprints.get(fingerprint)
        if existing:
            if _model_cloud_source(existing):
                existing.question = payload.get("question") or ""
                existing.platform = payload.get("platform") or ""
                existing.answer = payload.get("answer")
                existing.references = _json_text(payload.get("references"), [])
                existing.screenshot_path = payload.get("screenshot_path")
                existing.has_brand_exposure = bool(payload.get("has_brand_exposure"))
                existing.exposed_keywords = _json_text(payload.get("exposed_keywords"), [])
                existing.ai_sentiment_result = _json_text(payload.get("ai_sentiment_result"), None) if payload.get("ai_sentiment_result") is not None else None
                existing.ai_sentiment_updated_at = _parse_dt(payload.get("ai_sentiment_updated_at"))
                existing.rankings = _json_text(payload.get("rankings"), [])
                updated["results"] += 1
            else:
                skipped["results"] += 1
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
            cloud_source_install_id=source[0],
            cloud_source_local_id=source[1],
            created_at=_parse_dt(payload.get("created_at")) or datetime.now(),
        )
        db.session.add(result)
        db.session.flush()
        result_sources[source] = result
        result_fingerprints[fingerprint] = result
        added["results"] += 1

    local_manuscripts = GeoManuscript.query.filter_by(user_id=user.id).all()
    manuscript_sources: dict[tuple[str, int], GeoManuscript] = {}
    manuscript_fingerprints: dict[str, GeoManuscript] = {}
    for manuscript in local_manuscripts:
        source = _model_cloud_source(manuscript) or (install_id, int(manuscript.id))
        manuscript_sources[source] = manuscript
        manuscript_fingerprints[_manuscript_fingerprint(manuscript.title, manuscript.url)] = manuscript

    for row in manuscripts:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        source = _source_key(row)
        source_install = source[0]
        fingerprint = _manuscript_fingerprint(payload.get("title"), payload.get("url"))
        existing_manuscript = manuscript_sources.get(source) or manuscript_fingerprints.get(fingerprint)
        if existing_manuscript:
            if _model_cloud_source(existing_manuscript):
                existing_manuscript.title = payload.get("title") or existing_manuscript.title
                existing_manuscript.url = payload.get("url") or existing_manuscript.url
                updated["manuscripts"] += 1
            else:
                skipped["manuscripts"] += 1
            continue
        mapped_task_id = None
        mapped_task_ids = []
        source_task_refs = row.get("source_task_refs") if isinstance(row.get("source_task_refs"), list) else []
        for ref in source_task_refs:
            if not isinstance(ref, dict):
                continue
            mapped = task_map.get((str(ref.get("install_id") or ""), int(ref.get("local_id") or 0)))
            if mapped:
                mapped_task_ids.append(mapped)
        if not mapped_task_ids:
            fallback_ids = []
            if payload.get("task_id"):
                fallback_ids.append(payload.get("task_id"))
            fallback_ids.extend(payload.get("task_ids") or [])
            for task_id in fallback_ids:
                mapped = task_map.get((source_install, int(task_id)))
                if mapped:
                    mapped_task_ids.append(mapped)
        mapped_task_ids = list(dict.fromkeys(mapped_task_ids))
        if mapped_task_ids:
            mapped_task_id = mapped_task_ids[0]
        manuscript = GeoManuscript(
            user_id=user.id,
            task_id=mapped_task_id,
            task_ids=json.dumps(mapped_task_ids, ensure_ascii=False),
            title=payload.get("title") or "恢复稿件",
            url=payload.get("url") or "",
            cloud_source_install_id=source[0],
            cloud_source_local_id=source[1],
            created_at=_parse_dt(payload.get("created_at")) or datetime.now(),
        )
        db.session.add(manuscript)
        db.session.flush()
        manuscript_sources[source] = manuscript
        manuscript_fingerprints[fingerprint] = manuscript
        added["manuscripts"] += 1

    db.session.commit()
    _save_cloud_pull_cursor(user_key, final_cursor, final_cursor_time)
    total_changed = sum(added.values()) + sum(updated.values())
    return {
        "enabled": True,
        "restored": total_changed > 0,
        "merged": True,
        "counts": added,
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "cloud_counts": cloud_counts,
        "pages": pages,
        "result_cursor": final_cursor,
        "result_cursor_time": final_cursor_time,
    }


def sync_status(user_id: int | None = None, include_remote: bool = True) -> dict:
    status = {
        "enabled": cloud_sync_enabled(),
        "api_configured": bool(cloud_sync_url()),
        "token_configured": bool(cloud_sync_token()),
        "install_id": get_install_id(),
        "sync_keys": should_sync_keys(),
    }
    if not cloud_sync_enabled() or not user_id or not include_remote:
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
        existing_remote_task = next((task for task in existing_tasks if _task_has_remote_id(task, remote_id)), None)
        if existing_remote_task:
            skipped.append({
                "remote_task_id": remote_id,
                "local_task_id": int(existing_remote_task.id),
                "reason": "already imported",
            })
            continue

        questions = payload.get("questions") or []
        platforms = payload.get("platforms") or []
        brand_keywords = payload.get("brand_keywords") or []
        if not questions or not platforms or not brand_keywords:
            skipped.append({"remote_task_id": remote_id, "reason": "missing required fields"})
            continue
        if not isinstance(platforms, list):
            skipped.append({"remote_task_id": remote_id, "reason": "invalid platform list"})
            continue
        normalized_platforms = []
        unsupported_platforms = []
        for platform_id in platforms:
            platform_id = str(platform_id or "").strip()
            if not platform_id or platform_id in normalized_platforms:
                continue
            if platform_id not in SUPPORTED_PLATFORM_IDS:
                unsupported_platforms.append(platform_id)
                continue
            normalized_platforms.append(platform_id)
        if unsupported_platforms:
            skipped.append({
                "remote_task_id": remote_id,
                "reason": f"unsupported platforms: {', '.join(unsupported_platforms)}",
            })
            continue
        if not normalized_platforms:
            skipped.append({"remote_task_id": remote_id, "reason": "missing supported platforms"})
            continue
        platforms = normalized_platforms

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


def report_client_heartbeat(
    user_id: int,
    status: str = "online",
    message: str = "",
    runtime: dict | None = None,
) -> dict:
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
            "app_version": APP_VERSION,
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "runtime": runtime if isinstance(runtime, dict) else {},
    }
    response = requests.post(
        f"{cloud_sync_url()}/remote-tasks/heartbeat/",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_headers(),
        timeout=(5, 8),
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
