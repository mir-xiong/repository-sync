from __future__ import annotations

import httpx
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session, sessionmaker

from fastapi import HTTPException

from app.accounts import account_login
from app.config import Settings
from app.crypto import decrypt_text
from app.git_ops import (
    GitError,
    classify_refs,
    clone_or_update,
    count_refs,
    default_branch,
    directory_size,
    export_worktree,
    fetch_check_refs,
    is_ancestor,
    language_summary,
    list_local_refs,
    ls_remote,
    push_mirror,
    readme_text,
    recent_commits,
    run_git,
    tracked_files,
    git_proxy,
    current_git_proxy,
)
from app.models import AppSetting, Repo, RepoTarget, SyncLog, SyncLogTarget
from app.schedule_util import next_run
from app.timeutil import utcnow
from app.urls import Upstream, UrlError, auth_https_url, parse_upstream, redact
from app.webdav_client import WebDavClient, WebDavError


class RepoBusy(Exception):
    pass


@dataclass
class SyncOutcome:
    status: str
    upstream_failed: bool = False
    upstream_error: str = ""


class SyncCoordinator:
    def __init__(self, sessions: sessionmaker[Session], settings: Settings, fernet: Fernet) -> None:
        self.sessions = sessions
        self.settings = settings
        self.fernet = fernet
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._running: set[int] = set()
        self._active = 0

    def is_running(self, repo_id: int) -> bool:
        with self._lock:
            return repo_id in self._running

    @contextmanager
    def exclusive(self, repo_id: int):
        with self._lock:
            if repo_id in self._running:
                raise RepoBusy()
            self._running.add(repo_id)
        try:
            yield
        finally:
            with self._lock:
                self._running.discard(repo_id)
                self._cv.notify_all()

    def retry_target(self, repo_id: int, target_id: int) -> SyncOutcome:
        with self.exclusive(repo_id):
            self._acquire_slot()
            try:
                with git_proxy(self._proxy_for(repo_id)):
                    return self._retry_target(repo_id, target_id)
            finally:
                self._release_slot()

    def run(self, repo_id: int, trigger: str) -> SyncOutcome:
        try:
            with self.exclusive(repo_id):
                self._acquire_slot()
                try:
                    with git_proxy(self._proxy_for(repo_id)):
                        return self._execute(repo_id, trigger)
                finally:
                    self._release_slot()
        except RepoBusy:
            if trigger == "schedule":
                self._write_skip(repo_id)
                return SyncOutcome(status="skipped")
            raise

    def _acquire_slot(self) -> None:
        while True:
            with self._cv:
                if self._active < self._concurrency():
                    self._active += 1
                    return
                self._cv.wait(timeout=1)

    def _release_slot(self) -> None:
        with self._cv:
            self._active = max(0, self._active - 1)
            self._cv.notify_all()

    def _proxy_for(self, repo_id: int) -> str:
        db = self.sessions()
        try:
            repo = db.get(Repo, repo_id)
            if repo is None or not repo.use_proxy:
                return ""
            row = db.query(AppSetting).one_or_none()
            return (row.proxy_url or "").strip() if row else ""
        finally:
            db.close()

    def _concurrency(self) -> int:
        db = self.sessions()
        try:
            row = db.query(AppSetting).one_or_none()
            return row.sync_concurrency if row else 2
        finally:
            db.close()

    def _write_skip(self, repo_id: int) -> None:
        db = self.sessions()
        try:
            repo = db.get(Repo, repo_id)
            if repo is None:
                return
            log = SyncLog(
                repo_id=repo.id,
                repo_name=repo.name,
                upstream_url=repo.upstream_url,
                trigger="schedule",
                status="skipped",
                started_at=utcnow(),
                finished_at=utcnow(),
                upstream_status="skipped",
                upstream_error="上一次同步尚未结束",
            )
            db.add(log)
            repo.sync_status = "skipped"
            db.commit()
        finally:
            db.close()

    def _retry_target(self, repo_id: int, target_id: int) -> SyncOutcome:
        db = self.sessions()
        try:
            repo = db.get(Repo, repo_id)
            if repo is None:
                return SyncOutcome(status="failed", upstream_failed=True, upstream_error="仓库不存在")
            target = next((item for item in repo.targets if item.id == target_id), None)
            if target is None:
                return SyncOutcome(status="failed", upstream_failed=True, upstream_error="保存方式不存在")
            mirror = Path(repo.local_path) if repo.local_path else None
            if mirror is None or not mirror.exists():
                return SyncOutcome(status="failed", upstream_failed=True, upstream_error="本地镜像还不存在，请先完整同步")
            if repo.use_proxy and not current_git_proxy():
                return SyncOutcome(status="failed", upstream_failed=True, upstream_error="已选择使用代理，但设置里还没有代理地址")
            settings_row = db.query(AppSetting).one()
            log = SyncLog(
                repo_id=repo.id,
                repo_name=repo.name,
                upstream_url=repo.upstream_url,
                trigger="retry",
                status="running",
                upstream_status="skipped",
                upstream_error="只重试这一处保存方式，没有重新拉取上游",
            )
            db.add(log)
            repo.sync_status = "running"
            db.commit()
            db.refresh(log)
            db.refresh(repo)
            target = next(item for item in repo.targets if item.id == target_id)
            status, error = _sync_target(repo, target, settings_row, self.fernet, self.settings.git_timeout_seconds)
            target.last_status = status
            target.last_error = error
            db.add(
                SyncLogTarget(
                    log_id=log.id,
                    name=target.remote_url,
                    target_type=target.target_type,
                    status=status,
                    error=error,
                )
            )
            log.status = status
            log.finished_at = utcnow()
            repo.sync_status = "failed" if any(item.last_status == "failed" for item in repo.targets) else "success"
            repo.last_sync_at = utcnow()
            repo.updated_at = utcnow()
            db.commit()
            return SyncOutcome(status=status, upstream_failed=False, upstream_error=error)
        finally:
            db.close()

    def _execute(self, repo_id: int, trigger: str) -> SyncOutcome:
        db = self.sessions()
        try:
            repo = db.get(Repo, repo_id)
            if repo is None:
                return SyncOutcome(status="failed", upstream_failed=True, upstream_error="仓库不存在")
            settings_row = db.query(AppSetting).one()
            log = SyncLog(
                repo_id=repo.id,
                repo_name=repo.name,
                upstream_url=repo.upstream_url,
                trigger=trigger,
                status="running",
                upstream_status="pending",
            )
            db.add(log)
            repo.sync_status = "running"
            db.commit()
            db.refresh(log)
            db.refresh(repo)

            timeout = self.settings.git_timeout_seconds
            if repo.use_proxy and not current_git_proxy():
                message = "已选择使用代理，但设置里还没有代理地址"
                log.upstream_status = "failed"
                log.upstream_error = message
                log.status = "failed"
                log.finished_at = utcnow()
                repo.sync_status = "failed"
                repo.last_sync_at = utcnow()
                repo.updated_at = utcnow()
                db.commit()
                return SyncOutcome(status="failed", upstream_failed=True, upstream_error=message)
            mirror = Path(repo.local_path)
            token = _token_for(settings_row, self.fernet, repo.platform)
            auth_url = auth_https_url(repo.upstream_url, repo.platform, token)
            upstream_error = ""
            try:
                _retry(lambda: clone_or_update(mirror, repo.upstream_url, auth_url, timeout=timeout))
                branch = default_branch(mirror, timeout=timeout)
                branches, tags = count_refs(mirror, timeout=timeout)
                repo.default_branch = branch
                repo.branch_count = branches
                repo.tag_count = tags
                repo.size_bytes = directory_size(mirror)
                log.upstream_status = "success"
                repo.diff_status = "same"
                repo.last_diff_at = utcnow()
                db.commit()
            except GitError as exc:
                upstream_error = redact(str(exc))
                log.upstream_status = "failed"
                log.upstream_error = upstream_error
                log.status = "failed"
                log.finished_at = utcnow()
                for target in repo.targets:
                    db.add(
                        SyncLogTarget(
                            log_id=log.id,
                            name=target.remote_url,
                            target_type=target.target_type,
                            status="skipped",
                            error="上游失败，未执行",
                        )
                    )
                    target.last_status = "skipped"
                    target.last_error = "上游失败，未执行"
                repo.sync_status = "failed"
                repo.diff_status = "failed"
                repo.last_diff_at = utcnow()
                repo.last_sync_at = utcnow()
                repo.updated_at = utcnow()
                db.commit()
                return SyncOutcome(status="failed", upstream_failed=True, upstream_error=upstream_error)

            any_target_failed = False
            for target in list(repo.targets):
                status, error = _sync_target(repo, target, settings_row, self.fernet, timeout)
                target.last_status = status
                target.last_error = error
                db.add(
                    SyncLogTarget(
                        log_id=log.id,
                        name=target.remote_url,
                        target_type=target.target_type,
                        status=status,
                        error=error,
                    )
                )
                if status == "failed":
                    any_target_failed = True
            log.status = "failed" if any_target_failed else "success"
            log.finished_at = utcnow()
            repo.sync_status = log.status
            repo.last_sync_at = utcnow()
            repo.updated_at = utcnow()
            repo.next_run_at = _compute_next(repo)
            db.commit()
            return SyncOutcome(status=log.status, upstream_failed=False, upstream_error="")
        finally:
            db.close()


