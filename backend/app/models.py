from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.timeutil import utcnow


class Base(DeclarativeBase):
    pass


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text)
    session_epoch: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SessionToken(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    epoch: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    log_retention_days: Mapped[int] = mapped_column(Integer, default=7)
    sync_concurrency: Mapped[int] = mapped_column(Integer, default=2)
    gitee_token_encrypted: Mapped[str] = mapped_column(Text, default="")
    github_token_encrypted: Mapped[str] = mapped_column(Text, default="")
    webdav_url: Mapped[str] = mapped_column(Text, default="")
    webdav_username: Mapped[str] = mapped_column(Text, default="")
    webdav_password_encrypted: Mapped[str] = mapped_column(Text, default="")
    local_mirror_dir: Mapped[str] = mapped_column(Text, default="")
    proxy_url: Mapped[str] = mapped_column(Text, default="")


class AiProvider(Base):
    __tablename__ = "ai_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    base_url: Mapped[str] = mapped_column(Text)
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(200))
    use_proxy: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Repo(Base):
    __tablename__ = "repos"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_repo_dedupe"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    upstream_url: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(String(500))
    platform: Mapped[str] = mapped_column(String(20))
    owner: Mapped[str] = mapped_column(String(200), default="")
    repo_name: Mapped[str] = mapped_column(String(200), default="")
    local_path: Mapped[str] = mapped_column(Text, default="")
    save_local: Mapped[bool] = mapped_column(Boolean, default=True)
    use_proxy: Mapped[bool] = mapped_column(Boolean, default=False)
    default_branch: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    summary_source: Mapped[str] = mapped_column(String(20), default="")
    schedule_type: Mapped[str] = mapped_column(String(20))
    schedule_time: Mapped[str] = mapped_column(String(5), default="")
    schedule_weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule_monthday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cron_expr: Mapped[str] = mapped_column(String(120), default="")
    schedule_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_status: Mapped[str] = mapped_column(String(20), default="never")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_schedule_slot: Mapped[str] = mapped_column(String(20), default="")
    diff_status: Mapped[str] = mapped_column(String(20), default="unknown")
    last_diff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    branch_count: Mapped[int] = mapped_column(Integer, default=0)
    tag_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    targets: Mapped[list[RepoTarget]] = relationship(
        back_populates="repo", cascade="all, delete-orphan"
    )


class RepoTarget(Base):
    __tablename__ = "repo_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), index=True)
    target_type: Mapped[str] = mapped_column(String(20))
    remote_url: Mapped[str] = mapped_column(Text)
    last_status: Mapped[str] = mapped_column(String(20), default="never")
    last_error: Mapped[str] = mapped_column(Text, default="")

    repo: Mapped[Repo] = relationship(back_populates="targets")


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int | None] = mapped_column(ForeignKey("repos.id", ondelete="SET NULL"), nullable=True, index=True)
    repo_name: Mapped[str] = mapped_column(String(200), default="")
    upstream_url: Mapped[str] = mapped_column(Text, default="")
    trigger: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    upstream_status: Mapped[str] = mapped_column(String(20), default="pending")
    upstream_error: Mapped[str] = mapped_column(Text, default="")

    targets: Mapped[list[SyncLogTarget]] = relationship(
        back_populates="log", cascade="all, delete-orphan"
    )


class SyncLogTarget(Base):
    __tablename__ = "sync_log_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    log_id: Mapped[int] = mapped_column(ForeignKey("sync_logs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[str] = mapped_column(Text, default="")

    log: Mapped[SyncLog] = relationship(back_populates="targets")
