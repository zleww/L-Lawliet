// Law card and detail modal, shared by index.html and browse.html.
// Every law field is escaped before it goes into the page, because admins can now
// write law text through the API.
(function () {
  const { apiFetch, escapeHtml: e, getAuth, errorMessage } = window.LawlietAuth;

  function renderCard(law, onOpen) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
        <span class="badge" style="background: rgba(200, 155, 83, 0.15); color: var(--accent-gold); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem; font-weight: 600;">${e(law.category)}</span>
        <span style="color: var(--text-muted); font-size: 0.8rem;">${e(law.status)}</span>
      </div>
      <h3>${e(law.ra_number)}</h3>
      <h4>${e(law.plain_title)}</h4>
      <p class="summary">${e(law.tldr_summary)}</p>
      <span class="click-more">Click to view full details &rarr;</span>
    `;
    card.addEventListener("click", () => onOpen(law));
    return card;
  }

  function section(title, text) {
    return `
      <div class="detail-section" style="margin-bottom: 20px;">
        <h4 style="color: var(--accent-gold); margin-bottom: 5px;">${title}</h4>
        <p style="color: var(--text-main); line-height: 1.6;">${e(text)}</p>
      </div>`;
  }

  function meta(label, value, color = "var(--text-main)", extra = "") {
    return `
      <div ${extra}>
        <span style="color: var(--text-muted); font-size: 0.8rem; display: block;">${label}</span>
        <strong style="color: ${color}; font-size: 0.9rem;">${e(value)}</strong>
      </div>`;
  }

  function openModal(law, modal, modalBody) {
    const notes = Array.isArray(law.user_notes) ? law.user_notes : [];
    const fine = law.min_fine_php ? `₱${Number(law.min_fine_php).toLocaleString()}` : "None / Discretionary";
    const safeUrl = /^https:\/\//.test(law.source_url || "") ? law.source_url : "#";
    const auth = getAuth();

    modalBody.innerHTML = `
      <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px;">
        <span style="background: rgba(200, 155, 83, 0.15); color: var(--accent-gold); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem; font-weight: 600;">${e(law.category)} (${e(law.year)})</span>
        <span style="background: rgba(255, 255, 255, 0.08); color: var(--text-main); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem; border: 1px solid var(--border-color);">Status: <strong>${e(law.status)}</strong></span>
        <span style="background: rgba(255, 255, 255, 0.08); color: var(--text-muted); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem;">⏱️ ${e(law.reading_time_minutes)} min read</span>
        <span style="background: rgba(200, 155, 83, 0.1); color: var(--accent-gold); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem;">⭐ Impact: ${e(law.importance_rating)}/5</span>
      </div>

      <h2 style="color: var(--accent-gold); margin-bottom: 4px;">${e(law.ra_number)}: ${e(law.plain_title)}</h2>
      <p class="official-title" style="color: var(--text-muted); font-style: italic; margin-bottom: 20px; font-size: 0.95rem;">
        "${e(law.official_title)}" &bull; <span style="font-style: normal; font-size: 0.85rem;">System ID #${e(law.id)}</span>
      </p>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; background: rgba(6, 13, 20, 0.6); border: 1px solid var(--border-color); padding: 15px; border-radius: 8px; margin-bottom: 25px;">
        ${meta("Enacting President", law.enacting_president)}
        ${meta("Total Sections", `${law.total_sections} Sections`)}
        ${meta("Base Minimum Fine", fine, "var(--accent-gold)")}
        ${meta("Target Audience", law.target_audience, "var(--text-main)", 'style="grid-column: 1 / -1;"')}
      </div>

      ${section("Quick Summary (TL;DR)", law.tldr_summary)}
      ${section("Full Simplified Breakdown", law.full_breakdown)}
      ${section("Why It Matters", law.why_it_matters)}
      ${section("Example Scenario", law.example_scenario)}
      ${section("Penalties & Violations", law.penalties)}

      <div class="detail-section" style="margin-bottom: 20px;">
        <h4 style="color: var(--accent-gold); margin-bottom: 5px;">Official Source</h4>
        <a href="${e(safeUrl)}" target="_blank" rel="noopener noreferrer" style="color: var(--accent-gold); text-decoration: underline;">Read official gazette filing &rarr;</a>
      </div>

      <hr style="border: 0; border-top: 1px solid var(--border-color); margin: 25px 0;">

      <h3 style="color: var(--text-main); margin-bottom: 15px;">Community Notes & Tips</h3>
      <div id="commentsList">
        ${notes.length
          ? notes.map(n => `
              <div class="comment-bubble" style="margin-bottom: 10px;">
                <span><strong>${e(n.user_name)}:</strong> ${e(n.comment)}</span>
              </div>`).join("")
          : '<p style="color: var(--text-muted); font-size: 0.9rem;">No notes yet. Be the first to add a practical tip!</p>'}
      </div>

      ${auth
        ? `<div class="comment-form">
             <h4 style="color: var(--text-main); font-size: 1rem; margin-bottom: 10px;">Add a Note or Tip</h4>
             <input type="text" id="userNameInput" maxlength="100" value="${e(auth.username)}" placeholder="Display name">
             <textarea id="userCommentInput" maxlength="1000" placeholder="Share a practical tip or explanation..." rows="3"></textarea>
             <button id="submitCommentBtn">Post Note</button>
             <p id="commentError" style="color: #e57373; font-size: 0.85rem; margin-top: 8px;"></p>
           </div>`
        : `<p style="color: var(--text-muted); font-size: 0.9rem;"><a href="login.html" style="color: var(--accent-gold);">Log in</a> to add a note.</p>`}
    `;

    modal.classList.remove("hidden");

    const submitBtn = document.getElementById("submitCommentBtn");
    if (!submitBtn) return;
    submitBtn.addEventListener("click", async () => {
      const user_name = document.getElementById("userNameInput").value.trim();
      const comment = document.getElementById("userCommentInput").value.trim();
      const errorBox = document.getElementById("commentError");
      if (!user_name || !comment) { errorBox.textContent = "Name and note are both required."; return; }
      submitBtn.disabled = true;
      try {
        const res = await apiFetch(`/api/v1/laws/${encodeURIComponent(law.id)}/comments`, {
          method: "POST",
          body: JSON.stringify({ user_name, comment }),
        });
        if (!res.ok) { errorBox.textContent = await errorMessage(res); return; }
        const data = await res.json();
        law.user_notes = data.comments; // the list as saved in the database
        openModal(law, modal, modalBody);
      } catch (err) {
        console.error("Failed to post comment:", err);
        errorBox.textContent = "Sorry, your note couldn't be saved. Please try again.";
      } finally {
        submitBtn.disabled = false;
      }
    });
  }

  function wireModalClose(modal, closeBtn) {
    if (closeBtn) closeBtn.addEventListener("click", () => modal.classList.add("hidden"));
    window.addEventListener("click", ev => { if (ev.target === modal) modal.classList.add("hidden"); });
    window.addEventListener("keydown", ev => {
      if (ev.key === "Escape" && !modal.classList.contains("hidden")) modal.classList.add("hidden");
    });
  }

  // Guest notice, e.g. "Guest view: you can read the first 10 of 30 laws. Log in to see all."
  function accessBanner(data) {
    if (data.access !== "guest") return "";
    return `<p style="grid-column: 1/-1; background: rgba(200,155,83,0.12); border: 1px solid var(--accent-gold); color: var(--text-main); padding: 12px 16px; border-radius: 8px;">
      Guest view: you can read the first ${e(data.guest_limit)} of ${e(data.total)} laws. <a href="login.html" style="color: var(--accent-gold); font-weight: 600;">Log in to see all.</a>
    </p>`;
  }

  window.LawsUI = { renderCard, openModal, wireModalClose, accessBanner };
})();
