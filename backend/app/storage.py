from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import Settings, repo_root
from app.models import AppSetting, Repo, SyncLog
from app.sync_service import SyncCoordinator


def internal_mirror_root(settings: Settings) -> Path:
    path = settings.resolved_data_dir() / "mirrors"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def resolve_directory(raw: str) -> Path:
    text = raw.strip()
    if not text:
        raise HTTPException(status_code=422, detail="请填写本地目录")
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = repo_root() / path
    try:
        path = path.resolve()
    except OSError as exc:
        raise HTTPException(status_code=422, detail="本地目录无法解析") from exc
    if path.exists() and not path.is_dir():
        raise HTTPException(status_code=422, detail="本地目录必须是文件夹")
    path.mkdir(parents=True, exist_ok=True)
    return path


def current_local_root(settings: Settings, row: AppSetting) -> Path:
    raw = (row.local_mirror_dir or "").strip()
    if not raw:
        return internal_mirror_root(settings)
    return resolve_directory(raw)


def mirror_file(root: Path, repo_id: int) -> Path:
    return root / f"{repo_id}.git"


def relocate_mirror(source: Path, destination: Path) -> None:
    if source.resolve() == destination.resolve():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        return
    if destination.exists():
        raise HTTPException(status_code=409, detail=f"目标位置已有镜像：{destination}")
    shutil.move(str(source), str(destination))


def apply_local_directory(
    db: Session,
    settings: Settings,
    coordinator: SyncCoordinator,
    raw_path: str,
    *,
    migrate: bool,
) -> dict:
    row = db.query(AppSetting).one()
    new_root = resolve_directory(raw_path)
    old_root = current_local_root(settings, row)
    if new_root == old_root:
        raise HTTPException(status_code=422, detail="本地目录没有变化")
    repos = db.query(Repo).all()
    if any(coordinator.is_running(repo.id) for repo in repos):
        raise HTTPException(status_code=409, detail="有仓库正在同步，暂时不能切换本地目录")
    for repo in repos:
        if repo.local_path and new_root == Path(repo.local_path).resolve():
            raise HTTPException(status_code=422, detail="新目录不能是某个仓库镜像本身")

    removed: list[dict[str, str]] = []
    updated: list[dict[str, str]] = []
    moved: list[tuple[Path, Path]] = []
    try:
        if migrate:
            for repo in repos:
                if not repo.save_local:
                    continue
                source = Path(repo.local_path) if repo.local_path else mirror_file(old_root, repo.id)
                destination = mirror_file(new_root, repo.id)
                relocate_mirror(source, destination)
                if source.exists() or destination.exists():
                    moved.append((destination, source))
                repo.local_path = str(destination)
                updated.append({"id": str(repo.id), "name": repo.name, "location": repo.local_path})
        else:
            for repo in list(repos):
                if not repo.save_local:
                    continue
                repo.save_local = False
                if repo.targets:
                    updated.append({"id": str(repo.id), "name": repo.name, "location": ""})
                    continue
                removed.append({"id": str(repo.id), "name": repo.name, "location": repo.local_path})
                for log in db.query(SyncLog).filter(SyncLog.repo_id == repo.id).all():
                    log.repo_id = None
                db.delete(repo)
        row.local_mirror_dir = str(new_root)
        db.commit()
    except HTTPException:
        _restore_moves(moved)
        db.rollback()
        raise
    except Exception as exc:
        _restore_moves(moved)
        db.rollback()
        raise HTTPException(status_code=400, detail=f"切换本地目录失败：{exc}") from exc
    return {
        "local_mirror_dir": str(new_root),
        "migrated": migrate,
        "updated": updated,
        "removed": removed,
    }


def _restore_moves(moved: list[tuple[Path, Path]]) -> None:
    for destination, source in reversed(moved):
        if destination.exists() and not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(destination), str(source))
