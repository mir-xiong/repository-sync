from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def _fernet_from_secret(secret: str) -> Fernet:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def build_fernet(secret_key: str, data_dir: Path) -> Fernet:
    if secret_key.strip():
        return _fernet_from_secret(secret_key.strip())
    path = data_dir / "secret.key"
    if path.is_file():
        stored = path.read_text(encoding="utf-8").strip()
        if stored:
            return _fernet_from_secret(stored)
    data_dir.mkdir(parents=True, exist_ok=True)
    generated = Fernet.generate_key().decode("utf-8")
    path.write_text(generated, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return _fernet_from_secret(generated)


def encrypt_text(fernet: Fernet, value: str) -> str:
    if not value:
        return ""
    return fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(fernet: Fernet, value: str) -> str:
    if not value:
        return ""
    try:
        return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ""
