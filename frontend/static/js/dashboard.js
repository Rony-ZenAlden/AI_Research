// Dashboard orchestrator: auth gate, doc list, upload, search,
// realtime activity feed via the Go hub.
import { api, ApiError } from "./api.js";
import { RealtimeClient } from "./ws.js";

const cfg = window.NEUROSEEK_CONFIG || {};

// ----- Auth gate -----
if (!api.isAuthed()) {
  window.location.href = "/login";
}

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

// ----- Toasts -----
const toastsEl = $("#toasts");
function toast(message, kind = "info", ttl = 3500) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  toastsEl.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transform = "translateX(20px)";
    el.style.transition = "all 200ms ease-out";
    setTimeout(() => el.remove(), 200);
  }, ttl);
}

// ----- Activity log -----
const activityLog = $("#activity-log");
function logActivity(kind, message) {
  const div = document.createElement("div");
  div.className = `activity-item activity-${kind}`;
  const ts = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const tsEl = document.createElement("span");
  tsEl.className = "ts";
  tsEl.textContent = ts;
  const msgEl = document.createElement("span");
  msgEl.className = "msg";
  msgEl.textContent = message;
  div.appendChild(tsEl);
  div.appendChild(msgEl);
  activityLog.prepend(div);
  while (activityLog.children.length > 80) activityLog.removeChild(activityLog.lastChild);
}
$("#clear-log").addEventListener("click", () => { activityLog.innerHTML = ""; });

// ----- User -----
let user = null;
async function fetchUser() {
  try {
    user = await api.get("/auth/me/");
    $("#user-email").textContent = user.email;
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      api.logout();
      window.location.href = "/login";
    }
  }
}

$("#logout-btn").addEventListener("click", () => {
  api.logout();
  window.location.href = "/login";
});

// ----- Documents -----
let docsCache = [];

async function loadDocuments() {
  try {
    const res = await api.get("/vector/documents/");
    docsCache = res.results || res;
    renderDocs();
  } catch (e) {
    toast("Failed to load documents: " + e.message, "error");
  }
}

function renderDocs() {
  const list = $("#doc-list");
  $("#doc-count").textContent = docsCache.length;
  if (docsCache.length === 0) {
    list.innerHTML = '<div class="empty-state">No documents yet. Upload one →</div>';
    return;
  }
  list.innerHTML = "";
  for (const doc of docsCache) {
    list.appendChild(renderDoc(doc));
  }
}

function renderDoc(doc) {
  const div = document.createElement("div");
  div.className = `doc-item status-${doc.status}`;
  div.dataset.docId = doc.id;
  const icon = doc.source_type === "file" ? "📄" : doc.source_type === "web" ? "🌐" : "✏️";
  const iconEl = document.createElement("div");
  iconEl.className = "doc-icon";
  iconEl.textContent = icon;
  const meta = document.createElement("div");
  meta.className = "doc-meta";
  const title = document.createElement("div");
  title.className = "doc-title";
  title.textContent = doc.title;
  title.title = doc.title;
  const status = document.createElement("div");
  status.className = "doc-status";
  status.textContent = `${doc.status} · ${doc.chunk_count || 0} chunks`;
  meta.appendChild(title);
  meta.appendChild(status);
  // For failed docs, surface the error reason inline so the user doesn't have
  // to open the modal to see why.
  if (doc.status === "failed" && doc.error_message) {
    const err = document.createElement("div");
    err.className = "doc-error";
    err.textContent = doc.error_message;
    err.title = doc.error_message;
    meta.appendChild(err);
  }
  div.appendChild(iconEl);
  div.appendChild(meta);
  div.addEventListener("click", () => openDocModal(doc.id));
  return div;
}

