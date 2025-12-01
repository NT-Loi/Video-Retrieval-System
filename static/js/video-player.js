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

  // Đã bỏ listener static cũ vì button submit giờ được tạo động trong openModal
}

export function openModal(videoId, startTime, fps) {
  closeModal(); // Dọn dẹp instance cũ trước khi mở mới
  currentOpenVideoId = videoId;

  elements.modalVideoTitle.textContent = `Playing: ${videoId} (FPS: ${fps})`;
  elements.modalOverlay.classList.remove("hidden");

  const hlsUrl = `/hls/${videoId}/playlist.m3u8`;
  let mainHls = null;

  // --- HLS PLAYER SETUP ---
  if (Hls.isSupported()) {
    mainHls = new Hls({
      debug: false,
      enableWorker: true,
    });
    mainHls.loadSource(hlsUrl);
    mainHls.attachMedia(elements.modalVideoPlayer);

    mainHls.on(Hls.Events.MANIFEST_PARSED, function () {
      elements.modalVideoPlayer.currentTime = startTime;
      elements.modalVideoPlayer
        .play()
        .catch((e) => console.warn("Auto-play blocked:", e));
    });

    mainHls.on(Hls.Events.ERROR, function (event, data) {
      if (data.fatal) {
        switch (data.type) {
          case Hls.ErrorTypes.NETWORK_ERROR:
            console.error("Fatal network error encountered, trying to recover");
            mainHls.startLoad();
            break;
          case Hls.ErrorTypes.MEDIA_ERROR:
            console.error("Fatal media error encountered, trying to recover");
            mainHls.recoverMediaError();
            break;
          default:
            mainHls.destroy();
            break;
        }
      }
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
    console.error("HLS not supported in this browser.");
    elements.modalVideoPlayer.src = `/videos/${videoId}#t=${startTime}`;
  }

  // --- Video Wrapper styling ---
  const videoWrapper = elements.modalVideoPlayer.parentElement;
  if (getComputedStyle(videoWrapper).position === "static") {
    videoWrapper.style.position = "relative";
  }

  // --- Create Timeline UI ---
  const timelineBar = document.createElement("div");
  timelineBar.className = "video-timeline";

  const progressFill = document.createElement("div");
  Object.assign(progressFill.style, {
    position: "absolute",
    left: "0",
    top: "0",
    bottom: "0",
    width: "0%",
    background: "#1db954",
    borderRadius: "2px",
    pointerEvents: "none",
  });
  timelineBar.appendChild(progressFill);

  const timelinePreview = document.createElement("div");
  timelinePreview.className = "timeline-preview";
  timelinePreview.innerHTML = `
        <img src="" alt="Preview" style="display:none;">
        <div class="time-label">0:00</div>
    `;
  timelineBar.appendChild(timelinePreview);
  videoWrapper.appendChild(timelineBar);

  const previewImg = timelinePreview.querySelector("img");
  const timeLabel = timelinePreview.querySelector(".time-label");

  // --- HLS Preview Setup ---
  const previewVideo = document.createElement("video");
  previewVideo.muted = true;
  previewVideo.preload = "metadata";
  previewVideo.style.display = "none";
  videoWrapper.appendChild(previewVideo);

  let previewHls = null;
  if (Hls.isSupported()) {
    previewHls = new Hls({
      maxBufferLength: 1,
      maxMaxBufferLength: 2,
      enableWorker: true,
    });
    previewHls.loadSource(hlsUrl);
    previewHls.attachMedia(previewVideo);
  } else if (previewVideo.canPlayType("application/vnd.apple.mpegurl")) {
    previewVideo.src = hlsUrl;
  }

  // --- Hover Logic ---
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
      } catch (err) {
        previewImg.style.display = "none";
      }
    };

    previewVideo.removeEventListener("seeked", onSeeked);
    previewVideo.addEventListener("seeked", onSeeked, { once: true });
    previewVideo.currentTime = targetTime;
  };

  const scheduleHoverPreview = () => {
    if (!hoverScheduled) {
      hoverScheduled = true;
      setTimeout(runHoverPreview, 50);
    }
  };

  const handleMouseMove = (e) => {
    if (!elements.modalVideoPlayer.duration) return;

    const rect = timelineBar.getBoundingClientRect();
    const percent = Math.max(
      0,
      Math.min(1, (e.clientX - rect.left) / rect.width),
    );
    const hoverTime = percent * elements.modalVideoPlayer.duration;

    timelinePreview.style.display = "block";
    let previewLeft = percent * rect.width - timelinePreview.offsetWidth / 2;
    previewLeft = Math.max(
      0,
      Math.min(previewLeft, rect.width - timelinePreview.offsetWidth),
    );
    timelinePreview.style.left = `${percent * 100}%`;

    const minutes = Math.floor(hoverTime / 60);
    const seconds = Math.floor(hoverTime % 60);
    timeLabel.textContent = `${minutes}:${seconds.toString().padStart(2, "0")}`;

    hoverTargetTime = hoverTime;
    scheduleHoverPreview();
  };

  const handleTimelineClick = (e) => {
    if (!elements.modalVideoPlayer.duration) return;
    const rect = timelineBar.getBoundingClientRect();
    const percent = Math.max(
      0,
      Math.min(1, (e.clientX - rect.left) / rect.width),
    );
    elements.modalVideoPlayer.currentTime =
      percent * elements.modalVideoPlayer.duration;
  };

  const updateProgress = () => {
    if (!elements.modalVideoPlayer.duration) return;
    const p =
      (elements.modalVideoPlayer.currentTime /
        elements.modalVideoPlayer.duration) *
      100;
    progressFill.style.width = `${p}%`;
  };

  timelineBar.addEventListener("mousemove", handleMouseMove);
  timelineBar.addEventListener("mouseleave", () => {
    timelinePreview.style.display = "none";
    hoverTargetTime = null;
  });
  timelineBar.addEventListener("click", handleTimelineClick);
  elements.modalVideoPlayer.addEventListener("timeupdate", updateProgress);

  // --- Frame Controls & Submit Button ---
  const frameControls = document.createElement("div");
  frameControls.className = "frame-controls";

  // HTML mới: Submit bên trái, Frame Navigation ở giữa
  frameControls.innerHTML = `
        <button id="dynamic-submit-btn" class="modal-submit-btn" title="Submit this frame">Submit</button>
        
        <div class="frame-navigation">
            <button class="frame-btn" id="prev-frame-btn" title="Previous Frame">-</button>
            <div class="frame-input-group">
                <input type="number" id="current-frame-input" class="frame-input" value="0">
                <span id="total-frames-span">/ 0</span>
            </div>
            <button class="frame-btn" id="next-frame-btn" title="Next Frame">+</button>
        </div>
        
        <div style="width: 80px;"></div> `;
  elements.modalContent.appendChild(frameControls);

  const frameRate = fps;
  const frameDuration = 1 / frameRate;

  const frameInput = frameControls.querySelector("#current-frame-input");
  const totalFramesSpan = frameControls.querySelector("#total-frames-span");
  const dynSubmitBtn = frameControls.querySelector("#dynamic-submit-btn");

  // Logic Submit mới
  dynSubmitBtn.addEventListener("click", async () => {
    const sessionId = localStorage.getItem("sessionId");
    const evaluationId = localStorage.getItem("evaluationId");

    if (!sessionId || !evaluationId) {
      alert("Please LOGIN first!");
      return;
    }

    // Lấy frame và thời gian
    const currentFrame = Math.round(
      elements.modalVideoPlayer.currentTime * frameRate,
    );
    const timeMs = Math.round(elements.modalVideoPlayer.currentTime * 1000);

    // Confirm dialog với frame number
    const confirmSubmit = confirm(
      `Submit frame ${currentFrame} time ${timeMs}ms of video ${videoId}?`,
    );
    if (!confirmSubmit) return;

    try {
      const res = await submitResultAPI(
        sessionId,
        evaluationId,
        videoId,
        timeMs,
      );
      alert(`Success! Server msg: ${JSON.stringify(res.remote_response)}`);
    } catch (err) {
      alert(`Submit Failed: ${err.message}`);
    }
  });

  // Logic Update Input khi video chạy
  const updateFrameInfo = () => {
    if (!elements.modalVideoPlayer.duration) return;

    const currentFrame = Math.round(
      elements.modalVideoPlayer.currentTime * frameRate,
    );
    const totalFrames = Math.floor(
      elements.modalVideoPlayer.duration * frameRate,
    );

    if (document.activeElement !== frameInput) {
      frameInput.value = currentFrame;
    }
    totalFramesSpan.textContent = `/ ${isNaN(totalFrames) ? "..." : totalFrames}`;
  };

  elements.modalVideoPlayer.addEventListener("timeupdate", updateFrameInfo);
  elements.modalVideoPlayer.addEventListener("loadedmetadata", updateFrameInfo);

  // Nhảy frame khi Enter
  frameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const targetFrame = parseInt(frameInput.value, 10);
      if (!isNaN(targetFrame) && targetFrame >= 0) {
        elements.modalVideoPlayer.currentTime = targetFrame / frameRate;
        elements.modalVideoPlayer.pause();
      }
      frameInput.blur();
    }
  });

  // Next/Prev logic
  const handleFrameStep = (direction) => {
    elements.modalVideoPlayer.pause();
    const currentFrame = Math.round(
      elements.modalVideoPlayer.currentTime * frameRate,
    );
    const nextFrame = currentFrame + direction;
    let nextTime = nextFrame / frameRate + 0.0001;
    nextTime = Math.max(0, nextTime);
    elements.modalVideoPlayer.currentTime = nextTime;
  };

  const prevBtn = document.getElementById("prev-frame-btn");
  const nextBtn = document.getElementById("next-frame-btn");

  prevBtn.addEventListener("click", () => handleFrameStep(-1));
  nextBtn.addEventListener("click", () => handleFrameStep(1));

  const handleKeyPress = (e) => {
    if (elements.modalOverlay.classList.contains("hidden")) return;
    if (document.activeElement === frameInput) return;

    if (e.key === "ArrowLeft") handleFrameStep(-1);
    if (e.key === "ArrowRight") handleFrameStep(1);
    if (e.key === " ") {
      e.preventDefault();
      elements.modalVideoPlayer.paused
        ? elements.modalVideoPlayer.play()
        : elements.modalVideoPlayer.pause();
    }
    if (e.key === "Escape") closeModal();
  };
  document.addEventListener("keydown", handleKeyPress);

  // Cleanup Handlers
  elements.modalOverlay.dataset.handlersAttached = "true";
  elements.modalOverlay._cleanupHandlers = {
    handleKeyPress,
    timelineBar,
    frameControls,
    previewVideo,
    previewHls,
    mainHls,
    updateProgress,
    updateFrameInfo,
  };
}

export function closeModal() {
  if (elements.modalOverlay.classList.contains("hidden")) return;

  if (elements.modalOverlay.dataset.handlersAttached === "true") {
    const h = elements.modalOverlay._cleanupHandlers;
    if (h) {
      document.removeEventListener("keydown", h.handleKeyPress);
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

      if (h.previewHls) h.previewHls.destroy();
      if (h.mainHls) h.mainHls.destroy();

      if (h.previewVideo) {
        h.previewVideo.removeAttribute("src");
        h.previewVideo.load();
        h.previewVideo.remove();
      }
    }
    delete elements.modalOverlay._cleanupHandlers;
    delete elements.modalOverlay.dataset.handlersAttached;
  }

  currentOpenVideoId = null;

  elements.modalOverlay.classList.add("hidden");
  elements.modalVideoPlayer.pause();
  elements.modalVideoPlayer.removeAttribute("src");
  elements.modalVideoPlayer.load();
  elements.modalVideoTitle.textContent = "";
}
