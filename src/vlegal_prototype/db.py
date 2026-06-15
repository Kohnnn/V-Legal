from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime

from .settings import get_settings
from .vectorless import build_document_retrieval_profile


_DOCUMENT_NUMBER_WS_PATTERN = re.compile(r"\s+")


def normalize_document_number(value: str | None) -> str:
    """Canonical, sargable form of a Vietnamese legal document number.

    Collapses whitespace, uppercases, and unifies the ``-`` separator to ``/``
    so equality/prefix lookups can use an index instead of wrapping the column
    in ``REPLACE(UPPER(COALESCE(...)))`` at query time.
    """
    if not value:
        return ""
    collapsed = _DOCUMENT_NUMBER_WS_PATTERN.sub("", value.strip())
    return collapsed.upper().replace("-", "/")


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    canonical_id TEXT,
    document_number TEXT,
    document_number_norm TEXT,
    title TEXT NOT NULL,
    url TEXT,
    legal_type TEXT,
    legal_sectors TEXT,
    issuing_authority TEXT,
    issuance_date TEXT,
    signers TEXT,
    content TEXT NOT NULL,
    plain_content TEXT NOT NULL,
    excerpt TEXT,
    year INTEGER,
    source TEXT NOT NULL,
    source_system TEXT NOT NULL DEFAULT '',
    source_document_id TEXT NOT NULL DEFAULT '',
    document_layer TEXT NOT NULL DEFAULT 'issued',
    text_source TEXT NOT NULL DEFAULT 'html',
    parse_confidence TEXT NOT NULL DEFAULT 'high',
    corpus_path TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'unknown',
    effective_date TEXT NOT NULL DEFAULT '',
    expiry_date TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_canonical_id
    ON documents(canonical_id);

CREATE INDEX IF NOT EXISTS idx_documents_document_number
    ON documents(document_number);

CREATE INDEX IF NOT EXISTS idx_documents_document_number_norm
    ON documents(document_number_norm);

CREATE INDEX IF NOT EXISTS idx_documents_legal_type
    ON documents(legal_type);

CREATE INDEX IF NOT EXISTS idx_documents_issuing_authority
    ON documents(issuing_authority);

CREATE INDEX IF NOT EXISTS idx_documents_status
    ON documents(status);

