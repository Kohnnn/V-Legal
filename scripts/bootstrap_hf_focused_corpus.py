from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from vlegal_prototype.citations import rebuild_citation_index
from vlegal_prototype.db import (
    get_connection,
    import_documents,
    initialize_database,
    reset_database,
)
from vlegal_prototype.hf_ingest import (
    ensure_hf_content_cache,
    iter_hf_parquet_batches,
    load_content_batch,
    normalize_issuance_date,
    prepare_parquet_record,
)
from vlegal_prototype.relations import rebuild_relationship_graph
from vlegal_prototype.settings import get_settings
from vlegal_prototype.taxonomy import bootstrap_taxonomy, normalize_ascii


PRIMARY_ISSUER_KEYWORDS = (
    "bo tai chinh",
    "ngan hang nha nuoc",
    "uy ban chung khoan",
    "bo ke hoach va dau tu",
    "bo cong thuong",
    "bo xay dung",
    "bo tai nguyen va moi truong",
    "bo y te",
    "bo thong tin va truyen thong",
    "bo giao thong van tai",
    "bo nong nghiep va phat trien nong thon",
)

CONDITIONAL_ISSUER_KEYWORDS = (
    "chinh phu",
    "thu tuong chinh phu",
    "quoc hoi",
    "chu tich nuoc",
    "uy ban nhan dan",
    "ubnd",
    "hoi dong nhan dan",
    "hdnd",
)

HEAVILY_FILTERED_ISSUER_KEYWORDS = (
    "bo cong an",
    "bo giao duc va dao tao",
    "bo noi vu",
    "bo quoc phong",
    "bo tu phap",
)

EXCLUDED_SECTOR_KEYWORDS = (
    "noi vu",
    "bo may hanh chinh",
    "chinh quyen dia phuong",
    "can bo cong chuc vien chuc",
    "to chuc bien che",
    "thi dua khen thuong",
    "bao tro xa hoi",
    "nguoi co cong",
    "tre em",
    "binh dang gioi",
    "phong chong te nan",
    "an sinh xa hoi",
    "tu phap",
    "ho tich",
    "quoc tich",
    "ly lich tu phap",
    "tro giup phap ly",
    "tai chinh hanh chinh su nghiep",
    "tai chinh nha nuoc",
)

FOCUS_KEYWORDS = (
    "doanh nghiep",
    "co dong",
    "co phan",
    "trach nhiem huu han",
    "sap nhap",
    "hop nhat",
    "mua lai",
    "chuyen doi doanh nghiep",
    "quan tri cong ty",
    "chung khoan",
    "co phieu",
    "trai phieu",
    "niem yet",
    "cong ty dai chung",
    "ngan hang",
    "tin dung",
    "lai suat",
    "ngoai hoi",
    "bao hiem",
    "tai chinh",
    "dau tu",
    "dau thau",
    "thuong mai",
    "xuat khau",
    "nhap khau",
    "hai quan",
    "thue",
    "le phi",
    "ke toan",
    "kiem toan",
    "bat dong san",
    "nha o",
    "xay dung",
    "dat dai",
    "quyen su dung dat",
    "khu cong nghiep",
    "cum cong nghiep",
    "khu kinh te",
    "dien luc",
    "nang luong",
    "dau khi",
    "xang dau",
    "khoang san",
    "vien thong",
    "cong nghe thong tin",
    "internet",
    "du lieu",
    "duoc",
    "duoc pham",
    "gia thuoc",
    "kham chua benh",
    "giao thong",
    "van tai",
    "hang hai",
    "hang khong",
    "cang bien",
    "logistics",
    "nong nghiep",
    "lam nghiep",
    "thuy san",
    "chan nuoi",
    "trong trot",
    "phan bon",
    "bao ve thuc vat",
    "lao dong",
    "viec lam",
    "tien luong",
    "bao hiem xa hoi",
)

