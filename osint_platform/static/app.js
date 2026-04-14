/* ═══════════════════════════════════════════
   OSINT Industries Platform – Frontend Logic
   ═══════════════════════════════════════════ */

"use strict";

// ─────────────────────────────────────────────
// State
// ─────────────────────────────────────────────
let _lastResult  = null;
let _lastQuery   = "";
let _lastType    = "";
let _reportFile  = "";
let _modalReport = null;

// ─────────────────────────────────────────────
// DOM shortcuts
// ─────────────────────────────────────────────
const $  = id  => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);

// ─────────────────────────────────────────────
// Toast helper
// ─────────────────────────────────────────────
let _toastTimer = null;

function toast(msg, type = "ok") {
  const el = $("toast");
  el.textContent = msg;
  el.className   = `toast ${type}`;
  el.classList.remove("hidden");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.add("hidden"), 3200);
}

// ─────────────────────────────────────────────
// AI status indicator
// ─────────────────────────────────────────────
async function refreshAIStatus() {
  try {
    const r = await fetch("/api/ollama");
    const d = await r.json();
    const dot   = $("aiDot");
    const label = $("aiLabel");
    if (d.available) {
      dot.className   = "status-dot ok";
      label.textContent = `AI: ${d.model}`;
    } else {
      dot.className   = "status-dot err";
      label.textContent = "AI: offline";
    }
  } catch {
    $("aiDot").className = "status-dot err";
    $("aiLabel").textContent = "AI: error";
  }
}

// ─────────────────────────────────────────────
// Settings panel
// ─────────────────────────────────────────────
async function loadSettings() {
  try {
    const r = await fetch("/api/config");
    const d = await r.json();
    if (d.key_preview)   $("cfgApiKey").placeholder   = d.key_preview;
    if (d.base_url)      $("cfgBaseUrl").value         = d.base_url;
    if (d.auth_header)   $("cfgAuthHeader").value      = d.auth_header;

    $("cfgInfo").innerHTML = d.has_key
      ? `<strong style="color:var(--success)">✓ API key saved</strong><br>
         Model: <code>${d.model}</code><br>
         Endpoint: <code>${d.base_url || "default"}</code>`
      : `<strong style="color:var(--warn)">No API key configured.</strong><br>
         Enter your OSINT Industries key above and click Save.`;
  } catch (e) {
    console.error("loadSettings:", e);
  }
}

$("settingsToggle").addEventListener("click", () => {
  const panel = $("settingsPanel");
  if (panel.classList.contains("hidden")) {
    panel.classList.remove("hidden");
    loadSettings();
  } else {
    panel.classList.add("hidden");
  }
});

$("settingsClose").addEventListener("click", () => {
  $("settingsPanel").classList.add("hidden");
});

$("saveConfig").addEventListener("click", async () => {
  const btn = $("saveConfig");
  const msg = $("cfgMsg");

  const api_key     = $("cfgApiKey").value.trim();
  const base_url    = $("cfgBaseUrl").value.trim() || "https://api.osint.industries/v2/request";
  const auth_header = $("cfgAuthHeader").value.trim();

  if (!api_key) {
    msg.textContent = "API key required.";
    msg.className   = "cfg-msg err";
    return;
  }

  btn.disabled = true;
  msg.textContent = "Saving…";
  msg.className   = "cfg-msg";

  try {
    const r = await fetch("/api/config", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ api_key, base_url, auth_header }),
    });
    const d = await r.json();
    if (d.success) {
      msg.textContent = "✓ Saved";
      msg.className   = "cfg-msg ok";
      toast("Configuration saved.", "ok");
      loadSettings();
      refreshAIStatus();
    } else {
      msg.textContent = d.error || "Failed.";
      msg.className   = "cfg-msg err";
    }
  } catch (e) {
    msg.textContent = "Network error.";
    msg.className   = "cfg-msg err";
  } finally {
    btn.disabled = false;
    setTimeout(() => { msg.textContent = ""; }, 4000);
  }
});

// ─────────────────────────────────────────────
// Tab switching (results)
// ─────────────────────────────────────────────
function activateTab(tabEl) {
  const tabName = tabEl.dataset.tab;
  $$(".tabs .tab").forEach(t => t.classList.remove("active"));
  $$(".pane").forEach(p => p.classList.remove("active"));
  tabEl.classList.add("active");
  $(`pane-${tabName}`).classList.add("active");
}

