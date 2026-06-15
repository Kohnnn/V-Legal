from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ai_schema import maybe_generate_ai_schema_interpretation
from .citations import extract_section_mentions
from .hf_ingest import build_excerpt, normalize_text, split_into_passages
from .settings import get_settings
from .structure import (
    DOC_NUMBER_IN_TEXT_PATTERN,
    detect_section,
    extract_sections,
    is_annex_heading,
    is_endmatter_paragraph,
    is_enactment_line,
    is_legal_type_line,
    is_preamble_start,
    is_promulgator_line,
    split_display_paragraphs,
    split_motto,
    split_official_pair,
)
from .taxonomy import normalize_ascii


SCHEMA_VERSION = 1
LOCAL_AUTHORITY_MARKERS = (
    "uy ban nhan dan",
    "ubnd",
    "hoi dong nhan dan",
    "hdnd",
)
LOCALITY_PATTERN = re.compile(r"\b(?:tinh|thanh pho)\s+([a-z0-9\s-]{2,60})")
FRONTMATTER_BOUNDARY = "---"
TITLE_HEADING_PATTERN = re.compile(r"^#\s+(.*)$")
ISO_DATE_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
YEAR_PREFIX_PATTERN = re.compile(r"^(\d{4})")
NON_ALNUM_PATTERN = re.compile(r"[^0-9a-z]+")
BLANK_LINE_PATTERN = re.compile(r"\n{3,}")
SOURCE_SYSTEM_CODES = {
    "hf_bootstrap": "hf",
    "vbpl": "vbpl",
    "vanban_chinhphu": "vpcp",
    "phapdien": "phapdien",
}
SECTION_HEADING_LEVELS = {
    "part": 2,
    "chapter": 3,
    "section": 4,
    "heading": 4,
    "article": 5,
}


@dataclass(frozen=True)
class CorpusPaths:
    root: Path
    markdown_root: Path
    issued_root: Path
    phapdien_root: Path
    raw_root: Path
    manifests_root: Path
    sidecars_root: Path
    sqlite_root: Path
    documents_manifest: Path
    source_runs_manifest: Path
    conflicts_manifest: Path


@dataclass(frozen=True)
class CanonicalDocument:
    file_path: Path
    metadata: dict[str, Any]
    body: str


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def slugify_token(
    value: str | None, *, fallback: str = "document", limit: int = 80
) -> str:
    normalized = normalize_ascii(value or "")
    normalized = NON_ALNUM_PATTERN.sub("-", normalized).strip("-")
    if not normalized:
        return fallback
    return normalized[:limit].strip("-") or fallback


def get_corpus_paths() -> CorpusPaths:
    settings = get_settings()
    root = settings.corpus_root
    manifests_root = root / "manifests"
    return CorpusPaths(
        root=root,
        markdown_root=root / "markdown",
        issued_root=root / "markdown" / "issued",
        phapdien_root=root / "markdown" / "phapdien",
        raw_root=root / "raw",
        manifests_root=manifests_root,
        sidecars_root=manifests_root / "sidecars",
        sqlite_root=root / "sqlite",
        documents_manifest=manifests_root / "documents.jsonl",
        source_runs_manifest=manifests_root / "source_runs.jsonl",
        conflicts_manifest=manifests_root / "conflicts.jsonl",
    )


