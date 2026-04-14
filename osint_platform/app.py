#!/usr/bin/env python3
"""
OSINT Industries Web Platform
Integrates: OSINT Industries  •  HIBP  •  Maltego Export  •  Lampyre Import
"""

import csv
import html as _html
import io
import json
import logging
import hashlib
import math
import os
import subprocess
import time
import zipfile
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, render_template, request, jsonify, send_file, abort, Response

# ─────────────────────────────────────────────
# Paths & logging
# ─────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
REPORTS_DIR = BASE_DIR / "reports"
LOGS_DIR    = BASE_DIR / "logs"
CONFIG_FILE = BASE_DIR / "config.json"

for _d in [REPORTS_DIR, LOGS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "osint.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)
app = Flask(__name__)


# ═══════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════
def load_config() -> dict:
    cfg = {
        "api_key":    "",
        "base_url":   "https://api.osint.industries/v2/request",
        "auth_header": "api-key",
        "hibp_key":   "",
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg.update(json.load(f))
        except json.JSONDecodeError:
            log.warning("Config corrupt – using defaults")
    if os.environ.get("OSINT_API_KEY"):
        cfg["api_key"] = os.environ["OSINT_API_KEY"]
    if os.environ.get("HIBP_API_KEY"):
        cfg["hibp_key"] = os.environ["HIBP_API_KEY"]
    return cfg


def save_config(**kwargs) -> None:
    data = load_config()
    for k, v in kwargs.items():
        if v is not None:
            data[k] = str(v).strip()
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)
    CONFIG_FILE.chmod(0o600)
    log.info("Config saved")


# ═══════════════════════════════════════════════
# OSINT Industries Client
# ═══════════════════════════════════════════════
class OSINTClient:
    QUERY_TYPES = {"email", "phone", "username"}
    MAX_RETRIES = 4
    RETRY_CODES = {429, 500, 502, 503, 504}

    def __init__(self, api_key: str, base_url: str, auth_header: str = "api-key"):
        self.api_key   = api_key
        self.base_url  = base_url
        self.session   = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept":       "application/json",
            "User-Agent":   "OSINT-Platform/1.0",
        })
        style = auth_header.lower()
        if style == "bearer":
            self.session.headers["Authorization"] = f"Bearer {api_key}"
        elif style == "x-api-key":
            self.session.headers["X-API-Key"] = api_key
        else:
            self.session.headers["api-key"] = api_key

    def search(self, query: str, query_type: str, timeout: int = 60) -> dict:
        if query_type not in self.QUERY_TYPES:
            return {"success": False, "error": f"Invalid type '{query_type}'", "status": 400}

        payload = {"query": query.strip(), "type": query_type}
        t0 = time.monotonic()

        for attempt in range(self.MAX_RETRIES):
            wait = 2 ** attempt
            try:
                resp = self.session.post(self.base_url, json=payload, timeout=timeout)
                elapsed = round(time.monotonic() - t0, 2)

                if resp.status_code == 200:
                    try:    data = resp.json()
                    except: data = {"raw": resp.text}
                    log.info("OSINT OK type=%s t=%.2fs", query_type, elapsed)
                    return {"success": True, "data": data, "status": 200, "elapsed": elapsed}

                if resp.status_code == 404:
                    return {"success": True, "data": [], "status": 404,
                            "message": "No results found.", "elapsed": elapsed}

                if resp.status_code in (401, 403):
                    return {"success": False,
                            "error": f"Auth failed ({resp.status_code}). Check your API key.",
                            "status": resp.status_code}

                if resp.status_code in self.RETRY_CODES and attempt < self.MAX_RETRIES - 1:
                    log.warning("HTTP %d – retry in %ds", resp.status_code, wait)
                    time.sleep(wait)
                    continue

                return {"success": False,
                        "error": f"API error {resp.status_code}: {resp.text[:200]}",
                        "status": resp.status_code}

            except requests.exceptions.Timeout:
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(wait); continue
                return {"success": False, "error": "Timed out after all retries.", "status": 408}
            except requests.exceptions.ConnectionError as e:
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(wait); continue
                return {"success": False, "error": f"Connection failed: {e}", "status": 503}
            except Exception as e:
                log.exception("OSINT search error")
                return {"success": False, "error": str(e), "status": 500}

        return {"success": False, "error": "Max retries exceeded.", "status": 503}


