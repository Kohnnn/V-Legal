from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from .corpus import (
    CanonicalDocument,
    ensure_corpus_layout,
    iter_canonical_documents,
    load_jsonl_index,
    split_frontmatter,
    sha256_text,
    utc_now_iso,
    write_canonical_document,
    write_jsonl_records,
)
from .structure import (
    ANNEX_HEADING_PATTERN,
    CLAUSE_PATTERN,
    DASH_PATTERN,
    ENACTMENT_LINE_PATTERN,
    ENDMATTER_PATTERN,
    HEADING_PATTERN,
    NUMBER_BLOCK_PATTERN,
    POINT_PATTERN,
    detect_section,
)
from .settings import BASE_DIR, get_settings
from .taxonomy import normalize_ascii


PDF_SUFFIX_PATTERN = re.compile(r"\.pdf$", re.IGNORECASE)
SCAN_MARKERS = (
    "signed.pdf",
    "scan",
    "scanned",
)
RAW_OCR_DIRNAME = "ocr"
RAW_PDF_DIRNAME = "pdf_attachments"
MULTISPACE_PATTERN = re.compile(r"[ \t]+")
MULTIBLANK_PATTERN = re.compile(r"\n{3,}")
LOWER_CONTINUATION_PATTERN = re.compile(r"^[a-zà-ỹ(\[“'\"]")
PAGE_NUMBER_PATTERN = re.compile(r"^\d{1,3}$")
OCR_LEGAL_TOKEN_MAP = {
    "chuong": "Chương",
    "churong": "Chương",
    "phan": "Phần",
    "phn": "Phần",
    "muc": "Mục",
    "dieu": "Điều",
    "diu": "Điều",
    "đu": "Điều",
    "lut": "Luật",
}
OCR_ENACTMENT_MAP = {
    "quyt dinh:": "QUYẾT ĐỊNH:",
    "quyet dinh:": "QUYẾT ĐỊNH:",
    "nghi quyt:": "NGHỊ QUYẾT:",
    "nghi quyet:": "NGHỊ QUYẾT:",
    "thong tu:": "THÔNG TƯ:",
    "luat:": "LUẬT:",
}
OCR_PHRASE_CORRECTIONS = [
    (re.compile(r"\bQU[ÓO]C HI\b"), "QUỐC HỘI"),
    (re.compile(r"\bQuc hi\b", re.IGNORECASE), "Quốc hội"),
    (
        re.compile(r"\bCNG HÒA X HI CH NGHA VIT NAM\b"),
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
    ),
    (re.compile(r"\bĐc lp - T do - Hnh phúc\b"), "Độc lập - Tự do - Hạnh phúc"),
    (re.compile(r"\bLut s:\b", re.IGNORECASE), "Luật số:"),
    (re.compile(r"\bLUT\b"), "LUẬT"),
    (re.compile(r"\bLut\b", re.IGNORECASE), "Luật"),
    (re.compile(r"\bChurong\b", re.IGNORECASE), "Chương"),
    (re.compile(r"\bĐiu\b", re.IGNORECASE), "Điều"),
    (re.compile(r"\bT CHÚC TÒA ÁN\b"), "TỔ CHỨC TÒA ÁN"),
    (re.compile(r"\bNHNG QUY ĐNH CHUNG\b"), "NHỮNG QUY ĐỊNH CHUNG"),
    (
        re.compile(r"\bTA ÁN CHUYN BIT TI TRUNG TÂM TÀI CHÍNH QUC T\b"),
        "TÒA ÁN CHUYÊN BIỆT TẠI TRUNG TÂM TÀI CHÍNH QUỐC TẾ",
    ),
    (re.compile(r"\bTA ÁN\b"), "TÒA ÁN"),
    (re.compile(r"\bCHUYN BIT\b"), "CHUYÊN BIỆT"),
    (re.compile(r"\bquc t\b", re.IGNORECASE), "quốc tế"),
    (re.compile(r"\bCăn c\b", re.IGNORECASE), "Căn cứ"),
    (re.compile(r"\bHin pháp\b", re.IGNORECASE), "Hiến pháp"),
    (re.compile(r"\bCng hòa\b", re.IGNORECASE), "Cộng hòa"),
    (re.compile(r"\bxã hi\b", re.IGNORECASE), "xã hội"),
    (re.compile(r"\bVit Nam\b", re.IGNORECASE), "Việt Nam"),
    (re.compile(r"\bNghi quyt\b", re.IGNORECASE), "Nghị quyết"),
    (re.compile(r"\bPham vi điu chnh\b", re.IGNORECASE), "Phạm vi điều chỉnh"),
    (re.compile(r"\bĐi tưrng áp dng\b", re.IGNORECASE), "Đối tượng áp dụng"),
    (re.compile(r"\bNguyên tc\b", re.IGNORECASE), "Nguyên tắc"),
    (re.compile(r"\bGii thích tù ng\b", re.IGNORECASE), "Giải thích từ ngữ"),
    (re.compile(r"\bt chc\b", re.IGNORECASE), "tổ chức"),
    (re.compile(r"\bhot đng\b", re.IGNORECASE), "hoạt động"),
    (re.compile(r"\bthm quyn\b", re.IGNORECASE), "thẩm quyền"),
    (re.compile(r"\btrình t\b", re.IGNORECASE), "trình tự"),
    (re.compile(r"\bth tc\b", re.IGNORECASE), "thủ tục"),
    (re.compile(r"\bt tng\b", re.IGNORECASE), "tố tụng"),
    (re.compile(r"\bbn án\b", re.IGNORECASE), "bản án"),
    (re.compile(r"\bquyt đnh\b", re.IGNORECASE), "quyết định"),
    (re.compile(r"\bThm phán\b", re.IGNORECASE), "Thẩm phán"),
    (re.compile(r"\bThư ký Ta án\b", re.IGNORECASE), "Thư ký Tòa án"),
    (re.compile(r"\bbo đm\b", re.IGNORECASE), "bảo đảm"),
    (re.compile(r"\bquyn hn\b", re.IGNORECASE), "quyền hạn"),
    (re.compile(r"\bhiu qu\b", re.IGNORECASE), "hiệu quả"),
    (re.compile(r"\btranh tng\b", re.IGNORECASE), "tranh tụng"),
    (re.compile(r"\blinh hot\b", re.IGNORECASE), "linh hoạt"),
    (re.compile(r"\bthương mi\b", re.IGNORECASE), "thương mại"),
    (re.compile(r"\bpháp lut\b", re.IGNORECASE), "pháp luật"),
    (re.compile(r"\bngưi đi din\b", re.IGNORECASE), "người đại diện"),
]
OCR_SUSPICIOUS_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bLut\b",
        r"\bĐiu\b",
        r"\bChurong\b",
        r"\bQuc\b",
        r"\bthm quyn\b",
        r"\bt tng\b",
        r"\bhot đng\b",
        r"\bhiu qu\b",
        r"\bgii quyt\b",
        r"\bquyt đnh\b",
        r"\bquc t\b",
    )
]
ARTICLE_BODY_START_TOKENS = {
    "luật",
    "trong",
    "tòa",
    "cơ",
    "chánh",
    "thẩm",
    "thư",
    "người",
    "quốc",
    "pháp",
    "việc",
    "áp",
}


