# GEO-SOP Product Roadmap

This roadmap keeps the public release path simple. Detailed fixes can still be tracked in release notes, but the product should be communicated as three clear stages: desktop preview, v1.0 detection and sentiment analysis, and v2.0 fully automated GEO tasks.

## Version Policy

- `dev`: internal or early customer desktop preview.
- `stable`: commercial release with signing, support, documentation, and upgrade policy.
- `automation`: server-scheduled, locally executed GEO task automation.

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

## v1.0 - Detection and Sentiment Analysis

Goal: make GEO-SOP reliable enough for commercial detection and sentiment-analysis workflows.

Planned focus:

- Stable task creation, platform login checks, answer collection, screenshots, and exports.
- Brand visibility detection, reference-source extraction, and source-domain summaries.
- Local keyword sentiment analysis and AI-assisted sentiment analysis.
- Compact KPI dashboard for non-technical users.
- Cloud account login, local/cloud data sync, and server-side task visibility.
- Signed or clearly packaged macOS and Windows builds for customer use.

Acceptance criteria:

- A customer can detect how AI platforms mention a brand, review references, understand sentiment, and export evidence without developer assistance.
- Detection results and sentiment conclusions are consistent between the desktop app and cloud dashboard.
- Local data survives normal upgrades and can sync through HTTPS API and token authentication.

## v2.0 - Fully Automated GEO Tasks

Goal: let cloud users create GEO tasks that the local desktop app can execute automatically and safely.

Required before launch:

- Cloud task scheduling and task assignment to the correct desktop client.
- Local worker queue with retries, rate limits, failure diagnostics, and recovery guidance.
- Login-state monitoring and user prompts when a platform account needs local re-authentication.
- Automatic answer collection, screenshot evidence, sentiment analysis, dashboard refresh, and report generation.
- Audit trail, run logs, safe cancellation, and per-user data isolation.
- Upgrade and rollback policy for automation workers.

Acceptance criteria:

- A user can create a task in the cloud, leave the desktop client running, and receive completed GEO results automatically.
- Automation never exposes platform cookies or database credentials to the cloud page.
- Failed runs are explainable and recoverable without corrupting local or cloud data.

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
