# GEO-SOP Release Notes

## v0.3.13-dev - 2026-07-09

Cloud-to-desktop AI settings routing patch.

### Fixed

- Cloud dashboard AI settings button now opens the real desktop "智慧舆情设置" tab.
- Desktop dashboard now accepts both `#ai-settings` and `#sentiment_settings` hashes for backward compatibility.
- Cloud dashboard copy now explains that AI API URL, key, and model are configured locally for security.

## v0.3.12-dev - 2026-07-09

Windows bootstrap installer patch.

### Added

- Added `Install GEO-SOP.bat` and `Install GEO-SOP.ps1` as a bootstrap installer.
- The installer automatically installs Python 3.12 through Windows Package Manager when Python 3.10+ is missing.
- `Start GEO-SOP.bat`, `install.bat`, and the installer now all route users through the same first-run setup.
- Added an Inno Setup script and `build_windows_installer.bat` for building a real Windows setup EXE on Windows.

## v0.3.11-dev - 2026-07-09

Windows first-run reliability patch.

### Fixed

- `install.bat` now forwards to the desktop launcher instead of the old web-app dependency installer.
- Windows launcher now prefers the `py -3` launcher, verifies Python 3.10+, and avoids Windows Store Python aliases.
- First launch now installs the Playwright Chromium runtime before starting the desktop app.

## v0.3.10-dev - 2026-07-09

Windows batch compatibility patch.

### Fixed

- Windows launcher scripts now use ASCII-only command text and Windows CRLF line endings in the distribution ZIP.
- Fixed `cmd.exe` parsing failures where commands such as `pause`, `pip`, and `set` could be read incorrectly on Windows.

## v0.3.9-dev - 2026-07-09

Windows launcher patch.

### Fixed

- Added a clear Windows entry script, `Start GEO-SOP.bat`, for normal users.
- Windows launcher now uses safer local paths, verifies required files before startup, and shows readable recovery messages when the ZIP is not fully extracted or Python is missing.
- Windows README now separates the normal launch path from the developer-only EXE build script.

## v0.3.8-dev - 2026-07-07

Desktop launch integration patch.

### Fixed

- macOS app now registers the `geo-sop://` URL scheme so cloud dashboard buttons can launch the local desktop app.
- Desktop startup understands `geo-sop://open?target=...` links and opens the matching local workspace area.

## v0.3.7-dev - 2026-07-07

Cloud result upload patch.

### Added

- One-click cloud upload for the signed-in desktop workspace.
- Local collection statistics are uploaded with the current account, install ID, task count, result count, platform coverage, and screenshot coverage.
- Local screenshot evidence is uploaded automatically from saved collection results, without requiring users to choose image files manually.
- Server-side asset storage API for deduplicated screenshot uploads.

## v0.3.6-dev - 2026-07-06

Desktop update distribution patch.

### Added

- Stable macOS and Windows download URLs for long-term distribution.
- Desktop update check against the geo.allgood.cn update manifest.
- In-app update notification with a direct download button when a newer version is available.

## v0.3.5-dev - 2026-07-06

Cloud restore and legacy data migration patch.

### Added

- Desktop login can restore cloud history into a fresh local workspace.
- Cloud restore API returns synced tasks, results, manuscripts, and sentiment settings for the signed-in account.
- Legacy single-user SQLite data can be uploaded to a cloud account without exposing old local AI API keys.

### Fixed

- Restored tasks keep cloud source metadata so repeated installs do not duplicate the same historical task set.

## v0.3.4-dev - 2026-07-06

Desktop/cloud sync reliability patch.

### Fixed

- Desktop task completion now triggers a final blocking cloud sync, so finished tasks and collected results appear on geo.allgood.cn.
- Existing local-only workspace records are adopted into the signed-in cloud account, preventing old single-user tasks from staying invisible online.
- Cloud sync no longer depends on a volatile runtime flag after the desktop app restarts; a saved cloud URL and token are enough to keep sync active.

## v0.3.3-dev - 2026-07-03

Brand identity alignment patch.

### Changed

- Unified the desktop app icon, local header icon, website favicon, and download-page app icon to the blue "G" mark.
- Updated the local dashboard header brand text to "AI 答案".
- Rebuilt the macOS app icon so Dock and Finder no longer use the old GEO icon.

## v0.3.2-dev - 2026-07-03

Desktop/cloud account alignment patch.

### Fixed

- Desktop app now requires the geo.allgood.cn cloud account login on first launch.
- Removed the default local-only auto login from the packaged desktop launcher.
- Existing old `local` desktop sessions are redirected back to the login screen.
- macOS and Windows build metadata now point to v0.3.2-dev.

### Improved

- Login screen copy now makes it clear that the desktop account is synced through the cloud API.
- Windows build script includes the cloud-login HTTP dependency when building an EXE.

## v0.3.0-dev - 2026-07-02

Commercial workspace preview focused on product readiness.

### Added

- Redesigned dashboard entry with a modern GEO workspace hero, KPI cards, and clearer next-step guidance.
- New Data Dashboard tab for task coverage, answer volume, brand exposure rate, reference domains, platform mix, and source rankings.
- `/api/insights/overview` endpoint for product-level GEO monitoring metrics.
- `/api/insights/ai-analysis` endpoint that uses the user's default AI API URL, API key, and model to generate observations, risks, experiments, and next actions.

### Improved

- Default empty-state guidance now explains how to configure AI analysis instead of showing a blank feature.
- The dashboard first screen now prioritizes status, next action, and analysis over long instructions.

## v0.2.0 - 2026-07-02

This release moves GEO-SOP from a development preview toward a distributable desktop product.

### Added

- Unified application version metadata exposed in the desktop window and dashboard.
- `/api/app-info` endpoint for version, runtime mode, data directory, and answers directory.
- macOS packaging script that builds a `.app`, `.dmg`, icon, and SHA256 checksum.
- Dashboard version badge and desktop-mode badge.
- Export button loading states to prevent duplicate clicks while GEO reports or screenshot ZIPs are being generated.

### Improved

- Desktop launcher now resolves bundled resources when packaged by PyInstaller.
- Export failures show clearer user-facing messages instead of appearing like the button did nothing.
- Sensitive AI API key fragments are no longer printed to logs.

### Known Distribution Notes

- macOS builds still need Apple Developer ID signing and notarization before public commercial distribution.
- Windows builds should be produced on Windows and signed with an OV/EV code-signing certificate before broad distribution.
- AI platform login stability depends on each platform's web UI and anti-automation changes.
## v0.3.13-dev - 2026-07-10

- 云端任务管理增加桌面客户端心跳状态，服务端可以直接判断任务是在等待上线还是已在线执行。
- Windows Inno Setup 配置默认版本与应用版本统一为 v0.3.13-dev。
## v0.3.14-dev - 2026-07-10

- 连续创建任务、采集结果或保存配置时，云端同步会自动补齐并发期间发生的变更。
- 桌面端同步队列完成后再释放状态，减少云端历史记录缺失风险。
