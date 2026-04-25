"use strict";

// ── State ──────────────────────────────────────────────────────
let _lastResult   = null;
let _lastQuery    = "";
let _lastType     = "";
let _reportFile   = "";
let _hibpBreaches = [];

const $  = id  => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);

// ── Toast ──────────────────────────────────────────────────────
let _tt = null;
function toast(msg, type = "ok") {
  const el = $("toast");
  el.textContent = msg;
  el.className = `toast ${type}`;
  el.classList.remove("hidden");
  clearTimeout(_tt);
  _tt = setTimeout(() => el.classList.add("hidden"), 3500);
}

// ── AI status ──────────────────────────────────────────────────
async function refreshAIStatus() {
  try {
    const d = await fetch("/api/ollama").then(r => r.json());
    $("aiDot").className   = d.available ? "status-dot ok" : "status-dot err";
    $("aiLabel").textContent = d.available ? `AI: ${d.model}` : "AI: offline";
  } catch {
    $("aiDot").className   = "status-dot err";
    $("aiLabel").textContent = "AI: error";
  }
}

// ── Settings ───────────────────────────────────────────────────
async function loadSettings() {
  try {
    const d = await fetch("/api/config").then(r => r.json());
    if (d.key_preview)   $("cfgApiKey").placeholder  = d.key_preview;
    if (d.hibp_preview)  $("cfgHibpKey").placeholder = d.hibp_preview;
    if (d.base_url)      $("cfgBaseUrl").value        = d.base_url;
    if (d.auth_header)   $("cfgAuthHeader").value     = d.auth_header;
    $("cfgInfo").innerHTML = `
      <div style="display:flex;flex-direction:column;gap:.3rem">
        <div>OSINT key: <strong style="color:${d.has_key ? "var(--success)" : "var(--danger)"}">
          ${d.has_key ? "✓ saved" : "✗ missing"}</strong></div>
        <div>HIBP key: <strong style="color:${d.has_hibp ? "var(--success)" : "var(--warn)"}">
          ${d.has_hibp ? "✓ saved" : "not set"}</strong></div>
        <div>AI model: <code>${d.model}</code></div>
        <div style="font-size:.72rem;color:var(--text-muted)">${d.base_url}</div>
      </div>`;
  } catch (e) { console.error(e); }
}

$("settingsToggle").addEventListener("click", () => {
  const p = $("settingsPanel");
  if (p.classList.contains("hidden")) { p.classList.remove("hidden"); loadSettings(); }
  else p.classList.add("hidden");
});
$("settingsClose").addEventListener("click", () => $("settingsPanel").classList.add("hidden"));

// Auto-fill Maltego server URL with actual host
$("maltegoServerUrl").textContent = `http://${location.host}/maltego`;
$("copyMaltegoUrl").addEventListener("click", () => {
  navigator.clipboard.writeText($("maltegoServerUrl").textContent)
    .then(() => toast("Maltego URL copied!", "ok"))
    .catch(() => toast("Copy manually: " + $("maltegoServerUrl").textContent));
});

$("saveConfig").addEventListener("click", async () => {
  const btn = $("saveConfig"), msg = $("cfgMsg");
  const api_key     = $("cfgApiKey").value.trim();
  const hibp_key    = $("cfgHibpKey").value.trim();
  const base_url    = $("cfgBaseUrl").value.trim() || "https://api.osint.industries/v2/request";
  const auth_header = $("cfgAuthHeader").value.trim();
  if (!api_key) { msg.textContent = "OSINT API key required."; msg.className = "cfg-msg err"; return; }
  btn.disabled = true; msg.textContent = "Saving…"; msg.className = "cfg-msg";
  try {
    const d = await fetch("/api/config", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ api_key, hibp_key, base_url, auth_header })
    }).then(r => r.json());
    if (d.success) {
      msg.textContent = "✓ Saved"; msg.className = "cfg-msg ok";
      toast("Configuration saved."); loadSettings(); refreshAIStatus();
    } else { msg.textContent = d.error || "Failed."; msg.className = "cfg-msg err"; }
  } catch { msg.textContent = "Network error."; msg.className = "cfg-msg err"; }
  finally { btn.disabled = false; setTimeout(() => { msg.textContent = ""; }, 4000); }
});

