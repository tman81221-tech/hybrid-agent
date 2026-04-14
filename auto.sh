#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  OSINT Platform — الحل الأوتوماتيكي الكامل
#  يحدّث المنصة + يشغّلها في الخلفية + يربطها بـ Maltego تلقائياً
#  نسخ ولصق في الترمينال — بدون أي تدخل بشري
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

G='\033[0;32m'; B='\033[0;34m'; Y='\033[1;33m'
C='\033[0;36m'; R='\033[0;31m'; NC='\033[0m'
ok()    { echo -e "${G}[✓]${NC} $*"; }
info()  { echo -e "${B}[•]${NC} $*"; }
warn()  { echo -e "${Y}[!]${NC} $*"; }
header(){ echo -e "\n${C}══════════════════════════════════════${NC}"; \
          echo -e "${C}  $*${NC}"; \
          echo -e "${C}══════════════════════════════════════${NC}"; }

REPO="https://github.com/tman81221-tech/hybrid-agent.git"
BRANCH="claude/osint-web-platform-Ok8ua"
DEST="$HOME/osint-platform"
APP="$DEST/osint_platform"
PORT=5000
MALTEGO_URL="http://127.0.0.1:${PORT}/maltego"

header "OSINT Platform — الحل الأوتوماتيكي"

# ──────────────────────────────────────────────────────────────────
# 1. حزم النظام
# ──────────────────────────────────────────────────────────────────
info "فحص الحزم المطلوبة…"
PKGS=(); command -v git     &>/dev/null || PKGS+=(git)
         command -v python3 &>/dev/null || PKGS+=(python3 python3-pip python3-venv)
         command -v curl    &>/dev/null || PKGS+=(curl)
