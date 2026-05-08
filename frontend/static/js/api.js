// Tiny fetch wrapper that injects the JWT, refreshes on 401, and surfaces
// useful error info to the caller.
const BASE = (window.NEUROSEEK_CONFIG && window.NEUROSEEK_CONFIG.apiBase) || "/api/v1";

class ApiError extends Error {
  constructor(status, detail) {
    const msg = typeof detail === "string"
      ? detail
      : detail && (detail.detail || detail.error)
        ? (detail.detail || detail.error)
        : JSON.stringify(detail);
    super(msg);
    this.status = status;
    this.detail = detail;
  }
}

const Tokens = {
  get access() { return localStorage.getItem("access"); },
  get refresh() { return localStorage.getItem("refresh"); },
  set(access, refresh) {
    if (access) localStorage.setItem("access", access);
    if (refresh) localStorage.setItem("refresh", refresh);
  },
  clear() {
    localStorage.removeItem("access");
    localStorage.removeItem("refresh");
  },
};

let refreshing = null;

async function tryRefresh() {
  if (refreshing) return refreshing;
  const refresh = Tokens.refresh;
  if (!refresh) return false;
  refreshing = (async () => {
    try {
      const res = await fetch(`${BASE}/auth/refresh/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      Tokens.set(data.access, data.refresh);
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

async function request(method, path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (!opts.skipAuth) {
    const t = Tokens.access;
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  let body = opts.body;
  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  const url = path.startsWith("http") ? path : `${BASE}${path}`;
  let res = await fetch(url, { method, headers, body });

  if (res.status === 401 && !opts.skipAuth && !opts._retried) {
    const ok = await tryRefresh();
    if (ok) return request(method, path, { ...opts, _retried: true });
    Tokens.clear();
    throw new ApiError(401, "Authentication required");
  }
  if (!res.ok) {
    let detail;
    try { detail = await res.json(); } catch { detail = await res.text(); }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

export const api = {
  get: (p, o) => request("GET", p, o),
  post: (p, body, o) => request("POST", p, { ...(o || {}), body }),
  put: (p, body, o) => request("PUT", p, { ...(o || {}), body }),
  patch: (p, body, o) => request("PATCH", p, { ...(o || {}), body }),
  del: (p, o) => request("DELETE", p, o),
  raw: request,
  get tokens() { return Tokens; },
  logout: () => Tokens.clear(),
  isAuthed: () => !!Tokens.access,
};

export { ApiError };
