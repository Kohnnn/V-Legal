from __future__ import annotations

import argparse
import json

from vlegal_prototype.corpus import append_jsonl_record, ensure_corpus_layout
from vlegal_prototype.minimax_text import (
    correct_ocr_text_with_minimax,
    has_minimax_credentials,
    iter_minimax_repair_targets,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply MiniMax text-only OCR correction to queued OCR documents."
    )
    parser.add_argument(
        "--mode",
        default="recommended",
        choices=["recommended", "optional"],
        help="Which OCR LLM recommendations to process.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on how many targets to process.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not has_minimax_credentials():
        raise SystemExit("MiniMax credentials are not configured.")

    paths = ensure_corpus_layout()
    targets = iter_minimax_repair_targets(mode=args.mode)
    if args.limit:
        targets = targets[: args.limit]

    processed = 0
    failures: list[dict[str, str]] = []
    for target in targets:
        canonical_id = target["canonical_id"]
        try:
            result = correct_ocr_text_with_minimax(canonical_id)
            append_jsonl_record(
                paths.manifests_root / "minimax_ocr_runs.jsonl",
                {
                    "canonical_id": canonical_id,
                    "status": "corrected",
                    "pre_recommendation": result.get("pre_assessment", {}).get(
                        "recommendation", ""
                    ),
                    "post_recommendation": result.get("post_assessment", {}).get(
                        "recommendation", ""
                    ),
                },
            )
            processed += 1
            print(
                f"Corrected {canonical_id}: "
                f"{result.get('pre_assessment', {}).get('recommendation', 'unknown')} -> "
                f"{result.get('post_assessment', {}).get('recommendation', 'unknown')}"
            )
        except Exception as exc:
            failures.append({"canonical_id": canonical_id, "error": str(exc)})
            append_jsonl_record(
                paths.manifests_root / "minimax_ocr_runs.jsonl",
                {
                    "canonical_id": canonical_id,
                    "status": "failed",
                    "error": str(exc),
                },
            )
            print(f"Failed {canonical_id}: {exc}")

    print(f"Done. Corrected {processed} OCR documents with MiniMax.")
    if failures:
        print(json.dumps(failures, ensure_ascii=False))


if __name__ == "__main__":
    main()
