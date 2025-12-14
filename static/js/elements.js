export const elements = {
  searchForm: document.getElementById("search-form"),
  queryInputsContainer: document.getElementById("query-inputs-container"), // NEW
  addQueryBtn: document.getElementById("add-query-btn"), // NEW

  toggleFiltersBtn: document.getElementById("toggle-filters-btn"),
  advancedFilters: document.getElementById("advanced-filters"),

  // Group Shots Toggle
  toggleGroupShotsBtn: document.getElementById("toggle-group-shots-btn"),

  // Criteria Select
  criteriaSelect: document.getElementById("criteria-select"),

  // Object Filter Inputs
  addObjectBtn: document.getElementById("add-object-btn"),
  objectList: document.getElementById("object-list"),
  objectSelect: document.getElementById("object-select"),
  objectMin: document.getElementById("object-min"),
  objectMax: document.getElementById("object-max"),
  objectConfidence: document.getElementById("object-confidence"),

  loginBtn: document.getElementById("login-btn"),

  // Results & Controls
  resultsContainer: document.getElementById("results-container"),

  // Video Modal
  modalOverlay: document.getElementById("video-modal"),
  closeModalBtn: document.getElementById("close-modal-btn"),
  modalVideoPlayer: document.getElementById("modal-video-player"),
  modalVideoTitle: document.getElementById("modal-video-title"),

  // Sidebar containers
  modalContentWrapper: document.querySelector(".modal-content-wrapper"),
  modalPlayerSection: document.querySelector(".modal-player-section"),
  modalShotList: document.getElementById("modal-shot-list"),

  // Evaluation Modal
  evalModal: document.getElementById("evaluation-modal"),
  evalListContainer: document.getElementById("evaluation-list"),
  cancelEvalBtn: document.getElementById("cancel-eval-btn"),
};