@dataclass(frozen=True)
class OCRCapability:
    name: str
    available: bool
    kind: str
    notes: str


@dataclass(frozen=True)
class OCRTarget:
    canonical_id: str
    title: str
    document_number: str
    document_path: Path
    attachment_urls: list[str]
    text_source: str
    parse_confidence: str
    source_system: str
    recommended_backend: str
    recommendation_reason: str


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def detect_pdf_ocr_capabilities() -> list[OCRCapability]:
    ocr_env_available = get_settings().ocr_python_path.exists()
    return [
        OCRCapability(
            name="pymupdf",
            available=_module_available("fitz"),
            kind="direct_pdf_text",
            notes="Best first choice for digital-text PDFs before OCR.",
        ),
        OCRCapability(
            name="pypdf",
            available=_module_available("pypdf"),
            kind="direct_pdf_text",
            notes="Useful fallback for digital-text PDFs.",
        ),
        OCRCapability(
            name="pdfplumber",
            available=_module_available("pdfplumber"),
            kind="direct_pdf_text",
            notes="Useful for table-aware text extraction before OCR.",
        ),
        OCRCapability(
            name="paddleocr",
            available=_module_available("paddleocr") and _module_available("paddle"),
            kind="ocr_layout",
            notes="Recommended OCR/layout stack for Vietnamese legal PDFs via PP-OCRv5 and PP-StructureV3.",
        ),
        OCRCapability(
            name="paddleocr_ocr_env",
            available=ocr_env_available,
            kind="ocr_layout",
            notes="Dedicated Python 3.13 OCR environment for PaddleOCR scan-based PDF extraction.",
        ),
        OCRCapability(
            name="vietocr",
            available=_module_available("vietocr"),
            kind="ocr_recognition",
            notes="Vietnamese recognizer useful for line-level repair after layout detection.",
        ),
        OCRCapability(
            name="python-doctr",
            available=_module_available("doctr"),
            kind="ocr_layout",
            notes="Alternative OCR/layout stack with nested document structure export.",
        ),
        OCRCapability(
            name="tesseract",
            available=bool(shutil.which("tesseract")),
            kind="ocr_baseline",
            notes="Baseline OCR only; weaker for Vietnamese legal layout and structure.",
        ),
        OCRCapability(
            name="ocrmypdf",
            available=bool(shutil.which("ocrmypdf")),
            kind="ocr_wrapper",
            notes="Good wrapper for searchable-PDF generation when Tesseract is installed.",
        ),
        OCRCapability(
            name="pdftotext",
            available=bool(shutil.which("pdftotext")),
            kind="direct_pdf_text",
            notes="Fast text extraction for digital PDFs via Poppler.",
        ),
    ]


