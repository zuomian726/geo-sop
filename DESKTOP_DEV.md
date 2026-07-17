# GEO-SOP Desktop Development

The production desktop client requires the same cloud account used at
`geo.allgood.cn`. Browser login, collection, screenshots, SQLite, and AI API
Keys remain local; task metadata and results synchronize through authenticated
HTTPS APIs.

## Development launch

```bash
GEO_DESKTOP_MODE=1 \
GEO_REQUIRE_LOGIN=1 \
GEO_CLOUD_SYNC_URL=https://geo.allgood.cn/api \
./run_macos_desktop.sh
```

For an isolated UI test that must not contact the cloud, set
`GEO_REQUIRE_LOGIN=0`, `GEO_CLOUD_SYNC_ENABLED=0`, and a temporary
`GEO_DATA_DIR`.

## Runtime data

macOS stores runtime data under:

```text
~/Library/Application Support/GEO-SOP/
```

Windows stores runtime data under:

```text
%LOCALAPPDATA%\GEO-SOP\
```

Key paths include:

```text
instance/ai_monitor.db   local SQLite database
browser_profiles/       per-user AI platform login state
answers/                answers and screenshot evidence
cloud_account.json      revocable cloud token, current-user permissions only
```

Do not run release builds against a customer data directory. Packaging uses an
explicit asset allowlist and must pass the bundle scan before publication.
