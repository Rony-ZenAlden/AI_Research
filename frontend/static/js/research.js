// Research workspace orchestrator: create sessions, watch live progress, render reports.
import { api, ApiError } from "./api.js";
import { RealtimeClient } from "./ws.js";

const cfg = window.NEUROSEEK_CONFIG || {};

if (!api.isAuthed()) {
  window.location.href = "/login";
}

const $ = (sel) => document.querySelector(sel);

// ----- topbar -----
const wsPill = $("#ws-pill");
const wsLabel = $("#ws-label");

(async () => {
  try {
    const me = await api.get("/auth/me/");
    $("#user-email").textContent = me.email;
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      api.logout();
      window.location.href = "/login";
    }
  }
})();

$("#logout-btn").addEventListener("click", () => {
  api.logout();
  window.location.href = "/login";
});

// ----- state -----
let activeSessionId = null;          // id of the session currently displayed
let sessionsCache = [];

// ----- DOM refs -----
const sessionList = $("#session-list");
const sessionCount = $("#session-count");
const form = $("#research-form");
const questionInput = $("#question");
const startBtn = $("#start-btn");
const activeCard = $("#active-session");
const activeQuestion = $("#active-question");
const activeStatusPill = $("#active-status-pill");
const stepsEl = $("#active-steps");
const fetchLog = $("#active-fetch-log");
const reportEl = $("#active-report");
const errorEl = $("#active-error");
const exportBar = $("#active-export");
const btnExportMd = $("#export-md");
const btnExportPdf = $("#export-pdf");

// ============================================================
// Session list
// ============================================================
async function loadSessions() {
  try {
    const res = await api.get("/research/sessions/");
    sessionsCache = res.results || [];
    renderSessions();
  } catch (e) {
    /* non-critical */
  }
}

function renderSessions() {
  sessionCount.textContent = sessionsCache.length;
  if (sessionsCache.length === 0) {
    sessionList.innerHTML = '<div class="empty-state small">No sessions yet.</div>';
    return;
  }
  sessionList.innerHTML = "";
  for (const s of sessionsCache) {
    const li = document.createElement("button");
    li.type = "button";
    li.className = `session-item status-${s.status}`;
    li.dataset.id = s.id;
    if (s.id === activeSessionId) li.classList.add("active");
    const title = document.createElement("div");
    title.className = "session-title";
    title.textContent = s.question;
    title.title = s.question;
    const meta = document.createElement("div");
    meta.className = "session-meta muted small";
    meta.textContent = `${s.status}${s.duration_ms ? ` · ${(s.duration_ms / 1000).toFixed(1)}s` : ""}`;
    li.appendChild(title);
    li.appendChild(meta);
    li.addEventListener("click", () => openSession(s.id));
    sessionList.appendChild(li);
  }
}

// ============================================================
// Active session UI
// ============================================================
async function openSession(id) {
  activeSessionId = id;
  renderSessions(); // refresh "active" highlight
  activeCard.classList.remove("hidden");
  resetActiveUI();

  try {
    const s = await api.get(`/research/sessions/${id}/`);
    paintSession(s);
  } catch (err) {
    showError(`Failed to load session: ${err.message}`);
  }
}

function resetActiveUI() {
  activeQuestion.textContent = "Loading…";
  activeStatusPill.textContent = "";
  activeStatusPill.className = "status-pill";
  stepsEl.querySelectorAll("li").forEach((li) => {
    li.classList.remove("step-active", "step-done", "step-failed");
    li.querySelector(".step-msg").textContent = "";
  });
  fetchLog.innerHTML = "";
  fetchLog.classList.add("hidden");
  reportEl.innerHTML = "";
  reportEl.classList.add("hidden");
  errorEl.textContent = "";
  errorEl.classList.add("hidden");
  exportBar.classList.add("hidden");
}

function paintSession(s) {
  activeQuestion.textContent = s.question;
  setStatusPill(s.status);
  paintStepsForStatus(s.status);

  if (s.status === "ready" && s.report_text) {
    renderReport(s.report_text, s.report_sources || []);
    exportBar.classList.remove("hidden");
  } else if (s.status === "failed") {
    showError(s.error_message || "Session failed.");
  }

  // Replay plan/fetch info from saved fields if present
  if (s.plan && s.plan.queries) {
    setStepMessage("planning", `${s.plan.queries.length} queries: ${s.plan.queries.slice(0, 3).join(", ")}…`);
  }
  if (s.document_ids && s.document_ids.length) {
    setStepMessage("fetching", `${s.document_ids.length} pages indexed`);
  }
}

function setStatusPill(status) {
  activeStatusPill.textContent = status;
  activeStatusPill.className = `status-pill status-pill-${status}`;
}

const STEP_ORDER = ["planning", "searching", "fetching", "retrieving", "synthesizing"];

