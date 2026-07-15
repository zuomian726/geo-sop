"""Application release metadata."""

APP_NAME = "GEO-SOP"
APP_VERSION = "0.3.33-dev"
APP_CHANNEL = "desktop"
BUILD_DATE = "2026-07-16"
BUILD_NUMBER = "20260716.6"


def app_info() -> dict:
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "channel": APP_CHANNEL,
        "build_date": BUILD_DATE,
        "build_number": BUILD_NUMBER,
    }
