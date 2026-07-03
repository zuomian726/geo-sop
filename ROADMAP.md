# GEO-SOP Product Roadmap

This roadmap keeps the public release path simple. Detailed fixes can still be tracked in release notes, but the product should be communicated as three clear stages: desktop preview, customer beta, and commercial stable.

## Version Policy

- `dev`: internal or early customer desktop preview.
- `beta`: customer pilot build with installer, onboarding, and upgrade safeguards.
- `stable`: commercial release with signing, support, documentation, and upgrade policy.

## v0.3-dev - Desktop Preview

Status: active.

Goal: make the core local desktop workflow useful and understandable.

Current focus:

- Core GEO dashboard with a small set of meaningful metrics.
- AI analysis with OpenAI-compatible and Anthropic-compatible provider modes.
- Clear loading, failure, and success states for AI analysis.
- Exported GEO files and screenshots saved to a visible local folder.
- Online demo with synthetic data and read-only safety mode.
- macOS development DMG and Windows development package.

Acceptance criteria:

- A user can install, open, create a task, collect answers, review the dashboard, run AI analysis, and find exports without developer help.
- The dashboard explains what matters now and what to do next, instead of only listing raw data.

## v0.4-beta - Customer Beta

Goal: make GEO-SOP reliable enough for customer pilots.

Planned focus:

- First-run onboarding for non-technical users.
- Guided platform login and login recovery.
- Queue-based collection with retries and clearer failure diagnostics.
- Windows installer readiness, not only a ZIP build package.
- Local data backup and restore.
- Basic upgrade checks that preserve tasks, exports, screenshots, and browser profiles.

Acceptance criteria:

- A pilot customer can install and use GEO-SOP on macOS or Windows with minimal hand-holding.
- Collection failures are isolated and explain what the user should do next.
- Local data survives normal upgrades.

## v1.0 - Commercial Stable

Goal: public commercial desktop release.

Required before launch:

- Signed and notarized macOS DMG.
- Signed Windows installer.
- Stable collection, export, dashboard, AI analysis, and report workflows.
- Checksums for downloadable artifacts.
- Public documentation, support channel, release notes, and upgrade policy.
- Error log export for support and troubleshooting.

Acceptance criteria:

- A commercial user can install, configure, collect, analyze, export, and upgrade without developer assistance.
- Security prompts are reduced to the normal signed-app baseline.

## Release History

### v0.3.x-dev - 2026-07-02

- Commercial UI refresh.
- Compact analysis dashboard with scorecard, trend chart, platform comparison, and source distribution.
- AI provider modes for OpenAI-compatible and Anthropic-compatible APIs.
- AI analysis loading feedback and more tolerant JSON parsing.
- Export path visibility under `~/Downloads/GEO-SOP/`.
- Online demo and tools page updated.
- macOS DMG and Windows development ZIP published.

### v0.2.0 - 2026-07-02

- Desktop version metadata.
- macOS packaging script and DMG build.
- Export button loading states and clearer error messages.
- Reduced sensitive API key logging.

## Distribution Notes

- Current macOS development builds may still trigger Gatekeeper until notarization is complete.
- Current Windows downloads are development build packages until native signed installers are produced.
- AI platform login and collection behavior can change when each platform updates its web UI.
