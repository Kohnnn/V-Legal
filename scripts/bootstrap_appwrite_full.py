from __future__ import annotations

import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()

from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query

from vlegal_prototype.settings import get_settings
from vlegal_prototype.hf_ingest import (
    build_excerpt,
    normalize_text,
    split_into_passages,
    stream_hf_records,
)


AUTHORITY_RE = re.compile(
    r"^(.+?)\s*\|\s*CỘNG HÒA\s*XÃ HỘI\s*CHỦ NGHĨA\s*VIỆT\s*NAM\s*Độc lập\s*-\s*Tự do\s*-\s*Hạnh phúc\s*$",
    re.I,
)
DATE_RE = re.compile(
    r"^Số\s*:\s*.+?\s*\|\s*.+?,\s*ngày\s+(\d+)\s*tháng\s+(\d+)\s*năm\s+(\d+)$"
)
KNOWN_LEGAL_TYPES = {
    "NGHỊ ĐỊNH",
    "NGHỊ QUYẾT",
    "QUYẾT ĐỊNH",
    "THÔNG TƯ",
    "THÔNG TƯ LIÊN TỊCH",
    "CHỈ THỊ",
    "LUẬT",
    "BỘ LUẬT",
    "LỆNH",
    "KẾ HOẠCH",
    "KẾ HOẊCH",
    "KẾT LUẬN",
    "THÔNG BÁO",
    "THÔNG BÁO KẾT LUẬN",
    "THÔNG TRI",
    "HƯỚNG DẪN",
    "HƯỞNG DẪN TẠM THỜI",
    "QUY CHẾ PHỐI HỢP",
    "BÁO CÁO",
    "QUY TRÌNH, PHƯƠNG ÁN",
    "QUỐC HỘI",
}
SIMPLE_LEGAL_TYPES_RE = re.compile(
    r"^(NGHỊ ĐỊNH|NGHỊ QUYẾT|QUYẾT ĐỊNH|THÔNG TƯ|THÔNG TƯ LIÊN TỊCH|"
    r"CHỈ THỊ|LUẬT|BỘ LUẬT|LỆNH|KẾ HOẠCH|KẾ HOẠCH HÀNH ĐỘNG|"
    r"KẾT LUẬN|KẾT LUẬN THANH TRA|THÔNG BÁO|THÔNG BÁO KẾT LUẬN|"
    r"THÔNG TRI|HƯỚNG DẪN|HƯỞNG DẪN TẠM THỜI|QUY CHẾ PHỐI HỢP|"
    r"BÁO CÁO|QUY TRÌNH, PHƯƠNG ÁN|QUY ĐỊNH CỦA BỘ CHÍNH TRỊ|"
    r"DECREE|CIRCULAR|LAW)\b",
    re.I,
)


def parse_document(raw_content: str, doc_id: int) -> dict:
    lines = raw_content.split("\n")
    clean_lines = [l.strip() for l in lines if l.strip()]

    issuing_authority = ""
    document_number = ""
    issuance_date = ""
    legal_type = ""
    title = ""
    signer_block = ""

    authority_match = AUTHORITY_RE.match(clean_lines[0]) if clean_lines else None
    if authority_match:
        issuing_authority = authority_match.group(1).strip()
    elif len(clean_lines) > 0:
        issuing_authority = clean_lines[0][:200]

    for line in clean_lines[1:8]:
        dm = DATE_RE.match(line.strip())
        if dm:
            day, month, year = dm.groups()
            issuance_date = f"{day.zfill(2)}/{month.zfill(2)}/{year}"
            parts = line.split("|")
            if len(parts) >= 1:
                sn = parts[0].replace("Số:", "").strip()
                if "Số:" in line:
                    sn = parts[0].replace("Số:", "").strip()
                else:
                    sn = parts[0].strip()
                document_number = sn
            break

    if len(clean_lines) > 3:
        candidate = clean_lines[3].strip()
        if SIMPLE_LEGAL_TYPES_RE.match(candidate):
            legal_type = SIMPLE_LEGAL_TYPES_RE.match(candidate).group(1).upper()
    if not legal_type and len(clean_lines) > 3:
        legal_type = clean_lines[3].strip()[:100]

    if len(clean_lines) > 5:
        title = clean_lines[5].strip()
    elif len(clean_lines) > 4:
        title = clean_lines[4].strip()
    else:
        title = clean_lines[1][:200] if len(clean_lines) > 1 else f"Document {doc_id}"

    if title == issuing_authority and len(clean_lines) > 6:
        title = clean_lines[6].strip()
    if len(title) > 500:
        title = title[:497] + "..."

    plain = normalize_text(raw_content)
    passages = split_into_passages(raw_content)
    excerpt = build_excerpt(plain, max_length=280)

    year = None
    if issuance_date:
        try:
            year = datetime.strptime(issuance_date, "%d/%m/%Y").year
        except ValueError:
            pass

    return {
        "id": doc_id,
        "document_number": document_number,
        "title": title,
        "url": "",
        "legal_type": legal_type,
        "legal_sectors": "",
        "issuing_authority": issuing_authority,
        "issuance_date": issuance_date,
        "signers": signer_block,
        "content": raw_content,
        "plain_content": plain,
        "excerpt": excerpt,
        "year": year,
        "source": get_settings().dataset_name,
        "passages": passages,
    }


