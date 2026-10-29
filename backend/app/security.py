from __future__ import annotations

import hashlib
import secrets
import threading
from datetime import timedelta

from fastapi import HTTPException, Request, Response
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.models import Admin, SessionToken
from app.timeutil import utcnow

COOKIE_NAME = "rs_session"
SESSION_DAYS = 7
_password_hash = PasswordHash.recommended()
_login_guard = threading.Lock()
_login_failures: dict[str, list[float]] = {}
MAX_FAILURES = 5
WINDOW_SECONDS = 600


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _password_hash.verify(password, hashed)
    except Exception:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def assert_login_allowed(ip: str) -> None:
    now = utcnow().timestamp()
    with _login_guard:
        attempts = [item for item in _login_failures.get(ip, []) if now - item < WINDOW_SECONDS]
        _login_failures[ip] = attempts
        if len(attempts) >= MAX_FAILURES:
            raise HTTPException(status_code=429, detail="登录失败次数过多，请约 10 分钟后再试")


def record_login_failure(ip: str) -> None:
    now = utcnow().timestamp()
    with _login_guard:
        attempts = [item for item in _login_failures.get(ip, []) if now - item < WINDOW_SECONDS]
        attempts.append(now)
        _login_failures[ip] = attempts


def clear_login_failures(ip: str) -> None:
    with _login_guard:
        _login_failures.pop(ip, None)


def create_session(db: Session, admin: Admin) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(
        SessionToken(
            token_hash=hash_token(raw),
            epoch=admin.session_epoch,
            expires_at=utcnow() + timedelta(days=SESSION_DAYS),
        )
    )
    db.commit()
    return raw


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def admin_from_request(db: Session, request: Request) -> Admin:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        raise HTTPException(status_code=401, detail="请先登录")
    row = db.query(SessionToken).filter(SessionToken.token_hash == hash_token(raw)).one_or_none()
    if row is None:
        raise HTTPException(status_code=401, detail="请先登录")
    now = utcnow()
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        from datetime import timezone

        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=401, detail="登录已过期")
    admin = db.query(Admin).one_or_none()
    if admin is None or admin.session_epoch != row.epoch:
        raise HTTPException(status_code=401, detail="请先登录")
    return admin


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
