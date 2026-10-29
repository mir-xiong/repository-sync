from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.accounts import account_login
from app.crypto import decrypt_text
from app.deps import get_db, require_admin
from app.git_ops import GitError, list_tree, preview_file, read_image, recent_commits
from app.models import Admin, AppSetting, Repo, RepoTarget, SyncLog
from app.schedule_util import ScheduleError, next_run, validate_schedule
from app.schemas import RepoCreate, RepoUpdate, ScheduleIn, TargetIn, repo_dict
from app.summary_service import generate_summary
from app.storage import current_local_root, internal_mirror_root, mirror_file, relocate_mirror
from app.sync_service import RepoBusy, SyncCoordinator, preflight_upstream, remove_repo_files, run_diff
from app.webdav_client import WebDavError
from app.timeutil import utcnow
from app.proxy import require_proxy
from app.urls import UrlError, parse_git_target, parse_upstream, parse_webdav_remote

router = APIRouter(prefix="/api/repos", tags=["repos"])


def _coordinator(request: Request) -> SyncCoordinator:
    return request.app.state.coordinator


def _apply_schedule(repo: Repo, schedule: ScheduleIn) -> None:
    try:
        validate_schedule(schedule.type, schedule.time, schedule.weekday, schedule.monthday, schedule.cron)
    except ScheduleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    repo.schedule_type = schedule.type
    repo.schedule_time = schedule.time or ""
    repo.schedule_weekday = schedule.weekday if schedule.type == "weekly" else None
    repo.schedule_monthday = schedule.monthday if schedule.type == "monthly" else None
    repo.cron_expr = (schedule.cron or "").strip() if schedule.type == "cron" else ""
    repo.schedule_paused = schedule.paused
    repo.next_run_at = next_run(
        schedule_type=repo.schedule_type,
        schedule_time=repo.schedule_time,
        weekday=repo.schedule_weekday,
        monthday=repo.schedule_monthday,
        cron_expr=repo.cron_expr,
        paused=repo.schedule_paused,
    )


def _default_remote(repo: Repo, target_type: str, request: Request, db: Session) -> str:
    if not repo.owner or not repo.repo_name:
        raise HTTPException(status_code=422, detail="无法根据上游仓库确定保存位置")
    if target_type == "webdav":
        return parse_webdav_remote(f"/{repo.owner}/{repo.repo_name}")
    row = db.query(AppSetting).one()
    encrypted = row.github_token_encrypted if target_type == "github" else row.gitee_token_encrypted
    login = account_login(target_type, decrypt_text(request.app.state.fernet, encrypted), require_proxy(db, repo.use_proxy))
    host = "github.com" if target_type == "github" else "gitee.com"
    return parse_git_target(f"https://{host}/{login}/{repo.repo_name}", target_type)


def _normalize_targets(repo: Repo, targets: list[TargetIn], request: Request, db: Session) -> list[tuple[str, str]]:
    normalized: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for target in targets:
        raw = target.remote_url.strip()
        try:
            if not raw:
                remote = _default_remote(repo, target.target_type, request, db)
            elif target.target_type == "webdav":
                remote = parse_webdav_remote(raw)
            else:
                remote = parse_git_target(raw, target.target_type)
        except UrlError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        key = (target.target_type, remote.casefold())
        if key in seen:
            raise HTTPException(status_code=422, detail="目标重复")
        seen.add(key)
        normalized.append((target.target_type, remote))
    return normalized


def _replace_targets(repo: Repo, targets: list[TargetIn], request: Request, db: Session) -> None:
    normalized = _normalize_targets(repo, targets, request, db)
    previous = {
        (item.target_type, item.remote_url.casefold()): (item.last_status, item.last_error)
        for item in repo.targets
    }
    repo.targets.clear()
    for target_type, remote in normalized:
        status, error = previous.get((target_type, remote.casefold()), ("never", ""))
        repo.targets.append(RepoTarget(target_type=target_type, remote_url=remote, last_status=status, last_error=error))