// ── Tabs ───────────────────────────────────────────────────────
function activateTab(tabEl) {
  const name = tabEl.dataset.tab;
  $$(".tabs .tab").forEach(t => t.classList.remove("active"));
  $$(".pane").forEach(p => p.classList.remove("active"));
  tabEl.classList.add("active");
  $(`pane-${name}`).classList.add("active");
}
$$(".tabs .tab").forEach(t => t.addEventListener("click", () => activateTab(t)));

// ── Search ─────────────────────────────────────────────────────
$("queryInput").addEventListener("keydown", e => { if (e.key === "Enter") triggerSearch(); });
$("searchBtn").addEventListener("click", triggerSearch);

function triggerSearch() {
  const q = $("queryInput").value.trim();
  if (!q) { showError("Please enter a query."); return; }
  doSearch(q, $("queryType").value, $("useAI").checked);
}

async function doSearch(query, type, useAI) {
  $("searchBtn").disabled = true;
  $("results").classList.add("hidden");
  $("errorBanner").classList.add("hidden");
  $("toolBar").classList.add("hidden");
  $("spinner").classList.remove("hidden");
  $("spinnerMsg").textContent = "Querying OSINT Industries…";
  _hibpBreaches = [];

  try {
    const d = await fetch("/api/search", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ query, type, use_ai: useAI })
    }).then(r => r.json());

    $("spinner").classList.add("hidden");
    if (!d.success) { showError(d.error || "Unknown error."); return; }

    _lastResult = d; _lastQuery = query; _lastType = type; _reportFile = d.report_file || "";

    renderResults(d, query, type);
    $("toolBar").classList.remove("hidden");

    // Only show HIBP button for email
    $("hibpBtn").style.display = (type === "email") ? "" : "none";
    refreshHistory();

  } catch (e) {
    $("spinner").classList.add("hidden");
    showError(`Request failed: ${e.message}`);
  } finally { $("searchBtn").disabled = false; }
}

function showError(msg) {
  $("errorBanner").textContent = msg;
  $("errorBanner").classList.remove("hidden");
  $("results").classList.add("hidden");
}

// ── Render results ─────────────────────────────────────────────
function renderResults(d, query, type) {
  $("rQuery").textContent   = query;
  $("rType").textContent    = type;
  $("rElapsed").textContent = d.elapsed ? `${d.elapsed}s` : "–";
  $("rBreaches").textContent = "–";

  const modules = Array.isArray(d.data) ? d.data : [];
  const found   = modules.filter(m => m.status === "found").length;
  $("rServices").textContent = modules.length ? `${found} / ${modules.length}` : "–";

  $("rawJson").textContent = JSON.stringify(d.data, null, 2);

  const aiEl = $("aiOutput");
  if (d.ai_analysis && d.ai_analysis.trim()) {
    aiEl.textContent = d.ai_analysis;
  } else {
    aiEl.innerHTML = `<div class="ai-placeholder">${
      $("useAI").checked
        ? "No AI analysis (Ollama offline). Run: <code>ollama pull llama3 && ollama serve</code>"
        : "AI disabled. Enable the toggle and search again."
    }</div>`;
  }

  // Reset HIBP & Lampyre panes
  $("hibpContent").innerHTML  = `<div class="ai-placeholder">Click <strong>🔓 Check HIBP</strong> above.</div>`;
  $("lampyreContent").innerHTML = `<div class="ai-placeholder">Click <strong>📂 Import Lampyre</strong> above.</div>`;

  renderSummary(modules, query);
  renderModules(modules);

  $("results").classList.remove("hidden");
  activateTab(document.querySelector('.tabs .tab[data-tab="summary"]'));
}

