"""
Browser profile path helpers.

Each web user gets an isolated Playwright/Chrome profile per platform so AI
platform cookies do not leak across accounts.
"""
import os
import re
import shutil
from local_paths import browser_profile_dir


PROFILE_DIR = os.environ.get(
    "GEO_PROFILE_DIR",
    browser_profile_dir() if os.environ.get("GEO_DESKTOP_MODE") == "1" else os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_profile"),
)


def _safe_segment(value) -> str:
    value = str(value)
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def get_profile_dir(platform_key: str, user_id=None, allow_legacy: bool = True) -> str:
    platform = _safe_segment(platform_key)
    if user_id is None:
        return os.path.join(PROFILE_DIR, platform)

    user_profile = os.path.join(PROFILE_DIR, "users", _safe_segment(user_id), platform)

    # Keep the original admin account working without forcing every platform to
    # log in again immediately after the multi-user migration.
    legacy_profile = os.path.join(PROFILE_DIR, platform)
    if allow_legacy and str(user_id) == "1" and not os.path.exists(user_profile) and os.path.exists(legacy_profile):
        return legacy_profile

    return user_profile


def clear_profile_dir(platform_key: str, user_id=None) -> tuple[bool, str]:
    profile_dir = get_profile_dir(platform_key, user_id)
    if not os.path.exists(profile_dir):
        return False, profile_dir

    shutil.rmtree(profile_dir)
    return True, profile_dir
