"""Encrypt desktop-only credentials before they are written to local storage."""
from __future__ import annotations

import os
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from local_paths import app_data_dir


PREFIX = "enc:v1:"
_key_lock = threading.Lock()


def _key_path() -> Path:
    return Path(app_data_dir()) / "desktop_secret.key"


def _load_key() -> bytes:
    path = _key_path()
    with _key_lock:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            key = Fernet.generate_key()
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(key)
            except FileExistsError:
                pass
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return path.read_bytes().strip()


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(PREFIX))


def encrypt_secret(value: str | None) -> str | None:
    if not value or is_encrypted(value):
        return value
    encrypted = Fernet(_load_key()).encrypt(value.encode("utf-8")).decode("ascii")
    return PREFIX + encrypted


def decrypt_secret(value: str | None) -> str | None:
    if not value or not is_encrypted(value):
        return value
    try:
        token = value[len(PREFIX) :].encode("ascii")
        return Fernet(_load_key()).decrypt(token).decode("utf-8")
    except (InvalidToken, ValueError, OSError, UnicodeError):
        return None