def recommend_ocr_backend(
    *, text_source: str, attachment_urls: list[str], parse_confidence: str
) -> tuple[str, str]:
    available = {item.name for item in detect_pdf_ocr_capabilities() if item.available}

    if text_source in {"pdf", "mixed"}:
        if "pymupdf" in available and "paddleocr_ocr_env" in available:
            return (
                "pymupdf_then_paddleocr_subprocess",
                "Try embedded-text extraction first, then fall back to the dedicated PaddleOCR environment on scan-only pages.",
            )
        if "pymupdf" in available:
            return (
                "pymupdf",
                "Try embedded-text extraction first for digital-born PDFs.",
            )
        if (
            "pypdf" in available
            or "pdfplumber" in available
            or "pdftotext" in available
        ):
            if "paddleocr_ocr_env" in available:
                return (
                    "direct_pdf_text_then_paddleocr_subprocess",
                    "Try direct text extraction first, then use the dedicated PaddleOCR environment when extraction stays empty.",
                )
            return (
                "direct_pdf_text",
                "Try direct text extraction first for digital-born PDFs.",
            )

    if "paddleocr_ocr_env" in available:
        return (
            "paddleocr_subprocess",
            "Dedicated PaddleOCR environment is available for scan-based Vietnamese legal PDFs.",
        )
    if "paddleocr" in available and "vietocr" in available:
        return (
            "paddleocr_ppstructure_plus_vietocr",
            "Best fit for Vietnamese legal PDFs: layout-aware OCR plus Vietnamese line repair.",
        )
    if "paddleocr" in available:
        return (
            "paddleocr_ppstructure",
            "Best available layout-aware OCR stack for Vietnamese legal PDFs.",
        )
    if "python-doctr" in available:
        return (
            "doctr",
            "Usable OCR/layout fallback when PaddleOCR is unavailable.",
        )
    if "ocrmypdf" in available and "tesseract" in available:
        return (
            "ocrmypdf_tesseract_vie",
            "Baseline searchable-PDF OCR fallback; expect weaker structure recovery.",
        )
    return (
        "paddleocr_ppstructure_plus_vietocr",
        "Recommended target stack even though it is not installed yet; strongest fit for Vietnamese legal PDFs and markdown structure mapping.",
    )


