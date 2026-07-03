#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv-desktop" ]; then
  python3 -m venv .venv-desktop
fi

source .venv-desktop/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt

export GEO_DESKTOP_MODE=1
python desktop_app.py
