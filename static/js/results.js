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
  const scoreLabels = {
    fused_score: "Fused",
    clip_score: "CLIP",
    beit3_score: "BEiT-3",
  };

  results.forEach((item) => {
    const resultElement = document.createElement("div");
    resultElement.classList.add("result-item");
    resultElement.dataset.videoId = item.video_id;
    resultElement.dataset.keyframeIndex = item.keyframe_index;

    const imageUrl = `/keyframes/${item.video_id}/keyframe_${item.keyframe_index}.webp`;

    // 1. Hover Preview Container
    const previewContainer = document.createElement("div");
    previewContainer.className = "hover-preview";
    const previewVideo = document.createElement("video");
    previewVideo.muted = true;
    previewVideo.playsInline = true;
    // Style inline để đảm bảo object-fit
    Object.assign(previewVideo.style, {
      width: "100%",
      height: "100%",
      objectFit: "cover",
    });
    previewContainer.appendChild(previewVideo);

    // 2. Nội dung Card
    const infoHTML = `
            <img src="${imageUrl}" class="result-item-image" onerror="this.onerror=null;this.src='/static/placeholder.png';">
            <div class="result-info">
                <h3>${item.video_id} / ${item.keyframe_index}</h3>
                <div class="result-scores">
                    <span>FPS: ${item.fps}</span>
                    ${["fused_score", "clip_score", "beit3_score"]
                      .map((score) => {
                        const val = item[score] ? item[score].toFixed(3) : null;
                        return val
                          ? `<span>${scoreLabels[score]}: ${val}</span>`
                          : "";
                      })
                      .join("")}
                </div>
                ${item.temporal_sequence ? `<div style="font-size:11px; color:blue; margin-top:2px; font-weight:bold;">🔗 Sequence: ${item.temporal_sequence.length} events</div>` : ""}
                <button class="card-submit-btn" type="button">Submit</button>
            </div>`;

    resultElement.innerHTML = infoHTML;

    // Chèn Preview vào đầu (để nó đè lên ảnh nhờ CSS absolute)
    resultElement.insertBefore(previewContainer, resultElement.firstChild);

    // Setup Hover logic
    setupHoverPreview(resultElement, previewVideo, item);

    // Submit Handler
    const submitBtn = resultElement.querySelector(".card-submit-btn");
    submitBtn.addEventListener("click", (e) => handleSubmit(e, item));

    // Open Modal
    resultElement.addEventListener("click", () => {
      const fps = parseFloat(item.fps) || 25;
      let startTime = item.keyframe_index / fps;
      startTime = Math.max(0, startTime - 0.5);

      // Truyền sequenceData vào tham số cuối
      openModal(
        item.video_id,
        startTime,
        fps,
        null,
        item.keyframe_index,
        item.temporal_sequence,
      );
    });

    elements.resultsContainer.appendChild(resultElement);
  });
}