CREATE INDEX IF NOT EXISTS idx_documents_year_issuance_id
    ON documents(year DESC, issuance_date DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_documents_imported_at
    ON documents(imported_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS passages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    heading TEXT,
    text TEXT NOT NULL,
    UNIQUE(document_id, ordinal)
);

CREATE TABLE IF NOT EXISTS document_retrieval_profiles (
    document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    heading_index TEXT NOT NULL DEFAULT '',
    article_index TEXT NOT NULL DEFAULT '',
    citation_index TEXT NOT NULL DEFAULT '',
    keyword_index TEXT NOT NULL DEFAULT '',
    chunk_count INTEGER NOT NULL DEFAULT 0,
    source_hash TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_document_retrieval_profiles_source_hash
    ON document_retrieval_profiles(source_hash);

CREATE TABLE IF NOT EXISTS tracked_documents (
    document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    tracked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS taxonomy_subjects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    source_url TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_subjects (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    subject_id TEXT NOT NULL REFERENCES taxonomy_subjects(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, subject_id)
);

CREATE INDEX IF NOT EXISTS idx_document_subjects_subject_id
    ON document_subjects(subject_id);

CREATE TABLE IF NOT EXISTS document_relations (
    source_document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    target_document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    evidence_text TEXT,
    confidence TEXT NOT NULL DEFAULT 'high',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_document_id, target_document_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_document_relations_source
    ON document_relations(source_document_id, relation_type);

CREATE INDEX IF NOT EXISTS idx_document_relations_target
    ON document_relations(target_document_id, relation_type);

CREATE TABLE IF NOT EXISTS document_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    section_type TEXT NOT NULL,
    label TEXT NOT NULL,
    anchor TEXT NOT NULL,
    text TEXT NOT NULL,
    UNIQUE(document_id, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_document_sections_document_id
    ON document_sections(document_id, ordinal);

CREATE TABLE IF NOT EXISTS citation_mentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_section_id INTEGER NOT NULL REFERENCES document_sections(id) ON DELETE CASCADE,
    mention_order INTEGER NOT NULL,
    raw_reference TEXT NOT NULL,
    referenced_number TEXT,
    referenced_label TEXT,
    cue_phrase TEXT,
    mention_type TEXT NOT NULL DEFAULT 'document',
    confidence TEXT NOT NULL DEFAULT 'medium',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_citation_mentions_source_document
    ON citation_mentions(source_document_id, source_section_id);

CREATE TABLE IF NOT EXISTS citation_links (
    mention_id INTEGER NOT NULL REFERENCES citation_mentions(id) ON DELETE CASCADE,
    target_document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    target_section_id INTEGER REFERENCES document_sections(id) ON DELETE CASCADE,
    link_type TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 1.0,
    match_method TEXT NOT NULL DEFAULT 'document_number',
    PRIMARY KEY (mention_id, target_document_id, link_type)
);

CREATE INDEX IF NOT EXISTS idx_citation_links_target_document
    ON citation_links(target_document_id, link_type);

CREATE TABLE IF NOT EXISTS research_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    query TEXT NOT NULL DEFAULT '',
    topic_slug TEXT,
    legal_type TEXT,
    year INTEGER,
    issuer TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_research_views_created_at
    ON research_views(created_at DESC);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_name TEXT NOT NULL,
    dataset_revision TEXT,
    selection_mode TEXT NOT NULL DEFAULT 'full',
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    scanned_count INTEGER NOT NULL DEFAULT 0,
    imported_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingest_runs_started_at
    ON ingest_runs(started_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title,
    plain_content,
    excerpt,
    content = 'documents',
    content_rowid = 'id',
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    heading,
    text,
    content = 'passages',
    content_rowid = 'id',
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE VIRTUAL TABLE IF NOT EXISTS document_retrieval_fts USING fts5(
    heading_index,
    article_index,
    citation_index,
    keyword_index,
    content = 'document_retrieval_profiles',
    content_rowid = 'document_id',
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, plain_content, excerpt)
    VALUES (new.id, new.title, new.plain_content, new.excerpt);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, plain_content, excerpt)
    VALUES ('delete', old.id, old.title, old.plain_content, old.excerpt);
END;

CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents
WHEN old.title IS NOT new.title
    OR old.plain_content IS NOT new.plain_content
    OR old.excerpt IS NOT new.excerpt
BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, plain_content, excerpt)
    VALUES ('delete', old.id, old.title, old.plain_content, old.excerpt);
    INSERT INTO documents_fts(rowid, title, plain_content, excerpt)
    VALUES (new.id, new.title, new.plain_content, new.excerpt);
END;

CREATE TRIGGER IF NOT EXISTS passages_ai AFTER INSERT ON passages BEGIN
    INSERT INTO passages_fts(rowid, heading, text)
    VALUES (new.id, COALESCE(new.heading, ''), new.text);
END;

CREATE TRIGGER IF NOT EXISTS passages_ad AFTER DELETE ON passages BEGIN
    INSERT INTO passages_fts(passages_fts, rowid, heading, text)
    VALUES ('delete', old.id, COALESCE(old.heading, ''), old.text);
END;

CREATE TRIGGER IF NOT EXISTS passages_au AFTER UPDATE ON passages BEGIN
    INSERT INTO passages_fts(passages_fts, rowid, heading, text)
    VALUES ('delete', old.id, COALESCE(old.heading, ''), old.text);
    INSERT INTO passages_fts(rowid, heading, text)
    VALUES (new.id, COALESCE(new.heading, ''), new.text);
END;

CREATE TRIGGER IF NOT EXISTS document_retrieval_profiles_ai AFTER INSERT ON document_retrieval_profiles BEGIN
    INSERT INTO document_retrieval_fts(rowid, heading_index, article_index, citation_index, keyword_index)
    VALUES (new.document_id, new.heading_index, new.article_index, new.citation_index, new.keyword_index);
END;

CREATE TRIGGER IF NOT EXISTS document_retrieval_profiles_ad AFTER DELETE ON document_retrieval_profiles BEGIN
    INSERT INTO document_retrieval_fts(document_retrieval_fts, rowid, heading_index, article_index, citation_index, keyword_index)
    VALUES ('delete', old.document_id, old.heading_index, old.article_index, old.citation_index, old.keyword_index);
END;

CREATE TRIGGER IF NOT EXISTS document_retrieval_profiles_au AFTER UPDATE ON document_retrieval_profiles BEGIN
    INSERT INTO document_retrieval_fts(document_retrieval_fts, rowid, heading_index, article_index, citation_index, keyword_index)
    VALUES ('delete', old.document_id, old.heading_index, old.article_index, old.citation_index, old.keyword_index);
    INSERT INTO document_retrieval_fts(rowid, heading_index, article_index, citation_index, keyword_index)
    VALUES (new.document_id, new.heading_index, new.article_index, new.citation_index, new.keyword_index);
END;
"""


def get_connection() -> sqlite3.Connection:
    settings = get_settings()
    connection = sqlite3.connect(
        settings.database_path,
        check_same_thread=False,
        timeout=30.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute("PRAGMA cache_size = -20000")
    return connection


@contextmanager
def connection_context() -> sqlite3.Connection:
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


def initialize_database(connection: sqlite3.Connection) -> None:
    try:
        existing_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }
        if "documents" in existing_tables:
            _ensure_schema_migrations(connection)
        connection.executescript(SCHEMA)
        _ensure_schema_migrations(connection)
        connection.commit()
    except sqlite3.OperationalError as exc:
        if "readonly" not in str(exc).lower():
            raise

        required_tables = {
            "documents",
            "passages",
            "document_retrieval_profiles",
            "tracked_documents",
            "taxonomy_subjects",
            "document_subjects",
            "document_relations",
            "document_sections",
            "citation_mentions",
            "citation_links",
            "research_views",
            "ingest_runs",
        }
        if not required_tables.issubset(existing_tables):
            raise


def _ensure_document_columns(connection: sqlite3.Connection) -> None:
    """Add any missing ``documents`` columns. Cheap and always safe.

    ``ALTER TABLE ... ADD COLUMN`` for a nullable column is an O(1) metadata
    operation in SQLite, so this is safe to run at startup even on the full
    multi-GB corpus. Index creation is intentionally NOT done here (see
    ``_ensure_schema_migrations``) because building indexes over 150k+ rows is
    expensive and belongs in the migration script / full rebuild path.
    """
    document_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(documents)").fetchall()
    }
    required_document_columns = {
        "canonical_id": "ALTER TABLE documents ADD COLUMN canonical_id TEXT",
        "source_system": "ALTER TABLE documents ADD COLUMN source_system TEXT NOT NULL DEFAULT ''",
        "source_document_id": "ALTER TABLE documents ADD COLUMN source_document_id TEXT NOT NULL DEFAULT ''",
        "document_layer": "ALTER TABLE documents ADD COLUMN document_layer TEXT NOT NULL DEFAULT 'issued'",
        "text_source": "ALTER TABLE documents ADD COLUMN text_source TEXT NOT NULL DEFAULT 'html'",
        "parse_confidence": "ALTER TABLE documents ADD COLUMN parse_confidence TEXT NOT NULL DEFAULT 'high'",
        "corpus_path": "ALTER TABLE documents ADD COLUMN corpus_path TEXT NOT NULL DEFAULT ''",
        "document_number_norm": "ALTER TABLE documents ADD COLUMN document_number_norm TEXT",
        "status": "ALTER TABLE documents ADD COLUMN status TEXT NOT NULL DEFAULT 'unknown'",
        "effective_date": "ALTER TABLE documents ADD COLUMN effective_date TEXT NOT NULL DEFAULT ''",
        "expiry_date": "ALTER TABLE documents ADD COLUMN expiry_date TEXT NOT NULL DEFAULT ''",
    }
    for column_name, statement in required_document_columns.items():
        if column_name in document_columns:
            continue
        connection.execute(statement)


def _ensure_schema_migrations(connection: sqlite3.Connection) -> None:
    _ensure_document_columns(connection)
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_canonical_id ON documents(canonical_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_document_number_norm "
        "ON documents(document_number_norm)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_issuing_authority "
        "ON documents(issuing_authority)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_imported_at "
        "ON documents(imported_at DESC, id DESC)"
    )


def reset_database(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM passages")
    connection.execute("DELETE FROM documents")
    connection.commit()


def get_document_source_hashes(
    connection: sqlite3.Connection, document_ids: list[int]
) -> dict[int, str]:
    if not document_ids:
        return {}
    placeholders = ", ".join("?" for _ in document_ids)
    rows = connection.execute(
        f"""
        SELECT document_id, source_hash
        FROM document_retrieval_profiles
        WHERE document_id IN ({placeholders})
        """,
        document_ids,
    ).fetchall()
    return {int(row["document_id"]): row["source_hash"] for row in rows}


def start_ingest_run(
    connection: sqlite3.Connection,
    *,
    dataset_name: str,
    selection_mode: str,
    dataset_revision: str = "",
    notes: str = "",
) -> int:
    with connection:
        cursor = connection.execute(
            """
            INSERT INTO ingest_runs (dataset_name, dataset_revision, selection_mode, notes)
            VALUES (?, ?, ?, ?)
            """,
            (dataset_name, dataset_revision, selection_mode, notes or None),
        )
    return int(cursor.lastrowid)


def finish_ingest_run(
    connection: sqlite3.Connection,
    run_id: int,
    *,
    scanned_count: int,
    imported_count: int,
    skipped_count: int,
    notes: str = "",
) -> None:
    with connection:
        connection.execute(
            """
            UPDATE ingest_runs
            SET finished_at = CURRENT_TIMESTAMP,
                scanned_count = ?,
                imported_count = ?,
                skipped_count = ?,
                notes = ?
            WHERE id = ?
            """,
            (scanned_count, imported_count, skipped_count, notes or None, run_id),
        )


class InternalIdCollisionError(RuntimeError):
    """Raised when two distinct canonical IDs map to the same internal id.

    Internal ids are a 60-bit SHA256 truncation of the canonical id. A
    collision would silently overwrite a different document via the
    ``ON CONFLICT(id) DO UPDATE`` upsert, so detect it and fail loudly instead.
    """


def _guard_internal_id_collisions(
    connection: sqlite3.Connection, records: list[dict]
) -> None:
    # Within the batch: same internal id, different canonical id.
    seen: dict[int, str] = {}
    for record in records:
        internal_id = record["id"]
        canonical_id = record.get("canonical_id") or ""
        if not canonical_id:
            continue
        existing = seen.get(internal_id)
        if existing is not None and existing != canonical_id:
            raise InternalIdCollisionError(
                f"Internal id {internal_id} maps to two canonical ids within this "
                f"batch: {existing!r} and {canonical_id!r}."
            )
        seen[internal_id] = canonical_id

    # Against the database: same internal id already stored under a different
    # canonical id (i.e. not a legitimate re-import of the same document).
    candidates = {
        record["id"]: (record.get("canonical_id") or "")
        for record in records
        if record.get("canonical_id")
    }
    if not candidates:
        return
    ids = list(candidates.keys())
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        placeholders = ", ".join("?" for _ in chunk)
        rows = connection.execute(
            f"SELECT id, canonical_id FROM documents WHERE id IN ({placeholders})",
            chunk,
        ).fetchall()
        for row in rows:
            stored_canonical = row["canonical_id"] or ""
            incoming_canonical = candidates[row["id"]]
            if stored_canonical and stored_canonical != incoming_canonical:
                raise InternalIdCollisionError(
                    f"Internal id {row['id']} already stored under canonical id "
                    f"{stored_canonical!r} but incoming record uses "
                    f"{incoming_canonical!r}. Refusing to overwrite."
                )


def import_documents(
    connection: sqlite3.Connection,
    records: Iterable[dict],
    *,
    skip_unchanged: bool = False,
) -> dict[str, int]:
    records_list = list(records)
    if not records_list:
        return {"received_count": 0, "imported_count": 0, "skipped_count": 0}

    document_sql = """
    INSERT INTO documents (
        id,
        canonical_id,
        document_number,
        document_number_norm,
        title,
        url,
        legal_type,
        legal_sectors,
        issuing_authority,
        issuance_date,
        signers,
        content,
        plain_content,
        excerpt,
        year,
        source,
        source_system,
        source_document_id,
        document_layer,
        text_source,
        parse_confidence,
        corpus_path,
        status,
        effective_date,
        expiry_date
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        canonical_id = excluded.canonical_id,
        document_number = excluded.document_number,
        document_number_norm = excluded.document_number_norm,
        title = excluded.title,
        url = excluded.url,
        legal_type = excluded.legal_type,
        legal_sectors = excluded.legal_sectors,
        issuing_authority = excluded.issuing_authority,
        issuance_date = excluded.issuance_date,
        signers = excluded.signers,
        content = excluded.content,
        plain_content = excluded.plain_content,
        excerpt = excluded.excerpt,
        year = excluded.year,
        source = excluded.source,
        source_system = excluded.source_system,
        source_document_id = excluded.source_document_id,
        document_layer = excluded.document_layer,
        text_source = excluded.text_source,
        parse_confidence = excluded.parse_confidence,
        corpus_path = excluded.corpus_path,
        status = excluded.status,
        effective_date = excluded.effective_date,
        expiry_date = excluded.expiry_date,
        imported_at = CURRENT_TIMESTAMP
    """

    passage_sql = """
    INSERT INTO passages (document_id, ordinal, heading, text)
    VALUES (?, ?, ?, ?)
    """

    retrieval_sql = """
    INSERT INTO document_retrieval_profiles (
        document_id,
        heading_index,
        article_index,
        citation_index,
        keyword_index,
        chunk_count,
        source_hash
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(document_id) DO UPDATE SET
        heading_index = excluded.heading_index,
        article_index = excluded.article_index,
        citation_index = excluded.citation_index,
        keyword_index = excluded.keyword_index,
        chunk_count = excluded.chunk_count,
        source_hash = excluded.source_hash,
        updated_at = CURRENT_TIMESTAMP
    """

    profiles = {
        record["id"]: build_document_retrieval_profile(record)
        for record in records_list
    }
    records_to_import = records_list
    if skip_unchanged:
        existing_hashes = get_document_source_hashes(
            connection, [record["id"] for record in records_list]
        )
        records_to_import = [
            record
            for record in records_list
            if profiles[record["id"]]["source_hash"]
            != existing_hashes.get(record["id"])
        ]

    _guard_internal_id_collisions(connection, records_to_import)

    with connection:
        for record in records_to_import:
            profile = profiles[record["id"]]
            connection.execute(
                document_sql,
                (
                    record["id"],
                    record.get("canonical_id") or "",
                    record["document_number"],
                    normalize_document_number(record.get("document_number")),
                    record["title"],
                    record["url"],
                    record["legal_type"],
                    record["legal_sectors"],
                    record["issuing_authority"],
                    record["issuance_date"],
                    record["signers"],
                    record["content"],
                    record["plain_content"],
                    record["excerpt"],
                    record["year"],
                    record["source"],
                    record.get("source_system") or "",
                    str(record.get("source_document_id") or ""),
                    record.get("document_layer") or "issued",
                    record.get("text_source") or "html",
                    record.get("parse_confidence") or "high",
                    record.get("corpus_path") or "",
                    record.get("status") or "unknown",
                    record.get("effective_date") or "",
                    record.get("expiry_date") or "",
                ),
            )
            connection.execute(
                "DELETE FROM passages WHERE document_id = ?", (record["id"],)
            )
            connection.executemany(
                passage_sql,
                [
                    (
                        record["id"],
                        passage["ordinal"],
                        passage["heading"],
                        passage["text"],
                    )
                    for passage in record["passages"]
                ],
            )
            connection.execute(
                retrieval_sql,
                (
                    profile["document_id"],
                    profile["heading_index"],
                    profile["article_index"],
                    profile["citation_index"],
                    profile["keyword_index"],
                    profile["chunk_count"],
                    profile["source_hash"],
                ),
            )

    return {
        "received_count": len(records_list),
        "imported_count": len(records_to_import),
        "skipped_count": len(records_list) - len(records_to_import),
    }


def get_stats(connection: sqlite3.Connection) -> dict:
    max_reasonable_year = datetime.utcnow().year + 1
    document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    authority_count = connection.execute(
        "SELECT COUNT(DISTINCT issuing_authority) FROM documents WHERE COALESCE(issuing_authority, '') <> ''"
    ).fetchone()[0]
    tracked_count = connection.execute(
        "SELECT COUNT(*) FROM tracked_documents"
    ).fetchone()[0]
    taxonomy_subject_count = connection.execute(
        "SELECT COUNT(*) FROM taxonomy_subjects"
    ).fetchone()[0]
    relation_count = connection.execute(
        "SELECT COUNT(*) FROM document_relations"
    ).fetchone()[0]
    citation_link_count = connection.execute(
        "SELECT COUNT(*) FROM citation_links"
    ).fetchone()[0]
    research_view_count = connection.execute(
        "SELECT COUNT(*) FROM research_views"
    ).fetchone()[0]
    years = connection.execute(
        "SELECT MIN(year) AS min_year, MAX(year) AS max_year FROM documents WHERE year BETWEEN ? AND ?",
        (1800, max_reasonable_year),
    ).fetchone()
    last_import = connection.execute(
        "SELECT MAX(imported_at) AS imported_at FROM documents"
    ).fetchone()[0]
    return {
        "document_count": document_count,
        "authority_count": authority_count,
        "tracked_count": tracked_count,
        "taxonomy_subject_count": taxonomy_subject_count,
        "relation_count": relation_count,
        "citation_link_count": citation_link_count,
        "research_view_count": research_view_count,
        "min_year": years["min_year"],
        "max_year": years["max_year"],
        "last_imported_at": last_import,
    }


def get_archive_stats(connection: sqlite3.Connection) -> dict:
    summary_path = get_settings().corpus_root / "manifests" / "corpus_summary.json"
    if summary_path.exists():
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            return {
                "document_count": payload.get("document_count", 0),
                "min_year": payload.get("min_year"),
                "max_year": payload.get("max_year"),
                "last_imported_at": payload.get("last_imported_at"),
            }
        except Exception:
            pass

    max_reasonable_year = datetime.utcnow().year + 1
    document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    years = connection.execute(
        "SELECT MIN(year) AS min_year, MAX(year) AS max_year FROM documents WHERE year BETWEEN ? AND ?",
        (1800, max_reasonable_year),
    ).fetchone()
    last_import = connection.execute(
        "SELECT MAX(imported_at) AS imported_at FROM documents"
    ).fetchone()[0]
    return {
        "document_count": document_count,
        "min_year": years["min_year"],
        "max_year": years["max_year"],
        "last_imported_at": last_import,
    }


def get_archive_home_cache() -> dict | None:
    cache_path = get_settings().corpus_root / "manifests" / "archive_home_cache.json"
    if not cache_path.exists():
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_empty(connection: sqlite3.Connection) -> bool:
    return connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
