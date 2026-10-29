from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def find_env_file() -> Path | None:
    candidates = [Path.cwd() / ".env", repo_root() / ".env"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    initial_admin_password: str = Field(default="", alias="INITIAL_ADMIN_PASSWORD")
    admin_password_reset: bool = Field(default=False, alias="ADMIN_PASSWORD_RESET")
    data_dir: str = Field(default="", alias="DATA_DIR")
    database_url: str = Field(default="", alias="DATABASE_URL")
    secret_key: str = Field(default="", alias="SECRET_KEY")
    scheduler_enabled: bool = Field(default=True, alias="SCHEDULER_ENABLED")
    allow_file_upstreams: bool = Field(default=False, alias="ALLOW_FILE_UPSTREAMS")
    cors_origins: str = Field(
        default="http://127.0.0.1:5173,http://localhost:5173",
        alias="CORS_ORIGINS",
    )
    git_timeout_seconds: int = Field(default=600, alias="GIT_TIMEOUT_SECONDS")

    def resolved_data_dir(self) -> Path:
        raw = self.data_dir.strip()
        if not raw:
            return repo_root() / "data"
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = repo_root() / path
        return path

    def resolved_database_url(self) -> str:
        if self.database_url.strip():
            return self.database_url.strip()
        db_path = self.resolved_data_dir() / "app.db"
        return f"sqlite:///{db_path}"

    def origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


def load_dotenv() -> None:
    env_path = find_env_file()
    if env_path is None:
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_settings() -> Settings:
    load_dotenv()
    return Settings()