function paintStepsForStatus(status) {
  // Done = any earlier step. Active = current. Untouched = later.
  const idx = STEP_ORDER.indexOf(status);
  STEP_ORDER.forEach((step, i) => {
    const li = stepsEl.querySelector(`li[data-step="${step}"]`);
    if (!li) return;
    li.classList.remove("step-active", "step-done", "step-failed");
    if (status === "ready") li.classList.add("step-done");
    else if (status === "failed") {
      if (i < idx || idx < 0) li.classList.add("step-done");
      else if (i === idx) li.classList.add("step-failed");
    } else if (idx >= 0) {
      if (i < idx) li.classList.add("step-done");
      else if (i === idx) li.classList.add("step-active");
    }
  });
}

function setStepMessage(step, text) {
  const li = stepsEl.querySelector(`li[data-step="${step}"]`);
  if (li) li.querySelector(".step-msg").textContent = text || "";
}

function appendFetchLog(outcome, info) {
  fetchLog.classList.remove("hidden");
  const row = document.createElement("div");
  row.className = `fetch-row fetch-${outcome}`;
  const icon = outcome === "ok" ? "✓" : "✗";
  row.innerHTML = `
    <span class="fetch-icon">${icon}</span>
    <span class="fetch-url">${escapeHtml(info.url || "")}</span>
    <span class="fetch-msg muted small">${escapeHtml(info.message || "")}</span>
  `;
  fetchLog.appendChild(row);
  fetchLog.scrollTop = fetchLog.scrollHeight;
}

function showError(msg) {
  errorEl.textContent = msg;
  errorEl.classList.remove("hidden");
}

// ============================================================
// Render the markdown report (with [N] citations)
// ============================================================
function renderReport(text, sources) {
  reportEl.classList.remove("hidden");
  reportEl.innerHTML = renderMarkdown(text, sources);
  attachCitationHandlers(sources);
}