function updateDocUI(docId, patch) {
  const item = document.querySelector(`[data-doc-id="${docId}"]`);
  if (!item) return;
  if (patch.status) {
    item.classList.remove("status-pending", "status-processing", "status-ready", "status-failed");
    item.classList.add(`status-${patch.status}`);
  }
  const status = item.querySelector(".doc-status");
  const cur = docsCache.find((d) => d.id === docId);
  if (cur && patch) Object.assign(cur, patch);
  if (cur && status) status.textContent = `${cur.status} · ${cur.chunk_count || 0} chunks`;
}

// ----- Text ingest -----
$("#text-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  const title = form.title.value.trim();
  const text = form.text.value.trim();
  if (!title || text.length < 10) {
    toast("Title required and text must be ≥10 chars.", "error");
    return;
  }
  try {
    const doc = await api.post("/vector/ingest/text/", { title, text });
    logActivity("ingest", `Text "${doc.title}" ingested → ${doc.chunk_count} chunks`);
    toast("Text ingested.", "success");
    form.reset();
    loadDocuments();
  } catch (e) {
    toast("Ingest failed: " + e.message, "error");
  }
});

// ----- File upload (drag&drop + click) -----
const dropZone = $("#drop-zone");
const fileInput = $("#file-input");

dropZone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (e) => {
  uploadFiles(Array.from(e.target.files));
  fileInput.value = "";
});
["dragenter", "dragover"].forEach((evt) =>
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.add("dragging");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragging");
  })
);
dropZone.addEventListener("drop", (e) => {
  uploadFiles(Array.from(e.dataTransfer.files));
});

async function uploadFiles(files) {
  for (const f of files) {
    const fd = new FormData();
    fd.append("file", f);
    fd.append("title", f.name);
    try {
      const doc = await api.raw("POST", "/vector/ingest/file/", { body: fd });
      logActivity("upload", `Queued ${f.name} (id=${doc.id}) → status pending`);
      toast(`Uploaded ${f.name}`, "success");
      loadDocuments();
    } catch (e) {
      const detail = e.detail && typeof e.detail === "object"
        ? (e.detail.file ? e.detail.file.join(", ") : JSON.stringify(e.detail))
        : (e.message || "upload failed");
      logActivity("error", `Upload failed for ${f.name}: ${detail}`);
      toast(`Upload failed: ${detail}`, "error");
    }
  }
}

// ----- Search (semantic + web) -----
const searchForm = $("#search-form");
const searchInput = $("#q");
const resultList = $("#search-results");
const resultMeta = $("#result-meta");
const resultsTitle = $("#results-title");

let searchMode = "semantic";  // "semantic" | "web"

const placeholders = {
  semantic: "Ask anything across your documents…",
  web: "Search the live web (DuckDuckGo, Bing, Wikipedia…)…",
};

document.querySelectorAll(".search-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    searchMode = tab.dataset.mode;
    document.querySelectorAll(".search-tab").forEach((t) => {
      const active = t === tab;
      t.classList.toggle("active", active);
      t.setAttribute("aria-selected", active ? "true" : "false");
    });
    searchInput.placeholder = placeholders[searchMode];
    resultsTitle.textContent = searchMode === "web" ? "Web results" : "Results";
    resultList.innerHTML = `<div class="empty-state"><div class="empty-icon">⌖</div><div>${
      searchMode === "web"
        ? "Search the public web. Click <b>Ingest</b> on any result to add it to your library."
        : "Search to retrieve semantically relevant chunks across all your documents."
    }</div></div>`;
    resultMeta.textContent = "";
    searchInput.focus();
  });
});

searchForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = searchInput.value.trim();
  if (!q) return;
  resultList.innerHTML = '<div class="empty-state"><div class="empty-icon">⏳</div>Searching…</div>';
  resultMeta.textContent = "";
  try {
    const t0 = performance.now();
    if (searchMode === "semantic") {
      const res = await api.get(`/vector/search/?q=${encodeURIComponent(q)}&top_k=10`);
      const dt = Math.round(performance.now() - t0);
      renderSemanticResults(res.results || [], dt);
    } else {
      const res = await api.post("/search/web/", { q, count: 10 });
      const dt = Math.round(performance.now() - t0);
      renderWebResults(res.results || [], dt);
    }
    loadRecent();  // refresh recent chips after a successful search
  } catch (e) {
    resultList.innerHTML = `<div class="empty-state" style="color:var(--error)">Search failed: ${escapeHtml(e.message)}</div>`;
  }
});

