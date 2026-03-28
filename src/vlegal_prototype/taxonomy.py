from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from html import unescape
from pathlib import Path
from urllib.request import urlopen

from .settings import BASE_DIR, get_settings


SEED_PATH = BASE_DIR / "src" / "vlegal_prototype" / "seeds" / "phapdien_subjects.json"
OPTION_PATTERN = re.compile(r'<option value="([^"]+)">([^<]+)</option>')
TOKEN_PATTERN = re.compile(r"[0-9a-z]+")


def normalize_ascii(value: str) -> str:
    value = value.replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return value.lower().strip()


def slugify(value: str) -> str:
    normalized = normalize_ascii(value)
    normalized = re.sub(r"[^0-9a-z\s-]", " ", normalized)
    normalized = re.sub(r"\s+", "-", normalized).strip("-")
    return normalized


def tokenize(value: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(normalize_ascii(value)))


def load_seed_subjects() -> list[dict]:
    subjects = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return [
        {
            "id": subject["id"],
            "name": subject["name"],
            "slug": slugify(subject["name"]),
            "source": "phapdien-seed",
            "source_url": get_settings().phapdien_main_url,
        }
        for subject in subjects
    ]


def fetch_live_subjects(timeout: int = 20) -> list[dict]:
    settings = get_settings()
    with urlopen(settings.phapdien_main_url, timeout=timeout) as response:
        html = response.read().decode("utf-8", errors="ignore")

    options = OPTION_PATTERN.findall(html)
    subjects = []
    for subject_id, name in options:
        if subject_id == "-1":
            continue
        clean_name = unescape(name).strip()
        subjects.append(
            {
                "id": subject_id,
                "name": clean_name,
                "slug": slugify(clean_name),
                "source": "phapdien-live",
                "source_url": settings.phapdien_main_url,
            }
        )
    if not subjects:
        raise RuntimeError("Could not parse Phap dien subjects from live HTML")
    return subjects


def get_subject_records(prefer_live: bool = True) -> list[dict]:
    if prefer_live:
        try:
            return fetch_live_subjects()
        except Exception:
            return load_seed_subjects()
    return load_seed_subjects()


def upsert_subjects(connection: sqlite3.Connection, subjects: list[dict]) -> None:
    sql = """
    INSERT INTO taxonomy_subjects (id, name, slug, source, source_url)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        name = excluded.name,
        slug = excluded.slug,
        source = excluded.source,
        source_url = excluded.source_url,
        imported_at = CURRENT_TIMESTAMP
    """
    with connection:
        connection.executemany(
            sql,
            [
                (
                    subject["id"],
                    subject["name"],
                    subject["slug"],
                    subject["source"],
                    subject["source_url"],
                )
                for subject in subjects
            ],
        )


def classify_subject_ids(legal_sectors: str, subjects: list[dict]) -> list[str]:
    if not legal_sectors:
        return []
    sector_tokens = tokenize(legal_sectors)
    matched: list[str] = []
    for subject in subjects:
        subject_tokens = tokenize(subject["name"])
        if not subject_tokens:
            continue
        overlap = sector_tokens & subject_tokens
        required = 1 if len(subject_tokens) == 1 else 2
        if len(overlap) >= required:
            matched.append(subject["id"])
    return matched


def rebuild_document_subject_links(
    connection: sqlite3.Connection, subjects: list[dict]
) -> None:
    documents = connection.execute(
        "SELECT id, legal_sectors FROM documents WHERE COALESCE(legal_sectors, '') <> ''"
    ).fetchall()

    link_rows: list[tuple[int, str]] = []
    for document in documents:
        for subject_id in classify_subject_ids(document["legal_sectors"], subjects):
            link_rows.append((document["id"], subject_id))

    with connection:
        connection.execute("DELETE FROM document_subjects")
        connection.executemany(
            "INSERT OR IGNORE INTO document_subjects (document_id, subject_id) VALUES (?, ?)",
            link_rows,
        )


def bootstrap_taxonomy(
    connection: sqlite3.Connection, prefer_live: bool = True
) -> list[dict]:
    subjects = get_subject_records(prefer_live=prefer_live)
    upsert_subjects(connection, subjects)
    rebuild_document_subject_links(connection, subjects)
    return subjects


def get_taxonomy_subjects(
    connection: sqlite3.Connection, limit: int | None = None
) -> list[dict]:
    sql = """
    SELECT s.id, s.name, s.slug, s.source, s.source_url, COUNT(ds.document_id) AS document_count
    FROM taxonomy_subjects s
    LEFT JOIN document_subjects ds ON ds.subject_id = s.id
    GROUP BY s.id, s.name, s.slug, s.source, s.source_url
    ORDER BY s.name ASC
    """
    if limit is not None:
        sql += " LIMIT ?"
        rows = connection.execute(sql, (limit,)).fetchall()
    else:
        rows = connection.execute(sql).fetchall()
    return [dict(row) for row in rows]


def get_taxonomy_subject_by_slug(
    connection: sqlite3.Connection, slug: str
) -> dict | None:
    row = connection.execute(
        "SELECT id, name, slug, source, source_url FROM taxonomy_subjects WHERE slug = ?",
        (slug,),
    ).fetchone()
    return dict(row) if row else None


def get_document_subjects(
    connection: sqlite3.Connection, document_id: int
) -> list[dict]:
    rows = connection.execute(
        """
        SELECT s.id, s.name, s.slug
        FROM document_subjects ds
        JOIN taxonomy_subjects s ON s.id = ds.subject_id
        WHERE ds.document_id = ?
        ORDER BY s.name ASC
        """,
        (document_id,),
    ).fetchall()
    return [dict(row) for row in rows]
