from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse, parse_qs
from urllib.request import Request, urlopen

from .corpus import (
    append_jsonl_record,
    emit_canonical_document,
    ensure_corpus_layout,
    iter_canonical_documents,
    load_jsonl_index,
    split_frontmatter,
    write_canonical_document,
    write_jsonl_records,
)
from .relations import normalize_document_number
from .settings import get_settings


LISTING_ROW_PATTERN = re.compile(
    r"<tr>\s*<td>\s*<a href='(?P<detail_url>[^']*docid=\d+[^']*)'>\s*"
    r"<span class=\"code\">(?P<document_number>.*?)</span>.*?</a>\s*</td>\s*"
    r"<td>\s*<span class=\"issued-date\">(?P<issuance_date>.*?)</span>\s*</td>\s*"
    r"<td>\s*<a href='[^']*'>\s*<span class=\"substract\">(?P<summary>.*?)</span>\s*</a>"
    r"(?P<tail>.*?)</td>\s*</tr>",
    re.DOTALL | re.IGNORECASE,
)
ATTACHMENT_LINK_PATTERN = re.compile(
    r'<div class="bl-doc-file"><a href="([^"]+)"',
    re.IGNORECASE,
)
DETAIL_ATTACHMENT_HREF_PATTERN = re.compile(
    r'<a[^>]+href="([^"]+)"[^>]*class="view-file"|<a[^>]*class="view-file"[^>]+href="([^"]+)"',
    re.IGNORECASE,
)
DETAIL_TITLE_PATTERN = re.compile(
    r'<span id="[^"]*_lb_noidung">(.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)
DETAIL_BLOCK_PATTERN = re.compile(
    r'<div class="document-detail" id="block_detail">(.*?)</div>\s*<div id="[^"]*_Content"',
    re.DOTALL | re.IGNORECASE,
)
DETAIL_TABLE_PATTERN = re.compile(
    r'<div id="[^"]*_Content" class="Content">\s*<table[^>]*>(.*?)</table>',
    re.DOTALL | re.IGNORECASE,
)
DETAIL_ROW_PATTERN = re.compile(
    r'<tr[^>]*>\s*<td class="col1"[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>',
    re.DOTALL | re.IGNORECASE,
)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"[ \t]+")
MULTILINE_PATTERN = re.compile(r"\n{3,}")
DOCID_PATTERN = re.compile(r"(?:docid|document_id)=(\d+)", re.IGNORECASE)
DATE_DASH_PATTERN = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")
DETAIL_URL_TEMPLATE = "{base}/?pageid={pageid}&docid={docid}"
LEGAL_GROUPS = {
    "1": "Hiến pháp",
    "2": "Sắc lệnh - Sắc luật",
    "3": "Luật - Pháp lệnh",
    "4": "Nghị định",
    "5": "Quyết định",
    "6": "Thông tư",
}


