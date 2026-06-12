#!/usr/bin/env bash
#
# LitePaperReader - Linux / macOS installer
#
# Checks for Python 3.11+, offers to install it via system package
# manager if missing, then delegates to install.py.
#
# Usage:
#   ./install.sh
#   ./install.sh --all
#   ./install.sh --extras pdf,web

set -euo pipefail

MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=11

R="\033[1;31m"
G="\033[1;32m"
C="\033[1;36m"
Y="\033[1;33m"
M="\033[1;35m"
N="\033[0m"

step()  { echo -e "\n  ${C}*${N} $1"; }
ok()    { echo -e "  ${G}\xE2\x9C\x93${N} $1"; }
warn()  { echo -e "  ${Y}!${N} $1"; }
fail()  { echo -e "  ${R}\xE2\x9C\x97${N} $1"; }

detect_os() {
  case "$(uname -s)" in
    Darwin*)  echo "macos" ;;
    Linux*)   echo "linux" ;;
    *)        echo "unsupported" ;;
  esac
}

OS=$(detect_os)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Banner
echo ""
echo -e "${M}"
echo "   ------------------------------------------------------------"
echo "    LITE PAPER READER  -  Universal Data Flow Engine"
echo "   ------------------------------------------------------------"
echo -e "${N}"
echo "  Installer for Linux / macOS"
echo ""

# Move to project root
cd "$SCRIPT_DIR"

# Find Python >= 3.11
find_python() {
  for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
      full_ver=$("$candidate" --version 2>&1 | grep -oP "\d+\.\d+\.\d+" | head -1)
      if [ -n "$full_ver" ]; then
        major="${full_ver%%.*}"
        minor="${full_ver#*.}"
        minor="${minor%%.*}"
        if [ "$major" -ge "$MIN_PYTHON_MAJOR" ] && [ "$minor" -ge "$MIN_PYTHON_MINOR" ]; then
          echo "$candidate"
          return 0
        fi
      fi
    fi
  done
  return 1
}

PYTHON=""
PYTHON=$(find_python) || true

if [ -z "$PYTHON" ]; then
  warn "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ is not installed."
  echo ""
  echo "  Install it using your package manager:"

  case "$OS" in
    linux)
      echo ""
      if command -v apt &>/dev/null; then
        echo "    sudo apt update && sudo apt install -y python3 python3-pip python3-venv"
      elif command -v dnf &>/dev/null; then
        echo "    sudo dnf install -y python3 python3-pip"
      elif command -v pacman &>/dev/null; then
        echo "    sudo pacman -Sy python python-pip"
      elif command -v zypper &>/dev/null; then
        echo "    sudo zypper install -y python3 python3-pip"
      else
        echo "    Please install Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ manually."
      fi
      echo ""
      echo "  Or use pyenv:"
      echo "    curl https://pyenv.run | bash"
      echo "    pyenv install ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}"
      echo "    pyenv global ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}"
      ;;
    macos)
      echo ""
      if command -v brew &>/dev/null; then
        echo "    brew install python@3.11"
      else
        echo "  Install Homebrew first: https://brew.sh"
        echo "  Then: brew install python@3.11"
      fi
      echo ""
      echo "  Or use pyenv:"
      echo "    brew install pyenv"
      echo "    pyenv install ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}"
      echo "    pyenv global ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}"
      ;;
    *)
      fail "Unsupported OS: $(uname -s)"
      exit 1
      ;;
  esac

  echo ""
  read -rp "  Press Enter after installing Python, or Ctrl+C to abort... " _
  PYTHON=$(find_python) || true
  if [ -z "$PYTHON" ]; then
    fail "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ still not found."
    exit 1
  fi
fi

ok "Python $("$PYTHON" --version 2>&1 | head -1) -- $(command -v "$PYTHON")"

# Ensure pip
if ! "$PYTHON" -m pip --version &>/dev/null; then
  step "Installing pip..."
  "$PYTHON" -m ensurepip --upgrade
fi
ok "pip ready"

# Delegate to install.py
if [ $# -eq 0 ]; then
  step "Launching interactive installer..."
  exec "$PYTHON" "$SCRIPT_DIR/install.py"
else
  step "Launching installer with: $*"
  exec "$PYTHON" "$SCRIPT_DIR/install.py" "$@"
fi