$$(".tabs .tab").forEach(t => {
  t.addEventListener("click", () => activateTab(t));
});

// ─────────────────────────────────────────────
// Search
// ─────────────────────────────────────────────
$("queryInput").addEventListener("keydown", e => {
  if (e.key === "Enter") triggerSearch();
});

$("searchBtn").addEventListener("click", triggerSearch);

function triggerSearch() {
  const query = $("queryInput").value.trim();
  const type  = $("queryType").value;
  const useAI = $("useAI").checked;

  if (!query) {
    showError("Please enter a query.");
    return;
  }

  doSearch(query, type, useAI);
}

async function doSearch(query, type, useAI) {
  // UI → loading state
  $("searchBtn").disabled = true;
  $("results").classList.add("hidden");
  $("errorBanner").classList.add("hidden");
  $("spinner").classList.remove("hidden");
  $("spinnerMsg").textContent = "Querying OSINT Industries…";

  try {
    const r = await fetch("/api/search", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ query, type, use_ai: useAI }),
    });

    const d = await r.json();

    $("spinner").classList.add("hidden");

    if (!d.success) {
      showError(d.error || "Unknown error from API.");
      return;
    }

    // Store for export
    _lastResult  = d;
    _lastQuery   = query;
    _lastType    = type;
    _reportFile  = d.report_file || "";

    renderResults(d, query, type);
    refreshHistory();

  } catch (e) {
    $("spinner").classList.add("hidden");
    showError(`Request failed: ${e.message}`);
  } finally {
    $("searchBtn").disabled = false;
  }
}

function showError(msg) {
  const el = $("errorBanner");
  el.textContent = msg;
  el.classList.remove("hidden");
  $("results").classList.add("hidden");
}

// ─────────────────────────────────────────────
// Render results
// ─────────────────────────────────────────────
function renderResults(d, query, type) {
  // stat bar
  $("rQuery").textContent   = query;
  $("rType").textContent    = type;
  $("rElapsed").textContent = d.elapsed ? `${d.elapsed}s` : "–";

  const data     = d.data || {};
  const modules  = Array.isArray(data.modules) ? data.modules : [];
  const found    = modules.filter(m => m.found !== false && hasContent(m)).length;
  $("rServices").textContent = modules.length ? `${found} / ${modules.length}` : "–";

  // raw JSON
  $("rawJson").textContent = JSON.stringify(data, null, 2);

  // AI analysis
  const aiEl = $("aiOutput");
  if (d.ai_analysis && d.ai_analysis.trim()) {
    aiEl.innerHTML = "";
    aiEl.textContent = d.ai_analysis;
  } else if (!$("useAI").checked) {
    aiEl.innerHTML = `<div class="ai-placeholder">AI was disabled for this search. Enable the toggle and search again.</div>`;
  } else {
    aiEl.innerHTML = `<div class="ai-placeholder">No AI analysis available (Ollama may be offline).</div>`;
  }

  // summary + modules
  renderSummary(data);
  renderModules(modules);

  $("results").classList.remove("hidden");

  // switch to summary tab
  activateTab(document.querySelector('.tabs .tab[data-tab="summary"]'));
}

function hasContent(module) {
  if (!module) return false;
  const skip = ["name", "found", "error"];
  return Object.keys(module).some(k => !skip.includes(k) && module[k] !== null && module[k] !== "");
}

