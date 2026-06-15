from __future__ import annotations

import json
from datetime import datetime

from vlegal_prototype.corpus import ensure_corpus_layout


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


def main() -> None:
    paths = ensure_corpus_layout()
    total = 0
    min_year: int | None = None
    max_year: int | None = None
    last_imported_at = ""

    with paths.documents_manifest.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            item = json.loads(line)
            total += 1
            year = extract_year(item.get("issuance_date"))
            if year is not None:
                min_year = year if min_year is None else min(min_year, year)
                max_year = year if max_year is None else max(max_year, year)
            updated_at = str(item.get("updated_at") or "")
            if updated_at > last_imported_at:
                last_imported_at = updated_at

    summary = {
        "document_count": total,
        "min_year": min_year,
        "max_year": max_year,
        "last_imported_at": last_imported_at,
    }
    summary_path = paths.manifests_root / "corpus_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
