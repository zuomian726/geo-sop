# GEO-SOP Windows Package

Version: 0.3.10-dev

This ZIP is a Windows desktop package, not a signed commercial installer yet.

## Run Locally

1. Install Python 3.10 or later.
2. Unzip this package.
3. Double-click `Start GEO-SOP.bat`.

The first launch creates `.venv-desktop`, installs dependencies, and starts the local desktop app.

If Windows shows "The system cannot find the path specified", usually the ZIP was not fully extracted or a build script was clicked by mistake. Re-extract the ZIP to a normal folder such as `D:\GEO-SOP`, then double-click `Start GEO-SOP.bat`.

## Build EXE On Windows

For developers only: double-click `build_windows_exe.bat`.

The generated EXE is written to:

```text
dist\GEO-SOP\GEO-SOP.exe
```

For commercial distribution, build on Windows and sign the EXE or installer with an OV/EV code-signing certificate.