function renderSummary(data) {
  const grid = $("summaryGrid");
  grid.innerHTML = "";

  // Profile-level fields
  const topFields = {
    "Email":    data.query || data.email || "",
    "Name":     data.name  || extractName(data),
    "Country":  data.country || extractCountry(data),
    "Phone":    data.phone  || "",
    "Breaches": countBreaches(data),
    "Platforms": countPlatforms(data),
  };

  for (const [label, value] of Object.entries(topFields)) {
    if (!value && value !== 0) continue;
    const card = document.createElement("div");
    card.className = "summary-card";
    card.innerHTML = `<div class="sc-platform">${escHtml(label)}</div>
                      <div class="sc-value">${escHtml(String(value))}</div>`;
    grid.appendChild(card);
  }

  // Per-module cards (one per found service)
  const modules = Array.isArray(data.modules) ? data.modules : [];
  for (const mod of modules) {
    if (!hasContent(mod) || mod.found === false) continue;
    const card = document.createElement("div");
    card.className = "summary-card";
    const name = mod.name || "Unknown";
    const detail = extractModuleDetail(mod);
    card.innerHTML = `<div class="sc-platform">${escHtml(name)}</div>
                      <div class="sc-value">${escHtml(detail.value)}</div>
                      ${detail.label ? `<div class="sc-label">${escHtml(detail.label)}</div>` : ""}`;
    grid.appendChild(card);
  }

  if (grid.childElementCount === 0) {
    grid.innerHTML = `<p style="color:var(--text-muted);padding:.5rem">No structured data to display. Check the Raw JSON tab.</p>`;
  }
}

function extractName(data) {
  if (!data) return "";
  if (data.full_name)  return data.full_name;
  if (data.first_name) return `${data.first_name || ""} ${data.last_name || ""}`.trim();
  const mods = Array.isArray(data.modules) ? data.modules : [];
  for (const m of mods) {
    if (m.name && m.full_name) return m.full_name;
    if (m.display_name)        return m.display_name;
  }
  return "";
}

function extractCountry(data) {
  if (!data) return "";
  if (data.country) return data.country;
  const mods = Array.isArray(data.modules) ? data.modules : [];
  for (const m of mods) if (m.country) return m.country;
  return "";
}

function countBreaches(data) {
  if (!data) return 0;
  if (typeof data.breach_count === "number") return data.breach_count;
  if (Array.isArray(data.breaches)) return data.breaches.length;
  const mods = Array.isArray(data.modules) ? data.modules : [];
  const b = mods.filter(m => (m.name || "").toLowerCase().includes("breach") || (m.name || "").toLowerCase().includes("hibp") || (m.name || "").toLowerCase().includes("leak"));
  return b.filter(hasContent).length || "";
}

function countPlatforms(data) {
  if (!data) return 0;
  const mods = Array.isArray(data.modules) ? data.modules : [];
  return mods.filter(hasContent).length || "";
}

function extractModuleDetail(mod) {
  const skip = new Set(["name", "found", "error", "module", "id"]);
  // Prefer human-readable fields
  const prefer = ["username", "email", "display_name", "full_name", "url", "profile_url", "bio", "location", "city"];
  for (const k of prefer) {
    if (mod[k] && typeof mod[k] === "string") return { value: mod[k], label: k };
  }
  // Fall back to first non-skip string field
  for (const [k, v] of Object.entries(mod)) {
    if (skip.has(k)) continue;
    if (typeof v === "string" && v.length > 0 && v.length < 120) return { value: v, label: k };
    if (typeof v === "number") return { value: String(v), label: k };
  }
  return { value: "Found", label: "" };
}

function renderModules(modules) {
  const list = $("modulesList");
  list.innerHTML = "";

  if (!modules.length) {
    list.innerHTML = `<p style="color:var(--text-muted);padding:.5rem">No module data returned.</p>`;
    return;
  }

  // Sort: found first
  const sorted = [...modules].sort((a, b) => {
    const aHas = hasContent(a) ? 0 : 1;
    const bHas = hasContent(b) ? 0 : 1;
    return aHas - bHas;
  });

  for (const mod of sorted) {
    const name   = mod.name || "Unknown";
    const found  = hasContent(mod);
    const item   = document.createElement("div");
    item.className = "module-item";

    const header = document.createElement("div");
    header.className = "module-header";
    header.innerHTML = `
      <span class="module-name">${escHtml(name)}</span>
      <span class="module-indicator ${found ? "found" : "empty"}">${found ? "FOUND" : "NOT FOUND"}</span>`;

    const body = document.createElement("div");
    body.className = "module-body";

    // Pretty print only the non-meta fields
    const display = {};
    for (const [k, v] of Object.entries(mod)) {
      if (!["name", "found"].includes(k)) display[k] = v;
    }
    body.innerHTML = `<pre>${escHtml(JSON.stringify(display, null, 2))}</pre>`;

    // Collapsible
    header.addEventListener("click", () => {
      const visible = body.style.display !== "none" && body.style.display !== "";
      body.style.display = visible ? "none" : "block";
    });
    // Start collapsed if not found
    if (!found) body.style.display = "none";

    item.appendChild(header);
    item.appendChild(body);
    list.appendChild(item);
  }
}