# ═══════════════════════════════════════════════
# HIBP Client  (Have I Been Pwned v3)
# ═══════════════════════════════════════════════
class HIBPClient:
    BASE = "https://haveibeenpwned.com/api/v3"

    def __init__(self, api_key: str):
        self.session = requests.Session()
        self.session.headers.update({
            "hibp-api-key": api_key,
            "User-Agent":   "OSINT-Platform/1.0",
            "Accept":       "application/json",
        })

    def _get(self, path: str, params: dict = None) -> dict:
        for attempt in range(3):
            try:
                r = self.session.get(f"{self.BASE}{path}", params=params, timeout=20)
                if r.status_code == 200:
                    return {"success": True, "data": r.json()}
                if r.status_code == 404:
                    return {"success": True, "data": []}
                if r.status_code == 401:
                    return {"success": False, "error": "Invalid HIBP API key"}
                if r.status_code == 429:
                    time.sleep(2 ** attempt); continue
                return {"success": False, "error": f"HIBP {r.status_code}: {r.text[:100]}"}
            except Exception as e:
                if attempt == 2:
                    return {"success": False, "error": str(e)}
                time.sleep(2)
        return {"success": False, "error": "HIBP: max retries exceeded"}

    def breaches(self, email: str) -> dict:
        return self._get(f"/breachedaccount/{requests.utils.quote(email, safe='')}",
                         {"truncateResponse": "false"})

    def pastes(self, email: str) -> dict:
        return self._get(f"/pasteaccount/{requests.utils.quote(email, safe='')}")


# ═══════════════════════════════════════════════
# Lampyre Import Parser
# ═══════════════════════════════════════════════
def parse_lampyre(content: str, ext: str) -> list:
    """Parse Lampyre CSV or JSON export into a unified list of dicts."""
    ext = ext.lower()
    try:
        if ext == ".json":
            data = json.loads(content)
            return data if isinstance(data, list) else [data]

        # CSV (default Lampyre export)
        reader = csv.DictReader(io.StringIO(content))
        rows = []
        for row in reader:
            clean = {}
            for k, v in row.items():
                if k and v and str(v).strip():
                    clean[k.strip()] = str(v).strip()
            if clean:
                rows.append(clean)
        return rows
    except Exception as e:
        log.error("Lampyre parse error: %s", e)
        return []


# ═══════════════════════════════════════════════
# Maltego .mtgx Graph Export
# ═══════════════════════════════════════════════
def _esc(s) -> str:
    return _html.escape(str(s))


def _circle(index: int, total: int, cx: int, cy: int, r: int) -> tuple[int, int]:
    """Return (x, y) for evenly-spaced position on a circle."""
    angle = 2 * math.pi * index / max(total, 1) - math.pi / 2
    return int(cx + r * math.cos(angle)), int(cy + r * math.sin(angle))


