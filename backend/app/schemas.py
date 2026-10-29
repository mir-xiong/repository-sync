from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models import AiProvider, Repo, SyncLog
from app.timeutil import as_utc


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return as_utc(value).isoformat()


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class ScheduleIn(BaseModel):
    type: Literal["daily", "weekly", "monthly", "cron"]
    time: str | None = None
    weekday: int | None = None
    monthday: int | None = None
    cron: str | None = None
    paused: bool = False


class TargetIn(BaseModel):
    target_type: Literal["gitee", "github", "webdav"]
    remote_url: str = Field(default="", max_length=500)


class RepoCreate(BaseModel):
    upstream_url: str
    name: str | None = Field(default=None, max_length=200)
    schedule: ScheduleIn
    save_local: bool = True
    use_proxy: bool = False
    targets: list[TargetIn] = Field(default_factory=list)


class RepoUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    schedule: ScheduleIn | None = None
    save_local: bool | None = None
    use_proxy: bool | None = None
    targets: list[TargetIn] | None = None
    summary: str | None = Field(default=None, max_length=4000)


class SettingsPatch(BaseModel):
    log_retention_days: int | None = Field(default=None, ge=1, le=180)
    sync_concurrency: int | None = Field(default=None, ge=1, le=8)
    proxy_url: str | None = Field(default=None, max_length=400)


class LocalDirectoryIn(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    migrate: bool


class CredentialsPatch(BaseModel):
    gitee_token: str | None = None
    github_token: str | None = None
    clear_gitee_token: bool = False
    clear_github_token: bool = False
    webdav_url: str | None = None
    webdav_username: str | None = None
    webdav_password: str | None = None
    clear_webdav_password: bool = False


class CredentialTestIn(BaseModel):
    target: Literal["gitee", "github", "webdav"]


class ProviderIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=8, max_length=400)
    api_key: str | None = None
    model: str = Field(min_length=1, max_length=200)
    enabled: bool = False
    use_proxy: bool = False


class ProviderPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None
    use_proxy: bool | None = None


class ModelListIn(BaseModel):
    base_url: str = Field(min_length=8, max_length=400)
    api_key: str | None = None
    use_proxy: bool = False
    provider_id: int | None = None


class ProxyTestIn(BaseModel):
    proxy_url: str | None = Field(default=None, max_length=400)


def _storages(repo: Repo) -> list[dict]:
    items: list[dict] = []
    if repo.save_local and repo.local_path:
        items.append({"type": "local", "location": repo.local_path, "last_status": "", "last_error": ""})
    for target in repo.targets:
        items.append(
            {
                "id": target.id,
                "type": target.target_type,
                "location": target.remote_url,
                "last_status": target.last_status,
                "last_error": target.last_error,
            }
        )
    return items


def schedule_dict(repo: Repo) -> dict:
    return {
        "type": repo.schedule_type,
        "time": repo.schedule_time or None,
        "weekday": repo.schedule_weekday,
        "monthday": repo.schedule_monthday,
        "cron": repo.cron_expr or None,
        "paused": repo.schedule_paused,
    }


def repo_dict(repo: Repo) -> dict:
    summary = repo.summary or ""
    first_line = summary.strip().splitlines()[0] if summary.strip() else ""
    return {
        "id": repo.id,
        "name": repo.name,
        "upstream_url": repo.upstream_url,
        "platform": repo.platform,
        "owner": repo.owner,
        "repo_name": repo.repo_name,
        "summary": summary,
        "summary_excerpt": first_line[:180],
        "summary_source": repo.summary_source,
        "default_branch": repo.default_branch,
        "sync_status": repo.sync_status,
        "last_sync_at": iso(repo.last_sync_at),
        "next_run_at": iso(repo.next_run_at),
        "diff_status": repo.diff_status,
        "last_diff_at": iso(repo.last_diff_at),
        "size_bytes": repo.size_bytes,
        "branch_count": repo.branch_count,
        "tag_count": repo.tag_count,
        "schedule": schedule_dict(repo),
        "save_local": repo.save_local,
        "use_proxy": repo.use_proxy,
        "storages": _storages(repo),
        "targets": [
            {
                "id": target.id,
                "target_type": target.target_type,
                "remote_url": target.remote_url,
                "last_status": target.last_status,
                "last_error": target.last_error,
            }
            for target in repo.targets
        ],
        "created_at": iso(repo.created_at),
        "updated_at": iso(repo.updated_at),
    }


def log_dict(row: SyncLog) -> dict:
    return {
        "id": row.id,
        "repo_id": row.repo_id,
        "repo_name": row.repo_name,
        "upstream_url": row.upstream_url,
        "trigger": row.trigger,
        "status": row.status,
        "started_at": iso(row.started_at),
        "finished_at": iso(row.finished_at),
        "upstream_status": row.upstream_status,
        "upstream_error": row.upstream_error,
        "targets": [
            {
                "name": target.name,
                "target_type": target.target_type,
                "status": target.status,
                "error": target.error,
            }
            for target in row.targets
        ],
    }


def provider_dict(row: AiProvider) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "base_url": row.base_url,
        "model": row.model,
        "enabled": row.enabled,
        "use_proxy": row.use_proxy,
        "api_key_set": bool(row.api_key_encrypted),
        "created_at": iso(row.created_at),
    }