def ensure_corpus_layout() -> CorpusPaths:
    paths = get_corpus_paths()
    for path in (
        paths.root,
        paths.markdown_root,
        paths.issued_root,
        paths.phapdien_root,
        paths.raw_root,
        paths.manifests_root,
        paths.sidecars_root,
        paths.sqlite_root,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return paths


def reset_corpus_layout(*, keep_sqlite: bool = True) -> CorpusPaths:
    paths = ensure_corpus_layout()
    for path in (paths.markdown_root, paths.raw_root, paths.manifests_root):
        if path.exists():
            shutil.rmtree(path)
    if not keep_sqlite and paths.sqlite_root.exists():
        shutil.rmtree(paths.sqlite_root)
    return ensure_corpus_layout()


def build_canonical_id(
    *,
    source_system: str,
    source_document_id: str | int,
    document_layer: str = "issued",
) -> str:
    source_code = SOURCE_SYSTEM_CODES.get(source_system, slugify_token(source_system))
    source_id = slugify_token(str(source_document_id), fallback="unknown", limit=120)
    if document_layer == "phapdien":
        return f"vn-phapdien-{source_id}"
    return f"vn-{document_layer}-{source_code}-{source_id}"


def build_internal_document_id(canonical_id: str) -> int:
    digest = hashlib.sha256(canonical_id.encode("utf-8")).hexdigest()[:15]
    value = int(digest, 16) % ((1 << 63) - 1)
    return value or 1


def _infer_locality_slug(issuing_authority: str | None) -> str | None:
    authority = normalize_ascii(issuing_authority or "")
    match = LOCALITY_PATTERN.search(authority)
    if not match:
        return None
    return slugify_token(match.group(1), fallback="khong-ro")


def infer_jurisdiction_branch(record: dict) -> tuple[str, list[str]]:
    authority = normalize_ascii(record.get("issuing_authority") or "")
    year_token = extract_year_token(record.get("issuance_date"), record.get("year"))
    if any(marker in authority for marker in LOCAL_AUTHORITY_MARKERS):
        locality_slug = (
            _infer_locality_slug(record.get("issuing_authority")) or "dia-phuong"
        )
        return "local", [locality_slug, year_token]
    return "central", [year_token]


def extract_year_token(issuance_date: str | None, year: int | None = None) -> str:
    if year:
        return str(year)
    value = (issuance_date or "").strip()
    match = ISO_DATE_PATTERN.match(value) or YEAR_PREFIX_PATTERN.match(value)
    if not match:
        return "unknown"
    return match.group(1)


def build_markdown_body(record: dict) -> str:
    title = (record.get("title") or f"Document {record.get('id')}").strip()
    content = (record.get("content") or "").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = [f"# {title}", ""]

    for raw_line in content.split("\n"):
        line = raw_line.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue

        if line.startswith("#"):
            lines.append(line)
            if lines[-1] != "":
                lines.append("")
            continue

        detected = detect_section(line)
        if detected:
            heading_level = SECTION_HEADING_LEVELS.get(detected[0], 4)
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"{'#' * heading_level} {line}")
            lines.append("")
            continue

        lines.append(line)

    body = "\n".join(lines).strip()
    body = BLANK_LINE_PATTERN.sub("\n\n", body)
    return f"{body}\n"


def strip_title_heading(markdown_body: str, title: str | None) -> str:
    normalized_title = normalize_ascii(title or "")
    lines = markdown_body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines:
        return ""
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        return ""
    match = TITLE_HEADING_PATTERN.match(lines[index].strip())
    if not match:
        return markdown_body.strip()
    if normalize_ascii(match.group(1)) != normalized_title:
        return markdown_body.strip()
    body_lines = lines[index + 1 :]
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    return "\n".join(body_lines).strip()


def _serialize_yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _render_frontmatter_value(lines: list[str], key: str, value: Any, indent: int = 0) -> None:
    prefix = " " * indent
    if isinstance(value, list):
        if not value:
            lines.append(f"{prefix}{key}: []")
            return
        lines.append(f"{prefix}{key}:")
        for item in value:
            lines.append(f"{prefix}  - {_serialize_yaml_scalar(item)}")
        return
    if isinstance(value, dict):
        if not value:
            lines.append(f"{prefix}{key}: {{}}")
            return
        lines.append(f"{prefix}{key}:")
        for nested_key, nested_value in value.items():
            _render_frontmatter_value(
                lines,
                str(nested_key),
                nested_value,
                indent=indent + 2,
            )
        return
    lines.append(f"{prefix}{key}: {_serialize_yaml_scalar(value)}")


def render_frontmatter(metadata: dict[str, Any]) -> str:
    lines = [FRONTMATTER_BOUNDARY]
    for key, value in metadata.items():
        _render_frontmatter_value(lines, key, value)
    lines.append(FRONTMATTER_BOUNDARY)
    return "\n".join(lines)