def to_maltego_mtgx(query: str, query_type: str,
                    osint_modules: list, hibp_breaches: list) -> bytes:
    """
    Build a proper Maltego .mtgx graph file (ZIP containing Graphs/graph.xml).
    Layout: target at centre → OSINT platforms inner ring → HIBP breaches outer ring.
    """

    # ── Entity & link containers ──────────────────────────────
    entity_xmls = []
    link_xmls   = []
    eid         = 0      # entity id counter
    lid         = 0      # link id counter
    CX, CY      = 480, 360   # canvas centre

    def add_entity(etype: str, value: str, fields: dict,
                   x: int, y: int, color: str = "#4f9eff") -> int:
        nonlocal eid
        eid += 1
        fxml = "\n          ".join(
            f'<field displayName="{_esc(k)}" matchingRule="loose" name="{_esc(k.lower().replace(" ","_"))}">'
            f'{_esc(v)}</field>'
            for k, v in fields.items() if v
        )
        entity_xmls.append(f"""      <entity id="{eid}" type="{_esc(etype)}" x="{x}" y="{y}">
        <value>{_esc(value)}</value>
        <weight>100</weight>
        <additionalFields>
          {fxml}
        </additionalFields>
        <entityIcon><color>{color}</color></entityIcon>
      </entity>""")
        return eid

    def add_link(from_id: int, to_id: int, label: str) -> None:
        nonlocal lid
        lid += 1
        link_xmls.append(f"""      <link id="{lid}" from="{from_id}" to="{to_id}" label="{_esc(label)}">
        <weight>100</weight>
        <additionalFields/>
      </link>""")

    # ── 1. Target (centre) ────────────────────────────────────
    if query_type == "email":
        t_id = add_entity("maltego.EmailAddress", query,
                           {"Email Address": query}, CX, CY, "#0091cd")
    elif query_type == "phone":
        t_id = add_entity("maltego.PhoneNumber", query,
                           {"Phone Number": query}, CX, CY, "#e07b39")
    else:
        t_id = add_entity("maltego.Alias", query,
                           {"Alias": query}, CX, CY, "#7b5ea7")

    # ── 2. OSINT Industries platforms (inner ring, r=220) ─────
    found_mods = [m for m in osint_modules if m.get("status") == "found"]
    for i, mod in enumerate(found_mods):
        name  = mod.get("module", "unknown")
        cat   = (mod.get("category") or {}).get("name", "")
        sf    = ((mod.get("spec_format") or [{}])[0])
        ph    = (sf.get("phone_hint") or {}).get("value", "")
        x, y  = _circle(i, len(found_mods), CX, CY, 220)
        mid   = add_entity(
            "maltego.Website",
            f"{name}.com",
            {"Platform": name.capitalize(), "Category": cat, "Phone Hint": ph, "Status": "Registered"},
            x, y, "#3ecf8e",
        )
        add_link(t_id, mid, "registered on")

        # Phone hint as separate PhoneNumber entity (offset slightly)
        if ph:
            px, py = x + 80, y - 60
            pid = add_entity("maltego.PhoneNumber", ph,
                             {"Phone Number": ph, "Source": name.capitalize()},
                             px, py, "#e07b39")
            add_link(mid, pid, "phone hint")

    # ── 3. HIBP breaches (outer ring, r=400) ─────────────────
    for i, b in enumerate(hibp_breaches):
        bname   = b.get("Name", "Unknown")
        domain  = b.get("Domain", "") or f"{bname.lower()}.com"
        date    = b.get("BreachDate", "")
        count   = str(b.get("PwnCount", 0))
        classes = ", ".join(b.get("DataClasses", [])[:5])
        x, y    = _circle(i, len(hibp_breaches), CX, CY, 400)
        bid     = add_entity(
            "maltego.DNSName",
            domain,
            {"Breach Name": bname, "Breach Date": date,
             "Records Exposed": count, "Data Types": classes},
            x, y, "#e05252",
        )
        add_link(t_id, bid, f"breached ({date})")

    # ── Assemble graph.xml ────────────────────────────────────
    graph_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<MaltegoGraph version="1.2">
  <graph edgeStyle="curved" entityNamespace="maltego" imageStyle="round">
    <entities>
{chr(10).join(entity_xmls)}
    </entities>
    <links>
{chr(10).join(link_xmls)}
    </links>
  </graph>
</MaltegoGraph>"""

    # ── Pack into .mtgx (ZIP) ─────────────────────────────────
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Graphs/graph.xml", graph_xml.encode("utf-8"))
    return buf.getvalue()


# ═══════════════════════════════════════════════
# AI Analysis (Ollama)
# ═══════════════════════════════════════════════
def _best_model() -> str | None:
    try:
        out   = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=8)
        lines = [ln for ln in out.stdout.strip().splitlines()[1:] if ln.strip()]
        names = [ln.split()[0] for ln in lines if ln.split()]
        for pref in ["llama3", "llama3.1", "llama3.2", "mistral", "gemma", "phi", "qwen"]:
            for n in names:
                if pref in n.lower():
                    return n
        return names[0] if names else None
    except Exception:
        return None


def ai_analyze(query: str, query_type: str, osint_data: list, hibp_breaches: list = None) -> str:
    model = _best_model()
    if not model:
        return "AI analysis unavailable – run: ollama pull llama3"

    modules = osint_data if isinstance(osint_data, list) else []
    found   = [m for m in modules if m.get("status") == "found"]
    breaches = hibp_breaches or []

    # ── OSINT summary ──
    osint_lines = []
    for m in found:
        name = m.get("module", "?").capitalize()
        sf   = (m.get("spec_format") or [{}])[0]
        dets = []
        for k, v in sf.items():
            if k == "platform_variables":
                for pv in (v or []):
                    if pv.get("value") not in (None, False):
                        dets.append(f"{pv.get('proper_key', k)}: {pv['value']}")
            elif isinstance(v, dict) and "value" in v and v["value"] not in (None, False):
                dets.append(f"{v.get('proper_key', k)}: {v['value']}")
        osint_lines.append(f"  • {name}: " + (", ".join(dets) if dets else "registered"))

    # ── HIBP summary ──
    hibp_lines = []
    for b in breaches:
        hibp_lines.append(
            f"  • {b.get('Name')} ({b.get('BreachDate','?')}) "
            f"– {b.get('PwnCount',0):,} records – {', '.join(b.get('DataClasses',[])[:4])}"
        )

    prompt = f"""You are an expert OSINT analyst. Write a professional investigation report.