def iter_pdf_ocr_targets(
    limit: int | None = None, *, include_completed: bool = False
) -> list[OCRTarget]:
    targets: list[OCRTarget] = []
    for document in iter_canonical_documents():
        metadata = document.metadata
        attachments = [
            item
            for item in metadata.get("attachments") or []
            if PDF_SUFFIX_PATTERN.search(str(item))
        ]
        text_source = str(metadata.get("text_source") or "").lower()
        parse_confidence = str(metadata.get("parse_confidence") or "high").lower()
        if (
            not include_completed
            and text_source in {"pdf", "ocr"}
            and parse_confidence in {"medium", "high"}
        ):
            continue
        if not attachments and text_source not in {"pdf", "mixed", "ocr"}:
            continue
        backend, reason = recommend_ocr_backend(
            text_source=text_source,
            attachment_urls=attachments,
            parse_confidence=parse_confidence,
        )
        targets.append(
            OCRTarget(
                canonical_id=str(
                    metadata.get("canonical_id") or document.file_path.stem
                ),
                title=str(metadata.get("title") or document.file_path.stem),
                document_number=str(metadata.get("document_number") or ""),
                document_path=document.file_path,
                attachment_urls=attachments,
                text_source=text_source,
                parse_confidence=parse_confidence,
                source_system=str(metadata.get("source_system") or ""),
                recommended_backend=backend,
                recommendation_reason=reason,
            )
        )
        if limit is not None and len(targets) >= limit:
            break
    return targets


def build_pdf_ocr_queue(
    limit: int | None = None, *, include_completed: bool = False
) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for target in iter_pdf_ocr_targets(
        limit=limit, include_completed=include_completed
    ):
        queue.append(
            {
                "canonical_id": target.canonical_id,
                "title": target.title,
                "document_number": target.document_number,
                "document_path": target.document_path.as_posix(),
                "attachment_urls": target.attachment_urls,
                "text_source": target.text_source,
                "parse_confidence": target.parse_confidence,
                "source_system": target.source_system,
                "recommended_backend": target.recommended_backend,
                "recommendation_reason": target.recommendation_reason,
                "generated_at": utc_now_iso(),
            }
        )
    return queue


def _safe_attachment_filename(url: str, fallback: str) -> str:
    parsed = urlparse(url)
    name = Path(unquote(parsed.path)).name
    return name or fallback


def _load_canonical_document_by_id(canonical_id: str) -> CanonicalDocument | None:
    paths = ensure_corpus_layout()
    manifest_entry = load_jsonl_index(paths.documents_manifest).get(canonical_id)
    if manifest_entry is not None:
        markdown_path = paths.root / str(manifest_entry.get("markdown_path") or "")
        if markdown_path.exists():
            text = markdown_path.read_text(encoding="utf-8")
            metadata, body = split_frontmatter(text)
            return CanonicalDocument(
                file_path=markdown_path,
                metadata=metadata,
                body=body,
            )

    for document in iter_canonical_documents():
        if str(document.metadata.get("canonical_id") or "") == canonical_id:
            return document
    return None


def download_pdf_attachment(
    *, canonical_id: str, attachment_url: str, timeout: int = 120
) -> Path:
    paths = ensure_corpus_layout()
    filename = _safe_attachment_filename(attachment_url, f"{canonical_id}.pdf")
    target_path = paths.raw_root / RAW_PDF_DIRNAME / canonical_id / filename
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists() and target_path.stat().st_size > 0:
        return target_path

    request = Request(attachment_url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=timeout) as response:
        target_path.write_bytes(response.read())
    return target_path


