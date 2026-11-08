// Shared login helpers for every L-Lawliet page.
// The token lives in sessionStorage, so it is cleared when the tab closes.
// The server re-checks the token and role on every request; nothing here is trusted for security.
(function () {
  const KEY = "lawliet_auth";

  function getAuth() {
    try { return JSON.parse(sessionStorage.getItem(KEY)) || null; } catch { return null; }
  }
  function setAuth(auth) { sessionStorage.setItem(KEY, JSON.stringify(auth)); }
  function signOut() { sessionStorage.removeItem(KEY); }

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
        return body.detail.map(e => `${(e.loc || []).slice(1).join(".") || "body"}: ${e.msg}`).join("; ");
      }
    } catch { /* fall through */ }
    return `Request failed (HTTP ${res.status})`;
  }

  // Turn the "Sign In" button on every page into Sign In / username + Sign Out.
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
      <span style="color: var(--text-muted); font-size: 0.9rem;">${escapeHtml(auth.username)}</span>
      ${auth.role === "admin" ? '<a href="admin.html" style="color: var(--accent-gold); font-size: 0.9rem;">Admin</a>' : ""}
    `;
    const out = btn.cloneNode(false);
    out.textContent = "Sign Out";
    out.onclick = () => { signOut(); window.location.href = "login.html"; };
    wrap.appendChild(out);
    btn.replaceWith(wrap);
  }

  window.LawlietAuth = { getAuth, setAuth, signOut, apiFetch, escapeHtml, errorMessage };
  document.addEventListener("DOMContentLoaded", renderNav);
})();
