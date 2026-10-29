from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.deps import get_db, require_admin
from app.models import Admin, SyncLog
from app.schemas import log_dict
from app.timeutil import as_utc

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
def list_logs(
    repo_id: int | None = None,
    status: str = "",
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    query = db.query(SyncLog).options(selectinload(SyncLog.targets))
    if repo_id is not None:
        query = query.filter(SyncLog.repo_id == repo_id)
    if status:
        query = query.filter(SyncLog.status == status)
    if since is not None:
        query = query.filter(SyncLog.started_at >= as_utc(since))
    if until is not None:
        query = query.filter(SyncLog.started_at <= as_utc(until))
    rows = query.order_by(SyncLog.started_at.desc()).limit(limit).all()
    return {"items": [log_dict(row) for row in rows]}


@router.get("/{log_id}")
def get_log(log_id: int, db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)) -> dict:
    row = db.query(SyncLog).options(selectinload(SyncLog.targets)).filter(SyncLog.id == log_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="日志不存在")
    return log_dict(row)
