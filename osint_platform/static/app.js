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
  $("rQuery").textContent   = query;
  $("rType").textContent    = type;
  $("rElapsed").textContent = d.elapsed ? `${d.elapsed}s` : "–";

  // OSINT Industries returns raw_data as a direct array of module objects
  const modules = Array.isArray(d.data) ? d.data : [];
  const found   = modules.filter(m => m.status === "found").length;
  $("rServices").textContent = modules.length ? `${found} / ${modules.length}` : "–";

  $("rawJson").textContent = JSON.stringify(d.data, null, 2);

  const aiEl = $("aiOutput");
  if (d.ai_analysis && d.ai_analysis.trim()) {
    aiEl.textContent = d.ai_analysis;
  } else if (!$("useAI").checked) {
    aiEl.innerHTML = `<div class="ai-placeholder">AI was disabled for this search.</div>`;
  } else {
    aiEl.innerHTML = `<div class="ai-placeholder">No AI analysis available (Ollama may be offline).</div>`;
  }

  renderSummary(modules, query);
  renderModules(modules);

  $("results").classList.remove("hidden");
  activateTab(document.querySelector('.tabs .tab[data-tab="summary"]'));
}

// ── Helpers for OSINT Industries module structure ──────────────

function capitalize(str) {
  if (!str) return "";
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * Extract key/value pairs from a module's spec_format array.
 * spec_format: [ { registered: {proper_key, value}, phone_hint: {...}, platform_variables: [...] } ]
 */
function extractSpecDetails(mod) {
  const sf = (mod.spec_format && mod.spec_format[0]) ? mod.spec_format[0] : {};
  const results = [];
  for (const [key, val] of Object.entries(sf)) {
    if (key === "platform_variables") {
      for (const pv of (Array.isArray(val) ? val : [])) {
        if (pv.value !== null && pv.value !== undefined && pv.value !== false)
          results.push({ key: pv.proper_key || pv.key, value: pv.value });
      }
    } else if (val && typeof val === "object" && "value" in val) {
      if (val.value !== null && val.value !== undefined)
        results.push({ key: val.proper_key || key, value: val.value });
    }
  }
  return results;
}

function renderSummary(modules, query) {
  const grid = $("summaryGrid");
  grid.innerHTML = "";

  const foundMods = modules.filter(m => m.status === "found");

  // ── Top stat cards ──
  const topStats = [
    { label: "Query",          value: query },
    { label: "Platforms Found", value: String(foundMods.length) },
    { label: "Total Checked",  value: String(modules.length) },
  ];

  // Collect unique phone hints across all found modules
  const phones = [];
  for (const mod of foundMods) {
    const sf = (mod.spec_format && mod.spec_format[0]) || {};
    if (sf.phone_hint && sf.phone_hint.value)
      phones.push(sf.phone_hint.value);
  }
  if (phones.length)
    topStats.push({ label: "Phone Hints", value: [...new Set(phones)].join(" / ") });

  for (const s of topStats) {
    const card = document.createElement("div");
    card.className = "summary-card";
    card.innerHTML = `<div class="sc-platform">${escHtml(s.label)}</div>
                      <div class="sc-value">${escHtml(s.value)}</div>`;
    grid.appendChild(card);
  }

  // ── One card per found platform ──
  for (const mod of foundMods) {
    const card  = document.createElement("div");
    card.className = "summary-card";
    const name  = capitalize(mod.module || "Unknown");
    const cat   = (mod.category && mod.category.name) ? mod.category.name : "";
    const details = extractSpecDetails(mod);
    // Show the most interesting detail (skip plain "Registered: true")
    const detail  = details.find(d => d.key !== "Registered" && d.value !== true) || details[0];

    card.innerHTML = `
      <div class="sc-platform">${escHtml(name)}</div>
      ${detail
        ? `<div class="sc-value">${escHtml(String(detail.value))}</div>
           <div class="sc-label">${escHtml(detail.key)}</div>`
        : `<div class="sc-value" style="color:var(--success)">✓ Registered</div>`}
      ${cat ? `<div class="sc-label" style="margin-top:5px;opacity:.55">${escHtml(cat)}</div>` : ""}`;
    grid.appendChild(card);
  }

  if (foundMods.length === 0) {
    grid.innerHTML = `<p style="color:var(--text-muted);padding:.5rem 0">
      No platforms found for this query. Check the Modules tab for full details.</p>`;
  }
}

function renderModules(modules) {
  const list = $("modulesList");
  list.innerHTML = "";

  if (!modules.length) {
    list.innerHTML = `<p style="color:var(--text-muted);padding:.5rem">No module data returned.</p>`;
    return;
  }

  // Found first, then alphabetical within each group
  const sorted = [...modules].sort((a, b) => {
    const af = a.status === "found" ? 0 : 1;
    const bf = b.status === "found" ? 0 : 1;
    if (af !== bf) return af - bf;
    return (a.module || "").localeCompare(b.module || "");
  });

  for (const mod of sorted) {
    const name  = capitalize(mod.module || "Unknown");
    const found = mod.status === "found";
    const cat   = (mod.category && mod.category.name) ? ` · ${mod.category.name}` : "";

    const item  = document.createElement("div");
    item.className = "module-item";

    const header = document.createElement("div");
    header.className = "module-header";
    header.innerHTML = `
      <div>
        <span class="module-name">${escHtml(name)}</span>
        <span style="font-size:.73rem;color:var(--text-muted);margin-left:.45rem">${escHtml(cat)}</span>
      </div>
      <span class="module-indicator ${found ? "found" : "empty"}">${found ? "FOUND" : "NOT FOUND"}</span>`;

    const body = document.createElement("div");
    body.className = "module-body";

    if (found) {
      const details = extractSpecDetails(mod);
      if (details.length) {
        const rows = details.map(d =>
          `<div style="display:flex;justify-content:space-between;align-items:center;
                       padding:5px 0;border-bottom:1px solid var(--border)">
             <span style="color:var(--text-dim);font-size:.79rem">${escHtml(d.key)}</span>
             <span style="color:var(--text);font-size:.82rem;font-weight:600;
                          max-width:60%;word-break:break-all;text-align:right">
               ${escHtml(String(d.value))}
             </span>
           </div>`
        ).join("");
        body.innerHTML = `<div style="padding:.15rem 0">${rows}</div>`;
      } else {
        body.innerHTML = `<pre>${escHtml(JSON.stringify(mod.spec_format, null, 2))}</pre>`;
      }
    } else {
      body.style.display = "none";
    }

    header.addEventListener("click", () => {
      body.style.display = (body.style.display === "none") ? "block" : "none";
    });

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