def _retry(action, attempts: int = 3):
    last_error: Exception | None = None
    for index in range(attempts):
        try:
            return action()
        except (GitError, WebDavError) as exc:
            last_error = exc
            if not exc.retryable or index == attempts - 1:
                raise
    if last_error:
        raise last_error
    return None


def _token_for(settings_row: AppSetting, fernet: Fernet, platform: str) -> str:
    if platform == "github":
        return decrypt_text(fernet, settings_row.github_token_encrypted)
    if platform == "gitee":
        return decrypt_text(fernet, settings_row.gitee_token_encrypted)
    return ""


def _sync_target(repo: Repo, target: RepoTarget, settings_row: AppSetting, fernet: Fernet, timeout: int) -> tuple[str, str]:
    try:
        if target.target_type in {"github", "gitee"}:
            token = _token_for(settings_row, fernet, target.target_type)
            _ensure_remote_repository(
                target.remote_url,
                target.target_type,
                token,
                current_git_proxy(),
                repo.upstream_url,
            )
            auth_url = auth_https_url(target.remote_url, target.target_type, token)
            _retry(lambda: push_mirror(Path(repo.local_path), auth_url, timeout=timeout))
            return "success", ""
        if target.target_type == "webdav":
            _retry(lambda: _upload_webdav(repo, target.remote_url, settings_row, fernet, timeout))
            return "success", ""
        return "failed", "未知目标类型"
    except (GitError, WebDavError) as exc:
        return "failed", redact(str(exc))


