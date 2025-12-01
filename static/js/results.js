import { elements } from "./elements.js";
import { openModal } from "./video-player.js";
import { submitResultAPI } from "./api.js";

// Helper: Shuffle array
function shuffleArray(array) {
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
  return array;
}

export function displayResults(results, groupShots = false) {
  elements.resultsContainer.innerHTML = "";

  if (!results || results.length === 0) {
    elements.resultsContainer.innerHTML =
      '<p style="padding:10px;">No results found.</p>';
    return;
  }

  if (groupShots) {
    displayGroupedResults(results);
  } else {
    displayFlatResults(results);
  }
}

// --- HIỂN THỊ DẠNG DANH SÁCH THƯỜNG ---
function displayFlatResults(results) {
  const isSorted = true;
  results.forEach((item) => {
    const resultElement = document.createElement("div");
    resultElement.classList.add("result-item");

    // DATA ATTRIBUTE ĐỂ HIGHLIGHT
    resultElement.dataset.videoId = item.video_id;
    resultElement.dataset.keyframeIndex = item.keyframe_index;

    const imageUrl = `/keyframes/${item.video_id}/keyframe_${item.keyframe_index}.webp`;

    // Hover Preview
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

    resultElement.innerHTML = `
            <img src="${imageUrl}" class="result-item-image" onerror="this.onerror=null;this.src='/static/placeholder.png';">
            <div class="result-info">
                <h3>${item.video_id} / ${item.keyframe_index}</h3>
                <div class="result-scores">
                    <span>FPS: ${item.fps}</span>
                    <span class="${isSorted ? "sorted-by" : ""}">Clip: ${
                      item.clip_score ? item.clip_score.toFixed(4) : "N/A"
                    }</span>
                </div>
                <button class="card-submit-btn" type="button">Submit</button>
            </div>`;
    resultElement.insertBefore(previewContainer, resultElement.firstChild);

    // HLS Hover
    setupHoverPreview(resultElement, previewVideo, item);

    // Click Submit
    const submitBtn = resultElement.querySelector(".card-submit-btn");
    submitBtn.addEventListener("click", (e) => handleSubmit(e, item));

    // Click Open Modal
    resultElement.addEventListener("click", () => {
      const fps = parseFloat(item.fps) || 25;
      let startTime = item.keyframe_index / fps;
      startTime = Math.max(0, startTime - 0.5);
      openModal(item.video_id, startTime, fps, null);
    });

    elements.resultsContainer.appendChild(resultElement);
  });
}

