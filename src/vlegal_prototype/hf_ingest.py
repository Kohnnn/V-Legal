from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime

from datasets import load_dataset

from .settings import get_settings


HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.*)$")
ARTICLE_PATTERN = re.compile(r"^(Điều\s+\d+[A-Za-z0-9\-./]*)", re.IGNORECASE)
IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\([^\)]+\)")
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
MARKDOWN_DECORATION_PATTERN = re.compile(r"[`*_>{}]|\x0b")
SPACE_PATTERN = re.compile(r"[ \t]+")
SENTENCE_PATTERN = re.compile(r"(?<=[.;:!?])\s+")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = IMAGE_PATTERN.sub(" ", value)
    value = LINK_PATTERN.sub(r"\1", value)
    value = MARKDOWN_DECORATION_PATTERN.sub(" ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = SPACE_PATTERN.sub(" ", value)
    value = re.sub(r"\s+\n", "\n", value)
    value = re.sub(r"\n\s+", "\n", value)
    return value.strip()


def extract_year(issuance_date: str | None) -> int | None:
    if not issuance_date:
        return None
    try:
        return datetime.strptime(issuance_date, "%d/%m/%Y").year
    except ValueError:
        return None


def build_excerpt(plain_text: str, max_length: int = 280) -> str:
    collapsed = plain_text.replace("\n", " ")
    if len(collapsed) <= max_length:
        return collapsed
    return collapsed[: max_length - 3].rstrip() + "..."


def split_into_passages(markdown_content: str, max_chars: int = 1400) -> list[dict]:
    cleaned = normalize_text(markdown_content)
    if not cleaned:
        return []

    sections: list[tuple[str, str]] = []
    current_heading = "Mở đầu"
    current_lines: list[str] = []

    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            if current_lines and current_lines[-1] != "":
                current_lines.append("")
            continue

        heading_match = HEADING_PATTERN.match(line)
        article_match = ARTICLE_PATTERN.match(line)
        next_heading = (
            heading_match.group(1).strip()
            if heading_match
            else article_match.group(1).strip()
            if article_match
            else None
        )

        if next_heading and current_lines:
            sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = next_heading
            current_lines = [line]
            continue

        if next_heading and not current_lines:
            current_heading = next_heading
            current_lines = [line]
            continue

        current_lines.append(line)

    if current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))

    passages: list[dict] = []
    ordinal = 1

    for heading, section_text in sections:
        paragraphs = [
            paragraph.strip()
            for paragraph in section_text.split("\n\n")
            if paragraph.strip()
        ]
        if not paragraphs:
            continue

        chunk = ""
        for paragraph in paragraphs:
            candidate = f"{chunk}\n\n{paragraph}".strip() if chunk else paragraph
            if len(candidate) <= max_chars:
                chunk = candidate
                continue

            if chunk:
                passages.append({"ordinal": ordinal, "heading": heading, "text": chunk})
                ordinal += 1

            if len(paragraph) <= max_chars:
                chunk = paragraph
                continue

            sentence_chunk = ""
            for sentence in SENTENCE_PATTERN.split(paragraph):
                sentence = sentence.strip()
                if not sentence:
                    continue
                sentence_candidate = (
                    f"{sentence_chunk} {sentence}".strip()
                    if sentence_chunk
                    else sentence
                )
                if len(sentence_candidate) <= max_chars:
                    sentence_chunk = sentence_candidate
                    continue

                if sentence_chunk:
                    passages.append(
                        {"ordinal": ordinal, "heading": heading, "text": sentence_chunk}
                    )
                    ordinal += 1
                sentence_chunk = sentence

            if sentence_chunk:
                passages.append(
                    {"ordinal": ordinal, "heading": heading, "text": sentence_chunk}
                )
                ordinal += 1
            chunk = ""

        if chunk:
            passages.append({"ordinal": ordinal, "heading": heading, "text": chunk})
            ordinal += 1

    return passages


def prepare_record(metadata: dict, content: dict) -> dict:
    plain_content = normalize_text(content.get("content", ""))
    return {
        "id": metadata["id"],
        "document_number": metadata.get("document_number") or "",
        "title": metadata.get("title") or f"Document {metadata['id']}",
        "url": metadata.get("url") or "",
        "legal_type": metadata.get("legal_type") or "",
        "legal_sectors": metadata.get("legal_sectors") or "",
        "issuing_authority": metadata.get("issuing_authority") or "",
        "issuance_date": metadata.get("issuance_date") or "",
        "signers": metadata.get("signers") or "",
        "content": content.get("content") or "",
        "plain_content": plain_content,
        "excerpt": build_excerpt(plain_content),
        "year": extract_year(metadata.get("issuance_date")),
        "source": metadata.get("url") or get_settings().dataset_name,
        "passages": split_into_passages(content.get("content") or ""),
    }


def stream_hf_records(limit: int | None = None, skip: int = 0) -> Iterable[dict]:
    settings = get_settings()
    metadata_stream = load_dataset(
        settings.dataset_name,
        "metadata",
        split="data",
        streaming=True,
    )
    content_stream = load_dataset(
        settings.dataset_name,
        "content",
        split="data",
        streaming=True,
    )

    if skip:
        metadata_stream = metadata_stream.skip(skip)
        content_stream = content_stream.skip(skip)

    for index, (metadata, content) in enumerate(
        zip(metadata_stream, content_stream), start=1
    ):
        if metadata["id"] != content["id"]:
            raise RuntimeError(
                f"Dataset stream mismatch: metadata id {metadata['id']} != content id {content['id']}"
            )
        yield prepare_record(metadata, content)
        if limit is not None and index >= limit:
            break