def normalize_vncp_url(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    return urljoin(get_settings().government_portal_base_url, raw)


def extract_docid(value: str | None) -> str:
    raw = normalize_vncp_url(value)
    if not raw:
        return ""
    match = DOCID_PATTERN.search(raw)
    if match:
        return match.group(1)
    parsed = urlparse(raw)
    values = parse_qs(parsed.query)
    return (values.get("docid") or values.get("document_id") or [""])[0]


def strip_html(value: str | None) -> str:
    text = unescape(value or "")
    text = text.replace("\xa0", " ")
    text = text.replace("<br>", "\n").replace("<br />", "\n").replace("<br/>", "\n")
    text = HTML_TAG_PATTERN.sub(" ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = WHITESPACE_PATTERN.sub(" ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = MULTILINE_PATTERN.sub("\n\n", text)
    return text.strip()


def normalize_listing_date(value: str | None) -> str:
    raw = strip_html(value)
    match = DATE_DASH_PATTERN.match(raw)
    if not match:
        return raw
    return f"{match.group(1)}/{match.group(2)}/{match.group(3)}"


def fetch_html(url: str, *, timeout: int = 60) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


def fetch_government_listing_html(
    *,
    classid: int = 1,
    mode: int = 1,
    maxresults: int = 50,
    typegroupid: int | None = None,
    orggroupid: int | None = None,
    timeout: int = 60,
) -> str:
    params: dict[str, str] = {
        "classid": str(classid),
        "mode": str(mode),
        "maxresults": str(maxresults),
    }
    if typegroupid is not None:
        params["typegroupid"] = str(typegroupid)
    if orggroupid is not None:
        params["orggroupid"] = str(orggroupid)
    url = f"{get_settings().government_portal_base_url}/he-thong-van-ban?{urlencode(params)}"
    return fetch_html(url, timeout=timeout)


def parse_government_listing_rows(
    html: str,
    *,
    listing_url: str,
    typegroupid: int | None = None,
    orggroupid: int | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in LISTING_ROW_PATTERN.finditer(html):
        detail_url = normalize_vncp_url(match.group("detail_url"))
        document_number = strip_html(match.group("document_number"))
        issuance_date = normalize_listing_date(match.group("issuance_date"))
        summary = strip_html(match.group("summary"))
        attachment_urls = [
            normalize_vncp_url(url)
            for url in ATTACHMENT_LINK_PATTERN.findall(match.group("tail"))
        ]
        docid = extract_docid(detail_url)
        if not docid or not document_number:
            continue
        rows.append(
            {
                "docid": docid,
                "detail_url": detail_url,
                "document_number": document_number,
                "normalized_document_number": normalize_document_number(
                    document_number
                ),
                "issuance_date": issuance_date,
                "summary": summary,
                "attachment_urls": attachment_urls,
                "listing_url": listing_url,
                "typegroupid": str(typegroupid or ""),
                "orggroupid": str(orggroupid or ""),
            }
        )
    return rows


def build_government_detail_url(docid: str) -> str:
    settings = get_settings()
    return DETAIL_URL_TEMPLATE.format(
        base=settings.government_portal_base_url,
        pageid=settings.government_portal_detail_pageid,
        docid=docid,
    )


def parse_government_detail_page(
    html: str, *, detail_url: str, listing_row: dict[str, Any] | None = None
) -> dict[str, Any]:
    title_match = DETAIL_TITLE_PATTERN.search(html)
    detail_title = strip_html(title_match.group(1)) if title_match else ""
    block_match = DETAIL_BLOCK_PATTERN.search(html)
    inline_detail = strip_html(block_match.group(1)) if block_match else ""
    table_match = DETAIL_TABLE_PATTERN.search(html)
    metadata_rows: dict[str, str] = {}
    attachment_urls: list[str] = []
    if table_match:
        for label_html, value_html in DETAIL_ROW_PATTERN.findall(table_match.group(1)):
            label = strip_html(label_html)
            value = strip_html(value_html)
            metadata_rows[label] = value
            if label == "Tài liệu đính kèm":
                attachment_urls = []
                for first, second in DETAIL_ATTACHMENT_HREF_PATTERN.findall(value_html):
                    href = first or second
                    if href:
                        attachment_urls.append(normalize_vncp_url(href))

    if not attachment_urls and listing_row:
        attachment_urls = list(listing_row.get("attachment_urls") or [])

    title = metadata_rows.get("Trích yếu") or ""
    if not title and detail_title and ":" in detail_title:
        title = detail_title.split(":", 1)[1].strip()
    if not title:
        title = (
            detail_title
            or (listing_row or {}).get("summary")
            or f"Government document {extract_docid(detail_url)}"
        )

    document_number = (
        metadata_rows.get("Số ký hiệu")
        or (listing_row or {}).get("document_number")
        or ""
    )
    legal_type = metadata_rows.get("Loại văn bản") or ""
    issuing_authority = metadata_rows.get("Cơ quan ban hành") or ""
    signers = metadata_rows.get("Người ký") or ""
    issuance_date = normalize_listing_date(metadata_rows.get("Ngày ban hành"))
    effective_date = normalize_listing_date(metadata_rows.get("Ngày có hiệu lực"))
    text_source = "html" if inline_detail else "pdf" if attachment_urls else "mixed"
    parse_confidence = "medium" if inline_detail else "low"

    body_lines = [
        f"Số ký hiệu: {document_number}",
        f"Ngày ban hành: {issuance_date}",
    ]
    if effective_date:
        body_lines.append(f"Ngày có hiệu lực: {effective_date}")
    if legal_type:
        body_lines.append(f"Loại văn bản: {legal_type}")
    if issuing_authority:
        body_lines.append(f"Cơ quan ban hành: {issuing_authority}")
    if signers:
        body_lines.append(f"Người ký: {signers}")
    if title:
        body_lines.append(f"Trích yếu: {title}")
    body_lines.append("")
    if inline_detail:
        body_lines.append(inline_detail)
    elif attachment_urls:
        body_lines.append(
            "Nội dung toàn văn chưa xuất hiện trực tiếp trong HTML chi tiết; sử dụng tệp đính kèm chính thức bên dưới."
        )
    if attachment_urls:
        body_lines.append("")
        body_lines.append("Tài liệu đính kèm:")
        for url in attachment_urls:
            body_lines.append(f"- {url}")

    return {
        "docid": extract_docid(detail_url),
        "detail_url": detail_url,
        "detail_title": detail_title,
        "title": title,
        "document_number": document_number,
        "legal_type": legal_type,
        "issuing_authority": issuing_authority,
        "signers": signers,
        "issuance_date": issuance_date,
        "effective_date": effective_date,
        "attachment_urls": attachment_urls,
        "inline_detail": inline_detail,
        "text_source": text_source,
        "parse_confidence": parse_confidence,
        "content": "\n".join(body_lines).strip(),
        "metadata_rows": metadata_rows,
    }


def build_vncp_record(
    detail: dict[str, Any], listing_row: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "title": detail["title"],
        "document_number": detail["document_number"],
        "url": detail["detail_url"],
        "legal_type": detail["legal_type"],
        "legal_sectors": "",
        "issuing_authority": detail["issuing_authority"],
        "issuance_date": detail["issuance_date"],
        "effective_date": detail["effective_date"],
        "signers": detail["signers"],
        "content": detail["content"],
        "source": detail["detail_url"],
        "official_source_system": "vanban_chinhphu",
        "official_source_document_id": detail["docid"],
        "official_source_url": detail["detail_url"],
        "text_source": detail["text_source"],
        "status": "unknown",
        "scope": "central",
        "attachments": detail["attachment_urls"],
        "provisional": True,
    }


def load_existing_vncp_metadata(canonical_id: str) -> dict[str, Any] | None:
    paths = ensure_corpus_layout()
    manifest_index = load_jsonl_index(paths.documents_manifest)
    entry = manifest_index.get(canonical_id)
    if not entry:
        return None
    markdown_path = entry.get("markdown_path")
    if not markdown_path:
        return None
    file_path = paths.root / markdown_path
    if not file_path.exists():
        return None
    metadata, _ = split_frontmatter(file_path.read_text(encoding="utf-8"))
    return metadata


def _sync_manifest_official_source(
    manifest_index: dict[str, dict[str, Any]],
    canonical_id: str,
    source_system: str,
    source_document_id: str,
    source_url: str,
) -> None:
    manifest_entry = manifest_index.get(canonical_id)
    if not manifest_entry:
        return
    manifest_index[canonical_id] = {
        **manifest_entry,
        "official_source_system": source_system,
        "official_source_document_id": source_document_id,
        "official_source_url": source_url,
    }


def backfill_government_provenance(
    listing_rows: list[dict[str, Any]], *, overwrite: bool = False
) -> dict[str, int]:
    paths = ensure_corpus_layout()
    manifest_index = load_jsonl_index(paths.documents_manifest)
    by_number: dict[str, list[dict[str, Any]]] = {}
    for row in listing_rows:
        normalized = row.get("normalized_document_number") or ""
        if not normalized:
            continue
        by_number.setdefault(normalized, []).append(row)

    updated = 0
    candidates = 0
    for document in iter_canonical_documents():
        metadata = document.metadata
        if metadata.get("document_layer") != "issued":
            continue
        if metadata.get("source_system") == "vanban_chinhphu":
            continue
        normalized = normalize_document_number(
            str(metadata.get("document_number") or "")
        )
        if not normalized:
            continue
        matches = by_number.get(normalized, [])
        if len(matches) != 1:
            continue
        candidates += 1
        if metadata.get("official_source_url") and not overwrite:
            continue
        match = matches[0]
        metadata = dict(metadata)
        metadata["official_source_system"] = "vanban_chinhphu"
        metadata["official_source_document_id"] = match["docid"]
        metadata["official_source_url"] = match["detail_url"]
        attachments = list(metadata.get("attachments") or [])
        for attachment in match.get("attachment_urls", []):
            if attachment not in attachments:
                attachments.append(attachment)
        metadata["attachments"] = attachments
        write_canonical_document(document, metadata, document.body)
        _sync_manifest_official_source(
            manifest_index,
            metadata["canonical_id"],
            "vanban_chinhphu",
            match["docid"],
            match["detail_url"],
        )
        updated += 1

    write_jsonl_records(
        paths.documents_manifest,
        sorted(manifest_index.values(), key=lambda item: item["canonical_id"]),
    )
    append_jsonl_record(
        paths.source_runs_manifest,
        {
            "kind": "vncp_official_backfill_finished",
            "candidate_match_count": candidates,
            "updated_count": updated,
            "overwrite": overwrite,
        },
    )
    return {
        "candidate_match_count": candidates,
        "updated_count": updated,
    }


def import_government_listing(
    *,
    typegroupid: int | None = None,
    orggroupid: int | None = None,
    limit: int | None = None,
    maxresults: int = 50,
    timeout: int = 60,
    backfill_existing: bool = True,
    overwrite_backfill: bool = False,
) -> dict[str, Any]:
    paths = ensure_corpus_layout()
    params: dict[str, str] = {
        "classid": "1",
        "mode": "1",
        "maxresults": str(maxresults),
    }
    if typegroupid is not None:
        params["typegroupid"] = str(typegroupid)
    if orggroupid is not None:
        params["orggroupid"] = str(orggroupid)
    listing_url = f"{get_settings().government_portal_base_url}/he-thong-van-ban?{urlencode(params)}"
    listing_html = fetch_government_listing_html(
        classid=1,
        mode=1,
        maxresults=maxresults,
        typegroupid=typegroupid,
        orggroupid=orggroupid,
        timeout=timeout,
    )
    rows = parse_government_listing_rows(
        listing_html,
        listing_url=listing_url,
        typegroupid=typegroupid,
        orggroupid=orggroupid,
    )
    if limit is not None:
        rows = rows[:limit]

    manifest_index = load_jsonl_index(paths.documents_manifest)
    imported = 0
    details: list[dict[str, Any]] = []
    for row in rows:
        detail_html = fetch_html(row["detail_url"], timeout=timeout)
        detail = parse_government_detail_page(
            detail_html,
            detail_url=row["detail_url"],
            listing_row=row,
        )
        row["attachment_urls"] = detail.get(
            "attachment_urls", row.get("attachment_urls", [])
        )
        details.append(detail)
        record = build_vncp_record(detail, row)
        canonical_id = f"vn-issued-vpcp-{detail['docid']}"
        existing_metadata = load_existing_vncp_metadata(canonical_id)
        if existing_metadata and (
            str(existing_metadata.get("text_source") or "") == "ocr"
            or str(existing_metadata.get("parse_confidence") or "")
            in {"medium", "high"}
        ):
            imported += 1
            continue
        manifest_entry = emit_canonical_document(
            record,
            source_system="vanban_chinhphu",
            source_document_id=detail["docid"],
            raw_snapshot=detail_html,
            raw_snapshot_extension=".html",
            source_url=detail["detail_url"],
            document_layer="issued",
            trust_level="official_secondary",
        )
        manifest_index[manifest_entry["canonical_id"]] = {
            **manifest_entry,
            "listing_url": listing_url,
            "typegroupid": str(typegroupid or ""),
            "typegroup_label": LEGAL_GROUPS.get(str(typegroupid or ""), ""),
            "orggroupid": str(orggroupid or ""),
        }
        imported += 1

    write_jsonl_records(
        paths.documents_manifest,
        sorted(manifest_index.values(), key=lambda item: item["canonical_id"]),
    )
    listing_manifest_path = paths.manifests_root / "vncp_listing_documents.jsonl"
    existing_listing_index = load_jsonl_index(listing_manifest_path, key_field="docid")
    for row in rows:
        existing_listing_index[row["docid"]] = row
    write_jsonl_records(
        listing_manifest_path,
        sorted(existing_listing_index.values(), key=lambda item: item["docid"]),
    )

    backfill_stats = {"candidate_match_count": 0, "updated_count": 0}
    if backfill_existing:
        backfill_stats = backfill_government_provenance(
            rows,
            overwrite=overwrite_backfill,
        )

    append_jsonl_record(
        paths.source_runs_manifest,
        {
            "kind": "vncp_listing_import_finished",
            "listing_url": listing_url,
            "typegroupid": str(typegroupid or ""),
            "orggroupid": str(orggroupid or ""),
            "imported_count": imported,
            "backfill_updated_count": backfill_stats["updated_count"],
        },
    )
    return {
        "imported_count": imported,
        "listing_row_count": len(rows),
        "backfill_candidate_count": backfill_stats["candidate_match_count"],
        "backfill_updated_count": backfill_stats["updated_count"],
    }
