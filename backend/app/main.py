from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, load_settings
from app.crypto import build_fernet
from app.db import create_session_factory
from app.models import Admin, AppSetting, Repo, SyncLog
from app.routers import auth, logs, repos, settings as settings_router
from app.scheduler import start_scheduler
from app.security import hash_password
from app.sync_service import SyncCoordinator
from app.timeutil import utcnow

logger = logging.getLogger("repository_sync")


def ensure_baseline(sessions, settings: Settings) -> None:
    db = sessions()
    try:
        if db.query(AppSetting).one_or_none() is None:
            db.add(AppSetting(log_retention_days=7, sync_concurrency=2))
            db.commit()
        admin = db.query(Admin).one_or_none()
        if admin is None:
            if not settings.initial_admin_password:
                raise RuntimeError("首次启动需要环境变量 INITIAL_ADMIN_PASSWORD")
            db.add(Admin(password_hash=hash_password(settings.initial_admin_password), session_epoch=1))
            db.commit()
        elif settings.admin_password_reset:
            if not settings.initial_admin_password:
                raise RuntimeError("重置密码需要环境变量 INITIAL_ADMIN_PASSWORD")
            admin.password_hash = hash_password(settings.initial_admin_password)
            admin.session_epoch += 1
            from app.models import SessionToken

            db.query(SessionToken).delete()
            db.commit()
            logger.warning("已按 INITIAL_ADMIN_PASSWORD 重置管理员密码")
        for repo in db.query(Repo).filter(Repo.sync_status == "running").all():
            repo.sync_status = "failed"
        for row in db.query(SyncLog).filter(SyncLog.status == "running").all():
            row.status = "failed"
            row.upstream_status = "failed"
            row.upstream_error = row.upstream_error or "服务重启，同步中断"
            row.finished_at = utcnow()
        db.commit()
    finally:
        db.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    active = settings or load_settings()
    sessions = create_session_factory(active)
    ensure_baseline(sessions, active)
    fernet = build_fernet(active.secret_key, active.resolved_data_dir())
    coordinator = SyncCoordinator(sessions, active, fernet)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = None
        if app.state.settings.scheduler_enabled:
            stop = start_scheduler(app.state.coordinator, app.state.sessions)
        yield
        if stop is not None:
            stop.set()

    app = FastAPI(title="仓库定时同步", lifespan=lifespan)
    app.state.settings = active
    app.state.sessions = sessions
    app.state.fernet = fernet
    app.state.coordinator = coordinator
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active.origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(repos.router)
    app.include_router(logs.router)
    app.include_router(settings_router.router)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    return app