def _require_storage(save_local: bool, target_count: int) -> None:
    if not save_local and target_count == 0:
        raise HTTPException(status_code=422, detail="至少选择一种保存方式")


def _require_configured_accounts(db: Session, targets: list[TargetIn]) -> None:
    if not targets:
        return
    row = db.query(AppSetting).one()
    needed = {item.target_type for item in targets}
    if "github" in needed and not row.github_token_encrypted:
        raise HTTPException(status_code=422, detail="请先在设置中配置 GitHub 令牌")
    if "gitee" in needed and not row.gitee_token_encrypted:
        raise HTTPException(status_code=422, detail="请先在设置中配置 Gitee 令牌")
    if "webdav" in needed and not (row.webdav_url.strip() and row.webdav_username.strip()):
        raise HTTPException(status_code=422, detail="请先在设置中配置 WebDAV 地址和用户名")


def _token(db: Session, request: Request, platform: str) -> str:
    row = db.query(AppSetting).one()
    encrypted = row.github_token_encrypted if platform == "github" else row.gitee_token_encrypted
    return decrypt_text(request.app.state.fernet, encrypted)


def _safe_path(path: str) -> str:
    raw = path.strip().lstrip("/")
    if not raw:
        return ""
    parts = [part for part in raw.split("/") if part]
    if any(part == ".." for part in parts):
        raise HTTPException(status_code=400, detail="路径不合法")
    return "/".join(parts)


@router.get("")
def list_repos(
    q: str = "",
    platform: str = "",
    sync_status: str = "",
    diff_status: str = "",
    sort: str = Query(default="name"),
    order: str = Query(default="asc"),
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    query = db.query(Repo).options(selectinload(Repo.targets))
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Repo.name.ilike(like), Repo.upstream_url.ilike(like)))
    if platform:
        query = query.filter(Repo.platform == platform)
    if sync_status:
        query = query.filter(Repo.sync_status == sync_status)
    if diff_status:
        query = query.filter(Repo.diff_status == diff_status)
    column = Repo.last_sync_at if sort == "last_sync" else Repo.name
    query = query.order_by(column.desc() if order == "desc" else column.asc())
    rows = query.all()
    return {"items": [repo_dict(row) for row in rows]}


@router.post("")
def create_repo(payload: RepoCreate, request: Request, db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)) -> dict:
    settings = request.app.state.settings
    try:
        upstream = parse_upstream(payload.upstream_url, allow_file=settings.allow_file_upstreams)
    except UrlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if db.query(Repo).filter(Repo.dedupe_key == upstream.dedupe_key).one_or_none():
        raise HTTPException(status_code=409, detail="这个上游仓库已经添加过")
    name = (payload.name or f"{upstream.owner}/{upstream.repo_name}").strip()
    if not name:
        raise HTTPException(status_code=422, detail="仓库名称不能为空")
    _require_storage(payload.save_local, len(payload.targets))
    _require_configured_accounts(db, payload.targets)
    proxy = require_proxy(db, payload.use_proxy)
    token = "" if upstream.platform == "file" else _token(db, request, upstream.platform)
    try:
        preflight_upstream(upstream.canonical, upstream.platform, token, settings.git_timeout_seconds, proxy)
    except GitError as exc:
        raise HTTPException(status_code=400, detail=f"无法访问上游仓库：{exc}") from exc
    repo = Repo(
        name=name,
        upstream_url=upstream.canonical,
        dedupe_key=upstream.dedupe_key,
        platform=upstream.platform,
        owner=upstream.owner,
        repo_name=upstream.repo_name,
        sync_status="never",
    )
    _apply_schedule(repo, payload.schedule)
    repo.save_local = payload.save_local
    repo.use_proxy = payload.use_proxy
    _replace_targets(repo, payload.targets, request, db)
    db.add(repo)
    db.flush()
    settings_row = db.query(AppSetting).one()
    root = current_local_root(settings, settings_row) if payload.save_local else internal_mirror_root(settings)
    repo.local_path = str(mirror_file(root, repo.id))
    db.commit()
    coordinator: SyncCoordinator = _coordinator(request)
    try:
        outcome = coordinator.run(repo.id, "initial")
    except RepoBusy as exc:
        _discard_repo(db, repo.id)
        raise HTTPException(status_code=409, detail="仓库正在同步") from exc
    if outcome.upstream_failed:
        message = outcome.upstream_error or "上游拉取失败"
        _discard_repo(db, repo.id)
        raise HTTPException(status_code=400, detail=f"上游拉取失败：{message}")
    summary_error = generate_summary(coordinator, repo.id)
    db.expire_all()
    saved = db.query(Repo).options(selectinload(Repo.targets)).filter(Repo.id == repo.id).one()
    return {"repo": repo_dict(saved), "summary_error": summary_error}


