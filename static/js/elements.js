export const elements = {
  searchForm: document.getElementById("search-form"),
  toggleFiltersBtn: document.getElementById("toggle-filters-btn"),
  advancedFilters: document.getElementById("advanced-filters"),

  // Criteria Filter
  criteriaSelect: document.getElementById("criteria-select"),

  // Object Filter Inputs
  addObjectBtn: document.getElementById("add-object-btn"),
  objectList: document.getElementById("object-list"),
  objectSelect: document.getElementById("object-select"),
  objectMin: document.getElementById("object-min"),
  objectMax: document.getElementById("object-max"),
  objectConfidence: document.getElementById("object-confidence"),

  loginBtn: document.getElementById("login-btn"),

  // Modal Submit
  modalSubmitBtn: document.getElementById("modal-submit-btn"),

  // Results & Controls
  resultsContainer: document.getElementById("results-container"),
  sortBySelect: { value: "clip_score" },
  sortControlsBar: document.getElementById("sort-controls-bar"),
  // sortByClipBtn: document.getElementById("sort-by-clip-btn"),
  sortByShotBtn: document.getElementById("sort-by-shot-btn"),

  // Video Modal
  modalOverlay: document.getElementById("video-modal"),
  closeModalBtn: document.getElementById("close-modal-btn"),
  modalVideoPlayer: document.getElementById("modal-video-player"),
  modalVideoTitle: document.getElementById("modal-video-title"),
  modalContent: document.querySelector(".modal-content"),

  // --- NEW: Evaluation Modal ---
  evalModal: document.getElementById("evaluation-modal"),
  evalListContainer: document.getElementById("evaluation-list"),
  cancelEvalBtn: document.getElementById("cancel-eval-btn"),
};
