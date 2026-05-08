// Login / register page logic.
import { api, ApiError } from "./api.js";

// If already logged in, skip the login screen
if (api.isAuthed()) {
  // verify the token is still good before redirecting
  api.get("/auth/me/")
    .then(() => { window.location.href = "/app/"; })
    .catch(() => api.logout());
}

// Honor ?tab=register so the landing-page "Get started" button lands on the
// register form by default.
const initialTab = new URLSearchParams(window.location.search).get("tab");

const tabs = document.querySelectorAll(".tab");
const forms = {
  login: document.querySelector("#login-form"),
  register: document.querySelector("#register-form"),
};
const errorEl = document.querySelector("#auth-error");

function activateTab(name) {
  tabs.forEach((t) => {
    const active = t.dataset.tab === name;
    t.classList.toggle("active", active);
    t.setAttribute("aria-selected", active ? "true" : "false");
  });
  for (const [key, form] of Object.entries(forms)) {
    form.classList.toggle("hidden", key !== name);
  }
  hideError();
}

tabs.forEach((t) => {
  t.addEventListener("click", () => activateTab(t.dataset.tab));
});

if (initialTab && forms[initialTab]) {
  activateTab(initialTab);
}

function showError(msg) {
  errorEl.textContent = msg;
  errorEl.classList.remove("hidden");
}
function hideError() {
  errorEl.textContent = "";
  errorEl.classList.add("hidden");
}

function setLoading(form, on) {
  const btn = form.querySelector("button[type=submit]");
  if (!btn) return;
  btn.disabled = !!on;
  btn.classList.toggle("loading", !!on);
}

forms.login.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();
  const data = new FormData(forms.login);
  setLoading(forms.login, true);
  try {
    const res = await api.post("/auth/login/", {
      email: data.get("email"),
      password: data.get("password"),
    }, { skipAuth: true });
    api.tokens.set(res.access, res.refresh);
    window.location.href = "/app/";
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      showError("Invalid email or password.");
    } else {
      showError(err.message || "Sign-in failed.");
    }
  } finally {
    setLoading(forms.login, false);
  }
});

forms.register.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();
  const data = new FormData(forms.register);
  setLoading(forms.register, true);
  try {
    const payload = {
      email: data.get("email"),
      password: data.get("password"),
    };
    const fullName = (data.get("full_name") || "").trim();
    if (fullName) payload.full_name = fullName;

    await api.post("/auth/register/", payload, { skipAuth: true });

    // Auto-login after register
    const tokens = await api.post("/auth/login/", {
      email: payload.email,
      password: payload.password,
    }, { skipAuth: true });
    api.tokens.set(tokens.access, tokens.refresh);
    window.location.href = "/app/";
  } catch (err) {
    if (err instanceof ApiError && err.detail && typeof err.detail === "object") {
      // DRF returns field errors like {"email": ["already exists"]}
      const messages = [];
      for (const [k, v] of Object.entries(err.detail)) {
        const list = Array.isArray(v) ? v : [v];
        list.forEach((m) => messages.push(`${k}: ${m}`));
      }
      showError(messages.join(" — ") || err.message);
    } else {
      showError(err.message || "Sign-up failed.");
    }
  } finally {
    setLoading(forms.register, false);
  }
});
