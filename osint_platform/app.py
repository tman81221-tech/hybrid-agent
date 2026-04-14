#!/usr/bin/env python3
"""
OSINT Industries Web Platform
Flask backend with proper API client, retry logic, AI analysis, and report generation.
"""

import os
import json
import time
import logging
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, render_template, request, jsonify, send_file, abort

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


# ─────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────
def load_config() -> dict:
    """Return merged config: file → env overrides."""
    cfg = {
        "api_key":  "",
        "base_url": "https://api.osint.industries/v2/request",
        "auth_header": "api-key",   # api-key | Bearer | X-API-Key
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg.update(json.load(f))
        except json.JSONDecodeError:
            log.warning("Config file corrupt – using defaults")
    # Env vars override file
    if os.environ.get("OSINT_API_KEY"):
        cfg["api_key"] = os.environ["OSINT_API_KEY"]
    if os.environ.get("OSINT_BASE_URL"):
        cfg["base_url"] = os.environ["OSINT_BASE_URL"]
    return cfg


def save_config(api_key: str, base_url: str, auth_header: str) -> None:
    data = load_config()
    data["api_key"]     = api_key.strip()
    data["base_url"]    = base_url.strip().rstrip("/")
    data["auth_header"] = auth_header.strip()
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)
    CONFIG_FILE.chmod(0o600)
    log.info("Config saved")


# ─────────────────────────────────────────────
# OSINT Industries API client
# ─────────────────────────────────────────────
class OSINTClient:
    """
    Handles all communication with the OSINT Industries API.
    Supports all three common auth header styles.
    Implements exponential-backoff retry on 429/5xx.
    """

    QUERY_TYPES = {"email", "phone", "username"}
    MAX_RETRIES = 4
    RETRY_CODES = {429, 500, 502, 503, 504}

    def __init__(self, api_key: str, base_url: str, auth_header: str = "api-key"):
        self.api_key     = api_key
        self.base_url    = base_url
        self.auth_header = auth_header

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept":       "application/json",
            "User-Agent":   "OSINT-Platform/1.0",
        })
        self._apply_auth()

    def _apply_auth(self):
        """Set the authorization header based on selected style."""
        style = self.auth_header.lower()
        if style == "bearer":
            self.session.headers["Authorization"] = f"Bearer {self.api_key}"
        elif style == "x-api-key":
            self.session.headers["X-API-Key"] = self.api_key
        else:  # default: api-key (OSINT Industries standard header name)
            self.session.headers["api-key"] = self.api_key

    def search(self, query: str, query_type: str, timeout: int = 60) -> dict:
        """
        Perform an OSINT lookup with retry logic.

        Returns a dict:
          success   bool
          data      dict | None
          error     str  | None
          status    int
          elapsed   float  (seconds)
        """
        if query_type not in self.QUERY_TYPES:
            return {"success": False,
                    "error": f"Invalid type '{query_type}'. Valid: {sorted(self.QUERY_TYPES)}",
                    "status": 400}

        payload = {"query": query.strip(), "type": query_type}
        t_start = time.monotonic()

        for attempt in range(self.MAX_RETRIES):
            wait = 2 ** attempt          # 1, 2, 4, 8
            try:
                resp = self.session.post(self.base_url, json=payload, timeout=timeout)
                elapsed = round(time.monotonic() - t_start, 2)

                # ── Success ──────────────────────────────
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except ValueError:
                        data = {"raw": resp.text}
                    log.info("Search OK  type=%s  status=200  t=%.2fs", query_type, elapsed)
                    return {"success": True, "data": data, "status": 200, "elapsed": elapsed}

                # ── No results ───────────────────────────
                if resp.status_code == 404:
                    log.info("No results found for query.")
                    return {"success": True, "data": {}, "status": 404,
                            "message": "No results found for this query.",
                            "elapsed": elapsed}

                # ── Auth error (don't retry) ──────────────
                if resp.status_code in (401, 403):
                    msg = f"Authentication failed ({resp.status_code}). Check your API key."
                    log.error(msg)
                    return {"success": False, "error": msg, "status": resp.status_code}

                # ── Rate limit / server error (retry) ────
                if resp.status_code in self.RETRY_CODES:
                    if attempt < self.MAX_RETRIES - 1:
                        log.warning("HTTP %d – retrying in %ds (attempt %d/%d)",
                                    resp.status_code, wait, attempt + 1, self.MAX_RETRIES)
                        time.sleep(wait)
                        continue
                    return {"success": False,
                            "error": f"API returned {resp.status_code} after {self.MAX_RETRIES} retries.",
                            "status": resp.status_code}

                # ── Other HTTP errors ─────────────────────
                body_preview = resp.text[:300]
                log.error("HTTP %d: %s", resp.status_code, body_preview)
                return {"success": False,
                        "error": f"API error {resp.status_code}: {body_preview}",
                        "status": resp.status_code}

            except requests.exceptions.Timeout:
                if attempt < self.MAX_RETRIES - 1:
                    log.warning("Request timed out – retrying in %ds", wait)
                    time.sleep(wait)
                    continue
                return {"success": False, "error": "Request timed out after all retries.", "status": 408}

            except requests.exceptions.ConnectionError as exc:
                if attempt < self.MAX_RETRIES - 1:
                    log.warning("Connection error – retrying in %ds: %s", wait, exc)
                    time.sleep(wait)
                    continue
                return {"success": False, "error": f"Connection failed: {exc}", "status": 503}

            except Exception as exc:
                log.exception("Unexpected error in search")
                return {"success": False, "error": str(exc), "status": 500}

        return {"success": False, "error": "Max retries exceeded.", "status": 503}


