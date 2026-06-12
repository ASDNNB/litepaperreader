<#
.SYNOPSIS
  LitePaperReader — Windows installer (PowerShell).
.DESCRIPTION
  Checks for Python 3.11+, offers to install it via winget if missing,
  then delegates to install.py for venv setup and dependency installation.
.PARAMETER All
  Install all optional dependencies (pdf, embed, code, web, yaml, dev).
.PARAMETER Extras
  Comma-separated list of extras to install, e.g. "-Extras pdf,web,code".
.PARAMETER NoVenv
  Install into system Python instead of a virtual environment.
.PARAMETER NonInteractive
  Skip interactive prompts (core only unless -All or -Extras is set).
.EXAMPLE
  .\install.ps1
  .\install.ps1 -All
  .\install.ps1 -Extras "pdf,web"
#>
[CmdletBinding(DefaultParameterSetName="Default")]
param(
  [Parameter(ParameterSetName="All")]
  [switch]$All,
  [Parameter(ParameterSetName="Extras")]
  [string]$Extras,
  [switch]$NoVenv,
  [switch]$NonInteractive
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ProjectRoot) { $ProjectRoot = Get-Location }
function Write-Step  { Write-Host "`n  * $args" -ForegroundColor Cyan }
function Write-Ok    { Write-Host "  [+] $args" -ForegroundColor Green }
function Write-Warn  { Write-Host "  [!] $args" -ForegroundColor Yellow }
function Write-Fail  { Write-Host "  [x] $args" -ForegroundColor Red }
Write-Host ""
Write-Host "  ------------------------------------------------" -ForegroundColor Magenta
Write-Host "   LITE PAPER READER  -  Universal Data Flow Engine" -ForegroundColor Magenta
Write-Host "  ------------------------------------------------" -ForegroundColor Magenta
Write-Host ""
Write-Host "  Windows Installer (PowerShell)" -ForegroundColor Gray
Write-Host ""
$MinMajor = 3
$MinMinor = 11
$PythonPath = $null
$pythonCandidates = @("python3.exe", "python.exe")
foreach ($name in $pythonCandidates) {
  $p = Get-Command $name -ErrorAction SilentlyContinue
  if ($p) {
    $ver = & $p.Source -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
    if ($ver) {
      $parts = $ver.Split(".")
      if (($parts[0] -as [int]) -ge $MinMajor -and ($parts[1] -as [int]) -ge $MinMinor) {
        $PythonPath = $p.Source
        break
      }
    }
  }
}
$commonDirs = @(
  "${env:LOCALAPPDATA}\Programs\Python",
  "${env:ProgramFiles}\Python*",
  "C:\Python*"
)
if (-not $PythonPath) {
  foreach ($pattern in $commonDirs) {
    $dirs = Get-ChildItem $pattern -Directory -ErrorAction SilentlyContinue
    foreach ($d in $dirs) {
      $p = Join-Path $d.FullName "python.exe"
      if (Test-Path $p) {
        $ver = & $p -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
        if ($ver) {
          $parts = $ver.Split(".")
          if (($parts[0] -as [int]) -ge $MinMajor -and ($parts[1] -as [int]) -ge $MinMinor) {
            $PythonPath = $p
            break
          }
        }
      }
    }
    if ($PythonPath) { break }
  }
}
if (-not $PythonPath) {
  Write-Warn "Python $MinMajor.$MinMinor+ is not installed."
  Write-Host ""
  Write-Host "  Options:" -ForegroundColor Cyan
  Write-Host "    1. Install via Microsoft Store (recommended)"
  Write-Host "    2. Install via winget: winget install Python.Python.3.11"
  Write-Host "    3. Install via Chocolatey: choco install python"
  Write-Host "    4. Download manually: https://www.python.org/downloads/"
  Write-Host ""
  $choice = Read-Host "  Enter choice [1-4] or press Enter to skip"
  switch ($choice) {
    "1" {
      Write-Step "Opening Microsoft Store..."
      Start-Process "ms-windows-store://pdp/?productid=9NRWMJ6Q3J6Z"
    }
    "2" {
      Write-Step "Installing Python via winget..."
      winget install Python.Python.3.11
    }
    "3" {
      Write-Step "Installing Python via Chocolatey..."
      choco install python -y
    }
  }
  Write-Host ""
  Read-Host "  Press Enter after installing Python, or Ctrl+C to abort"
  $p = Get-Command "python.exe" -ErrorAction SilentlyContinue
  if ($p) {
    $ver = & $p.Source -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
    if ($ver) {
      $parts = $ver.Split(".")
      if (($parts[0] -as [int]) -ge $MinMajor -and ($parts[1] -as [int]) -ge $MinMinor) {
        $PythonPath = $p.Source
      }
    }
  }
  if (-not $PythonPath) {
    Write-Fail "Python $MinMajor.$MinMinor+ still not found. Exiting."
    exit 1
  }
}
Write-Ok "Python $(& $PythonPath --version 2>&1 | Select-Object -First 1) -- $PythonPath"
$pipCheck = & $PythonPath -m pip --version 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Step "Installing pip..."
  & $PythonPath -m ensurepip --upgrade
}
Write-Ok "pip ready"
$installPy = Join-Path $ProjectRoot "install.py"
if (-not (Test-Path $installPy)) {
  Write-Fail "install.py not found at $installPy"
  exit 1
}
$argsList = @()
if ($All)        { $argsList += "--all" }
if ($Extras)     { $argsList += "--extras", $Extras }
if ($NoVenv)     { $argsList += "--no-venv" }
if ($NonInteractive) { $argsList += "--non-interactive" }
Write-Step "Launching install.py..."
if ($argsList.Count -eq 0) {
  & $PythonPath $installPy
} else {
  & $PythonPath $installPy $argsList
}
if ($LASTEXITCODE -ne 0) {
  Write-Fail "install.py exited with code $LASTEXITCODE"
  Read-Host "Press Enter to exit"
  exit $LASTEXITCODE
}