// ── Helpers ────────────────────────────────────────────────────
function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ""; }

function specDetails(mod) {
  const sf = (mod.spec_format && mod.spec_format[0]) ? mod.spec_format[0] : {};
  const out = [];
  for (const [k, v] of Object.entries(sf)) {
    if (k === "platform_variables") {
      for (const pv of (Array.isArray(v) ? v : []))
        if (pv.value !== null && pv.value !== undefined && pv.value !== false)
          out.push({ key: pv.proper_key || pv.key, value: pv.value });
    } else if (v && typeof v === "object" && "value" in v && v.value !== null && v.value !== undefined)
      out.push({ key: v.proper_key || k, value: v.value });
  }
  return out;
}

function escHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
                  .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// ── Summary tab ────────────────────────────────────────────────
function renderSummary(modules, query) {
  const grid = $("summaryGrid");
  grid.innerHTML = "";
  const found = modules.filter(m => m.status === "found");

  const phones = [];
  for (const m of found) {
    const sf = (m.spec_format && m.spec_format[0]) || {};
    if (sf.phone_hint && sf.phone_hint.value) phones.push(sf.phone_hint.value);
  }

  const stats = [
    { label: "Query",           value: query },
    { label: "Platforms Found", value: String(found.length) },
    { label: "Total Checked",   value: String(modules.length) },
  ];
  if (phones.length) stats.push({ label: "Phone Hints", value: [...new Set(phones)].join(" / ") });

  for (const s of stats) {
    const c = document.createElement("div");
    c.className = "summary-card";
    c.innerHTML = `<div class="sc-platform">${escHtml(s.label)}</div>
                   <div class="sc-value">${escHtml(s.value)}</div>`;
    grid.appendChild(c);
  }

  for (const mod of found) {
    const c    = document.createElement("div");
    c.className = "summary-card";
    const name  = cap(mod.module || "Unknown");
    const cat   = (mod.category && mod.category.name) ? mod.category.name : "";
    const dets  = specDetails(mod);
    const det   = dets.find(d => d.key !== "Registered" && d.value !== true) || dets[0];
    c.innerHTML = `
      <div class="sc-platform">${escHtml(name)}</div>
      ${det
        ? `<div class="sc-value">${escHtml(String(det.value))}</div>
           <div class="sc-label">${escHtml(det.key)}</div>`
        : `<div class="sc-value" style="color:var(--success)">✓ Registered</div>`}
      ${cat ? `<div class="sc-label" style="margin-top:4px;opacity:.5">${escHtml(cat)}</div>` : ""}`;
    grid.appendChild(c);
  }

  if (!grid.children.length)
    grid.innerHTML = `<p style="color:var(--text-muted)">No platforms found.</p>`;
}

// ── Modules tab ────────────────────────────────────────────────
function renderModules(modules) {
  const list = $("modulesList");
  list.innerHTML = "";
  if (!modules.length) {
    list.innerHTML = `<p style="color:var(--text-muted)">No module data.</p>`; return;
  }
  const sorted = [...modules].sort((a, b) => {
    const d = (a.status === "found" ? 0 : 1) - (b.status === "found" ? 0 : 1);
    return d || (a.module || "").localeCompare(b.module || "");
  });
  for (const mod of sorted) {
    const found = mod.status === "found";
    const name  = cap(mod.module || "Unknown");
    const cat   = (mod.category && mod.category.name) ? ` · ${mod.category.name}` : "";
    const item  = document.createElement("div");
    item.className = "module-item";

    const hdr = document.createElement("div");
    hdr.className = "module-header";
    hdr.innerHTML = `
      <div><span class="module-name">${escHtml(name)}</span>
           <span style="font-size:.72rem;color:var(--text-muted);margin-left:.4rem">${escHtml(cat)}</span></div>
      <span class="module-indicator ${found ? "found" : "empty"}">${found ? "FOUND" : "NOT FOUND"}</span>`;

    const body = document.createElement("div");
    body.className = "module-body";

    if (found) {
      const dets = specDetails(mod);
      body.innerHTML = dets.length
        ? `<div style="padding:.15rem 0">${dets.map(d =>
            `<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border)">
               <span style="color:var(--text-dim);font-size:.79rem">${escHtml(d.key)}</span>
               <span style="color:var(--text);font-weight:600;font-size:.82rem;max-width:60%;text-align:right;word-break:break-all">
                 ${escHtml(String(d.value))}</span>
             </div>`).join("")}</div>`
        : `<pre>${escHtml(JSON.stringify(mod.spec_format, null, 2))}</pre>`;
    } else {
      body.style.display = "none";
    }

    hdr.addEventListener("click", () => {
      body.style.display = body.style.display === "none" ? "block" : "none";
    });
    item.appendChild(hdr);
    item.appendChild(body);
    list.appendChild(item);
  }
}