# ─────────────────────────────────────────────
# AI Analysis (Ollama)
# ─────────────────────────────────────────────
def _best_model() -> str | None:
    """Return the best locally available Ollama model name."""
    try:
        out = subprocess.run(["ollama", "list"],
                             capture_output=True, text=True, timeout=8)
        lines = [ln for ln in out.stdout.strip().splitlines()[1:] if ln.strip()]
        names = [ln.split()[0] for ln in lines if ln.split()]
        priority = ["llama3", "llama3.1", "llama3.2", "mistral", "gemma", "phi", "qwen"]
        for pref in priority:
            for n in names:
                if pref in n.lower():
                    return n
        return names[0] if names else None
    except Exception:
        return None


def ai_analyze(query: str, query_type: str, data: dict) -> str:
    """Generate a structured OSINT analysis report via a local LLM."""
    model = _best_model()
    if not model:
        return "AI analysis unavailable – no Ollama model found. Run: ollama pull llama3"

    # Limit payload to avoid context overflow
    compact = json.dumps(data, ensure_ascii=False, default=str)[:4500]

    prompt = f"""You are an expert OSINT analyst. Analyze the following data and write a clear, structured report.

Target  : {query}
Type    : {query_type}

=== RAW DATA ===
{compact}
=== END DATA ===

Your report must include:
1. **Executive Summary** – one paragraph
2. **Digital Footprint** – platforms, accounts, and services detected
3. **Breach & Leak Exposure** – any credential or data leaks
4. **Key Personal Details** – names, locations, dates found (if any)
5. **Risk Assessment** – LOW / MEDIUM / HIGH, with reasons
6. **Recommended Actions** – for a security / investigative context

Be concise, factual, and professional."""

    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=180,
        )
        output = result.stdout.strip()
        return output if output else "Model returned no output."
    except subprocess.TimeoutExpired:
        return "AI analysis timed out (>180 s)."
    except FileNotFoundError:
        return "Ollama not installed. Install from https://ollama.com"
    except Exception as exc:
        return f"AI analysis error: {exc}"


