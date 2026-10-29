from __future__ import annotations

from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import AppSetting


def normalize_proxy(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=422, detail="代理地址需要是 http 或 https，例如 http://127.0.0.1:7890")
    return text


def stored_proxy(db: Session) -> str:
    row = db.query(AppSetting).one_or_none()
    return (row.proxy_url or "").strip() if row else ""


def require_proxy(db: Session, use_proxy: bool) -> str:
    if not use_proxy:
        return ""
    url = stored_proxy(db)
    if not url:
        raise HTTPException(status_code=422, detail="请先在设置中配置代理")
    return url
