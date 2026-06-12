#!/usr/bin/env python3
"""Build LitePaperReader Windows standalone installer (.exe).

Uses PyInstaller to bundle the installer + project metadata into a single
executable that can be run without Python.

Usage:
    python build_exe.py                     # build .exe
    python build_exe.py --onefile           # single-file .exe (default)
    python build_exe.py --onedir            # directory mode (for debugging)

Output:
    dist/LitePaperReader_Setup.exe
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_NAME = "LitePaperReader"
PROJECT_DIR = Path(__file__).resolve().parent


def _step(msg: str) -> None:
    print(f"\n  \033[1;36m*\033[0m {msg}")


def _ok(msg: str) -> None:
    print(f"  \033[1;32m\u2713\033[0m {msg}")


def _fail(msg: str) -> None:
    print(f"  \033[1;31m\u2717\033[0m {msg}")


def check_prerequisites() -> None:
    """Ensure PyInstaller is available."""
    _step("Checking prerequisites")

    if platform.system().lower() != "windows":
        _fail("This builder only works on Windows (produces .exe)")
        sys.exit(1)

    try:
        import PyInstaller  # noqa: F401
        _ok("PyInstaller is available")
    except ImportError:
        _step("Installing PyInstaller...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            check=True,
        )
        _ok("PyInstaller installed")


def clean_build() -> None:
    """Remove previous build artifacts."""
    _step("Cleaning previous builds")
    for d in ["build", "dist", "__pycache__"]:
        p = PROJECT_DIR / d
        if p.exists():
            shutil.rmtree(p)
            _ok(f"Removed {d}")


def build_exe() -> None:
    """Run PyInstaller to create the .exe."""
    _step("Building .exe with PyInstaller")

    exe_path = PROJECT_DIR / "dist" / f"{PROJECT_NAME}_Setup.exe"

    # Entry point: we bundle the bootstrap installer
    entry_point = PROJECT_DIR / "get-litepaperreader.py"
    if not entry_point.exists():
        _fail(f"Entry point not found: {entry_point}")
        _fail("Run this script from the project root directory.")
        sys.exit(1)

    banner_file = PROJECT_DIR / "assets" / "logo.png"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", f"{PROJECT_NAME}_Setup",
        "--console",
        "--clean",
        "--noconfirm",
        f"--distpath={PROJECT_DIR / 'dist'}",
        f"--workpath={PROJECT_DIR / 'build'}",
        "--add-data", f"{entry_point}{os.pathsep}.",
        "--add-data", f"{PROJECT_DIR / 'install.py'}{os.pathsep}.",
        "--add-data", f"{PROJECT_DIR / 'install.ps1'}{os.pathsep}.",
        "--add-data", f"{PROJECT_DIR / 'install.sh'}{os.pathsep}.",
        "--add-data", f"{PROJECT_DIR / 'pyproject.toml'}{os.pathsep}.",
        "--add-data", f"{PROJECT_DIR / 'LICENSE'}{os.pathsep}.",
        "--add-data", f"{PROJECT_DIR / 'README.md'}{os.pathsep}.",
        "--add-data", f"{PROJECT_DIR / 'litepaper_config.yaml'}{os.pathsep}.",
        "--add-data", f"{PROJECT_DIR / 'mcp_server.py'}{os.pathsep}.",
        "--add-data", f"{PROJECT_DIR / 'webui.py'}{os.pathsep}.",
        "--add-data", f"{PROJECT_DIR / 'webui_template.html'}{os.pathsep}.",
        "--hidden-import", "pydantic",
        "--hidden-import", "rank_bm25",
        "--hidden-import", "numpy",
        "--icon", str(banner_file) if banner_file.exists() else "",
        str(entry_point),
    ]

    # Remove empty icon arg
    cmd = [c for c in cmd if c]

    _ok(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_DIR)
    if result.returncode != 0:
        _fail("PyInstaller build failed")
        sys.exit(1)

    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        _ok(f"Executable created: {exe_path} ({size_mb:.1f} MB)")
    else:
        _fail("Executable not found at expected path")
        sys.exit(1)


def main() -> None:
    print(f"""
  \033[1;35m============================================\033[0m
   {PROJECT_NAME} — Windows Installer Builder
  \033[1;35m============================================\033[0m
""")
    check_prerequisites()
    clean_build()
    build_exe()
    print(f"""
  \033[1;32mBuild complete!\033[0m
  Output: {PROJECT_DIR / 'dist' / f'{PROJECT_NAME}_Setup.exe'}
""")


if __name__ == "__main__":
    main()
