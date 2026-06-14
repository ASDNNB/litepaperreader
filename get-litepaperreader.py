#!/usr/bin/env python3
"""LitePaperReader — One-click bootstrap installer.

Usage:
    curl -sSL https://raw.githubusercontent.com/ASDNNB/litepaperreader/master/get-litepaperreader.py | python3
    python get-litepaperreader.py
    python get-litepaperreader.py --all
    python get-litepaperreader.py --edge  (install Microsoft Edge WebView2 runtime if needed)

Downloads the project, sets up a virtual environment, installs dependencies,
and creates launcher scripts. Designed to work on Windows/macOS/Linux with
zero prior setup beyond Python 3.11+.

For Windows .exe users: download LitePaperReader_Setup.exe from the GitHub
Releases page instead.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import textwrap
import zipfile
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_NAME = "LitePaperReader"
PROJECT_REPO = "ASDNNB/litepaperreader"
GITHUB_API = f"https://api.github.com/repos/{PROJECT_REPO}"
GITHUB_RAW = f"https://raw.githubusercontent.com/{PROJECT_REPO}"
DEFAULT_BRANCH = "master"
MIN_PYTHON = (3, 11)

VERSION = "1.0.0-dev"

AVAILABLE_EXTRAS = {
    "pdf":   "PDF processing  (docling, markitdown)",
    "embed": "Embeddings      (sentence-transformers, scikit-learn)",
    "code":  "Code parsing    (tree-sitter, tree-sitter-languages)",
    "web":   "Web fetching    (trafilatura, httpx)",
    "yaml":  "YAML config     (pyyaml)",
    "dev":   "Development     (pytest, pytest-asyncio)",
}

EXTRAS_HELP = {
    "pdf": "Process PDF documents using Docling & MarkItDown",
    "embed": "Semantic search with embeddings (large download ~1 GB)",
    "code": "Parse source-code files with tree-sitter",
    "web": "Fetch and process web pages via HTTPX",
    "yaml": "Load configuration from YAML files",
    "dev": "Development & testing tools (pytest)",
}

# ---------------------------------------------------------------------------
# Terminal styling
# ---------------------------------------------------------------------------

def _c(code: str, text: str) -> str:
    if os.name == "nt" and not os.environ.get("WT_SESSION"):
        return text
    return f"\033[{code}m{text}\033[0m"

def _bold(text: str) -> str: return _c("1", text)
def _dim(text: str) -> str: return _c("2", text)
def _cyan(text: str) -> str: return _c("1;36", text)
def _green(text: str) -> str: return _c("1;32", text)
def _yellow(text: str) -> str: return _c("1;33", text)
def _red(text: str) -> str: return _c("1;31", text)
def _magenta(text: str) -> str: return _c("1;35", text)

def step(msg: str) -> None:
    print(f"\n  {_cyan('\u25c6')} {_bold(msg)}")

def ok(msg: str) -> None:
    print(f"  {_green('\u2713')} {msg}")

def warn(msg: str) -> None:
    print(f"  {_yellow('\u26a0')} {msg}")

def fail(msg: str) -> None:
    print(f"  {_red('\u2717')} {msg}")

def info(msg: str) -> None:
    print(f"    {_dim('\u00b7')} {msg}")

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

p = platform.system().lower()
IS_WINDOWS = p == "windows"
IS_MACOS = p == "darwin"
IS_LINUX = p == "linux"

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

BANNER = f"""
{_magenta('\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557')}
{_magenta('\u2551')}  {_bold('LitePaperReader')} — Universal Data Flow Engine  {_magenta('\u2551')}
{_magenta('\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d')}
{_dim(f'  Version {VERSION}  |  Cross-platform Installer')}
"""

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def run(cmd: list[str], desc: str, cwd: Path | None = None, capture: bool = True) -> str:
    info(f"$ {' '.join(str(c) for c in cmd)}")
    try:
        r = subprocess.run(cmd, cwd=cwd or Path.cwd(),
                           capture_output=capture, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(f"{desc} failed (exit {r.returncode}):\n{r.stderr[:2000]}")
        return r.stdout or ""
    except FileNotFoundError:
        raise RuntimeError(f"{desc} — command not found: {cmd[0]}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{desc} timed out after 10 min")


def download_url(url: str, dest: Path) -> None:
    info(f"Downloading {url}")
    try:
        with urlopen(url, timeout=30) as resp:
            size = int(resp.headers.get("Content-Length", "0"))
            downloaded = 0
            chunk_size = 8192
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if size > 0:
                        percent = int(downloaded * 100 / size)
                        sys.stdout.write(f"\r    {_dim(f'Progress: {percent}%')}   ")
                        sys.stdout.flush()
        if size > 0:
            print()
    except URLError as e:
        raise RuntimeError(f"Download failed: {e.reason}")


def check_python() -> Path:
    v = sys.version_info[:2]
    if v < MIN_PYTHON:
        fail(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required, found {v[0]}.{v[1]}")
        print()
        print("  Install Python from: https://www.python.org/downloads/")
        if IS_WINDOWS:
            print("  Or: winget install Python.Python.3.11")
        elif IS_MACOS:
            print("  Or: brew install python@3.11")
        else:
            print("  Or: sudo apt install python3 python3-pip python3-venv")
        sys.exit(1)
    ok(f"Python {v[0]}.{v[1]} — {sys.executable}")
    return Path(sys.executable)


def confirm(question: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        ans = input(f"  {question} [{hint}] ").strip().lower()
        if not ans:
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def step_check_env() -> Path:
    step("Step 1/6: Checking environment")
    python = check_python()
    try:
        subprocess.run([str(python), "-m", "pip", "--version"],
                       capture_output=True, check=True)
        ok("pip is available")
    except (subprocess.CalledProcessError, FileNotFoundError):
        step("Installing pip...")
        run([str(python), "-m", "ensurepip", "--upgrade"], "pip install")
        ok("pip installed")
    git_avail = shutil.which("git") is not None
    if git_avail:
        ok("git is available")
    else:
        warn("git not found — will download ZIP instead")
    usage = shutil.disk_usage(Path.cwd())
    free_gb = usage.free / (1024**3)
    if free_gb < 1:
        warn(f"Low disk space: only {free_gb:.1f} GB free")
    else:
        ok(f"Disk space: {free_gb:.1f} GB free")
    return python


def step_download_project() -> Path:
    step("Step 2/6: Downloading LitePaperReader")
    target_dir = Path.cwd() / "litepaperreader-src"
    if target_dir.exists():
        if confirm(f"Directory {target_dir} already exists. Re-download?"):
            shutil.rmtree(target_dir)
        else:
            ok("Using existing directory")
            return target_dir
    git_avail = shutil.which("git") is not None
    if git_avail:
        try:
            info("Cloning via git...")
            run(["git", "clone", "--depth=1",
                 f"https://github.com/{PROJECT_REPO}.git",
                 str(target_dir)], "git clone")
            ok("Repository cloned")
            return target_dir
        except RuntimeError as e:
            warn(f"Git clone failed: {e}")
            warn("Falling back to ZIP download...")
            if target_dir.exists():
                shutil.rmtree(target_dir)
    info("Downloading ZIP archive...")
    zip_url = f"{GITHUB_API}/zipball/{DEFAULT_BRANCH}"
    zip_path = target_dir.with_suffix(".zip")
    download_url(zip_url, zip_path)
    info("Extracting archive...")
    if zipfile.is_zipfile(zip_path):
        with zipfile.ZipFile(zip_path) as zf:
            members = zf.namelist()
            top_dir = members[0].split("/")[0]
            zf.extractall(target_dir.parent)
        extracted = target_dir.parent / top_dir
        if extracted.exists():
            if target_dir.exists():
                shutil.rmtree(target_dir)
            extracted.rename(target_dir)
    else:
        raise RuntimeError("Downloaded file is not a valid ZIP archive")
    zip_path.unlink(missing_ok=True)
    ok("Project downloaded and extracted")
    return target_dir


def step_setup_venv(python: Path, project_dir: Path) -> Path:
    step("Step 3/6: Creating virtual environment")
    venv_dir = project_dir / ".venv"
    if IS_WINDOWS:
        py_venv = venv_dir / "Scripts" / "python.exe"
    else:
        py_venv = venv_dir / "bin" / "python"
    if py_venv.exists():
        ok(f"Virtual environment already exists: {venv_dir}")
        return py_venv
    info("Creating venv...")
    run([str(python), "-m", "venv", str(venv_dir)], "venv creation")
    ok(f"Virtual environment created: {venv_dir}")
    info("Upgrading pip...")
    run([str(py_venv), "-m", "pip", "install", "--upgrade", "pip"], "pip upgrade")
    ok("pip upgraded")
    return py_venv


def step_install_package(python: Path, project_dir: Path) -> list[str]:
    step("Step 4/6: Installing LitePaperReader")
    chosen_extras: list[str] = []
    if "--all" in sys.argv:
        chosen_extras = ["all"]
    else:
        for key in ["pdf", "embed", "code", "web", "yaml", "dev"]:
            label = AVAILABLE_EXTRAS[key]
            if confirm(f"Install {label}?"):
                chosen_extras.append(key)
    info("Installing core package...")
    run([str(python), "-m", "pip", "install", "-e", str(project_dir)], "core install")
    ok("Core package installed")
    if chosen_extras:
        label = ",".join(chosen_extras)
        info(f"Installing extras: [{label}]")
        if chosen_extras == ["all"]:
            spec = f"{project_dir}[all]"
        else:
            spec = f"{project_dir}[{label}]"
        run([str(python), "-m", "pip", "install", "-e", spec], f"extras: {label}")
        ok(f"Extras installed: {label}")
    return chosen_extras


def step_create_launchers(python: Path, project_dir: Path) -> list[str]:
    step("Step 5/6: Creating launcher scripts")
    launchers: list[str] = []
    entries = [
        ("litepaperreader-webui",
         f'"{str(python)}" "{str(project_dir / "webui.py")}"',
         "Start LitePaperReader Web UI"),
        ("litepaperreader-mcp",
         f'"{str(python)}" "{str(project_dir / "mcp_server.py")}"',
         "Start LitePaperReader MCP Server"),
    ]
    if IS_WINDOWS:
        for name, cmd, desc in entries:
            bat_path = project_dir / f"{name}.bat"
            content = f"""@echo off
