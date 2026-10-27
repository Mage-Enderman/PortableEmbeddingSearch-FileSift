// FileSift Frontend Application Logic with Grid View & Multimodal Search
document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const spotlightBar = document.querySelector(".spotlight-bar");
  const searchInput = document.getElementById("search-input");
  const clearSearchBtn = document.getElementById("clear-search-btn");
  const mediaUploadBtn = document.getElementById("media-upload-btn");
  const mediaFileInput = document.getElementById("media-file-input");
  const attachedMediaPill = document.getElementById("attached-media-pill");
  const attachedMediaThumb = document.getElementById("attached-media-thumb");
  const attachedMediaName = document.getElementById("attached-media-name");
  const removeMediaBtn = document.getElementById("remove-media-btn");

  // Negative / Inverse Media Elements
  const negMediaUploadBtn = document.getElementById("neg-media-upload-btn");
  const negMediaFileInput = document.getElementById("neg-media-file-input");
  const attachedNegMediaPill = document.getElementById("attached-neg-media-pill");
  const attachedNegThumb = document.getElementById("attached-neg-thumb");
  const attachedNegName = document.getElementById("attached-neg-name");
  const removeNegMediaBtn = document.getElementById("remove-neg-media-btn");

  const foldersModalBtn = document.getElementById("folders-modal-btn");
  const folderCountBadge = document.getElementById("folder-count-badge");
  const filterChips = document.querySelectorAll(".filter-chips .chip");
  const statsPill = document.getElementById("stats-pill");
  const modelText = document.getElementById("model-text");

  const viewListBtn = document.getElementById("view-list-btn");
  const viewGridBtn = document.getElementById("view-grid-btn");

  const emptyState = document.getElementById("empty-state");
  const resultsList = document.getElementById("results-list");
  const noResults = document.getElementById("no-results");
  const noResultsQuery = document.getElementById("no-results-query");

  const indexingBanner = document.getElementById("indexing-banner");
  const indexProgressBar = document.getElementById("index-progress-bar");
  const indexStatusLabel = document.getElementById("index-status-label");
  const indexPctLabel = document.getElementById("index-pct-label");
  const indexCurrentFile = document.getElementById("index-current-file");
  const cancelIndexBtn = document.getElementById("cancel-index-btn");

  const previewDrawer = document.getElementById("preview-drawer");
  const closeDrawerBtn = document.getElementById("close-drawer-btn");
  const previewFilename = document.getElementById("preview-filename");
  const previewMeta = document.getElementById("preview-meta");
  const previewPath = document.getElementById("preview-path");
  const previewLoc = document.getElementById("preview-loc");
  const previewContent = document.getElementById("preview-content");
  const previewOpenFileBtn = document.getElementById("preview-open-file-btn");
  const previewOpenFolderBtn = document.getElementById("preview-open-folder-btn");
  const previewHideExtBtn = document.getElementById("preview-hide-ext-btn");

  const foldersModal = document.getElementById("folders-modal");
  const closeModalBtn = document.getElementById("close-modal-btn");
  const modalDoneBtn = document.getElementById("modal-done-btn");
  const browseFolderBtn = document.getElementById("browse-folder-btn");
  const manualFolderInput = document.getElementById("manual-folder-input");
  const manualAddBtn = document.getElementById("manual-add-btn");
  const foldersList = document.getElementById("folders-list");
  const modalDbStats = document.getElementById("modal-db-stats");
  const syncChangesBtn = document.getElementById("sync-changes-btn");
  const reindexAllBtn = document.getElementById("reindex-all-btn");

  // State
  let currentFilter = "all";
  let currentView = "list"; // 'list' or 'grid'
  let activeIndex = -1;
  let searchTimeout = null;
  let currentResults = [];
  let currentActiveResult = null;
  let attachedMediaFile = null;
  let attachedNegMediaFile = null;

  // Initialize
  fetchStatus();
  fetchFolders();
  startStatusPolling();

  // Search Input Event
  searchInput.addEventListener("input", (e) => {
    const query = e.target.value.trim();
    clearSearchBtn.style.display = query || attachedMediaFile ? "block" : "none";

    clearTimeout(searchTimeout);
    if (!query && !attachedMediaFile) {
      showEmptyState();
      return;
    }

    searchTimeout = setTimeout(() => {
      if (attachedMediaFile) {
        performMediaSearch(attachedMediaFile, currentFilter);
      } else {
        performSearch(query, currentFilter);
      }
    }, 200);
  });

  clearSearchBtn.addEventListener("click", () => {
    searchInput.value = "";
    detachMediaFile();
    clearSearchBtn.style.display = "none";
    showEmptyState();
    searchInput.focus();
  });

  // Multimodal Media Query Upload
  mediaUploadBtn.addEventListener("click", () => {
    mediaFileInput.click();
  });

  mediaFileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handleMediaFileSelection(e.target.files[0]);
    }
  });

  removeMediaBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    detachMediaFile();
    const query = searchInput.value.trim();
    if (query) {
      performSearch(query, currentFilter);
    } else {
      showEmptyState();
    }
  });

  // Inverse / Negative Media Query Upload
  negMediaUploadBtn.addEventListener("click", () => {
    negMediaFileInput.click();
  });

  negMediaFileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handleNegMediaFileSelection(e.target.files[0]);
    }
  });

  removeNegMediaBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    detachNegMediaFile();
    if (attachedMediaFile) {
      performMediaSearch(attachedMediaFile, currentFilter);
    } else {
      const query = searchInput.value.trim();
      if (query) {
        performSearch(query, currentFilter);
      } else {
        showEmptyState();
      }
    }
  });

  function handleNegMediaFileSelection(file) {
    attachedNegMediaFile = file;
    attachedNegMediaPill.style.display = "flex";
    attachedNegName.textContent = file.name;
    clearSearchBtn.style.display = "block";

    if (file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = (e) => {
        attachedNegThumb.src = e.target.result;
        attachedNegThumb.style.display = "block";
      };
      reader.readAsDataURL(file);
    } else {
      attachedNegThumb.style.display = "none";
    }

    if (attachedMediaFile) {
      performMediaSearch(attachedMediaFile, currentFilter);
    } else {
      const query = searchInput.value.trim() || "all";
      performSearch(query, currentFilter);
    }
  }

  function detachNegMediaFile() {
    attachedNegMediaFile = null;
    attachedNegMediaPill.style.display = "none";
    negMediaFileInput.value = "";
  }

  function handleMediaFileSelection(file) {
    attachedMediaFile = file;
    attachedMediaPill.style.display = "flex";
    attachedMediaName.textContent = file.name;
    clearSearchBtn.style.display = "block";

    if (file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = (e) => {
        attachedMediaThumb.src = e.target.result;
        attachedMediaThumb.style.display = "block";
      };
      reader.readAsDataURL(file);
    } else {
      attachedMediaThumb.style.display = "none";
    }

    // Switch view to grid if searching with an image
    if (file.type.startsWith("image/") && currentView !== "grid") {
      setView("grid");
    }

    performMediaSearch(file, currentFilter);
  }

  function detachMediaFile() {
    attachedMediaFile = null;
    attachedMediaPill.style.display = "none";
    mediaFileInput.value = "";
  }

  // Drag and Drop Files onto Search Bar
  window.addEventListener("dragover", (e) => {
    e.preventDefault();
    spotlightBar.classList.add("drag-over");
  });

  window.addEventListener("dragleave", (e) => {
    if (e.relatedTarget === null) {
      spotlightBar.classList.remove("drag-over");
    }
  });

  window.addEventListener("drop", (e) => {
    e.preventDefault();
    spotlightBar.classList.remove("drag-over");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleMediaFileSelection(e.dataTransfer.files[0]);
    }
  });

  // Clipboard Paste Support (Ctrl+V with image)
  window.addEventListener("paste", (e) => {
    if (e.clipboardData && e.clipboardData.files && e.clipboardData.files.length > 0) {
      const file = e.clipboardData.files[0];
      handleMediaFileSelection(file);
    }
  });

  // View Mode Toggles
  viewListBtn.addEventListener("click", () => setView("list"));
  viewGridBtn.addEventListener("click", () => setView("grid"));

  function setView(view) {
    currentView = view;
    viewListBtn.classList.toggle("active", view === "list");
    viewGridBtn.classList.toggle("active", view === "grid");
    resultsList.classList.toggle("grid-mode", view === "grid");
    if (currentResults.length > 0) {
      renderResults(currentResults, searchInput.value || (attachedMediaFile ? attachedMediaFile.name : ""));
    }
  }

  // Filter Chips
  filterChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      filterChips.forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      currentFilter = chip.dataset.filter;

      // Auto switch to grid when Images or Videos filter is clicked
      if ((currentFilter === "images" || currentFilter === "videos") && currentView !== "grid") {
        setView("grid");
      }

      if (attachedMediaFile) {
        performMediaSearch(attachedMediaFile, currentFilter);
      } else {
        const query = searchInput.value.trim();
        if (query) {
          performSearch(query, currentFilter);
        }
      }
    });
  });

  // Sample Query Chips
  document.querySelectorAll(".sample-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      detachMediaFile();
      searchInput.value = chip.textContent.trim();
      clearSearchBtn.style.display = "block";
      performSearch(searchInput.value, currentFilter);
      searchInput.focus();
    });
  });

  // Keyboard Navigation
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (foldersModal.style.display === "flex") {
        closeModal();
      } else if (previewDrawer.classList.contains("open")) {
        closeDrawer();
      } else if (searchInput.value || attachedMediaFile) {
        searchInput.value = "";
        detachMediaFile();
        clearSearchBtn.style.display = "none";
        showEmptyState();
      }
      return;
    }

    if ((e.ctrlKey && e.key === "f") || (e.key === "/" && document.activeElement !== searchInput)) {
      e.preventDefault();
      searchInput.focus();
      searchInput.select();
      return;
    }

    if (currentResults.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((activeIndex + 1) % currentResults.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((activeIndex - 1 + currentResults.length) % currentResults.length);
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      const res = currentResults[activeIndex];
      if (e.ctrlKey) {
        openFolder(res.path);
      } else {
        openFile(res.path);
      }
    } else if (e.key === " " && activeIndex >= 0 && document.activeElement !== searchInput) {
      e.preventDefault();
      showPreview(currentResults[activeIndex]);
    }
  });

  // Text Search
  async function performSearch(query, kind) {
    try {
      const url = `/api/search?q=${encodeURIComponent(query)}&kind=${encodeURIComponent(kind)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Search failed");
      const data = await res.json();
      currentResults = data.results || [];
      renderResults(currentResults, query);
    } catch (err) {
      console.error("Search error:", err);
    }
  }

  // Multimodal Media Search (Image, Audio, Video) with Inverse Search Support
  async function performMediaSearch(file, kind) {
    try {
      emptyState.style.display = "none";
      noResults.style.display = "none";
      resultsList.style.display = "flex";
      const statusText = attachedNegMediaFile 
        ? `Embedding ${escapeHtml(file.name)} (excluding ${escapeHtml(attachedNegMediaFile.name)})...`
        : `Embedding ${escapeHtml(file.name)} and matching files...`;
      resultsList.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-muted);"><span class="spinner" style="display:inline-block; margin-right:8px;"></span>${statusText}</div>`;

      const formData = new FormData();
      formData.append("file", file);
      if (attachedNegMediaFile) {
        formData.append("neg_file", attachedNegMediaFile);
      }
      const rawQuery = searchInput.value.trim();
      if (rawQuery) {
        formData.append("neg_query", rawQuery);
      }

      const url = `/api/search-media?kind=${encodeURIComponent(kind)}&limit=35`;
      const res = await fetch(url, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) throw new Error("Media search failed");
      const data = await res.json();
      currentResults = data.results || [];
      const label = attachedNegMediaFile ? `${file.name} (not ${attachedNegMediaFile.name})` : file.name;
      renderResults(currentResults, `similar to ${label}`);
    } catch (err) {
      console.error("Media search error:", err);
      resultsList.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--accent-rose);">Error searching media: ${escapeHtml(err.message)}</div>`;
    }
  }

  function hideExtension(ext) {
    if (!ext) return;
    const cleanExt = ext.replace(".", "").toLowerCase();
    const token = `!${cleanExt}`;
    const cur = searchInput.value.trim();
    if (!cur.includes(token)) {
      searchInput.value = (cur ? cur + " " : "") + token;
      clearSearchBtn.style.display = "block";
      if (attachedMediaFile) {
        performMediaSearch(attachedMediaFile, currentFilter);
      } else {
        performSearch(searchInput.value.trim(), currentFilter);
      }
    }
  }

  function showEmptyState() {
    emptyState.style.display = "block";
    resultsList.style.display = "none";
    noResults.style.display = "none";
    currentResults = [];
    activeIndex = -1;
  }

  // Render Results (List or Grid mode)
  function renderResults(results, query) {
    emptyState.style.display = "none";
    if (results.length === 0) {
      resultsList.style.display = "none";
      noResults.style.display = "block";
      noResultsQuery.textContent = query;
      return;
    }

    noResults.style.display = "none";
    resultsList.style.display = currentView === "grid" ? "grid" : "flex";
    resultsList.innerHTML = "";
    activeIndex = -1;

    if (currentView === "grid") {
      renderGridResults(results);
    } else {
      renderListResults(results);
    }

    if (results.length > 0) {
      setActiveIndex(0);
    }
  }

  // Grid Renderer (Photo & Visual Cards)
  function renderGridResults(results) {
    results.forEach((r, idx) => {
      const card = document.createElement("div");
      card.className = "grid-card";
      card.dataset.index = idx;

      const isImage = r.kind === "images";
      const isVideo = r.kind === "videos" || r.kind === "video";
      const isAudio = r.kind === "audio";
      const tsQuery = (r.loc_start > 0 && isVideo) ? `&timestamp=${r.loc_start}` : "";
      const thumbUrl = `/api/thumbnail?path=${encodeURIComponent(r.path)}&size=360${tsQuery}`;
      const isKeyword = r.bm25_score > 0 && r.semantic_score < 0.3;
      const scoreText = isKeyword ? "Exact Match" : `${r.score_pct}% Match`;

      let thumbHtml = "";
      if (isImage || isVideo) {
        thumbHtml = `
          <div class="grid-thumb-box">
            <img class="grid-thumb" src="${thumbUrl}" alt="${escapeHtml(r.filename)}" loading="lazy" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';" />
            <div class="grid-placeholder" style="display: none;">${getKindIcon(r.kind, r.extension)}</div>
            <span class="grid-score-badge">${scoreText}</span>
          </div>
        `;
      } else if (isAudio) {
        thumbHtml = `
          <div class="grid-thumb-box" style="background: linear-gradient(135deg, rgba(56, 189, 248, 0.15), rgba(168, 85, 247, 0.15));">
            <div class="grid-placeholder">🎵</div>
            <span class="grid-score-badge">${scoreText}</span>
          </div>
        `;
      } else {
        thumbHtml = `
          <div class="grid-thumb-box">
            <div class="grid-placeholder">${getKindIcon(r.kind, r.extension)}</div>
            <span class="grid-score-badge">${scoreText}</span>
          </div>
        `;
      }

      card.innerHTML = `
        ${thumbHtml}
        <div class="grid-details">
          <span class="grid-filename" title="${escapeHtml(r.filename)}">${escapeHtml(r.filename)}</span>
          <div class="grid-meta">
            <span>${escapeHtml(r.loc_label)}</span>
            <button class="mini-btn hide-ext-btn" title="Exclude .${r.extension.replace('.', '')} from search">🚫 .${r.extension.replace('.', '')}</button>
          </div>
        </div>
      `;

      const hideBtn = card.querySelector(".hide-ext-btn");
      if (hideBtn) {
        hideBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          hideExtension(r.extension);
        });
      }

      card.addEventListener("click", () => {
        setActiveIndex(idx);
        showPreview(r);
      });

      card.addEventListener("dblclick", () => {
        openFile(r.path);
      });

      resultsList.appendChild(card);
    });
  }

  // List Renderer (Spotlight Cards with Photo Thumbnails)
  function renderListResults(results) {
    results.forEach((r, idx) => {
      const card = document.createElement("div");
      card.className = "result-card";
      card.dataset.index = idx;

      const kindIcon = getKindIcon(r.kind, r.extension);
      const isKeyword = r.bm25_score > 0 && r.semantic_score < 0.3;
      const scoreBadgeClass = isKeyword ? "score-badge keyword-match" : "score-badge";
      const scoreText = isKeyword ? "Exact Match" : `${r.score_pct}% Match`;
      const isImage = r.kind === "images";
      const isVideo = r.kind === "videos" || r.kind === "video";
      const isAudio = r.kind === "audio";
      const tsQuery = (r.loc_start > 0 && isVideo) ? `&timestamp=${r.loc_start}` : "";
      const thumbUrl = `/api/thumbnail?path=${encodeURIComponent(r.path)}&size=160${tsQuery}`;

      let contentSection = "";
      if (isImage || isVideo) {
        contentSection = `
          <div class="list-photo-row">
            <img class="list-thumb-img" src="${thumbUrl}" alt="" loading="lazy" onerror="this.style.display='none';" />
            <div class="result-snippet" style="flex:1;">${r.snippet}</div>
          </div>
        `;
      } else if (isAudio) {
        contentSection = `
          <div class="list-photo-row">
            <div style="width: 48px; height: 48px; display: flex; align-items: center; justify-content: center; background: rgba(56, 189, 248, 0.15); border-radius: var(--radius-sm); font-size: 1.4rem;">🎵</div>
            <div class="result-snippet" style="flex:1;">${r.snippet}</div>
          </div>
        `;
      } else {
        contentSection = `<div class="result-snippet">${r.snippet}</div>`;
      }

      card.innerHTML = `
        <div class="result-header">
          <span class="file-kind-badge">${kindIcon}</span>
          <div class="file-info">
            <div class="filename-row">
              <span class="filename" title="${escapeHtml(r.filename)}">${escapeHtml(r.filename)}</span>
              <span class="loc-badge">${escapeHtml(r.loc_label)}</span>
            </div>
            <span class="filepath" title="${escapeHtml(r.path)}">${escapeHtml(r.path)}</span>
          </div>
          <span class="${scoreBadgeClass}">${scoreText}</span>
        </div>
        ${contentSection}
        <div class="result-actions">
          <button class="mini-btn open-file-btn" title="Open in default program">
            <svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2" fill="none"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
            Open File
          </button>
          <button class="mini-btn open-folder-btn" title="Reveal in Explorer">
            <svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2" fill="none"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
            In Explorer
          </button>
          <button class="mini-btn hide-ext-btn" title="Exclude .${r.extension.replace('.', '')} from search">
            🚫 Hide .${r.extension.replace('.', '')}
          </button>
          <button class="mini-btn preview-btn" title="Quick preview (Space)">
            <svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2" fill="none"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
            Preview
          </button>
        </div>
      `;

      card.addEventListener("click", (e) => {
        if (e.target.closest("button")) return;
        setActiveIndex(idx);
        showPreview(r);
      });

      card.querySelector(".open-file-btn").addEventListener("click", (e) => {
        e.stopPropagation();
        openFile(r.path);
      });

      card.querySelector(".open-folder-btn").addEventListener("click", (e) => {
        e.stopPropagation();
        openFolder(r.path);
      });

      card.querySelector(".hide-ext-btn").addEventListener("click", (e) => {
        e.stopPropagation();
        hideExtension(r.extension);
      });

      card.querySelector(".preview-btn").addEventListener("click", (e) => {
        e.stopPropagation();
        setActiveIndex(idx);
        showPreview(r);
      });

      resultsList.appendChild(card);
    });
  }

  function setActiveIndex(idx) {
    if (idx < 0 || idx >= currentResults.length) return;
    activeIndex = idx;
    const cards = resultsList.querySelectorAll(currentView === "grid" ? ".grid-card" : ".result-card");
    cards.forEach((c, i) => {
      c.classList.toggle("active", i === activeIndex);
    });
    const activeCard = cards[activeIndex];
    if (activeCard) {
      activeCard.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }

  function getKindIcon(kind, ext) {
    switch (kind) {
      case "docs": return "📄";
      case "sheets": return "📊";
      case "code": return "💻";
      case "images": return "🖼️";
      case "videos":
      case "video": return "🎬";
      case "audio": return "🎵";
      default: return "📁";
    }
  }

  function escapeHtml(str) {
    return (str || "").replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[m]));
  }

  // Preview Drawer
  function showPreview(result) {
    currentActiveResult = result;
    previewFilename.textContent = result.filename;
    previewMeta.textContent = `${result.kind.toUpperCase()} • ${result.extension}`;
    previewPath.textContent = result.path;
    previewLoc.textContent = result.loc_label;
    if (previewHideExtBtn) {
      previewHideExtBtn.textContent = `🚫 Hide .${result.extension.replace('.', '')}`;
    }

    if (result.kind === "images") {
      const thumbUrl = `/api/thumbnail?path=${encodeURIComponent(result.path)}&size=800`;
      previewContent.innerHTML = `
        <div style="text-align: center; margin-bottom: 14px;">
          <img src="${thumbUrl}" style="max-width: 100%; max-height: 380px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); object-fit: contain;" />
        </div>
        <div style="font-size: 0.85rem; color: var(--text-muted); font-family: var(--font-sans); line-height: 1.5;">${escapeHtml(result.full_text)}</div>
      `;
    } else if (result.kind === "videos" || result.kind === "video") {
      const mediaUrl = `/api/stream-media?path=${encodeURIComponent(result.path)}`;
      const seekTime = result.loc_start > 0 ? result.loc_start : 0;
      previewContent.innerHTML = `
        <div style="text-align: center; margin-bottom: 14px;">
          <video id="preview-video-player" controls style="width: 100%; max-height: 340px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); background: #000;" src="${mediaUrl}"></video>
        </div>
        <div style="font-size: 0.85rem; color: var(--text-muted); font-family: var(--font-sans); line-height: 1.5;">
          <strong>Scene Moment: ${escapeHtml(result.loc_label)}</strong><br/>
          ${escapeHtml(result.full_text)}
        </div>
      `;
      const vid = document.getElementById("preview-video-player");
      if (vid && seekTime > 0) {
        vid.addEventListener("loadedmetadata", () => {
          vid.currentTime = seekTime;
        });
      }
    } else if (result.kind === "audio") {
      const mediaUrl = `/api/stream-media?path=${encodeURIComponent(result.path)}`;
      const seekTime = result.loc_start > 0 ? result.loc_start : 0;
      previewContent.innerHTML = `
        <div style="text-align: center; margin-bottom: 14px; padding: 16px; background: var(--bg-surface); border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
          <div style="font-size: 2rem; margin-bottom: 8px;">🎵</div>
          <audio id="preview-audio-player" controls autoplay style="width: 100%;" src="${mediaUrl}"></audio>
        </div>
        <div style="font-size: 0.85rem; color: var(--text-muted); font-family: var(--font-sans); line-height: 1.5;">
          <strong>Audio Moment: ${escapeHtml(result.loc_label)}</strong><br/>
          ${escapeHtml(result.full_text)}
        </div>
      `;
      const aud = document.getElementById("preview-audio-player");
      if (aud && seekTime > 0) {
        aud.addEventListener("loadedmetadata", () => {
          aud.currentTime = seekTime;
        });
      }
    } else {
      previewContent.textContent = result.full_text || "No text available.";
    }

    previewDrawer.classList.add("open");
  }

  function closeDrawer() {
    previewDrawer.classList.remove("open");
  }

  closeDrawerBtn.addEventListener("click", closeDrawer);

  previewOpenFileBtn.addEventListener("click", () => {
    if (currentActiveResult) openFile(currentActiveResult.path);
  });

  previewOpenFolderBtn.addEventListener("click", () => {
    if (currentActiveResult) openFolder(currentActiveResult.path);
  });

  if (previewHideExtBtn) {
    previewHideExtBtn.addEventListener("click", () => {
      if (currentActiveResult) {
        hideExtension(currentActiveResult.extension);
      }
    });
  }

  // Windows Actions
  async function openFile(path) {
    try {
      await fetch("/api/open-file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
    } catch (err) {
      console.error("Open file error:", err);
    }
  }

  async function openFolder(path) {
    try {
      await fetch("/api/open-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
    } catch (err) {
      console.error("Open folder error:", err);
    }
  }

  // Folders Modal
  foldersModalBtn.addEventListener("click", openModal);
  closeModalBtn.addEventListener("click", closeModal);
  modalDoneBtn.addEventListener("click", closeModal);

  function openModal() {
    foldersModal.style.display = "flex";
    fetchFolders();
    fetchStatus();
  }

  function closeModal() {
    foldersModal.style.display = "none";
  }

  browseFolderBtn.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/folders/browse", { method: "POST" });
      const data = await res.json();
      if (!data.cancelled && data.path) {
        await addFolder(data.path);
      }
    } catch (err) {
      console.error("Browse folder error:", err);
    }
  });

  manualAddBtn.addEventListener("click", async () => {
    const path = manualFolderInput.value.trim();
    if (path) {
      await addFolder(path);
      manualFolderInput.value = "";
    }
  });

  async function addFolder(path) {
    try {
      const res = await fetch("/api/folders/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      if (res.ok) {
        await fetchFolders();
        await fetchStatus();
      } else {
        const err = await res.json();
        alert(err.detail || "Failed to add folder.");
      }
    } catch (err) {
      console.error("Add folder error:", err);
    }
  }

  async function removeFolder(path) {
    if (!confirm(`Stop indexing "${path}"?`)) return;
    try {
      await fetch("/api/folders/remove", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      await fetchFolders();
      await fetchStatus();
    } catch (err) {
      console.error("Remove folder error:", err);
    }
  }

  if (syncChangesBtn) {
    syncChangesBtn.addEventListener("click", async () => {
      try {
        // Incremental: preserves existing index and only indexes new or modified files
        await fetch("/api/index/start?full_reindex=false", { method: "POST" });
        closeModal();
      } catch (err) {
        console.error("Scan changes error:", err);
      }
    });
  }

  if (reindexAllBtn) {
    reindexAllBtn.addEventListener("click", async () => {
      const ok = confirm("This will clear the database and rebuild all embeddings from scratch. Continue?");
      if (!ok) return;
      try {
        await fetch("/api/index/start?full_reindex=true", { method: "POST" });
        closeModal();
      } catch (err) {
        console.error("Rebuild from scratch error:", err);
      }
    });
  }

  cancelIndexBtn.addEventListener("click", async () => {
    try {
      await fetch("/api/index/cancel", { method: "POST" });
    } catch (err) {
      console.error("Cancel index error:", err);
    }
  });

  statsPill.title = "Click to scan for new or modified files (incremental sync)";
  statsPill.addEventListener("click", async () => {
    try {
      await fetch("/api/index/start?full_reindex=false", { method: "POST" });
    } catch (err) {
      console.error("Incremental scan error:", err);
    }
  });

  // Fetch Folders List
  async function fetchFolders() {
    try {
      const res = await fetch("/api/folders");
      const data = await res.json();
      const folders = data.chosen_folders || [];
      folderCountBadge.textContent = folders.length;

      if (folders.length === 0) {
        foldersList.innerHTML = `<p class="empty-hint">No folders chosen yet. Click "Choose Folder..." to pick one.</p>`;
        return;
      }

      foldersList.innerHTML = "";
      folders.forEach((f) => {
        const item = document.createElement("div");
        item.className = "folder-item";
        item.innerHTML = `
          <div class="folder-item-info">
            <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
            <div class="folder-item-text">
              <span class="folder-name">${escapeHtml(f.name)}</span>
              <span class="folder-path" title="${escapeHtml(f.path)}">${escapeHtml(f.path)}</span>
            </div>
          </div>
          <div class="folder-item-meta">
            <span class="file-count-badge">${f.file_count} files</span>
            <button class="icon-btn remove-folder-btn" title="Remove from FileSift">
              <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
            </button>
          </div>
        `;
        item.querySelector(".remove-folder-btn").addEventListener("click", () => {
          removeFolder(f.path);
        });
        foldersList.appendChild(item);
      });
    } catch (err) {
      console.error("Fetch folders error:", err);
    }
  }

  const deviceGpuRadio = document.getElementById("device-gpu-radio");
  const deviceCpuRadio = document.getElementById("device-cpu-radio");
  const gpuOptionLabel = document.getElementById("gpu-option-label");
  const gpuModelLabel = document.getElementById("gpu-model-label");
  const modelIndicator = document.getElementById("model-indicator");

  if (modelIndicator) {
    modelIndicator.style.cursor = "pointer";
    modelIndicator.addEventListener("click", openModal);
  }

  // Device Selection Switcher
  if (deviceGpuRadio && deviceCpuRadio) {
    deviceGpuRadio.addEventListener("change", () => switchComputeDevice("cuda"));
    deviceCpuRadio.addEventListener("change", () => switchComputeDevice("cpu"));
  }

  async function switchComputeDevice(device) {
    try {
      const res = await fetch("/api/device", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device }),
      });
      if (res.ok) {
        await fetchStatus();
      }
    } catch (err) {
      console.error("Error switching device:", err);
    }
  }

  // Fetch Status
  async function fetchStatus() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();
      statsPill.textContent = `${data.total_files} files • ${data.total_chunks} chunks`;
      modalDbStats.textContent = `${data.total_files} files indexed (${data.db_size_mb} MB)`;

      const devName = data.device === "cuda" ? (data.gpu_name ? `GPU: ${data.gpu_name.replace("NVIDIA GeForce ", "")}` : "GPU") : "CPU";
      modelText.textContent = `EmbeddingGemma 2 (${devName})`;

      if (data.cuda_available) {
        if (deviceGpuRadio) deviceGpuRadio.disabled = false;
        if (gpuOptionLabel) gpuOptionLabel.style.opacity = "1";
        if (gpuModelLabel) gpuModelLabel.textContent = `${data.gpu_name} (${data.vram_gb} GB VRAM)`;
      } else {
        if (deviceGpuRadio) deviceGpuRadio.disabled = true;
        if (gpuOptionLabel) gpuOptionLabel.style.opacity = "0.5";
        if (gpuModelLabel) gpuModelLabel.textContent = "No CUDA GPU detected";
      }

      if (deviceGpuRadio && deviceCpuRadio) {
        if (data.device === "cuda") {
          deviceGpuRadio.checked = true;
        } else {
          deviceCpuRadio.checked = true;
        }
      }
    } catch (err) {
      console.error("Status error:", err);
    }
  }

  // Polling for Indexing Progress
  function startStatusPolling() {
    setInterval(async () => {
      try {
        const res = await fetch("/api/index/progress");
        const p = await res.json();

        if (p.status === "indexing" || p.status === "scanning" || p.status === "loading_model") {
          indexingBanner.style.display = "block";
          indexProgressBar.style.width = `${p.progress_pct}%`;
          indexPctLabel.textContent = `${p.progress_pct}%`;

          if (p.status === "loading_model") {
            indexStatusLabel.textContent = "Loading EmbeddingGemma 2...";
            indexCurrentFile.textContent = "Initializing model weights on device...";
          } else if (p.status === "scanning") {
            indexStatusLabel.textContent = "Scanning folder contents...";
            indexCurrentFile.textContent = "Checking for new and modified files...";
          } else {
            indexStatusLabel.textContent = `Indexing: ${p.files_indexed} / ${p.total_files} files`;
            indexCurrentFile.textContent = p.current_file || "Processing...";
          }
        } else {
          indexingBanner.style.display = "none";
        }
      } catch (err) {
        // Silent fail during poll
      }
    }, 1000);
  }
});
