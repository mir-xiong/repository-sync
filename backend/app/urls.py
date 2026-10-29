from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class UrlError(ValueError):
    pass


@dataclass(frozen=True)
class Upstream:
    canonical: str
    dedupe_key: str
    platform: str
    owner: str
    repo_name: str


def parse_upstream(url: str, *, allow_file: bool = False) -> Upstream:
    raw = url.strip()
    if allow_file and raw.startswith("/") and "://" not in raw:
        path = Path(raw)
        if not path.is_absolute():
            raise UrlError("本地上游必须是绝对路径")
        name = path.name or "repo"
        return Upstream(
            canonical=str(path),
            dedupe_key=f"file:{path}",
            platform="file",
            owner="local",
            repo_name=name,
        )
    if not raw.lower().startswith("https://"):
        raise UrlError("只接受 HTTPS 仓库地址")
    parsed = urlparse(raw)
    if parsed.username or parsed.password:
        raise UrlError("请不要在地址中携带账号或令牌")
    if parsed.query or parsed.fragment:
        raise UrlError("仓库地址不能包含查询参数")
    host = (parsed.hostname or "").lower()
    if host == "www.github.com":
        host = "github.com"
    if host == "www.gitee.com":
        host = "gitee.com"
    if host not in {"github.com", "gitee.com"}:
        raise UrlError("上游只支持 github.com 和 gitee.com")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise UrlError("地址需要是 https://主机/拥有者/仓库")
    owner, name = parts
    if name.endswith(".git"):
        name = name[: -len(".git")]
    if not owner or not name or owner in {".", ".."} or name in {".", ".."}:
        raise UrlError("仓库地址不完整")
    canonical = f"https://{host}/{owner}/{name}"
    return Upstream(
        canonical=canonical,
        dedupe_key=canonical.casefold(),
        platform="gitee" if host == "gitee.com" else "github",
        owner=owner,
        repo_name=name,
    )


def parse_git_target(url: str, platform: str) -> str:
    if platform not in {"gitee", "github"}:
        raise UrlError("目标平台不正确")
    parsed = parse_upstream(url, allow_file=False)
    if parsed.platform != platform:
        expected = "Gitee" if platform == "gitee" else "GitHub"
        raise UrlError(f"该目标必须是 {expected} 仓库地址")
    return parsed.canonical


def parse_webdav_remote(path: str) -> str:
    raw = path.strip()
    if not raw.startswith("/"):
        raise UrlError("WebDAV 目录需要以 / 开头")
    if "\\" in raw or any(part == ".." for part in raw.split("/")):
        raise UrlError("WebDAV 目录不能包含 ..")
    collapsed = "/" + "/".join(part for part in raw.split("/") if part)
    return collapsed or "/"


def auth_https_url(canonical: str, platform: str, token: str) -> str:
    if not token or platform == "file":
        return canonical
    if platform == "github":
        return canonical.replace("https://", f"https://x-access-token:{token}@", 1)
    if platform == "gitee":
        return canonical.replace("https://", f"https://oauth2:{token}@", 1)
    return canonical


def redact(text: str) -> str:
    import re

    return re.sub(r"https://[^/\s@]+@", "https://", text or "")