// --- HIỂN THỊ DẠNG GROUP SHOTS ---
function displayGroupedResults(results) {
  // 1. Grouping
  const groups = {}; // key: "video_id|start|end"

  results.forEach((item) => {
    const vId = item.video_id;
    const sStart = item.shot_start_frame;
    const sEnd = item.shot_end_frame;
    const key = `${vId}|${sStart}|${sEnd}`;

    if (!groups[key]) {
      groups[key] = {
        video_id: vId,
        start_frame: sStart,
        end_frame: sEnd,
        fps: item.fps,
        max_score: -1,
        items: [],
      };
    }
    groups[key].items.push(item);
    if (item.clip_score > groups[key].max_score) {
      groups[key].max_score = item.clip_score;
    }
  });

  // 2. Sorting by max_score
  const sortedGroups = Object.values(groups).sort(
    (a, b) => b.max_score - a.max_score,
  );

  // 3. Rendering
  sortedGroups.forEach((group) => {
    const card = document.createElement("div");
    card.classList.add("shot-group-card");

    // DATA ATTRIBUTE ĐỂ HIGHLIGHT
    const shotKey = `${group.video_id}|${group.start_frame}|${group.end_frame}`;
    card.setAttribute("data-shot-key", shotKey);

    // Chọn ảnh thumbnail
    const shuffledItems = shuffleArray([...group.items]);
    let thumbnailItems = shuffledItems.slice(0, 4);

    // FIX: Nếu có 3 ảnh -> chỉ lấy 2 ảnh
    if (thumbnailItems.length === 3) {
      thumbnailItems = thumbnailItems.slice(0, 2);
    }

    // Grid class (items-2 sẽ được CSS xếp ngang)
    const gridClass = `items-${thumbnailItems.length}`;
    let gridHTML = `<div class="shot-thumbnails-grid ${gridClass}">`;

    thumbnailItems.forEach((itm) => {
      gridHTML += `<img src="/keyframes/${itm.video_id}/keyframe_${itm.keyframe_index}.webp" loading="lazy">`;
    });
    gridHTML += `</div>`;

    const infoHTML = `
            <div class="shot-info">
                <h3>${group.video_id}</h3>
                <div class="shot-stats">
                    Shot: ${group.start_frame} - ${group.end_frame}<br>
                    Top Score: ${group.max_score.toFixed(4)}<br>
                    Matches: ${group.items.length}
                </div>
            </div>
        `;

    card.innerHTML = gridHTML + infoHTML;

    // Click Event
    card.addEventListener("click", () => {
      // Tìm frame điểm cao nhất
      const bestFrame = group.items.reduce((prev, current) =>
        prev.clip_score > current.clip_score ? prev : current,
      );

      const fps = parseFloat(group.fps) || 25;
      let startTime = bestFrame.keyframe_index / fps;
      startTime = Math.max(0, startTime - 0.5);

      const shotData = {
        items: group.items,
        shotStart: group.start_frame,
        shotEnd: group.end_frame,
      };

      openModal(group.video_id, startTime, fps, shotData);
    });

    elements.resultsContainer.appendChild(card);
  });
}

// --- HELPER FUNCTIONS ---
function setupHoverPreview(element, videoEl, item) {
  let hls = null;
  let hoverTimeout;

  const cleanup = () => {
    if (hls) {
      hls.destroy();
      hls = null;
    }
    videoEl.pause();
    videoEl.removeAttribute("src");
    videoEl.load();
  };

  element.addEventListener("mouseenter", () => {
    hoverTimeout = setTimeout(() => {
      const videoId = item.video_id;
      const fps = item.fps || 25;
      const startTime = Math.max(0, item.keyframe_index / fps - 1.5);
      const hlsUrl = `/hls/${videoId}/playlist.m3u8?t=${Date.now()}`;

      if (Hls.isSupported()) {
        hls = new Hls({
          startPosition: startTime,
          capLevelToPlayerSize: true,
          maxBufferLength: 5,
        });
        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          videoEl.play().catch((e) => {});
        });
        hls.attachMedia(videoEl);
        hls.loadSource(hlsUrl);
      } else if (videoEl.canPlayType("application/vnd.apple.mpegurl")) {
        videoEl.src = hlsUrl;
        videoEl.currentTime = startTime;
        videoEl.play().catch((e) => {});
      }
    }, 200);
  });

  element.addEventListener("mouseleave", () => {
    clearTimeout(hoverTimeout);
    cleanup();
  });
}

async function handleSubmit(e, item) {
  e.stopPropagation();
  const sessionId = localStorage.getItem("sessionId");
  const evaluationId = localStorage.getItem("evaluationId");

  if (!sessionId || !evaluationId) {
    alert("Please LOGIN first!");
    return;
  }

  const confirmSubmit = confirm(
    `Submit frame ${item.keyframe_index} of ${item.video_id}?`,
  );
  if (!confirmSubmit) return;

  const fps = parseFloat(item.fps) || 25.0;
  const timeMs = Math.round((item.keyframe_index / fps) * 1000);

  try {
    const res = await submitResultAPI(
      sessionId,
      evaluationId,
      item.video_id,
      timeMs,
    );
    alert(`Success! ${JSON.stringify(res.remote_response)}`);
  } catch (err) {
    alert(`Submit Failed: ${err.message}`);
  }
}