@router.get("/{repo_id}")
def get_repo(repo_id: int, db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)) -> dict:
    return repo_dict(_load(db, repo_id))


@router.patch("/{repo_id}")
def update_repo(
    repo_id: int,
    payload: RepoUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    repo = _load(db, repo_id)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="仓库名称不能为空")
        repo.name = name
    if payload.schedule is not None:
        _apply_schedule(repo, payload.schedule)
    if payload.use_proxy is not None:
        require_proxy(db, payload.use_proxy)
        repo.use_proxy = payload.use_proxy
    next_local = repo.save_local if payload.save_local is None else payload.save_local
    next_targets = repo.targets if payload.targets is None else payload.targets
    _require_storage(next_local, len(next_targets))
    if payload.targets is not None:
        _require_configured_accounts(db, payload.targets)
        _replace_targets(repo, payload.targets, request, db)
    if payload.save_local is True and not repo.save_local:
        root = current_local_root(request.app.state.settings, db.query(AppSetting).one())
        destination = mirror_file(root, repo.id)
        if repo.local_path:
            relocate_mirror(Path(repo.local_path), destination)
        repo.local_path = str(destination)
    if payload.save_local is not None:
        repo.save_local = payload.save_local
    repo.updated_at = utcnow()
    db.commit()
    db.refresh(repo)
    return repo_dict(_load(db, repo.id))


@router.delete("/{repo_id}")
def delete_repo(repo_id: int, request: Request, db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)) -> dict:
    coordinator = _coordinator(request)
    if coordinator.is_running(repo_id):
        raise HTTPException(status_code=409, detail="同步进行中，暂时不能删除")
    repo = _load(db, repo_id)
    settings_row = db.query(AppSetting).one()
    try:
        warnings = remove_repo_files(coordinator, repo, settings_row)
    except (GitError, WebDavError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    for log in db.query(SyncLog).filter(SyncLog.repo_id == repo.id).all():
        log.repo_id = None
    mirror = repo.local_path
    db.delete(repo)
    db.commit()
    if mirror:
        shutil.rmtree(mirror, ignore_errors=True)
    return {"ok": True, "warnings": warnings}


@router.post("/{repo_id}/targets/{target_id}/retry")
def retry_target(repo_id: int, target_id: int, request: Request, db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)) -> dict:
    repo = _load(db, repo_id)
    target = next((item for item in repo.targets if item.id == target_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="保存方式不存在")
    if target.last_status != "failed":
        raise HTTPException(status_code=422, detail="只有失败的保存方式可以重试")
    try:
        outcome = _coordinator(request).retry_target(repo_id, target_id)
    except RepoBusy as exc:
        raise HTTPException(status_code=409, detail="仓库正在同步") from exc
    if outcome.upstream_failed:
        raise HTTPException(status_code=400, detail=outcome.upstream_error)
    db.expire_all()
    saved = _load(db, repo_id)
    return {"repo": repo_dict(saved), "status": outcome.status}


@router.post("/{repo_id}/sync")
def sync_repo(repo_id: int, request: Request, db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)) -> dict:
    _load(db, repo_id)
    try:
        outcome = _coordinator(request).run(repo_id, "manual")
    except RepoBusy as exc:
        raise HTTPException(status_code=409, detail="仓库正在同步") from exc
    summary_error = None
    if not outcome.upstream_failed:
        summary_error = None
    saved = _load(db, repo_id)
    return {"repo": repo_dict(saved), "status": outcome.status, "upstream_error": outcome.upstream_error, "summary_error": summary_error}