function renderSemanticResults(hits, dt) {
  lastSearchSources = hits.map((h) => ({
    title: h.document_title,
    ref: `chunk ${h.position}`,
    text: h.text || "",
  }));
  setAISourcesAvailable(lastSearchSources.length, "semantic");
  if (hits.length === 0) {
    resultList.innerHTML = '<div class="empty-state">No matches across your documents.</div>';
    resultMeta.textContent = `0 results · ${dt}ms`;
    return;
  }
  resultList.innerHTML = "";
  for (const hit of hits) resultList.appendChild(renderSemanticHit(hit));
  resultMeta.textContent = `${hits.length} results · ${dt}ms`;
}

function renderSemanticHit(hit) {
  const div = document.createElement("div");
  div.className = "search-hit";
  const meta = document.createElement("div");
  meta.className = "hit-meta";
  const score = document.createElement("span");
  score.className = "hit-score";
  score.textContent = `${(hit.score * 100).toFixed(0)}%`;
  const docTitle = document.createElement("span");
  docTitle.className = "hit-doc";
  docTitle.textContent = `${hit.document_title} · chunk ${hit.position}`;
  meta.appendChild(score);
  meta.appendChild(docTitle);
  const text = document.createElement("div");
  text.className = "hit-text";
  text.textContent = hit.text;
  div.appendChild(meta);
  div.appendChild(text);
  return div;
}

function renderWebResults(results, dt) {
  lastSearchSources = results
    .filter((r) => r.snippet)
    .map((r) => ({
      title: r.title || r.url,
      ref: r.url,
      text: r.snippet || "",
    }));
  setAISourcesAvailable(lastSearchSources.length, "web");
  if (results.length === 0) {
    resultList.innerHTML = '<div class="empty-state">No web results. Try different keywords.</div>';
    resultMeta.textContent = `0 results · ${dt}ms`;
    return;
  }
  resultList.innerHTML = "";
  for (const r of results) resultList.appendChild(renderWebHit(r));
  resultMeta.textContent = `${results.length} web results · ${dt}ms`;
}

function renderWebHit(r) {
  const div = document.createElement("div");
  div.className = "search-hit web-hit";

  const head = document.createElement("div");
  head.className = "hit-head";
  const link = document.createElement("a");
  link.className = "hit-link";
  link.href = r.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = r.title || r.url;
  const engine = document.createElement("span");
  engine.className = "hit-engine";
  engine.textContent = r.engine || "";
  head.appendChild(link);
  head.appendChild(engine);

  const urlEl = document.createElement("div");
  urlEl.className = "hit-url";
  urlEl.textContent = r.url;

  const snippet = document.createElement("div");
  snippet.className = "hit-text";
  snippet.textContent = r.snippet || "";

  const actions = document.createElement("div");
  actions.className = "hit-actions";
  const ingestBtn = document.createElement("button");
  ingestBtn.type = "button";
  ingestBtn.className = "btn btn-ghost btn-xs";
  ingestBtn.textContent = "+ Ingest";
  ingestBtn.addEventListener("click", () => ingestUrl(r.url, r.title, ingestBtn));
  actions.appendChild(ingestBtn);

  div.appendChild(head);
  div.appendChild(urlEl);
  if (r.snippet) div.appendChild(snippet);
  div.appendChild(actions);
  return div;
}

