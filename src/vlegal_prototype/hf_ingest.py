from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from html import unescape
from pathlib import Path

from datasets import load_dataset
from huggingface_hub import HfApi, hf_hub_download
import pyarrow.parquet as pq

from .settings import get_settings


HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.*)$")
ARTICLE_PATTERN = re.compile(r"^(Điều\s+\d+[A-Za-z0-9\-./]*)", re.IGNORECASE)
IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\([^\)]+\)")
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
MARKDOWN_DECORATION_PATTERN = re.compile(r"[`*_>{}]|\x0b")
SPACE_PATTERN = re.compile(r"[ \t]+")
SENTENCE_PATTERN = re.compile(r"(?<=[.;:!?])\s+")
HTML_BLOCK_CLOSE_PATTERN = re.compile(
    r"(?i)</(?:p|div|tr|td|table|dir|center|li|ul|ol|blockquote|h[1-6])>"
)
HTML_BREAK_PATTERN = re.compile(r"(?i)<br\s*/?>")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
MULTILINE_BREAK_PATTERN = re.compile(r"\n{3,}")
YEAR_HINT_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
MIN_REASONABLE_YEAR = 1800


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


def normalize_html_content(value: str | None) -> str:
    if not value:
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = HTML_BREAK_PATTERN.sub("\n", value)
    value = HTML_BLOCK_CLOSE_PATTERN.sub("\n", value)
    value = HTML_TAG_PATTERN.sub(" ", value)
    value = unescape(value)
    value = value.replace("\xa0", " ")
    value = MULTILINE_BREAK_PATTERN.sub("\n\n", value)
    return normalize_text(value)


def extract_year(issuance_date: str | None) -> int | None:
    if not issuance_date:
        return None
    try:
        return datetime.strptime(issuance_date, "%d/%m/%Y").year
    except ValueError:
        return None


def get_max_reasonable_year() -> int:
    return datetime.utcnow().year + 1


def extract_year_hint(*values: str | None) -> int | None:
    max_year = get_max_reasonable_year()
    for value in values:
        text = value or ""
        for match in YEAR_HINT_PATTERN.finditer(text):
            year = int(match.group(0))
            if MIN_REASONABLE_YEAR <= year <= max_year:
                return year
    return None


def normalize_issuance_date(
    issuance_date: str | None, *year_hints: str | None
) -> tuple[str, int | None]:
    raw = (issuance_date or "").strip()
    if not raw:
        return "", None

    try:
        parsed = datetime.strptime(raw, "%d/%m/%Y")
    except ValueError:
        return raw, None

    year = parsed.year
    max_year = get_max_reasonable_year()
    if MIN_REASONABLE_YEAR <= year <= max_year:
        return raw, year

    hint_year = extract_year_hint(*year_hints)
    if hint_year is not None:
        normalized = parsed.replace(year=hint_year).strftime("%d/%m/%Y")
        return normalized, hint_year

    if year >= 3000 and MIN_REASONABLE_YEAR <= year - 1000 <= max_year:
        normalized = parsed.replace(year=year - 1000).strftime("%d/%m/%Y")
        return normalized, year - 1000

    return raw, None


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
    issuance_date, year = normalize_issuance_date(
        metadata.get("issuance_date"),
        metadata.get("document_number"),
        metadata.get("title"),
    )
    return {
        "id": metadata["id"],
        "document_number": metadata.get("document_number") or "",
        "title": metadata.get("title") or f"Document {metadata['id']}",
        "url": metadata.get("url") or "",
        "legal_type": metadata.get("legal_type") or "",
        "legal_sectors": metadata.get("legal_sectors") or "",
        "issuing_authority": metadata.get("issuing_authority") or "",
        "issuance_date": issuance_date,
        "signers": metadata.get("signers") or "",
        "content": content.get("content") or "",
        "plain_content": plain_content,
        "excerpt": build_excerpt(plain_content),
        "year": year,
        "source": metadata.get("url") or get_settings().dataset_name,
        "passages": split_into_passages(content.get("content") or ""),
    }


def prepare_parquet_record(metadata: dict, content: dict) -> dict:
    raw_content = normalize_html_content(content.get("content_html", ""))
    plain_content = normalize_text(raw_content)
    legal_sectors = " | ".join(
        value.strip()
        for value in [metadata.get("nganh"), metadata.get("linh_vuc")]
        if value and str(value).strip()
    )
    signers = " | ".join(
        value.strip()
        for value in [metadata.get("chuc_danh"), metadata.get("nguoi_ky")]
        if value and str(value).strip()
    )
    issuance_date, year = normalize_issuance_date(
        metadata.get("ngay_ban_hanh"),
        metadata.get("so_ky_hieu"),
        metadata.get("title"),
    )
    return {
        "id": int(metadata["id"]),
        "document_number": metadata.get("so_ky_hieu") or "",
        "title": metadata.get("title") or f"Document {metadata['id']}",
        "url": "",
        "legal_type": metadata.get("loai_van_ban") or "",
        "legal_sectors": legal_sectors,
        "issuing_authority": metadata.get("co_quan_ban_hanh") or "",
        "issuance_date": issuance_date,
        "signers": signers,
        "content": raw_content,
        "plain_content": plain_content,
        "excerpt": build_excerpt(plain_content),
        "year": year,
        "source": metadata.get("nguon_thu_thap") or get_settings().dataset_name,
        "passages": split_into_passages(raw_content),
    }


