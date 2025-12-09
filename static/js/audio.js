// File: static/js/audio.js
import { loginAPI } from "./api.js";
import { displayResults } from "./results.js";
import { initVideoModal } from "./video-player.js";
import { elements as sharedElements } from "./elements.js";

// Override lại elements cần thiết cho trang riêng này
const ui = {
  statusBox: document.getElementById("bot-status"),
  transcriptInput: document.getElementById("audio-transcript-display"),
  loginBtn: document.getElementById("audio-login-btn"),
  evalModal: document.getElementById("evaluation-modal"),
  evalList: document.getElementById("evaluation-list"),
  recIcon: document.getElementById("rec-icon"),
  // Dùng chung container kết quả với logic cũ
  resultsContainer: document.getElementById("results-container"),
};

// Gán lại container cho module results.js dùng chung
sharedElements.resultsContainer = ui.resultsContainer;

document.addEventListener("DOMContentLoaded", () => {
  initVideoModal(); // Khởi tạo player video
  initLoginHandler(); // Cấu hình nút Login
  connectSSE(); // Bắt đầu lắng nghe sự kiện từ server
});

function log(msg) {
  ui.statusBox.textContent = `[BOT] ${msg}`;
  console.log(`[AudioBot] ${msg}`);
}

// 1. KẾT NỐI SSE ĐỂ NHẬN DỮ LIỆU TỰ ĐỘNG
function connectSSE() {
  const eventSource = new EventSource("/api/audio/stream");

  eventSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);

    if (msg.type === "system") {
      log(msg.data);
      if (msg.data.includes("Transcribing")) {
        ui.recIcon.style.display = "inline";
      } else {
        ui.recIcon.style.display = "none";
      }
    } else if (msg.type === "transcript") {
      // Tự động điền text vào ô input
      ui.transcriptInput.value = msg.data;
      ui.transcriptInput.style.backgroundColor = "#e8f0fe";
    } else if (msg.type === "search_results") {
      // Tự động hiển thị kết quả (tái sử dụng hàm của app chính)
      log(`Found ${msg.data.length} matches. Updating UI...`);
      displayResults(msg.data, false); // false = không group shots
    } else if (msg.type === "error") {
      ui.statusBox.textContent = `[ERROR] ${msg.data}`;
      ui.statusBox.style.color = "red";
    }
  };

  eventSource.onerror = () => {
    // Mất kết nối thì thử lại sau 3s
    eventSource.close();
    setTimeout(connectSSE, 3000);
  };
}

// 2. XỬ LÝ LOGIN & CHỌN EVALUATION (Logic riêng cho trang này)
function initLoginHandler() {
  ui.loginBtn.addEventListener("click", async () => {
    ui.loginBtn.textContent = "Checking DRES...";
    try {
      const data = await loginAPI();
      showEvalModal(data.evaluations, data.sessionId);
    } catch (error) {
      alert("Login failed: " + error.message);
      ui.loginBtn.textContent = "Login DRES";
    }
  });
}

function showEvalModal(evaluations, sessionId) {
  ui.evalList.innerHTML = "";
  ui.evalModal.classList.remove("hidden");

  evaluations.forEach((ev) => {
    const btn = document.createElement("button");
    btn.textContent = `${ev.name} (${ev.status})`;
    btn.style.display = "block";
    btn.style.width = "100%";
    btn.style.margin = "5px 0";
    btn.style.padding = "10px";
    btn.style.cursor = "pointer";

    btn.onclick = async () => {
      // Gửi lệnh START BOT lên server
      await startBot(sessionId, ev.id);

      ui.evalModal.classList.add("hidden");
      ui.loginBtn.textContent = `Bot Active: ${ev.name}`;
      ui.loginBtn.style.background = "#28a745";
      localStorage.setItem("sessionId", sessionId);
      localStorage.setItem("evaluationId", ev.id);
    };
    ui.evalList.appendChild(btn);
  });

  document.getElementById("cancel-eval-btn").onclick = () => {
    ui.evalModal.classList.add("hidden");
    ui.loginBtn.textContent = "Login DRES";
  };
}

async function startBot(sessionId, evaluationId) {
  try {
    log("Starting automation loop...");
    const res = await fetch("/api/audio/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId, evaluationId }),
    });
    const data = await res.json();
    if (data.status === "started") {
      log("Bot STARTED. Waiting for new tasks...");
    }
  } catch (e) {
    alert("Cannot start bot: " + e.message);
  }
}
