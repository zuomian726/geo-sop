# GEO-SOP Release Notes

## v0.3.27-dev - 2026-07-15

- 桌面端工作区同步默认改为非破坏性合并，本地数据库为空、刚安装或正在恢复时不会删除云端历史记录。
- 服务端只有收到明确的替换模式请求时才执行缺失记录清理，普通登录、后台同步和断网补传均保留既有云端数据。
- 同步接口返回实际合并模式，便于客户端和运维确认本次同步是否可能涉及删除。
- 新增空本地库同步保护测试，并在隔离账户中完成线上 API 实测：空数据再次同步后原任务保持完整。

## v0.3.26-dev - 2026-07-15

- 客户端心跳新增远程任务工作器状态，可区分等待任务、本地排队、正在采集和等待结果回传。
- 云端连接诊断会显示本机排队任务、执行中任务和待补传任务数量，不再只显示笼统的在线或离线。
- 任务采集和断网补传期间会给出对应状态说明，用户可以直接判断任务停留在哪个阶段。
- 心跳仅上传运行状态和计数，不上传问题、回答、API Key 或其他业务内容。
- 新增心跳隐私边界、任务状态计算及云端展示契约测试。

## v0.3.25-dev - 2026-07-15

- 客户端更新检测现已执行服务端最低兼容版本和强制升级策略，协议不兼容时会显示不可误关的升级提示。
- 版本比较正确区分开发版、Beta、RC 和正式版，避免同一版本号的预发布版本错过正式更新。
- 更新窗口清楚展示当前版本、最新版本、安装包大小和更新内容，并明确说明本地任务、登录状态与历史数据会保留。
- 桌面端通过操作系统默认浏览器打开同域 HTTPS 官方安装包，桌面壳拦截新窗口时仍可正常下载。
- 更新清单同步返回最低版本、SHA-256 校验值与平台安装包信息，为后续签名与自动校验提供统一协议。

## v0.3.24-dev - 2026-07-15

- 桌面任务、平台登录检测和平台列表统一使用同一份 8 平台目录，避免平台数量和状态显示不一致。
- 云端创建任务现已支持与客户端一致的全部平台，不再只显示其中 5 个。
- 云端 API 和桌面客户端增加双重平台白名单校验，未知平台不会进入采集线程造成运行期错误。
- 远程任务会自动去重平台、限制并行数不超过所选平台数，并将采集间隔收敛到安全范围。
- 登录步骤徽标改为动态平台总数，不再写死为 7。
- 新增平台目录一致性、采集模块存在性和非法远程任务回绝测试。

## v0.3.23-dev - 2026-07-15

- 云端任务区新增实时连接诊断，明确显示客户端在线状态、最后心跳、版本和待领取任务原因。
- 云端每 15 秒自动刷新客户端与远程任务状态，无需手动刷新页面判断任务是否开始执行。
- 在线但版本过旧的客户端会显示升级提醒，离线超过 90 秒会准确标记并说明恢复方法。
- 客户端心跳、任务拉取和云端数据恢复改为独立容错；单个网络请求失败不再阻塞已进入本机队列的任务。
- 新增断网状态下继续执行已导入远程任务的自动回归测试。

## v0.3.22-dev - 2026-07-15

- AI 分析结果会保存到本地数据库，刷新或重新打开客户端后仍能继续查看最近一次分析。
- 最近一次 AI 分析可随账号同步到云端，并在其他设备恢复；API Key 默认始终只保存在本机，不上传服务器。
- 云端看板展示最近一次 AI 总结、关键观察和下一步动作，不再把未上传的 Key 错误显示为“等待 Key”。
- 云端任务数、运行状态、截图留证、引用域名和 GEO 健康分与客户端使用同一计算口径。
- 引用来源改为分批读取全部同步结果，兼顾大数据账户的准确性和内存稳定性。
- 新增 AI 分析持久化、密钥隔离和跨设备配置回传的自动回归测试。

## v0.3.21-dev - 2026-07-15

- 云端任务采集成功后，即使结果同步或状态回报临时断网，也不会把本地已完成任务错误标记为失败。
- 未完成的结果、截图和任务终态会在后续客户端心跳中自动补传，无需用户手动重新执行任务。
- 多个待补传任务会合并工作区同步请求，减少重复上传和服务器压力。
- 新增断网恢复、终态补报和多任务批量同步自动回归测试。

## v0.3.20-dev - 2026-07-15

- 修复 Excel 导出无法嵌入 `answers/...` 相对路径截图的问题，Windows 与 macOS 均统一使用安全路径解析。
- 截图 ZIP 不再对已丢失的本地文件返回空包成功，而是给出明确错误提示。
- 同一问题、平台和时间的多张截图在 ZIP 中加入结果 ID，避免文件名冲突。
- 新增远程任务状态回传、云端统计与截图上传、Excel/ZIP 文件内容的自动回归测试。

## v0.3.19-dev - 2026-07-15

- Windows 首次启动改为按需加载 Playwright 登录模块，先显示登录界面，再在用户点击平台登录或检测时加载浏览器能力。
- Windows 构建增加原生 EXE 运行测试：必须完成 SQLite 建表并能访问本地登录页，才允许生成安装包。
- 启动调试日志增加数据库初始化阶段信息，便于定位客户端无法打开或首启卡住的问题。

## v0.3.18-dev - 2026-07-15

### Added

- Windows setup now installs a native PyInstaller desktop application with its Playwright Chromium runtime included.
- The installed Windows app no longer requires Python, `winget`, dependency installation, or a first-run browser download.
- Windows setup registers the `geo-sop://` protocol so cloud dashboard actions can launch the installed app.

### Fixed

- Cloud tasks are atomically claimed by one desktop client, preventing duplicate execution when the same account is online on multiple computers.
- Unacknowledged task claims are released after ten minutes so another online client can recover them.
- Remote task status updates are accepted only from the client that owns the claim.
- Repeated task pulls now acknowledge the existing local task ID instead of creating a duplicate or leaving the cloud task stuck.
- Cloud task states use consistent `claimed`, `imported`, `running`, `completed`, `failed`, and `skipped` semantics in the server dashboard.

## v0.3.17-dev - 2026-07-13

- Existing desktops now incrementally merge cloud records from other devices instead of restoring only into an empty database.
- Cloud restore uses cursor pagination, preventing large accounts from timing out and only pulling new rows after the first merge.
- Synced results, manuscripts, and sentiment settings carry source identifiers for idempotent cross-device merging.
- Completed tasks automatically upload their screenshots; login also starts a background backfill for historical screenshots.
- Cloud login sends an immediate heartbeat while the background worker continues pulling tasks and new data.

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
## v0.3.15-dev - 2026-07-10

- 多用户桌面端不再把未匹配的云端账号回退到本地第一位用户，避免跨账号执行任务或同步数据。
- 客户端心跳增加应用版本信息，云端任务管理可以识别客户端版本。
## v0.3.16-dev - 2026-07-10

- 桌面 dashboard 顶部增加云端同步状态，显示已同步、已连接、未连接或同步异常。
- 同步状态包含最近成功同步时间，减少用户对数据是否上传的疑问。
