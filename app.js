document.addEventListener("DOMContentLoaded", () => {
  const lawsGrid = document.getElementById("lawsGrid");
  const searchInput = document.getElementById("searchInput");
  const searchSubmitBtn = document.getElementById("searchSubmitBtn");
  const popularTags = document.querySelectorAll(".tag-link");
  const featuredReadMoreBtn = document.getElementById("featuredReadMoreBtn");
  const modal = document.getElementById("lawModal");
  const modalBody = document.getElementById("modalBody");
  const closeModal = document.getElementById("closeModal");

  let allLaws = [];

  // 1. Fetch laws from your FastAPI backend
  async function fetchLaws() {
    try {
      const response = await fetch('/api/v1/laws')
      allLaws = await response.json();
      
      // Limit to first 5 laws on the home page
      const top5Laws = allLaws.slice(0, 5);
      displayLaws(top5Laws);
    } catch (error) {
      console.error("Error fetching laws:", error);
      lawsGrid.innerHTML = `<p style="color: var(--text-muted);">Failed to load laws from the backend.</p>`;
    }
  }

  // 2. Render laws into the grid
  function displayLaws(laws) {
    lawsGrid.innerHTML = "";
    
    if (laws.length === 0) {
      lawsGrid.innerHTML = `<p style="color: var(--text-muted);">No laws found matching your search.</p>`;
      return;
    }

    laws.forEach(law => {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `
        <span class="badge" style="background: rgba(200, 155, 83, 0.15); color: var(--accent-gold); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; display: inline-block; margin-bottom: 10px;">${law.category}</span>
        <h3 style="color: var(--accent-gold); margin-bottom: 5px;">${law.ra_number}</h3>
        <h4 style="color: var(--text-main); margin-bottom: 10px; font-size: 1.1rem;">${law.plain_title}</h4>
        <p class="summary" style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 15px;">${law.tldr_summary}</p>
        <span class="click-more" style="color: var(--accent-gold); font-size: 0.85rem; font-weight: bold;">Click to view full details &rarr;</span>
      `;
      
      card.addEventListener("click", () => openModal(law));
      lawsGrid.appendChild(card);
    });
  }

  // 3. Handle live search filtering & search submission button
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      const query = e.target.value.toLowerCase();
      const filtered = allLaws.slice(0, 5).filter(law => 
        law.ra_number.toLowerCase().includes(query) ||
        law.plain_title.toLowerCase().includes(query) ||
        law.official_title.toLowerCase().includes(query) ||
        law.tldr_summary.toLowerCase().includes(query) ||
        law.category.toLowerCase().includes(query)
      );
      displayLaws(filtered);
    });
  }

  if (searchSubmitBtn) {
    searchSubmitBtn.addEventListener("click", () => {
      const query = searchInput.value.trim();
      if (query) {
        // Redirect to browse page with search query parameter
        window.location.href = `browse.html?search=${encodeURIComponent(query)}`;
      } else {
        window.location.href = `browse.html`;
      }
    });
  }

  // 4. Handle Popular Tags Click -> Redirect to Browse Page with filter query
  popularTags.forEach(tag => {
    tag.style.cursor = "pointer";
    tag.addEventListener("click", () => {
      const searchTerm = tag.getAttribute("data-search");
      window.location.href = `browse.html?search=${encodeURIComponent(searchTerm)}`;
    });
  });

  // 5. Handle Featured Law "Read More" Button -> Open modal for RA 10175 (ID 1)
  if (featuredReadMoreBtn) {
    featuredReadMoreBtn.addEventListener("click", () => {
      // Find RA 10175 from our loaded dataset
      const ra10175 = allLaws.find(law => law.ra_number === "RA 10175") || allLaws[0];
      if (ra10175) {
        openModal(ra10175);
      }
    });
  }

