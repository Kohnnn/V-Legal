from __future__ import annotations

import argparse

from vlegal_prototype.official_sources import fetch_source_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch and store a raw snapshot from an official legal source."
    )
    parser.add_argument(
        "--source-system",
        required=True,
        choices=["vbpl", "vanban_chinhphu", "phapdien"],
        help="Which official source this snapshot belongs to.",
    )
    parser.add_argument(
        "--source-document-id",
        required=True,
        help="Stable source-native identifier for the document or node.",
    )
    parser.add_argument("--url", required=True, help="Official source URL to snapshot.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = fetch_source_snapshot(
        source_system=args.source_system,
        source_document_id=args.source_document_id,
        source_url=args.url,
        timeout=args.timeout,
    )
    print(f"Saved snapshot to {snapshot.path}")
    print(f"Content-Type: {snapshot.content_type}")
    print(f"Body hash: {snapshot.body_hash}")


if __name__ == "__main__":
    main()
