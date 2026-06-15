from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .corpus import append_jsonl_record, ensure_corpus_layout, sha256_bytes, utc_now_iso


DEFAULT_USER_AGENT = "V-Legal Prototype/0.1"
CONTENT_TYPE_EXTENSION_MAP = {
    "text/html": ".html",
    "application/pdf": ".pdf",
    "application/json": ".json",
    "text/plain": ".txt",
    "application/zip": ".zip",
}


@dataclass(frozen=True)
class SourceSnapshot:
    source_system: str
    source_document_id: str
    source_url: str
    content_type: str
    body: bytes
    fetched_at: str
    path: Path
    body_hash: str


def guess_extension(url: str, content_type: str) -> str:
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type in CONTENT_TYPE_EXTENSION_MAP:
        return CONTENT_TYPE_EXTENSION_MAP[normalized_type]
    parsed = urlparse(url)
    guessed = Path(parsed.path).suffix
    if guessed:
        return guessed
    mime_guess, _ = mimetypes.guess_type(url)
    if mime_guess and mime_guess in CONTENT_TYPE_EXTENSION_MAP:
        return CONTENT_TYPE_EXTENSION_MAP[mime_guess]
    return ".bin"


def fetch_source_snapshot(
    *, source_system: str, source_document_id: str, source_url: str, timeout: int = 30
) -> SourceSnapshot:
    request = Request(source_url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
        content_type = response.headers.get_content_type() or "application/octet-stream"
    paths = ensure_corpus_layout()
    extension = guess_extension(source_url, content_type)
    snapshot_path = (
        paths.raw_root
        / source_system
        / f"{source_system}-{source_document_id}{extension}"
    )
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_bytes(body)
    snapshot = SourceSnapshot(
        source_system=source_system,
        source_document_id=source_document_id,
        source_url=source_url,
        content_type=content_type,
        body=body,
        fetched_at=utc_now_iso(),
        path=snapshot_path,
        body_hash=sha256_bytes(body),
    )
    append_jsonl_record(
        paths.source_runs_manifest,
        {
            "kind": "official_snapshot",
            "source_system": source_system,
            "source_document_id": source_document_id,
            "source_url": source_url,
            "content_type": content_type,
            "body_hash": snapshot.body_hash,
            "path": snapshot.path.relative_to(paths.root).as_posix(),
            "fetched_at": snapshot.fetched_at,
        },
    )
    metadata_path = snapshot_path.with_suffix(f"{snapshot_path.suffix}.json")
    metadata_path.write_text(
        json.dumps(
            {
                "source_system": source_system,
                "source_document_id": source_document_id,
                "source_url": source_url,
                "content_type": content_type,
                "body_hash": snapshot.body_hash,
                "fetched_at": snapshot.fetched_at,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return snapshot
