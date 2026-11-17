// Shared login helpers for every L-Lawliet page.
// The token lives in sessionStorage, so it is cleared when the tab closes.
// The server re-checks the token and role on every request; nothing here is trusted for security.
(function () {
  const KEY = "lawliet_auth";

  function getAuth() {
    try { return JSON.parse(sessionStorage.getItem(KEY)) || null; } catch { return null; }
  }
  function setAuth(auth) { sessionStorage.setItem(KEY, JSON.stringify(auth)); applyTheme(); }
  function signOut() { sessionStorage.removeItem(KEY); applyTheme(); }

  // Save a login result ({token, user: {...}}) from login, sign-up, Google or a password change.
  function saveSession(data) {
    const u = data.user || {};
    setAuth({
      token: data.token,
      id: u.id,
      username: u.username || data.username,
      role: u.role || data.role,
      display_name: u.display_name || null,
      theme: u.theme || "dark",
      accent: u.accent || "gold",
      has_password: u.has_password !== false,
    });
  }

  // Keep the stored copy of the profile in step after the user changes their settings.
  function updateUser(profile) {
    const auth = getAuth();
    if (!auth) return;
    setAuth({ ...auth, display_name: profile.display_name, theme: profile.theme, accent: profile.accent });
  }

  // Theme and accent colour from the user's settings; guests get the default dark + gold.
  function applyTheme() {
    const auth = getAuth();
    const root = document.documentElement;
    const theme = auth && auth.theme === "light" ? "light" : null;
    const accent = auth && ["blue", "green", "rose"].includes(auth.accent) ? auth.accent : null;
    theme ? root.setAttribute("data-theme", theme) : root.removeAttribute("data-theme");
    accent ? root.setAttribute("data-accent", accent) : root.removeAttribute("data-accent");
  }
  applyTheme();

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // fetch() with the token attached. A 401 while logged in means the token expired
  // or was rejected, so the user is sent back to the login screen.
  async function apiFetch(url, options = {}) {
    const auth = getAuth();
    const headers = { ...(options.headers || {}) };
    if (auth && auth.token) headers["Authorization"] = `Bearer ${auth.token}`;
    if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";

    const res = await fetch(url, { ...options, headers });
    if (res.status === 401 && auth) {
      signOut();
      window.location.href = "login.html?expired=1";
      throw new Error("Login expired");
    }
    return res;
  }

  // Readable message from a FastAPI error body ({detail: "..."} or {detail: [{loc, msg}]}).
  async function errorMessage(res) {
    try {
      const body = await res.json();
      if (typeof body.detail === "string") return body.detail;
      if (Array.isArray(body.detail)) {
        // Pydantic prefixes custom rule messages with "Value error, "; the rule text alone reads better.
        return body.detail.map(e => {
          const msg = String(e.msg || "").replace(/^Value error, /, "");
          const field = (e.loc || []).slice(1).join(".");
          return field && e.type !== "value_error" ? `${field}: ${msg}` : msg;
        }).join("; ");
      }
    } catch { /* fall through */ }
    return `Request failed (HTTP ${res.status})`;
  }

  // Turn the "Sign In" button on every page into Sign In / name (links to Settings) + Sign Out.
  function renderNav() {
    const btn = document.querySelector(".btn-signin");
    if (!btn) return;
    const auth = getAuth();
    if (!auth) {
      btn.textContent = "Sign In";
      btn.onclick = () => { window.location.href = "login.html"; };
      return;
    }
    const wrap = document.createElement("div");
    wrap.style.cssText = "display:flex;align-items:center;gap:12px;";
    wrap.innerHTML = `
      <a href="settings.html" title="Profile and settings" style="color: var(--text-muted); font-size: 0.9rem; text-decoration: none;">${escapeHtml(auth.display_name || auth.username)} &#9881;</a>
      ${auth.role === "admin" ? '<a href="admin.html" style="color: var(--accent-gold); font-size: 0.9rem;">Admin</a>' : ""}
    `;
    const out = btn.cloneNode(false);
    out.textContent = "Sign Out";
    out.onclick = () => { signOut(); window.location.href = "login.html"; };
    wrap.appendChild(out);
    btn.replaceWith(wrap);
  }

  window.LawlietAuth = {
    getAuth, setAuth, saveSession, updateUser, signOut, applyTheme, apiFetch, escapeHtml, errorMessage,
  };
  document.addEventListener("DOMContentLoaded", renderNav);
})();
