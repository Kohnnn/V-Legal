from __future__ import annotations

import argparse
from pathlib import Path

from vlegal_prototype.corpus import (
    ensure_corpus_layout,
    iter_canonical_documents,
    write_jsonl_records,
)


def resolve_optional_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if path.exists() else ""


def build_manifest_record(document, root: Path) -> dict:
    metadata = document.metadata
    canonical_id = str(metadata.get("canonical_id") or document.file_path.stem)
    sidecar_path = root / "manifests" / "sidecars" / f"{canonical_id}.json"

    source_system = str(metadata.get("source_system") or "")
    raw_path = Path()
    if source_system:
        raw_dir = root / "raw" / source_system
        if raw_dir.exists():
            matches = sorted(raw_dir.glob(f"{canonical_id}*"))
            if matches:
                raw_path = matches[0]

    return {
        "canonical_id": canonical_id,
        "document_layer": str(metadata.get("document_layer") or ""),
        "title": str(metadata.get("title") or ""),
        "document_number": str(metadata.get("document_number") or ""),
        "source_system": source_system,
        "source_document_id": str(metadata.get("source_document_id") or ""),
        "source_url": str(metadata.get("source_url") or ""),
        "official_source_system": str(metadata.get("official_source_system") or ""),
        "official_source_document_id": str(
            metadata.get("official_source_document_id") or ""
        ),
        "official_source_url": str(metadata.get("official_source_url") or ""),
        "trust_level": str(metadata.get("trust_level") or ""),
        "text_source": str(metadata.get("text_source") or ""),
        "parse_confidence": str(metadata.get("parse_confidence") or ""),
        "issuance_date": str(metadata.get("issuance_date") or ""),
        "markdown_path": document.file_path.relative_to(root).as_posix(),
        "raw_path": resolve_optional_path(raw_path, root) if raw_path else "",
        "sidecar_path": resolve_optional_path(sidecar_path, root),
        "source_hash": str(metadata.get("source_hash") or ""),
        "markdown_hash": str(metadata.get("markdown_hash") or ""),
        "updated_at": str(metadata.get("updated_at") or ""),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regenerate corpus manifest files from canonical markdown documents."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on how many markdown documents to scan.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = ensure_corpus_layout()
    documents = iter_canonical_documents(limit=args.limit or None)
    records = [build_manifest_record(document, paths.root) for document in documents]
    write_jsonl_records(
        paths.documents_manifest,
        sorted(records, key=lambda item: item["canonical_id"]),
    )
    print(f"Done. Regenerated documents manifest with {len(records)} records.")


if __name__ == "__main__":
    main()
