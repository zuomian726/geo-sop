# GEO-SOP

GEO-SOP is a desktop and cloud workspace for monitoring how AI answer platforms
describe a brand. It collects answers locally, preserves screenshot evidence,
extracts reference sources, measures brand visibility, and supports keyword or
AI-assisted sentiment analysis.

## Product Architecture

- **Desktop client:** runs browser login and collection on the user's Windows or
  macOS computer. Local SQLite, browser profiles, screenshots, and exports stay
  in the current operating-system account.
- **Cloud workspace:** `geo.allgood.cn` provides registration, login, dashboard
  queries, remote task dispatch, history restore, and HTTPS synchronization.
- **Security boundary:** clients never receive MySQL credentials and never send
  AI-platform cookies to the server. Desktop API keys and cloud tokens are encrypted
  before local storage. AI API Keys are not synced by default and
  are never returned by configuration APIs.
- **Demo:** uses synthetic read-only data and cannot create tasks, control a
  desktop app, save settings, or alter production customer data.

## Supported Platforms

The canonical platform catalog currently includes Doubao, DeepSeek, Kimi,
Qianwen, Tencent Yuanbao, and Baidu Wenxin. Each collector uses a persistent
local browser profile so login state can survive normal app restarts.

## Customer Installation

Customers should use the native installers linked from
[geo.allgood.cn](https://geo.allgood.cn/):

- Windows 10/11 x64: one Setup EXE with Python runtime and Chromium included.
- macOS 12 or newer: separate DMGs for Apple Silicon and Intel.

Source bootstrap scripts are retained for development and recovery only. A
customer installation does not require Python, pip, PowerShell setup, or manual
Playwright installation.

## Local Data

Normal upgrades preserve the app data directory:

- Windows: `%LOCALAPPDATA%\GEO-SOP\`
- macOS: `~/Library/Application Support/GEO-SOP/`

The directory contains the local SQLite database, platform browser profiles,
collection evidence, and the revocable cloud login token. It must not be
committed to Git or bundled into a release.

## Development

Use Python 3.12 and the pinned desktop dependencies:

```bash
python3.12 -m venv .venv-desktop
.venv-desktop/bin/python -m pip install -r requirements-desktop.txt
.venv-desktop/bin/python -m playwright install chromium
```

Run the local development server:

```bash
GEO_DESKTOP_MODE=1 GEO_REQUIRE_LOGIN=0 \
  .venv-desktop/bin/python web_app/app.py
```

Run verification before committing:

```bash
.venv-desktop/bin/python -m unittest discover -s tests -v
.venv-desktop/bin/python tools/smoke_desktop_ui.py
python tools/smoke_cloud_site.py https://geo.allgood.cn
```

Windows and macOS installers are release artifacts. Windows packaging is manual
through GitHub Actions; source pushes run tests only. V1.0 release requirements
are tracked in [V1_ACCEPTANCE.md](V1_ACCEPTANCE.md), and product boundaries are
tracked in [ROADMAP.md](ROADMAP.md).

## Secrets and Customer Data

Do not add `.env` files, databases, screenshots, browser profiles, API Keys,
tokens, private server configuration, exports, or build artifacts to this
repository. Production configuration is injected through environment variables
and private files outside the public document root.