// ═══════════════════════════════════════════════
// HIBP Integration
// ═══════════════════════════════════════════════
$("hibpBtn").addEventListener("click", checkHIBP);

async function checkHIBP() {
  if (!_lastQuery || _lastType !== "email") {
    toast("HIBP requires an email search first.", "err"); return;
  }
  $("hibpBtn").disabled = true;
  $("hibpBtn").textContent = "🔓 Checking…";
  activateTab(document.querySelector('.tabs .tab[data-tab="hibp"]'));
  $("hibpContent").innerHTML = `<div class="spinner-wrap"><div class="spinner"></div><span>Querying HIBP…</span></div>`;

  try {
    const d = await fetch("/api/hibp", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ email: _lastQuery })
    }).then(r => r.json());

    if (!d.success) {
      $("hibpContent").innerHTML = `<div class="error-banner" style="display:block">${escHtml(d.error)}</div>`;
      return;
    }

    _hibpBreaches = d.breaches || [];
    const total   = _hibpBreaches.length + (d.pastes || []).length;
    $("rBreaches").textContent = total ? String(total) : "0";

    renderHIBP(d.breaches || [], d.pastes || []);
    toast(`HIBP: ${_hibpBreaches.length} breaches, ${(d.pastes || []).length} pastes`);
  } catch (e) {
    $("hibpContent").innerHTML = `<div class="error-banner" style="display:block">HIBP error: ${escHtml(e.message)}</div>`;
  } finally {
    $("hibpBtn").disabled = false;
    $("hibpBtn").textContent = "🔓 Check HIBP";
  }
}

