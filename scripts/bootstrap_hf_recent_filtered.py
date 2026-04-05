from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path

from vlegal_prototype.citations import rebuild_citation_index
from vlegal_prototype.db import get_connection, import_documents, initialize_database
from vlegal_prototype.hf_ingest import (
    ensure_hf_content_cache,
    iter_hf_parquet_batches,
    load_content_batch,
    normalize_issuance_date,
    prepare_parquet_record,
)
from vlegal_prototype.relations import rebuild_relationship_graph
from vlegal_prototype.settings import get_settings
from vlegal_prototype.taxonomy import bootstrap_taxonomy


ECONOMY_KEYWORDS = (
    "kinh te",
    "kinh doanh",
    "tai chinh",
    "ngan hang",
    "chung khoan",
    "bao hiem",
    "thue",
    "phi",
    "le phi",
    "doanh nghiep",
    "dau tu",
    "dau thau",
    "thuong mai",
    "xuat khau",
    "nhap khau",
    "hai quan",
    "gia ca",
    "gia thi truong",
    "ke toan",
    "kiem toan",
    "tien te",
    "ngoai hoi",
    "thi truong",
    "cong nghiep",
    "khu cong nghiep",
    "cum cong nghiep",
    "nong nghiep",
    "lam nghiep",
    "ngu nghiep",
    "thuy san",
    "chan nuoi",
    "trong trot",
    "xay dung",
    "bat dong san",
    "nang luong",
    "dien luc",
    "dau khi",
    "khoang san",
    "giao thong",
    "van tai",
    "hang hai",
    "hang khong",
    "buu chinh",
    "vien thong",
    "cong nghe thong tin",
    "du lich",
    "dich vu",
    "lao dong",
    "viec lam",
    "tien luong",
)

METADATA_COLUMNS = [
    "id",
    "title",
    "ngay_ban_hanh",
    "so_ky_hieu",
    "loai_van_ban",
    "co_quan_ban_hanh",
    "nganh",
    "linh_vuc",
    "nguon_thu_thap",
    "chuc_danh",
    "nguoi_ky",
]


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Import newer non-economy HF records into local SQLite."
    )
    parser.add_argument("--target-total", type=int, required=True)
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument(
        "--selection-path",
        type=Path,
        default=settings.database_path.parent / "hf_recent_non_economy_selection.json",
    )
    parser.add_argument("--rebuild-selection", action="store_true")
    parser.add_argument("--skip-postprocess", action="store_true")
    return parser.parse_args()