function renderMarkdown(text, sources) {
  let html = escapeHtml(text);
  // citations [N] (do this BEFORE other markdown so [N] inside text isn't escaped further)
  html = html.replace(/\[(\d+)\]/g, (m, n) => {
    const idx = parseInt(n, 10);
    if (idx < 1 || idx > sources.length) return m;
    const title = sources[idx - 1].title || "";
    return `<span class="cite" data-index="${idx}" title="${escapeAttr(title)}">[${idx}]</span>`;
  });
  // simple markdown — headers, bold, italic, bullets, tables
  html = html
    .replace(/^### (.+)$/gm, "<h4>$1</h4>")
    .replace(/^## (.+)$/gm, "<h3>$1</h3>")
    .replace(/^# (.+)$/gm, "<h2>$1</h2>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, "<em>$1</em>");

  // Tables — pipe-style
  html = renderMarkdownTables(html);

  // Bullets — group consecutive "- " lines into <ul>
  html = html.replace(
    /(?:^|\n)((?:- [^\n]+\n?)+)/g,
    (m, block) => {
      const items = block
        .trim()
        .split("\n")
        .map((line) => line.replace(/^- /, "").trim())
        .filter(Boolean)
        .map((t) => `<li>${t}</li>`)
        .join("");
      return `\n<ul>${items}</ul>`;
    }
  );

  // Paragraphs from blank lines
  html = html.replace(/\n{2,}/g, "<br><br>");
  return html;
}

function renderMarkdownTables(html) {
  // Match table blocks: header row + separator + data rows
  return html.replace(
    /(?:^|\n)((?:\|[^\n]+\|\n)+)/g,
    (m, block) => {
      const lines = block.trim().split("\n").filter((l) => l.trim().startsWith("|"));
      if (lines.length < 2) return m;
      const headerCells = splitRow(lines[0]);
      // second line should be the separator
      const isSep = /\|?\s*[:\-\s|]+\s*\|?/.test(lines[1]) && lines[1].includes("-");
      if (!isSep) return m;
      const dataRows = lines.slice(2);
      let table = "<table class='report-table'><thead><tr>";
      headerCells.forEach((h) => (table += `<th>${h}</th>`));
      table += "</tr></thead><tbody>";
      for (const row of dataRows) {
        const cells = splitRow(row);
        table += "<tr>" + cells.map((c) => `<td>${c}</td>`).join("") + "</tr>";
      }
      table += "</tbody></table>";
      return "\n" + table;
    }
  );
}

function splitRow(line) {
  return line
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());
}

function attachCitationHandlers(sources) {
  reportEl.querySelectorAll(".cite").forEach((el) => {
    el.addEventListener("click", () => {
      const idx = parseInt(el.dataset.index, 10);
      const src = sources[idx - 1];
      if (!src) return;
      // Highlight matching reference if present
      const refList = reportEl.querySelectorAll("li, p");
      // Simple visual feedback — just briefly flash the clicked element
      el.classList.add("flash");
      setTimeout(() => el.classList.remove("flash"), 800);
    });
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}
function escapeAttr(s) {
  return String(s).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// ============================================================
// Export buttons (Markdown / PDF)
// ============================================================
async function downloadExport(format) {
  if (!activeSessionId) return;
  const btn = format === "pdf" ? btnExportPdf : btnExportMd;
  const originalLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Preparing…";
  try {
    const url = `${cfg.apiBase}/research/sessions/${activeSessionId}/export.${format}`;
    const resp = await fetch(url, {
      headers: { Authorization: `Bearer ${api.tokens.access}` },
    });
    if (!resp.ok) {
      const detail = await resp.text();
      throw new Error(`HTTP ${resp.status}: ${detail.slice(0, 200)}`);
    }
    const blob = await resp.blob();
    const cd = resp.headers.get("Content-Disposition") || "";
    const filename = (cd.match(/filename="?([^"]+)"?/) || [])[1] || `research.${format}`;

    const downloadUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(downloadUrl);
  } catch (err) {
    showError(`Export failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = originalLabel;
  }
}

btnExportMd.addEventListener("click", () => downloadExport("md"));
btnExportPdf.addEventListener("click", () => downloadExport("pdf"));

// ============================================================
// Form: start a new research session
// ============================================================
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = questionInput.value.trim();
  if (q.length < 10) return;
  startBtn.disabled = true;
  startBtn.classList.add("loading");
  try {
    const session = await api.post("/research/sessions/", { question: q });
    sessionsCache.unshift({
      id: session.id,
      question: session.question,
      status: session.status,
      duration_ms: 0,
      created_at: session.created_at,
    });
    renderSessions();
    activeSessionId = session.id;
    questionInput.value = "";
    activeCard.classList.remove("hidden");
    resetActiveUI();
    paintSession(session);
  } catch (err) {
    showError(`Could not start session: ${err.message}`);
  } finally {
    startBtn.disabled = false;
    startBtn.classList.remove("loading");
  }
});

// ============================================================
// Realtime — listen for research.* events
// ============================================================
const rt = new RealtimeClient({
  url: cfg.wsUrl,
  getToken: () => api.tokens.access,
  onStatus: (s) => {
    wsPill.dataset.status = s;
    wsLabel.textContent = s;
  },
  onEvent: handleEvent,
});

function handleEvent(msg) {
  const type = msg.type || "";
  const data = msg.data || {};
  if (!type.startsWith("research.")) return;

  const sid = data.session_id;
  if (sid !== activeSessionId) {
    // Update list-side status badge silently
    const cached = sessionsCache.find((s) => s.id === sid);
    if (cached) {
      if (type === "research.completed") cached.status = "ready";
      else if (type === "research.failed") cached.status = "failed";
      else if (data.step) cached.status = data.step;
      renderSessions();
    }
    return;
  }

  if (type === "research.progress") {
    const step = data.step;
    const message = data.message || "";

    if (step === "planning" || step === "planned") {
      paintStepsForStatus(step === "planned" ? "searching" : "planning");
      setStatusPill(step === "planned" ? "searching" : "planning");
      if (data.queries) {
        setStepMessage("planning", `${data.queries.length} queries: ${data.queries.slice(0, 3).join(", ")}…`);
      } else if (message) {
        setStepMessage("planning", message);
      }
    } else if (step === "searching" || step === "searched") {
      paintStepsForStatus(step === "searched" ? "fetching" : "searching");
      setStatusPill(step === "searched" ? "fetching" : "searching");
      setStepMessage("searching", message);
    } else if (step === "fetching" || step === "fetched") {
      if (step === "fetching" && data.url) {
        appendFetchLog(data.outcome || "ok", data);
      }
      paintStepsForStatus(step === "fetched" ? "retrieving" : "fetching");
      setStatusPill(step === "fetched" ? "retrieving" : "fetching");
      setStepMessage("fetching", message);
    } else if (step === "retrieving" || step === "retrieved") {
      paintStepsForStatus(step === "retrieved" ? "synthesizing" : "retrieving");
      setStatusPill(step === "retrieved" ? "synthesizing" : "retrieving");
      setStepMessage("retrieving", message);
    } else if (step === "synthesizing") {
      paintStepsForStatus("synthesizing");
      setStatusPill("synthesizing");
      setStepMessage("synthesizing", message);
    }
  } else if (type === "research.completed") {
    setStatusPill("ready");
    paintStepsForStatus("ready");
    exportBar.classList.remove("hidden");
    // refresh full session to get the report text
    api.get(`/research/sessions/${sid}/`).then(paintSession).catch(() => {});
    loadSessions();
  } else if (type === "research.failed") {
    setStatusPill("failed");
    paintStepsForStatus("failed");
    showError(data.error || "Session failed.");
    loadSessions();
  }
}

// ============================================================
// Boot
// ============================================================
(async () => {
  await loadSessions();
  rt.connect();
  // Auto-open the most recent session if any
  if (sessionsCache.length > 0) {
    openSession(sessionsCache[0].id);
  }
})();
