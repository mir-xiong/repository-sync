from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import httpx

DAV = "{DAV:}"


class WebDavError(Exception):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class WebDavClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: float = 60, proxy: str = "") -> None:
        parsed = urlparse(base_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise WebDavError("WebDAV 地址需要是 http 或 https", retryable=False)
        self.base_url = base_url.strip().rstrip("/") + "/"
        self._client = httpx.Client(
            auth=httpx.BasicAuth(username, password),
            timeout=timeout,
            follow_redirects=True,
            proxy=proxy or None,
            trust_env=False,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> WebDavClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _url(self, remote_path: str) -> str:
        parts = [quote(part) for part in remote_path.strip("/").split("/") if part]
        return urljoin(self.base_url, "/".join(parts))

    def check(self) -> None:
        response = self._client.request("PROPFIND", self.base_url, headers={"Depth": "0"})
        if response.status_code in {401, 403}:
            raise WebDavError("WebDAV 认证失败", retryable=False)
        if response.status_code >= 400 and response.status_code not in {405, 207}:
            raise WebDavError(f"WebDAV 连接失败：HTTP {response.status_code}", retryable=response.status_code >= 500)

    def upload_directory(self, remote_dir: str, local_dir: Path) -> None:
        self._mkdirs(remote_dir)
        local_files: set[str] = set()
        for path in local_dir.rglob("*"):
            relative = path.relative_to(local_dir).as_posix()
            remote = f"{remote_dir.rstrip('/')}/{relative}"
            if path.is_dir():
                self._mkdirs(remote)
                continue
            if path.name == ".git":
                continue
            local_files.add(remote.strip("/"))
            self._mkdirs(str(Path(remote).parent).replace("\\", "/"))
            self._put(remote, path)
        existing = self._list_files(remote_dir)
        for remote in existing - local_files:
            self._delete("/" + remote)

    def delete_directory(self, remote_dir: str) -> None:
        response = self._client.request("DELETE", self._url(remote_dir), headers={"Depth": "infinity"})
        if response.status_code in {200, 202, 204, 404}:
            return
        raise WebDavError(f"删除 WebDAV 目录失败：HTTP {response.status_code}", retryable=response.status_code >= 500)

    def _mkdirs(self, remote_dir: str) -> None:
        current = ""
        for part in [item for item in remote_dir.strip("/").split("/") if item]:
            current += "/" + part
            response = self._client.request("MKCOL", self._url(current))
            if response.status_code in {200, 201, 301, 405}:
                continue
            if response.status_code == 409:
                continue
            raise WebDavError(f"创建 WebDAV 目录失败：HTTP {response.status_code}", retryable=response.status_code >= 500)

    def _put(self, remote_path: str, file_path: Path) -> None:
        with file_path.open("rb") as handle:
            response = self._client.put(self._url(remote_path), content=handle.read())
        if response.status_code not in {200, 201, 204}:
            retryable = response.status_code >= 500 or response.status_code in {408, 429}
            raise WebDavError(f"上传 {remote_path} 失败：HTTP {response.status_code}", retryable=retryable)

    def _delete(self, remote_path: str) -> None:
        response = self._client.request("DELETE", self._url(remote_path))
        if response.status_code not in {200, 202, 204, 404}:
            raise WebDavError(f"删除 {remote_path} 失败：HTTP {response.status_code}", retryable=response.status_code >= 500)

    def _list_files(self, remote_dir: str) -> set[str]:
        response = self._client.request(
            "PROPFIND",
            self._url(remote_dir),
            headers={"Depth": "infinity"},
            content=(
                '<?xml version="1.0" encoding="utf-8"?>'
                '<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>'
            ),
        )
        if response.status_code == 404:
            return set()
        if response.status_code not in {207, 200}:
            raise WebDavError(f"列出 WebDAV 目录失败：HTTP {response.status_code}", retryable=response.status_code >= 500)
        root = ET.fromstring(response.text)
        files: set[str] = set()
        base_path = urlparse(self.base_url).path.rstrip("/")
        for node in root.findall(f"{DAV}response"):
            href = node.findtext(f"{DAV}href") or ""
            resourcetype = node.find(f"{DAV}propstat/{DAV}prop/{DAV}resourcetype")
            is_collection = resourcetype is not None and resourcetype.find(f"{DAV}collection") is not None
            if is_collection:
                continue
            path = urlparse(href).path
            if base_path and path.startswith(base_path):
                path = path[len(base_path) :]
            files.add(path.strip("/"))
        return files
