import { elements } from "./elements.js";
import { initFilters, getObjectQueries } from "./filters.js";
import { searchAPI, loginAPI } from "./api.js";
import { displayResults } from "./results.js";
import { initVideoModal } from "./video-player.js";

let currentResults = [];
let isGroupShots = false; // Trạng thái mặc định

document.addEventListener("DOMContentLoaded", () => {
  initFilters();
  initVideoModal();

  // --- TOGGLE GROUP SHOTS ---
  if (elements.toggleGroupShotsBtn) {
    elements.toggleGroupShotsBtn.addEventListener("click", () => {
      isGroupShots = !isGroupShots;

      // Update UI Button
      elements.toggleGroupShotsBtn.textContent = isGroupShots
        ? "Group Shots: ON"
        : "Group Shots: OFF";
      elements.toggleGroupShotsBtn.classList.toggle("active", isGroupShots);

      // Re-display results without API call
      displayResults(currentResults, isGroupShots);
    });
  }

  // --- XỬ LÝ LOGIN VÀ CHỌN EVALUATION (Giữ nguyên) ---
  if (elements.loginBtn) {
    elements.loginBtn.addEventListener("click", async () => {
      elements.loginBtn.textContent = "Logging in...";
      try {
        const data = await loginAPI();
        if (!data.evaluations || data.evaluations.length === 0) {
          throw new Error("No active evaluations found.");
        }
        showEvaluationModal(data.evaluations, data.sessionId);
      } catch (error) {
        alert(`Login Failed: ${error.message}`);
        elements.loginBtn.textContent = "Login failed";
        elements.loginBtn.style.background = "#dc3545";
        setTimeout(() => {
          elements.loginBtn.textContent = "Login";
          elements.loginBtn.style.background = "#e76f51";
        }, 2000);
      }
    });
  }

  function showEvaluationModal(evaluations, sessionId) {
    elements.evalListContainer.innerHTML = "";
    elements.evalListContainer.style.display = "flex";
    elements.evalListContainer.style.flexDirection = "column";
    elements.evalListContainer.style.gap = "10px";

    evaluations.forEach((ev) => {
      const btn = document.createElement("button");
      btn.textContent = `${ev.name} (ID: ${ev.id}) - ${ev.status}`;
      btn.style.padding = "10px";
      btn.style.textAlign = "left";
      btn.style.border = "1px solid #ccc";
      btn.style.borderRadius = "4px";
      btn.style.background = "#f8f9fa";
      btn.style.cursor = "pointer";

      btn.onmouseover = () => {
        btn.style.background = "#e2e6ea";
      };
      btn.onmouseout = () => {
        btn.style.background = "#f8f9fa";
      };

      btn.onclick = () => {
        localStorage.setItem("sessionId", sessionId);
        localStorage.setItem("evaluationId", ev.id);
        elements.evalModal.classList.add("hidden");
        elements.loginBtn.textContent = `Logged: ${ev.name}`;
        elements.loginBtn.style.background = "#28a745";
        alert(`Selected Evaluation: ${ev.name}\nID: ${ev.id}`);
      };
      elements.evalListContainer.appendChild(btn);
    });
    elements.evalModal.classList.remove("hidden");
  }

  if (elements.cancelEvalBtn) {
    elements.cancelEvalBtn.addEventListener("click", () => {
      elements.evalModal.classList.add("hidden");
      elements.loginBtn.textContent = "Login";
      elements.loginBtn.style.background = "#e76f51";
    });
  }

  // 1. Search Handler
  elements.searchForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData(elements.searchForm);
    const queryData = {
      description: formData.get("description"),
      criteria: elements.criteriaSelect.value || "fused_score", // Default to "fused" nếu không chọn
      objects: getObjectQueries(),
      audio: formData.get("audio"),
    };

    elements.resultsContainer.innerHTML = "<p>Searching...</p>";
    const results = await searchAPI(queryData);
    currentResults = results;

    // Hiển thị dựa theo trạng thái toggle hiện tại
    displayResults(currentResults, isGroupShots);
  });

  // 2. Scroll to Top
  const scrollTopBtn = document.getElementById("scroll-top-btn");
  if (scrollTopBtn) {
    scrollTopBtn.addEventListener("click", (e) => {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: "instant" });
      scrollTopBtn.blur();
    });
  }
});
