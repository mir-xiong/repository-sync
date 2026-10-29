from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.crypto import decrypt_text, encrypt_text
from app.directory_picker import DirectoryPickerBusy, DirectoryPickerError, pick_directory
from app.deps import get_db, require_admin
from app.models import Admin, AiProvider, AppSetting
from app.proxy import normalize_proxy, require_proxy, stored_proxy
from app.schemas import (
    CredentialTestIn,
    CredentialsPatch,
    LocalDirectoryIn,
    ModelListIn,
    ProviderIn,
    ProviderPatch,
    ProxyTestIn,
    SettingsPatch,
    provider_dict,
)
from app.storage import apply_local_directory, current_local_root
from app.scheduler import purge_expired_logs
from app.summary_service import list_models, test_provider
from app.webdav_client import WebDavClient, WebDavError

router = APIRouter(prefix="/api", tags=["settings"])


def _settings_row(db: Session) -> AppSetting:
    row = db.query(AppSetting).one_or_none()
    if row is None:
        row = AppSetting(log_retention_days=7, sync_concurrency=2)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _settings_dict(row: AppSetting, request: Request) -> dict:
    return {
        "log_retention_days": row.log_retention_days,
        "sync_concurrency": row.sync_concurrency,
        "local_mirror_dir": str(current_local_root(request.app.state.settings, row)),
        "proxy_url": row.proxy_url or "",
        "gitee_token_set": bool(row.gitee_token_encrypted),
        "github_token_set": bool(row.github_token_encrypted),
        "webdav_url": row.webdav_url,
        "webdav_username": row.webdav_username,
        "webdav_password_set": bool(row.webdav_password_encrypted),
    }


@router.get("/settings")
def get_settings(request: Request, db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)) -> dict:
    return _settings_dict(_settings_row(db), request)


