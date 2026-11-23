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
      btn.classList.add("nav-auth");
      btn.textContent = "Sign In";
      btn.onclick = () => { window.location.href = "login.html"; };
      return;
    }
    const wrap = document.createElement("div");
    wrap.className = "nav-auth";
    wrap.style.cssText = "display:flex;align-items:center;gap:12px;";
    wrap.innerHTML = `
      <a href="profile.html" class="nav-item" title="My profile, saved laws and suggestions" style="color: var(--text-muted); font-size: 0.9rem; text-decoration: none;"><span class="nav-label">My profile</span><span class="nav-name">${escapeHtml(auth.display_name || auth.username)}</span></a>
      <a href="settings.html" class="nav-item" title="Settings" aria-label="Settings" style="color: var(--text-muted); font-size: 1rem; text-decoration: none;"><span class="nav-label">Settings</span><span class="nav-icon">Settings</span></a>
      ${auth.role === "admin" ? '<a href="admin.html" class="nav-item" style="color: var(--accent-gold); font-size: 0.9rem;"><span class="nav-label">Admin dashboard</span><span class="nav-name">Admin</span></a>' : ""}
    `;
    const out = btn.cloneNode(false);
    out.textContent = "Sign Out";
    out.onclick = () => { signOut(); window.location.href = "login.html"; };
    wrap.appendChild(out);
    btn.replaceWith(wrap);
  }

  // Phones and small tablets: a hamburger button shows and hides the links and the
  // sign-in area (see the max-width: 900px rules in style.css). Desktop is unchanged.
  function setUpNavToggle() {
    const nav = document.querySelector(".navbar");
    const links = nav && nav.querySelector(".nav-links");
    if (!nav || !links || nav.querySelector(".nav-toggle")) return;
    links.id = links.id || "navLinks";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "nav-toggle";
    toggle.setAttribute("aria-controls", links.id);
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Open menu");
    toggle.innerHTML = '<span></span><span></span><span></span>';
    nav.querySelector(".logo").after(toggle);

    function setOpen(open) {
      nav.classList.toggle("nav-open", open);
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    }
    toggle.addEventListener("click", () => setOpen(!nav.classList.contains("nav-open")));
    links.addEventListener("click", ev => { if (ev.target.closest("a")) setOpen(false); });
    document.addEventListener("keydown", ev => { if (ev.key === "Escape") setOpen(false); });
    window.matchMedia("(min-width: 901px)").addEventListener("change", ev => { if (ev.matches) setOpen(false); });
  }

  window.LawlietAuth = {
    getAuth, setAuth, saveSession, updateUser, signOut, applyTheme, apiFetch, escapeHtml, errorMessage,
  };
  document.addEventListener("DOMContentLoaded", () => { renderNav(); setUpNavToggle(); });
})();