def _parse_yaml_scalar(value: str) -> Any:
    raw = value.strip()
    if raw == "[]":
        return []
    if raw in {"true", "false", "null"}:
        return json.loads(raw)
    if raw.startswith('"') or raw.startswith("["):
        return json.loads(raw)
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    return raw


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith(f"{FRONTMATTER_BOUNDARY}\n"):
        return {}, normalized
    boundary = f"\n{FRONTMATTER_BOUNDARY}\n"
    end_index = normalized.find(boundary, len(FRONTMATTER_BOUNDARY) + 1)
    if end_index == -1:
        return {}, normalized
    block = normalized[len(FRONTMATTER_BOUNDARY) + 1 : end_index]
    body = normalized[end_index + len(boundary) :]
    metadata: dict[str, Any] = {}
    current_list_key: str | None = None
    for line in block.split("\n"):
        if not line.strip():
            continue
        if line.startswith("  - ") and current_list_key:
            metadata.setdefault(current_list_key, []).append(
                _parse_yaml_scalar(line[4:])
            )
            continue
        key, _, raw_value = line.partition(":")
        key = key.strip()
        raw_value = raw_value.strip()
        if not key:
            continue
        if not raw_value:
            metadata[key] = []
            current_list_key = key
            continue
        metadata[key] = _parse_yaml_scalar(raw_value)
        current_list_key = None
    return metadata, body


def build_frontmatter_metadata(
    record: dict,
    *,
    canonical_id: str,
    source_system: str,
    source_document_id: str | int,
    source_hash: str,
    markdown_hash: str,
    document_layer: str,
    source_url: str,
    text_source: str,
    parse_confidence: str,
    trust_level: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "canonical_id": canonical_id,
        "document_layer": document_layer,
        "title": record.get("title") or f"Document {record.get('id')}",
        "document_number": record.get("document_number") or "",
        "document_type": record.get("legal_type") or "",
        "issuing_authority": record.get("issuing_authority") or "",
        "issuance_date": normalize_frontmatter_date(record.get("issuance_date") or ""),
        "effective_date": record.get("effective_date") or "",
        "expiry_date": record.get("expiry_date") or "",
        "status": record.get("status") or "unknown",
        "language": "vi",
        "source_system": source_system,
        "source_document_id": str(source_document_id),
        "source_url": source_url,
        "official_source_system": record.get("official_source_system") or "",
        "official_source_document_id": record.get("official_source_document_id") or "",
        "official_source_url": record.get("official_source_url") or "",
        "source_hash": source_hash,
        "markdown_hash": markdown_hash,
        "text_source": text_source,
        "parse_confidence": parse_confidence,
        "updated_at": utc_now_iso(),
        "official_journal": record.get("official_journal") or "",
        "scope": record.get("scope") or infer_jurisdiction_branch(record)[0],
        "signers": [item for item in split_pipe_values(record.get("signers"))],
        "legal_sectors": [
            item for item in split_pipe_values(record.get("legal_sectors"))
        ],
        "attachments": record.get("attachments") or [],
        "provisional": bool(record.get("provisional") or False),
        "supersedes": record.get("supersedes") or [],
        "superseded_by": record.get("superseded_by") or [],
        "phapdien_topics": record.get("phapdien_topics") or [],
        "trust_level": trust_level,
    }


def split_pipe_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split("|") if item.strip()]