// ─────────────────────────────────────────────
// Export
// ─────────────────────────────────────────────
$("exportJson").addEventListener("click", () => {
  if (!_lastResult) return;
  downloadJson(_lastResult.data || {}, `osint_${_lastType}_${_lastQuery.substring(0, 20)}.json`);
});

$("exportReport").addEventListener("click", () => {
  if (!_reportFile) { toast("No report file available.", "err"); return; }
  window.location.href = `/api/reports/${encodeURIComponent(_reportFile)}`;
});

function downloadJson(obj, filename) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ─────────────────────────────────────────────
// History / Reports sidebar
// ─────────────────────────────────────────────
async function refreshHistory() {
  try {
    const r    = await fetch("/api/reports");
    const list = await r.json();
    const ul   = $("historyList");
    ul.innerHTML = "";

    if (!list.length) {
      ul.innerHTML = `<li class="history-empty">No reports yet</li>`;
      return;
    }

    for (const item of list) {
      const li = document.createElement("li");
      li.className = "history-item";
      const ts = item.timestamp ? item.timestamp.replace("T", " ").substring(0, 16) : "";
      li.innerHTML = `
        <div class="h-query">
          <span class="h-badge">${escHtml(item.type)}</span>${escHtml(item.query)}
        </div>
        <div class="h-meta">${escHtml(ts)}</div>`;
      li.addEventListener("click", () => openReport(item.filename));
      ul.appendChild(li);
    }
  } catch (e) {
    console.error("refreshHistory:", e);
  }
}

$("refreshHistory").addEventListener("click", refreshHistory);

// ─────────────────────────────────────────────
// Report modal
// ─────────────────────────────────────────────
async function openReport(filename) {
  try {
    const r = await fetch(`/api/reports/${encodeURIComponent(filename)}`);
    const d = await r.json();
    _modalReport = d;

    $("modalTitle").textContent = `Report – ${d.metadata?.query || filename}`;
    $("modalRaw").textContent   = JSON.stringify(d.raw_data || {}, null, 2);

    const aiEl = $("modalAI");
    if (d.ai_analysis) {
      aiEl.textContent = d.ai_analysis;
      aiEl.classList.remove("hidden");
    } else {
      aiEl.classList.add("hidden");
    }

    // Reset tabs
    $$(".modal-tabs .tab").forEach(t => t.classList.remove("active"));
    document.querySelector('.modal-tabs .tab[data-modal-tab="raw"]').classList.add("active");
    $("modalRaw").classList.remove("hidden");
    aiEl.classList.add("hidden");

    $("reportModal").classList.remove("hidden");
    $("modalDownload").dataset.filename = filename;
  } catch (e) {
    toast(`Failed to load report: ${e.message}`, "err");
  }
}

$("modalClose").addEventListener("click", () => {
  $("reportModal").classList.add("hidden");
});

$("reportModal").addEventListener("click", e => {
  if (e.target === $("reportModal")) $("reportModal").classList.add("hidden");
});

$$(".modal-tabs .tab").forEach(t => {
  t.addEventListener("click", () => {
    $$(".modal-tabs .tab").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    const tabName = t.dataset.modalTab;
    if (tabName === "raw") {
      $("modalRaw").classList.remove("hidden");
      $("modalAI").classList.add("hidden");
    } else {
      $("modalRaw").classList.add("hidden");
      $("modalAI").classList.remove("hidden");
    }
  });
});

$("modalDownload").addEventListener("click", () => {
  const fn = $("modalDownload").dataset.filename;
  if (fn) window.location.href = `/api/reports/${encodeURIComponent(fn)}`;
});

// ─────────────────────────────────────────────
// Utility
// ─────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ─────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────
(function init() {
  refreshAIStatus();
  refreshHistory();

  // Show settings banner if no API key
  fetch("/api/config")
    .then(r => r.json())
    .then(d => {
      if (!d.has_key) {
        $("settingsPanel").classList.remove("hidden");
      }
    })
    .catch(() => {});
})();