async function ingestUrl(url, title, btn) {
  if (btn) {
    btn.disabled = true;
    btn.textContent = "queued…";
  }
  try {
    const doc = await api.post("/search/ingest/url/", { url, title: title || "" });
    logActivity("upload", `Queued URL doc ${doc.id}: ${url}`);
    toast(`Queued: ${url}`, "success");
    if (btn) btn.textContent = "queued ✓";
    loadDocuments();
  } catch (e) {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "+ Ingest";
    }
    const detail = e.detail && typeof e.detail === "object"
      ? (e.detail.url ? e.detail.url.join(", ") : JSON.stringify(e.detail))
      : (e.message || "ingest failed");
    logActivity("error", `URL ingest failed: ${detail}`);
    toast(`URL ingest failed: ${detail}`, "error");
  }
}

// ----- Standalone URL ingest form -----
const urlForm = $("#url-form");
if (urlForm) {
  urlForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = urlForm.url.value.trim();
    if (!url) return;
    await ingestUrl(url, "");
    urlForm.reset();
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

// ----- Realtime hub -----
const wsPill = $("#ws-pill");
const wsLabel = $("#ws-label");

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

  if (type === "hello") {
    logActivity("ws", `Connected as user #${data.user_id}`);
    return;
  }

  if (type.startsWith("document.processing.")) {
    const phase = type.split(".").pop();
    const doc_id = data.document_id;
    const extra = describePhase(phase, data);
    logActivity(
      phase === "completed" ? "completed" : phase === "failed" ? "failed" : "processing",
      `doc ${doc_id} → ${phase}${extra ? " " + extra : ""}`
    );

    let nextStatus = phase;
    if (phase === "started" || phase === "extracted" || phase === "chunked" || phase === "embedded") {
      nextStatus = "processing";
    } else if (phase === "completed") {
      nextStatus = "ready";
    } else if (phase === "failed") {
      nextStatus = "failed";
    }
    updateDocUI(doc_id, {
      status: nextStatus,
      chunk_count: data.chunk_count ?? undefined,
    });

    if (phase === "completed" || phase === "failed") {
      // refresh from server for chunk_count and final state
      setTimeout(loadDocuments, 400);
    }
    return;
  }

  if (type === "test.ping") {
    logActivity("ws", `ping: ${data.message || "(no message)"}`);
    return;
  }

  logActivity("ws", `${type}: ${JSON.stringify(data)}`);
}

function describePhase(phase, data) {
  if (phase === "extracted") return `(${data.char_count} chars)`;
  if (phase === "chunked" || phase === "embedded") return `(${data.chunk_count} chunks)`;
  if (phase === "completed") return `(${data.chunk_count} chunks)`;
  if (phase === "failed") return `: ${data.error || "error"}`;
  return "";
}

