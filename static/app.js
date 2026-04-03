function renderBrief(payload) {
  const findings = (payload.findings || [])
    .map(
      (item) => `
        <li>
          <p>${item.text}</p>
          <small>${item.citation.title} / ${item.citation.heading}</small>
        </li>
      `
    )
    .join("");

  const sources = (payload.sources || [])
    .map(
      (item) => `
        <li>
          <strong>${item.title}</strong>
          <small>${item.document_number || item.legal_type || "Document"}</small>
        </li>
      `
    )
    .join("");

  return `
    <div class="brief-card">
      <h3>${payload.headline}</h3>
      <p>${payload.summary}</p>
      ${findings ? `<div class="brief-section"><strong>Key findings</strong><ul>${findings}</ul></div>` : ""}
      ${sources ? `<div class="brief-section"><strong>Source documents</strong><ul>${sources}</ul></div>` : ""}
      <p class="brief-disclaimer">${payload.disclaimer}</p>
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
    const response = await fetch("/api/ask", {
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

  button.disabled = true;
  button.textContent = tracked ? "Removing..." : "Tracking...";

  try {
    const response = await fetch(`/api/tracked/${documentId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ tracked: !tracked }),
    });

    if (!response.ok) {
      throw new Error("Track request failed");
    }

    window.location.reload();
  } catch (error) {
    button.disabled = false;
    button.textContent = tracked ? "Tracked" : "Track law";
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

  function renderCitationPreview(payload) {
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

    return `
      <div class="citation-preview__body">
        <button type="button" class="citation-preview__close" data-citation-preview-close aria-label="Close citation preview">Close</button>
        <p class="citation-preview__eyebrow">${escapeHtml(mention.link_label || "Referenced Document")}</p>
        <h3>${escapeHtml(target.title || "Referenced legal document")}</h3>
        <p class="citation-preview__meta">${escapeHtml(target.document_number || target.legal_type || "Văn bản pháp luật")}${target.issuance_date ? ` · ${escapeHtml(target.issuance_date)}` : ""}</p>
        ${target.excerpt ? `<p class="citation-preview__excerpt">${escapeHtml(target.excerpt)}</p>` : ""}

        <div class="citation-preview__block">
          <strong>Reference Context</strong>
          <p>${escapeHtml(sourceSection.label || "Current section")}${mention.raw_reference ? ` · ${escapeHtml(mention.raw_reference)}` : ""}</p>
        </div>

        ${targetSection ? `
          <div class="citation-preview__block">
            <strong>Referenced Section</strong>
            <a href="/documents/${target.id}#${escapeHtml(targetSection.anchor)}">${escapeHtml(targetSection.label)}</a>
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
          ${comparePreview?.compare_path ? `<a href="${escapeHtml(comparePreview.compare_path)}">Review Change</a>` : target.compare_path ? `<a href="${escapeHtml(target.compare_path)}">Compare</a>` : ""}
          ${provenanceRoute ? `<a href="${escapeHtml(provenanceRoute.url)}" target="_blank" rel="noreferrer">Official Source</a>` : ""}
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
    const cache = new Map();
    let activeLink = null;
    let hideTimer = 0;

    function isMobilePreview() {
      return window.matchMedia("(max-width: 900px)").matches;
    }

    function cancelHide() {
      if (hideTimer) {
        window.clearTimeout(hideTimer);
        hideTimer = 0;
      }
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
        const request = fetch(
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
      activeLink = null;
      preview.hidden = true;
      preview.classList.remove("is-open");
      preview.style.top = "";
      preview.style.left = "";
    }

    function scheduleHide() {
      cancelHide();
      hideTimer = window.setTimeout(() => {
        closePreview();
      }, 160);
    }

    async function openPreview(link) {
      cancelHide();
      activeLink = link;
      preview.hidden = false;
      preview.classList.add("is-open");
      surface.innerHTML = '<div class="citation-preview__loading">Loading citation context…</div>';
      positionPreview(link);

      try {
        const payload = await loadPreview(link);
        if (activeLink !== link) {
          return;
        }
        surface.innerHTML = renderCitationPreview(payload);
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
          openPreview(link);
        }
      });
      link.addEventListener("mouseleave", () => {
        if (!isMobilePreview()) {
          scheduleHide();
        }
      });
      link.addEventListener("focus", () => {
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
      const closeButton = event.target.closest("[data-citation-preview-close]");
      if (closeButton) {
        event.preventDefault();
        closePreview();
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
});
