from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

from vlegal_prototype.corpus import build_internal_document_id, ensure_corpus_layout


def extract_year(value: str | None) -> int | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        if len(raw) >= 10 and raw[4] == "-":
            return datetime.strptime(raw[:10], "%Y-%m-%d").year
        return datetime.strptime(raw, "%d/%m/%Y").year
    except ValueError:
        return None


def manifest_recent_item(item: dict) -> dict:
    canonical_id = str(item.get("canonical_id") or "")
    return {
        "id": int(item.get("internal_id") or build_internal_document_id(canonical_id)),
        "title": str(item.get("title") or canonical_id),
        "document_number": str(item.get("document_number") or ""),
        "legal_type": str(item.get("document_type") or item.get("legal_type") or ""),
        "issuing_authority": str(item.get("issuing_authority") or ""),
        "issuance_date": str(item.get("issuance_date") or ""),
        "excerpt": "",
    }


def main() -> None:
    paths = ensure_corpus_layout()
    output_path = paths.manifests_root / "archive_home_cache.json"
    legal_type_counts: Counter[str] = Counter()
    year_counts: Counter[int] = Counter()
    recent_candidates: list[dict] = []

    with paths.documents_manifest.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            item = json.loads(line)
            legal_type = str(item.get("document_type") or item.get("legal_type") or "")
            if legal_type:
                legal_type_counts[legal_type] += 1
            year = extract_year(str(item.get("issuance_date") or ""))
            if year is not None:
                year_counts[year] += 1
            recent_candidates.append(item)

    recent_candidates.sort(
        key=lambda item: (
            extract_year(str(item.get("issuance_date") or "")) or 0,
            str(item.get("issuance_date") or ""),
            str(item.get("updated_at") or ""),
        ),
        reverse=True,
    )
    top_legal_types = [
        {"legal_type": legal_type, "total": total}
        for legal_type, total in legal_type_counts.most_common(6)
    ]
    payload = {
        "filters": {
            "legal_types": [legal_type for legal_type, _ in legal_type_counts.most_common(12)],
            "years": [year for year, _ in sorted(year_counts.items(), reverse=True)[:20]],
        },
        "top_legal_types": top_legal_types,
        "recent_documents": [
            manifest_recent_item(item) for item in recent_candidates[:12]
        ],
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output_path),
                "recent": len(payload["recent_documents"]),
                "legal_types": len(payload["filters"]["legal_types"]),
                "years": len(payload["filters"]["years"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
