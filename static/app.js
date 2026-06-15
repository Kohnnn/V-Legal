function generateUserId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }

  return `vlegal-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getUserId() {
  try {
    const existing = window.localStorage.getItem("vlegal_user_id");
    if (existing && existing.length >= 8) {
      return existing;
    }

    const created = generateUserId();
    window.localStorage.setItem("vlegal_user_id", created);
    return created;
  } catch (error) {
    return generateUserId();
  }
}

function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("x-user-id", getUserId());
  return fetch(url, {
    ...options,
    headers,
    credentials: "same-origin",
  });
}

function escapeHtmlValue(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderBrief(payload) {
  const findings = (payload.findings || [])
    .map(
      (item) => `
        <li>
          <p>${escapeHtmlValue(item.text)}</p>
          <small>${escapeHtmlValue(item.citation && item.citation.title)} / ${escapeHtmlValue(item.citation && item.citation.heading)}</small>
        </li>
      `
    )
    .join("");

  const sources = (payload.sources || [])
    .map(
      (item) => `
        <li>
          <strong>${escapeHtmlValue(item.title)}</strong>
          <small>${escapeHtmlValue(item.document_number || item.legal_type || "Document")}</small>
        </li>
      `
    )
    .join("");

  return `
    <div class="brief-card">
      <h3>${escapeHtmlValue(payload.headline)}</h3>
      <p>${escapeHtmlValue(payload.summary)}</p>
      ${findings ? `<div class="brief-section"><strong>Key findings</strong><ul>${findings}</ul></div>` : ""}
      ${sources ? `<div class="brief-section"><strong>Source documents</strong><ul>${sources}</ul></div>` : ""}
      <p class="brief-disclaimer">${escapeHtmlValue(payload.disclaimer)}</p>
    </div>
  `;
}

async function handleAskFormSubmit(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const output = form.parentElement.querySelector("[data-ask-output]");
  const questionField = form.querySelector("textarea[name='question']");
  const button = form.querySelector("button[type='submit']");
  const documentId = form.dataset.documentId;

  if (!output || !questionField) {
    return;
  }

  const question = questionField.value.trim();
  if (!question) {
    output.innerHTML = "Enter a question first.";
    output.classList.remove("muted");
    return;
  }

  button.disabled = true;
  button.textContent = "Working...";
  output.innerHTML = "Retrieving grounded passages...";
  output.classList.add("muted");

  try {
    const response = await apiFetch("/api/ask", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question,
        document_id: documentId ? Number(documentId) : null,
      }),
    });

    if (!response.ok) {
      throw new Error("Ask request failed");
    }

    const payload = await response.json();
    output.innerHTML = renderBrief(payload);
    output.classList.remove("muted");
  } catch (error) {
    output.innerHTML = "Something went wrong while generating the grounded brief.";
    output.classList.remove("muted");
  } finally {
    button.disabled = false;
    button.textContent = documentId ? "Analyze Document" : "Generate Brief";
  }
}

async function handleTrackButtonClick(event) {
  const button = event.currentTarget;
  const documentId = button.dataset.documentId;
  const tracked = button.dataset.tracked === "true";

  if (!documentId) {
    return;
  }

  const activeClass = button.dataset.activeClass || "is-active";
  const labelTrack = button.dataset.labelTrack || "Track law";
  const labelTracked = button.dataset.labelTracked || "Tracked";

  button.disabled = true;
  button.textContent = tracked ? "Removing..." : "Tracking...";

  try {
    const response = await apiFetch(`/api/tracked/${documentId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ tracked: !tracked }),
    });

    if (!response.ok) {
      throw new Error("Track request failed");
    }

    // Optimistic in-place update: flip state without a full page reload so the
    // reader keeps its scroll position and any pinned citation card.
    const nowTracked = !tracked;
    button.dataset.tracked = nowTracked ? "true" : "false";
    button.classList.toggle(activeClass, nowTracked);
    button.textContent = nowTracked ? labelTracked : labelTrack;
    button.disabled = false;
  } catch (error) {
    button.disabled = false;
    button.textContent = tracked ? labelTracked : labelTrack;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-ask-form]").forEach((form) => {
    form.addEventListener("submit", handleAskFormSubmit);
  });

  document.querySelectorAll("[data-track-button]").forEach((button) => {
    button.addEventListener("click", handleTrackButtonClick);
  });

  const compareBarId = "global-compare-bar";
  const compareStorageKey = "vlegal-compare-documents";
  let selected = [];

  function normalizeCompareItem(value) {
    if (typeof value === "number") {
      return {
        id: value,
        title: `Document ${value}`,
        number: "",
      };
    }

    if (!value || !Number.isInteger(Number(value.id))) {
      return null;
    }

    return {
      id: Number(value.id),
      title: String(value.title || `Document ${value.id}`).trim(),
      number: String(value.number || "").trim(),
    };
  }

  function getCompareButtonItem(button) {
    return normalizeCompareItem({
      id: Number(button.dataset.compareId),
      title: button.dataset.compareTitle,
      number: button.dataset.compareNumber,
    });
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function escapeRegExp(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function renderHighlightedText(value, phrase) {
    const content = String(value || "").trim();
    if (!content) {
      return "";
    }
    if (!phrase) {
      return escapeHtml(content);
    }

    const match = content.match(new RegExp(escapeRegExp(phrase), "i"));
    if (!match || match.index === undefined) {
      return escapeHtml(content);
    }

    const start = match.index;
    const end = start + match[0].length;
    return `${escapeHtml(content.slice(0, start))}<mark class="citation-preview__mark">${escapeHtml(content.slice(start, end))}</mark>${escapeHtml(content.slice(end))}`;
  }

  function saveSelected() {
    window.localStorage.setItem(compareStorageKey, JSON.stringify(selected));
  }

  function loadSelected() {
    try {
      const raw = window.localStorage.getItem(compareStorageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      selected = Array.isArray(parsed)
        ? parsed
            .map((value) => normalizeCompareItem(value))
            .filter((value) => value !== null)
            .slice(0, 2)
        : [];
    } catch (error) {
      selected = [];
    }
  }

  function getCompareBar() {
    return document.getElementById(compareBarId);
  }

  function buildCompareBar() {
    const bar = document.createElement("div");
    bar.className = "compare-bar";
    bar.id = compareBarId;
    bar.innerHTML = `
      <span class="compare-bar__label">Compare Pair</span>
      <div class="compare-bar__slots" id="compare-bar-docs"></div>
      <div class="compare-bar__actions">
        <a class="compare-bar__clear-btn" href="#" id="compare-clear">Clear</a>
        <a class="compare-bar__compare-btn" href="#" id="compare-go">Compare Now</a>
      </div>
    `;
    document.body.appendChild(bar);

    bar.querySelector("#compare-clear").addEventListener("click", (e) => {
      e.preventDefault();
      clearCompare();
    });
    bar.querySelector("#compare-go").addEventListener("click", (e) => {
      e.preventDefault();
      goCompare();
    });
  }

  function updateCompareBar() {
    const bar = getCompareBar();
    if (!bar) return;
    const docsEl = bar.querySelector("#compare-bar-docs");
    docsEl.innerHTML = [0, 1]
      .map((slot) => {
        const item = selected[slot];
        if (!item) {
          return `
            <div class="compare-bar__slot compare-bar__slot--empty">
              <small>${slot === 0 ? "Left" : "Right"}</small>
              <strong>Select a document</strong>
            </div>
          `;
        }
        return `
          <div class="compare-bar__slot">
            <small>${slot === 0 ? "Left" : "Right"}</small>
            <strong>${escapeHtml(item.title)}</strong>
            <span>${escapeHtml(item.number || "Văn bản pháp luật")}</span>
          </div>
        `;
      })
      .join("");
    const goBtn = bar.querySelector("#compare-go");
    goBtn.style.visibility = selected.length === 2 ? "visible" : "hidden";
  }

  function syncCompareButtons() {
    document.querySelectorAll("[data-compare-id]").forEach((btn) => {
      const id = Number(btn.dataset.compareId);
      const selectedIndex = selected.findIndex((item) => item.id === id);
      const isSelected = selectedIndex >= 0;
      btn.classList.toggle("is-selected", isSelected);
      btn.textContent = isSelected
        ? `Selected ${selectedIndex + 1}/2`
        : btn.dataset.compareDefaultLabel || "Add to Compare";
    });
  }

  function clearCompare() {
    selected = [];
    saveSelected();
    syncCompareButtons();
    const bar = getCompareBar();
    if (bar) bar.remove();
  }

  function goCompare() {
    if (selected.length !== 2) return;
    window.location.href = `/compare/${selected[0].id}/${selected[1].id}`;
  }

  function renderCitationPreview(payload, options = {}) {
    const {
      showClose = true,
      includePinAction = true,
      pinned = false,
    } = options;
    const target = payload.target_document || {};
    const mention = payload.mention || {};
    const sourceSection = payload.source_section || {};
    const targetSection = payload.target_section;
    const signals = payload.signals || [];
    const incomingMentions = payload.incoming_mentions || [];
    const provenanceRoute = (target.provenance?.routes || [])[0];
    const comparePreview = target.compare_preview;
    const meaningfulComparePreview =
      comparePreview && comparePreview.change?.label !== "unmatched";
    const sourceQuote = sourceSection.quote || sourceSection.excerpt;

    const signalMarkup = signals
      .map((item) => {
        const doc = item.document || {};
        const suffix = item.count ? ` ${escapeHtml(String(item.count))}` : "";
        return `
          <article class="citation-preview__signal">
            <small>${escapeHtml(item.label || item.kind || "Related")}${suffix}</small>
            ${doc.id ? `<a href="/documents/${doc.id}">${escapeHtml(doc.title || "Linked document")}</a>` : ""}
          </article>
        `;
      })
      .join("");

    const incomingMarkup = incomingMentions
      .map(
        (item) => `
          <li>
            <a href="/documents/${item.id}">${escapeHtml(item.title)}</a>
            <small>${escapeHtml(item.link_label || "Mentioned in")} · ${escapeHtml(item.source_section_label || "Section")}</small>
          </li>
        `,
      )
      .join("");

    const sourceQuoteMarkup = sourceQuote
      ? `<blockquote class="citation-preview__quote">${renderHighlightedText(sourceQuote, mention.raw_reference || "")}</blockquote>`
      : "";

    const compareChangeMarkup = meaningfulComparePreview
      ? `
        <div class="citation-preview__block citation-preview__compare">
          <strong>Change Review</strong>
          <a href="${escapeHtml(comparePreview.compare_path)}">${escapeHtml(comparePreview.comparison_document.title)}</a>
          <p>${escapeHtml(comparePreview.change.summary || "Comparison context available.")}</p>
          ${comparePreview.focus?.left?.label ? `<small>${escapeHtml(comparePreview.focus.left.label)}</small>` : ""}
          ${comparePreview.change.added?.length ? `<ul class="citation-preview__diff-list">${comparePreview.change.added.map((item) => `<li><span>Added</span>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
          ${comparePreview.change.removed?.length ? `<ul class="citation-preview__diff-list">${comparePreview.change.removed.map((item) => `<li><span>Removed</span>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
          ${comparePreview.change.changed?.length ? `<ul class="citation-preview__diff-list">${comparePreview.change.changed.map((item) => `<li><span>Changed</span>${escapeHtml(item.left)} → ${escapeHtml(item.right)}</li>`).join("")}</ul>` : ""}
          ${comparePreview.change.instruction_clauses?.length ? `<ul class="citation-preview__diff-list">${comparePreview.change.instruction_clauses.map((item) => `<li><span>Clause</span>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
        </div>
      `
      : "";

    const pinActionMarkup = includePinAction
      ? `<button type="button" class="citation-preview__pin-btn" data-citation-pin>${pinned ? "Remove Pin" : "Pin to Rail"}</button>`
      : "";

    const compareActionMarkup = meaningfulComparePreview
      ? `<a href="${escapeHtml(comparePreview.compare_path)}">Review Change</a>`
      : target.compare_path
        ? `<a href="${escapeHtml(target.compare_path)}">Compare</a>`
        : "";

    return `
      <div class="citation-preview__body">
        ${showClose ? '<button type="button" class="citation-preview__close" data-citation-preview-close aria-label="Close citation preview">Close</button>' : ""}
        <p class="citation-preview__eyebrow">${escapeHtml(mention.link_label || "Referenced Document")}</p>
        <h3>${escapeHtml(target.title || "Referenced legal document")}</h3>
        <p class="citation-preview__meta">${escapeHtml(target.document_number || target.legal_type || "Văn bản pháp luật")}${target.issuance_date ? ` · ${escapeHtml(target.issuance_date)}` : ""}</p>
        ${target.excerpt ? `<p class="citation-preview__excerpt">${escapeHtml(target.excerpt)}</p>` : ""}

        <div class="citation-preview__block">
          <strong>Reference Context</strong>
          <p>${escapeHtml(sourceSection.label || "Current section")}${mention.referenced_label ? ` · ${escapeHtml(mention.referenced_label)}` : mention.raw_reference ? ` · ${escapeHtml(mention.raw_reference)}` : ""}</p>
          ${sourceQuoteMarkup}
        </div>

        ${targetSection ? `
          <div class="citation-preview__block">
            <strong>Referenced Section</strong>
            <a href="/documents/${target.id}#${escapeHtml(targetSection.anchor)}">${escapeHtml(targetSection.label)}</a>
            ${mention.referenced_label && mention.referenced_label !== targetSection.label ? `<small class="citation-preview__path">Requested reference: ${escapeHtml(mention.referenced_label)}</small>` : ""}
            ${targetSection.excerpt ? `<p>${escapeHtml(targetSection.excerpt)}</p>` : ""}
          </div>
        ` : ""}

        ${signalMarkup ? `
          <div class="citation-preview__block citation-preview__signals">
            <strong>Lifecycle Signals</strong>
            <div class="citation-preview__signal-list">${signalMarkup}</div>
          </div>
        ` : ""}

        ${compareChangeMarkup}

        ${incomingMarkup ? `
          <div class="citation-preview__block">
            <strong>Mentioned In Other Documents</strong>
            <ul class="citation-preview__mention-list">${incomingMarkup}</ul>
          </div>
        ` : ""}

        <div class="citation-preview__actions">
          <a href="${escapeHtml(target.reader_path || `/documents/${target.id}`)}">Open Document</a>
          ${compareActionMarkup}
          ${provenanceRoute ? `<a href="${escapeHtml(provenanceRoute.url)}" target="_blank" rel="noreferrer">Official Source</a>` : ""}
          ${pinActionMarkup}
        </div>
      </div>
    `;
  }

  function initCitationPreview(root) {
    const links = Array.from(
      root.querySelectorAll(".doc-ref-link[data-target-document-id]"),
    );
    if (!links.length) {
      return;
    }

    const sourceDocumentId = Number(root.dataset.documentId || "0");
    if (!Number.isInteger(sourceDocumentId) || sourceDocumentId <= 0) {
      return;
    }

    const preview = document.createElement("div");
    preview.className = "citation-preview";
    preview.hidden = true;
    preview.innerHTML = '<div class="citation-preview__surface" aria-live="polite"></div>';
    document.body.appendChild(preview);

    const surface = preview.querySelector(".citation-preview__surface");
    const railPanel = document.querySelector("[data-citation-rail]");
    const railEmpty = railPanel?.querySelector("[data-citation-rail-empty]");
    const railBody = railPanel?.querySelector("[data-citation-rail-body]");
    const cache = new Map();
    let activeLink = null;
    let activePayload = null;
    let pinnedLink = null;
    let pinnedPayload = null;
    let hideTimer = 0;
    let openTimer = 0;

    function isMobilePreview() {
      return window.matchMedia("(max-width: 900px)").matches;
    }

    function cancelHide() {
      if (hideTimer) {
        window.clearTimeout(hideTimer);
        hideTimer = 0;
      }
    }

    function cancelOpen() {
      if (openTimer) {
        window.clearTimeout(openTimer);
        openTimer = 0;
      }
    }

    function updateLinkStates() {
      links.forEach((item) => {
        item.classList.toggle("doc-ref-link--active", item === activeLink);
        item.classList.toggle("doc-ref-link--pinned", item === pinnedLink);
      });
    }

    function decorateCitationLink(link, payload) {
      link.classList.add("doc-ref-link--resolved");
      if (payload.target_section) {
        link.classList.add("doc-ref-link--has-section");
      }
      if ((payload.signals || []).length) {
        link.classList.add("doc-ref-link--has-signal");
      }
      if (
        payload.target_document?.compare_preview
        && payload.target_document.compare_preview.change?.label !== "unmatched"
      ) {
        link.classList.add("doc-ref-link--has-compare");
      }
    }

    function clearPinnedCitation() {
      pinnedLink = null;
      pinnedPayload = null;
      if (railPanel) {
        railPanel.classList.remove("is-active");
      }
      if (railBody) {
        railBody.hidden = true;
        railBody.innerHTML = "";
      }
      if (railEmpty) {
        railEmpty.hidden = false;
      }
      updateLinkStates();
    }

    function pinCitation(link, payload) {
      if (!railBody || !railEmpty || !railPanel) {
        return;
      }
      pinnedLink = link;
      pinnedPayload = payload;
      railPanel.classList.add("is-active");
      railEmpty.hidden = true;
      railBody.hidden = false;
      railBody.innerHTML = renderCitationPreview(payload, {
        showClose: false,
        includePinAction: true,
        pinned: true,
      });
      updateLinkStates();
    }

    function getSourceAnchor(link) {
      const article = link.closest(".law-article");
      const directAnchor = article?.querySelector(".anchor-target[id]");
      if (directAnchor?.id) {
        return directAnchor.id;
      }

      let lastAnchor = null;
      root.querySelectorAll(".anchor-target[id]").forEach((anchor) => {
        const position = anchor.compareDocumentPosition(link);
        if (position & Node.DOCUMENT_POSITION_FOLLOWING) {
          lastAnchor = anchor;
        }
      });
      return lastAnchor?.id || "";
    }

    function positionPreview(link) {
      preview.classList.toggle("citation-preview--mobile", isMobilePreview());
      if (isMobilePreview()) {
        preview.style.top = "";
        preview.style.left = "";
        preview.style.maxWidth = "";
        return;
      }

      const rect = link.getBoundingClientRect();
      preview.style.maxWidth = "380px";
      const previewRect = preview.getBoundingClientRect();
      const scrollX = window.scrollX;
      const scrollY = window.scrollY;
      let left = scrollX + rect.left;
      let top = scrollY + rect.bottom + 12;

      left = Math.max(
        scrollX + 12,
        Math.min(left, scrollX + window.innerWidth - previewRect.width - 12),
      );

      if (top + previewRect.height > scrollY + window.innerHeight - 12) {
        top = scrollY + rect.top - previewRect.height - 12;
      }

      preview.style.left = `${left}px`;
      preview.style.top = `${Math.max(scrollY + 12, top)}px`;
    }

    async function loadPreview(link) {
      const targetDocumentId = Number(link.dataset.targetDocumentId || "0");
      if (!Number.isInteger(targetDocumentId) || targetDocumentId <= 0) {
        throw new Error("Missing target document id");
      }
      const sourceAnchor = getSourceAnchor(link);
      const rawReference = link.dataset.reference || link.textContent.trim();
      const cacheKey = `${sourceDocumentId}:${targetDocumentId}:${sourceAnchor}:${rawReference}`;

      if (!cache.has(cacheKey)) {
        const params = new URLSearchParams();
        if (sourceAnchor) {
          params.set("source_anchor", sourceAnchor);
        }
        if (rawReference) {
          params.set("raw_reference", rawReference);
        }
        const request = apiFetch(
          `/api/citation-preview/${sourceDocumentId}/${targetDocumentId}?${params.toString()}`,
        )
          .then((response) => {
            if (!response.ok) {
              throw new Error("Citation preview request failed");
            }
            return response.json();
          })
          .catch((error) => {
            cache.delete(cacheKey);
            throw error;
          });
        cache.set(cacheKey, request);
      }
      return cache.get(cacheKey);
    }

    function closePreview() {
      cancelHide();
      cancelOpen();
      activeLink = null;
      activePayload = null;
      preview.hidden = true;
      preview.classList.remove("is-open");
      preview.style.top = "";
      preview.style.left = "";
      updateLinkStates();
    }

    function scheduleHide() {
      cancelHide();
      hideTimer = window.setTimeout(() => {
        closePreview();
      }, 260);
    }

    async function openPreview(link) {
      cancelHide();
      cancelOpen();
      activeLink = link;
      activePayload = null;
      preview.hidden = false;
      preview.classList.add("is-open");
      surface.innerHTML = '<div class="citation-preview__loading">Loading citation context…</div>';
      updateLinkStates();
      positionPreview(link);

      try {
        const payload = await loadPreview(link);
        if (activeLink !== link) {
          return;
        }
        activePayload = payload;
        decorateCitationLink(link, payload);
        surface.innerHTML = renderCitationPreview(payload, {
          showClose: true,
          includePinAction: Boolean(railBody),
          pinned: pinnedLink === link,
        });
        positionPreview(link);
      } catch (error) {
        if (activeLink !== link) {
          return;
        }
        surface.innerHTML = '<div class="citation-preview__loading">Unable to load citation context.</div>';
        positionPreview(link);
      }
    }

    links.forEach((link) => {
      link.addEventListener("mouseenter", () => {
        if (!isMobilePreview()) {
          // Debounce: skating the cursor across a dense article should not fire
          // a preview request for every citation it passes over.
          cancelOpen();
          openTimer = window.setTimeout(() => {
            openTimer = 0;
            openPreview(link);
          }, 140);
        }
      });
      link.addEventListener("mouseleave", () => {
        if (!isMobilePreview()) {
          cancelOpen();
          scheduleHide();
        }
      });
      link.addEventListener("focus", () => {
        cancelOpen();
        openPreview(link);
      });
      link.addEventListener("blur", () => {
        scheduleHide();
      });
      link.addEventListener("click", (event) => {
        if (isMobilePreview()) {
          event.preventDefault();
          openPreview(link);
        }
      });
    });

    preview.addEventListener("mouseenter", cancelHide);
    preview.addEventListener("mouseleave", scheduleHide);
    preview.addEventListener("click", (event) => {
      const pinButton = event.target.closest("[data-citation-pin]");
      if (pinButton) {
        event.preventDefault();
        if (activeLink && activePayload) {
          if (pinnedLink === activeLink) {
            clearPinnedCitation();
          } else {
            pinCitation(activeLink, activePayload);
          }
          closePreview();
        }
        return;
      }

      const closeButton = event.target.closest("[data-citation-preview-close]");
      if (closeButton) {
        event.preventDefault();
        closePreview();
      }
    });

    railBody?.addEventListener("click", (event) => {
      const pinButton = event.target.closest("[data-citation-pin]");
      if (pinButton) {
        event.preventDefault();
        clearPinnedCitation();
      }
    });

    window.addEventListener(
      "resize",
      () => {
        if (!preview.hidden && activeLink) {
          positionPreview(activeLink);
        }
      },
      { passive: true },
    );

    window.addEventListener(
      "scroll",
      () => {
        if (!preview.hidden && activeLink) {
          positionPreview(activeLink);
        }
      },
      { passive: true },
    );

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closePreview();
      }
    });
  }

  document.querySelectorAll("[data-compare-id]").forEach((btn) => {
    btn.dataset.compareDefaultLabel = btn.textContent.trim();
    btn.addEventListener("click", () => {
      const item = getCompareButtonItem(btn);
      if (!item) {
        return;
      }

      const existingIndex = selected.findIndex((entry) => entry.id === item.id);
      if (btn.classList.contains("is-selected")) {
        selected = selected.filter((entry) => entry.id !== item.id);
      } else {
        if (existingIndex >= 0) {
          selected.splice(existingIndex, 1);
        }
        if (selected.length === 2) {
          selected.shift();
        }
        selected.push(item);
      }

      saveSelected();
      syncCompareButtons();

      if (selected.length > 0) {
        if (!getCompareBar()) buildCompareBar();
        updateCompareBar();
      } else {
        const bar = getCompareBar();
        if (bar) bar.remove();
      }
    });
  });

  loadSelected();
  syncCompareButtons();
  if (selected.length > 0) {
    buildCompareBar();
    updateCompareBar();
  }

  document
    .querySelectorAll("[data-citation-preview-root]")
    .forEach((root) => initCitationPreview(root));

  initDocTabScrollSpy();
  initDocOutlineTree();
  initArticleAnchorLinks();
});

function initDocTabScrollSpy() {
  const nav = document.querySelector("[data-doc-tabs]");
  if (!nav) {
    return;
  }
  const tabs = Array.from(nav.querySelectorAll("[data-doc-tab]"));
  const entries = tabs
    .map((tab) => ({
      tab,
      section: document.getElementById(tab.dataset.docTab),
    }))
    .filter((entry) => entry.section);
  if (!entries.length) {
    return;
  }

  function setActive(tab) {
    tabs.forEach((item) =>
      item.classList.toggle("doc-tab--active", item === tab),
    );
  }

  // Clicking a tab should immediately reflect the active state.
  entries.forEach((entry) => {
    entry.tab.addEventListener("click", () => setActive(entry.tab));
  });

  if (!("IntersectionObserver" in window)) {
    return;
  }

  const visible = new Set();
  const observer = new IntersectionObserver(
    (observed) => {
      observed.forEach((item) => {
        if (item.isIntersecting) {
          visible.add(item.target);
        } else {
          visible.delete(item.target);
        }
      });
      // Activate the tab for the topmost section currently in view.
      const topEntry = entries
        .filter((entry) => visible.has(entry.section))
        .sort(
          (a, b) =>
            a.section.getBoundingClientRect().top -
            b.section.getBoundingClientRect().top,
        )[0];
      if (topEntry) {
        setActive(topEntry.tab);
      }
    },
    { rootMargin: "-45% 0px -45% 0px", threshold: 0 },
  );
  entries.forEach((entry) => observer.observe(entry.section));
}

// Collapsible nested outline tree. Branch rows (depth 1-2) toggle the
// visibility of their deeper descendants until the next branch at the same or
// shallower depth.
function initDocOutlineTree() {
  const tree = document.querySelector("[data-doc-outline]");
  if (!tree) {
    return;
  }
  const items = Array.from(tree.querySelectorAll(".doc-outline-item"));

  function depthOf(el) {
    return Number(el.dataset.outlineDepth || "4");
  }

  function descendantsOf(index) {
    const baseDepth = depthOf(items[index]);
    const result = [];
    for (let i = index + 1; i < items.length; i += 1) {
      if (depthOf(items[i]) <= baseDepth) {
        break;
      }
      result.push(items[i]);
    }
    return result;
  }

  items.forEach((item, index) => {
    if (!item.hasAttribute("data-outline-branch")) {
      return;
    }
    item.setAttribute("aria-expanded", "true");
    item.addEventListener("click", (event) => {
      // Let cmd/ctrl-click and middle-click follow the anchor normally.
      if (event.metaKey || event.ctrlKey) {
        return;
      }
      event.preventDefault();
      const expanded = item.getAttribute("aria-expanded") !== "false";
      item.setAttribute("aria-expanded", expanded ? "false" : "true");
      descendantsOf(index).forEach((child) => {
        if (expanded) {
          child.setAttribute("data-outline-collapsed", "");
        } else {
          child.removeAttribute("data-outline-collapsed");
          if (child.hasAttribute("data-outline-branch")) {
            child.setAttribute("aria-expanded", "true");
          }
        }
      });
    });
  });
}

// Per-article "copy link" affordance. Clicking the # copies a deep link to the
// article anchor and shows a brief confirmation.
function initArticleAnchorLinks() {
  const links = Array.from(document.querySelectorAll("[data-article-anchor]"));
  if (!links.length) {
    return;
  }
  links.forEach((link) => {
    link.addEventListener("click", async (event) => {
      event.preventDefault();
      const anchor = link.dataset.articleAnchor;
      const url = `${window.location.origin}${window.location.pathname}#${anchor}`;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(url);
        }
      } catch (error) {
        /* clipboard may be unavailable; still update the hash below */
      }
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, "", `#${anchor}`);
      }
      const original = link.textContent;
      link.textContent = "Đã sao chép";
      link.classList.add("doc-article-anchor-link--copied");
      window.setTimeout(() => {
        link.textContent = original;
        link.classList.remove("doc-article-anchor-link--copied");
      }, 1400);
    });
  });
}
