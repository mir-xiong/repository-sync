from __future__ import annotations

import httpx
from fastapi import HTTPException


def account_login(platform: str, token: str, proxy: str = "") -> str:
    if platform not in {"github", "gitee"}:
        raise HTTPException(status_code=422, detail="目标平台不正确")
    if not token:
        name = "GitHub" if platform == "github" else "Gitee"
        raise HTTPException(status_code=422, detail=f"请先在设置中配置 {name} 令牌")
    request_kwargs: dict = {"timeout": 20, "trust_env": False}
    if proxy:
        request_kwargs["proxy"] = proxy
    try:
        if platform == "github":
            response = httpx.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "repository-sync",
                },
                **request_kwargs,
            )
        else:
            response = httpx.get("https://gitee.com/api/v5/user", params={"access_token": token}, **request_kwargs)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="无法连接平台账户") from exc
    name = "GitHub" if platform == "github" else "Gitee"
    if response.status_code == 401:
        raise HTTPException(status_code=422, detail=f"{name} 令牌无效")
    if response.status_code >= 400:
        raise HTTPException(status_code=422, detail=f"无法读取{name}账户：HTTP {response.status_code}")
    login = ""
    try:
        body = response.json()
        if isinstance(body, dict) and isinstance(body.get("login"), str):
            login = body["login"].strip()
    except Exception:
        login = ""
    if not login or login in {".", ".."} or any(char.isspace() or char in "/\\" for char in login):
        raise HTTPException(status_code=422, detail=f"无法从{name}令牌识别账户")
    return login