def extract_text_with_pypdf(pdf_path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    page_texts: list[str] = []
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if text:
            page_texts.append(text)
    return "\n\n".join(page_texts).strip()


def extract_text_with_pymupdf(pdf_path: Path) -> str:
    import fitz

    document = fitz.open(pdf_path)
    page_texts: list[str] = []
    for page in document:
        text = (page.get_text("text") or "").strip()
        if text:
            page_texts.append(text)
    document.close()
    return "\n\n".join(page_texts).strip()


def choose_pdf_text_backend() -> str:
    available = {item.name for item in detect_pdf_ocr_capabilities() if item.available}
    if "pymupdf" in available:
        return "pymupdf"
    if "pypdf" in available:
        return "pypdf"
    if "pdfplumber" in available:
        return "pdfplumber"
    if "pdftotext" in available:
        return "pdftotext"
    raise RuntimeError("No direct PDF text backend is available in this environment.")


def _ocr_runner_script_path() -> Path:
    return BASE_DIR / "scripts" / "paddleocr_extract_text.py"


def has_paddleocr_ocr_env() -> bool:
    settings = get_settings()
    return settings.ocr_python_path.exists() and _ocr_runner_script_path().exists()


def extract_pdf_text(pdf_path: Path, *, backend: str = "auto") -> tuple[str, str]:
    resolved_backend = choose_pdf_text_backend() if backend == "auto" else backend
    if resolved_backend == "pymupdf":
        return extract_text_with_pymupdf(pdf_path), resolved_backend
    if resolved_backend == "pypdf":
        return extract_text_with_pypdf(pdf_path), resolved_backend
    raise RuntimeError(f"Unsupported PDF backend: {resolved_backend}")


def extract_text_with_paddleocr_env(
    pdf_path: Path,
    *,
    timeout: int = 1800,
    quality: str = "fast",
    max_pages: int | None = None,
) -> tuple[str, str]:
    if not has_paddleocr_ocr_env():
        raise RuntimeError("Dedicated PaddleOCR OCR environment is not available.")
    settings = get_settings()
    command = [
        str(settings.ocr_python_path),
        str(_ocr_runner_script_path()),
        "--pdf-file",
        str(pdf_path),
        "--quality",
        quality,
    ]
    if max_pages:
        command.extend(["--max-pages", str(max_pages)])
    environment = dict(os.environ)
    environment.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    environment.setdefault("FLAGS_use_mkldnn", "0")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=True,
        env=environment,
    )
    payload = json.loads(result.stdout)
    backend_name = (
        "paddleocr_subprocess_hq" if quality == "high" else "paddleocr_subprocess"
    )
    return str(payload.get("raw_text") or ""), backend_name


def estimate_extracted_text_confidence(raw_text: str) -> str:
    normalized = normalize_ocr_text(raw_text)
    article_count = 0
    chapter_count = 0
    for line in normalized.split("\n"):
        line = normalize_ocr_legal_line(line.strip())
        detected = detect_section(line.strip())
        if not detected:
            continue
        if detected[0] == "article":
            article_count += 1
        elif detected[0] == "chapter":
            chapter_count += 1
    if article_count >= 3:
        return "high"
    if article_count >= 1 or chapter_count >= 1 or len(normalized) >= 1500:
        return "medium"
    return "low"


def normalize_ocr_text(raw_text: str) -> str:
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    text = MULTISPACE_PATTERN.sub(" ", text)
    text = re.sub(r" *\n *", "\n", text)
    corrected, _ = apply_vietnamese_legal_ocr_corrections(text)
    return MULTIBLANK_PATTERN.sub("\n\n", corrected).strip()


def apply_vietnamese_legal_ocr_corrections(raw_text: str) -> tuple[str, int]:
    corrected = raw_text
    correction_hits = 0
    for pattern, replacement in OCR_PHRASE_CORRECTIONS:
        corrected, hit_count = pattern.subn(replacement, corrected)
        correction_hits += hit_count
    return corrected, correction_hits


