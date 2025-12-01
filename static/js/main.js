import { elements } from "./elements.js";
import { initFilters, getObjectQueries } from "./filters.js";
import { searchAPI, loginAPI } from "./api.js";
import { displayResults } from "./results.js";
import { initVideoModal } from "./video-player.js";

let currentResults = [];

document.addEventListener("DOMContentLoaded", () => {
  // Initialize UI Logic
  initFilters();
  initVideoModal();

  // --- XỬ LÝ LOGIN VÀ CHỌN EVALUATION ---
  if (elements.loginBtn) {
    elements.loginBtn.addEventListener("click", async () => {
      elements.loginBtn.textContent = "Logging in...";
      try {
        const data = await loginAPI();

        // Data format: { sessionId: "...", evaluations: [ {id:..., name:...}, ... ] }

        if (!data.evaluations || data.evaluations.length === 0) {
          throw new Error("No active evaluations found.");
        }

        // Mở Modal để user chọn
        showEvaluationModal(data.evaluations, data.sessionId);
      } catch (error) {
        alert(`Login Failed: ${error.message}`);
        elements.loginBtn.textContent = "Login failed";
        elements.loginBtn.style.background = "#dc3545";

        // Reset button text after 2 seconds
        setTimeout(() => {
          elements.loginBtn.textContent = "Login";
          elements.loginBtn.style.background = "#e76f51";
        }, 2000);
      }
    });
  }

  // Hàm hiển thị Modal chọn Evaluation
  function showEvaluationModal(evaluations, sessionId) {
    elements.evalListContainer.innerHTML = "";

    // Tạo style cho list
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

      // Xử lý khi chọn
      btn.onclick = () => {
        localStorage.setItem("sessionId", sessionId);
        localStorage.setItem("evaluationId", ev.id);

        elements.evalModal.classList.add("hidden");
        elements.loginBtn.textContent = `Logged: ${ev.name}`;
        elements.loginBtn.style.background = "#28a745"; // Green
        alert(`Selected Evaluation: ${ev.name}\nID: ${ev.id}`);
      };

      elements.evalListContainer.appendChild(btn);
    });

    // Hiển thị modal
    elements.evalModal.classList.remove("hidden");
  }

  // Xử lý nút Cancel trong Evaluation Modal
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
      objects: getObjectQueries(),
      audio: formData.get("audio"),
    };

    // Clear old results
    elements.resultsContainer.innerHTML = "<p>Searching...</p>";

    const results = await searchAPI(queryData);
    currentResults = results;
    displayResults(currentResults);
  });

  // 2. Scroll to Top Logic
  const scrollTopBtn = document.getElementById("scroll-top-btn");

  // Function to perform immediate scroll
  const scrollToTop = () => {
    window.scrollTo({
      top: 0,
      behavior: "instant",
    });
  };

  // Button Click Event
  if (scrollTopBtn) {
    scrollTopBtn.addEventListener("click", (e) => {
      e.preventDefault();
      scrollToTop();
      scrollTopBtn.blur();
    });
  }
});
