from __future__ import annotations

import logging
import threading

from sqlalchemy.orm import Session, sessionmaker

from app.models import Repo, SyncLog, SyncLogTarget
from app.schedule_util import is_due, slot_key
from app.sync_service import SyncCoordinator
from app.timeutil import shanghai_now, utcnow

logger = logging.getLogger("repository_sync.scheduler")


def purge_expired_logs(db: Session, retention_days: int) -> None:
    from datetime import timedelta

    cutoff = utcnow() - timedelta(days=retention_days)
    old_ids = [row.id for row in db.query(SyncLog.id).filter(SyncLog.started_at < cutoff).all()]
    if not old_ids:
        return
    db.query(SyncLogTarget).filter(SyncLogTarget.log_id.in_(old_ids)).delete(synchronize_session=False)
    db.query(SyncLog).filter(SyncLog.id.in_(old_ids)).delete(synchronize_session=False)
    db.commit()


def tick(coordinator: SyncCoordinator) -> None:
    from app.models import AppSetting

    slot = slot_key(shanghai_now())
    db = coordinator.sessions()
    try:
        settings_row = db.query(AppSetting).one_or_none()
        if settings_row is not None:
            purge_expired_logs(db, settings_row.log_retention_days)
        repos = db.query(Repo).filter(Repo.schedule_paused.is_(False)).all()
        due_ids: list[int] = []
        for repo in repos:
            if repo.last_schedule_slot == slot:
                continue
            if not is_due(
                schedule_type=repo.schedule_type,
                schedule_time=repo.schedule_time,
                weekday=repo.schedule_weekday,
                monthday=repo.schedule_monthday,
                cron_expr=repo.cron_expr,
                moment=shanghai_now(),
            ):
                continue
            repo.last_schedule_slot = slot
            due_ids.append(repo.id)
        db.commit()
    finally:
        db.close()
    for repo_id in due_ids:
        threading.Thread(target=coordinator.run, args=(repo_id, "schedule"), daemon=True).start()


def start_scheduler(coordinator: SyncCoordinator, sessions: sessionmaker[Session]) -> threading.Event:
    stop = threading.Event()
    # 启动这一分钟不补跑，避免每次重启都触发当前分钟的调度。
    current = slot_key(shanghai_now())
    db = sessions()
    try:
        for repo in db.query(Repo).all():
            repo.last_schedule_slot = current
        db.commit()
    finally:
        db.close()

    def loop() -> None:
        while not stop.wait(5):
            try:
                tick(coordinator)
            except Exception:
                logger.exception("调度执行失败")

    threading.Thread(target=loop, name="repo-scheduler", daemon=True).start()
    return stop
