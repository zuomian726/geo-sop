"""
Background worker for cloud-created GEO tasks.

The cloud never connects directly to a user's machine. The desktop app keeps a
small outbound polling loop: heartbeat, pull pending tasks, execute locally,
then report status and sync results back.
"""
from __future__ import annotations

import logging
import os
import threading
import time

from cloud_sync import (
    cloud_sync_enabled,
    load_cloud_account,
    pull_remote_tasks,
    remote_task_id_for_task,
    report_client_heartbeat,
    report_remote_task_status,
    sync_user_workspace,
)
from models import MonitorTask, User, db

logger = logging.getLogger("remote_worker")

_worker_started = False
_worker_lock = threading.Lock()
_running_task_ids: set[int] = set()


def _poll_seconds() -> int:
    try:
        value = int(os.environ.get("GEO_REMOTE_TASK_POLL_SECONDS", "10"))
    except Exception:
        value = 10
    return max(5, min(value, 120))


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

    return User.query.order_by(User.id.asc()).first()


def _remote_pending_tasks(user_id: int) -> list[MonitorTask]:
    tasks = MonitorTask.query.filter_by(user_id=user_id, status="pending").order_by(MonitorTask.id.asc()).all()
    return [task for task in tasks if remote_task_id_for_task(task)]


def _execute_remote_task(app, user_id: int, task_id: int, remote_task_id: int) -> None:
    with _worker_lock:
        if task_id in _running_task_ids:
            return
        _running_task_ids.add(task_id)

    try:
        with app.app_context():
            task = db.session.get(MonitorTask, task_id)
            if not task:
                report_remote_task_status(user_id, remote_task_id, task_id, "failed", "本地任务不存在")
                return

            report_remote_task_status(user_id, remote_task_id, task_id, "running", "本机客户端已开始采集")
            from collector import run_collection

            try:
                interval = task.collection_interval or 20
                run_collection(task.id, min_interval=interval, max_interval=interval)
                db.session.expire_all()
                finished_task = db.session.get(MonitorTask, task_id)
                final_status = finished_task.status if finished_task else "completed"
                if final_status not in {"completed", "stopped", "failed"}:
                    final_status = "completed"
                sync_user_workspace(user_id)
                report_remote_task_status(
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
                try:
                    sync_user_workspace(user_id)
                except Exception:
                    logger.exception("[RemoteWorker] 失败状态同步失败")
                report_remote_task_status(user_id, remote_task_id, task_id, "failed", str(exc))
    finally:
        with _worker_lock:
            _running_task_ids.discard(task_id)


def _tick(app) -> None:
    if not cloud_sync_enabled():
        return

    user = _find_cloud_user()
    if not user:
        return

    user_id = int(user.id)
    report_client_heartbeat(user_id, "online", "客户端在线，等待云端任务")
    pulled = pull_remote_tasks(user_id)
    if pulled.get("created"):
        logger.info("[RemoteWorker] pulled remote tasks: %s", pulled)

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


def start_remote_task_worker(app) -> bool:
    global _worker_started
    if os.environ.get("GEO_DESKTOP_MODE") != "1":
        return False
    if os.environ.get("GEO_REMOTE_TASK_WORKER", "1").strip().lower() in {"0", "false", "off", "no"}:
        return False

    with _worker_lock:
        if _worker_started:
            return False
        _worker_started = True

    def loop() -> None:
        logger.info("[RemoteWorker] started")
        while True:
            try:
                with app.app_context():
                    _tick(app)
            except Exception as exc:
                logger.warning("[RemoteWorker] tick failed: %s", exc)
            time.sleep(_poll_seconds())

    threading.Thread(target=loop, daemon=True, name="geo-remote-worker").start()
    return True
