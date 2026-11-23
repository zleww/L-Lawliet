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
      <span class="click-more">Read more</span>
      ${law.rating_count ? `<span class="card-rating" title="Average rating">★ ${e(law.rating_avg)} (${e(law.rating_count)})</span>` : ""}
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

  const REPORT_REASONS = [["spam", "Spam"], ["offensive", "Offensive"], ["wrong_info", "Wrong information"], ["other", "Other"]];

  // Saved / rating bar under the title. Guests see the average and a log-in link.
  function engageBar(law, auth) {
    const avg = law.rating_count ? `${e(law.rating_avg)} / 5` : "No ratings yet";
    const count = law.rating_count ? `(${e(law.rating_count)} rating${law.rating_count === 1 ? "" : "s"})` : "";
    const stars = auth
      ? `<span class="rate-stars" role="group" aria-label="Your rating">${[1, 2, 3, 4, 5].map(i =>
          `<button type="button" class="star ${law.my_rating && i <= law.my_rating ? "on" : ""}" data-rate="${i}" aria-label="Rate ${i} out of 5">★</button>`).join("")}</span>
         ${law.my_rating ? '<button type="button" class="link-btn" data-unrate>Remove my rating</button>' : '<span class="muted-small">Tap a star to rate</span>'}`
      : '<a href="login.html" class="link-btn">Log in to rate or save</a>';
    return `
      <div class="law-engage">
        <div class="law-rating"><strong>★ ${avg}</strong> <span class="muted-small">${count}</span> ${stars}</div>
        ${auth ? `<button type="button" class="save-btn ${law.saved ? "on" : ""}" data-save aria-pressed="${law.saved ? "true" : "false"}">${law.saved ? "Saved" : "Save law"}</button>` : ""}
      </div>
      <p class="engage-error form-error" role="alert"></p>`;
  }

  function noteHtml(n, auth) {
    const mine = auth && auth.id != null && n.user_id === auth.id;
    const author = auth && n.user_id
      ? `<a class="note-author" href="profile.html?id=${encodeURIComponent(n.user_id)}">${e(n.user_name)}</a>`
      : `<strong>${e(n.user_name)}</strong>`;
    const helpful = auth && !mine
      ? `<button type="button" class="helpful-btn ${n.voted_by_me ? "on" : ""}" data-vote aria-pressed="${n.voted_by_me ? "true" : "false"}" title="Mark as helpful">Helpful ${e(n.helpful_count || 0)}</button>`
      : `<span class="helpful-count" title="Marked helpful">Helpful ${e(n.helpful_count || 0)}</span>`;
    const actions = [];
    if (mine) actions.push('<button type="button" class="note-edit-btn">Edit</button>');
    if (mine || (auth && auth.role === "admin")) actions.push('<button type="button" class="note-delete-btn">Delete</button>');
    if (auth && !mine) actions.push('<button type="button" class="note-report-btn">Report</button>');
    return `
      <div class="comment-bubble" style="margin-bottom: 10px;" data-note-id="${e(n.id)}">
        <span>${author}: <span class="note-text">${e(n.comment)}</span></span>
        ${n.edited_at ? '<span class="note-edited">(edited)</span>' : ""}
        <div class="note-footer">${helpful}${actions.length ? `<span class="note-actions">${actions.join("")}</span>` : ""}</div>
      </div>`;
  }

  function openModal(law, modal, modalBody) {
    const auth = getAuth();
    renderModal(law, modal, modalBody);
    // Logged in: reload the law so the pop-up shows your own state (saved, rating, votes).
    if (auth && !law._fresh) {
      apiFetch(`/api/v1/laws/${encodeURIComponent(law.id)}`)
        .then(res => (res.ok ? res.json() : null))
        .then(fresh => {
          if (!fresh || modal.classList.contains("hidden")) return;
          Object.assign(law, fresh, { _fresh: true });
          renderModal(law, modal, modalBody);
        })
        .catch(err => console.error("Failed to refresh the law:", err));
    }
  }

  function renderModal(law, modal, modalBody) {
    const notes = Array.isArray(law.user_notes) ? law.user_notes : [];
    const fine = law.min_fine_php ? `₱${Number(law.min_fine_php).toLocaleString()}` : "None / Discretionary";
    const safeUrl = /^https:\/\//.test(law.source_url || "") ? law.source_url : "#";
    const auth = getAuth();
    const reload = () => { law._fresh = false; openModal(law, modal, modalBody); };

    modalBody.innerHTML = `
      <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px;">
        <span style="background: rgba(200, 155, 83, 0.15); color: var(--accent-gold); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem; font-weight: 600;">${e(law.category)} (${e(law.year)})</span>
        <span style="background: var(--chip-bg); color: var(--text-main); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem; border: 1px solid var(--border-color);">Status: <strong>${e(law.status)}</strong></span>
        <span style="background: var(--chip-bg); color: var(--text-muted); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem;">${e(law.reading_time_minutes)} min read</span>
        <span style="background: rgba(200, 155, 83, 0.1); color: var(--accent-gold); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem;">Impact ${e(law.importance_rating)} of 5</span>
      </div>

      <h2 style="color: var(--accent-gold); margin-bottom: 4px;">${e(law.ra_number)}: ${e(law.plain_title)}</h2>
      <p class="official-title" style="color: var(--text-muted); font-style: italic; margin-bottom: 20px; font-size: 0.95rem;">
        "${e(law.official_title)}" &bull; <span style="font-style: normal; font-size: 0.85rem;">System ID #${e(law.id)}</span>
      </p>

      ${engageBar(law, auth)}

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; background: var(--bg-inset); border: 1px solid var(--border-color); padding: 15px; border-radius: 8px; margin-bottom: 25px;">
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
        <a href="${e(safeUrl)}" target="_blank" rel="noopener noreferrer" style="color: var(--accent-gold); text-decoration: underline;">Read the full text in the Official Gazette</a>
      </div>

      <hr style="border: 0; border-top: 1px solid var(--border-color); margin: 25px 0;">

      <h3 style="color: var(--text-main); margin-bottom: 15px;">Community Notes & Tips</h3>
      <div id="commentsList">
        ${notes.length
          ? notes.map(n => noteHtml(n, auth)).join("")
          : '<p style="color: var(--text-muted); font-size: 0.9rem;">No notes yet. Be the first to add a practical tip!</p>'}
      </div>

      ${auth
        ? `<div class="comment-form">
             <h4 style="color: var(--text-main); font-size: 1rem; margin-bottom: 10px;">Add a Note or Tip</h4>
             <input type="text" id="userNameInput" maxlength="100" value="${e(auth.display_name || auth.username)}" placeholder="Display name">
             <textarea id="userCommentInput" maxlength="1000" placeholder="Share a practical tip or explanation..." rows="3"></textarea>
             <button id="submitCommentBtn">Post Note</button>
             <p id="commentError" style="color: #e57373; font-size: 0.85rem; margin-top: 8px;"></p>
           </div>`
        : `<p style="color: var(--text-muted); font-size: 0.9rem;"><a href="login.html" style="color: var(--accent-gold);">Log in</a> to add a note.</p>`}
    `;

    modal.classList.remove("hidden");

    // Save / unsave, rate / remove rating. Each change reloads the law from the API.
    const engageError = modalBody.querySelector(".engage-error");
    async function engage(url, options) {
      engageError.textContent = "";
      try {
        const res = await apiFetch(url, options);
        if (!res.ok) { engageError.textContent = await errorMessage(res); return; }
        reload();
      } catch (err) {
        console.error(err);
        engageError.textContent = "Could not reach the server. Please try again.";
      }
    }
    const saveBtn = modalBody.querySelector("[data-save]");
    if (saveBtn) saveBtn.addEventListener("click", () =>
      engage(`/api/v1/laws/${encodeURIComponent(law.id)}/save`, { method: law.saved ? "DELETE" : "POST" }));
    modalBody.querySelectorAll("[data-rate]").forEach(btn => btn.addEventListener("click", () =>
      engage(`/api/v1/laws/${encodeURIComponent(law.id)}/rating`, {
        method: "PUT", body: JSON.stringify({ rating: Number(btn.dataset.rate) }),
      })));
    const unrate = modalBody.querySelector("[data-unrate]");
    if (unrate) unrate.addEventListener("click", () =>
      engage(`/api/v1/laws/${encodeURIComponent(law.id)}/rating`, { method: "DELETE" }));

    // Helpful votes: tap to add, tap again to remove.
    modalBody.querySelectorAll("[data-vote]").forEach(btn => btn.addEventListener("click", async () => {
      const noteId = Number(btn.closest(".comment-bubble").dataset.noteId);
      const note = notes.find(n => n.id === noteId);
      btn.disabled = true;
      try {
        const res = await apiFetch(`/api/v1/comments/${encodeURIComponent(noteId)}/vote`,
          { method: note && note.voted_by_me ? "DELETE" : "POST" });
        if (!res.ok) { alert(await errorMessage(res)); return; }
        reload();
      } finally {
        btn.disabled = false;
      }
    }));

    // Report someone else's note to the admins.
    modalBody.querySelectorAll(".note-report-btn").forEach(btn => btn.addEventListener("click", () => {
      const bubble = btn.closest(".comment-bubble");
      const noteId = Number(bubble.dataset.noteId);
      if (bubble.querySelector(".report-form")) return;
      bubble.insertAdjacentHTML("beforeend", `
        <div class="report-form note-edit">
          <label for="reportReason${noteId}" style="font-size: 0.8rem; color: var(--text-muted);">Why are you reporting this note?</label>
          <select id="reportReason${noteId}">${REPORT_REASONS.map(([v, label]) => `<option value="${v}">${label}</option>`).join("")}</select>
          <textarea rows="2" maxlength="500" placeholder="Details (optional)"></textarea>
          <button type="button" class="report-send">Send report</button>
          <button type="button" class="report-cancel btn-outline">Cancel</button>
          <p class="form-error report-error"></p>
        </div>`);
      const form = bubble.querySelector(".report-form");
      form.querySelector(".report-cancel").addEventListener("click", () => form.remove());
      form.querySelector(".report-send").addEventListener("click", async (ev) => {
        const errorBox = form.querySelector(".report-error");
        ev.target.disabled = true;
        try {
          const details = form.querySelector("textarea").value.trim();
          const res = await apiFetch(`/api/v1/comments/${encodeURIComponent(noteId)}/report`, {
            method: "POST",
            body: JSON.stringify({ reason: form.querySelector("select").value, ...(details ? { details } : {}) }),
          });
          if (!res.ok) { errorBox.textContent = await errorMessage(res); return; }
          form.innerHTML = '<p class="form-ok">Thanks, an admin will review this note.</p>';
        } catch (err) {
          console.error(err);
          errorBox.textContent = "Could not reach the server. Please try again.";
        } finally {
          ev.target.disabled = false;
        }
      });
    }));

    // Edit one of your own notes in place. The server checks again that it is yours.
    modalBody.querySelectorAll(".note-edit-btn").forEach(btn => btn.addEventListener("click", () => {
      const bubble = btn.closest(".comment-bubble");
      const noteId = Number(bubble.dataset.noteId);
      const note = notes.find(n => n.id === noteId);
      bubble.innerHTML = `
        <div class="note-edit">
          <label for="editNote${noteId}" style="font-size: 0.8rem; color: var(--text-muted);">Edit your note</label>
          <textarea id="editNote${noteId}" rows="3" maxlength="1000"></textarea>
          <button type="button" class="note-save">Save</button>
          <button type="button" class="note-cancel btn-outline">Cancel</button>
          <p class="form-error note-error"></p>
        </div>`;
      const box = bubble.querySelector("textarea");
      box.value = note ? note.comment : "";
      box.focus();
      bubble.querySelector(".note-cancel").addEventListener("click", () => openModal(law, modal, modalBody));
      bubble.querySelector(".note-save").addEventListener("click", async (ev) => {
        const errorBox = bubble.querySelector(".note-error");
        const text = box.value.trim();
        if (!text) { errorBox.textContent = "A note cannot be empty."; return; }
        ev.target.disabled = true;
        try {
          const res = await apiFetch(`/api/v1/comments/${encodeURIComponent(noteId)}`, {
            method: "PATCH",
            body: JSON.stringify({ comment: text }),
          });
          if (!res.ok) { errorBox.textContent = await errorMessage(res); return; }
          law.user_notes = (await res.json()).comments;
          openModal(law, modal, modalBody);
        } catch (err) {
          console.error("Failed to edit note:", err);
          errorBox.textContent = "Sorry, your change couldn't be saved. Please try again.";
        } finally {
          ev.target.disabled = false;
        }
      });
    }));

    // Delete your own note (admins can delete any). The server checks again.
    modalBody.querySelectorAll(".note-delete-btn").forEach(btn => btn.addEventListener("click", async () => {
      const noteId = Number(btn.closest(".comment-bubble").dataset.noteId);
      if (!confirm("Delete this note? This cannot be undone.")) return;
      btn.disabled = true;
      try {
        const res = await apiFetch(`/api/v1/comments/${encodeURIComponent(noteId)}`, { method: "DELETE" });
        if (res.status !== 204) { alert(await errorMessage(res)); return; }
        law.user_notes = notes.filter(n => n.id !== noteId);
        openModal(law, modal, modalBody);
      } catch (err) {
        console.error("Failed to delete note:", err);
        alert("Sorry, the note couldn't be deleted. Please try again.");
      } finally {
        btn.disabled = false;
      }
    }));

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