def iter_hf_parquet_batches(
    filename: str,
    *,
    columns: list[str] | None = None,
    skip: int = 0,
    limit: int | None = None,
    batch_size: int = 128,
) -> Iterable[list[dict]]:
    settings = get_settings()
    path = hf_hub_download(
        repo_id=settings.dataset_name,
        filename=filename,
        repo_type="dataset",
        cache_dir=str(get_hf_cache_dir()),
    )
    parquet_file = pq.ParquetFile(path)
    seen = 0
    yielded = 0
    for batch in parquet_file.iter_batches(batch_size=batch_size, columns=columns):
        output_batch: list[dict] = []
        for row in batch.to_pylist():
            if seen < skip:
                seen += 1
                continue
            if limit is not None and yielded >= limit:
                break
            output_batch.append(row)
            seen += 1
            yielded += 1
        if output_batch:
            yield output_batch
        if limit is not None and yielded >= limit:
            return


def get_hf_content_cache_path() -> Path:
    return get_settings().database_path.parent / "hf_content_cache.sqlite"


def get_hf_cache_dir() -> Path:
    cache_dir = get_settings().database_path.parent / "hf_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_dataset_revision() -> str:
    settings = get_settings()
    try:
        api = HfApi(token=settings.hf_token or None)
        info = api.dataset_info(repo_id=settings.dataset_name)
    except Exception:
        return ""
    return info.sha or ""


def ensure_hf_content_cache() -> Path:
    cache_path = get_hf_content_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(cache_path)
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS content_cache (id INTEGER PRIMARY KEY, content_html TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS cache_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        ready_row = connection.execute(
            "SELECT value FROM cache_meta WHERE key = 'ready'"
        ).fetchone()
        if ready_row and ready_row[0] == "1":
            return cache_path

        connection.execute("DELETE FROM content_cache")
        connection.execute("DELETE FROM cache_meta")
        content_path = hf_hub_download(
            repo_id=get_settings().dataset_name,
            filename="data/content.parquet",
            repo_type="dataset",
            cache_dir=str(get_hf_cache_dir()),
        )
        parquet_file = pq.ParquetFile(content_path)
        with connection:
            for batch in parquet_file.iter_batches(
                batch_size=64, columns=["id", "content_html"]
            ):
                rows = [
                    (int(row["id"]), row.get("content_html") or "")
                    for row in batch.to_pylist()
                    if row.get("id") is not None and row.get("content_html")
                ]
                connection.executemany(
                    """
                    INSERT INTO content_cache (id, content_html)
                    VALUES (?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        content_html = CASE
                            WHEN LENGTH(excluded.content_html) > LENGTH(content_cache.content_html)
                                THEN excluded.content_html
                            ELSE content_cache.content_html
                        END
                    """,
                    rows,
                )
            connection.execute(
                "INSERT INTO cache_meta (key, value) VALUES ('ready', '1')"
            )
        return cache_path
    finally:
        connection.close()


def load_content_batch(
    connection: sqlite3.Connection, document_ids: list[int]
) -> dict[int, str]:
    placeholders = ", ".join("?" for _ in document_ids)
    rows = connection.execute(
        f"SELECT id, content_html FROM content_cache WHERE id IN ({placeholders})",
        document_ids,
    ).fetchall()
    return {int(row[0]): row[1] for row in rows}


def stream_hf_parquet_records(
    limit: int | None = None, skip: int = 0
) -> Iterable[dict]:
    cache_path = ensure_hf_content_cache()
    content_connection = sqlite3.connect(cache_path)
    yielded = 0
    skipped = 0
    try:
        for metadata_batch in iter_hf_parquet_batches(
            "data/metadata.parquet",
            batch_size=128,
        ):
            document_ids = [int(item["id"]) for item in metadata_batch]
            content_lookup = load_content_batch(content_connection, document_ids)
            for metadata in metadata_batch:
                document_id = int(metadata["id"])
                content_html = content_lookup.get(document_id)
                if not content_html:
                    continue
                if skipped < skip:
                    skipped += 1
                    continue
                if limit is not None and yielded >= limit:
                    return
                yield prepare_parquet_record(
                    metadata,
                    {"id": document_id, "content_html": content_html},
                )
                yielded += 1
    finally:
        content_connection.close()


def stream_hf_records(limit: int | None = None, skip: int = 0) -> Iterable[dict]:
    settings = get_settings()
    if settings.dataset_name == "th1nhng0/vietnamese-legal-documents":
        yield from stream_hf_parquet_records(limit=limit, skip=skip)
        return

    dataset_kwargs = {
        "split": "data",
        "streaming": True,
        "cache_dir": str(get_hf_cache_dir()),
    }
    if settings.hf_token:
        dataset_kwargs["token"] = settings.hf_token

    metadata_stream = load_dataset(
        settings.dataset_name,
        "metadata",
        **dataset_kwargs,
    )
    content_stream = load_dataset(
        settings.dataset_name,
        "content",
        **dataset_kwargs,
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
