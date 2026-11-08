// Home page: hero search, category counts, featured law, first 5 laws.
// All data comes from the API (which reads Neon). No API key: auth.js attaches the login token.
document.addEventListener("DOMContentLoaded", () => {
  const { apiFetch } = window.LawlietAuth;
  const { renderCard, openModal, wireModalClose, accessBanner } = window.LawsUI;

  const lawsGrid = document.getElementById("lawsGrid");
  const searchInput = document.getElementById("searchInput");
  const searchSubmitBtn = document.getElementById("searchSubmitBtn");
  const popularTags = document.querySelectorAll(".tag-link");
  const featuredReadMoreBtn = document.getElementById("featuredReadMoreBtn");
  const modal = document.getElementById("lawModal");
  const modalBody = document.getElementById("modalBody");

  let lastResult = null;
  const show = law => openModal(law, modal, modalBody);

  function displayLaws(result) {
    if (!lawsGrid) return;
    lawsGrid.innerHTML = accessBanner(result);
    const laws = result.laws.slice(0, 5);
    if (laws.length === 0) {
      lawsGrid.insertAdjacentHTML("beforeend", `<p style="color: var(--text-muted);">No laws found matching your search.</p>`);
      return;
    }
    laws.forEach(law => lawsGrid.appendChild(renderCard(law, show)));
  }

  async function fetchLaws(search = "") {
    try {
      const qs = search ? `?search=${encodeURIComponent(search)}` : "";
      const res = await apiFetch(`/api/v1/laws${qs}`);
      if (!res.ok) throw new Error(`Server returned HTTP ${res.status}`);
      lastResult = await res.json();
      displayLaws(lastResult);
    } catch (error) {
      console.error("Error fetching laws:", error);
      if (lawsGrid) lawsGrid.innerHTML = `<p style="color: var(--text-muted);">Failed to load laws from the backend.</p>`;
    }
  }

  // Category counts and the "Republic Acts" stat come from the database, not hardcoded text.
  async function fetchStats() {
    try {
      const res = await apiFetch("/api/v1/stats");
      if (!res.ok) return;
      const stats = await res.json();
      document.querySelectorAll("[data-count-category]").forEach(el => {
        const n = stats.categories[el.dataset.countCategory] || 0;
        el.textContent = `${n} ${n === 1 ? "Law" : "Laws"}`;
      });
      const total = document.getElementById("statTotalLaws");
      if (total) total.textContent = stats.total;
    } catch (error) {
      console.error("Error fetching stats:", error);
    }
  }

  // Live search asks the server (debounced) instead of filtering in the browser.
  let timer;
  if (searchInput) {
    searchInput.addEventListener("input", ev => {
      clearTimeout(timer);
      timer = setTimeout(() => fetchLaws(ev.target.value.trim()), 300);
    });
  }

  if (searchSubmitBtn) {
    searchSubmitBtn.addEventListener("click", () => {
      const query = searchInput ? searchInput.value.trim() : "";
      window.location.href = query ? `browse.html?search=${encodeURIComponent(query)}` : "browse.html";
    });
  }

  popularTags.forEach(tag => {
    tag.style.cursor = "pointer";
    tag.addEventListener("click", () => {
      window.location.href = `browse.html?search=${encodeURIComponent(tag.getAttribute("data-search"))}`;
    });
  });

  if (featuredReadMoreBtn) {
    featuredReadMoreBtn.addEventListener("click", async () => {
      try {
        const res = await apiFetch(`/api/v1/laws/search?q=${encodeURIComponent("RA 10175")}`);
        if (!res.ok) return;
        const data = await res.json();
        const law = data.results.find(l => l.ra_number === "RA 10175") || data.results[0];
        if (law) show(law);
      } catch (error) {
        console.error("Error loading featured law:", error);
      }
    });
  }

  wireModalClose(modal, document.getElementById("closeModal"));
  fetchLaws();
  fetchStats();
});