def _upload_webdav(repo: Repo, remote_dir: str, settings_row: AppSetting, fernet: Fernet, timeout: int) -> None:
    if not settings_row.webdav_url or not settings_row.webdav_username:
        raise WebDavError("请先在设置中配置 WebDAV", retryable=False)
    password = decrypt_text(fernet, settings_row.webdav_password_encrypted)
    branch = repo.default_branch or "HEAD"
    with tempfile.TemporaryDirectory(prefix="repo-sync-") as temp:
        export_worktree(Path(repo.local_path), branch, Path(temp), timeout=timeout)
        with WebDavClient(
            settings_row.webdav_url,
            settings_row.webdav_username,
            password,
            timeout=120,
            proxy=current_git_proxy(),
        ) as client:
            client.upload_directory(remote_dir, Path(temp))


def _compute_next(repo: Repo):
    return next_run(
        schedule_type=repo.schedule_type,
        schedule_time=repo.schedule_time,
        weekday=repo.schedule_weekday,
        monthday=repo.schedule_monthday,
        cron_expr=repo.cron_expr,
        paused=repo.schedule_paused,
    )


def preflight_upstream(repo_url: str, platform: str, token: str, timeout: int, proxy: str = "") -> None:
    auth_url = auth_https_url(repo_url, platform, token)
    try:
        with git_proxy(proxy):
            run_git(["ls-remote", auth_url, "HEAD"], timeout=min(timeout, 90))
    except GitError as exc:
        raise GitError(redact(str(exc)), retryable=exc.retryable) from exc


