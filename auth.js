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
    const name = auth.display_name || auth.username || "Me";
    const here = (page) => (location.pathname.endsWith("/" + page) ? ' aria-current="page"' : "");
    const wrap = document.createElement("div");
    wrap.className = "nav-auth";
    wrap.innerHTML = `
      ${auth.role === "admin" ? `<a href="admin.html" class="nav-item nav-btn nav-admin" title="Admin dashboard"${here("admin.html")}>${ICONS.shield}<span class="nav-btn-text">Admin</span></a>` : ""}
      <a href="settings.html" class="nav-item nav-btn nav-icon-btn" title="Settings" aria-label="Settings"${here("settings.html")}>${ICONS.gear}<span class="nav-btn-text nav-label">Settings</span></a>
      <a href="profile.html" class="nav-item nav-btn nav-profile" title="My profile, saved laws and suggestions"${here("profile.html")}>
        <span class="nav-avatar" aria-hidden="true">${escapeHtml(name.trim().charAt(0).toUpperCase() || "?")}</span>
        <span class="nav-btn-text"><span class="nav-label">My profile · </span>${escapeHtml(name)}</span>
      </a>
    `;
    const out = btn.cloneNode(false);
    out.classList.add("nav-signout");
    out.innerHTML = `${ICONS.logout}<span>Sign Out</span>`;
    out.onclick = () => { signOut(); window.location.href = "login.html"; };
    wrap.appendChild(out);
    btn.replaceWith(wrap);
  }

  // Small line icons for the account buttons (stroke uses the text colour).
  const ICON = (d) => `<svg class="nav-svg" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  const ICONS = {
    gear: ICON('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'),
    shield: ICON('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'),
    logout: ICON('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>'),
  };

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

;// Show / hide toggle on every password field
(function () {
  var CSS =
    ".pw-wrap{position:relative;display:block}" +
    ".pw-wrap>input{padding-right:4.5rem!important;margin-top:0!important;margin-bottom:0!important}" +
    ".pw-wrap>button.pw-toggle{position:absolute!important;top:50%!important;right:.35rem!important;left:auto!important;" +
    "transform:translateY(-50%)!important;width:auto!important;min-width:0!important;height:auto!important;margin:0!important;" +
    "border:0!important;background:transparent!important;box-shadow:none!important;color:inherit!important;opacity:.8;" +
    "font:inherit;font-size:.8125rem!important;font-weight:600!important;line-height:1!important;letter-spacing:0!important;" +
    "text-transform:none!important;padding:.45rem .55rem!important;border-radius:.4rem!important;cursor:pointer}" +
    ".pw-wrap>button.pw-toggle:hover{opacity:1;background:rgba(127,127,127,.15)!important}" +
    ".pw-wrap>button.pw-toggle:focus-visible{outline:2px solid currentColor;outline-offset:1px;opacity:1}";

  function addToggles() {
    var inputs = document.querySelectorAll('input[type="password"]:not([data-pw-toggle])');
    if (!inputs.length) return;
    if (!document.getElementById("pw-toggle-css")) {
      var style = document.createElement("style");
      style.id = "pw-toggle-css";
      style.textContent = CSS;
      document.head.appendChild(style);
    }
    inputs.forEach(function (input) {
      input.setAttribute("data-pw-toggle", "");
      var cs = getComputedStyle(input);
      var wrap = document.createElement("span");
      wrap.className = "pw-wrap";
      wrap.style.marginTop = cs.marginTop;
      wrap.style.marginBottom = cs.marginBottom;
      wrap.style.color = cs.color;
      input.parentNode.insertBefore(wrap, input);
      wrap.appendChild(input);

      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "pw-toggle";
      btn.textContent = "Show";
      btn.setAttribute("aria-label", "Show password");
      btn.setAttribute("aria-pressed", "false");
      if (input.id) btn.setAttribute("aria-controls", input.id);
      btn.addEventListener("click", function () {
        var show = input.type === "password";
        input.type = show ? "text" : "password";
        btn.textContent = show ? "Hide" : "Show";
        btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
        btn.setAttribute("aria-pressed", String(show));
        input.focus();
      });
      wrap.appendChild(btn);
      // Hide it again on submit so the browser's password manager sees a password field
      if (input.form) input.form.addEventListener("submit", function () {
        input.type = "password";
        btn.textContent = "Show";
        btn.setAttribute("aria-label", "Show password");
        btn.setAttribute("aria-pressed", "false");
      });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", addToggles);
  else addToggles();
})();
