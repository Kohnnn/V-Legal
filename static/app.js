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

  function saveSelected() {
    window.localStorage.setItem(compareStorageKey, JSON.stringify(selected));
  }

  function loadSelected() {
    try {
      const raw = window.localStorage.getItem(compareStorageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      selected = Array.isArray(parsed)
        ? parsed.map((value) => Number(value)).filter((value) => Number.isInteger(value))
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
      <span class="compare-bar__label">Compare</span>
      <div class="compare-bar__docs" id="compare-bar-docs"></div>
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
    if (selected.length === 0) {
      docsEl.textContent = "Select documents above to compare";
    } else {
      docsEl.innerHTML = selected
        .map((id) => `<span class="compare-bar__doc">Doc #${id}</span>`)
        .join("");
    }
    const goBtn = bar.querySelector("#compare-go");
    goBtn.style.visibility = selected.length >= 2 ? "visible" : "hidden";
  }

  function syncCompareButtons() {
    document.querySelectorAll("[data-compare-id]").forEach((btn) => {
      const id = Number(btn.dataset.compareId);
      const isSelected = selected.includes(id);
      btn.classList.toggle("is-selected", isSelected);
      btn.textContent = isSelected ? "Selected" : "Compare";
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
    if (selected.length < 2) return;
    window.location.href = `/compare/${selected[0]}/${selected[1]}`;
  }

  document.querySelectorAll("[data-compare-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = parseInt(btn.dataset.compareId, 10);
      if (btn.classList.contains("is-selected")) {
        selected = selected.filter((s) => s !== id);
      } else {
        if (selected.length >= 4) {
          const oldest = selected.shift();
        }
        selected.push(id);
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
});
