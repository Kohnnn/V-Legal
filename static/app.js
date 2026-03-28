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
});