def run_diff(coordinator: SyncCoordinator, repo_id: int) -> str:
    with coordinator.exclusive(repo_id):
        with git_proxy(coordinator._proxy_for(repo_id)):
            return _run_diff(coordinator, repo_id)


def _run_diff(coordinator: SyncCoordinator, repo_id: int) -> str:
        db = coordinator.sessions()
        try:
            repo = db.get(Repo, repo_id)
            if repo is None:
                raise GitError("仓库不存在", retryable=False)
            settings_row = db.query(AppSetting).one()
            token = _token_for(settings_row, coordinator.fernet, repo.platform)
            timeout = coordinator.settings.git_timeout_seconds
            mirror = Path(repo.local_path)
            auth_url = auth_https_url(repo.upstream_url, repo.platform, token)
            try:
                remote = _retry(lambda: ls_remote(auth_url, timeout=timeout))
                local = list_local_refs(mirror, timeout=timeout)
                if local == remote:
                    status = "same"
                else:
                    fetched = _retry(lambda: fetch_check_refs(mirror, auth_url, timeout=timeout))

                    def ancestor(left: str, right: str) -> bool:
                        return is_ancestor(mirror, left, right, timeout=timeout)

                    status = classify_refs(local, fetched, ancestor)
            except GitError as exc:
                repo.diff_status = "failed"
                repo.last_diff_at = utcnow()
                db.commit()
                raise GitError(redact(str(exc)), retryable=exc.retryable) from exc
            repo.diff_status = status
            repo.last_diff_at = utcnow()
            db.commit()
            return status
        finally:
            db.close()


def remove_repo_files(coordinator: SyncCoordinator, repo: Repo, settings_row: AppSetting) -> list[str]:
    warnings: list[str] = []
    proxy = (settings_row.proxy_url or "").strip() if repo.use_proxy else ""
    if repo.use_proxy and not proxy:
        raise GitError("已选择使用代理，但设置里还没有代理地址", retryable=False)
    for target in repo.targets:
        if target.target_type == "webdav":
            if not settings_row.webdav_url or not settings_row.webdav_username:
                raise GitError("未配置 WebDAV，无法删除远程目录", retryable=False)
            password = decrypt_text(coordinator.fernet, settings_row.webdav_password_encrypted)
            try:
                with WebDavClient(settings_row.webdav_url, settings_row.webdav_username, password, proxy=proxy) as client:
                    client.delete_directory(target.remote_url)
            except WebDavError as exc:
                raise GitError(redact(str(exc)), retryable=False) from exc
            continue
        if target.target_type not in {"github", "gitee"}:
            continue
        if _same_repository(repo.upstream_url, target.remote_url):
            warnings.append("保存目标与上游是同一个仓库，已保留上游")
            continue
        token = _token_for(settings_row, coordinator.fernet, target.target_type)
        if not token:
            label = "GitHub" if target.target_type == "github" else "Gitee"
            raise GitError(f"请先配置 {label} 令牌，才能删除保存到那里的仓库", retryable=False)
        _delete_remote_repository(target.remote_url, target.target_type, token, proxy)
    mirror = Path(repo.local_path) if repo.local_path else None
    if mirror and mirror.exists():
        shutil.rmtree(mirror, ignore_errors=True)
    return warnings


def _same_repository(left: str, right: str) -> bool:
    try:
        return parse_upstream(left).dedupe_key == parse_upstream(right).dedupe_key
    except UrlError:
        return left.strip().rstrip("/").casefold() == right.strip().rstrip("/").casefold()


def _request_kwargs(platform: str, token: str, proxy: str) -> dict:
    kwargs: dict = {"timeout": 30, "trust_env": False}
    if proxy:
        kwargs["proxy"] = proxy
    if platform == "github":
        kwargs["headers"] = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "repository-sync",
        }
    else:
        kwargs["params"] = {"access_token": token}
    return kwargs


