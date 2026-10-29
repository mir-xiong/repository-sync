from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.deps import get_db, require_admin
from app.models import Admin, SessionToken
from app.schemas import LoginIn, PasswordIn
from app.security import (
    assert_login_allowed,
    clear_login_failures,
    clear_session_cookie,
    client_ip,
    create_session,
    hash_token,
    record_login_failure,
    set_session_cookie,
    verify_password,
    hash_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    ip = client_ip(request)
    assert_login_allowed(ip)
    admin = db.query(Admin).one_or_none()
    if admin is None or not verify_password(payload.password, admin.password_hash):
        record_login_failure(ip)
        raise HTTPException(status_code=401, detail="密码不正确")
    clear_login_failures(ip)
    set_session_cookie(response, create_session(db, admin))
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    raw = request.cookies.get("rs_session")
    if raw:
        row = db.query(SessionToken).filter(SessionToken.token_hash == hash_token(raw)).one_or_none()
        if row is not None:
            db.delete(row)
            db.commit()
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(_admin: Admin = Depends(require_admin)) -> dict:
    return {"ok": True}


@router.post("/password")
def change_password(
    payload: PasswordIn,
    response: Response,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_admin),
) -> dict:
    if not verify_password(payload.current_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="新密码需要和当前密码不同")
    admin.password_hash = hash_password(payload.new_password)
    admin.session_epoch += 1
    db.query(SessionToken).delete()
    db.commit()
    set_session_cookie(response, create_session(db, admin))
    return {"ok": True}
