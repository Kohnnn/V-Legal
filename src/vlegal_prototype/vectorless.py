from __future__ import annotations

import hashlib
import json
import re
from collections import Counter

from .taxonomy import normalize_ascii


ARTICLE_PATTERN = re.compile(r"\bdieu\s+\d+[a-z]?\b", re.IGNORECASE)
DOCUMENT_NUMBER_PATTERN = re.compile(
    r"\b\d{1,4}/\d{4}/[0-9a-z][0-9a-z/-]{1,30}\b", re.IGNORECASE
)
TOKEN_PATTERN = re.compile(r"[0-9a-z]+")

STOPWORDS = {
    "ban",
    "bo",
    "cac",
    "can",
    "cho",
    "co",
    "cua",
    "da",
    "den",
    "dia",
    "dieu",
    "duoc",
    "hai",
    "khi",
    "mot",
    "nay",
    "nguoi",
    "nhung",
    "quy",
    "quyet",
    "so",
    "tai",
    "theo",
    "thi",
    "thu",
    "thuc",
    "trach",
    "tren",
    "trong",
    "tu",
    "van",
    "viec",
    "voi",
    "xac",
}


def normalize_retrieval_text(value: str | None) -> str:
    normalized = normalize_ascii(value or "")
    normalized = re.sub(r"[^0-9a-z/\s-]", " ", normalized)
    return " ".join(normalized.split())


def unique_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def build_source_hash(record: dict) -> str:
    payload = {
        "id": record["id"],
        "document_number": record.get("document_number") or "",
        "title": record.get("title") or "",
        "url": record.get("url") or "",
        "legal_type": record.get("legal_type") or "",
        "legal_sectors": record.get("legal_sectors") or "",
        "issuing_authority": record.get("issuing_authority") or "",
        "issuance_date": record.get("issuance_date") or "",
        "signers": record.get("signers") or "",
        "content": record.get("content") or "",
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def collect_keywords(record: dict, limit: int = 48) -> list[str]:
    weights = [
        (record.get("title") or "", 4),
        (record.get("document_number") or "", 3),
        (record.get("legal_type") or "", 3),
        (record.get("legal_sectors") or "", 2),
        (record.get("issuing_authority") or "", 2),
        (record.get("excerpt") or "", 1),
    ]
    weights.extend(
        (passage.get("heading") or "", 1) for passage in record.get("passages", [])
    )

    counts: Counter[str] = Counter()
    for value, weight in weights:
        for token in TOKEN_PATTERN.findall(normalize_retrieval_text(value)):
            if len(token) < 3 and not any(char.isdigit() for char in token):
                continue
            if token in STOPWORDS:
                continue
            counts[token] += weight

    return [token for token, _ in counts.most_common(limit)]


def build_document_retrieval_profile(record: dict) -> dict:
    headings = unique_in_order(
        [
            normalize_retrieval_text(passage.get("heading"))
            for passage in record.get("passages", [])
            if normalize_retrieval_text(passage.get("heading"))
            and normalize_retrieval_text(passage.get("heading")) != "mo dau"
        ]
    )
    normalized_content = normalize_retrieval_text(record.get("content"))
    article_index = unique_in_order(ARTICLE_PATTERN.findall(normalized_content))[:128]
    citation_index = unique_in_order(
        [
            item.upper().replace("-", "/")
            for item in DOCUMENT_NUMBER_PATTERN.findall(normalized_content)
        ]
    )[:128]
    keyword_index = collect_keywords(record)
    return {
        "document_id": record["id"],
        "heading_index": "\n".join(headings),
        "article_index": "\n".join(article_index),
        "citation_index": "\n".join(citation_index),
        "keyword_index": " ".join(keyword_index),
        "chunk_count": len(record.get("passages", [])),
        "source_hash": build_source_hash(record),
    }
