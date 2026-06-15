"""Backfill validity columns onto an existing V-Legal SQLite database.

Additive and idempotent. It:

1. adds ``status`` / ``effective_date`` / ``expiry_date`` columns if missing,
2. backfills them from each document's canonical markdown frontmatter
   (the importer already maps these fields; this catches rows imported before
   the columns existed),
3. creates ``idx_documents_status`` and runs ``ANALYZE``.

Operates ONLY on ``VLEGAL_DATABASE_PATH`` (default: the workspace corpus DB).
It never touches deploy/OCI configuration.

IMPORTANT: stop the local dev server first so a concurrent reader does not block
WAL checkpoints on the multi-GB database. The backfill drops the heavy
``documents_au`` FTS trigger for its duration (the validity columns are not part
of any FTS index) and recreates the guarded version afterwards.

Usage:
    uv run python scripts/migrate_add_validity_columns.py
    uv run python scripts/migrate_add_validity_columns.py --dry-run
"""

from __future__ import annotations

import argparse
import sqlite3
import time

from vlegal_prototype.corpus import get_corpus_paths, split_frontmatter
from vlegal_prototype.settings import get_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill status/effective_date/expiry_date on the workspace DB."
    )
    parser.add_argument("--batch-size", type=int, default=10000)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    return any(
        row[1] == column
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    )


def _read_frontmatter_validity(corpus_path: str) -> tuple[str, str, str] | None:
    """Return (status, effective_date, expiry_date) from a corpus markdown file."""
    if not corpus_path:
        return None
    root = get_corpus_paths().root
    file_path = root / corpus_path
    if not file_path.exists():
        return None
    try:
        text = file_path.read_text(encoding="utf-8")
        metadata, _ = split_frontmatter(text)
    except Exception:
        return None
    return (
        str(metadata.get("status") or "unknown"),
        str(metadata.get("effective_date") or ""),
        str(metadata.get("expiry_date") or ""),
    )


def main() -> None:
    args = parse_args()
    settings = get_settings()
    db_path = settings.database_path
    print(f"Target database: {db_path}")

    connection = sqlite3.connect(db_path, timeout=60.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 60000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")

    try:
        for column, ddl in (
            ("status", "ALTER TABLE documents ADD COLUMN status TEXT NOT NULL DEFAULT 'unknown'"),
            ("effective_date", "ALTER TABLE documents ADD COLUMN effective_date TEXT NOT NULL DEFAULT ''"),
            ("expiry_date", "ALTER TABLE documents ADD COLUMN expiry_date TEXT NOT NULL DEFAULT ''"),
        ):
            if not _column_exists(connection, "documents", column):
                if args.dry_run:
                    print(f"[dry-run] would ADD COLUMN {column}")
                else:
                    connection.execute(ddl)
                    connection.commit()
                    print(f"Added column {column}")

        rows = connection.execute(
            "SELECT COUNT(*) FROM documents WHERE COALESCE(corpus_path, '') != ''"
        ).fetchone()[0]
        print(f"Documents with a corpus_path: {rows:,}")

        if args.dry_run:
            print("[dry-run] would backfill from frontmatter, index, and ANALYZE.")
            return

        print("Dropping legacy documents_au FTS trigger during backfill ...")
        connection.execute("DROP TRIGGER IF EXISTS documents_au")
        connection.commit()

        updated = 0
        scanned = 0
        started = time.time()
        cursor = connection.execute(
            "SELECT id, corpus_path FROM documents WHERE COALESCE(corpus_path, '') != ''"
        )
        batch: list[tuple] = []
        for row in cursor:
            scanned += 1
            validity = _read_frontmatter_validity(row["corpus_path"])
            if not validity:
                continue
            status, effective_date, expiry_date = validity
            batch.append((status, effective_date, expiry_date, row["id"]))
            if len(batch) >= args.batch_size:
                connection.executemany(
                    "UPDATE documents SET status = ?, effective_date = ?, expiry_date = ? WHERE id = ?",
                    batch,
                )
                connection.commit()
                connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
                updated += len(batch)
                batch = []
                print(f"  scanned {scanned:,}; updated {updated:,}", flush=True)
        if batch:
            connection.executemany(
                "UPDATE documents SET status = ?, effective_date = ?, expiry_date = ? WHERE id = ?",
                batch,
            )
            connection.commit()
            updated += len(batch)

        print("Recreating guarded documents_au FTS trigger ...")
        connection.execute(
            """
            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents
            WHEN old.title IS NOT new.title
                OR old.plain_content IS NOT new.plain_content
                OR old.excerpt IS NOT new.excerpt
            BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, title, plain_content, excerpt)
                VALUES ('delete', old.id, old.title, old.plain_content, old.excerpt);
                INSERT INTO documents_fts(rowid, title, plain_content, excerpt)
                VALUES (new.id, new.title, new.plain_content, new.excerpt);
            END
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)"
        )
        connection.commit()

        print("Running ANALYZE ...")
        connection.execute("ANALYZE")
        connection.commit()

        elapsed = time.time() - started
        print(f"Done. Scanned {scanned:,}, updated {updated:,} in {elapsed:.1f}s.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