def normalize_frontmatter_date(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    if ISO_DATE_PATTERN.match(raw):
        return raw
    try:
        return datetime.strptime(raw, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return raw


def format_date_for_database(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return raw


def estimate_parse_confidence(markdown_body: str, record: dict) -> str:
    content = strip_title_heading(markdown_body, record.get("title") or "")
    sections = extract_sections(content)
    article_count = sum(
        1 for section in sections if section["section_type"] == "article"
    )
    structural_count = sum(
        1
        for section in sections
        if section["section_type"]
        in {"article", "chapter", "part", "section", "heading"}
    )
    confidence = "low"
    if article_count >= 1 and record.get("document_number"):
        confidence = "high"
    elif structural_count >= 2 or len(content) >= 1500:
        confidence = "medium"

    text_source = (record.get("text_source") or "html").lower()
    if text_source in {"pdf", "ocr", "mixed"} and confidence == "high":
        return "medium"
    return confidence


def infer_structural_blocks(
    markdown_body: str, title: str | None = None
) -> list[dict[str, Any]]:
    body = strip_title_heading(markdown_body, title)
    blocks: list[dict[str, Any]] = []
    for ordinal, paragraph in enumerate(split_display_paragraphs(body), start=1):
        normalized_paragraph = re.sub(r"^#+\s*", "", paragraph).strip()
        if not normalized_paragraph:
            continue
        block_type = "body"
        details: dict[str, Any] = {}
        pair = split_official_pair(normalized_paragraph)
        if pair and any(is_promulgator_line(part) for part in pair):
            block_type = "official_pair"
            details = {"left": pair[0], "right": pair[1]}
        else:
            motto = split_motto(normalized_paragraph)
            if motto[1]:
                block_type = "motto"
                details = {"left": motto[0], "right": motto[1]}
            elif is_promulgator_line(normalized_paragraph):
                block_type = "promulgator"
            elif len(normalized_paragraph) <= 140 and DOC_NUMBER_IN_TEXT_PATTERN.search(
                normalized_paragraph
            ):
                block_type = "number_line"
            elif is_legal_type_line(normalized_paragraph):
                block_type = "legal_type"
            elif is_enactment_line(normalized_paragraph):
                block_type = "enactment"
            elif is_preamble_start(normalized_paragraph):
                block_type = "preamble"
            elif is_annex_heading(normalized_paragraph):
                block_type = "annex_heading"
            elif is_endmatter_paragraph(normalized_paragraph):
                block_type = "endmatter"
        blocks.append(
            {
                "ordinal": ordinal,
                "block_type": block_type,
                "text": normalized_paragraph,
                **details,
            }
        )
    return blocks


def build_deterministic_sidecar(
    metadata: dict[str, Any], record: dict, markdown_body: str
) -> dict[str, Any]:
    content = strip_title_heading(markdown_body, record.get("title") or "")
    sections = extract_sections(content)
    pseudo_document = {
        "document_number": record.get("document_number") or "",
        "title": record.get("title") or "",
        "issuing_authority": record.get("issuing_authority") or "",
        "year": record.get("year"),
    }
    citation_mentions: list[dict[str, Any]] = []
    for section in sections:
        if not section.get("text"):
            continue
        for mention in extract_section_mentions(section, pseudo_document):
            citation_mentions.append(
                {
                    "section_anchor": section["anchor"],
                    "section_label": section["label"],
                    **mention,
                }
            )
    outline = [
        {
            "section_type": section["section_type"],
            "label": section["label"],
            "anchor": section["anchor"],
        }
        for section in sections
        if section["section_type"]
        in {"part", "chapter", "section", "article", "heading"}
    ]
    structural_blocks = infer_structural_blocks(markdown_body, record.get("title"))
    return {
        "schema_version": SCHEMA_VERSION,
        "canonical_id": metadata["canonical_id"],
        "generated_at": utc_now_iso(),
        "parse_confidence": metadata["parse_confidence"],
        "counts": {
            "sections": len(sections),
            "outline_items": len(outline),
            "citation_mentions": len(citation_mentions),
            "structural_blocks": len(structural_blocks),
        },
        "sections": sections,
        "outline": outline,
        "structural_blocks": structural_blocks,
        "citation_mentions": citation_mentions,
    }


def _resolve_snapshot_extension(extension: str | None, default: str) -> str:
    candidate = (extension or default or ".txt").strip()
    if not candidate.startswith("."):
        candidate = f".{candidate}"
    return candidate


def build_markdown_file_path(paths: CorpusPaths, metadata: dict[str, Any]) -> Path:
    canonical_id = metadata["canonical_id"]
    slug_source = (
        metadata.get("document_number") or metadata.get("title") or canonical_id
    )
    slug = slugify_token(slug_source, fallback="van-ban")
    document_layer = metadata.get("document_layer") or "issued"
    if document_layer == "phapdien":
        return paths.phapdien_root / f"{canonical_id}--{slug}.md"

    branch = slugify_token(metadata.get("scope") or "central", fallback="central")
    year_token = extract_year_token(metadata.get("issuance_date") or "")
    if branch == "local":
        locality = _infer_locality_slug(
            metadata.get("issuing_authority")
        ) or slugify_token(metadata.get("issuing_authority") or "dia-phuong")
        return (
            paths.issued_root
            / branch
            / locality
            / year_token
            / f"{canonical_id}--{slug}.md"
        )
    return paths.issued_root / branch / year_token / f"{canonical_id}--{slug}.md"


def build_raw_snapshot_path(
    paths: CorpusPaths,
    *,
    source_system: str,
    canonical_id: str,
    extension: str,
) -> Path:
    ext = _resolve_snapshot_extension(extension, ".txt")
    return (
        paths.raw_root
        / slugify_token(source_system, fallback="source")
        / f"{canonical_id}{ext}"
    )


def build_sidecar_path(paths: CorpusPaths, canonical_id: str) -> Path:
    return paths.sidecars_root / f"{canonical_id}.json"


def _write_text_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")


def _write_bytes_if_changed(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content:
        return
    path.write_bytes(content)


def emit_canonical_document(
    record: dict,
    *,
    source_system: str,
    source_document_id: str | int,
    raw_snapshot: str | bytes | None = None,
    raw_snapshot_extension: str = ".txt",
    source_url: str = "",
    document_layer: str = "issued",
    trust_level: str = "bootstrap_only",
) -> dict[str, Any]:
    paths = ensure_corpus_layout()
    canonical_id = build_canonical_id(
        source_system=source_system,
        source_document_id=source_document_id,
        document_layer=document_layer,
    )
    markdown_body = build_markdown_body(record)
    markdown_hash = sha256_text(markdown_body)
    if raw_snapshot is None:
        raw_bytes = markdown_body.encode("utf-8")
    elif isinstance(raw_snapshot, str):
        raw_bytes = raw_snapshot.encode("utf-8")
    else:
        raw_bytes = raw_snapshot
    source_hash = sha256_bytes(raw_bytes)
    text_source = (record.get("text_source") or "html").lower()
    parse_confidence = estimate_parse_confidence(markdown_body, record)
    metadata = build_frontmatter_metadata(
        record,
        canonical_id=canonical_id,
        source_system=source_system,
        source_document_id=source_document_id,
        source_hash=source_hash,
        markdown_hash=markdown_hash,
        document_layer=document_layer,
        source_url=source_url,
        text_source=text_source,
        parse_confidence=parse_confidence,
        trust_level=trust_level,
    )
    markdown_path = build_markdown_file_path(paths, metadata)
    markdown_text = f"{render_frontmatter(metadata)}\n{markdown_body}"
    _write_text_if_changed(markdown_path, markdown_text)

    raw_path = build_raw_snapshot_path(
        paths,
        source_system=source_system,
        canonical_id=canonical_id,
        extension=raw_snapshot_extension,
    )
    _write_bytes_if_changed(raw_path, raw_bytes)

    sidecar = build_deterministic_sidecar(
        metadata, {**record, **metadata}, markdown_body
    )
    ai_interpretation = maybe_generate_ai_schema_interpretation(
        {**record, **metadata}, markdown_body, sidecar
    )
    if ai_interpretation:
        sidecar["ai_schema"] = ai_interpretation
    sidecar_path = build_sidecar_path(paths, canonical_id)
    _write_text_if_changed(
        sidecar_path,
        json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n",
    )

    relative_markdown_path = markdown_path.relative_to(paths.root).as_posix()
    relative_raw_path = raw_path.relative_to(paths.root).as_posix()
    relative_sidecar_path = sidecar_path.relative_to(paths.root).as_posix()
    return {
        "canonical_id": canonical_id,
        "internal_id": build_internal_document_id(canonical_id),
        "document_layer": document_layer,
        "title": metadata["title"],
        "document_number": metadata["document_number"],
        "source_system": source_system,
        "source_document_id": str(source_document_id),
        "source_url": source_url,
        "official_source_system": record.get("official_source_system") or "",
        "official_source_document_id": record.get("official_source_document_id") or "",
        "official_source_url": record.get("official_source_url") or "",
        "trust_level": trust_level,
        "text_source": text_source,
        "parse_confidence": parse_confidence,
        "issuance_date": metadata["issuance_date"],
        "markdown_path": relative_markdown_path,
        "raw_path": relative_raw_path,
        "sidecar_path": relative_sidecar_path,
        "source_hash": source_hash,
        "markdown_hash": markdown_hash,
        "updated_at": metadata["updated_at"],
    }


def load_jsonl_index(
    path: Path, *, key_field: str = "canonical_id"
) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    index: dict[str, dict[str, Any]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = item.get(key_field)
        if key:
            index[str(key)] = item
    return index


def write_jsonl_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records
    ]
    content = "\n".join(lines)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def write_canonical_document(
    document: CanonicalDocument, metadata: dict[str, Any], body: str
) -> None:
    _write_text_if_changed(
        document.file_path,
        f"{render_frontmatter(metadata)}\n{body.lstrip()}"
        if body
        else f"{render_frontmatter(metadata)}\n",
    )


def append_jsonl_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def iter_canonical_documents(limit: int | None = None) -> list[CanonicalDocument]:
    paths = ensure_corpus_layout()
    file_paths = sorted(paths.markdown_root.rglob("*.md"))
    if limit is not None:
        file_paths = file_paths[:limit]
    documents: list[CanonicalDocument] = []
    for file_path in file_paths:
        text = file_path.read_text(encoding="utf-8")
        metadata, body = split_frontmatter(text)
        documents.append(
            CanonicalDocument(file_path=file_path, metadata=metadata, body=body)
        )
    return documents


def build_record_from_canonical_document(document: CanonicalDocument) -> dict[str, Any]:
    metadata = document.metadata
    canonical_id = metadata.get("canonical_id") or slugify_token(
        document.file_path.stem
    )
    body = strip_title_heading(document.body, metadata.get("title") or "")
    content = body.strip()
    plain_content = normalize_text(content)
    issuance_date = format_date_for_database(str(metadata.get("issuance_date") or ""))
    year_token = extract_year_token(str(metadata.get("issuance_date") or ""))
    year = int(year_token) if year_token.isdigit() else None
    signers = " | ".join(metadata.get("signers") or [])
    legal_sectors = " | ".join(metadata.get("legal_sectors") or [])
    return {
        "id": build_internal_document_id(canonical_id),
        "canonical_id": canonical_id,
        "document_number": str(metadata.get("document_number") or ""),
        "title": str(metadata.get("title") or document.file_path.stem),
        "url": str(
            metadata.get("official_source_url") or metadata.get("source_url") or ""
        ),
        "legal_type": str(metadata.get("document_type") or ""),
        "legal_sectors": legal_sectors,
        "issuing_authority": str(metadata.get("issuing_authority") or ""),
        "issuance_date": issuance_date,
        "signers": signers,
        "content": content,
        "plain_content": plain_content,
        "excerpt": build_excerpt(plain_content),
        "year": year,
        "source": str(
            metadata.get("official_source_url")
            or metadata.get("source_url")
            or metadata.get("source_system")
            or "markdown_corpus"
        ),
        "source_system": str(metadata.get("source_system") or ""),
        "source_document_id": str(metadata.get("source_document_id") or ""),
        "document_layer": str(metadata.get("document_layer") or "issued"),
        "text_source": str(metadata.get("text_source") or "html"),
        "parse_confidence": str(metadata.get("parse_confidence") or "high"),
        "status": str(metadata.get("status") or "unknown"),
        "effective_date": format_date_for_database(
            str(metadata.get("effective_date") or "")
        ),
        "expiry_date": format_date_for_database(
            str(metadata.get("expiry_date") or "")
        ),
        "corpus_path": document.file_path.relative_to(
            get_corpus_paths().root
        ).as_posix(),
        "passages": split_into_passages(content),
    }