FOCUS_SECTOR_KEYWORDS = (
    "tai chinh",
    "ngan hang",
    "ke hoach va dau tu",
    "cong thuong",
    "thuong mai",
    "doanh nghiep",
    "thue",
    "hai quan",
    "xay dung",
    "bat dong san",
    "dat dai",
    "moi truong",
    "giao thong van tai",
    "hang hai",
    "hang khong",
    "thong tin va truyen thong",
    "cong nghe",
    "y te",
    "duoc",
    "nong nghiep",
    "thuy san",
    "lao dong",
)

PUBLIC_EXCLUDE_KEYWORDS = (
    "hien phap",
    "bo luat hinh su",
    "to tung hinh su",
    "thi hanh an hinh su",
    "an ninh quoc gia",
    "nghia vu quan su",
    "dan quan tu ve",
    "cong an nhan dan",
    "ho tich",
    "quoc tich",
    "cu tru",
    "ho khau",
    "hon nhan",
    "gia dinh",
    "ly hon",
    "thua ke",
    "nuoi con nuoi",
    "can bo cong chuc",
    "cong chuc",
    "vien chuc",
    "bo may hanh chinh",
    "chinh quyen dia phuong",
    "thi dua",
    "khen thuong",
    "bao tro xa hoi",
    "nguoi co cong",
    "tre em",
    "binh dang gioi",
    "phong chong te nan",
    "an sinh xa hoi",
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

FOCUS_LEGAL_TYPES = {
    "luat",
    "phap lenh",
    "nghi dinh",
    "thong tu",
    "thong tu lien tich",
    "quyet dinh",
    "nghi quyet",
    "chi thi",
}


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Build a focused economy/finance/industry corpus in local SQLite."
    )
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument(
        "--selection-path",
        type=Path,
        default=settings.database_path.parent / "hf_focused_corpus_selection.json",
    )
    parser.add_argument("--rebuild-selection", action="store_true")
    parser.add_argument("--skip-postprocess", action="store_true")
    return parser.parse_args()


def get_document_count(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]


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


def match_keywords(value: str, keywords: tuple[str, ...]) -> list[str]:
    padded_value = f" {value} "
    return [keyword for keyword in keywords if f" {keyword} " in padded_value]


def normalize_field(value: str | None) -> str:
    normalized = normalize_ascii(value or "")
    normalized = re.sub(r"[^0-9a-z\s]", " ", normalized)
    return " ".join(normalized.split())


def is_focus_legal_type(value: str | None) -> bool:
    return normalize_field(value) in FOCUS_LEGAL_TYPES


def should_include_document(metadata: dict) -> bool:
    title = normalize_field(metadata.get("title"))
    legal_type = normalize_field(metadata.get("loai_van_ban"))
    issuer = normalize_field(metadata.get("co_quan_ban_hanh"))
    sectors = normalize_field(
        " | ".join(
            part.strip()
            for part in [metadata.get("nganh"), metadata.get("linh_vuc")]
            if part and str(part).strip()
        )
    )
    haystack = " | ".join(filter(None, [title, legal_type, issuer, sectors]))

    primary_issuer_hits = match_keywords(issuer, PRIMARY_ISSUER_KEYWORDS)
    conditional_issuer_hits = match_keywords(issuer, CONDITIONAL_ISSUER_KEYWORDS)
    filtered_issuer_hits = match_keywords(issuer, HEAVILY_FILTERED_ISSUER_KEYWORDS)
    excluded_sector_hits = match_keywords(sectors, EXCLUDED_SECTOR_KEYWORDS)
    focus_keyword_hits = match_keywords(haystack, FOCUS_KEYWORDS)
    sector_keyword_hits = match_keywords(sectors, FOCUS_SECTOR_KEYWORDS)
    public_exclude_hits = match_keywords(haystack, PUBLIC_EXCLUDE_KEYWORDS)

    include_score = 0
    if primary_issuer_hits:
        include_score += 5
    if sector_keyword_hits:
        include_score += min(4, len(sector_keyword_hits) + 1)
    if focus_keyword_hits:
        include_score += min(6, len(focus_keyword_hits) * 2)
    if conditional_issuer_hits and (sector_keyword_hits or focus_keyword_hits):
        include_score += 2
    if is_focus_legal_type(legal_type) and (sector_keyword_hits or focus_keyword_hits):
        include_score += 1

    exclude_score = len(public_exclude_hits) * 3
    if filtered_issuer_hits:
        exclude_score += 4
    if excluded_sector_hits:
        exclude_score += min(6, len(excluded_sector_hits) * 2)

    if filtered_issuer_hits and include_score < 6:
        return False
    if excluded_sector_hits and include_score < 7:
        return False
    if (
        primary_issuer_hits
        and include_score >= 5
        and include_score + 1 >= exclude_score
    ):
        return True
    if conditional_issuer_hits and include_score >= 4 and include_score > exclude_score:
        return True
    if sector_keyword_hits and focus_keyword_hits and include_score >= exclude_score:
        return True
    return include_score >= 5 and include_score > exclude_score