cd /d "{project_dir}"
{cmd}
if errorlevel 1 pause
"""
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(content)
            launchers.append(bat_path.name)
            ok(f"  {name}.bat — {desc}")
    else:
        for name, cmd, desc in entries:
            sh_path = project_dir / name
            content = f"""#!/usr/bin/env bash
set -e
cd "{project_dir}"
exec {cmd} "$@"
"""
            with open(sh_path, "w", encoding="utf-8") as f:
                f.write(content)
            sh_path.chmod(sh_path.stat().st_mode | stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            launchers.append(sh_path.name)
            ok(f"  {name} — {desc}")
    return launchers


def step_show_summary(python: Path, project_dir: Path, extras: list[str],
                      launchers: list[str]) -> None:
    step("Step 6/6: Installation complete!")
    print()
    print(f"  {_green('\u2501' * 55)}")
    print(f"  {_bold('LitePaperReader has been successfully installed!')}")
    print(f"  {_green('\u2501' * 55)}")
    print()
    print(f"  {_bold('\U0001f4c1 Project directory:')}  {project_dir}")
    print(f"  {_bold('\U0001f40d Python:')}             {python}")
    print(f"  {_bold('\U0001f4e6 Extras:')}             {', '.join(extras) if extras else '(core only)'}")
    print()
    if launchers:
        print(f"  {_bold('\U0001f680 Launcher scripts:')}")
        for l in launchers:
            print(f"    {_cyan('\u00b7')} {project_dir / l}")
        print()
    print(f"  {_bold('\U0001f4a1 Quick start:')}")
    print()
    print(f"    {_cyan('1.')} Start Web UI:")
    print(f"       python {project_dir / 'webui.py'}")
    print(f"       {_dim('\u2192 Open http://localhost:8765')}")
    print()
    print(f"    {_cyan('2.')} Start MCP Server:")
    print(f"       python {project_dir / 'mcp_server.py'} --db index.db")
    print()
    print(f"    {_cyan('3.')} Process a document in Python:")
    print(f"       cd {project_dir}")
    print(f'       python -c "from litepaperreader.pipeline.orchestrator import DataPipeline; print(\'Ready!\')"')
    print()
    if IS_WINDOWS:
        print(f"  {_bold('\U0001f4cc Tips:')}")
        print(f'    · Add to PATH:  $env:Path += \\\";{project_dir}\\\"')
        print(f"    · Run tests:    python -m pytest tests/")
        print(f"    · Uninstall:    Remove-Item -Recurse -Force '{project_dir}'")
    else:
        print(f"  {_bold('\U0001f4cc Tips:')}")
        print(f'    · Add to PATH:  export PATH="$PATH:{project_dir}"')
        print(f"    · Run tests:    python -m pytest tests/")
        print(f"    · Uninstall:    rm -rf '{project_dir}'")
    print()
    print(f"  {_yellow('\u2b50 Enjoying LitePaperReader? Give us a star on GitHub!')}")
    print(f"    https://github.com/{PROJECT_REPO}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        python = step_check_env()
        project_dir = step_download_project()
        py_venv = step_setup_venv(python, project_dir)
        extras = step_install_package(py_venv, project_dir)
        launchers = step_create_launchers(py_venv, project_dir)
        step_show_summary(py_venv, project_dir, extras, launchers)
    except KeyboardInterrupt:
        print()
        warn("Installation cancelled.")
        sys.exit(1)
    except RuntimeError as e:
        fail(str(e))
        print()
        print(f"  {_yellow('Need help?')} Open an issue: https://github.com/{PROJECT_REPO}/issues")
        sys.exit(1)
    except Exception as e:
        fail(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
