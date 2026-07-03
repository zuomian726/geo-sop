"""
Local data paths for desktop/development runs.
"""
import os
import sys
from pathlib import Path


APP_NAME = "GEO-SOP"


def app_data_dir() -> str:
    override = os.environ.get("GEO_DATA_DIR")
    if override:
        path = Path(override).expanduser()
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    elif sys.platform.startswith("win"):
        path = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    else:
        path = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME

    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def instance_dir() -> str:
    path = Path(app_data_dir()) / "instance"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def database_path() -> str:
    return str(Path(instance_dir()) / "ai_monitor.db")


def answers_dir() -> str:
    path = Path(app_data_dir()) / "answers"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def browser_profile_dir() -> str:
    path = Path(app_data_dir()) / "browser_profile"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)