// --- HIỂN THỊ DẠNG GROUP SHOTS ---
function displayGroupedResults(results) {
  const groups = {};
  const criteria = elements.criteriaSelect.value || "fused_score";
  const threshold = 0.3;

  // Grouping Logic
  results.forEach((item) => {
    const key = `${item.video_id}|${item.shot_start_frame}|${item.shot_end_frame}`;
    if (!groups[key]) {
      groups[key] = {
        video_id: item.video_id,
        start_frame: item.shot_start_frame,
        end_frame: item.shot_end_frame,
        fps: item.fps,
        shot_score: 0,
        items: [],
        num_valid_items: 0,
      };
    }
    groups[key].items.push(item);
    if (item[criteria] > threshold) {
      groups[key].shot_score += item[criteria];
      groups[key].num_valid_items += 1;
    }
  });

  const sortedGroups = Object.values(groups).sort(
    (a, b) => b.shot_score - a.shot_score,
  );

  sortedGroups.forEach((group) => {
    const card = document.createElement("div");
    card.classList.add("shot-group-card"); // Class này sẽ có position relative
    const shotKey = `${group.video_id}|${group.start_frame}|${group.end_frame}`;
    card.setAttribute("data-shot-key", shotKey);

    // Tìm best frame để lấy làm đại diện video preview và tính start time
    const bestFrame = group.items.reduce(
      (prev, current) =>
        (prev[criteria] || 0) > (current[criteria] || 0) ? prev : current,
      group.items[0],
    );

    // 1. Hover Preview Container (Giống Flat Result)
    const previewContainer = document.createElement("div");
    previewContainer.className = "hover-preview"; // CSS class này đã có sẵn absolute full size
    const previewVideo = document.createElement("video");
    previewVideo.muted = true;
    previewVideo.playsInline = true;
    Object.assign(previewVideo.style, {
      width: "100%",
      height: "100%",
      objectFit: "cover",
    });
    previewContainer.appendChild(previewVideo);

    // 2. Grid Thumbnails
    let thumbnailItems = shuffleArray([...group.items]).slice(0, 4);
    if (thumbnailItems.length === 3)
      thumbnailItems = thumbnailItems.slice(0, 2);
    const gridClass = `items-${thumbnailItems.length}`;

    let gridHTML = `<div class="shot-thumbnails-grid ${gridClass}">`;
    thumbnailItems.forEach((itm) => {
      gridHTML += `<img src="/keyframes/${itm.video_id}/keyframe_${itm.keyframe_index}.webp" loading="lazy">`;
    });
    gridHTML += `</div>`;

    // 3. Info
    const infoHTML = `
            <div class="shot-info">
                <h3>${group.video_id}</h3>
                <div class="shot-stats">
                    Shot: ${group.start_frame} - ${group.end_frame}<br>
                    Score: ${group.shot_score.toFixed(2)} | Matches: ${group.num_valid_items}
                </div>
            </div>
        `;

    // Ghép HTML: Preview (ẩn) -> Grid (hiện) -> Info
    card.innerHTML = gridHTML + infoHTML;
    // Chèn Preview lên đầu để CSS absolute đè lên Grid
    card.insertBefore(previewContainer, card.firstChild);

    // --- SETUP HOVER ---
    // Gọi hàm setup giống hệt flat list
    setupHoverPreview(card, previewVideo, bestFrame);

    // Click Event
    card.addEventListener("click", () => {
      const fps = parseFloat(group.fps) || 25;
      let startTime = bestFrame.keyframe_index / fps;
      startTime = Math.max(0, startTime - 0.5);

      const shotData = {
        items: group.items,
        shotStart: group.start_frame,
        shotEnd: group.end_frame,
      };

      // Group shot không có sequenceData (hoặc có thể có nếu logic phức tạp hơn, tạm để null)
      openModal(group.video_id, startTime, fps, shotData, null, null);
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
    // Reset lại trạng thái ẩn video khi chuột rời đi
    videoEl.classList.remove("is-playing");
    videoEl.style.opacity = 0;
  };

  // Hàm xử lý khi video đã thực sự có hình
  const onVideoReady = () => {
    videoEl.classList.add("is-playing");
    videoEl.style.opacity = 1;
  };

  element.addEventListener("mouseenter", () => {
    hoverTimeout = setTimeout(() => {
      const videoId = item.video_id;
      const fps = item.fps || 25;
      const startTime = Math.max(0, item.keyframe_index / fps - 1.0); // Preview trước 1s
      const hlsUrl = `/hls/${videoId}/playlist.m3u8`;

      // Lắng nghe sự kiện timeupdate hoặc playing để hiện video
      // timeupdate > 0 nghĩa là frame đã chạy, đảm bảo không bị màn hình đen
      videoEl.removeEventListener("timeupdate", onVideoReady); // Xóa listener cũ tránh duplicate
      videoEl.addEventListener("timeupdate", function checkFrame() {
        if (videoEl.currentTime > 0) {
          onVideoReady();
          videoEl.removeEventListener("timeupdate", checkFrame);
        }
      });

      if (Hls.isSupported()) {
        hls = new Hls({
          startPosition: startTime,
          capLevelToPlayerSize: true,
          maxBufferLength: 2,
        });
        hls.loadSource(hlsUrl);
        hls.attachMedia(videoEl);
        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          videoEl.muted = true;
          videoEl.play().catch((e) => {});
        });
      } else if (videoEl.canPlayType("application/vnd.apple.mpegurl")) {
        videoEl.src = hlsUrl;
        videoEl.currentTime = startTime;
        videoEl.play().catch((e) => {});
      }
    }, 200); // Delay nhẹ tránh spam
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
    alert(`Success!`);
  } catch (err) {
    alert(`Submit Failed: ${err.message}`);
  }
}