def assess_ocr_llm_need(raw_text: str) -> dict[str, Any]:
    normalized_text = normalize_ocr_text(raw_text)
    _, correction_hits = apply_vietnamese_legal_ocr_corrections(raw_text)
    suspicious_hits = sum(
        len(pattern.findall(normalized_text)) for pattern in OCR_SUSPICIOUS_PATTERNS
    )
    article_count = 0
    chapter_count = 0
    for line in normalized_text.split("\n"):
        detected = detect_section(line.strip())
        if not detected:
            continue
        if detected[0] == "article":
            article_count += 1
        elif detected[0] == "chapter":
            chapter_count += 1

    recommendation = "not_needed"
    reason = "Deterministic OCR and correction are likely sufficient for this document."
    if suspicious_hits >= 25 or (suspicious_hits >= 12 and article_count < 8):
        recommendation = "recommended"
        reason = "Substantial OCR corruption remains after correction; an OCR LLM sidecar would likely help with low-confidence spans and heading repair."
    elif correction_hits >= 15 or suspicious_hits >= 5:
        recommendation = "optional"
        reason = "Deterministic OCR is usable, but an OCR LLM post-correction pass could improve Vietnamese diacritics and legal phrasing."

    return {
        "recommendation": recommendation,
        "reason": reason,
        "correction_hits": correction_hits,
        "suspicious_hits": suspicious_hits,
        "article_count": article_count,
        "chapter_count": chapter_count,
        "character_count": len(normalized_text),
    }


def normalize_ocr_legal_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""
    normalized = normalize_ascii(stripped).lower()
    for source, replacement in OCR_ENACTMENT_MAP.items():
        if normalized.startswith(source):
            return replacement

    parts = stripped.split(maxsplit=1)
    first_token = parts[0]
    remainder = parts[1] if len(parts) > 1 else ""
    first_norm = normalize_ascii(first_token).lower().rstrip(":.;")
    replacement = OCR_LEGAL_TOKEN_MAP.get(first_norm)
    if replacement:
        return f"{replacement} {remainder}".strip()
    return stripped


