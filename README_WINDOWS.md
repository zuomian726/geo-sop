# GEO-SOP Windows Build Package

Version: 0.3.5-dev

This ZIP is a Windows development/build package, not a signed commercial installer.

## Run Locally

1. Install Python 3.10 or later.
2. Unzip this package.
3. Double-click `run_windows_desktop.bat`.

The first launch creates `.venv-desktop`, installs dependencies, and starts the local desktop app.

## Build EXE On Windows

Double-click `build_windows_exe.bat`.

The generated EXE is written to:

```text
dist\GEO-SOP\GEO-SOP.exe
```

For commercial distribution, build on Windows and sign the EXE or installer with an OV/EV code-signing certificate.
