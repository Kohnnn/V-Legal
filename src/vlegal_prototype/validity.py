"""Legal validity and text-provenance presentation helpers.

The canonical markdown schema carries ``status``, ``effective_date``, and
``expiry_date`` plus ``text_source`` / ``parse_confidence`` / ``source_system``.
These helpers turn those raw fields into honest, display-ready badges:

- a validity badge (in force / expired / partially expired / unknown), never
  asserting a legal conclusion the data does not support
- a text-provenance banner for OCR/PDF or low-confidence documents that tells the
  reader to verify against the official source

All functions are pure and operate on a single ``document`` row dict.
"""

from __future__ import annotations


# Map raw frontmatter status tokens to a normalized key + Vietnamese label.
_STATUS_LABELS = {
    "in_force": ("in_force", "Còn hiệu lực"),
    "active": ("in_force", "Còn hiệu lực"),
    "expired": ("expired", "Hết hiệu lực"),
    "repealed": ("expired", "Hết hiệu lực"),
    "partially_expired": ("partial", "Hết hiệu lực một phần"),
    "partially_in_force": ("partial", "Hết hiệu lực một phần"),
    "unknown": ("unknown", "Chưa xác định hiệu lực"),
}

# Source systems whose documents are not yet officially reconciled.
_UNVERIFIED_SOURCE_SYSTEMS = {"hf_bootstrap", ""}


def _normalize_status_token(value: str | None) -> str:
    return (value or "").strip().lower().replace("-", "_").replace(" ", "_")


def build_validity_badge(document: dict) -> dict:
    """Return a display-ready validity badge for a document row.

    The badge never invents a status: when the frontmatter status is unknown it
    says so. ``unverified`` flags bootstrap-only records so the UI can mark the
    status as not yet officially reconciled.
    """
    token = _normalize_status_token(document.get("status"))
    key, label = _STATUS_LABELS.get(token, ("unknown", "Chưa xác định hiệu lực"))

    source_system = (document.get("source_system") or "").strip().lower()
    unverified = source_system in _UNVERIFIED_SOURCE_SYSTEMS

    effective_date = (document.get("effective_date") or "").strip()
    expiry_date = (document.get("expiry_date") or "").strip()

    return {
        "key": key,
        "label": label,
        "effective_date": effective_date,
        "expiry_date": expiry_date,
        "unverified": unverified,
        # Only the explicit, source-backed states should read as confident.
        "is_explicit": key != "unknown",
    }


def build_text_provenance_notice(document: dict) -> dict | None:
    """Return an OCR / low-confidence banner payload, or ``None`` when not needed.

    Triggers when the body came from OCR/PDF or when parse confidence is not
    ``high``. Points the reader at the official/source URL for verification.
    """
    text_source = (document.get("text_source") or "html").strip().lower()
    parse_confidence = (document.get("parse_confidence") or "high").strip().lower()

    reasons: list[str] = []
    if text_source in {"ocr", "pdf", "mixed"}:
        reasons.append(
            {
                "ocr": "Nội dung được trích xuất bằng OCR từ bản quét.",
                "pdf": "Nội dung được trích xuất từ tệp PDF.",
                "mixed": "Nội dung được trích xuất từ nhiều nguồn (HTML, PDF, OCR).",
            }[text_source]
        )
    if parse_confidence in {"low", "medium"}:
        reasons.append(
            "Độ tin cậy phân tích cấu trúc ở mức "
            f"{'thấp' if parse_confidence == 'low' else 'trung bình'}."
        )

    if not reasons:
        return None

    verify_url = (
        document.get("official_source_url")
        or document.get("url")
        or document.get("source")
        or ""
    )
    severity = "high" if (text_source == "ocr" or parse_confidence == "low") else "medium"
    return {
        "severity": severity,
        "reasons": reasons,
        "verify_url": verify_url,
        "headline": "Hãy đối chiếu với nguồn chính thức",
    }