def _is_upper_heading_candidate(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    alpha_chars = [char for char in stripped if char.isalpha()]
    if not alpha_chars:
        return False
    uppercase_ratio = sum(1 for char in alpha_chars if char.isupper()) / len(
        alpha_chars
    )
    return uppercase_ratio >= 0.75 and len(stripped.split()) <= 16


def _looks_like_article_heading_continuation(previous: str, current: str) -> bool:
    if not previous or not current:
        return False
    detected = detect_section(previous)
    if not detected or detected[0] != "article":
        return False
    if _looks_like_new_block(current):
        return False
    current_words = current.split()
    if len(current_words) > 5:
        return False
    if current.endswith((".", ";", ":")):
        return False
    first_token = normalize_ascii(current_words[0]).lower() if current_words else ""
    if first_token in ARTICLE_BODY_START_TOKENS:
        return False
    return current[:1].islower() or _is_upper_heading_candidate(current)


def _looks_like_new_block(line: str) -> bool:
    return any(
        pattern.match(line)
        for pattern in (
            HEADING_PATTERN,
            ANNEX_HEADING_PATTERN,
            ENACTMENT_LINE_PATTERN,
            NUMBER_BLOCK_PATTERN,
            CLAUSE_PATTERN,
            POINT_PATTERN,
            DASH_PATTERN,
            ENDMATTER_PATTERN,
        )
    ) or bool(detect_section(line))


def _should_merge_with_previous(previous: str, current: str) -> bool:
    if not previous or not current:
        return False
    if _looks_like_article_heading_continuation(previous, current):
        return True
    previous_detected = detect_section(previous)
    if previous_detected:
        if previous_detected[0] == "article":
            return False
        if previous_detected[0] in {"part", "chapter", "section", "heading"}:
            if _is_upper_heading_candidate(current):
                return True
            return False
    if _is_upper_heading_candidate(previous) and _is_upper_heading_candidate(current):
        return False
    if _looks_like_new_block(current):
        return False
    if previous.endswith(":"):
        return False
    if previous.endswith((".", ";", "!", "?")):
        return False
    if LOWER_CONTINUATION_PATTERN.match(current):
        return True
    if current[:1].isdigit() and not CLAUSE_PATTERN.match(current):
        return True
    if len(current.split()) <= 5 and not current.isupper():
        return True
    return True


def _merge_ocr_lines(lines: list[str]) -> list[str]:
    merged: list[str] = []
    for line in lines:
        if not line:
            if merged and merged[-1] != "":
                merged.append("")
            continue
        if PAGE_NUMBER_PATTERN.match(line):
            continue
        if merged and merged[-1] and _should_merge_with_previous(merged[-1], line):
            merged[-1] = f"{merged[-1]} {line}".strip()
            continue
        merged.append(line)
    while merged and merged[-1] == "":
        merged.pop()
    return merged


def map_ocr_text_to_markdown(raw_text: str, *, title: str = "") -> str:
    normalized = normalize_ocr_text(raw_text)
    raw_lines = [
        normalize_ocr_legal_line(line.strip()) for line in normalized.split("\n")
    ]
    merged_lines = _merge_ocr_lines(raw_lines)
    markdown_lines: list[str] = []
    if title:
        markdown_lines.extend([f"# {title}", ""])

    for line in merged_lines:
        if not line:
            if markdown_lines and markdown_lines[-1] != "":
                markdown_lines.append("")
            continue
        detected = detect_section(line)
        if detected:
            section_type = detected[0]
            level = 4
            if section_type == "part":
                level = 2
            elif section_type == "chapter":
                level = 3
            elif section_type in {"section", "heading"}:
                level = 4
            elif section_type == "article":
                level = 5
            if markdown_lines and markdown_lines[-1] != "":
                markdown_lines.append("")
            markdown_lines.append(f"{'#' * level} {line}")
            markdown_lines.append("")
            continue
        markdown_lines.append(line)

    result = "\n".join(markdown_lines).strip()
    result = MULTIBLANK_PATTERN.sub("\n\n", result)
    return f"{result}\n" if result else ""


def apply_ocr_text_to_document(
    *, canonical_id: str, raw_text: str, backend: str, raw_text_extension: str = ".txt"
) -> dict[str, Any]:
    return apply_extracted_text_to_document(
        canonical_id=canonical_id,
        raw_text=raw_text,
        backend=backend,
        text_source="ocr",
        parse_confidence="medium",
        raw_text_extension=raw_text_extension,
    )


def apply_extracted_text_to_document(
    *,
    canonical_id: str,
    raw_text: str,
    backend: str,
    text_source: str,
    parse_confidence: str,
    raw_text_extension: str = ".txt",
    extraction_notes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paths = ensure_corpus_layout()
    manifest_index = load_jsonl_index(paths.documents_manifest)
    target_document = _load_canonical_document_by_id(canonical_id)
    if target_document is None:
        raise ValueError(f"Unknown canonical_id: {canonical_id}")

    metadata = dict(target_document.metadata)
    metadata.pop("extraction_notes", None)
    metadata.pop("partial_ocr", None)
    metadata.pop("ocr_page_limit", None)
    metadata.pop("ocr_note", None)
    llm_assessment = assess_ocr_llm_need(raw_text)
    markdown_body = map_ocr_text_to_markdown(
        raw_text, title=str(metadata.get("title") or "")
    )
    metadata["text_source"] = text_source
    metadata["parse_confidence"] = parse_confidence
    if extraction_notes:
        metadata["partial_ocr"] = bool(extraction_notes.get("partial_ocr"))
        metadata["ocr_page_limit"] = int(extraction_notes.get("max_ocr_pages") or 0)
        metadata["ocr_note"] = str(extraction_notes.get("reason") or "")
    metadata["updated_at"] = utc_now_iso()
    metadata["markdown_hash"] = sha256_text(markdown_body)
    write_canonical_document(target_document, metadata, markdown_body)

    raw_dir = paths.raw_root / RAW_OCR_DIRNAME
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{canonical_id}{raw_text_extension}"
    raw_path.write_text(raw_text, encoding="utf-8")

    sidecar_path = paths.manifests_root / f"{canonical_id}.ocr.json"
    sidecar_path.write_text(
        json.dumps(
            {
                "canonical_id": canonical_id,
                "backend": backend,
                "generated_at": utc_now_iso(),
                "raw_text_path": raw_path.relative_to(paths.root).as_posix(),
                "extraction_notes": extraction_notes or {},
                "ocr_llm_assessment": llm_assessment,
                "mapped_markdown_preview": markdown_body[:4000],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_entry = manifest_index.get(canonical_id)
    if manifest_entry is not None:
        manifest_index[canonical_id] = {
            **manifest_entry,
            "text_source": text_source,
            "parse_confidence": parse_confidence,
            "updated_at": metadata["updated_at"],
            "markdown_hash": metadata["markdown_hash"],
        }
        write_jsonl_records(
            paths.documents_manifest,
            sorted(manifest_index.values(), key=lambda item: item["canonical_id"]),
        )

    return {
        "canonical_id": canonical_id,
        "backend": backend,
        "raw_text_path": raw_path.relative_to(paths.root).as_posix(),
        "sidecar_path": sidecar_path.relative_to(paths.root).as_posix(),
        "ocr_llm_assessment": llm_assessment,
    }


def process_pdf_attachment_for_document(
    *,
    canonical_id: str,
    attachment_index: int = 0,
    backend: str = "auto",
    timeout: int = 120,
    max_ocr_pages: int | None = None,
) -> dict[str, Any]:
    target_document = _load_canonical_document_by_id(canonical_id)
    if target_document is None:
        raise ValueError(f"Unknown canonical_id: {canonical_id}")

    attachment_urls = [
        item
        for item in target_document.metadata.get("attachments") or []
        if PDF_SUFFIX_PATTERN.search(str(item))
    ]
    if not attachment_urls:
        raise ValueError(f"Document {canonical_id} has no PDF attachment URLs")
    if attachment_index < 0 or attachment_index >= len(attachment_urls):
        raise IndexError(
            f"attachment_index {attachment_index} is out of range for {len(attachment_urls)} attachments"
        )

    attachment_url = str(attachment_urls[attachment_index])
    pdf_path = download_pdf_attachment(
        canonical_id=canonical_id,
        attachment_url=attachment_url,
        timeout=timeout,
    )
    extracted_text = ""
    resolved_backend = backend
    text_source = "pdf"
    extraction_notes: dict[str, Any] = {}

    if backend in {"auto", "pymupdf", "pypdf", "pdfplumber", "pdftotext"}:
        try:
            extracted_text, resolved_backend = extract_pdf_text(
                pdf_path, backend=backend
            )
        except RuntimeError:
            extracted_text = ""

    parse_confidence = estimate_extracted_text_confidence(extracted_text)
    should_fallback_to_ocr = (
        backend == "auto" and has_paddleocr_ocr_env() and parse_confidence == "low"
    ) or backend in {
        "paddleocr_subprocess",
        "paddleocr_subprocess_hq",
        "pymupdf_then_paddleocr_subprocess",
        "direct_pdf_text_then_paddleocr_subprocess",
    }
    if should_fallback_to_ocr:
        ocr_quality = "high" if backend == "paddleocr_subprocess_hq" else "fast"
        ocr_text, ocr_backend = extract_text_with_paddleocr_env(
            pdf_path,
            timeout=max(timeout, 1800),
            quality=ocr_quality,
            max_pages=max_ocr_pages,
        )
        ocr_confidence = estimate_extracted_text_confidence(ocr_text)
        if ocr_text.strip() and ocr_confidence >= parse_confidence:
            extracted_text = ocr_text
            resolved_backend = ocr_backend
            parse_confidence = ocr_confidence
            text_source = "ocr"
            if max_ocr_pages:
                extraction_notes = {
                    "partial_ocr": True,
                    "max_ocr_pages": max_ocr_pages,
                    "reason": "Full scan OCR is expensive; leading pages were extracted for search preview coverage.",
                }

    if not extracted_text.strip():
        raise RuntimeError(
            f"No text could be extracted from PDF attachment for {canonical_id}."
        )

    result = apply_extracted_text_to_document(
        canonical_id=canonical_id,
        raw_text=extracted_text,
        backend=resolved_backend,
        text_source=text_source,
        parse_confidence=parse_confidence,
        extraction_notes=extraction_notes,
    )
    return {
        **result,
        "attachment_url": attachment_url,
        "pdf_path": pdf_path.as_posix(),
        "backend": resolved_backend,
        "text_source": text_source,
        "parse_confidence": parse_confidence,
    }
