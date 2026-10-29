from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from app.crypto import decrypt_text
from app.models import AiProvider, Repo
from app.sync_service import SyncCoordinator, repo_material


def active_provider(db: Session) -> AiProvider | None:
    return db.query(AiProvider).filter(AiProvider.enabled.is_(True)).one_or_none()


def generate_summary(coordinator: SyncCoordinator, repo_id: int) -> str | None:
    db = coordinator.sessions()
    try:
        repo = db.get(Repo, repo_id)
        provider = active_provider(db)
        if repo is None:
            return "仓库不存在"
        if provider is None:
            return "还没有启用的 AI 厂商。请到设置里启用一个，再生成概要"
        try:
            material = repo_material(repo, coordinator.settings.git_timeout_seconds)
            text = chat_completion(provider, coordinator, material)
        except Exception as exc:  # noqa: BLE001 — 概要失败不能影响同步结果
            return str(exc)[:500]
        repo.summary = text[:4000]
        repo.summary_source = "ai"
        db.commit()
        return None
    finally:
        db.close()


def chat_completion(provider: AiProvider, coordinator: SyncCoordinator, user_content: str) -> str:
    api_key = decrypt_text(coordinator.fernet, provider.api_key_encrypted)
    url = provider.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": provider.model,
        "temperature": 0.3,
        "messages": [
            {
                "role": "system",
                "content": "你是代码仓库介绍撰写助手。只输出一段中文概要，150到300字，不要标题、列表或 Markdown。",
            },
            {"role": "user", "content": user_content},
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=60, proxy=_provider_proxy(provider, coordinator), trust_env=False)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"AI 请求失败：{exc}") from exc
    if response.status_code >= 400:
        raise RuntimeError(f"AI 返回 HTTP {response.status_code}")
    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("AI 响应中没有概要内容") from exc
    text = str(content).strip()
    if not text:
        raise RuntimeError("AI 返回了空概要")
    return text


def test_provider(provider: AiProvider, coordinator: SyncCoordinator) -> None:
    chat_completion(provider, coordinator, "只回复 OK")


def list_models(base_url: str, api_key: str, proxy: str | None) -> list[str]:
    url = base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = httpx.get(url, headers=headers, timeout=30, proxy=proxy, trust_env=False)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"获取模型列表失败：{exc}") from exc
    if response.status_code >= 400:
        raise RuntimeError(f"模型列表返回 HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("模型列表不是有效的 JSON") from exc
    rows = body.get("data") if isinstance(body, dict) else None
    names = [str(item["id"]) for item in rows or [] if isinstance(item, dict) and item.get("id")]
    if not names:
        raise RuntimeError("接口没有返回可用模型")
    return names


def _provider_proxy(provider: AiProvider, coordinator: SyncCoordinator) -> str | None:
    if not provider.use_proxy:
        return None
    db = coordinator.sessions()
    try:
        from app.models import AppSetting

        row = db.query(AppSetting).one_or_none()
        url = (row.proxy_url or "").strip() if row else ""
    finally:
        db.close()
    if not url:
        raise RuntimeError("已选择使用代理，但设置里还没有代理地址")
    return url
