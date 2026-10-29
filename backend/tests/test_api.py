from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for key in (
        "INITIAL_ADMIN_PASSWORD",
        "ADMIN_PASSWORD_RESET",
        "DATA_DIR",
        "DATABASE_URL",
        "SECRET_KEY",
        "SCHEDULER_ENABLED",
        "ALLOW_FILE_UPSTREAMS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "secret-pass")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("SCHEDULER_ENABLED", "0")
    monkeypatch.setenv("ALLOW_FILE_UPSTREAMS", "1")
    monkeypatch.setenv("ADMIN_PASSWORD_RESET", "0")
    app = create_app(Settings())
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, password: str = "secret-pass") -> None:
    response = client.post("/api/auth/login", json={"password": password})
    assert response.status_code == 200, response.text


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_source(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    (path / "README.md").write_text("# Demo\n\n一个用于测试的仓库。\n", encoding="utf-8")
    (path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (path / "src").mkdir()
    (path / "src" / "note.txt").write_text("nested\n", encoding="utf-8")
    (path / "dot.png").write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    ))
    git(path, "add", ".")
    git(path, "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "init")


def test_login_and_password_rotation(client: TestClient) -> None:
    assert client.get("/api/repos").status_code == 401
    login(client)
    assert client.get("/api/auth/me").status_code == 200
    previous = client.cookies.get("rs_session")
    changed = client.post("/api/auth/password", json={"current_password": "secret-pass", "new_password": "new-secret"})
    assert changed.status_code == 200, changed.text
    current = client.cookies.get("rs_session")
    assert current and current != previous
    client.cookies.set("rs_session", previous or "")
    assert client.get("/api/settings").status_code == 401
    client.cookies.set("rs_session", current)
    assert client.get("/api/settings").status_code == 200
    assert client.post("/api/auth/login", json={"password": "secret-pass"}).status_code == 401


def test_retention_limit(client: TestClient) -> None:
    login(client)
    ok = client.patch("/api/settings", json={"log_retention_days": 7, "sync_concurrency": 2})
    assert ok.status_code == 200
    rejected = client.patch("/api/settings", json={"log_retention_days": 181})
    assert rejected.status_code == 422
    rejected_low = client.patch("/api/settings", json={"log_retention_days": 0})
    assert rejected_low.status_code == 422


def test_only_one_ai_provider_enabled(client: TestClient) -> None:
    login(client)
    first = client.post(
        "/api/ai/providers",
        json={"name": "甲", "base_url": "https://example.com/v1", "api_key": "k1", "model": "m", "enabled": True},
    )
    second = client.post(
        "/api/ai/providers",
        json={"name": "乙", "base_url": "https://example.com/v1", "api_key": "k2", "model": "m", "enabled": True},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    items = client.get("/api/ai/providers").json()["items"]
    enabled = [item for item in items if item["enabled"]]
    assert len(enabled) == 1
    assert enabled[0]["name"] == "乙"
    blocked = client.delete(f"/api/ai/providers/{second.json()['id']}")
    assert blocked.status_code == 422
    assert "不能删除" in blocked.json()["detail"]
    assert client.patch(f"/api/ai/providers/{second.json()['id']}", json={"enabled": False}).status_code == 200
    assert client.delete(f"/api/ai/providers/{second.json()['id']}").status_code == 200
    assert items[0]["api_key_set"] is True
    assert "k1" not in str(items)


def test_summary_requires_enabled_provider_and_returns_generated_text(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    login(client)
    source = tmp_path / "summary-source"
    make_source(source)
    created = client.post("/api/repos", json={"upstream_url": str(source), "schedule": {"type": "daily", "time": "09:30"}, "targets": []})
    assert created.status_code == 200, created.text
    repo_id = created.json()["repo"]["id"]
    missing = client.post(f"/api/repos/{repo_id}/summary")
    assert missing.status_code == 400
    assert "启用" in missing.json()["detail"]
    provider = client.post(
        "/api/ai/providers",
        json={"name": "演示", "base_url": "https://example.invalid/v1", "api_key": "k", "model": "demo", "enabled": True},
    )
    assert provider.status_code == 200, provider.text
    monkeypatch.setattr("app.summary_service.chat_completion", lambda provider, coordinator, content: "这是一段仓库概要。")
    generated = client.post(f"/api/repos/{repo_id}/summary")
    assert generated.status_code == 200, generated.text
    assert generated.json()["summary"] == "这是一段仓库概要。"


def test_add_list_detail_and_diff(client: TestClient, tmp_path: Path) -> None:
    login(client)
    source = tmp_path / "source"
    make_source(source)
    bad = client.post(
        "/api/repos",
        json={"upstream_url": str(source), "schedule": {"type": "cron", "cron": "not a cron"}},
    )
    assert bad.status_code == 422
    created = client.post(
        "/api/repos",
        json={
            "upstream_url": str(source),
            "schedule": {"type": "daily", "time": "09:30"},
            "targets": [],
        },
    )
    assert created.status_code == 200, created.text
    repo = created.json()["repo"]
    assert repo["sync_status"] == "success"
    assert repo["diff_status"] == "same"
    assert repo["platform"] == "file"
    assert (tmp_path / "mirrors" / f"{repo['id']}.git").exists()
    listed = client.get("/api/repos", params={"q": "source"}).json()["items"]
    assert len(listed) == 1
    tree = client.get(f"/api/repos/{repo['id']}/tree").json()
    assert tree["entries"][0]["name"] == "src"
    assert tree["entries"][0]["type"] == "dir"
    nested = client.get(f"/api/repos/{repo['id']}/tree", params={"path": "src"}).json()
    assert nested["entries"][0]["name"] == "note.txt"
    note = client.get(f"/api/repos/{repo['id']}/file", params={"path": "src/note.txt"})
    assert note.json()["kind"] == "text"
    assert "nested" in note.json()["content"]
    image = client.get(f"/api/repos/{repo['id']}/file", params={"path": "dot.png"})
    assert image.json()["kind"] == "image"
    assert image.json()["media_type"] == "image/png"
    readme = client.get(f"/api/repos/{repo['id']}/file", params={"path": "README.md"})
    assert readme.json()["kind"] == "text"
    assert "测试" in readme.json()["content"]
    commits = client.get(f"/api/repos/{repo['id']}/commits").json()["items"]
    assert commits[0]["subject"] == "init"
    same = client.post(f"/api/repos/{repo['id']}/diff")
    assert same.status_code == 200, same.text
    assert same.json()["diff_status"] == "same"
    (source / "README.md").write_text("# Demo\n\n更新了。\n", encoding="utf-8")
    git(source, "add", "README.md")
    git(source, "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "update")
    behind = client.post(f"/api/repos/{repo['id']}/diff")
    assert behind.status_code == 200, behind.text
    assert behind.json()["diff_status"] == "behind"
    logs = client.get("/api/logs").json()["items"]
    assert logs[0]["trigger"] == "initial"
    assert logs[0]["upstream_status"] == "success"
    removed = client.delete(f"/api/repos/{repo['id']}")
    assert removed.status_code == 200
    assert client.get("/api/repos").json()["items"] == []


def test_duplicate_upstream_rejected(client: TestClient, tmp_path: Path) -> None:
    login(client)
    source = tmp_path / "source"
    make_source(source)
    body = {"upstream_url": str(source), "schedule": {"type": "weekly", "time": "10:00", "weekday": 1}}
    assert client.post("/api/repos", json=body).status_code == 200
    assert client.post("/api/repos", json=body).status_code == 409


def test_save_methods_and_local_directory(client: TestClient, tmp_path: Path) -> None:
    login(client)
    assert client.post(
        "/api/repos",
        json={"upstream_url": "https://github.com/octocat/Hello-World", "schedule": {"type": "daily", "time": "09:30"}, "save_local": False, "targets": []},
    ).status_code == 422
    missing_account = client.post(
        "/api/repos",
        json={
            "upstream_url": "https://github.com/octocat/Hello-World",
            "schedule": {"type": "daily", "time": "09:30"},
            "targets": [{"target_type": "github", "remote_url": "https://github.com/octocat/Hello-World"}],
        },
    )
    assert missing_account.status_code == 422
    assert "GitHub" in missing_account.json()["detail"]
    source = tmp_path / "only-local"
    make_source(source)
    created = client.post(
        "/api/repos",
        json={"upstream_url": str(source), "schedule": {"type": "daily", "time": "09:30"}},
    )
    assert created.status_code == 200, created.text
    repo = created.json()["repo"]
    assert repo["save_local"] is True
    assert repo["storages"][0]["type"] == "local"
    old_mirror = Path(repo["storages"][0]["location"])
    assert old_mirror.exists()
    moved_root = tmp_path / "moved"
    moved = client.post("/api/settings/local-directory", json={"path": str(moved_root), "migrate": True})
    assert moved.status_code == 200, moved.text
    assert (moved_root / f"{repo['id']}.git").exists()
    assert not old_mirror.exists()
    configured = client.patch(
        "/api/settings/credentials",
        json={"webdav_url": "https://dav.example.com/webdav", "webdav_username": "ada"},
    )
    assert configured.status_code == 200, configured.text
    kept = client.patch(
        f"/api/repos/{repo['id']}",
        json={"targets": [{"target_type": "webdav", "remote_url": "/keep"}]},
    )
    assert kept.status_code == 200, kept.text
    other = tmp_path / "other"
    make_source(other)
    second = client.post(
        "/api/repos",
        json={"upstream_url": str(other), "schedule": {"type": "daily", "time": "09:30"}},
    ).json()["repo"]
    second_mirror = Path(second["storages"][0]["location"])
    declined = client.post("/api/settings/local-directory", json={"path": str(tmp_path / "fresh"), "migrate": False})
    assert declined.status_code == 200, declined.text
    assert second["name"] in [item["name"] for item in declined.json()["removed"]]
    assert client.get(f"/api/repos/{second['id']}").status_code == 404
    assert second_mirror.exists()
    survivor = client.get(f"/api/repos/{repo['id']}").json()
    assert survivor["save_local"] is False
    assert [item["type"] for item in survivor["storages"]] == ["webdav"]


def test_save_method_without_address_uses_account(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    login(client)
    source = tmp_path / "demo-repo"
    make_source(source)
    created = client.post("/api/repos", json={"upstream_url": str(source), "schedule": {"type": "daily", "time": "09:30"}})
    assert created.status_code == 200, created.text
    repo = created.json()["repo"]
    configured = client.patch(
        "/api/settings/credentials",
        json={"github_token": "ghp_example", "webdav_url": "https://dav.example.com/webdav", "webdav_username": "ada"},
    )
    assert configured.status_code == 200, configured.text
    webdav = client.patch(
        f"/api/repos/{repo['id']}",
        json={"save_local": True, "targets": [{"target_type": "webdav", "remote_url": ""}]},
    )
    assert webdav.status_code == 200, webdav.text
    assert webdav.json()["targets"][0]["remote_url"] == f"/{repo['owner']}/{repo['repo_name']}"
    monkeypatch.setattr("app.routers.repos.account_login", lambda platform, token, proxy="": "ada")
    github = client.patch(
        f"/api/repos/{repo['id']}",
        json={"save_local": True, "targets": [{"target_type": "github", "remote_url": ""}]},
    )
    assert github.status_code == 200, github.text
    assert github.json()["targets"][0]["remote_url"] == f"https://github.com/ada/{repo['repo_name']}"


def test_delete_removes_remote_repository(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    login(client)
    source = tmp_path / "kept-upstream"
    make_source(source)
    created = client.post("/api/repos", json={"upstream_url": str(source), "schedule": {"type": "daily", "time": "09:30"}})
    assert created.status_code == 200, created.text
    repo = created.json()["repo"]
    configured = client.patch("/api/settings/credentials", json={"github_token": "ghp_example"})
    assert configured.status_code == 200, configured.text
    saved = client.patch(
        f"/api/repos/{repo['id']}",
        json={"save_local": True, "targets": [{"target_type": "github", "remote_url": "https://github.com/ada/mirror"}]},
    )
    assert saved.status_code == 200, saved.text
    calls: list[str] = []

    class Response:
        status_code = 204

    def fake_delete(url: str, **kwargs: object) -> Response:
        calls.append(url)
        assert kwargs["headers"]["Authorization"] == "Bearer ghp_example"
        return Response()

    monkeypatch.setattr("app.sync_service.httpx.delete", fake_delete)
    removed = client.delete(f"/api/repos/{repo['id']}")
    assert removed.status_code == 200, removed.text
    assert calls == ["https://api.github.com/repos/ada/mirror"]
    assert client.get(f"/api/repos/{repo['id']}").status_code == 404


def test_credentials_round_trip_without_echo(client: TestClient) -> None:
    login(client)
    saved = client.patch("/api/settings/credentials", json={"github_token": "ghp_example", "webdav_url": "https://dav.example.com/remote.php/webdav", "webdav_username": "ada"})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["github_token_set"] is True
    assert "ghp_example" not in str(body)
    assert body["webdav_username"] == "ada"


def test_browse_directory_returns_selected_path(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    login(client)
    chosen = tmp_path / "chosen"
    monkeypatch.setattr("app.routers.settings.pick_directory", lambda default: str(chosen))
    response = client.post("/api/settings/local-directory/browse")
    assert response.status_code == 200, response.text
    assert response.json()["path"] == str(chosen)


def test_browse_directory_cancel_keeps_current_path(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    login(client)
    monkeypatch.setattr("app.routers.settings.pick_directory", lambda default: None)
    response = client.post("/api/settings/local-directory/browse")
    assert response.status_code == 200, response.text
    assert response.json()["path"] is None


def test_proxy_and_ai_models_and_secret(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    login(client)
    rejected = client.patch("/api/settings", json={"proxy_url": "socks5://127.0.0.1:1080"})
    assert rejected.status_code == 422
    blocked = client.post(
        "/api/repos",
        json={
            "upstream_url": "https://github.com/octocat/Hello-World",
            "schedule": {"type": "daily", "time": "09:30", "paused": False},
            "use_proxy": True,
        },
    )
    assert blocked.status_code == 422
    assert "代理" in blocked.json()["detail"]
    saved = client.patch("/api/settings", json={"proxy_url": "http://127.0.0.1:7890"})
    assert saved.status_code == 200
    assert saved.json()["proxy_url"] == "http://127.0.0.1:7890"
    created = client.post(
        "/api/ai/providers",
        json={"name": "本地", "base_url": "https://example.com/v1", "api_key": "sk-visible", "model": "m", "use_proxy": True},
    )
    assert created.status_code == 200, created.text
    provider_id = created.json()["id"]
    secret = client.get(f"/api/ai/providers/{provider_id}/secret")
    assert secret.status_code == 200
    assert secret.json()["api_key"] == "sk-visible"
    listed = client.get("/api/ai/providers").json()["items"]
    assert "sk-visible" not in str(listed)

    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {"data": [{"id": "demo-model"}, {"id": ""}]}

    monkeypatch.setattr("app.summary_service.httpx.get", lambda *args, **kwargs: FakeResponse())
    models = client.post("/api/ai/models", json={"base_url": "https://example.com/v1", "provider_id": provider_id, "use_proxy": True})
    assert models.status_code == 200, models.text
    assert models.json()["items"] == ["demo-model"]
    cleared = client.patch("/api/settings", json={"proxy_url": ""})
    assert cleared.status_code == 200
    assert cleared.json()["proxy_url"] == ""


def test_missing_github_repository_is_created_before_push(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.git_ops import GitError
    from app.sync_service import _ensure_remote_repository

    calls: list[tuple] = []

    class Response:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    def fake_get(url: str, **kwargs: object) -> Response:
        calls.append(("GET", url))
        headers = kwargs["headers"]
        assert isinstance(headers, dict)
        assert headers["Authorization"] == "Bearer ghp_example"
        return Response(404)

    def fake_post(url: str, **kwargs: object) -> Response:
        calls.append(("POST", url, kwargs.get("json")))
        return Response(201)

    monkeypatch.setattr("app.sync_service.httpx.get", fake_get)
    monkeypatch.setattr("app.sync_service.httpx.post", fake_post)
    monkeypatch.setattr("app.sync_service.account_login", lambda platform, token, proxy="": "mir-xiong")
    _ensure_remote_repository("https://github.com/mir-xiong/Hello-World", "github", "ghp_example", "")
    assert calls[0] == ("GET", "https://api.github.com/repos/mir-xiong/Hello-World")
    assert calls[1] == ("POST", "https://api.github.com/user/repos", {"name": "Hello-World", "private": True, "auto_init": False})

    def existing_get(url: str, **kwargs: object) -> Response:
        calls.append(("GET", url))
        return Response(200)

    monkeypatch.setattr("app.sync_service.httpx.get", existing_get)
    before = len(calls)
    _ensure_remote_repository("https://github.com/mir-xiong/Hello-World", "github", "ghp_example", "")
    assert [item[0] for item in calls[before:]] == ["GET"]

    monkeypatch.setattr("app.sync_service.httpx.get", fake_get)
    monkeypatch.setattr("app.sync_service.account_login", lambda platform, token, proxy="": "ada")
    with pytest.raises(GitError, match="只能在账户 ada 下创建"):
        _ensure_remote_repository("https://github.com/mir-xiong/Hello-World", "github", "ghp_example", "")


def test_same_platform_target_forks_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.git_ops import GitError
    from app.sync_service import _ensure_remote_repository

    calls: list[tuple] = []
    posted = {"done": False}
    fork_body = {"fork": True, "name": "Hello-World", "full_name": "mir-xiong/Hello-World", "parent": {"full_name": "octocat/Hello-World"}}

    class Response:
        def __init__(self, status_code: int, body: dict | None = None) -> None:
            self.status_code = status_code
            self._body = body or {}

        def json(self) -> dict:
            return self._body

    def fake_get(url: str, **kwargs: object) -> Response:
        calls.append(("GET", url))
        if posted["done"]:
            return Response(200, fork_body)
        return Response(404)

    def fake_post(url: str, **kwargs: object) -> Response:
        calls.append(("POST", url, kwargs.get("json")))
        posted["done"] = True
        return Response(202, fork_body)

    monkeypatch.setattr("app.sync_service.httpx.get", fake_get)
    monkeypatch.setattr("app.sync_service.httpx.post", fake_post)
    monkeypatch.setattr("app.sync_service.account_login", lambda platform, token, proxy="": "mir-xiong")
    _ensure_remote_repository(
        "https://github.com/mir-xiong/Hello-World",
        "github",
        "ghp_example",
        "",
        "https://github.com/octocat/Hello-World",
    )
    assert ("POST", "https://api.github.com/repos/octocat/Hello-World/forks", {"name": "Hello-World", "default_branch_only": False}) in calls
    assert not any(item[1] == "https://api.github.com/user/repos" for item in calls if item[0] == "POST")

    posted["done"] = False
    calls.clear()

    def already_fork(url: str, **kwargs: object) -> Response:
        calls.append(("GET", url))
        return Response(200, fork_body)

    monkeypatch.setattr("app.sync_service.httpx.get", already_fork)
    _ensure_remote_repository(
        "https://github.com/mir-xiong/Hello-World",
        "github",
        "ghp_example",
        "",
        "https://github.com/octocat/Hello-World",
    )
    assert [item[0] for item in calls] == ["GET"]

    calls.clear()

    def plain_repo(url: str, **kwargs: object) -> Response:
        calls.append(("GET", url))
        if any(item[0] == "DELETE" for item in calls):
            return Response(200, fork_body)
        return Response(200, {"fork": False, "full_name": "mir-xiong/Hello-World"})

    def fake_delete(url: str, **kwargs: object) -> Response:
        calls.append(("DELETE", url))
        return Response(204)

    monkeypatch.setattr("app.sync_service.httpx.get", plain_repo)
    monkeypatch.setattr("app.sync_service.httpx.delete", fake_delete)
    _ensure_remote_repository(
        "https://github.com/mir-xiong/Hello-World",
        "github",
        "ghp_example",
        "",
        "https://github.com/octocat/Hello-World",
    )
    assert ("DELETE", "https://api.github.com/repos/mir-xiong/Hello-World") in calls
    assert ("POST", "https://api.github.com/repos/octocat/Hello-World/forks", {"name": "Hello-World", "default_branch_only": False}) in calls

    def denied_delete(url: str, **kwargs: object) -> Response:
        return Response(403)

    calls.clear()
    monkeypatch.setattr("app.sync_service.httpx.get", plain_repo)
    monkeypatch.setattr("app.sync_service.httpx.delete", denied_delete)
    with pytest.raises(GitError, match="Administration"):
        _ensure_remote_repository(
            "https://github.com/mir-xiong/Hello-World",
            "github",
            "ghp_example",
            "",
            "https://github.com/octocat/Hello-World",
        )
    assert not any(item[0] == "POST" for item in calls)

    calls.clear()

    def hidden(url: str, **kwargs: object) -> Response:
        calls.append(("GET", url))
        return Response(403)

    monkeypatch.setattr("app.sync_service.httpx.get", hidden)
    with pytest.raises(GitError, match="避免生成带数字后缀"):
        _ensure_remote_repository(
            "https://github.com/mir-xiong/Hello-World",
            "github",
            "ghp_example",
            "",
            "https://github.com/octocat/Hello-World",
        )
    assert not any(item[0] == "POST" for item in calls)


def test_retry_failed_save_target(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    login(client)
    source = tmp_path / "retry-source"
    make_source(source)
    created = client.post("/api/repos", json={"upstream_url": str(source), "schedule": {"type": "daily", "time": "09:30"}})
    assert created.status_code == 200, created.text
    repo = created.json()["repo"]
    configured = client.patch("/api/settings/credentials", json={"github_token": "ghp_example"})
    assert configured.status_code == 200, configured.text
    saved = client.patch(
        f"/api/repos/{repo['id']}",
        json={"save_local": True, "targets": [{"target_type": "github", "remote_url": "https://github.com/ada/mirror"}]},
    )
    assert saved.status_code == 200, saved.text
    calls = {"count": 0}

    def fake_sync_target(*args: object, **kwargs: object) -> tuple[str, str]:
        calls["count"] += 1
        if calls["count"] == 1:
            return "failed", "remote: Repository not found"
        return "success", ""

    monkeypatch.setattr("app.sync_service._sync_target", fake_sync_target)
    synced = client.post(f"/api/repos/{repo['id']}/sync")
    assert synced.status_code == 200, synced.text
    target = synced.json()["repo"]["targets"][0]
    assert target["last_status"] == "failed"
    kept_failed = client.patch(
        f"/api/repos/{repo['id']}",
        json={"use_proxy": False, "targets": [{"target_type": "github", "remote_url": "https://github.com/ada/mirror"}]},
    )
    assert kept_failed.status_code == 200, kept_failed.text
    target = kept_failed.json()["targets"][0]
    assert target["last_status"] == "failed"
    assert "Repository not found" in target["last_error"]
    storage = next(item for item in kept_failed.json()["storages"] if item["type"] == "github")
    assert storage["id"] == target["id"]
    denied = client.post(f"/api/repos/{repo['id']}/targets/999999/retry")
    assert denied.status_code == 404
    retried = client.post(f"/api/repos/{repo['id']}/targets/{target['id']}/retry")
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "success"
    assert retried.json()["repo"]["targets"][0]["last_status"] == "success"
    assert retried.json()["repo"]["sync_status"] == "success"
    logs = client.get("/api/logs", params={"repo_id": repo["id"]})
    assert logs.status_code == 200, logs.text
    assert any(item["trigger"] == "retry" and item["upstream_status"] == "skipped" for item in logs.json()["items"])
    again = client.post(f"/api/repos/{repo['id']}/targets/{target['id']}/retry")
    assert again.status_code == 422
    kept = client.patch(
        f"/api/repos/{repo['id']}",
        json={"name": repo["name"], "targets": [{"target_type": "github", "remote_url": "https://github.com/ada/mirror"}]},
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["targets"][0]["last_status"] == "success"


def test_push_mirror_skips_hidden_pull_refs(tmp_path: Path) -> None:
    from app.git_ops import push_mirror

    work = tmp_path / "work"
    source = tmp_path / "source.git"
    dest = tmp_path / "dest.git"
    work.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(work)], check=True, capture_output=True)
    (work / "README.md").write_text("hi\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(work), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(work), "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "-C", str(work), "tag", "v1"], check=True, capture_output=True)
    subprocess.run(["git", "clone", "--mirror", str(work), str(source)], check=True, capture_output=True)
    sha = subprocess.run(
        ["git", "--git-dir", str(source), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "--git-dir", str(source), "update-ref", "refs/pull/1/head", sha], check=True, capture_output=True)
    subprocess.run(["git", "init", "--bare", str(dest)], check=True, capture_output=True)
    push_mirror(source, str(dest), timeout=30)
    refs = subprocess.run(["git", "--git-dir", str(dest), "show-ref"], check=True, capture_output=True, text=True).stdout
    assert "refs/heads/main" in refs
    assert "refs/tags/v1" in refs
    assert "refs/pull/" not in refs
