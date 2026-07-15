from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from local_paths import app_data_dir

logger = logging.getLogger(__name__)

LEGACY_CONFIG_FILE = Path(__file__).resolve().with_name("browser_config.json")

_DEFAULT_CANDIDATES = [
    # Linux
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    # Windows
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\\Microsoft\\Edge\\Application\\msedge.exe"),
]

def browser_config_path() -> Path:
    """Return the per-user config path, which is writable in installed apps."""
    return Path(app_data_dir()) / "browser_config.json"


def _default_config() -> dict:
    return {"browser_path": "", "candidates": list(_DEFAULT_CANDIDATES)}


def _normalize_config(data) -> dict:
    if not isinstance(data, dict):
        return _default_config()

    browser_path = data.get("browser_path")
    candidates = data.get("candidates")
    return {
        "browser_path": browser_path.strip() if isinstance(browser_path, str) else "",
        "candidates": [item for item in candidates if isinstance(item, str) and item.strip()]
        if isinstance(candidates, list)
        else list(_DEFAULT_CANDIDATES),
    }


def _read_config(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _normalize_config(data)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Browser config could not be loaded from %s: %s", path, exc)
        return None


def _write_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(_normalize_config(config), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def load_browser_config():
    config_path = browser_config_path()
    if config_path.exists():
        config = _read_config(config_path)
        if config is not None:
            return config

    # Versions before v0.3.34 wrote this file beside the executable. Import it
    # once when available, then keep all future writes in the user data folder.
    if LEGACY_CONFIG_FILE != config_path and LEGACY_CONFIG_FILE.exists():
        legacy_config = _read_config(LEGACY_CONFIG_FILE)
        if legacy_config is not None and legacy_config.get("browser_path"):
            try:
                _write_config(config_path, legacy_config)
            except OSError as exc:
                logger.warning("Legacy browser config could not be migrated: %s", exc)
            return legacy_config

    return _default_config()

def save_browser_config(browser_path):
    config = load_browser_config()
    config["browser_path"] = str(browser_path or "").strip()
    _write_config(browser_config_path(), config)
    return True

def get_browser_candidates():
    config = load_browser_config()
    candidates = []
    if config.get("browser_path"):
        candidates.append(config["browser_path"])
    candidates.extend(config.get("candidates", []))
    candidates.extend(_DEFAULT_CANDIDATES)

    seen = set()
    unique_candidates = []
    for path in candidates:
        if path and path not in seen:
            seen.add(path)
            unique_candidates.append(path)
    return unique_candidates