// Move API_KEY declaration ABOVE any function calls
  const API_KEY = "student-api-key-123";

  // 6. Open Modal with full breakdown & comments (All 20 Identifiers)
  function openModal(law) {
    if (!law.user_notes) law.user_notes = [];
    
    const formattedFine = law.min_fine_php 
      ? `₱${Number(law.min_fine_php).toLocaleString()}` 
      : "None / Discretionary";

    modalBody.innerHTML = `
      <!-- Header Meta & Badges -->
      <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px;">
        <span style="background: rgba(200, 155, 83, 0.15); color: var(--accent-gold); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem; font-weight: 600;">
          ${law.category} (${law.year})
        </span>
        <span style="background: rgba(255, 255, 255, 0.08); color: var(--text-main); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem; border: 1px solid var(--border-color);">
          Status: <strong>${law.status}</strong>
        </span>
        <span style="background: rgba(255, 255, 255, 0.08); color: var(--text-muted); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem;">
          ⏱️ ${law.reading_time_minutes} min read
        </span>
        <span style="background: rgba(200, 155, 83, 0.1); color: var(--accent-gold); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem;">
          ⭐ Impact: ${law.importance_rating}/5
        </span>
      </div>

      <!-- Titles & ID -->
      <h2 style="color: var(--accent-gold); margin-bottom: 4px;">${law.ra_number}: ${law.plain_title}</h2>
      <p class="official-title" style="color: var(--text-muted); font-style: italic; margin-bottom: 20px; font-size: 0.95rem;">
        "${law.official_title}" &bull; <span style="font-style: normal; color: var(--text-muted); font-size: 0.85rem;">System ID #${law.id}</span>
      </p>

      <!-- Key Metadata Panel -->
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; background: rgba(6, 13, 20, 0.6); border: 1px solid var(--border-color); padding: 15px; border-radius: 8px; margin-bottom: 25px;">
        <div>
          <span style="color: var(--text-muted); font-size: 0.8rem; display: block;">Enacting President</span>
          <strong style="color: var(--text-main); font-size: 0.9rem;">${law.enacting_president}</strong>
        </div>
        <div>
          <span style="color: var(--text-muted); font-size: 0.8rem; display: block;">Total Sections</span>
          <strong style="color: var(--text-main); font-size: 0.9rem;">${law.total_sections} Sections</strong>
        </div>
        <div>
          <span style="color: var(--text-muted); font-size: 0.8rem; display: block;">Base Minimum Fine</span>
          <strong style="color: var(--accent-gold); font-size: 0.9rem;">${formattedFine}</strong>
        </div>
        <div style="grid-column: 1 / -1;">
          <span style="color: var(--text-muted); font-size: 0.8rem; display: block;">Target Audience</span>
          <strong style="color: var(--text-main); font-size: 0.9rem;">${law.target_audience}</strong>
        </div>
      </div>
      
      <!-- Core Explanations -->
      <div class="detail-section" style="margin-bottom: 20px;">
        <h4 style="color: var(--accent-gold); margin-bottom: 5px;">Quick Summary (TL;DR)</h4>
        <p style="color: var(--text-main); line-height: 1.6;">${law.tldr_summary}</p>
      </div>

      <div class="detail-section" style="margin-bottom: 20px;">
        <h4 style="color: var(--accent-gold); margin-bottom: 5px;">Full Simplified Breakdown</h4>
        <p style="color: var(--text-main); line-height: 1.6;">${law.full_breakdown}</p>
      </div>

      <div class="detail-section" style="margin-bottom: 20px;">
        <h4 style="color: var(--accent-gold); margin-bottom: 5px;">Why It Matters</h4>
        <p style="color: var(--text-main); line-height: 1.6;">${law.why_it_matters}</p>
      </div>

      <div class="detail-section" style="margin-bottom: 20px;">
        <h4 style="color: var(--accent-gold); margin-bottom: 5px;">Example Scenario</h4>
        <p style="color: var(--text-main); line-height: 1.6;">${law.example_scenario}</p>
      </div>

      <div class="detail-section" style="margin-bottom: 20px;">
        <h4 style="color: var(--accent-gold); margin-bottom: 5px;">Penalties & Violations</h4>
        <p style="color: var(--text-main); line-height: 1.6;">${law.penalties}</p>
      </div>

      <div class="detail-section" style="margin-bottom: 20px;">
        <h4 style="color: var(--accent-gold); margin-bottom: 5px;">Official Source</h4>
        <a href="${law.source_url}" target="_blank" rel="noopener noreferrer" style="color: var(--accent-gold); text-decoration: underline;">Read official gazette filing &rarr;</a>
      </div>

      <hr style="border: 0; border-top: 1px solid var(--border-color); margin: 25px 0;">

      <!-- Identifier 20: user_notes -->
      <h3 style="color: var(--text-main); margin-bottom: 15px;">Community Notes & Tips</h3>
      <div id="commentsList">
        ${law.user_notes.length > 0 
          ? law.user_notes.map((n, i) => `
              <div class="comment-bubble" data-index="${i}" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span><strong>${n.user_name}:</strong> ${n.comment}</span>
                <button class="delete-comment-btn" style="background: none; border: none; color: #ef4444; cursor: pointer; font-size: 0.8rem; font-weight: bold; margin-left: 10px;">Delete</button>
              </div>
            `).join('') 
          : '<p style="color: var(--text-muted); font-size: 0.9rem;">No notes yet. Be the first to add a practical tip!</p>'}
      </div>

      <div class="comment-form">
        <h4 style="color: var(--text-main); font-size: 1rem; margin-bottom: 10px;">Add a Note or Tip</h4>
        <input type="text" id="userNameInput" placeholder="Your Name (e.g., Maria S.)">
        <textarea id="userCommentInput" placeholder="Share a practical tip or explanation..." rows="3"></textarea>
        <button id="submitCommentBtn">Post Note</button>
      </div>
    `;

    modal.classList.remove("hidden");

    // Reattach delete event listeners
    modalBody.querySelectorAll(".delete-comment-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const bubble = e.target.closest(".comment-bubble");
        const idx = Number(bubble.dataset.index);
        law.user_notes.splice(idx, 1);
        openModal(law);
      });
    });

    // Reattach comment submit handler
    const submitBtn = document.getElementById("submitCommentBtn");
    submitBtn.addEventListener("click", () => {
      const nameInput = document.getElementById("userNameInput").value.trim();
      const commentInput = document.getElementById("userCommentInput").value.trim();

      if (nameInput && commentInput) {
        law.user_notes.push({ user_name: nameInput, comment: commentInput });
        openModal(law);
      }
    });
  }

  if (closeModal) {
    closeModal.addEventListener("click", () => modal.classList.add("hidden"));
  }
  window.addEventListener("click", (e) => {
    if (e.target === modal) modal.classList.add("hidden");
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.classList.contains("hidden")) {
      modal.classList.add("hidden");
    }
  });

  // Fetch implementation
  async function fetchLaws() {
    try {
      const response = await fetch('/api/v1/laws', {
        headers: {
          'x-api-key': API_KEY
        }
      });
      const result = await response.json();
      allLaws = Array.isArray(result) ? result : (result.laws || []);
      
      const top5Laws = allLaws.slice(0, 5);
      displayLaws(top5Laws);
    } catch (error) {
      console.error("Fetch error:", error);
      if (lawsGrid) {
        lawsGrid.innerHTML = `<p style="color: var(--text-muted);">Failed to load laws from the backend.</p>`;
      }
    }
  }

  // Execute fetch after everything is defined
  fetchLaws();
});