"""
Background worker for cloud-created GEO tasks.

The cloud never connects directly to a user's machine. The desktop app keeps a
small outbound polling loop: heartbeat, pull pending tasks, execute locally,
then report status and sync results back.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time

from sqlalchemy import inspect

from cloud_sync import (
    cloud_sync_enabled,
    load_cloud_account,
    pull_remote_tasks,
    remote_task_id_for_task,
    report_client_heartbeat,
    report_remote_task_status,
    restore_workspace_from_cloud,
    sync_user_workspace,
    upload_workspace_assets,
)
from models import MonitorTask, User, db

logger = logging.getLogger("remote_worker")

_worker_started = False
_worker_thread: threading.Thread | None = None
_heartbeat_thread: threading.Thread | None = None
_worker_started_epoch: float | None = None
_heartbeat_started_epoch: float | None = None
_worker_restart_count = 0
_worker_lock = threading.Lock()
_worker_wakeup = threading.Event()
_heartbeat_wakeup = threading.Event()
_running_task_ids: set[int] = set()
_last_cloud_merge_at: dict[int, float] = {}
_heartbeat_state_lock = threading.Lock()
_heartbeat_states: dict[int, dict] = {}
_TERMINAL_REMOTE_STATUSES = {"completed", "failed", "stopped"}


def _ensure_local_schema() -> None:
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    required_tables = {"users", "monitor_tasks", "collection_results"}
    if required_tables.issubset(existing_tables):
        return
    db.create_all()
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    missing = sorted(required_tables - existing_tables)
    if missing:
        raise RuntimeError(f"local database is not ready, missing tables: {', '.join(missing)}")


def _poll_seconds() -> int:
    try:
        value = int(os.environ.get("GEO_REMOTE_TASK_POLL_SECONDS", "10"))
    except Exception:
        value = 10
    return max(5, min(value, 120))


def _merge_interval_seconds() -> int:
    try:
        value = int(os.environ.get("GEO_CLOUD_PULL_SECONDS", "300"))
    except Exception:
        value = 300
    return max(60, min(value, 3600))


def _heartbeat_seconds() -> int:
    try:
        value = int(os.environ.get("GEO_CLOUD_HEARTBEAT_SECONDS", "20"))
    except Exception:
        value = 20
    return max(10, min(value, 60))


def _heartbeat_timestamp(epoch: float | None) -> str | None:
    if not epoch:
        return None
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))


def _record_heartbeat_attempt(user_id: int, runtime: dict | None = None) -> None:
    with _heartbeat_state_lock:
        state = _heartbeat_states.setdefault(int(user_id), {})
        state["last_attempt_epoch"] = time.time()
        state["runtime"] = dict(runtime or {})


def _record_heartbeat_success(user_id: int) -> None:
    with _heartbeat_state_lock:
        state = _heartbeat_states.setdefault(int(user_id), {})
        state["last_success_epoch"] = time.time()
        state["last_error"] = ""
        state["last_error_epoch"] = None


def _record_heartbeat_failure(user_id: int, error: Exception | str) -> None:
    with _heartbeat_state_lock:
        state = _heartbeat_states.setdefault(int(user_id), {})
        state.setdefault("last_attempt_epoch", time.time())
        state["last_error"] = str(error)[:300]
        state["last_error_epoch"] = time.time()


def worker_health(user_id: int) -> dict:
    """Return a local, non-sensitive snapshot of the desktop cloud worker."""
    with _heartbeat_state_lock:
        state = dict(_heartbeat_states.get(int(user_id), {}))
        runtime = dict(state.get("runtime") or {})

    now = time.time()
    last_success = state.get("last_success_epoch")
    last_error = state.get("last_error", "")
    last_error_epoch = state.get("last_error_epoch") or 0
    age_seconds = max(0, int(now - last_success)) if last_success else None
    stale_after = max(45, _poll_seconds() * 3)
    online = bool(last_success and age_seconds is not None and age_seconds <= stale_after)
    stale = bool(last_success and not online)
    degraded = bool(last_error and last_error_epoch >= (last_success or 0))
    with _worker_lock:
        thread_alive = bool(_worker_thread and _worker_thread.is_alive())
        heartbeat_thread_alive = bool(_heartbeat_thread and _heartbeat_thread.is_alive())
        worker_started_epoch = _worker_started_epoch
        heartbeat_started_epoch = _heartbeat_started_epoch
        restart_count = _worker_restart_count
    return {
        "started": bool(_worker_started and thread_alive and heartbeat_thread_alive),
        "thread_alive": thread_alive,
        "heartbeat_thread_alive": heartbeat_thread_alive,
        "worker_started_at": _heartbeat_timestamp(worker_started_epoch),
        "heartbeat_started_at": _heartbeat_timestamp(heartbeat_started_epoch),
        "restart_count": restart_count,
        "online": online,
        "stale": stale,
        "degraded": degraded,
        "stale_after_seconds": stale_after,
        "age_seconds": age_seconds,
        "last_attempt_at": _heartbeat_timestamp(state.get("last_attempt_epoch")),
        "last_success_at": _heartbeat_timestamp(last_success),
        "last_error_at": _heartbeat_timestamp(last_error_epoch),
        "last_error": last_error,
        "runtime": runtime,
    }


def _find_cloud_user() -> User | None:
    account = load_cloud_account()
    cloud_user = account.get("user") if isinstance(account.get("user"), dict) else {}
    username = (cloud_user.get("username") or "").strip()
    email = (cloud_user.get("email") or "").strip()

    query = None
    if username and email:
        query = (User.username == username) | (User.email == email)
    elif username:
        query = User.username == username
    elif email:
        query = User.email == email

    if query is not None:
        user = User.query.filter(query).first()
        if user:
            return user

    if username or email:
        logger.warning("[RemoteWorker] cloud account does not match a local user: username=%s email=%s", username, email)
    else:
        logger.warning("[RemoteWorker] cloud account identity is missing; remote tasks are paused")
    return None


def _remote_pending_tasks(user_id: int) -> list[MonitorTask]:
    tasks = MonitorTask.query.filter_by(user_id=user_id, status="pending").order_by(MonitorTask.id.asc()).all()
    return [task for task in tasks if remote_task_id_for_task(task)]


def _runtime_telemetry(user_id: int) -> dict:
    remote_tasks = (
        MonitorTask.query.filter(
            MonitorTask.user_id == user_id,
            MonitorTask.schedule_config.like('%"remote_task_id"%'),
        )
        .order_by(MonitorTask.id.desc())
        .all()
    )
    running = sum(1 for task in remote_tasks if int(task.id) in _running_task_ids)
    pending = sum(1 for task in remote_tasks if task.status == "pending")
    sync_backlog = 0
    for task in remote_tasks:
        if task.status not in _TERMINAL_REMOTE_STATUSES:
            continue
        config = _schedule_config(task)
        needs_results = not config.get("remote_results_synced")
        needs_assets = task.status == "completed" and not config.get("remote_assets_uploaded")
        needs_status = config.get("remote_status_reported") != task.status
        if needs_results or needs_assets or needs_status:
            sync_backlog += 1

    if running:
        state = "collecting"
    elif sync_backlog:
        state = "syncing"
    elif pending:
        state = "queued"
    else:
        state = "ready"
    return {
        "worker_state": state,
        "running_tasks": running,
        "pending_remote_tasks": pending,
        "sync_backlog": sync_backlog,
        "poll_seconds": _poll_seconds(),
    }


def _schedule_config(task: MonitorTask) -> dict:
    try:
        config = json.loads(task.schedule_config or "{}")
    except Exception:
        config = {}
    return config if isinstance(config, dict) else {}


def _update_task_schedule_config(task_id: int, **values) -> None:
    task = db.session.get(MonitorTask, task_id)
    if not task:
        return
    config = _schedule_config(task)
    config.update(values)
    task.schedule_config = json.dumps(config, ensure_ascii=False)
    db.session.commit()


def _mark_remote_status_reported(task_id: int, status: str) -> None:
    _update_task_schedule_config(
        task_id,
        remote_status_reported=status,
        remote_status_reported_at=int(time.time()),
    )


def _report_remote_status_safely(
    user_id: int,
    remote_task_id: int,
    local_task_id: int,
    status: str,
    message: str,
) -> bool:
    try:
        report_remote_task_status(user_id, remote_task_id, local_task_id, status, message)
        if status in _TERMINAL_REMOTE_STATUSES:
            _mark_remote_status_reported(local_task_id, status)
        return True
    except Exception as exc:
        logger.warning(
            "[RemoteWorker] status report deferred remote=%s local=%s status=%s: %s",
            remote_task_id,
            local_task_id,
            status,
            exc,
        )
        return False


def _deliver_remote_outputs_safely(user_id: int, task_id: int, status: str) -> bool:
    task = db.session.get(MonitorTask, task_id)
    if not task:
        return False
    config = _schedule_config(task)
    if not config.get("remote_results_synced"):
        try:
            sync_user_workspace(user_id)
            _update_task_schedule_config(
                task_id,
                remote_results_synced=True,
                remote_results_synced_at=int(time.time()),
            )
        except Exception as sync_error:
            logger.warning("[RemoteWorker] result sync deferred task=%s: %s", task_id, sync_error)
            return False

    if status != "completed":
        return True

    task = db.session.get(MonitorTask, task_id)
    config = _schedule_config(task) if task else {}
    if config.get("remote_assets_uploaded"):
        return True
    try:
        upload_workspace_assets(user_id, task_ids=[task_id])
        _update_task_schedule_config(
            task_id,
            remote_assets_uploaded=True,
            remote_assets_uploaded_at=int(time.time()),
        )
        return True
    except Exception as asset_error:
        logger.warning("[RemoteWorker] screenshot upload deferred task=%s: %s", task_id, asset_error)
        return False


def _reconcile_terminal_remote_statuses(user_id: int) -> None:
    tasks = (
        MonitorTask.query.filter(
            MonitorTask.user_id == user_id,
            MonitorTask.status.in_(_TERMINAL_REMOTE_STATUSES),
        )
        .order_by(MonitorTask.id.asc())
        .all()
    )
    pending = []
    for task in tasks:
        remote_id = remote_task_id_for_task(task)
        if not remote_id:
            continue
        config = _schedule_config(task)
        if config.get("cloud_source_install_id"):
            continue
        needs_results = not config.get("remote_results_synced")
        needs_assets = task.status == "completed" and not config.get("remote_assets_uploaded")
        needs_status = config.get("remote_status_reported") != task.status
        if needs_results or needs_assets or needs_status:
            pending.append((task, int(remote_id)))
        if len(pending) >= 20:
            break

    pending_results = [task for task, _remote_id in pending if not _schedule_config(task).get("remote_results_synced")]
    if pending_results:
        try:
            sync_user_workspace(user_id)
            synced_at = int(time.time())
            for task in pending_results:
                config = _schedule_config(task)
                config.update(remote_results_synced=True, remote_results_synced_at=synced_at)
                task.schedule_config = json.dumps(config, ensure_ascii=False)
            db.session.commit()
        except Exception as sync_error:
            db.session.rollback()
            logger.warning("[RemoteWorker] batched result sync deferred: %s", sync_error)

    for task, remote_id in pending:
        config = _schedule_config(task)
        if task.status == "completed" and config.get("remote_results_synced") and not config.get("remote_assets_uploaded"):
            try:
                upload_workspace_assets(user_id, task_ids=[int(task.id)])
                _update_task_schedule_config(
                    int(task.id),
                    remote_assets_uploaded=True,
                    remote_assets_uploaded_at=int(time.time()),
                )
            except Exception as asset_error:
                logger.warning("[RemoteWorker] screenshot upload deferred task=%s: %s", task.id, asset_error)

        config = _schedule_config(db.session.get(MonitorTask, task.id) or task)
        if config.get("remote_status_reported") == task.status:
            continue
        _report_remote_status_safely(
            user_id,
            remote_id,
            int(task.id),
            task.status,
            f"本机客户端补报任务状态：{task.status}",
        )


def _execute_remote_task(app, user_id: int, task_id: int, remote_task_id: int) -> None:
    with _worker_lock:
        if task_id in _running_task_ids:
            return
        _running_task_ids.add(task_id)

    try:
        with app.app_context():
            task = db.session.get(MonitorTask, task_id)
            if not task:
                _report_remote_status_safely(
                    user_id,
                    remote_task_id,
                    task_id,
                    "failed",
                    "本地任务不存在",
                )
                return

            _report_remote_status_safely(
                user_id,
                remote_task_id,
                task_id,
                "running",
                "本机客户端已开始采集",
            )
            from collector import run_collection

            try:
                interval = task.collection_interval or 20
                run_collection(task.id, min_interval=interval, max_interval=interval)
                db.session.expire_all()
                finished_task = db.session.get(MonitorTask, task_id)
                final_status = finished_task.status if finished_task else "completed"
                if final_status not in {"completed", "stopped", "failed"}:
                    final_status = "completed"
                _deliver_remote_outputs_safely(user_id, task_id, final_status)
                _report_remote_status_safely(
                    user_id,
                    remote_task_id,
                    task_id,
                    final_status,
                    "本机客户端已完成采集" if final_status == "completed" else f"采集结束：{final_status}",
                )
            except Exception as exc:
                logger.exception("[RemoteWorker] 远程任务执行失败 remote=%s local=%s", remote_task_id, task_id)
                failed_task = db.session.get(MonitorTask, task_id)
                if failed_task:
                    failed_task.status = "failed"
                    db.session.commit()
                _deliver_remote_outputs_safely(user_id, task_id, "failed")
                _report_remote_status_safely(user_id, remote_task_id, task_id, "failed", str(exc))
    finally:
        with _worker_lock:
            _running_task_ids.discard(task_id)


def _tick(app) -> None:
    _ensure_local_schema()
    if not cloud_sync_enabled():
        return

    user = _find_cloud_user()
    if not user:
        return

    user_id = int(user.id)

    try:
        pulled = pull_remote_tasks(user_id)
        if pulled.get("created"):
            logger.info("[RemoteWorker] pulled remote tasks: %s", pulled)
    except Exception as exc:
        logger.warning("[RemoteWorker] task pull deferred: %s", exc)

    now = time.monotonic()
    if now - _last_cloud_merge_at.get(user_id, 0) >= _merge_interval_seconds():
        _last_cloud_merge_at[user_id] = now
        try:
            merged = restore_workspace_from_cloud(user_id, only_if_empty=False)
            if merged.get("restored"):
                logger.info("[RemoteWorker] merged cloud workspace: %s", merged)
        except Exception as exc:
            logger.warning("[RemoteWorker] cloud merge deferred: %s", exc)

    _reconcile_terminal_remote_statuses(user_id)

    if _running_task_ids:
        return

    for task in _remote_pending_tasks(user_id):
        remote_id = remote_task_id_for_task(task)
        if not remote_id:
            continue
        threading.Thread(
            target=_execute_remote_task,
            args=(app, user_id, int(task.id), int(remote_id)),
            daemon=True,
        ).start()
        break


def _heartbeat_tick() -> None:
    """Send liveness independently from slower task and workspace operations."""
    _ensure_local_schema()
    if not cloud_sync_enabled():
        return
    user = _find_cloud_user()
    if not user:
        return

    user_id = int(user.id)
    runtime = _runtime_telemetry(user_id)
    _record_heartbeat_attempt(user_id, runtime)
    heartbeat_message = {
        "collecting": "客户端在线，正在执行云端采集任务",
        "syncing": "客户端在线，正在补传采集结果",
        "queued": "客户端在线，云端任务已进入本地队列",
    }.get(runtime["worker_state"], "客户端在线，等待云端任务")
    try:
        report_client_heartbeat(user_id, "online", heartbeat_message, runtime=runtime)
        _record_heartbeat_success(user_id)
    except Exception as exc:
        _record_heartbeat_failure(user_id, exc)
        raise


def _task_loop(app) -> None:
    global _worker_started, _worker_thread
    logger.info("[RemoteWorker] task loop started")
    try:
        while True:
            try:
                with app.app_context():
                    _tick(app)
            except Exception as exc:
                logger.warning("[RemoteWorker] task tick failed: %s", exc)
            _worker_wakeup.wait(_poll_seconds())
            _worker_wakeup.clear()
    finally:
        with _worker_lock:
            if _worker_thread is threading.current_thread():
                _worker_thread = None
                _worker_started = False


def _heartbeat_loop(app) -> None:
    global _heartbeat_thread
    logger.info("[RemoteWorker] heartbeat loop started")
    try:
        while True:
            try:
                with app.app_context():
                    _heartbeat_tick()
            except Exception as exc:
                logger.warning("[RemoteWorker] heartbeat deferred: %s", exc)
            _heartbeat_wakeup.wait(_heartbeat_seconds())
            _heartbeat_wakeup.clear()
    finally:
        with _worker_lock:
            if _heartbeat_thread is threading.current_thread():
                _heartbeat_thread = None


def start_remote_task_worker(app) -> bool:
    global _worker_started, _worker_thread, _heartbeat_thread
    global _worker_started_epoch, _heartbeat_started_epoch, _worker_restart_count
    if os.environ.get("GEO_DESKTOP_MODE") != "1":
        return False
    if os.environ.get("GEO_REMOTE_TASK_WORKER", "1").strip().lower() in {"0", "false", "off", "no"}:
        return False

    with _worker_lock:
        task_alive = bool(_worker_thread and _worker_thread.is_alive())
        heartbeat_alive = bool(_heartbeat_thread and _heartbeat_thread.is_alive())
        if task_alive and heartbeat_alive:
            _worker_started = True
            return False

        replacing_dead_worker = bool(
            (_worker_thread is not None and not task_alive)
            or (_heartbeat_thread is not None and not heartbeat_alive)
            or (_worker_started and not task_alive)
        )
        threads_to_start = []
        if not task_alive:
            _worker_thread = threading.Thread(target=_task_loop, args=(app,), daemon=True, name="geo-remote-worker")
            threads_to_start.append(("task", _worker_thread))
            _worker_started_epoch = time.time()
        if not heartbeat_alive:
            _heartbeat_thread = threading.Thread(
                target=_heartbeat_loop,
                args=(app,),
                daemon=True,
                name="geo-heartbeat-worker",
            )
            threads_to_start.append(("heartbeat", _heartbeat_thread))
            _heartbeat_started_epoch = time.time()
        _worker_started = True
        if replacing_dead_worker:
            _worker_restart_count += 1
        try:
            for _kind, thread in threads_to_start:
                thread.start()
        except Exception:
            if _worker_thread and not _worker_thread.is_alive():
                _worker_thread = None
                _worker_started_epoch = None
            if _heartbeat_thread and not _heartbeat_thread.is_alive():
                _heartbeat_thread = None
                _heartbeat_started_epoch = None
            _worker_started = bool(_worker_thread and _worker_thread.is_alive())
            raise
    return bool(threads_to_start)


def wake_remote_task_worker(app) -> bool:
    """Ensure the worker is alive and request an immediate cloud retry."""
    started = start_remote_task_worker(app)
    _worker_wakeup.set()
    _heartbeat_wakeup.set()
    return started
