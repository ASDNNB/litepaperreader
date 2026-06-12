#!/usr/bin/env python3
"""LitePaperReader — Cross-platform installer.

Detects Python, sets up a venv, installs the package & optional extras,
and creates launcher scripts for `webui.py` and `mcp_server.py`.

Usage:
    python install.py                    # interactive — asks about extras
    python install.py --all              # install everything (all extras)
    python install.py --no-venv          # install into the system Python
    python install.py --extras pdf,web   # only specific extras

Platforms: Windows, macOS, Linux
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_NAME = "LitePaperReader"
MIN_PYTHON = (3, 11)
PROJECT_DIR = Path(__file__).resolve().parent

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
# Helpers
# ---------------------------------------------------------------------------

def _print_step(msg: str) -> None:
    print(f"\n  \033[1;36m*\033[0m {msg}")


def _print_ok(msg: str) -> None:
    print(f"  \033[1;32m\u2713\033[0m {msg}")


def _print_warn(msg: str) -> None:
    print(f"  \033[1;33m!\033[0m {msg}")


def _print_fail(msg: str) -> None:
    print(f"  \033[1;31m\u2717\033[0m {msg}")


def _print_banner() -> None:
    print(textwrap.dedent(f"""\
    \033[1;35m
     _ _       _          ____                       ____           _
    | (_)_ __ | | ___    |  _ \\ ___ _ __   ___ _ __ |  _ \\ ___  ___| |_ ___ _ __
    | | | '_ \\| |/ _ \\   | |_) / _ \\ '_ \\ / _ \\ '_ \\| |_) / _ \\/ __| __/ _ \\ '__|
    | | | |_) | |  __/   |  __/  __/ |_) |  __/ | | |  __/  __/\\__ \\ ||  __/ |
    |_|_| .__/|_|\\___|   |_|   \\___| .__/ \\___|_| |_|_|   \\___||___/\\__\\___|_|
        |_|                         |_|
    \033[0m
    Universal Data Flow Intelligence Engine
    \033[2mCross-platform installer — v1.0.0-dev\033[0m
    """))


def _detect_platform() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "macos"
    return "linux"


def _check_python() -> Path:
    """Return the path to the Python interpreter, ensuring it meets the minimum version."""
    v = sys.version_info[:2]
    if v < MIN_PYTHON:
        _print_fail(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required, "
            f"found {v[0]}.{v[1]} ({sys.executable})"
        )
        sys.exit(1)
    _print_ok(f"Python {v[0]}.{v[1]} \u2014 {sys.executable}")
    return Path(sys.executable)


def _check_pip(python: Path) -> Path:
    """Return the path to pip, or exit."""
    candidates = ["pip", "pip3"] if platform.system().lower() != "windows" else ["pip", "pip3"]
    pip_path = python.parent / candidates[0]
    if not pip_path.exists():
        # try running pip as a module
        try:
            subprocess.run([str(python), "-m", "pip", "--version"], capture_output=True, check=True)
        except subprocess.CalledProcessError:
            _print_fail("pip is not available. Install pip and try again.")
            _print_step("  Run: python -m ensurepip --upgrade")
            sys.exit(1)
        _print_ok("pip (via python -m pip)")
        return python
    _print_ok(f"pip \u2014 {pip_path}")
    return pip_path


def _run(cmd: list[str], desc: str, cwd: Path | None = None) -> str:
    """Run a command and exit on failure."""
    print(f"    $ {' '.join(str(c) for c in cmd)}")
    try:
        r = subprocess.run(cmd, cwd=cwd or PROJECT_DIR, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            _print_fail(f"{desc} failed")
            if r.stderr:
                print(r.stderr[:2000])
            sys.exit(1)
        return r.stdout or ""
    except FileNotFoundError:
        _print_fail(f"{desc} \u2014 command not found: {cmd[0]}")
        sys.exit(1)


def _venv_paths() -> tuple[Path, Path, Path]:
    """Return (venv_dir, python_bin, pip_bin)."""
    venv_dir = PROJECT_DIR / ".venv"
    if platform.system().lower() == "windows":
        scripts = venv_dir / "Scripts"
        py = scripts / "python.exe"
        pip_exe = scripts / "pip.exe"
    else:
        scripts = venv_dir / "bin"
        py = scripts / "python"
        pip_exe = scripts / "pip"
    return venv_dir, py, pip_exe


def _create_venv(python: Path) -> tuple[Path, Path]:
    venv_dir, py, pip_exe = _venv_paths()
    if py.exists():
        _print_ok(f"Virtual environment already exists \u2014 {venv_dir}")
        return py, pip_exe
    _print_step("Creating virtual environment...")
    _run([str(python), "-m", "venv", str(venv_dir)], "venv creation")
    _print_ok(f"Virtual environment created \u2014 {venv_dir}")
    return py, pip_exe


def _upgrade_pip(python: Path) -> None:
    _print_step("Upgrading pip...")
    _run([str(python), "-m", "pip", "install", "--upgrade", "pip"], "pip upgrade")


def _install_core(python: Path) -> None:
    _print_step("Installing LitePaperReader core...")
    _run([str(python), "-m", "pip", "install", "-e", str(PROJECT_DIR)], "core install")
    _print_ok("Core package installed")


def _install_extras(python: Path, extras: list[str]) -> None:
    if not extras:
        return
    label = ",".join(extras)
    _print_step(f"Installing extras: [{label}]")
    spec = f"{PROJECT_DIR}[{label}]"
    _run([str(python), "-m", "pip", "install", "-e", spec], f"extras install: {label}")
    _print_ok(f"Extras installed: {label}")


def _create_launchers(python: Path) -> list[str]:
    """Create convenience launcher scripts for webui.py and mcp_server.py."""
    _print_step("Creating launcher scripts...")
    platform_name = _detect_platform()
    launchers_created: list[str] = []

    entries = [
        ("litepaperreader-webui", "webui.py", "Start LitePaperReader Web UI"),
        ("litepaperreader-mcp", "mcp_server.py", "Start LitePaperReader MCP Server"),
    ]

    if platform_name == "windows":
        for name, script, desc in entries:
            bat_path = PROJECT_DIR / f"{name}.bat"
            py_exec = str(python)
            script_path = str(PROJECT_DIR / script)
            content = f"""@echo off
cd /d "{PROJECT_DIR}"
"{py_exec}" "{script_path}"
if errorlevel 1 pause
"""
            bat_path.write_text(content, encoding="utf-8")
            launchers_created.append(bat_path.name)
            _print_ok(f"  {name}.bat \u2014 {desc}")
    else:
        for name, script, desc in entries:
            sh_path = PROJECT_DIR / name
            py_exec = str(python)
            script_path = str(PROJECT_DIR / script)
            content = f"""#!/usr/bin/env bash
set -e
cd "{PROJECT_DIR}"
exec "{py_exec}" "{script_path}" "$@"
"""
            sh_path.write_text(content, encoding="utf-8")
            sh_path.chmod(sh_path.stat().st_mode | stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            launchers_created.append(sh_path.name)
            _print_ok(f"  {name} \u2014 {desc}")

    return launchers_created


def _print_summary(python: Path, extras: list[str], launchers: list[str]) -> None:
    platform_name = _detect_platform()
    print()
    print("=" * 60)
    print("  \033[1;32mInstallation complete!\033[0m")
    print("=" * 60)
    print()
    print(f"  Python        : {python}")
    print(f"  Project       : {PROJECT_DIR}")
    print(f"  Extras        : {', '.join(extras) if extras else '(core only)'}")
    print()

    if launchers:
        print("  \033[1mLaunchers:\033[0m")
        for l in launchers:
            print(f"    \033[1;36m{l}\033[0m")
        print()

    print("  \033[1mQuick start:\033[0m")
    if platform_name == "windows":
        print(f"    {PROJECT_DIR}\\litepaperreader-webui.bat")
        print(f"    {PROJECT_DIR}\\litepaperreader-mcp.bat")
    else:
        print(f"    {PROJECT_DIR}/litepaperreader-webui")
        print(f"    {PROJECT_DIR}/litepaperreader-mcp")
    print()
    print("  Open http://localhost:8765 in your browser.")
    print()

    # Suggest adding to PATH
    print("  \033[1mTip:\033[0m Add the project directory to your PATH to run launchers from anywhere.")
    if platform_name == "windows":
        print(f"    $env:Path += \";\" + \"{PROJECT_DIR}\"")
    else:
        print(f"    export PATH=\"$PATH:{PROJECT_DIR}\"")
    print()


def _prompt_extras_interactive() -> list[str]:
    """Ask the user which extras they want."""
    print()
    print("  \033[1mOptional dependency groups\033[0m")
    print("  " + "-" * 50)

    extra_keys = ["pdf", "embed", "code", "web", "yaml", "dev"]
    chosen: list[str] = []

    for key in extra_keys:
        label = AVAILABLE_EXTRAS[key]
        help_text = EXTRAS_HELP[key]
        while True:
            ans = input(f"  Install {label}?  [y/N] ").strip().lower()
            if ans in ("", "n", "no"):
                break
            if ans in ("y", "yes"):
                chosen.append(key)
                break
            print("    Please answer y or n.")

    return chosen


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="install.py",
        description=f"Install {PROJECT_NAME} \u2014 cross-platform Python package installer.",
    )
    p.add_argument(
        "--all", action="store_true",
        help="Install all optional dependencies (pdf, embed, code, web, yaml, dev)",
    )
    p.add_argument(
        "--extras", type=str, default=None,
        help="Comma-separated list of extras to install, e.g. 'pdf,web,code'",
    )
    p.add_argument(
        "--no-venv", action="store_true",
        help="Install into the system Python instead of creating a virtual environment",
    )
    p.add_argument(
        "--non-interactive", "-y", action="store_true",
        help="Skip prompts; only core dependencies unless --all or --extras is set",
    )
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    _print_banner()

    # 1. Check Python
    python = _check_python()
    _check_pip(python)

    # 2. Decide on venv vs system
    if args.no_venv:
        py_target = python
    else:
        venv_dir, py_target, pip_target = _venv_paths()
        if not py_target.exists():
            py_target, pip_target = _create_venv(python)
            _upgrade_pip(py_target)
        else:
            _print_ok(f"Virtual environment exists \u2014 {venv_dir}")

    # 3. Determine extras
    extras: list[str] = []
    if args.all:
        extras = ["all"]
    elif args.extras:
        extras = [e.strip() for e in args.extras.split(",") if e.strip()]
    elif not args.non_interactive:
        extras = _prompt_extras_interactive()

    # 4. Upgrade pip in target
    _upgrade_pip(py_target)

    # 5. Install core
    _install_core(py_target)

    # 6. Install extras
    _install_extras(py_target, extras)

    # 7. Create launcher scripts
    launchers = _create_launchers(py_target)

    # 8. Summary
    flat_extras = extras if extras != ["all"] else list(AVAILABLE_EXTRAS.keys())
    _print_summary(py_target, flat_extras, launchers)


if __name__ == "__main__":
    main()
