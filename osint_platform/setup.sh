#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  OSINT Industries Web Platform – Setup & Launch Script
#  Usage:  bash setup.sh [--port 5000] [--no-ollama]
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=5000
INSTALL_OLLAMA=true

# ── Parse args ──────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)       PORT="$2";       shift 2 ;;
    --no-ollama)  INSTALL_OLLAMA=false; shift ;;
    *) echo "Unknown arg: $1"; shift ;;
  esac
done

info()    { echo "[INFO]  $*"; }
success() { echo "[OK]    $*"; }
warn()    { echo "[WARN]  $*"; }
error()   { echo "[ERROR] $*" >&2; }

# ── Python check ────────────────────────────────────────────────
info "Checking Python 3…"
if ! command -v python3 &>/dev/null; then
  info "Installing Python 3…"
  sudo apt-get update -qq
  sudo apt-get install -y python3 python3-pip python3-venv
fi

PYTHON_VER=$(python3 --version 2>&1)
success "Found: $PYTHON_VER"

# ── Virtual environment ─────────────────────────────────────────
VENV="$SCRIPT_DIR/.venv"
if [[ ! -d "$VENV" ]]; then
  info "Creating virtual environment at $VENV …"
  python3 -m venv "$VENV"
fi
success "Virtual environment ready."

# Activate
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# ── Python dependencies ─────────────────────────────────────────
info "Installing Python dependencies…"
pip install --quiet --upgrade pip
pip install --quiet -r "$SCRIPT_DIR/requirements.txt"
success "Dependencies installed."

# ── Ollama ──────────────────────────────────────────────────────
if [[ "$INSTALL_OLLAMA" == true ]]; then
  if ! command -v ollama &>/dev/null; then
    info "Installing Ollama…"
    curl -fsSL https://ollama.com/install.sh | sh
  else
    success "Ollama already installed: $(ollama --version 2>/dev/null || true)"
  fi

  # Pull a model if none are available
  MODELS=$(ollama list 2>/dev/null | awk 'NR>1 {print $1}' | head -1 || true)
  if [[ -z "$MODELS" ]]; then
    info "No Ollama model found. Pulling llama3 (this may take a while)…"
    ollama pull llama3 || warn "Could not pull llama3. AI analysis will be unavailable."
  else
    success "Ollama model available: $MODELS"
  fi
else
  warn "Skipping Ollama install (--no-ollama). AI analysis will be unavailable."
fi

# ── Report / log dirs ────────────────────────────────────────────
mkdir -p "$SCRIPT_DIR/reports" "$SCRIPT_DIR/logs"

# ── First-run config ─────────────────────────────────────────────
CONFIG="$SCRIPT_DIR/config.json"
if [[ ! -f "$CONFIG" ]]; then
  echo ""
  echo "╔══════════════════════════════════════════╗"
  echo "║     OSINT Industries – First Run Setup   ║"
  echo "╚══════════════════════════════════════════╝"
  echo ""

  read -rp "  Enter your OSINT Industries API key: " API_KEY
  if [[ -z "$API_KEY" ]]; then
    warn "No API key entered. You can set it later via the Settings panel in the UI."
    API_KEY=""
  fi

  read -rp "  API endpoint [https://api.osint.industries/v2/request]: " BASE_URL
  BASE_URL="${BASE_URL:-https://api.osint.industries/v2/request}"

  echo "  Auth header style:"
  echo "    1) apikey           (default – OSINT Industries standard)"
  echo "    2) Authorization: Bearer"
  echo "    3) X-API-Key"
  read -rp "  Choice [1]: " AUTH_CHOICE
  case "${AUTH_CHOICE:-1}" in
    2) AUTH_HEADER="Bearer"    ;;
    3) AUTH_HEADER="X-API-Key" ;;
    *) AUTH_HEADER="apikey"    ;;
  esac

  python3 - <<PYEOF
import json, pathlib
cfg = {
    "api_key":     "$API_KEY",
    "base_url":    "$BASE_URL",
    "auth_header": "$AUTH_HEADER"
}
p = pathlib.Path("$CONFIG")
p.write_text(json.dumps(cfg, indent=2))
p.chmod(0o600)
PYEOF
  success "Config saved to $CONFIG"
fi

# ── Launch ───────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Launching OSINT Industries Platform    ║"
echo "╚══════════════════════════════════════════╝"
echo ""
success "Open your browser at: http://127.0.0.1:$PORT"
echo ""

PORT="$PORT" python3 "$SCRIPT_DIR/app.py"
