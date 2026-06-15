from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .corpus import (
    append_jsonl_record,
    ensure_corpus_layout,
    iter_canonical_documents,
    load_jsonl_index,
    write_canonical_document,
    write_jsonl_records,
)
from .phapdien import parse_demuc_html
from .relations import normalize_document_number


ARTICLE_LABEL_PATTERN = re.compile(r"^(Điều\s+[^.]+(?:\.[^.]+)*\.)", re.IGNORECASE)
DOCUMENT_PATTERN = re.compile(
    r"\b(?P<legal_type>Bộ luật|Luật|Pháp lệnh|Nghị định|Nghị quyết|Quyết định|Chỉ thị|Thông tư liên tịch|Thông tư)\s+số\s+(?P<document_number>\d{1,4}/\d{4}/[0-9A-Za-z\u00c0-\u1ef9]+(?:\s*-\s*[0-9A-Za-z\u00c0-\u1ef9]+)*)",
    re.IGNORECASE,
)
ISSUANCE_DATE_PATTERN = re.compile(r"ngày\s+(\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE)
EFFECTIVE_DATE_PATTERN = re.compile(
    r"có hiệu lực thi hành kể từ ngày\s+(\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)
ISSUER_PATTERN = re.compile(
    r"của\s+(?P<issuer>[^,\)]+)",
    re.IGNORECASE,
)
WHITESPACE_PATTERN = re.compile(r"\s+")
VBPL_ITEM_ID_PATTERN = re.compile(r"ItemID=(\d+)", re.IGNORECASE)


def normalize_vbpl_url(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    raw = raw.replace("http://vbpl.vn", "https://vbpl.vn")
    raw = raw.replace("http://www.vbpl.vn", "https://vbpl.vn")
    return raw


def extract_item_id(url: str | None) -> str:
    normalized_url = normalize_vbpl_url(url)
    if not normalized_url:
        return ""
    match = VBPL_ITEM_ID_PATTERN.search(normalized_url)
    if match:
        return match.group(1)
    parsed = urlparse(normalized_url)
    values = parse_qs(parsed.query)
    return (values.get("ItemID") or [""])[0]


def clean_reference_text(value: str | None) -> str:
    text = (value or "").strip()
    text = text.strip("() ")
    text = WHITESPACE_PATTERN.sub(" ", text)
    return text.strip()


def parse_vbpl_reference_block(
    block: dict[str, Any], topic_entry: dict[str, Any]
) -> dict[str, Any] | None:
    links = [
        link
        for link in block.get("links", [])
        if "vbpl.vn" in (link.get("href") or "").lower()
    ]
    if not links:
        return None

    primary_link = links[0]
    raw_text = clean_reference_text(block.get("text") or "")
    if not raw_text:
        return None

    article_match = ARTICLE_LABEL_PATTERN.search(raw_text)
    document_match = DOCUMENT_PATTERN.search(raw_text)
    issuance_date_match = ISSUANCE_DATE_PATTERN.search(raw_text)
    effective_date_match = EFFECTIVE_DATE_PATTERN.search(raw_text)
    issuer_match = ISSUER_PATTERN.search(raw_text)

    document_number = ""
    legal_type = ""
    title = ""
    if document_match:
        legal_type = WHITESPACE_PATTERN.sub(
            " ", document_match.group("legal_type")
        ).strip()
        document_number = WHITESPACE_PATTERN.sub(
            " ", document_match.group("document_number")
        ).strip()
        document_number = re.sub(r"\s*-\s*", "-", document_number)
        start = document_match.end()
        end_candidates = []
        if issuance_date_match:
            end_candidates.append(issuance_date_match.start())
        if issuer_match:
            end_candidates.append(issuer_match.start())
        end = min(end_candidates) if end_candidates else len(raw_text)
        title = raw_text[start:end].strip(" ,")

    source_url = normalize_vbpl_url(primary_link.get("href"))
    item_id = extract_item_id(source_url)
    return {
        "source_system": "vbpl",
        "source_document_id": item_id,
        "source_url": source_url,
        "article_label": article_match.group(1).strip() if article_match else "",
        "document_number": document_number,
        "normalized_document_number": normalize_document_number(document_number),
        "legal_type": legal_type,
        "title": title,
        "issuance_date": issuance_date_match.group(1) if issuance_date_match else "",
        "effective_date": effective_date_match.group(1) if effective_date_match else "",
        "issuing_authority": issuer_match.group("issuer").strip()
        if issuer_match
        else "",
        "raw_text": raw_text,
        "topic_canonical_id": topic_entry.get("canonical_id") or "",
        "topic_id": topic_entry.get("topic_id")
        or topic_entry.get("source_document_id")
        or "",
        "topic_name": topic_entry.get("topic_name") or topic_entry.get("title") or "",
        "topic_markdown_path": topic_entry.get("markdown_path") or "",
        "document_list_url": topic_entry.get("document_list_url") or "",
    }


def harvest_vbpl_references_from_phapdien() -> dict[str, list[dict[str, Any]]]:
    paths = ensure_corpus_layout()
    manifest_index = load_jsonl_index(paths.documents_manifest)
    mention_records: list[dict[str, Any]] = []
    grouped_documents: dict[str, dict[str, Any]] = {}

    for entry in manifest_index.values():
        if entry.get("document_layer") != "phapdien":
            continue
        raw_path_value = entry.get("raw_path")
        if not raw_path_value:
            continue
        raw_path = paths.root / raw_path_value
        if not raw_path.exists() or raw_path.suffix.lower() != ".html":
            continue
        html = raw_path.read_text(encoding="utf-8", errors="ignore")
        _, blocks, _ = parse_demuc_html(html)
        for block in blocks:
            if block.get("kind") != "pGhiChu":
                continue
            parsed = parse_vbpl_reference_block(block, entry)
            if not parsed or not parsed.get("source_document_id"):
                continue
            mention_records.append(parsed)

            item_id = parsed["source_document_id"]
            document_record = grouped_documents.setdefault(
                item_id,
                {
                    "source_system": "vbpl",
                    "source_document_id": item_id,
                    "source_url": parsed["source_url"],
                    "document_number": parsed["document_number"],
                    "normalized_document_number": parsed["normalized_document_number"],
                    "legal_type": parsed["legal_type"],
                    "title": parsed["title"],
                    "issuance_date": parsed["issuance_date"],
                    "effective_date": parsed["effective_date"],
                    "issuing_authority": parsed["issuing_authority"],
                    "topic_ids": [],
                    "topic_names": [],
                    "topic_count": 0,
                    "mention_count": 0,
                },
            )
            if (
                parsed["topic_id"]
                and parsed["topic_id"] not in document_record["topic_ids"]
            ):
                document_record["topic_ids"].append(parsed["topic_id"])
            if (
                parsed["topic_name"]
                and parsed["topic_name"] not in document_record["topic_names"]
            ):
                document_record["topic_names"].append(parsed["topic_name"])
            document_record["topic_count"] = len(document_record["topic_ids"])
            document_record["mention_count"] += 1

    mention_path = paths.manifests_root / "vbpl_reference_mentions.jsonl"
    document_path = paths.manifests_root / "vbpl_reference_documents.jsonl"
    write_jsonl_records(
        mention_path,
        sorted(
            mention_records,
            key=lambda item: (
                item["source_document_id"],
                item["topic_canonical_id"],
                item["article_label"],
            ),
        ),
    )
    write_jsonl_records(
        document_path,
        sorted(grouped_documents.values(), key=lambda item: item["source_document_id"]),
    )
    append_jsonl_record(
        paths.source_runs_manifest,
        {
            "kind": "vbpl_reference_harvest_finished",
            "mention_count": len(mention_records),
            "document_count": len(grouped_documents),
            "mentions_path": mention_path.relative_to(paths.root).as_posix(),
            "documents_path": document_path.relative_to(paths.root).as_posix(),
        },
    )
    return {
        "mentions": mention_records,
        "documents": sorted(
            grouped_documents.values(), key=lambda item: item["source_document_id"]
        ),
    }


def backfill_official_vbpl_links_into_issued_corpus(
    *, overwrite: bool = False
) -> dict[str, int]:
    paths = ensure_corpus_layout()
    harvested = harvest_vbpl_references_from_phapdien()
    documents = harvested["documents"]
    manifest_index = load_jsonl_index(paths.documents_manifest)
    by_number: dict[str, list[dict[str, Any]]] = {}
    for item in documents:
        normalized_number = item.get("normalized_document_number") or ""
        if not normalized_number:
            continue
        by_number.setdefault(normalized_number, []).append(item)

    updated = 0
    candidates = 0
    for document in iter_canonical_documents():
        metadata = document.metadata
        if metadata.get("document_layer") != "issued":
            continue
        normalized_number = normalize_document_number(
            str(metadata.get("document_number") or "")
        )
        if not normalized_number:
            continue
        matches = by_number.get(normalized_number, [])
        if len(matches) != 1:
            continue
        candidates += 1
        match = matches[0]
        if metadata.get("official_source_url") and not overwrite:
            continue
        metadata = dict(metadata)
        metadata["official_source_system"] = "vbpl"
        metadata["official_source_document_id"] = match["source_document_id"]
        metadata["official_source_url"] = match["source_url"]
        existing_topics = list(metadata.get("phapdien_topics") or [])
        for topic_name in match.get("topic_names", []):
            if topic_name not in existing_topics:
                existing_topics.append(topic_name)
        metadata["phapdien_topics"] = existing_topics
        write_canonical_document(document, metadata, document.body)
        manifest_entry = manifest_index.get(metadata.get("canonical_id") or "")
        if manifest_entry is not None:
            manifest_index[metadata["canonical_id"]] = {
                **manifest_entry,
                "official_source_system": "vbpl",
                "official_source_document_id": match["source_document_id"],
                "official_source_url": match["source_url"],
            }
        updated += 1

    write_jsonl_records(
        paths.documents_manifest,
        sorted(manifest_index.values(), key=lambda item: item["canonical_id"]),
    )

    append_jsonl_record(
        paths.source_runs_manifest,
        {
            "kind": "vbpl_official_backfill_finished",
            "candidate_match_count": candidates,
            "updated_count": updated,
            "overwrite": overwrite,
        },
    )
    return {
        "reference_document_count": len(documents),
        "candidate_match_count": candidates,
        "updated_count": updated,
    }