def get_db() -> Databases:
    settings = get_settings()
    client = Client()
    client.set_endpoint(settings.appwrite_endpoint)
    client.set_project(settings.appwrite_project_id)
    client.set_key(settings.appwrite_api_key)
    return Databases(client)


def create_documents_batch(
    db: Databases, records: list[dict], db_id: str, batch_size: int = 50
) -> tuple[int, int]:
    success = 0
    errors = 0
    for record in records:
        try:
            db.create_document(
                database_id=db_id,
                collection_id="documents",
                document_id=str(record["id"]),
                data={
                    "document_number": record["document_number"],
                    "title": record["title"],
                    "url": record["url"],
                    "legal_type": record["legal_type"],
                    "legal_sectors": record["legal_sectors"],
                    "issuing_authority": record["issuing_authority"],
                    "issuance_date": record["issuance_date"],
                    "signers": record["signers"],
                    "content": record["content"],
                    "plain_content": record["plain_content"],
                    "excerpt": record["excerpt"],
                    "year": record["year"],
                    "source": record["source"],
                    "imported_at": datetime.utcnow().isoformat(),
                },
            )
            success += 1
        except Exception as e:
            errors += 1
    return success, errors


def create_passages_batch(
    db: Databases, doc_id: int, passages: list[dict], db_id: str
) -> int:
    count = 0
    for p in passages:
        try:
            db.create_document(
                database_id=db_id,
                collection_id="passages",
                document_id="unique()",
                data={
                    "document_id": doc_id,
                    "ordinal": p["ordinal"],
                    "heading": p.get("heading") or "",
                    "text": p["text"],
                },
            )
            count += 1
        except Exception:
            pass
    return count


def main() -> None:
    settings = get_settings()
    if not settings.appwrite_api_key:
        print("ERROR: VLEGAL_APPWRITE_API_KEY not set")
        sys.exit(1)

    db = get_db()
    db_id = settings.appwrite_database_id

    print(f"Streaming full dataset from HuggingFace into Appwrite DB '{db_id}'...")
    print(f"Dataset: {settings.dataset_name}")
    print("WARNING: This will take 2-4 hours for all ~518k documents!")
    print()

    BATCH = 100
    COMMIT_EVERY = 500
    PAUSE_EVERY = 2000

    ds = stream_hf_records()

    total_docs = 0
    total_passages = 0
    total_errors = 0
    batch_docs: list[dict] = []

    start_time = time.time()
    last_report = start_time

    for i, row in enumerate(ds):
        try:
            record = row
            batch_docs.append(record)
        except Exception as e:
            total_errors += 1

        if len(batch_docs) >= BATCH:
            s, e = create_documents_batch(db, batch_docs, db_id)
            for rec in batch_docs:
                if rec["passages"]:
                    total_passages += create_passages_batch(
                        db, rec["id"], rec["passages"], db_id
                    )
            total_docs += s
            total_errors += e
            batch_docs = []

            if (i + 1) % COMMIT_EVERY == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                print(
                    f"  Processed {i + 1} rows | {total_docs} docs | {total_passages} passages | {total_errors} errors | {rate:.1f} rows/sec"
                )

            if (i + 1) % PAUSE_EVERY == 0:
                time.sleep(2)

    if batch_docs:
        s, e = create_documents_batch(db, batch_docs, db_id)
        for rec in batch_docs:
            if rec["passages"]:
                total_passages += create_passages_batch(
                    db, rec["id"], rec["passages"], db_id
                )
        total_docs += s
        total_errors += e

    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.0f}s.")
    print(f"  Total documents: {total_docs}")
    print(f"  Total passages: {total_passages}")
    print(f"  Errors: {total_errors}")


if __name__ == "__main__":
    main()
