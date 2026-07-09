$ErrorActionPreference = "Stop"

function Write-Step($message) {
    Write-Host ""
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Get-PythonCommand {
    $candidates = @(
        @{ Cmd = "py"; Args = @("-3") },
        @{ Cmd = "python"; Args = @() }
    )

    foreach ($candidate in $candidates) {
        $cmd = Get-Command $candidate.Cmd -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        try {
            $args = @($candidate.Args) + @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)")
            & $candidate.Cmd @args | Out-Null
            if ($LASTEXITCODE -eq 0) {
                return (@($candidate.Cmd) + $candidate.Args) -join " "
            }
        } catch {
            continue
        }
    }

    $searchRoots = @(
        Join-Path $env:LocalAppData "Programs\Python",
        $env:ProgramFiles,
        ${env:ProgramFiles(x86)}
    ) | Where-Object { $_ -and (Test-Path $_) }

    foreach ($root in $searchRoots) {
        $matches = Get-ChildItem -Path $root -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch "\\WindowsApps\\" } |
            Sort-Object FullName -Descending
        foreach ($match in $matches) {
            try {
                & $match.FullName -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    return '"' + $match.FullName + '"'
                }
            } catch {
                continue
            }
        }
    }

    return $null
}

function Install-Python {
    Write-Step "Python 3.10+ was not found. Installing Python 3.12..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget install --id Python.Python.3.12 --exact --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            throw "winget failed to install Python. Please install Python 3.10+ manually from https://www.python.org/downloads/windows/"
        }
    } else {
        throw "winget is not available. Please install Python 3.10+ manually from https://www.python.org/downloads/windows/"
    }

    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

Set-Location -Path $PSScriptRoot
Write-Host "GEO-SOP Windows Installer" -ForegroundColor Green
Write-Host "Folder: $PSScriptRoot"

$pythonCmd = Get-PythonCommand
if (-not $pythonCmd) {
    Install-Python
    $pythonCmd = Get-PythonCommand
}

if (-not $pythonCmd) {
    throw "Python 3.10+ is still not available after installation. Please close this window and run Install GEO-SOP.bat again."
}

Write-Step "Python ready: $pythonCmd"
$env:GEO_PYTHON_CMD = $pythonCmd

if (-not (Test-Path "desktop_app.py")) {
    throw "desktop_app.py was not found. Please fully extract the ZIP package first."
}

if (-not (Test-Path "requirements-desktop.txt")) {
    throw "requirements-desktop.txt was not found. Please fully extract the ZIP package first."
}

Write-Step "Starting GEO-SOP launcher"
& "$PSScriptRoot\run_windows_desktop.bat"
if ($LASTEXITCODE -ne 0) {
    throw "GEO-SOP launcher exited with code $LASTEXITCODE"
}