@router.patch("/settings")
def patch_settings(
    payload: SettingsPatch,
    request: Request,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    row = _settings_row(db)
    if payload.log_retention_days is not None:
        row.log_retention_days = payload.log_retention_days
        purge_expired_logs(db, row.log_retention_days)
    if payload.sync_concurrency is not None:
        row.sync_concurrency = payload.sync_concurrency
    if payload.proxy_url is not None:
        row.proxy_url = normalize_proxy(payload.proxy_url)
    db.commit()
    db.refresh(row)
    return _settings_dict(row, request)


@router.post("/settings/proxy/test")
def test_proxy(
    payload: ProxyTestIn,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    url = normalize_proxy(payload.proxy_url if payload.proxy_url is not None else stored_proxy(db))
    if not url:
        raise HTTPException(status_code=400, detail="请先填写代理地址")
    try:
        response = httpx.get("https://github.com", proxy=url, timeout=20, follow_redirects=True, trust_env=False)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"代理连接失败：{exc}") from exc
    if response.status_code >= 500:
        raise HTTPException(status_code=400, detail=f"代理返回 HTTP {response.status_code}")
    return {"ok": True}


@router.post("/settings/local-directory/browse")
async def browse_local_directory(
    request: Request,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    default = current_local_root(request.app.state.settings, _settings_row(db))
    try:
        path = await run_in_threadpool(pick_directory, default)
    except DirectoryPickerBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DirectoryPickerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": path}


@router.post("/settings/local-directory")
def change_local_directory(
    payload: LocalDirectoryIn,
    request: Request,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    result = apply_local_directory(
        db,
        request.app.state.settings,
        request.app.state.coordinator,
        payload.path,
        migrate=payload.migrate,
    )
    row = _settings_row(db)
    return {**_settings_dict(row, request), **result}


@router.patch("/settings/credentials")
def patch_credentials(
    payload: CredentialsPatch,
    request: Request,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    row = _settings_row(db)
    fernet = request.app.state.fernet
    if payload.clear_gitee_token:
        row.gitee_token_encrypted = ""
    elif payload.gitee_token:
        row.gitee_token_encrypted = encrypt_text(fernet, payload.gitee_token.strip())
    if payload.clear_github_token:
        row.github_token_encrypted = ""
    elif payload.github_token:
        row.github_token_encrypted = encrypt_text(fernet, payload.github_token.strip())
    if payload.webdav_url is not None:
        row.webdav_url = payload.webdav_url.strip()
    if payload.webdav_username is not None:
        row.webdav_username = payload.webdav_username.strip()
    if payload.clear_webdav_password:
        row.webdav_password_encrypted = ""
    elif payload.webdav_password:
        row.webdav_password_encrypted = encrypt_text(fernet, payload.webdav_password)
    db.commit()
    return _settings_dict(row, request)


@router.post("/settings/credentials/test")
def test_credentials(
    payload: CredentialTestIn,
    request: Request,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    row = _settings_row(db)
    fernet = request.app.state.fernet
    try:
        if payload.target == "github":
            _test_github(decrypt_text(fernet, row.github_token_encrypted))
        elif payload.target == "gitee":
            _test_gitee(decrypt_text(fernet, row.gitee_token_encrypted))
        else:
            password = decrypt_text(fernet, row.webdav_password_encrypted)
            if not row.webdav_url:
                raise HTTPException(status_code=400, detail="请先填写 WebDAV 地址")
            with WebDavClient(row.webdav_url, row.webdav_username, password) as client:
                client.check()
    except HTTPException:
        raise
    except WebDavError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


def _test_github(token: str) -> None:
    if not token:
        raise HTTPException(status_code=400, detail="请先保存 GitHub 令牌")
    response = httpx.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "repository-sync"},
        timeout=20,
    )
    if response.status_code == 401:
        raise HTTPException(status_code=400, detail="GitHub 令牌无效")
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"GitHub 返回 HTTP {response.status_code}")


def _test_gitee(token: str) -> None:
    if not token:
        raise HTTPException(status_code=400, detail="请先保存 Gitee 令牌")
    response = httpx.get("https://gitee.com/api/v5/user", params={"access_token": token}, timeout=20)
    if response.status_code == 401:
        raise HTTPException(status_code=400, detail="Gitee 令牌无效")
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Gitee 返回 HTTP {response.status_code}")


@router.get("/ai/providers")
def list_providers(db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)) -> dict:
    rows = db.query(AiProvider).order_by(AiProvider.id.asc()).all()
    return {"items": [provider_dict(row) for row in rows]}


@router.post("/ai/providers")
def create_provider(
    payload: ProviderIn,
    request: Request,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    if db.query(AiProvider).count() >= 20:
        raise HTTPException(status_code=422, detail="最多保存 20 个 AI 厂商")
    require_proxy(db, payload.use_proxy)
    if payload.enabled:
        db.query(AiProvider).update({AiProvider.enabled: False})
    row = AiProvider(
        name=payload.name.strip(),
        base_url=payload.base_url.strip().rstrip("/"),
        model=payload.model.strip(),
        enabled=payload.enabled,
        use_proxy=payload.use_proxy,
        api_key_encrypted=encrypt_text(request.app.state.fernet, (payload.api_key or "").strip()),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return provider_dict(row)


@router.patch("/ai/providers/{provider_id}")
def update_provider(
    provider_id: int,
    payload: ProviderPatch,
    request: Request,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    row = _provider(db, provider_id)
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.base_url is not None:
        row.base_url = payload.base_url.strip().rstrip("/")
    if payload.model is not None:
        row.model = payload.model.strip()
    if payload.api_key:
        row.api_key_encrypted = encrypt_text(request.app.state.fernet, payload.api_key.strip())
    if payload.enabled is True:
        db.query(AiProvider).filter(AiProvider.id != row.id).update({AiProvider.enabled: False})
        row.enabled = True
    elif payload.enabled is False:
        row.enabled = False
    if payload.use_proxy is not None:
        require_proxy(db, payload.use_proxy)
        row.use_proxy = payload.use_proxy
    db.commit()
    db.refresh(row)
    return provider_dict(row)


@router.delete("/ai/providers/{provider_id}")
def delete_provider(provider_id: int, db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)) -> dict:
    row = _provider(db, provider_id)
    if row.enabled:
        raise HTTPException(status_code=422, detail="启用中的厂商不能删除，请先停用")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/ai/providers/{provider_id}/secret")
def provider_secret(
    provider_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    row = _provider(db, provider_id)
    return {"api_key": decrypt_text(request.app.state.fernet, row.api_key_encrypted)}


@router.post("/ai/models")
def provider_models(
    payload: ModelListIn,
    request: Request,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    api_key = (payload.api_key or "").strip()
    if not api_key and payload.provider_id is not None:
        api_key = decrypt_text(request.app.state.fernet, _provider(db, payload.provider_id).api_key_encrypted)
    proxy = require_proxy(db, payload.use_proxy)
    try:
        items = list_models(payload.base_url.strip().rstrip("/"), api_key, proxy or None)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": items}


@router.post("/ai/providers/{provider_id}/test")
def test_ai_provider(
    provider_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> dict:
    row = _provider(db, provider_id)
    try:
        test_provider(row, request.app.state.coordinator)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


def _provider(db: Session, provider_id: int) -> AiProvider:
    row = db.get(AiProvider, provider_id)
    if row is None:
        raise HTTPException(status_code=404, detail="厂商不存在")
    return row