# ─────────────────────────────────────────────
# Report persistence
# ─────────────────────────────────────────────
def save_report(query: str, query_type: str,
                raw_data: dict, ai_text: str,
                elapsed: float) -> str:
    """Persist result to a JSON report; returns filename."""
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    qhash    = hashlib.md5(query.encode()).hexdigest()[:8]
    filename = f"osint_{query_type}_{qhash}_{ts}.json"
    filepath = REPORTS_DIR / filename

    report = {
        "metadata": {
            "tool":      "OSINT Industries Web Platform",
            "version":   "1.0",
            "timestamp": datetime.now().isoformat(),
            "query":     query,
            "type":      query_type,
            "elapsed_s": elapsed,
        },
        "raw_data":    raw_data,
        "ai_analysis": ai_text,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    log.info("Report saved: %s", filename)
    return filename


def _report_meta(filepath: Path) -> dict | None:
    """Read only metadata from a saved report."""
    try:
        with open(filepath, encoding="utf-8") as f:
            d = json.load(f)
        m = d.get("metadata", {})
        return {
            "filename":  filepath.name,
            "query":     m.get("query", "?"),
            "type":      m.get("type", "?"),
            "timestamp": m.get("timestamp", "?"),
            "elapsed_s": m.get("elapsed_s", 0),
        }
    except Exception:
        return None


# ─────────────────────────────────────────────
# Flask routes
# ─────────────────────────────────────────────
@app.route("/")
def index():
    cfg = load_config()
    return render_template(
        "index.html",
        has_key=bool(cfg.get("api_key")),
        base_url=cfg.get("base_url", ""),
        auth_header=cfg.get("auth_header", "api-key"),
        model=_best_model() or "none",
    )


# ── Config ──────────────────────────────────
@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        api_key     = body.get("api_key", "").strip()
        base_url    = body.get("base_url", "https://api.osint.industries/v2/request").strip()
        auth_header = body.get("auth_header", "api-key").strip()
        if not api_key:
            return jsonify({"success": False, "error": "API key is required."}), 400
        if not base_url.startswith("http"):
            return jsonify({"success": False, "error": "Base URL must start with http(s)://"}), 400
        save_config(api_key, base_url, auth_header)
        return jsonify({"success": True, "message": "Configuration saved."})

    cfg = load_config()
    key = cfg.get("api_key", "")
    return jsonify({
        "has_key":      bool(key),
        "key_preview":  ("●" * 16 + key[-4:]) if len(key) >= 4 else ("●" * len(key)),
        "base_url":     cfg.get("base_url", ""),
        "auth_header":  cfg.get("auth_header", "api-key"),
        "model":        _best_model() or "none",
    })


# ── Search ──────────────────────────────────
@app.route("/api/search", methods=["POST"])
def api_search():
    cfg = load_config()
    if not cfg.get("api_key"):
        return jsonify({"success": False,
                        "error": "API key not configured. Open Settings and save your key."}), 400

    body       = request.get_json(silent=True) or {}
    query      = body.get("query", "").strip()
    query_type = body.get("type", "email").strip().lower()
    use_ai     = bool(body.get("use_ai", True))

    if not query:
        return jsonify({"success": False, "error": "Query cannot be empty."}), 400

    client = OSINTClient(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        auth_header=cfg.get("auth_header", "api-key"),
    )

    result = client.search(query, query_type)

    ai_text     = ""
    report_file = ""

    if result.get("success") and result.get("data"):
        if use_ai:
            ai_text = ai_analyze(query, query_type, result["data"])
        report_file = save_report(
            query, query_type,
            result["data"], ai_text,
            result.get("elapsed", 0),
        )

    return jsonify({
        "success":     result.get("success"),
        "data":        result.get("data", {}),
        "message":     result.get("message", ""),
        "error":       result.get("error", ""),
        "ai_analysis": ai_text,
        "report_file": report_file,
        "elapsed":     result.get("elapsed", 0),
        "status":      result.get("status", 0),
    })


# ── Reports ─────────────────────────────────
@app.route("/api/reports")
def list_reports():
    files   = sorted(REPORTS_DIR.glob("*.json"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    reports = [m for p in files[:100] if (m := _report_meta(p))]
    return jsonify(reports)


@app.route("/api/reports/<path:filename>")
def download_report(filename):
    # Sanitize: strip any directory traversal
    safe = Path(filename).name
    if not safe.endswith(".json") or ".." in safe:
        abort(400)
    filepath = REPORTS_DIR / safe
    if not filepath.exists():
        abort(404)
    return send_file(filepath, as_attachment=True, download_name=safe)


# ── Ollama status ────────────────────────────
@app.route("/api/ollama")
def ollama_status():
    model = _best_model()
    return jsonify({"available": model is not None, "model": model or "none"})


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info("Starting OSINT Industries Web Platform on http://0.0.0.0:%d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
