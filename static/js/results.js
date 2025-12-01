import { elements } from "./elements.js";
import { openModal } from "./video-player.js";
import { submitResultAPI } from "./api.js";

export function displayResults(results) {
  if (!results || results.length === 0) {
    elements.resultsContainer.innerHTML =
      '<p style="padding:10px;">No results found.</p>';
    return;
  }

  // Mock variable để giữ màu highlight cho Clip Score
  const isSorted = true;
  elements.resultsContainer.innerHTML = "";

  results.forEach((item) => {
    const resultElement = document.createElement("div");
    resultElement.classList.add("result-item");

    // Metadata
    resultElement.dataset.videoId = item.video_id;
    resultElement.dataset.keyframeIndex = item.keyframe_index;
    resultElement.dataset.fps = item.fps;
    resultElement.style.cursor = "pointer";

    const imageUrl = `/keyframes/${item.video_id}/keyframe_${item.keyframe_index}.webp`;

    // Hover Preview Setup (Video ẩn để hover)
    const previewContainer = document.createElement("div");
    previewContainer.className = "hover-preview";
    const previewVideo = document.createElement("video");
    previewVideo.muted = true;
    previewVideo.playsInline = true;
    Object.assign(previewVideo.style, {
      width: "100%",
      height: "100%",
      objectFit: "cover",
    });
    previewContainer.appendChild(previewVideo);

    // --- HTML Cấu trúc Card ---
    resultElement.innerHTML = `
        <img 
            src="${imageUrl}" 
            alt="Frame from ${item.video_id}" 
            class="result-item-image" 
            onerror="this.onerror=null;this.src='/static/placeholder.png';"
        >
        <div class="result-info">
            <h3>${item.video_id} / ${item.keyframe_index}</h3>
            <div class="result-scores">
                <span>FPS: ${item.fps}</span>
                ${["clip_score"]
                  .map((score) => {
                    const val = item[score] ? item[score].toFixed(4) : "N/A";
                    return `<span class="${isSorted ? "sorted-by" : ""}">Clip: ${val}</span>`;
                  })
                  .join("")}
            </div>
            <button class="card-submit-btn" type="button">Submit</button>
        </div>`;

    resultElement.insertBefore(previewContainer, resultElement.firstChild);

    // --- HLS Hover Logic (Giữ nguyên) ---
    let hls = null;
    let hoverTimeout;
    const cleanupHls = () => {
      // console.log("Cleaning up HLS instance");
      if (hls) {
        hls.destroy();
        hls = null;
      }
      previewVideo.pause();
      previewVideo.removeAttribute("src");
      previewVideo.load();
    };

    resultElement.addEventListener("mouseenter", () => {
      hoverTimeout = setTimeout(() => {
        const videoId = item.video_id;
        const fps = item.fps || 25;
        const startTime = Math.max(0, item.keyframe_index / fps - 1.5);
        const hlsUrl = `/hls/${videoId}/playlist.m3u8?t=${Date.now()}`;
        // console.log(`Hovering on ${videoId}, starting at ${startTime}s`);
        if (Hls.isSupported()) {
          // cleanupHls();
          hls = new Hls({
            startPosition: startTime,
            capLevelToPlayerSize: true,
            // autoStartLoad: true,
            maxBufferLength: 5,
          });

          hls.on(Hls.Events.MANIFEST_PARSED, () => {
            previewVideo.play().catch(e => {
              console.warn('Autoplay failed:', e);
            });
          });
          
          hls.attachMedia(previewVideo);
          hls.loadSource(hlsUrl);
          
        } else if (previewVideo.canPlayType("application/vnd.apple.mpegurl")) {
          previewVideo.src = hlsUrl;
          previewVideo.currentTime = startTime;
          previewVideo.play().catch(e => {
            console.warn('Autoplay failed:', e);
          });
        }
      }, 200);
    });

    resultElement.addEventListener("mouseleave", () => {
      clearTimeout(hoverTimeout);
      cleanupHls();
    });

    // --- XỬ LÝ SỰ KIỆN CLICK ---

    // 1. Click nút Submit trên Card
    const submitBtn = resultElement.querySelector(".card-submit-btn");
    submitBtn.addEventListener("click", async (e) => {
      e.stopPropagation(); // Ngăn mở modal

      const sessionId = localStorage.getItem("sessionId");
      const evaluationId = localStorage.getItem("evaluationId");

      if (!sessionId || !evaluationId) {
        alert("Please LOGIN first!");
        return;
      }

      const confirmSubmit = confirm(
        `Submit frame ${item.keyframe_index} of video ${item.video_id}?`,
      );
      if (!confirmSubmit) return;

      // TÍNH TOÁN THỜI GIAN (MS)
      // Công thức: (Frame Index / FPS) * 1000
      const fps = parseFloat(item.fps) || 25.0;
      const timeMs = Math.round((item.keyframe_index / fps) * 1000);

      try {
        const res = await submitResultAPI(
          sessionId,
          evaluationId,
          item.video_id,
          timeMs,
        );
        alert(`Success! Server msg: ${JSON.stringify(res.remote_response)}`);
      } catch (err) {
        alert(`Submit Failed: ${err.message}`);
      }
    });

    // 2. Click vào vùng còn lại -> Mở Video Modal
    resultElement.addEventListener("click", () => {
      const fps = parseFloat(item.fps) || 25;
      let startTime = item.keyframe_index / fps;
      startTime = Math.max(0, startTime - 0.5);
      openModal(item.video_id, startTime, fps);
    });

    elements.resultsContainer.appendChild(resultElement);
  });
}
