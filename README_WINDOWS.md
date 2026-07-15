# GEO-SOP Windows Package

Version: 0.3.18-dev

The public Windows download is a native setup EXE. It includes the GEO-SOP
desktop runtime and Playwright Chromium, so customers do not need Python,
PowerShell commands, or a separate browser download.

## Install

1. Download `GEO-SOP-Setup-dev.exe` from geo.allgood.cn.
2. Double-click the setup file and finish the installation.
3. Launch GEO-SOP from the Start menu or the optional desktop shortcut.
4. Sign in with the same geo.allgood.cn account used by the cloud dashboard.

The installed application keeps its SQLite database, browser profiles, exports,
and cloud account token in the current Windows user's application-data folder.
Normal upgrades do not remove that data.

The current development build is not yet code-signed. Windows SmartScreen may
show an unknown-publisher warning; choose `More info` and then `Run anyway`.

## Source Package

`Install GEO-SOP.bat`, `Start GEO-SOP.bat`, and the Python bootstrap remain in
the repository for development and recovery only. Customers should use the
native setup EXE.

## Build EXE On Windows

For developers only: run `build_windows_exe.bat`, then
`build_windows_installer.bat` on Windows.

The generated EXE is written to:

```text
dist\GEO-SOP\GEO-SOP.exe
```

The build downloads Playwright Chromium into `.playwright-browsers` and embeds
it in the Inno Setup installer. A production release should still sign the EXE
and installer with an OV/EV code-signing certificate.
