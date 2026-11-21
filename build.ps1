#Requires -Version 5.1
# Build RobRunAutoClicker release + debug executables with PyInstaller.
# Run from anywhere:  powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

Write-Host ""
Write-Host "=== RobRunAutoClicker build ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"

# --- 1. Verify the system Python -------------------------------------------
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    throw "Python was not found in PATH. Install Python 3.11+ (64-bit) and retry."
}

$versionText = (& python -c "import sys; print(str(sys.version_info.major) + '.' + str(sys.version_info.minor))").Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Could not run 'python --version' from PATH."
}
if ([version]$versionText -lt [version]"3.11") {
    throw "Python 3.11+ is required; found $versionText."
}
Write-Host "Python found: $versionText ($(& python -c "import sys; print(sys.executable)"))" -ForegroundColor Green

# --- 2. Create / reuse the build virtual environment -----------------------
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    if (Test-Path -LiteralPath ".venv") {
        Remove-Item -LiteralPath ".venv" -Recurse -Force
    }
    Write-Host "Creating .venv ..."
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the .venv virtual environment."
    }
}

$venvVersion = (& $VenvPython -c "import sys; print(str(sys.version_info.major) + '.' + str(sys.version_info.minor))").Trim()
if ([version]$venvVersion -lt [version]"3.11") {
    throw "The existing .venv uses Python $venvVersion. Delete .venv and rerun the build."
}
Write-Host "Build environment: $VenvPython (Python $venvVersion)"

# --- 3. Install PyInstaller -------------------------------------------------
Write-Host "Installing build requirements ..."
& $VenvPython -m pip install --disable-pip-version-check --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed."
}
& $VenvPython -m pip install --disable-pip-version-check -r requirements-build.txt
if ($LASTEXITCODE -ne 0) {
    throw "Installing requirements-build.txt failed."
}

# --- 4. Clean previous output ----------------------------------------------
foreach ($path in @("build", "dist")) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}
New-Item -ItemType Directory -Force -Path "build" | Out-Null
New-Item -ItemType Directory -Force -Path "dist" | Out-Null

# --- 5. Build both executables ---------------------------------------------
$CommonArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--distpath", "dist",
    "--specpath", "build"
)

Write-Host ""
Write-Host "Building dist\RobRunAutoClicker.exe (release, no console) ..." -ForegroundColor Cyan
& $VenvPython @CommonArgs --workpath "build\release" --noconsole --name RobRunAutoClicker main.py
if ($LASTEXITCODE -ne 0) {
    throw "Release build failed."
}

Write-Host ""
Write-Host "Building dist\RobRunAutoClicker-debug.exe (debug, console) ..." -ForegroundColor Cyan
& $VenvPython @CommonArgs --workpath "build\debug" --console --name RobRunAutoClicker-debug main.py
if ($LASTEXITCODE -ne 0) {
    throw "Debug build failed."
}

# --- 6. Copy editable runtime files next to the executables ----------------
Copy-Item -LiteralPath "config.json" -Destination "dist\config.json" -Force
Copy-Item -LiteralPath "README.md" -Destination "dist\README.md" -Force

$ReleaseExe = Join-Path $ProjectRoot "dist\RobRunAutoClicker.exe"
$DebugExe = Join-Path $ProjectRoot "dist\RobRunAutoClicker-debug.exe"
foreach ($exe in @($ReleaseExe, $DebugExe)) {
    if (-not (Test-Path -LiteralPath $exe)) {
        throw "Expected output not found: $exe"
    }
}

# Compiled intermediates are not part of the deliverable.
Remove-Item -LiteralPath "build" -Recurse -Force

Write-Host ""
Write-Host "=== Build complete ===" -ForegroundColor Green
Write-Host ("Release: {0} ({1:N2} MB)" -f $ReleaseExe, ((Get-Item -LiteralPath $ReleaseExe).Length / 1MB))
Write-Host ("Debug:   {0} ({1:N2} MB)" -f $DebugExe, ((Get-Item -LiteralPath $DebugExe).Length / 1MB))
Write-Host ("Config:  {0}" -f (Join-Path $ProjectRoot "dist\config.json"))
Write-Host ("README:  {0}" -f (Join-Path $ProjectRoot "dist\README.md"))
Write-Host ""