def _optional_upstream(url: str) -> Upstream | None:
    if not url or "://" not in url:
        return None
    try:
        parsed = parse_upstream(url)
    except UrlError:
        return None
    if parsed.platform not in {"github", "gitee"}:
        return None
    return parsed


def _response_body(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _is_fork_of(body: dict, upstream: Upstream) -> bool:
    if not body.get("fork"):
        return False
    expected = f"{upstream.owner}/{upstream.repo_name}".casefold()
    for key in ("parent", "source"):
        node = body.get(key)
        if isinstance(node, dict) and str(node.get("full_name", "")).casefold() == expected:
            return True
    return False


def _ensure_remote_repository(remote_url: str, platform: str, token: str, proxy: str, upstream_url: str = "") -> None:
    parsed = parse_upstream(remote_url)
    label = "GitHub" if platform == "github" else "Gitee"
    if not token:
        raise GitError(f"请先配置 {label} 令牌，才能保存到那里", retryable=False)
    upstream = _optional_upstream(upstream_url)
    same_origin = upstream is not None and upstream.platform == platform
    if same_origin and upstream is not None and _same_repository(upstream.canonical, parsed.canonical):
        return
    status, body = _repository_info(parsed.owner, parsed.repo_name, platform, token, proxy)
    if status == 401:
        raise GitError(f"{label} 令牌无效，无法确认目标仓库", retryable=False)
    if status == 200 and (not same_origin or (upstream is not None and _is_fork_of(body, upstream))):
        return
    if status not in {200, 403, 404}:
        raise GitError(f"无法确认 {label} 仓库 {parsed.owner}/{parsed.repo_name}：HTTP {status}", retryable=status >= 500)
    if status == 403 and same_origin:
        raise GitError(
            f"无法确认 {label} 仓库 {parsed.owner}/{parsed.repo_name}。同名仓库可能已存在，但当前令牌看不到它。请先删除该仓库，或给令牌加上 Administration 权限，避免生成带数字后缀的 fork",
            retryable=False,
        )
    try:
        login = account_login(platform, token, proxy)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else f"无法读取{label}账户"
        raise GitError(detail, retryable=False) from exc
    if login.casefold() != parsed.owner.casefold():
        if status == 200:
            return
        raise GitError(f"目标仓库 {parsed.canonical} 不存在。当前令牌只能在账户 {login} 下创建仓库", retryable=False)
    if status == 200:
        _delete_remote_repository(parsed.canonical, platform, token, proxy)
    if same_origin and upstream is not None:
        created = _fork_upstream(upstream, parsed.repo_name, platform, token, proxy)
        action = "fork"
    else:
        created = _create_remote_repository(parsed.repo_name, platform, token, proxy)
        action = "创建"
    if created.status_code in {200, 201, 202}:
        if action == "fork" and upstream is not None:
            created_body = _response_body(created)
            created_name = str(created_body.get("name") or "")
            full_name = str(created_body.get("full_name") or "")
            expected_full = f"{parsed.owner}/{parsed.repo_name}"
            if (created_name and created_name.casefold() != parsed.repo_name.casefold()) or (
                full_name and full_name.casefold() != expected_full.casefold()
            ):
                shown = full_name or created_name
                raise GitError(
                    f"{label} 没有生成 {expected_full}，而是生成了 {shown}。请先删除同名仓库后再同步，避免留下带数字后缀的 fork",
                    retryable=False,
                )
            _wait_for_repository(parsed.owner, parsed.repo_name, platform, token, proxy, upstream)
        return
    if created.status_code == 422:
        raise GitError(
            f"无法在 {label} 账户 {login} 下{action} {parsed.repo_name}。同名仓库可能已存在，但当前令牌看不到它",
            retryable=False,
        )
    if created.status_code in {401, 403}:
        if action == "fork":
            raise GitError(f"没有权限把上游 fork 到 {label} 账户 {login} 的仓库 {parsed.repo_name}", retryable=False)
        raise GitError(f"没有权限在 {label} 账户 {login} 下创建仓库 {parsed.repo_name}", retryable=False)
    raise GitError(f"{action} {label} 仓库失败：HTTP {created.status_code}", retryable=created.status_code >= 500)


def _repository_info(owner: str, repo_name: str, platform: str, token: str, proxy: str) -> tuple[int, dict]:
    if platform == "github":
        url = f"https://api.github.com/repos/{owner}/{repo_name}"
    else:
        url = f"https://gitee.com/api/v5/repos/{owner}/{repo_name}"
    response = httpx.get(url, **_request_kwargs(platform, token, proxy))
    return response.status_code, _response_body(response)


def _fork_upstream(upstream: Upstream, repo_name: str, platform: str, token: str, proxy: str) -> httpx.Response:
    if platform == "github":
        return httpx.post(
            f"https://api.github.com/repos/{upstream.owner}/{upstream.repo_name}/forks",
            json={"name": repo_name, "default_branch_only": False},
            **_request_kwargs(platform, token, proxy),
        )
    return httpx.post(
        f"https://gitee.com/api/v5/repos/{upstream.owner}/{upstream.repo_name}/forks",
        data={"name": repo_name, "path": repo_name},
        **_request_kwargs(platform, token, proxy),
    )


def _wait_for_repository(owner: str, repo_name: str, platform: str, token: str, proxy: str, upstream: Upstream) -> None:
    label = "GitHub" if platform == "github" else "Gitee"
    for _ in range(8):
        status, body = _repository_info(owner, repo_name, platform, token, proxy)
        if status == 200 and _is_fork_of(body, upstream):
            return
        time.sleep(2)
    raise GitError(f"{label} 正在准备 fork，请稍后再试一次", retryable=True)


def _create_remote_repository(repo_name: str, platform: str, token: str, proxy: str) -> httpx.Response:
    if platform == "github":
        return httpx.post(
            "https://api.github.com/user/repos",
            json={"name": repo_name, "private": True, "auto_init": False},
            **_request_kwargs(platform, token, proxy),
        )
    return httpx.post(
        "https://gitee.com/api/v5/user/repos",
        data={"name": repo_name, "private": "true", "auto_init": "false"},
        **_request_kwargs(platform, token, proxy),
    )


def _delete_remote_repository(remote_url: str, platform: str, token: str, proxy: str) -> None:
    parsed = parse_upstream(remote_url)
    label = "GitHub" if platform == "github" else "Gitee"
    request_kwargs: dict = {"timeout": 30, "trust_env": False}
    if proxy:
        request_kwargs["proxy"] = proxy
    if platform == "github":
        response = httpx.delete(
            f"https://api.github.com/repos/{parsed.owner}/{parsed.repo_name}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "repository-sync",
            },
            **request_kwargs,
        )
    else:
        response = httpx.delete(
            f"https://gitee.com/api/v5/repos/{parsed.owner}/{parsed.repo_name}",
            params={"access_token": token},
            **request_kwargs,
        )
    if response.status_code in {200, 202, 204, 404}:
        return
    if response.status_code in {401, 403}:
        extra = "。删除已有仓库需要令牌具备 Administration 写入权限" if platform == "github" else ""
        raise GitError(f"没有权限删除 {label} 仓库 {parsed.owner}/{parsed.repo_name}{extra}", retryable=False)
    raise GitError(f"删除 {label} 仓库失败：HTTP {response.status_code}", retryable=response.status_code >= 500)


def repo_material(repo: Repo, timeout: int) -> str:
    mirror = Path(repo.local_path)
    branch = repo.default_branch or default_branch(mirror, timeout=timeout)
    readme = readme_text(mirror, branch, timeout=timeout)[:8000]
    files = tracked_files(mirror, branch, timeout=timeout)
    languages = language_summary(files)
    commits = recent_commits(mirror, branch, timeout=timeout, limit=10)
    language_text = "、".join(f"{item['name']} {item['percent']}%" for item in languages) or "未知"
    commit_text = "\n".join(f"- {item['subject']}" for item in commits) or "无"
    return (
        f"仓库：{repo.name}\n上游：{repo.upstream_url}\n主要语言：{language_text}\n"
        f"最近提交：\n{commit_text}\n\nREADME：\n{readme or '（无 README）'}"
    )
