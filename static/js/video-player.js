import { elements } from "./elements.js";
import { submitResultAPI } from "./api.js";

let currentOpenVideoId = null;

export function initVideoModal() {
  elements.closeModalBtn.addEventListener("click", closeModal);
  elements.modalOverlay.addEventListener("click", (e) => {
    if (e.target === elements.modalOverlay) {
      closeModal();
    }
  });
}

function highlightActiveCard(videoId, shotData, specificKeyframe) {
  // Xóa highlight cũ
  document.querySelectorAll(".active-viewed-card").forEach((el) => {
    el.classList.remove("active-viewed-card");
  });

  let selector = "";

  if (shotData) {
    // Chế độ Group Shot: Giữ nguyên logic cũ (theo shot key)
    const shotKey = `${videoId}|${shotData.shotStart}|${shotData.shotEnd}`;
    selector = `.shot-group-card[data-shot-key="${shotKey}"]`;
  } else {
    // Chế độ lẻ: Tìm chính xác theo videoId VÀ keyframeIndex
    // Lưu ý: attribute trong HTML là data-keyframe-index (kebab-case)
    if (specificKeyframe !== undefined && specificKeyframe !== null) {
      selector = `.result-item[data-video-id="${videoId}"][data-keyframe-index="${specificKeyframe}"]`;
    } else {
      // Fallback nếu không truyền keyframe (dù hiếm khi xảy ra nếu gọi đúng)
      selector = `.result-item[data-video-id="${videoId}"]`;
    }
  }

  const activeCard = document.querySelector(selector);
  if (activeCard) {
    activeCard.classList.add("active-viewed-card");
    activeCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

export function openModal(
  videoId,
  startTime,
  fps,
  shotData = null,
  specificKeyframe = null,
) {
  closeModal();
  currentOpenVideoId = videoId;

  // Truyền specificKeyframe vào hàm highlight
  highlightActiveCard(videoId, shotData, specificKeyframe);

  elements.modalVideoTitle.textContent = `Playing: ${videoId} (FPS: ${fps})`;
  elements.modalOverlay.classList.remove("hidden");

  // --- 1. SETUP HLS PLAYER ---
  const hlsUrl = `/hls/${videoId}/playlist.m3u8`;
  let mainHls = null;

  if (Hls.isSupported()) {
    mainHls = new Hls({ debug: false, enableWorker: true });
    mainHls.loadSource(hlsUrl);
    mainHls.attachMedia(elements.modalVideoPlayer);
    mainHls.on(Hls.Events.MANIFEST_PARSED, function () {
      elements.modalVideoPlayer.currentTime = startTime;
      elements.modalVideoPlayer
        .play()
        .catch((e) => console.warn("Auto-play blocked:", e));
    });
  } else if (
    elements.modalVideoPlayer.canPlayType("application/vnd.apple.mpegurl")
  ) {
    elements.modalVideoPlayer.src = hlsUrl;
    elements.modalVideoPlayer.addEventListener(
      "loadedmetadata",
      function () {
        elements.modalVideoPlayer.currentTime = startTime;
        elements.modalVideoPlayer.play();
      },
      { once: true },
    );
  } else {
    elements.modalVideoPlayer.src = `/videos/${videoId}#t=${startTime}`;
  }

  // --- 2. SETUP TIMELINE UI ---
  const videoWrapper = elements.modalVideoPlayer.parentElement;
  // Đảm bảo position relative để con (timeline) tuyệt đối theo nó
  if (getComputedStyle(videoWrapper).position === "static") {
    videoWrapper.style.position = "relative";
  }

  // Xóa timeline cũ nếu còn sót
  const oldTimeline = videoWrapper.querySelector(".video-timeline");
  if (oldTimeline) oldTimeline.remove();

  const timelineBar = document.createElement("div");
  timelineBar.className = "video-timeline";
  videoWrapper.appendChild(timelineBar);

  // Thanh Progress (Màu xanh)
  const progressFill = document.createElement("div");
  Object.assign(progressFill.style, {
    position: "absolute",
    left: "0",
    top: "0",
    bottom: "0",
    width: "0%",
    background: "#1db954", // Màu xanh
    borderRadius: "2px",
    pointerEvents: "none",
    zIndex: "10",
  });
  timelineBar.appendChild(progressFill);

  // --- 3. SETUP RED SHOT BAR ---
  if (shotData) {
    const addRedBar = () => {
      const duration = elements.modalVideoPlayer.duration;
      if (!duration || duration === Infinity) return;

      const startSec = shotData.shotStart / fps;
      const endSec = shotData.shotEnd / fps;

      const leftPct = (startSec / duration) * 100;
      const widthPct = ((endSec - startSec) / duration) * 100;

      const redBar = document.createElement("div");
      redBar.className = "shot-highlight-bar";
      Object.assign(redBar.style, {
        position: "absolute",
        top: "0",
        bottom: "0",
        left: `${leftPct}%`,
        width: `${widthPct}%`,
        backgroundColor: "rgba(220, 53, 69, 0.9)", // Màu đỏ đậm
        pointerEvents: "none",
        zIndex: "20", // CAO HƠN GREEN (10) ĐỂ KHÔNG BỊ ĐÈ
      });

      timelineBar.appendChild(redBar);
    };

    if (elements.modalVideoPlayer.readyState >= 1) {
      addRedBar();
    } else {
      elements.modalVideoPlayer.addEventListener("loadedmetadata", addRedBar, {
        once: true,
      });
    }
  }

  // --- 4. PREVIEW HOVER ---
  const timelinePreview = document.createElement("div");
  timelinePreview.className = "timeline-preview";
  timelinePreview.innerHTML = `
        <img src="" alt="Preview" style="display:none;">
        <div class="time-label">0:00</div>
    `;
  timelineBar.appendChild(timelinePreview);

  const previewVideo = document.createElement("video");
  previewVideo.muted = true;
  previewVideo.style.display = "none";
  videoWrapper.appendChild(previewVideo);

  let previewHls = null;
  if (Hls.isSupported()) {
    previewHls = new Hls({ maxBufferLength: 1, enableWorker: true });
    previewHls.loadSource(hlsUrl);
    previewHls.attachMedia(previewVideo);
  } else if (previewVideo.canPlayType("application/vnd.apple.mpegurl")) {
    previewVideo.src = hlsUrl;
  }

  // --- 5. SIDEBAR PLAYLIST ---
  if (elements.modalShotList) {
    elements.modalShotList.innerHTML = "";
    if (shotData && shotData.items && shotData.items.length > 0) {
      const sortedItems = [...shotData.items].sort(
        (a, b) => a.keyframe_index - b.keyframe_index,
      );

      sortedItems.forEach((kf) => {
        const criteria = elements.criteriaSelect.value || "fused_score";
        const itemDiv = document.createElement("div");
        itemDiv.className = "sidebar-keyframe-item";
        itemDiv.innerHTML = `
            <img src="/keyframes/${kf.video_id}/keyframe_${
              kf.keyframe_index
            }.webp" loading="lazy">
            <div class="sidebar-info">
                <strong>Frame: ${kf.keyframe_index}</strong>
                <span>Score: ${kf[criteria].toFixed(4)}</span>
            </div>
          `;
        itemDiv.addEventListener("click", () => {
          elements.modalVideoPlayer.currentTime = kf.keyframe_index / fps;
          elements.modalVideoPlayer.play();
        });
        elements.modalShotList.appendChild(itemDiv);
      });
    } else {
      elements.modalShotList.innerHTML =
        "<p style='padding:10px; color:#666; font-size:13px;'>No specific shot keyframes.</p>";
    }
  }

  // --- 6. FRAME CONTROLS (Submit & Nav) ---
  // Xóa controls cũ để tránh trùng lặp
  const oldControls =
    elements.modalPlayerSection.querySelector(".frame-controls");
  if (oldControls) oldControls.remove();

  const frameControls = document.createElement("div");
  frameControls.className = "frame-controls";
  frameControls.innerHTML = `
        <button id="dynamic-submit-btn" class="modal-submit-btn">Submit</button>
        <div class="frame-navigation">
            <button class="frame-btn" id="prev-frame-btn">-</button>
            <div class="frame-input-group">
                <input type="number" id="current-frame-input" class="frame-input" value="0">
                <span id="total-frames-span">/ 0</span>
            </div>
            <button class="frame-btn" id="next-frame-btn">+</button>
        </div>
        <div style="width: 80px;"></div>`;

  // Append vào phần Player Section (bên trái), dưới cùng
  elements.modalPlayerSection.appendChild(frameControls);

  // --- 7. EVENT LISTENERS ---
  const frameRate = fps;
  const dynSubmitBtn = frameControls.querySelector("#dynamic-submit-btn");
  const frameInput = frameControls.querySelector("#current-frame-input");
  const totalFramesSpan = frameControls.querySelector("#total-frames-span");
  const prevBtn = frameControls.querySelector("#prev-frame-btn");
  const nextBtn = frameControls.querySelector("#next-frame-btn");

  // Logic Hover Timeline
  const previewImg = timelinePreview.querySelector("img");
  const timeLabel = timelinePreview.querySelector(".time-label");
  const previewCanvas = document.createElement("canvas");
  const previewCtx = previewCanvas.getContext("2d");
  let hoverTargetTime = null;
  let hoverScheduled = false;

  const runHoverPreview = () => {
    hoverScheduled = false;
    if (hoverTargetTime === null || !elements.modalVideoPlayer.duration) return;
    const targetTime = hoverTargetTime;
    hoverTargetTime = null;

    const onSeeked = () => {
      if (Math.abs(previewVideo.currentTime - targetTime) > 0.5) return;
      const vw = previewVideo.videoWidth || previewVideo.clientWidth;
      const vh = previewVideo.videoHeight || previewVideo.clientHeight;
      if (!vw || !vh) return;
      previewCanvas.width = vw;
      previewCanvas.height = vh;
      try {
        previewCtx.drawImage(previewVideo, 0, 0, vw, vh);
        previewImg.src = previewCanvas.toDataURL("image/jpeg", 0.6);
        previewImg.style.display = "block";
      } catch (e) {
        previewImg.style.display = "none";
      }
    };
    previewVideo.removeEventListener("seeked", onSeeked);
    previewVideo.addEventListener("seeked", onSeeked, { once: true });
    previewVideo.currentTime = targetTime;
  };

  timelineBar.addEventListener("mousemove", (e) => {
    if (!elements.modalVideoPlayer.duration) return;
    const rect = timelineBar.getBoundingClientRect();
    const percent = Math.max(
      0,
      Math.min(1, (e.clientX - rect.left) / rect.width),
    );
    const hoverTime = percent * elements.modalVideoPlayer.duration;

    timelinePreview.style.display = "block";
    let left = percent * rect.width - timelinePreview.offsetWidth / 2;
    left = Math.max(
      0,
      Math.min(left, rect.width - timelinePreview.offsetWidth),
    );
    timelinePreview.style.left = `${percent * 100}%`;

    const m = Math.floor(hoverTime / 60);
    const s = Math.floor(hoverTime % 60);
    timeLabel.textContent = `${m}:${s.toString().padStart(2, "0")}`;

    hoverTargetTime = hoverTime;
    if (!hoverScheduled) {
      hoverScheduled = true;
      setTimeout(runHoverPreview, 50);
    }
  });

  timelineBar.addEventListener("mouseleave", () => {
    timelinePreview.style.display = "none";
    hoverTargetTime = null;
  });

  timelineBar.addEventListener("click", (e) => {
    if (!elements.modalVideoPlayer.duration) return;
    const rect = timelineBar.getBoundingClientRect();
    const percent = Math.max(
      0,
      Math.min(1, (e.clientX - rect.left) / rect.width),
    );
    elements.modalVideoPlayer.currentTime =
      percent * elements.modalVideoPlayer.duration;
  });

  // Logic Progress Update
  const updateProgress = () => {
    if (!elements.modalVideoPlayer.duration) return;
    const p =
      (elements.modalVideoPlayer.currentTime /
        elements.modalVideoPlayer.duration) *
      100;
    progressFill.style.width = `${p}%`;
  };
  elements.modalVideoPlayer.addEventListener("timeupdate", updateProgress);

  // Logic Frame Info Update
  const updateFrameInfo = () => {
    if (!elements.modalVideoPlayer.duration) return;
    const cf = Math.round(elements.modalVideoPlayer.currentTime * frameRate);
    if (document.activeElement !== frameInput) frameInput.value = cf;
    totalFramesSpan.textContent = `/ ${Math.floor(
      elements.modalVideoPlayer.duration * frameRate,
    )}`;
  };
  elements.modalVideoPlayer.addEventListener("timeupdate", updateFrameInfo);
  elements.modalVideoPlayer.addEventListener("loadedmetadata", updateFrameInfo);

  // Logic Submit
  dynSubmitBtn.addEventListener("click", async () => {
    const sId = localStorage.getItem("sessionId");
    const eId = localStorage.getItem("evaluationId");
    if (!sId || !eId) {
      alert("Please LOGIN first!");
      return;
    }
    const tMs = Math.round(elements.modalVideoPlayer.currentTime * 1000);
    const cf = Math.round(elements.modalVideoPlayer.currentTime * frameRate);
    if (confirm(`Submit frame ${cf} (${tMs}ms) of ${videoId}?`)) {
      try {
        const res = await submitResultAPI(sId, eId, videoId, tMs);
        alert(`Success! ${JSON.stringify(res.remote_response)}`);
      } catch (err) {
        alert(`Failed: ${err.message}`);
      }
    }
  });

  // Logic Navigation
  const stepFrame = (dir) => {
    elements.modalVideoPlayer.pause();
    const cf = Math.round(elements.modalVideoPlayer.currentTime * frameRate);
    let nextTime = (cf + dir) / frameRate + 0.0001;
    nextTime = Math.max(0, nextTime);
    elements.modalVideoPlayer.currentTime = nextTime;
  };
  prevBtn.addEventListener("click", () => stepFrame(-1));
  nextBtn.addEventListener("click", () => stepFrame(1));

  frameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const val = parseInt(frameInput.value, 10);
      if (!isNaN(val) && val >= 0) {
        elements.modalVideoPlayer.currentTime = val / frameRate;
        elements.modalVideoPlayer.pause();
      }
      frameInput.blur();
    }
  });

  // Keyboard Shortcuts
  const handleKey = (e) => {
    if (elements.modalOverlay.classList.contains("hidden")) return;
    if (document.activeElement === frameInput) return;
    if (e.key === "ArrowLeft") stepFrame(-1);
    if (e.key === "ArrowRight") stepFrame(1);
    if (e.key === " ") {
      e.preventDefault();
      elements.modalVideoPlayer.paused
        ? elements.modalVideoPlayer.play()
        : elements.modalVideoPlayer.pause();
    }
    if (e.key === "Escape") closeModal();
  };
  document.addEventListener("keydown", handleKey);

  // Store handlers for cleanup
  elements.modalOverlay.dataset.handlersAttached = "true";
  elements.modalOverlay._cleanupHandlers = {
    handleKey,
    timelineBar,
    frameControls,
    mainHls,
    previewHls,
    previewVideo,
    updateProgress,
    updateFrameInfo,
  };
}

export function closeModal() {
  if (elements.modalOverlay.classList.contains("hidden")) return;

  const h = elements.modalOverlay._cleanupHandlers;
  if (h) {
    document.removeEventListener("keydown", h.handleKey);
    if (h.timelineBar) h.timelineBar.remove();
    if (h.frameControls) h.frameControls.remove();
    elements.modalVideoPlayer.removeEventListener(
      "timeupdate",
      h.updateProgress,
    );
    elements.modalVideoPlayer.removeEventListener(
      "timeupdate",
      h.updateFrameInfo,
    );
    elements.modalVideoPlayer.removeEventListener(
      "loadedmetadata",
      h.updateFrameInfo,
    );
    if (h.mainHls) h.mainHls.destroy();
    if (h.previewHls) h.previewHls.destroy();
    if (h.previewVideo) h.previewVideo.remove();
  }
  delete elements.modalOverlay._cleanupHandlers;

  elements.modalOverlay.classList.add("hidden");
  elements.modalVideoPlayer.pause();
  elements.modalVideoPlayer.removeAttribute("src");
  elements.modalVideoPlayer.load();

  if (elements.modalShotList) elements.modalShotList.innerHTML = "";
}
