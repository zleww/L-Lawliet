const API_URL = "/api";
let currentLawId = null;

// Fetch and render law cards (Only shows 4-5 initial identifiers)
async function loadLaws(searchTerm = "") {
  const res = await fetch(`${API_URL}/laws${searchTerm ? `?search=${encodeURIComponent(searchTerm)}` : ''}`);
  const laws = await res.json();
  const grid = document.getElementById("lawsGrid");
  
  grid.innerHTML = laws.map(law => `
    <div class="card" onclick="openLawDetail(${law.id})">
      <div class="badge">${law.category}</div>
      <h3>${law.ra_number}</h3>
      <h4>${law.plain_title}</h4>
      <p class="summary">${law.tldr_summary}</p>
      <span class="click-more">Click to view all 14 details →</span>
    </div>
  `).join("");
}

// Open modal displaying full 14 identifiers
async function openLawDetail(id) {
  currentLawId = id;
  const res = await fetch(`${API_URL}/laws/${id}`);
  const law = await res.json();
  
  const modalBody = document.getElementById("modalBody");
  modalBody.innerHTML = `
    <span class="badge">${law.category}</span>
    <h2>${law.ra_number}: ${law.plain_title}</h2>
    <p class="official-title"><strong>Official Title:</strong> ${law.official_title} (${law.year})</p>
    
    <hr/>
    <div class="detail-section">
      <h4>📌 Quick Summary (TL;DR)</h4>
      <p>${law.tldr_summary}</p>
    </div>

    <div class="detail-section">
      <h4>📖 Full Simplified Breakdown</h4>
      <p>${law.full_breakdown}</p>
    </div>

    <div class="detail-section">
      <h4>💡 Why It Matters to You</h4>
      <p>${law.why_it_matters}</p>
    </div>

    <div class="detail-section">
      <h4>⚖️ Real-World Scenario</h4>
      <p>${law.example_scenario}</p>
    </div>

    <div class="detail-section">
      <h4>🚨 Penalties & Violations</h4>
      <p>${law.penalties}</p>
    </div>

    <div class="detail-section">
      <h4>👥 Who Is Affected</h4>
      <p>${law.target_audience}</p>
    </div>

    <div class="detail-section">
      <h4>🔗 Official Government Text</h4>
      <a href="${law.source_url}" target="_blank" rel="noopener">Read Full Official Gazette Text</a>
    </div>

    <hr/>
    <div class="comment-section">
      <h4>💬 Community Insights & Tips (${law.user_notes.length})</h4>
      <div id="commentList">
        ${law.user_notes.length ? law.user_notes.map(c => `
          <div class="comment-bubble"><strong>${c.user_name}:</strong> ${c.comment}</div>
        `).join("") : "<p class='empty-note'>No tips added yet. Be the first!</p>"}
      </div>

      <div class="comment-form">
        <h5>Add Your Knowledge or Practical Tip</h5>
        <input type="text" id="userNameInput" placeholder="Your Name or Handle" />
        <textarea id="userCommentInput" rows="2" placeholder="Add a clarification, practical tip, or note..."></textarea>
        <button onclick="submitComment()">Post Knowledge</button>
      </div>
    </div>
  `;
  
  document.getElementById("lawModal").classList.remove("hidden");
}

async function submitComment() {
  const name = document.getElementById("userNameInput").value.trim();
  const comment = document.getElementById("userCommentInput").value.trim();
  
  if (!name || !comment) return alert("Please fill out both fields.");

  const res = await fetch(`${API_URL}/laws/${currentLawId}/comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_name: name, comment: comment })
  });

  if (res.ok) {
    openLawDetail(currentLawId); // Refresh modal view
  }
}

// Close Modal
document.getElementById("closeModal").onclick = () => {
  document.getElementById("lawModal").classList.add("hidden");
};

// Search listener
document.getElementById("searchInput").addEventListener("input", (e) => {
  loadLaws(e.target.value);
});

// Initial Load
loadLaws();