from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.models import Admin
from app.security import admin_from_request


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.sessions()
    try:
        yield db
    finally:
        db.close()


def require_admin(request: Request, db: Session = Depends(get_db)) -> Admin:
    return admin_from_request(db, request)