if [[ ${#PKGS[@]} -gt 0 ]]; then
  sudo apt-get update -qq && sudo apt-get install -y -qq "${PKGS[@]}"
fi
ok "الحزم جاهزة"

# ──────────────────────────────────────────────────────────────────
# 2. استنساخ / تحديث الريبو
# ──────────────────────────────────────────────────────────────────
info "تحديث الكود…"
if [[ -d "$DEST/.git" ]]; then
  git -C "$DEST" fetch origin "$BRANCH" -q
  git -C "$DEST" checkout "$BRANCH" -q
  git -C "$DEST" pull origin "$BRANCH" -q
else
  git clone -b "$BRANCH" "$REPO" "$DEST" -q
fi
ok "الكود محدّث"

mkdir -p "$APP/reports" "$APP/logs"

# ──────────────────────────────────────────────────────────────────
# 3. بيئة Python + مكتبات
# ──────────────────────────────────────────────────────────────────
info "إعداد بيئة Python…"
[[ -d "$APP/.venv" ]] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade pip
"$APP/.venv/bin/pip" install -q flask requests
ok "مكتبات Python جاهزة"

# ──────────────────────────────────────────────────────────────────
# 4. إيقاف أي instance قديمة
# ──────────────────────────────────────────────────────────────────
pkill -f "python3.*app.py" 2>/dev/null && sleep 1 || true

# ──────────────────────────────────────────────────────────────────
# 5. تشغيل المنصة كخدمة في الخلفية (تستمر بعد إغلاق الترمينال)
# ──────────────────────────────────────────────────────────────────
info "تشغيل المنصة في الخلفية…"

# systemd (الأفضل — يعيد التشغيل تلقائياً)
if command -v systemctl &>/dev/null && [[ $EUID -ne 0 ]]; then
  SERVICE_FILE="$HOME/.config/systemd/user/osint-platform.service"
  mkdir -p "$(dirname "$SERVICE_FILE")"
  cat > "$SERVICE_FILE" << SVC
[Unit]
Description=OSINT Industries Web Platform
After=network.target

[Service]
WorkingDirectory=${APP}
ExecStart=${APP}/.venv/bin/python3 ${APP}/app.py
Restart=always
RestartSec=3
Environment=PORT=${PORT}
StandardOutput=append:${APP}/logs/server.log
StandardError=append:${APP}/logs/server.log

[Install]
WantedBy=default.target
SVC
  systemctl --user daemon-reload 2>/dev/null || true
  systemctl --user enable  osint-platform 2>/dev/null || true
  systemctl --user restart osint-platform 2>/dev/null || true
  ok "تم تسجيل systemd service (يبدأ تلقائياً عند التشغيل)"
else
  # fallback: nohup
  nohup "$APP/.venv/bin/python3" "$APP/app.py" \
    >> "$APP/logs/server.log" 2>&1 &
  echo $! > "$APP/server.pid"
  ok "تشغيل بـ nohup (PID $(cat "$APP/server.pid"))"
fi

# انتظر حتى يصبح جاهزاً
info "انتظار جاهزية المنصة…"
for i in $(seq 1 20); do
  if curl -sf "http://127.0.0.1:${PORT}/api/ollama" >/dev/null 2>&1; then
    ok "المنصة جاهزة على http://127.0.0.1:${PORT}"; break
  fi
  sleep 1
  [[ $i -eq 20 ]] && { warn "المنصة لم تستجب بعد 20 ثانية — تحقق من logs/server.log"; }
done

# ──────────────────────────────────────────────────────────────────
# 6. ربط Maltego تلقائياً
# ──────────────────────────────────────────────────────────────────
info "البحث عن Maltego وإعداده تلقائياً…"

# --- أين ملفات إعداد Maltego؟ ---
MALTEGO_CONF_DIR=""
for d in \
  "$HOME/.maltego/v4/config" \
  "$HOME/.maltego/config"    \
  "$HOME/.local/share/maltego/config" \
  "/opt/Maltego4/config"     \
  "/opt/maltego/config"; do
  [[ -d "$d" ]] && { MALTEGO_CONF_DIR="$d"; break; }
done

# --- كتابة XML التسجيل مباشرة في Maltego ---
MALTEGO_SERVER_XML() {
cat << XML
<?xml version="1.0" encoding="UTF-8"?>
<MaltegoServer enabled="true"
               lastSync="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
               name="OSINT Platform"
               summary="OSINT Industries + HIBP live transforms"
               url="http://127.0.0.1:${PORT}"
               uuid="osint-platform-local-v2"
               protocol="0.0">
  <Transforms>
    <Transform name="osint.EmailLookup"
               displayName="[OSINT] Email → Registered Platforms">
      <UI displayName="[OSINT] Email → Registered Platforms"/>
      <Limits HardLimit="255" SoftLimit="12"/>
      <Transform>
        <URL>http://127.0.0.1:${PORT}/maltego/email_lookup</URL>
      </Transform>
      <InputConstraints>
        <Property name="fields" type="entityType" value="maltego.EmailAddress"/>
      </InputConstraints>
    </Transform>
    <Transform name="osint.HIBPCheck"
               displayName="[OSINT] Email → HIBP Breaches">
      <UI displayName="[OSINT] Email → HIBP Breaches"/>
      <Limits HardLimit="255" SoftLimit="12"/>
      <Transform>
        <URL>http://127.0.0.1:${PORT}/maltego/hibp_check</URL>
      </Transform>
      <InputConstraints>
        <Property name="fields" type="entityType" value="maltego.EmailAddress"/>
      </InputConstraints>
    </Transform>
    <Transform name="osint.PhoneLookup"
               displayName="[OSINT] Phone → Registered Platforms">
      <UI displayName="[OSINT] Phone → Registered Platforms"/>
      <Limits HardLimit="255" SoftLimit="12"/>
      <Transform>
        <URL>http://127.0.0.1:${PORT}/maltego/phone_lookup</URL>
      </Transform>
      <InputConstraints>
        <Property name="fields" type="entityType" value="maltego.PhoneNumber"/>
      </InputConstraints>
    </Transform>
    <Transform name="osint.UsernameLookup"
               displayName="[OSINT] Username → Registered Platforms">
      <UI displayName="[OSINT] Username → Registered Platforms"/>
      <Limits HardLimit="255" SoftLimit="12"/>
      <Transform>
        <URL>http://127.0.0.1:${PORT}/maltego/username_lookup</URL>
      </Transform>
      <InputConstraints>
        <Property name="fields" type="entityType" value="maltego.Alias"/>
      </InputConstraints>
    </Transform>
  </Transforms>
</MaltegoServer>
XML
}

# اكتب في مجلد Maltego المكتشف
if [[ -n "$MALTEGO_CONF_DIR" ]]; then
  REPO_DIR="$MALTEGO_CONF_DIR/TransformRepositories/RemoteTransformRepositories"
  mkdir -p "$REPO_DIR"
  MALTEGO_SERVER_XML > "$REPO_DIR/osint-platform.server"
  ok "تم كتابة إعداد Maltego في: $REPO_DIR"
fi

# أنشئ ملف seed على سطح المكتب (نسخة احتياطية)
DESKTOP="${HOME}/Desktop"
mkdir -p "$DESKTOP" 2>/dev/null || true
echo "$MALTEGO_URL" > "$DESKTOP/OSINT-Platform-Transforms.itds"
ok "تم إنشاء ملف التسجيل على سطح المكتب"

# ابحث عن مجلد Maltego في أي مكان وأضف الملفات
for d in $(find /opt /usr/share /usr/local "$HOME" -maxdepth 5 \
           -iname "*maltego*" -type d 2>/dev/null | head -5); do
  SUB="$d/config/TransformRepositories/RemoteTransformRepositories"
  if [[ -d "$(dirname "$(dirname "$SUB")")" ]]; then
    mkdir -p "$SUB"
    MALTEGO_SERVER_XML > "$SUB/osint-platform.server"
    ok "Maltego config written → $SUB"
  fi
done

# ──────────────────────────────────────────────────────────────────
# 7. النتيجة النهائية
# ──────────────────────────────────────────────────────────────────
header "اكتمل الإعداد"
echo ""
echo -e "  ${G}المنصة:${NC}    http://127.0.0.1:${PORT}"
echo -e "  ${G}Maltego:${NC}   http://127.0.0.1:${PORT}/maltego"
echo ""
echo -e "  ${C}لإضافة الـ Transforms في Maltego (مرة واحدة فقط):${NC}"
echo -e "  Transforms → Import Config → الصق هذا الـ URL:"
echo ""
echo -e "    ${Y}http://127.0.0.1:${PORT}/maltego${NC}"
echo ""
echo -e "  ${B}أو اسحب الملف:${NC} ~/Desktop/OSINT-Platform-Transforms.itds"
echo "  وافتحه بـ Maltego مباشرة"
echo ""