def build_selection() -> list[int]:
    cached_content_ids = get_cached_content_ids()
    candidates: list[tuple[tuple[int, str, int], int]] = []
    skipped_missing_content = 0
    skipped_out_of_scope = 0

    for batch in iter_hf_parquet_batches(
        "data/metadata.parquet",
        columns=METADATA_COLUMNS,
        batch_size=2048,
    ):
        for metadata in batch:
            document_id = int(metadata["id"])
            if document_id not in cached_content_ids:
                skipped_missing_content += 1
                continue
            if not should_include_document(metadata):
                skipped_out_of_scope += 1
                continue
            candidates.append((build_sort_key(metadata), document_id))

    candidates.sort(key=lambda item: item[0], reverse=True)
    selected_ids = [document_id for _, document_id in candidates]
    print(
        f"Selected {len(selected_ids)} focused documents. "
        f"Skipped {skipped_out_of_scope} out-of-scope documents and {skipped_missing_content} without cached content."
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
    connection: sqlite3.Connection,
    document_ids: list[int],
    *,
    chunk_size: int,
    batch_size: int,
) -> int:
    metadata_lookup = fetch_metadata_lookup(document_ids)
    cache_path = ensure_hf_content_cache()
    content_connection = sqlite3.connect(cache_path)
    imported = 0

    try:
        for start in range(0, len(document_ids), chunk_size):
            chunk_ids = document_ids[start : start + chunk_size]
            print(
                f"Starting focused chunk {start // chunk_size + 1} with {len(chunk_ids)} documents..."
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
                        f"  imported {chunk_imported}/{len(chunk_ids)} in current focused chunk..."
                    )
                    batch.clear()

            if batch:
                import_documents(connection, batch)
                imported += len(batch)
                chunk_imported += len(batch)

            print(
                f"Focused chunk complete. Imported {chunk_imported}. Total imported this run {imported}."
            )
    finally:
        content_connection.close()

    return imported


def main() -> None:
    args = parse_args()
    connection = get_connection()
    initialize_database(connection)

    if args.reset:
        print("Resetting local corpus tables before focused rebuild...")
        reset_database(connection)

    print(f"Dataset: {get_settings().dataset_name}")
    print(f"Current local document count: {get_document_count(connection)}")

    selected_ids = [] if args.rebuild_selection else load_selection(args.selection_path)
    if not selected_ids:
        print("Building newest-first focused selection...")
        selected_ids = build_selection()
        save_selection(args.selection_path, selected_ids)
    else:
        print(f"Loaded cached focused selection with {len(selected_ids)} document ids.")

    imported = import_selected_records(
        connection,
        selected_ids,
        chunk_size=args.chunk_size,
        batch_size=args.batch_size,
    )
    print(f"Imported {imported} focused documents.")

    if not args.skip_postprocess:
        print("Refreshing taxonomy, relations, and citations...")
        bootstrap_taxonomy(connection, prefer_live=False)
        relation_count = rebuild_relationship_graph(connection)
        citation_count = rebuild_citation_index(connection)
        print(f"Built {relation_count} relations and {citation_count} citation links.")

    print(f"Final local document count: {get_document_count(connection)}")
    connection.close()


if __name__ == "__main__":
    main()
