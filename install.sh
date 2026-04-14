#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  OSINT Industries Web Platform – Full Auto Install & Launch
#  نسخه وألصقه مباشرة في الترمينال:
#  bash <(curl -fsSL https://raw.githubusercontent.com/tman81221-tech/hybrid-agent/claude/osint-web-platform-Ok8ua/install.sh)
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

# ── ألوان ──────────────────────────────────────────────────────
R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'
B='\033[0;34m'; C='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${B}[•]${NC} $*"; }
ok()    { echo -e "${G}[✓]${NC} $*"; }
warn()  { echo -e "${Y}[!]${NC} $*"; }
die()   { echo -e "${R}[✗]${NC} $*" >&2; exit 1; }
header(){ echo -e "\n${C}══════════════════════════════════════════${NC}"; \
          echo -e "${C}  $*${NC}"; \
          echo -e "${C}══════════════════════════════════════════${NC}\n"; }

REPO_URL="https://github.com/tman81221-tech/hybrid-agent.git"
BRANCH="claude/osint-web-platform-Ok8ua"
DEST="$HOME/osint-platform"
APP="$DEST/osint_platform"
VENV="$APP/.venv"
CONFIG="$APP/config.json"
PORT="${PORT:-5000}"

header "OSINT Industries Web Platform – Auto Install"

# ─────────────────────────────────────────────
# 1. حزم النظام
# ─────────────────────────────────────────────
info "فحص حزم النظام…"
PKGS=()
command -v git     &>/dev/null || PKGS+=(git)
command -v python3 &>/dev/null || PKGS+=(python3 python3-pip python3-venv)
command -v curl    &>/dev/null || PKGS+=(curl)

if [[ ${#PKGS[@]} -gt 0 ]]; then
  info "تثبيت: ${PKGS[*]}"
  sudo apt-get update -qq
  sudo apt-get install -y "${PKGS[@]}" -qq
fi
ok "حزم النظام جاهزة."

# ─────────────────────────────────────────────
# 2. استنساخ / تحديث الريبو
# ─────────────────────────────────────────────
if [[ -d "$DEST/.git" ]]; then
  info "تحديث النسخة الموجودة في $DEST …"
  git -C "$DEST" fetch origin "$BRANCH" -q
  git -C "$DEST" checkout "$BRANCH" -q
  git -C "$DEST" pull origin "$BRANCH" -q
  ok "تم التحديث."
else
  info "استنساخ الريبو إلى $DEST …"
  git clone -b "$BRANCH" "$REPO_URL" "$DEST" -q
  ok "تم الاستنساخ."
fi

mkdir -p "$APP/reports" "$APP/logs"

# ─────────────────────────────────────────────
# 3. بيئة Python الافتراضية
# ─────────────────────────────────────────────
if [[ ! -d "$VENV" ]]; then
  info "إنشاء بيئة Python افتراضية…"
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
ok "بيئة Python نشطة."

# ─────────────────────────────────────────────
# 4. مكتبات Python
# ─────────────────────────────────────────────
info "تثبيت مكتبات Python…"
pip install --quiet --upgrade pip
pip install --quiet flask requests
ok "المكتبات جاهزة."

# ─────────────────────────────────────────────
# 5. Ollama + نموذج AI
# ─────────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
  info "تثبيت Ollama لتحليل AI…"
  curl -fsSL https://ollama.com/install.sh | sh -s -- 2>/dev/null || \
    warn "تثبيت Ollama فشل – تحليل AI لن يكون متاحاً."
fi

if command -v ollama &>/dev/null; then
  # تأكد أن خدمة ollama شغّالة
  ollama serve &>/dev/null & disown 2>/dev/null || true
  sleep 1

  FIRST_MODEL=$(ollama list 2>/dev/null | awk 'NR>1 && $1 {print $1; exit}' || true)
  if [[ -z "$FIRST_MODEL" ]]; then
    info "تحميل نموذج llama3 (قد يستغرق بضع دقائق)…"
    ollama pull llama3 || warn "فشل تحميل النموذج – يمكنك تشغيله لاحقاً: ollama pull llama3"
  else
    ok "نموذج AI متاح: $FIRST_MODEL"
  fi
fi

# ─────────────────────────────────────────────
# 6. إعداد API Key (مرة واحدة فقط)
# ─────────────────────────────────────────────
if [[ ! -f "$CONFIG" ]] || ! python3 -c "
import json,sys
d=json.load(open('$CONFIG'))
sys.exit(0 if d.get('api_key','').strip() else 1)
" 2>/dev/null; then

  header "إعداد OSINT Industries"
  echo -e "  الرجاء إدخال بيانات API الخاصة بك."
  echo -e "  (يمكنك تركها فارغة والإعداد لاحقاً من Settings في الواجهة)\n"

  read -rp "  🔑  API Key: " API_KEY
  read -rp "  🌐  API Endpoint  [اضغط Enter للافتراضي]: " BASE_URL
  BASE_URL="${BASE_URL:-https://api.osint.industries/v2/request}"

  echo ""
  echo "  نمط إرسال الـ API Key:"
  echo "    1) apikey               ← الافتراضي (OSINT Industries)"
  echo "    2) Authorization: Bearer"
  echo "    3) X-API-Key"
  read -rp "  اختر [1]: " AUTH_CHOICE
  case "${AUTH_CHOICE:-1}" in
    2) AUTH_HEADER="Bearer"    ;;
    3) AUTH_HEADER="X-API-Key" ;;
    *) AUTH_HEADER="apikey"    ;;
  esac

  # كتابة JSON بأمان (لا مشاكل من رموز خاصة في API key)
  python3 - "$API_KEY" "$BASE_URL" "$AUTH_HEADER" "$CONFIG" << 'PYEOF'
import json, pathlib, sys
api_key, base_url, auth_header, config_path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
cfg = {"api_key": api_key, "base_url": base_url, "auth_header": auth_header}
p = pathlib.Path(config_path)
p.write_text(json.dumps(cfg, indent=2))
p.chmod(0o600)
PYEOF

  ok "تم حفظ الإعدادات في $CONFIG"
fi

# ─────────────────────────────────────────────
# 7. تشغيل المنصة
# ─────────────────────────────────────────────
header "المنصة جاهزة!"
echo -e "  ${G}افتح المتصفح على:${NC}  ${C}http://127.0.0.1:${PORT}${NC}"
echo -e "  ${Y}إيقاف التشغيل:${NC}   Ctrl+C\n"

cd "$APP"
PORT="$PORT" "$VENV/bin/python3" "$APP/app.py"