TARGET : {query}
TYPE   : {query_type}

=== OSINT Industries ({len(found)}/{len(modules)} platforms found) ===
{chr(10).join(osint_lines) or "  No platforms found."}

=== Have I Been Pwned ({len(breaches)} breaches) ===
{chr(10).join(hibp_lines) or "  No breaches found / HIBP not queried."}

Write a structured report:
1. Executive Summary
2. Digital Footprint (platforms, accounts)
3. Breach & Leak Exposure (details from HIBP)
4. Phone / Personal Details discovered
5. Risk Assessment: LOW / MEDIUM / HIGH (justify)
6. Recommended Actions

Be factual, concise, professional."""

    try:
        out = subprocess.run(
            ["ollama", "run", model], input=prompt,
            capture_output=True, text=True, timeout=180,
        )
        return out.stdout.strip() or "Model returned no output."
    except subprocess.TimeoutExpired:
        return "AI timed out."
    except FileNotFoundError:
        return "Ollama not installed."
    except Exception as e:
        return f"AI error: {e}"


# ═══════════════════════════════════════════════
# Report persistence
# ═══════════════════════════════════════════════
def save_report(query, query_type, osint_data, hibp_data, ai_text, elapsed) -> str:
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    qhash    = hashlib.md5(query.encode()).hexdigest()[:8]
    filename = f"osint_{query_type}_{qhash}_{ts}.json"
    report   = {
        "metadata": {
            "tool": "OSINT Industries Web Platform", "version": "2.0",
            "timestamp": datetime.now().isoformat(),
            "query": query, "type": query_type, "elapsed_s": elapsed,
        },
        "osint_data":  osint_data,
        "hibp_data":   hibp_data,
        "ai_analysis": ai_text,
    }
    path = REPORTS_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    log.info("Report saved: %s", filename)
    return filename


def _report_meta(p: Path) -> dict | None:
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        m = d.get("metadata", {})
        return {
            "filename":  p.name,
            "query":     m.get("query", "?"),
            "type":      m.get("type", "?"),
            "timestamp": m.get("timestamp", "?"),
            "elapsed_s": m.get("elapsed_s", 0),
        }
    except Exception:
        return None


# ═══════════════════════════════════════════════
# Flask Routes
# ═══════════════════════════════════════════════

@app.route("/")
def index():
    cfg = load_config()
    return render_template("index.html",
                           has_key=bool(cfg.get("api_key")),
                           has_hibp=bool(cfg.get("hibp_key")),
                           model=_best_model() or "none")


# ── Config ──────────────────────────────────────
@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        api_key  = body.get("api_key", "").strip()
        base_url = body.get("base_url", "https://api.osint.industries/v2/request").strip()
        auth_hdr = body.get("auth_header", "api-key").strip()
        hibp_key = body.get("hibp_key", "").strip()

        if not api_key:
            return jsonify({"success": False, "error": "OSINT API key required."}), 400
        if not base_url.startswith("http"):
            return jsonify({"success": False, "error": "Invalid endpoint URL."}), 400

        save_config(api_key=api_key, base_url=base_url,
                    auth_header=auth_hdr, hibp_key=hibp_key)
        return jsonify({"success": True, "message": "Configuration saved."})

    cfg = load_config()
    key      = cfg.get("api_key", "")
    hibp_key = cfg.get("hibp_key", "")
    return jsonify({
        "has_key":      bool(key),
        "key_preview":  ("●" * 16 + key[-4:])      if len(key) >= 4      else "●" * len(key),
        "has_hibp":     bool(hibp_key),
        "hibp_preview": ("●" * 12 + hibp_key[-4:]) if len(hibp_key) >= 4 else "●" * len(hibp_key),
        "base_url":     cfg.get("base_url", ""),
        "auth_header":  cfg.get("auth_header", "api-key"),
        "model":        _best_model() or "none",
    })


# ── OSINT Search ────────────────────────────────
@app.route("/api/search", methods=["POST"])
def api_search():
    cfg = load_config()
    if not cfg.get("api_key"):
        return jsonify({"success": False,
                        "error": "OSINT API key not configured."}), 400

    body       = request.get_json(silent=True) or {}
    query      = body.get("query", "").strip()
    query_type = body.get("type", "email").strip().lower()
    use_ai     = bool(body.get("use_ai", True))

    if not query:
        return jsonify({"success": False, "error": "Query cannot be empty."}), 400

    client = OSINTClient(cfg["api_key"], cfg["base_url"], cfg.get("auth_header", "api-key"))
    result = client.search(query, query_type)

    ai_text = report_file = ""
    hibp_data = []

    if result.get("success"):
        if use_ai:
            ai_text = ai_analyze(query, query_type, result.get("data", []), [])
        report_file = save_report(
            query, query_type, result.get("data", []),
            [], ai_text, result.get("elapsed", 0)
        )

    return jsonify({
        "success":     result.get("success"),
        "data":        result.get("data", []),
        "message":     result.get("message", ""),
        "error":       result.get("error", ""),
        "ai_analysis": ai_text,
        "report_file": report_file,
        "elapsed":     result.get("elapsed", 0),
    })


# ── HIBP Check ──────────────────────────────────
@app.route("/api/hibp", methods=["POST"])
def api_hibp():
    cfg      = load_config()
    hibp_key = cfg.get("hibp_key", "")
    if not hibp_key:
        return jsonify({"success": False,
                        "error": "HIBP API key not configured. Add it in Settings."}), 400

    body  = request.get_json(silent=True) or {}
    email = body.get("email", "").strip()
    if not email or "@" not in email:
        return jsonify({"success": False, "error": "Valid email address required."}), 400

    client   = HIBPClient(hibp_key)
    breaches = client.breaches(email)
    pastes   = client.pastes(email)

    log.info("HIBP check for %s: %d breaches", email,
             len(breaches.get("data", [])))

    return jsonify({
        "success":       True,
        "breaches":      breaches.get("data", []),
        "breaches_error": breaches.get("error", ""),
        "pastes":        pastes.get("data", []),
        "pastes_error":  pastes.get("error", ""),
    })


# ── Maltego .mtgx Export ────────────────────────
@app.route("/api/export/maltego", methods=["POST"])
def api_export_maltego():
    body          = request.get_json(silent=True) or {}
    query         = body.get("query", "").strip()
    query_type    = body.get("type", "email")
    osint_modules = body.get("osint_data", [])
    hibp_breaches = body.get("hibp_breaches", [])

    if not query:
        return jsonify({"success": False, "error": "Query required."}), 400

    mtgx_bytes = to_maltego_mtgx(query, query_type, osint_modules, hibp_breaches)
    safe_q     = "".join(c for c in query if c.isalnum() or c in "._-")[:30]
    log.info("Maltego export: query=%s modules=%d breaches=%d",
             query, len(osint_modules), len(hibp_breaches))
    return Response(
        mtgx_bytes,
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="maltego_{safe_q}.mtgx"'},
    )


# ── Lampyre Import ──────────────────────────────
@app.route("/api/lampyre/import", methods=["POST"])
def api_lampyre_import():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded."}), 400

    f   = request.files["file"]
    ext = Path(f.filename or "").suffix.lower()
    if ext not in (".csv", ".json"):
        return jsonify({"success": False,
                        "error": "Unsupported format. Use CSV or JSON from Lampyre."}), 400

    content = f.read().decode("utf-8", errors="replace")
    rows    = parse_lampyre(content, ext)
    log.info("Lampyre import: %d rows from %s", len(rows), f.filename)
    return jsonify({"success": True, "rows": rows, "count": len(rows)})


# ── Reports ─────────────────────────────────────
@app.route("/api/reports")
def list_reports():
    files   = sorted(REPORTS_DIR.glob("*.json"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    reports = [m for p in files[:100] if (m := _report_meta(p))]
    return jsonify(reports)


@app.route("/api/reports/<path:filename>")
def download_report(filename):
    safe = Path(filename).name
    if not safe.endswith(".json") or ".." in safe:
        abort(400)
    fp = REPORTS_DIR / safe
    if not fp.exists():
        abort(404)
    return send_file(fp, as_attachment=True, download_name=safe)


# ── Ollama ──────────────────────────────────────
@app.route("/api/ollama")
def ollama_status():
    m = _best_model()
    return jsonify({"available": m is not None, "model": m or "none"})


# ═══════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info("OSINT Platform v2 starting on http://0.0.0.0:%d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
