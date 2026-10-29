from __future__ import annotations

import base64
import os
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path

from app.urls import redact

GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
_PROXY_KEYS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy")
_git_proxy: ContextVar[str] = ContextVar("git_proxy", default="")


class GitError(Exception):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


def _classify(stderr: str, returncode: int) -> GitError:
    text = redact(stderr).strip() or f"git 退出码 {returncode}"
    lowered = text.lower()
    fatal_markers = (
        "authentication failed",
        "invalid username or password",
        "permission denied",
        "access denied",
        "repository not found",
        "not found",
        "could not read username",
        "terminal prompts disabled",
        "403",
        "401",
    )
    retry_markers = (
        "could not resolve",
        "timed out",
        "connection reset",
        "unable to connect",
        "rpc failed",
        "early eof",
        "the remote end hung up",
        "failed to connect",
        "temporary failure",
        "network",
    )
    if any(marker in lowered for marker in fatal_markers):
        return GitError(text, retryable=False)
    if any(marker in lowered for marker in retry_markers):
        return GitError(text, retryable=True)
    return GitError(text, retryable=False)


def git_env() -> dict[str, str]:
    env = {key: value for key, value in GIT_ENV.items() if key not in _PROXY_KEYS}
    proxy = _git_proxy.get()
    if proxy:
        env["http_proxy"] = proxy
        env["https_proxy"] = proxy
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy
    return env


def current_git_proxy() -> str:
    return _git_proxy.get()


@contextmanager
def git_proxy(url: str | None) -> Iterator[None]:
    token: Token[str] = _git_proxy.set((url or "").strip())
    try:
        yield
    finally:
        _git_proxy.reset(token)


def run_git(args: list[str], *, timeout: int, cwd: Path | None = None) -> str:
    command = ["git", "-c", "safe.directory=*", *args]
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=git_env(),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError("git 执行超时", retryable=True) from exc
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace")
        stdout = completed.stdout.decode("utf-8", errors="replace")
        raise _classify(stderr or stdout, completed.returncode)
    return completed.stdout.decode("utf-8", errors="replace")