def normalize_ascii(value: str | None) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    normalized = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    normalized = normalized.replace("đ", "d").replace("Đ", "D")
    normalized = re.sub(r"[^0-9A-Za-z\s/.-]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip().lower()


def is_economy_related(metadata: dict) -> bool:
    haystack = normalize_ascii(
        " | ".join(
            str(metadata.get(key) or "")
            for key in (
                "title",
                "loai_van_ban",
                "co_quan_ban_hanh",
                "nganh",
                "linh_vuc",
            )
        )
    )
    return any(keyword in haystack for keyword in ECONOMY_KEYWORDS)


def get_document_count(connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]


def get_existing_ids(connection) -> set[int]:
    return {
        int(row[0]) for row in connection.execute("SELECT id FROM documents").fetchall()
    }


def get_cached_content_ids() -> set[int]:
    cache_path = ensure_hf_content_cache()
    content_connection = sqlite3.connect(cache_path)
    try:
        return {
            int(row[0])
            for row in content_connection.execute(
                "SELECT id FROM content_cache"
            ).fetchall()
        }
    finally:
        content_connection.close()


def build_sort_key(metadata: dict) -> tuple[int, str, int]:
    issuance_date, year = normalize_issuance_date(
        metadata.get("ngay_ban_hanh"),
        metadata.get("so_ky_hieu"),
        metadata.get("title"),
    )
    if issuance_date:
        try:
            sortable_date = datetime.strptime(issuance_date, "%d/%m/%Y").strftime(
                "%Y%m%d"
            )
        except ValueError:
            sortable_date = f"{year or 0:04d}0000"
    else:
        sortable_date = f"{year or 0:04d}0000"
    return (year or 0, sortable_date, int(metadata["id"]))


def load_selection(path: Path) -> list[int]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [int(item) for item in payload.get("document_ids", [])]


def save_selection(path: Path, document_ids: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"document_ids": document_ids}, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def build_selection(connection, needed_count: int) -> list[int]:
    existing_ids = get_existing_ids(connection)
    cached_content_ids = get_cached_content_ids()
    candidates: list[tuple[tuple[int, str, int], int]] = []
    skipped_economy = 0
    skipped_missing_content = 0

    for batch in iter_hf_parquet_batches(
        "data/metadata.parquet",
        columns=METADATA_COLUMNS,
        batch_size=2048,
    ):
        for metadata in batch:
            document_id = int(metadata["id"])
            if document_id in existing_ids:
                continue
            if document_id not in cached_content_ids:
                skipped_missing_content += 1
                continue
            if is_economy_related(metadata):
                skipped_economy += 1
                continue
            candidates.append((build_sort_key(metadata), document_id))

    candidates.sort(key=lambda item: item[0], reverse=True)
    selected_ids = [document_id for _, document_id in candidates[:needed_count]]
    print(
        f"Selected {len(selected_ids)} non-economy documents from metadata scan. "
        f"Skipped {skipped_economy} economy-related candidates and {skipped_missing_content} without cached content."
    )
    return selected_ids


def fetch_metadata_lookup(document_ids: list[int]) -> dict[int, dict]:
    target_ids = set(document_ids)
    metadata_lookup: dict[int, dict] = {}
    for batch in iter_hf_parquet_batches(
        "data/metadata.parquet",
        columns=METADATA_COLUMNS,
        batch_size=2048,
    ):
        for metadata in batch:
            document_id = int(metadata["id"])
            if document_id not in target_ids:
                continue
            metadata_lookup[document_id] = metadata
        if len(metadata_lookup) >= len(target_ids):
            break
    return metadata_lookup


def import_selected_records(
    connection,
    document_ids: list[int],
    *,
    chunk_size: int,
    batch_size: int,
) -> int:
    if not document_ids:
        return 0

    metadata_lookup = fetch_metadata_lookup(document_ids)
    cache_path = ensure_hf_content_cache()
    content_connection = sqlite3.connect(cache_path)
    imported = 0

    try:
        for start in range(0, len(document_ids), chunk_size):
            chunk_ids = document_ids[start : start + chunk_size]
            print(
                f"Starting filtered chunk {start // chunk_size + 1} with {len(chunk_ids)} documents..."
            )
            content_lookup = load_content_batch(content_connection, chunk_ids)
            batch: list[dict] = []
            chunk_imported = 0
            for document_id in chunk_ids:
                metadata = metadata_lookup.get(document_id)
                content_html = content_lookup.get(document_id)
                if not metadata or not content_html:
                    continue
                batch.append(
                    prepare_parquet_record(
                        metadata,
                        {"id": document_id, "content_html": content_html},
                    )
                )
                if len(batch) >= batch_size:
                    import_documents(connection, batch)
                    imported += len(batch)
                    chunk_imported += len(batch)
                    print(
                        f"  imported {chunk_imported}/{len(chunk_ids)} in current filtered chunk..."
                    )
                    batch.clear()

            if batch:
                import_documents(connection, batch)
                imported += len(batch)
                chunk_imported += len(batch)

            print(
                f"Filtered chunk complete. Imported {chunk_imported}. Total imported this run {imported}."
            )
    finally:
        content_connection.close()

    return imported


def main() -> None:
    args = parse_args()
    connection = get_connection()
    initialize_database(connection)

    current_count = get_document_count(connection)
    needed_count = max(args.target_total - current_count, 0)

    print(f"Dataset: {get_settings().dataset_name}")
    print(f"Current local document count: {current_count}")
    print(f"Target document count: {args.target_total}")

    if needed_count <= 0:
        print("Target already reached.")
        return

    selected_ids = [] if args.rebuild_selection else load_selection(args.selection_path)
    if len(selected_ids) < needed_count:
        print("Building newest-first non-economy selection...")
        selected_ids = build_selection(connection, needed_count)
        save_selection(args.selection_path, selected_ids)
    else:
        selected_ids = selected_ids[:needed_count]
        print(f"Loaded cached selection with {len(selected_ids)} document ids.")

    imported = import_selected_records(
        connection,
        selected_ids[:needed_count],
        chunk_size=args.chunk_size,
        batch_size=args.batch_size,
    )
    print(f"Imported {imported} new filtered documents.")

    if not args.skip_postprocess:
        print("Refreshing taxonomy, relations, and citations...")
        bootstrap_taxonomy(connection, prefer_live=False)
        relation_count = rebuild_relationship_graph(connection)
        citation_count = rebuild_citation_index(connection)
        print(f"Built {relation_count} relations and {citation_count} citation links.")

    connection.close()


if __name__ == "__main__":
    main()