function renderHIBP(breaches, pastes) {
  const el = $("hibpContent");
  if (!breaches.length && !pastes.length) {
    el.innerHTML = `<div class="ai-placeholder" style="color:var(--success)">
      ✓ No breaches found for this email in HIBP.</div>`;
    return;
  }
  let html = `<div class="breach-grid">`;

  // Stats
  html += `<div class="stat-bar" style="margin-bottom:.5rem">
    <div class="stat"><span class="stat-label">Breaches</span>
      <span class="stat-val breach-val">${breaches.length}</span></div>
    <div class="stat"><span class="stat-label">Pastes</span>
      <span class="stat-val" style="color:var(--warn)">${pastes.length}</span></div>
    <div class="stat"><span class="stat-label">Total Records Exposed</span>
      <span class="stat-val breach-val">${breaches.reduce((s, b) => s + (b.PwnCount || 0), 0).toLocaleString()}</span></div>
  </div>`;

  // Breach cards
  for (const b of breaches) {
    const classes = (b.DataClasses || []).map(c => `<span>${escHtml(c)}</span>`).join("");
    html += `<div class="breach-card">
      <div class="breach-name">${escHtml(b.Name || "Unknown")}</div>
      <div class="breach-meta">
        <span class="breach-badge">${escHtml(b.BreachDate || "?")}</span>
        <span class="breach-badge">${(b.PwnCount || 0).toLocaleString()} records</span>
        ${b.Domain ? `<span class="breach-badge warn">${escHtml(b.Domain)}</span>` : ""}
        ${b.IsVerified ? `<span class="breach-badge">Verified</span>` : ""}
      </div>
      ${classes ? `<div class="breach-classes">${classes}</div>` : ""}
    </div>`;
  }

  // Paste cards
  for (const p of pastes) {
    html += `<div class="breach-card paste-card">
      <div class="breach-name">📋 Paste: ${escHtml(p.Title || p.Id || "Unknown")}</div>
      <div class="breach-meta">
        <span class="breach-badge warn">${escHtml(p.Source || "Unknown source")}</span>
        ${p.Date ? `<span class="breach-badge warn">${escHtml(p.Date.slice(0,10))}</span>` : ""}
        ${p.EmailCount ? `<span class="breach-badge warn">${p.EmailCount} emails</span>` : ""}
      </div>
    </div>`;
  }

  html += `</div>`;
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════
// Maltego Export
// ═══════════════════════════════════════════════
$("maltegoBtn").addEventListener("click", exportMaltego);

async function exportMaltego() {
  if (!_lastResult) { toast("Run a search first.", "err"); return; }
  $("maltegoBtn").disabled = true;
  $("maltegoBtn").textContent = "🕸 Exporting…";
  try {
    const resp = await fetch("/api/export/maltego", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        query:         _lastQuery,
        type:          _lastType,
        osint_data:    Array.isArray(_lastResult.data) ? _lastResult.data : [],
        hibp_breaches: _hibpBreaches,
      })
    });
    if (!resp.ok) { toast("Maltego export failed.", "err"); return; }
    const blob = await resp.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `maltego_${_lastQuery.substring(0,20)}.mtgx`;
    a.click();
    URL.revokeObjectURL(url);
    toast("Maltego XML downloaded.", "ok");
  } catch (e) {
    toast(`Export error: ${e.message}`, "err");
  } finally {
    $("maltegoBtn").disabled = false;
    $("maltegoBtn").textContent = "🕸 Export Maltego";
  }
}

// ═══════════════════════════════════════════════
// Lampyre Import
// ═══════════════════════════════════════════════
$("lampyreFile").addEventListener("change", uploadLampyre);

async function uploadLampyre(e) {
  const file = e.target.files[0];
  if (!file) return;
  activateTab(document.querySelector('.tabs .tab[data-tab="lampyre"]'));
  $("lampyreContent").innerHTML = `<div class="spinner-wrap"><div class="spinner"></div><span>Parsing ${escHtml(file.name)}…</span></div>`;

  const form = new FormData();
  form.append("file", file);

  try {
    const d = await fetch("/api/lampyre/import", { method: "POST", body: form }).then(r => r.json());
    if (!d.success) {
      $("lampyreContent").innerHTML = `<div class="error-banner" style="display:block">${escHtml(d.error)}</div>`;
      return;
    }
    renderLampyre(d.rows, file.name);
    toast(`Lampyre: loaded ${d.count} rows.`);
  } catch (err) {
    $("lampyreContent").innerHTML = `<div class="error-banner" style="display:block">Import error: ${escHtml(err.message)}</div>`;
  } finally {
    e.target.value = "";
  }
}