def clone_or_update(dest: Path, clean_url: str, auth_url: str, *, timeout: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not dest.exists():
            run_git(["clone", "--mirror", auth_url, str(dest)], timeout=timeout)
        else:
            run_git(["-C", str(dest), "remote", "set-url", "origin", auth_url], timeout=timeout)
            run_git(["-C", str(dest), "remote", "update", "--prune", "origin"], timeout=timeout)
    finally:
        if dest.exists():
            try:
                run_git(["-C", str(dest), "remote", "set-url", "origin", clean_url], timeout=timeout)
            except GitError:
                pass


def ls_remote(auth_url: str, *, timeout: int) -> dict[str, str]:
    text = run_git(["ls-remote", "--heads", "--tags", auth_url], timeout=timeout)
    return _parse_remote_refs(text)


def list_local_refs(dest: Path, *, timeout: int) -> dict[str, str]:
    try:
        text = run_git(["-C", str(dest), "show-ref", "--dereference"], timeout=timeout)
    except GitError:
        return {}
    return _parse_remote_refs(text)


def _parse_remote_refs(text: str) -> dict[str, str]:
    peeled: dict[str, str] = {}
    plain: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        sha, name = parts[0], parts[1]
        if name.endswith("^{}"):
            peeled[name[: -len("^{}")]] = sha
        elif name.startswith("refs/heads/") or name.startswith("refs/tags/"):
            plain[name] = sha
    plain.update(peeled)
    return plain


def fetch_check_refs(dest: Path, auth_url: str, *, timeout: int) -> dict[str, str]:
    run_git(
        [
            "-C",
            str(dest),
            "fetch",
            auth_url,
            "+refs/heads/*:refs/sync-check/heads/*",
            "+refs/tags/*:refs/sync-check/tags/*",
        ],
        timeout=timeout,
    )
    text = run_git(["-C", str(dest), "show-ref"], timeout=timeout)
    fetched: dict[str, str] = {}
    check_names: list[str] = []
    for line in text.splitlines():
        sha, _, name = line.partition(" ")
        if name.startswith("refs/sync-check/heads/"):
            fetched["refs/heads/" + name.removeprefix("refs/sync-check/heads/")] = sha
            check_names.append(name)
        elif name.startswith("refs/sync-check/tags/") and not name.endswith("^{}"):
            fetched["refs/tags/" + name.removeprefix("refs/sync-check/tags/")] = sha
            check_names.append(name)
    for name in check_names:
        try:
            run_git(["-C", str(dest), "update-ref", "-d", name], timeout=timeout)
        except GitError:
            pass
    return fetched


def is_ancestor(dest: Path, ancestor: str, descendant: str, *, timeout: int) -> bool:
    try:
        run_git(["-C", str(dest), "merge-base", "--is-ancestor", ancestor, descendant], timeout=timeout)
        return True
    except GitError:
        return False


def default_branch(dest: Path, *, timeout: int) -> str:
    try:
        name = run_git(["-C", str(dest), "symbolic-ref", "--short", "HEAD"], timeout=timeout).strip()
        if name:
            return name.removeprefix("refs/heads/")
    except GitError:
        pass
    return "HEAD"


def count_refs(dest: Path, *, timeout: int) -> tuple[int, int]:
    refs = list_local_refs(dest, timeout=timeout)
    branches = sum(1 for name in refs if name.startswith("refs/heads/"))
    tags = sum(1 for name in refs if name.startswith("refs/tags/"))
    return branches, tags


def directory_size(dest: Path) -> int:
    total = 0
    if not dest.exists():
        return 0
    for path in dest.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total


def list_tree(dest: Path, branch: str, path: str, *, timeout: int) -> list[dict[str, str]]:
    spec = branch if not path else f"{branch}:{path.strip('/')}"
    text = run_git(["-C", str(dest), "ls-tree", "-l", spec], timeout=timeout)
    entries: list[dict[str, str]] = []
    for line in text.splitlines():
        meta, _, filename = line.partition("\t")
        mode, kind, _sha, *rest = meta.split()
        if kind == "tree":
            entry_type = "dir"
        elif kind == "commit":
            entry_type = "submodule"
        else:
            entry_type = "file"
        size = rest[0] if rest and rest[0].isdigit() else ""
        child = f"{path.strip('/')}/{filename}".strip("/")
        entries.append({"name": filename, "path": child, "type": entry_type, "mode": mode, "size": size})
    entries.sort(key=lambda item: (item["type"] != "dir", item["name"].casefold()))
    return entries


def read_file(dest: Path, branch: str, path: str, *, timeout: int, limit: int = 200_000) -> tuple[str, bool]:
    proc = subprocess.run(
        ["git", "-c", "safe.directory=*", "-C", str(dest), "show", f"{branch}:{path}"],
        capture_output=True,
        timeout=timeout,
        check=False,
        env=git_env(),
    )
    if proc.returncode != 0:
        message = redact(proc.stderr.decode("utf-8", errors="replace"))
        raise GitError(message or "无法读取文件", retryable=False)
    data = proc.stdout
    if b"\x00" in data[:4096]:
        raise GitError("无法预览二进制文件", retryable=False)
    truncated = len(data) > limit
    text = data[:limit].decode("utf-8", errors="replace")
    return text, truncated


def recent_commits(dest: Path, branch: str, *, timeout: int, limit: int = 20) -> list[dict[str, str]]:
    text = run_git(
        ["-C", str(dest), "log", f"-n{limit}", "--format=%H%x1f%an%x1f%aI%x1f%s", branch],
        timeout=timeout,
    )
    commits: list[dict[str, str]] = []
    for line in text.splitlines():
        sha, author, authored_at, subject = (line.split("\x1f") + ["", "", "", ""])[:4]
        commits.append({"sha": sha, "author": author, "authored_at": authored_at, "subject": subject})
    return commits


_IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
}


def read_image(dest: Path, branch: str, path: str, *, timeout: int, limit: int = 8_000_000) -> tuple[bytes, str]:
    media = _IMAGE_TYPES.get(Path(path).suffix.lower())
    if media is None:
        raise GitError("不是可显示的图片", retryable=False)
    proc = subprocess.run(
        ["git", "-c", "safe.directory=*", "-C", str(dest), "show", f"{branch}:{path}"],
        capture_output=True,
        timeout=timeout,
        check=False,
        env=git_env(),
    )
    if proc.returncode != 0:
        message = redact(proc.stderr.decode("utf-8", errors="replace"))
        raise GitError(message or "无法读取图片", retryable=False)
    if len(proc.stdout) > limit:
        raise GitError("图片超过 8MB，无法预览", retryable=False)
    return proc.stdout, media


