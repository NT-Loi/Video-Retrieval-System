import { elements } from "./elements.js";
import { initFilters, getObjectQueries } from "./filters.js";
import { searchAPI, loginAPI } from "./api.js";
import { displayResults } from "./results.js";
import { initVideoModal } from "./video-player.js";

let currentResults = [];
let isGroupShots = false;

document.addEventListener("DOMContentLoaded", () => {
  initFilters();
  initVideoModal();
  initDynamicInputs(); // Khởi tạo logic thêm bớt input

  // --- TOGGLE GROUP SHOTS ---
  if (elements.toggleGroupShotsBtn) {
    elements.toggleGroupShotsBtn.addEventListener("click", () => {
      isGroupShots = !isGroupShots;
      elements.toggleGroupShotsBtn.textContent = isGroupShots
        ? "Group Shots: ON"
        : "Group Shots: OFF";
      elements.toggleGroupShotsBtn.classList.toggle("active", isGroupShots);
      displayResults(currentResults, isGroupShots);
    });
  }

  // --- LOGIN LOGIC (Giữ nguyên) ---
  if (elements.loginBtn) {
    elements.loginBtn.addEventListener("click", async () => {
      elements.loginBtn.textContent = "Logging in...";
      try {
        const data = await loginAPI();
        if (!data.evaluations || data.evaluations.length === 0) {
          alert("No active evaluations found.");
          elements.loginBtn.textContent = "Login";
          return;
        }
        showEvaluationModal(data.evaluations, data.sessionId);
      } catch (error) {
        alert(`Login Failed: ${error.message}`);
        elements.loginBtn.textContent = "Login failed";
      }
    });
  }

  // --- SEARCH SUBMIT ---
  elements.searchForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    // 1. Thu thập các câu query text
    const textQueries = [];
    const rows = elements.queryInputsContainer.querySelectorAll(".query-row");
    let anchorIndex = 0;

    rows.forEach((row, index) => {
      const input = row.querySelector(".main-query-input");
      const radio = row.querySelector('input[type="radio"]');
      const text = input.value.trim();

      if (text) {
        textQueries.push(text);
        if (radio.checked) {
          anchorIndex = index; // Xác định dòng nào được chọn để Rank
        }
      }
    });

    // Nếu người dùng chọn Rank dòng trống hoặc dòng k có text, fallback về dòng đầu tiên có text
    // Nhưng đơn giản nhất là gửi anchorIndex theo thứ tự đã filter
    // Tuy nhiên, để chính xác, ta cần map đúng index của list textQueries.
    // Logic dưới đây giả định người dùng nhập liên tiếp.

    // Build payload
    const queryData = {
      text_queries: textQueries, // List of strings
      anchor_index: anchorIndex, // Index của câu query dùng để sort (trong list textQueries)
      criteria: elements.criteriaSelect.value || "fused_score",
      objects: getObjectQueries(),
      audio: document.getElementById("audio-filter").value, // Lấy audio filter riêng
    };

    if (
      queryData.text_queries.length === 0 &&
      !queryData.audio &&
      queryData.objects.length === 0
    ) {
      alert("Please enter at least one description, audio, or object filter.");
      return;
    }

    elements.resultsContainer.innerHTML = "<p>Searching sequence...</p>";
    const results = await searchAPI(queryData);
    currentResults = results;

    displayResults(currentResults, isGroupShots);
  });

  // --- SCROLL TOP ---
  const scrollTopBtn = document.getElementById("scroll-top-btn");
  if (scrollTopBtn) {
    scrollTopBtn.addEventListener("click", (e) => {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: "instant" });
      scrollTopBtn.blur();
    });
  }
});

// --- LOGIC INPUT ĐỘNG ---
function initDynamicInputs() {
  if (!elements.addQueryBtn) return;

  elements.addQueryBtn.addEventListener("click", () => {
    const rows = elements.queryInputsContainer.querySelectorAll(".query-row");
    if (rows.length >= 3) {
      alert("Maximum 3 events allow.");
      return;
    }

    const newIndex = rows.length;
    const div = document.createElement("div");
    div.className = "search-row query-row";
    div.dataset.index = newIndex;
    div.style.marginTop = "5px";

    div.innerHTML = `
            <input type="radio" name="rank_by" value="${newIndex}" title="Rank results by this query">
            <input type="text" name="description_${newIndex}" class="main-query-input" placeholder="Next Event (approx. 1 min later)..." autocomplete="off">
            <button type="button" class="remove-query-btn" style="background:#dc3545; color:white; border:none; border-radius:4px; cursor:pointer; padding:0 8px;">X</button>
        `;

    elements.queryInputsContainer.appendChild(div);
    updateRemoveButtons();
  });

  elements.queryInputsContainer.addEventListener("click", (e) => {
    if (e.target.classList.contains("remove-query-btn")) {
      e.target.parentElement.remove();
      reindexRows();
    }
  });
}

function updateRemoveButtons() {
  // Chỉ hiện nút X nếu có > 1 dòng
  const rows = elements.queryInputsContainer.querySelectorAll(".query-row");
  rows.forEach((row) => {
    const btn = row.querySelector(".remove-query-btn");
    if (btn) btn.style.display = rows.length > 1 ? "block" : "none";
  });
}

function reindexRows() {
  const rows = elements.queryInputsContainer.querySelectorAll(".query-row");
  rows.forEach((row, index) => {
    row.dataset.index = index;
    const radio = row.querySelector('input[type="radio"]');
    radio.value = index;
    if (
      index === 0 &&
      !document.querySelector('input[name="rank_by"]:checked')
    ) {
      radio.checked = true; // Đảm bảo luôn có 1 cái được check
    }

    const input = row.querySelector(".main-query-input");
    input.name = `description_${index}`;
    input.placeholder = index === 0 ? "Event 1..." : "Next Event...";
  });
}

// ... (Giữ nguyên phần showEvaluationModal) ...
function showEvaluationModal(evaluations, sessionId) {
  elements.evalListContainer.innerHTML = "";
  evaluations.forEach((ev) => {
    const btn = document.createElement("button");
    btn.textContent = `${ev.name} (${ev.status})`;
    btn.style.width = "100%";
    btn.style.margin = "5px 0";
    btn.onclick = () => {
      localStorage.setItem("sessionId", sessionId);
      localStorage.setItem("evaluationId", ev.id);
      elements.evalModal.classList.add("hidden");
      elements.loginBtn.textContent = `Logged: ${ev.name}`;
      elements.loginBtn.style.background = "#28a745";
    };
    elements.evalListContainer.appendChild(btn);
  });
  elements.evalModal.classList.remove("hidden");

  if (elements.cancelEvalBtn) {
    elements.cancelEvalBtn.onclick = () => {
      elements.evalModal.classList.add("hidden");
      elements.loginBtn.textContent = "Login";
    };
  }
}
