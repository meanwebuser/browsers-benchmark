#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

STATE_DIR="$REPO_ROOT/.install_state"
mkdir -p "$STATE_DIR"

PLAYWRIGHT_INSTALL_DEPS="${PLAYWRIGHT_INSTALL_DEPS:-auto}" # auto|always|never
VENV_DIR="${VENV_DIR:-}"

log() {
  printf '[install] %s\n' "$*"
}

warn() {
  printf '[install][warn] %s\n' "$*" >&2
}

die() {
  printf '[install][error] %s\n' "$*" >&2
  exit 1
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

sha256_of_file() {
  if have_cmd sha256sum; then
    sha256sum "$1" | awk '{print $1}'
  elif have_cmd shasum; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    die "Need 'sha256sum' or 'shasum' for change detection."
  fi
}

get_py_pkg_version() {
  "$VENV_PY" - "$1" <<'PY'
import importlib.metadata
import sys
pkg = sys.argv[1]
try:
    print(importlib.metadata.version(pkg))
except importlib.metadata.PackageNotFoundError:
    print("missing")
PY
}

if have_cmd python3; then
  PYTHON_BIN="python3"
elif have_cmd python; then
  PYTHON_BIN="python"
else
  die "Python is required but was not found."
fi

if ! have_cmd git; then
  die "git is required but was not found."
fi

if ! have_cmd node || ! have_cmd npm; then
  die "Node.js + npm are required but were not found."
fi

if [ -z "$VENV_DIR" ]; then
  if [ -d ".venv" ]; then
    VENV_DIR=".venv"
  elif [ -d "venv" ]; then
    VENV_DIR="venv"
  else
    VENV_DIR=".venv"
  fi
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  log "Creating virtualenv at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  log "Using existing virtualenv at $VENV_DIR"
fi

VENV_PY="$REPO_ROOT/$VENV_DIR/bin/python"

PIP_TOOLING_SIG_FILE="$STATE_DIR/pip_tooling.sig"
PIP_TOOLING_SIG="$("$VENV_PY" -c 'import platform; print(platform.python_version())')"
if [ ! -f "$PIP_TOOLING_SIG_FILE" ] || [ "$PIP_TOOLING_SIG" != "$(cat "$PIP_TOOLING_SIG_FILE")" ]; then
  log "Updating pip tooling"
  "$VENV_PY" -m pip install --upgrade pip setuptools wheel >/dev/null
  printf '%s' "$PIP_TOOLING_SIG" > "$PIP_TOOLING_SIG_FILE"
else
  log "Pip tooling already updated for this Python version, skipping"
fi

if [ ! -f requirements.txt ]; then
  die "requirements.txt not found"
fi

REQ_SIG_FILE="$STATE_DIR/requirements.sig"
REQ_SIG="$("$VENV_PY" -c 'import platform; print(platform.python_version())')|$(sha256_of_file requirements.txt)"
if [ ! -f "$REQ_SIG_FILE" ] || [ "$REQ_SIG" != "$(cat "$REQ_SIG_FILE")" ]; then
  log "Installing Python dependencies"
  "$VENV_PY" -m pip install -r requirements.txt
  printf '%s' "$REQ_SIG" > "$REQ_SIG_FILE"
else
  log "Python dependencies unchanged, skipping"
fi

NPM_SIG_FILE="$STATE_DIR/npm.sig"
NPM_SOURCE_FILE="package-lock.json"
if [ ! -f "$NPM_SOURCE_FILE" ]; then
  NPM_SOURCE_FILE="package.json"
fi

if [ -f "$NPM_SOURCE_FILE" ]; then
  NPM_SIG="$(sha256_of_file "$NPM_SOURCE_FILE")"
  NPM_CHANGED=1
  if [ -f "$NPM_SIG_FILE" ] && [ "$NPM_SIG" = "$(cat "$NPM_SIG_FILE")" ] && [ -d node_modules ]; then
    NPM_CHANGED=0
  fi

  if [ "$NPM_CHANGED" -eq 1 ]; then
    if [ -f package-lock.json ]; then
      log "Installing Node dependencies with npm ci"
      npm ci
    else
      log "Installing Node dependencies with npm install"
      npm install
    fi
    printf '%s' "$NPM_SIG" > "$NPM_SIG_FILE"
  else
    log "Node dependencies unchanged, skipping"
  fi
else
  warn "No package.json/package-lock.json found, skipping npm install"
fi

PLAYWRIGHT_SIG_FILE="$STATE_DIR/playwright.sig"
PLAYWRIGHT_SIG="$(get_py_pkg_version playwright)"
if [ ! -f "$PLAYWRIGHT_SIG_FILE" ] || [ "$PLAYWRIGHT_SIG" != "$(cat "$PLAYWRIGHT_SIG_FILE")" ]; then
  log "Installing Playwright browsers"
  "$VENV_PY" -m playwright install
  printf '%s' "$PLAYWRIGHT_SIG" > "$PLAYWRIGHT_SIG_FILE"
else
  log "Playwright browsers already installed, skipping"
fi

if [ "$PLAYWRIGHT_INSTALL_DEPS" != "never" ]; then
  SHOULD_INSTALL_DEPS=0
  PLAYWRIGHT_DEPS_MARKER="$STATE_DIR/playwright-deps.done"
  if [ "$PLAYWRIGHT_INSTALL_DEPS" = "always" ]; then
    SHOULD_INSTALL_DEPS=1
  elif [ "$PLAYWRIGHT_INSTALL_DEPS" = "auto" ] && [ ! -f "$PLAYWRIGHT_DEPS_MARKER" ] && [ "$(uname -s)" = "Linux" ]; then
    SHOULD_INSTALL_DEPS=1
  fi

  if [ "$SHOULD_INSTALL_DEPS" -eq 1 ]; then
    if [ "$(id -u)" -eq 0 ]; then
      log "Installing Playwright system dependencies (root)"
      "$VENV_PY" -m playwright install-deps
      touch "$PLAYWRIGHT_DEPS_MARKER"
    elif have_cmd sudo; then
      log "Installing Playwright system dependencies (sudo may prompt)"
      sudo "$VENV_PY" -m playwright install-deps
      touch "$PLAYWRIGHT_DEPS_MARKER"
    else
      warn "sudo not found; skipping playwright install-deps"
    fi
  else
    log "Playwright system dependencies unchanged, skipping"
  fi
else
  log "PLAYWRIGHT_INSTALL_DEPS=never, skipping playwright install-deps"
fi

CAMOUFOX_SIG_FILE="$STATE_DIR/camoufox.sig"
CAMOUFOX_SIG="$(get_py_pkg_version camoufox)"
if [ ! -f "$CAMOUFOX_SIG_FILE" ] || [ "$CAMOUFOX_SIG" != "$(cat "$CAMOUFOX_SIG_FILE")" ]; then
  log "Fetching Camoufox browser bundle"
  "$VENV_PY" -m camoufox fetch
  printf '%s' "$CAMOUFOX_SIG" > "$CAMOUFOX_SIG_FILE"
else
  log "Camoufox bundle already fetched, skipping"
fi

PATCHRIGHT_SIG_FILE="$STATE_DIR/patchright.sig"
PATCHRIGHT_SIG="$(get_py_pkg_version patchright)"
if [ ! -f "$PATCHRIGHT_SIG_FILE" ] || [ "$PATCHRIGHT_SIG" != "$(cat "$PATCHRIGHT_SIG_FILE")" ]; then
  log "Installing Patchright Chromium"
  "$VENV_PY" -m patchright install chromium
  printf '%s' "$PATCHRIGHT_SIG" > "$PATCHRIGHT_SIG_FILE"
else
  log "Patchright Chromium already installed, skipping"
fi

CURRENT_HOOKS_PATH="$(git config --get core.hooksPath || true)"
if [ "$CURRENT_HOOKS_PATH" != ".githooks" ]; then
  log "Setting git hooks path to .githooks"
  git config core.hooksPath .githooks
else
  log "Git hooks path already configured, skipping"
fi

STEALTH_SRC="$REPO_ROOT/utils/js_scripts/stealth_improved.js"
STEALTH_OBF="$REPO_ROOT/utils/js_scripts/stealth_improved.obf.js"
if [ ! -f "$STEALTH_OBF" ] || [ "$STEALTH_SRC" -nt "$STEALTH_OBF" ]; then
  log "Refreshing obfuscated stealth script"
  ./scripts/obfuscate_improved_stealth.sh
else
  log "Obfuscated stealth script up to date, skipping"
fi

if [ ! -f .env ] && [ -f .env.example ]; then
  log "Creating .env from .env.example"
  cp .env.example .env
fi

if [ ! -f documents/proxies.txt ] && [ -f documents/proxies.txt.example ]; then
  log "Creating documents/proxies.txt from example"
  cp documents/proxies.txt.example documents/proxies.txt
fi

log "Install completed"