// ----- Demo data button (header + empty state both use class .js-load-demo) -----
document.addEventListener("click", async (e) => {
  const btn = e.target.closest(".js-load-demo");
  if (!btn) return;
  const originalLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Queuing…";
  try {
    const res = await api.post("/vector/load-demo/", {});
    logActivity("upload", `Queued ${res.queued} demo documents — watch progress in the activity feed.`);
    toast(`Queued ${res.queued} demo documents.`, "success");
    loadDocuments();
  } catch (err) {
    toast(`Demo load failed: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = originalLabel;
  }
});

// ============================================================
// Doc detail modal
// ============================================================
const modal = $("#doc-modal");
const modalTitle = $("#modal-title");
const modalSubtitle = $("#modal-subtitle");
const modalStatusRow = $("#modal-status-row");
const modalSource = $("#modal-source");
const modalText = $("#modal-text");
const modalChunks = $("#modal-chunks");
const modalChunkCount = $("#modal-chunk-count");
const modalDelete = $("#modal-delete");
const modalClose = $("#modal-close");

let currentDocId = null;

modalClose.addEventListener("click", closeDocModal);
modal.addEventListener("click", (e) => {
  if (e.target === modal) closeDocModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !modal.classList.contains("hidden")) closeDocModal();
});

async function openDocModal(docId) {
  currentDocId = docId;
  modalTitle.textContent = "Loading…";
  modalSubtitle.textContent = "";
  modalStatusRow.innerHTML = "";
  modalSource.textContent = "";
  modalText.textContent = "";
  modalChunks.innerHTML = "";
  modalChunkCount.textContent = "";
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");

  try {
    const [doc, chunks] = await Promise.all([
      api.get(`/vector/documents/${docId}/`),
      api.get(`/vector/documents/${docId}/chunks/`).catch(() => []),
    ]);
    renderDocModal(doc, Array.isArray(chunks) ? chunks : (chunks.results || []));
  } catch (err) {
    modalTitle.textContent = "Error";
    modalText.textContent = `Failed to load document: ${err.message}`;
  }
}

function closeDocModal() {
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  currentDocId = null;
}

function renderDocModal(doc, chunks) {
  modalTitle.textContent = doc.title || `Document #${doc.id}`;
  const subParts = [
    `id ${doc.id}`,
    doc.source_type,
    doc.created_at ? `created ${new Date(doc.created_at).toLocaleString()}` : null,
  ].filter(Boolean);
  modalSubtitle.textContent = subParts.join(" · ");

  modalStatusRow.innerHTML = "";
  modalStatusRow.appendChild(renderStatusPill(doc.status));
  if (doc.processed_at) {
    const proc = document.createElement("span");
    proc.className = "muted small";
    proc.textContent = `processed ${new Date(doc.processed_at).toLocaleString()}`;
    modalStatusRow.appendChild(proc);
  }
  if (doc.error_message) {
    const err = document.createElement("div");
    err.className = "modal-error";
    err.textContent = doc.error_message;
    modalStatusRow.appendChild(err);
  }

  // Source line — URL link, file link, or "—"
  modalSource.innerHTML = "";
  if (doc.source_type === "web" && doc.source_uri) {
    const a = document.createElement("a");
    a.href = doc.source_uri;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = doc.source_uri;
    modalSource.appendChild(a);
  } else if (doc.source_type === "file" && doc.file_url) {
    const a = document.createElement("a");
    a.href = doc.file_url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    const sizeMB = doc.file_size_bytes ? (doc.file_size_bytes / 1024 / 1024).toFixed(2) : "?";
    a.textContent = `${doc.source_uri} (${sizeMB} MB · ${doc.mime_type || "unknown"})`;
    modalSource.appendChild(a);
  } else if (doc.source_type === "text") {
    modalSource.textContent = "Pasted text";
  } else {
    modalSource.textContent = "—";
  }

  modalText.textContent = doc.raw_text_preview || "(no extracted text)";

  modalChunkCount.textContent = `${chunks.length}`;
  modalChunks.innerHTML = "";
  if (chunks.length === 0) {
    const empty = document.createElement("div");
    empty.className = "muted small";
    empty.textContent = doc.status === "processing" || doc.status === "pending"
      ? "Chunks will appear here once processing finishes."
      : "No chunks for this document yet.";
    modalChunks.appendChild(empty);
  } else {
    for (const c of chunks.slice(0, 50)) {
      const piece = document.createElement("div");
      piece.className = "modal-chunk";
      const head = document.createElement("div");
      head.className = "modal-chunk-head muted small";
      head.textContent = `chunk ${c.position} · ${c.char_count} chars`;
      const body = document.createElement("div");
      body.className = "modal-chunk-body";
      body.textContent = c.text;
      piece.appendChild(head);
      piece.appendChild(body);
      modalChunks.appendChild(piece);
    }
    if (chunks.length > 50) {
      const more = document.createElement("div");
      more.className = "muted small";
      more.textContent = `… ${chunks.length - 50} more chunks not shown`;
      modalChunks.appendChild(more);
    }
  }
}

function renderStatusPill(status) {
  const span = document.createElement("span");
  span.className = `status-pill status-pill-${status}`;
  span.textContent = status;
  return span;
}

modalDelete.addEventListener("click", async () => {
  if (currentDocId == null) return;
  if (!confirm("Delete this document and all its chunks? This cannot be undone.")) return;
  modalDelete.disabled = true;
  modalDelete.textContent = "Deleting…";
  try {
    await api.del(`/vector/documents/${currentDocId}/`);
    toast("Document deleted.", "success");
    logActivity("ws", `doc ${currentDocId} deleted`);
    closeDocModal();
    loadDocuments();
  } catch (err) {
    toast(`Delete failed: ${err.message}`, "error");
  } finally {
    modalDelete.disabled = false;
    modalDelete.textContent = "Delete document";
  }
});

// ============================================================
// AI panel — Summarize / Compare against current results
// ============================================================
const btnSummarize = $("#btn-summarize");
const btnCompare = $("#btn-compare");
const aiOutput = $("#ai-output");
const aiMeta = $("#ai-meta");

let lastSearchSources = []; // {title, ref, text}[]

function setAISourcesAvailable(count, mode) {
  const has = count > 0;
  btnSummarize.disabled = !has;
  btnCompare.disabled = !has;
  if (!has) {
    aiMeta.textContent = "";
    aiOutput.classList.add("hidden");
    aiOutput.innerHTML = "";
    return;
  }
  const note = mode === "web" ? " (snippets only)" : "";
  aiMeta.textContent = `${count} source${count === 1 ? "" : "s"}${note}`;
  aiOutput.classList.add("hidden");
  aiOutput.innerHTML = "";
}

async function runAI(mode) {
  if (!lastSearchSources.length) return;
  const query = searchInput.value.trim();
  if (!query) return;

  btnSummarize.disabled = true;
  btnCompare.disabled = true;
  aiOutput.classList.remove("hidden");
  aiOutput.innerHTML = `<div class="ai-loading"><span class="ai-spinner"></span> ${
    mode === "compare" ? "Comparing sources" : "Synthesizing"
  }… (this can take a while on a small model)</div>`;

  try {
    const res = await api.post("/ai/summarize/", {
      query,
      mode,
      sources: lastSearchSources.slice(0, 10),
    });
    renderAIResponse(res);
  } catch (err) {
    renderAIError(err);
  } finally {
    btnSummarize.disabled = false;
    btnCompare.disabled = false;
  }
}

btnSummarize.addEventListener("click", () => runAI("summarize"));
btnCompare.addEventListener("click", () => runAI("compare"));

function renderAIResponse(res) {
  const safeText = renderTextWithCitations(res.text, res.sources);
  aiOutput.innerHTML = `
    <div class="ai-meta-row">
      <span class="ai-mode-badge ai-mode-${res.mode}">${res.mode}</span>
      <span class="muted small">${escapeHtml(res.provider)} · ${escapeHtml(res.model)} · ${res.duration_ms}ms</span>
    </div>
    <div class="ai-text">${safeText}</div>
    <details class="ai-sources">
      <summary class="muted small">${res.sources.length} source${res.sources.length === 1 ? "" : "s"}</summary>
      <ol class="ai-source-list">
        ${res.sources.map((s) => `
          <li>
            <span class="src-num">[${s.index}]</span>
            <span class="src-title">${escapeHtml(s.title || "(untitled)")}</span>
            ${s.ref ? `<span class="src-ref">${escapeHtml(s.ref)}</span>` : ""}
          </li>
        `).join("")}
      </ol>
    </details>
  `;
  attachCitationHandlers(res.sources);
}

function renderAIError(err) {
  let body = `AI request failed: ${escapeHtml(err.message || "unknown error")}`;
  if (err.status === 503) {
    body = `${escapeHtml(err.message)}<br><br>
      To fix:<br>
      • Pull the local model: <code>docker compose exec ollama ollama pull qwen2.5:1.5b</code><br>
      • Or for cloud models: <code>docker compose exec -it ollama ollama signin</code><br>
      • Verify env var <code>OLLAMA_MODEL</code> matches what's available.`;
  } else if (err.status === 429) {
    body = `${escapeHtml(err.message)} — wait a moment and try again.`;
  }
  aiOutput.innerHTML = `<div class="ai-error">${body}</div>`;
}

function renderTextWithCitations(text, sources) {
  // 1) escape everything first
  let html = escapeHtml(text);
  // 2) make [N] clickable
  html = html.replace(/\[(\d+)\]/g, (m, n) => {
    const idx = parseInt(n, 10);
    if (idx < 1 || idx > sources.length) return m;
    const title = sources[idx - 1].title || "";
    return `<span class="cite" data-index="${idx}" title="${escapeAttr(title)}">[${idx}]</span>`;
  });
  // 3) very light markdown: ## headers, - bullets, blank-line paragraphs
  html = html
    .replace(/^## (.+)$/gm, "<h3>$1</h3>")
    .replace(/(?:^|\n)- (.+?)(?=\n[^-]|\n*$)/gs, (m, item) => `\n<li>${item}</li>`)
    .replace(/(<li>[\s\S]+?<\/li>(?:\s*<li>[\s\S]+?<\/li>)*)/g, "<ul>$1</ul>")
    .replace(/\n{2,}/g, "<br><br>");
  return html;
}

function attachCitationHandlers(sources) {
  document.querySelectorAll(".ai-text .cite").forEach((el) => {
    el.addEventListener("click", () => {
      const idx = parseInt(el.dataset.index, 10);
      const card = resultList.children[idx - 1];
      if (!card) return;
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      card.classList.add("flash");
      setTimeout(() => card.classList.remove("flash"), 1400);
    });
  });
}

function escapeAttr(s) {
  return String(s).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// ============================================================
// Recent searches (chips below the search bar)
// ============================================================
const recentRow = $("#recent-row");

async function loadRecent() {
  try {
    const res = await api.get("/queries/");
    renderRecent(res.results || []);
  } catch {
    /* silently ignore — history is non-critical */
  }
}

function renderRecent(items) {
  recentRow.innerHTML = "";
  if (!items.length) {
    recentRow.classList.add("hidden");
    return;
  }
  recentRow.classList.remove("hidden");

  const label = document.createElement("span");
  label.className = "muted small recent-label";
  label.textContent = "Recent:";
  recentRow.appendChild(label);

  for (const q of items.slice(0, 12)) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `recent-chip recent-${q.kind}`;
    chip.title = `${q.kind} · ${q.result_count} result${q.result_count === 1 ? "" : "s"} · ${formatRelative(q.created_at)}`;
    const icon = document.createElement("span");
    icon.className = "recent-icon";
    icon.textContent = q.kind === "web" ? "🌐" : "⌖";
    const text = document.createElement("span");
    text.className = "recent-text";
    text.textContent = truncate(q.query, 32);
    chip.appendChild(icon);
    chip.appendChild(text);
    chip.addEventListener("click", () => runRecentQuery(q.query, q.kind));
    recentRow.appendChild(chip);
  }

  const clearBtn = document.createElement("button");
  clearBtn.type = "button";
  clearBtn.className = "btn btn-ghost btn-xs recent-clear";
  clearBtn.textContent = "clear";
  clearBtn.title = "Delete all search history";
  clearBtn.addEventListener("click", clearRecent);
  recentRow.appendChild(clearBtn);
}

function runRecentQuery(query, kind) {
  // Switch tabs if needed
  const targetTab = document.querySelector(`.search-tab[data-mode="${kind}"]`);
  if (targetTab && !targetTab.classList.contains("active")) {
    targetTab.click();
  }
  searchInput.value = query;
  if (typeof searchForm.requestSubmit === "function") {
    searchForm.requestSubmit();
  } else {
    searchForm.dispatchEvent(new Event("submit", { cancelable: true }));
  }
}

async function clearRecent() {
  if (!confirm("Clear all search history?")) return;
  try {
    await api.del("/queries/");
    toast("Search history cleared.", "success");
    loadRecent();
  } catch (err) {
    toast(`Could not clear history: ${err.message}`, "error");
  }
}

function formatRelative(iso) {
  const ms = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return "just now";
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

// ----- Boot -----
(async () => {
  await fetchUser();
  await loadDocuments();
  loadRecent();
  rt.connect();
})();
