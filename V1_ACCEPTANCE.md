# GEO-SOP V1.0 Acceptance

V1.0 is released once, after the desktop clients, cloud workspace, Demo, sync
protocol, installers, and public download page pass the same release gate. The
current production packages remain unchanged while this checklist is open.

## Product Boundary

V1.0 covers reliable brand detection and sentiment analysis. Fully unattended
scheduled GEO automation remains the V2.0 product boundary, although V1.0 may
receive and execute an explicit cloud task while the signed-in desktop client
is online.

## Release Gates

### Account and local data

- First launch requires the same cloud account used by `geo.allgood.cn`.
- Registration and login preserve form input after recoverable errors.
- Reinstalling or upgrading does not delete local tasks, platform profiles, or
  historical results.
- A clean installation restores the signed-in account's cloud history without
  duplicating users, tasks, or results.
- Local SQLite remains the desktop source of truth; MySQL is reachable only
  through authenticated HTTPS APIs.

### Collection

- Every supported platform can be checked, logged in, collected, screenshotted,
  and diagnosed from the same workflow.
- A page-structure change, expired login, timeout, or network error produces a
  clear task/result error and a recoverable next action.
- Closing and reopening the app does not leave a task permanently `running`.
- Brand exposure, references, rank, and sentiment use documented definitions.

### Sync and cloud tasks

- Local changes sync non-destructively and are isolated by cloud user.
- One-click upload includes statistics and all available screenshots without a
  file picker.
- A cloud-created task is claimed exactly once by the correct signed-in client.
- Completion, failure, results, screenshots, and terminal status return to the
  cloud automatically, with retry after a temporary outage.
- Heartbeats, tokens, and payloads never include platform cookies or AI API Keys.

### Analysis and exports

- Desktop and cloud dashboards expose the same core metrics, filters, details,
  pagination, references, trends, and GEO manuscript analysis.
- Keyword sentiment and optional OpenAI/Anthropic-compatible analysis have
  bounded timeouts, useful errors, and a deterministic local fallback.
- Saved AI API Keys are never returned by an API, logged, synced by default, or
  included in exported files.
- Excel, screenshot ZIP, and long-image exports have visible save locations and
  open successfully with large accounts.

### Desktop experience

- Windows 10/11 x64 installs from one Setup EXE without Python or manual
  dependency installation.
- Apple Silicon and Intel macOS builds install from a DMG with an Applications
  shortcut and the same product identity.
- Login, first-run guidance, browser setup, platform login, collection, sync,
  analysis, export, update, and error recovery are usable at the minimum window
  size without clipped controls.
- The update prompt uses stable official URLs, verifies release metadata, and
  preserves local data.

### Cloud and Demo

- Production registration, login, dashboard, remote tasks, sync APIs, exports,
  pagination, screenshot display, and account isolation pass the acceptance
  pipeline.
- Demo contains synthetic data only, opens in one click, mirrors core query and
  export behavior, and blocks all writes and desktop control.
- Public pages use GEO-SOP branding, commercial copy, responsive media, and
  permanent Windows/macOS download links.

### Security and operations

- No credentials, customer databases, browser profiles, screenshots, tokens,
  build outputs, or private server configuration are tracked by Git.
- Sessions, API tokens, upload validation, query limits, and per-user ownership
  are covered by tests.
- Database migrations are versioned, repeatable, and backed up before the V1.0
  deployment.
- macOS notarization and Windows code signing are either completed for V1.0 or
  explicitly recorded as release blockers; unsigned builds are not labelled as
  a commercial stable release.

## Final Verification

1. Run the full unit and contract test suite.
2. Run real-browser desktop UI checks at minimum and standard window sizes.
3. Run the production cloud/Demo smoke suite against a staging deployment.
4. Run the disposable two-account desktop/cloud pipeline and clean its data.
5. Install and launch the native Windows Setup EXE on Windows 10/11.
6. Install and launch both macOS DMGs from clean user data directories.
7. Scan Git and all packages for secrets and local/customer data.
8. Build once, publish V1.0 once, update permanent links once, then repeat the
   production smoke and update checks.

## Current Local Verification

This section records development evidence without changing production packages.

- Unit and contract suite: 134 tests passing on 2026-07-17.
- Real-browser desktop UI: login, task recovery, task creation, and verified
  update dialogs pass at 1000x700 and 1440x900. Cloud-to-desktop GEO deep
  links, 30-day date filters, responsive controls, and zero horizontal overflow
  pass at both sizes.
- Cloud-to-desktop links now open platform login, AI settings, collection
  limits, and browser settings in the matching desktop workflow. Collection
  and browser setting dialogs pass real-browser checks at both release sizes.
- Desktop and cloud GEO manuscript analysis now share multi-task manuscript
  filtering, date-range filters, title grouping, and URL/article-ID matching.
- Fresh-schema staging Demo: 6 synthetic tasks, 144 synthetic results, 4 GEO
  manuscripts, and 6 platforms; query/export and read-only smoke passed.
- Disposable two-account staging pipeline: registration, desktop login,
  heartbeat, workspace/history sync, private statistics and screenshots, cloud
  analysis, remote-task execution, cross-account isolation, and both export
  formats passed end to end.
- Database sessions now inherit the PHP runtime timezone, preventing new
  heartbeats from being misclassified as eight-hour-old offline clients.
- The strengthened V1 cloud smoke now requires CSRF-protected registration and
  Demo login plus account-private screenshots. Current legacy production is
  intentionally rejected until the one-time V1 deployment.
- Stable publishing is prepare-only by default and requires notarized macOS
  DMGs, valid Windows Authenticode evidence, matching versions and hashes, and
  a clean Git worktree. Versioned files and permanent aliases are staged before
  `update.json` is switched last.
- Tracked-file audit: no databases, browser profiles, screenshots, private
  configuration, certificates, private keys, or common live API Key formats.
- Pending final release gates: native Windows install, both native macOS
  installs, Apple notarization, and Windows Authenticode signing.
