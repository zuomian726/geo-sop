"""Application release metadata."""

APP_NAME = "GEO-SOP"
APP_VERSION = "1.0.0"
APP_CHANNEL = "stable"
BUILD_DATE = "2026-07-17"
BUILD_NUMBER = "20260717.1"


def app_info() -> dict:
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "channel": APP_CHANNEL,
        "build_date": BUILD_DATE,
        "build_number": BUILD_NUMBER,
    }
