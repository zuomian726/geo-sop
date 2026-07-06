# GEO-SOP Release Notes

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