@router.post("/{repo_id}/diff")
def diff_repo(repo_id: int, request: Request, db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)) -> dict:
    _load(db, repo_id)
    try:
        status = run_diff(_coordinator(request), repo_id)
    except RepoBusy as exc:
        raise HTTPException(status_code=409, detail="仓库正在同步") from exc
    except GitError as exc:
        raise HTTPException(status_code=400, detail=f"差异检测失败：{exc}") from exc
    return {"repo": repo_dict(_load(db, repo_id)), "diff_status": status}


@router.post("/{repo_id}/summary")
def regenerate_summary(repo_id: int, request: Request, db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)) -> dict:
    _load(db, repo_id)
    error = generate_summary(_coordinator(request), repo_id)
    if error:
        raise HTTPException(status_code=400, detail=error)
    db.expire_all()
    return repo_dict(_load(db, repo_id))


@router.get("/{repo_id}/tree")
def repo_tree(
    repo_id: int,
    path: str = "",
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    repo = _load(db, repo_id)
    if not repo.local_path or not Path(repo.local_path).exists():
        raise HTTPException(status_code=404, detail="本地镜像还不存在")
    branch = repo.default_branch or "HEAD"
    try:
        entries = list_tree(Path(repo.local_path), branch, _safe_path(path), timeout=60)
    except GitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": _safe_path(path), "entries": entries}


@router.get("/{repo_id}/file")
def repo_file(
    repo_id: int,
    path: str,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    repo = _load(db, repo_id)
    relative = _safe_path(path)
    if not relative:
        raise HTTPException(status_code=400, detail="需要文件路径")
    try:
        return preview_file(Path(repo.local_path), repo.default_branch or "HEAD", relative, timeout=60)
    except GitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{repo_id}/raw")
def repo_raw(
    repo_id: int,
    path: str,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> Response:
    repo = _load(db, repo_id)
    relative = _safe_path(path)
    if not relative:
        raise HTTPException(status_code=400, detail="需要文件路径")
    if not repo.local_path or not Path(repo.local_path).exists():
        raise HTTPException(status_code=404, detail="本地镜像还不存在")
    try:
        data, media = read_image(Path(repo.local_path), repo.default_branch or "HEAD", relative, timeout=60)
    except GitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=data, media_type=media, headers={"Cache-Control": "private, max-age=300", "Content-Security-Policy": "default-src 'none'", "X-Content-Type-Options": "nosniff"})


@router.get("/{repo_id}/commits")
def repo_commits(repo_id: int, db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)) -> dict:
    repo = _load(db, repo_id)
    if not repo.local_path or not Path(repo.local_path).exists():
        return {"items": []}
    try:
        items = recent_commits(Path(repo.local_path), repo.default_branch or "HEAD", timeout=60)
    except GitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": items}


def _load(db: Session, repo_id: int) -> Repo:
    repo = db.query(Repo).options(selectinload(Repo.targets)).filter(Repo.id == repo_id).one_or_none()
    if repo is None:
        raise HTTPException(status_code=404, detail="仓库不存在")
    return repo


def _discard_repo(db: Session, repo_id: int) -> None:
    repo = db.get(Repo, repo_id)
    mirror = repo.local_path if repo else ""
    for log in db.query(SyncLog).filter(SyncLog.repo_id == repo_id).all():
        log.repo_id = None
    if repo is not None:
        db.delete(repo)
    db.commit()
    if mirror:
        shutil.rmtree(mirror, ignore_errors=True)