def preview_file(dest: Path, branch: str, path: str, *, timeout: int, limit: int = 200_000) -> dict[str, str | bool | int]:
    proc = subprocess.run(
        ["git", "-c", "safe.directory=*", "-C", str(dest), "show", f"{branch}:{path}"],
        capture_output=True,
        timeout=timeout,
        check=False,
        env=git_env(),
    )
    if proc.returncode != 0:
        message = redact(proc.stderr.decode("utf-8", errors="replace"))
        raise GitError(message or "无法读取文件", retryable=False)
    data = proc.stdout
    suffix = Path(path).suffix.lower()
    media = _IMAGE_TYPES.get(suffix)
    if media and len(data) <= 1_500_000:
        return {
            "path": path,
            "kind": "image",
            "media_type": media,
            "content": base64.b64encode(data).decode("ascii"),
            "truncated": False,
            "size": len(data),
        }
    if media or b"\x00" in data[:8192]:
        return {"path": path, "kind": "binary", "media_type": "", "content": "", "truncated": False, "size": len(data)}
    truncated = len(data) > limit
    return {
        "path": path,
        "kind": "text",
        "media_type": "text/plain",
        "content": data[:limit].decode("utf-8", errors="replace"),
        "truncated": truncated,
        "size": len(data),
    }


def readme_text(dest: Path, branch: str, *, timeout: int) -> str:
    for name in ("README.md", "readme.md", "README.markdown", "README.txt", "README"):
        try:
            text, _truncated = read_file(dest, branch, name, timeout=timeout, limit=12000)
            return text
        except GitError:
            continue
    return ""


def tracked_files(dest: Path, branch: str, *, timeout: int) -> list[str]:
    text = run_git(["-C", str(dest), "ls-tree", "-r", "--name-only", branch], timeout=timeout)
    return [line for line in text.splitlines() if line]


def export_worktree(dest: Path, branch: str, target_dir: Path, *, timeout: int) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(
        ["git", "-c", "safe.directory=*", "-C", str(dest), "archive", "--format=tar", branch],
        capture_output=True,
        timeout=timeout,
        check=False,
        env=git_env(),
    )
    if archive.returncode != 0:
        raise GitError(redact(archive.stderr.decode("utf-8", errors="replace")) or "无法导出工作区", retryable=False)
    extract = subprocess.run(
        ["tar", "-x", "-C", str(target_dir)],
        input=archive.stdout,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if extract.returncode != 0:
        raise GitError("无法解包工作区", retryable=False)


def push_mirror(dest: Path, auth_url: str, *, timeout: int) -> None:
    refspecs: list[str] = []
    if run_git(["-C", str(dest), "for-each-ref", "--format=%(refname)", "refs/heads"], timeout=timeout).strip():
        refspecs.append("+refs/heads/*:refs/heads/*")
    if run_git(["-C", str(dest), "for-each-ref", "--format=%(refname)", "refs/tags"], timeout=timeout).strip():
        refspecs.append("+refs/tags/*:refs/tags/*")
    if not refspecs:
        return
    run_git(["-C", str(dest), "push", "--prune", auth_url, *refspecs], timeout=timeout)


def classify_refs(
    local: dict[str, str],
    remote: dict[str, str],
    is_ancestor_fn: Callable[[str, str], bool],
) -> str:
    if local == remote:
        return "same"
    behind = False
    diverged = False
    for name in set(local) | set(remote):
        left = local.get(name)
        right = remote.get(name)
        if left is None and right is not None:
            behind = True
            continue
        if right is None and left is not None:
            diverged = True
            continue
        if left == right or left is None or right is None:
            continue
        local_is_older = is_ancestor_fn(left, right)
        remote_is_older = is_ancestor_fn(right, left)
        if local_is_older and not remote_is_older:
            behind = True
        else:
            diverged = True
    if diverged:
        return "diverged"
    if behind:
        return "behind"
    return "same"


LANGUAGE_BY_EXT = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".java": "Java",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".vue": "Vue",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".md": "Markdown",
    ".json": "JSON",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".sh": "Shell",
    ".sql": "SQL",
}


def language_summary(paths: list[str]) -> list[dict[str, int | str]]:
    counts: dict[str, int] = {}
    total = 0
    for path in paths:
        suffix = Path(path).suffix.lower()
        language = LANGUAGE_BY_EXT.get(suffix)
        if not language:
            continue
        counts[language] = counts.get(language, 0) + 1
        total += 1
    if total == 0:
        return []
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:6]
    return [{"name": name, "count": count, "percent": round(count * 100 / total)} for name, count in ranked]