function renderLampyre(rows, filename) {
  const el = $("lampyreContent");
  if (!rows || !rows.length) {
    el.innerHTML = `<div class="ai-placeholder">No data found in ${escHtml(filename)}.</div>`; return;
  }
  const keys = [...new Set(rows.flatMap(r => Object.keys(r)))];
  let html = `<p style="color:var(--text-dim);font-size:.8rem;margin-bottom:.6rem">
    📂 ${escHtml(filename)} — ${rows.length} rows</p>
    <div class="lampyre-table-wrap">
    <table class="lampyre-table">
      <thead><tr>${keys.map(k => `<th>${escHtml(k)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map(r =>
        `<tr>${keys.map(k =>
          `<td title="${escHtml(r[k] || "")}">${escHtml(r[k] || "–")}</td>`
        ).join("")}</tr>`
      ).join("")}</tbody>
    </table></div>`;
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════
// Export buttons
// ═══════════════════════════════════════════════
$("exportJson").addEventListener("click", () => {
  if (!_lastResult) return;
  const blob = new Blob([JSON.stringify(_lastResult.data, null, 2)], {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `osint_${_lastType}_${_lastQuery.substring(0,20)}.json`;
  a.click();
});

$("exportReport").addEventListener("click", () => {
  if (!_reportFile) { toast("No report file.", "err"); return; }
  window.location.href = `/api/reports/${encodeURIComponent(_reportFile)}`;
});

// ═══════════════════════════════════════════════
// History / Report modal
// ═══════════════════════════════════════════════
async function refreshHistory() {
  try {
    const list = await fetch("/api/reports").then(r => r.json());
    const ul   = $("historyList");
    ul.innerHTML = "";
    if (!list.length) { ul.innerHTML = `<li class="history-empty">No reports yet</li>`; return; }
    for (const item of list) {
      const li  = document.createElement("li");
      li.className = "history-item";
      const ts  = (item.timestamp || "").replace("T"," ").substring(0,16);
      li.innerHTML = `<div class="h-query"><span class="h-badge">${escHtml(item.type)}</span>${escHtml(item.query)}</div>
                      <div class="h-meta">${escHtml(ts)}</div>`;
      li.addEventListener("click", () => openReport(item.filename));
      ul.appendChild(li);
    }
  } catch {}
}
$("refreshHistory").addEventListener("click", refreshHistory);

async function openReport(filename) {
  try {
    const d = await fetch(`/api/reports/${encodeURIComponent(filename)}`).then(r => r.json());
    $("modalTitle").textContent = `Report – ${d.metadata?.query || filename}`;
    // Support both old (raw_data) and new (osint_data) schema
    const raw = d.osint_data || d.raw_data || {};
    $("modalRaw").textContent = JSON.stringify(raw, null, 2);
    const aiEl = $("modalAI");
    if (d.ai_analysis) { aiEl.textContent = d.ai_analysis; aiEl.classList.remove("hidden"); }
    else aiEl.classList.add("hidden");
    $$(".modal-tabs .tab").forEach(t => t.classList.remove("active"));
    document.querySelector('.modal-tabs .tab[data-modal-tab="raw"]').classList.add("active");
    $("modalRaw").classList.remove("hidden");
    aiEl.classList.add("hidden");
    $("reportModal").classList.remove("hidden");
    $("modalDownload").dataset.filename = filename;
  } catch (e) { toast(`Failed to load report: ${e.message}`, "err"); }
}

$("modalClose").addEventListener("click", () => $("reportModal").classList.add("hidden"));
$("reportModal").addEventListener("click", e => { if (e.target === $("reportModal")) $("reportModal").classList.add("hidden"); });
$$(".modal-tabs .tab").forEach(t => t.addEventListener("click", () => {
  $$(".modal-tabs .tab").forEach(x => x.classList.remove("active")); t.classList.add("active");
  const tab = t.dataset.modalTab;
  $("modalRaw").classList.toggle("hidden", tab !== "raw");
  $("modalAI").classList.toggle("hidden",  tab !== "ai");
}));
$("modalDownload").addEventListener("click", () => {
  const fn = $("modalDownload").dataset.filename;
  if (fn) window.location.href = `/api/reports/${encodeURIComponent(fn)}`;
});

// ═══════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════
(async function init() {
  refreshAIStatus();
  refreshHistory();
  const cfg = await fetch("/api/config").then(r => r.json()).catch(() => ({}));
  if (!cfg.has_key) $("settingsPanel").classList.remove("hidden");
})();
