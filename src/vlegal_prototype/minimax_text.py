from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .corpus import ensure_corpus_layout, iter_canonical_documents, utc_now_iso
from .pdf_ocr import apply_extracted_text_to_document, assess_ocr_llm_need
from .settings import get_settings


JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
MAX_CHARS_PER_CALL = 1000
DEFAULT_MINIMAX_CHAT_PATH = "/v1/chat/completions"


def has_minimax_credentials() -> bool:
    settings = get_settings()
    return bool(
        settings.minimax_api_key and settings.minimax_api_url and settings.minimax_model
    )


def resolve_minimax_api_url() -> str:
    settings = get_settings()
    url = (settings.minimax_api_url or "").strip()
    if not url:
        return ""
    if url.rstrip("/") in {
        "https://api.minimax.io",
        "https://api.minimax.io/v1",
        "https://api.minimaxi.com",
        "https://api.minimaxi.com/v1",
    }:
        if url.rstrip("/").startswith("https://api.minimax.io"):
            return f"https://api.minimax.io{DEFAULT_MINIMAX_CHAT_PATH}"
        return f"https://api.minimaxi.com{DEFAULT_MINIMAX_CHAT_PATH}"
    if url.endswith(DEFAULT_MINIMAX_CHAT_PATH):
        return url
    if url.endswith("/v1"):
        return f"{url}{DEFAULT_MINIMAX_CHAT_PATH[3:]}"
    if url.endswith("/"):
        return f"{url.rstrip('/')}{DEFAULT_MINIMAX_CHAT_PATH}"
    if "/v1/" in url:
        return url
    return f"{url}{DEFAULT_MINIMAX_CHAT_PATH}"


def _extract_json_object(content: str) -> dict[str, Any] | None:
    text = (content or "").strip()
    match = JSON_BLOCK_PATTERN.search(text)
    if match:
        text = match.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _extract_message_text(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            item.get("text", "") for item in content if isinstance(item, dict)
        )
    return ""


def ensure_minimax_success(response_payload: dict[str, Any]) -> None:
    base_resp = response_payload.get("base_resp") or {}
    status_code = base_resp.get("status_code", 0)
    if status_code and int(status_code) != 0:
        raise RuntimeError(
            f"MiniMax request failed with status_code={status_code}: {base_resp.get('status_msg', '')}"
        )


def call_minimax_text(
    messages: list[dict[str, str]], *, temperature: float = 0.1
) -> dict[str, Any]:
    settings = get_settings()
    payload = {
        "model": settings.minimax_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
        "reasoning_split": True,
    }
    request = Request(
        resolve_minimax_api_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.minimax_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=settings.minimax_timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    ensure_minimax_success(payload)
    return payload


def build_ocr_correction_messages(
    metadata: dict[str, Any],
    raw_text: str,
    *,
    chunk_index: int = 1,
    chunk_count: int = 1,
) -> list[dict[str, str]]:
    document_hint = (
        f"title={metadata.get('title') or ''}; "
        f"number={metadata.get('document_number') or ''}; "
        f"chunk={chunk_index}/{chunk_count}"
    )
    return [
        {
            "role": "system",
            "name": "MiniMax AI",
            "content": (
                "You repair OCR text for Vietnamese legal documents. "
                "Return only a JSON object with key corrected_text. "
                "Do not explain. Do not summarize. Do not add content that is not present. "
                "Preserve legal numbering and line breaks."
            ),
        },
        {
            "role": "user",
            "name": "User",
            "content": (
                f"{document_hint}\n"
                "Correct the OCR text below and return JSON only.\n"
                "<ocr_text>\n"
                f"{raw_text[:MAX_CHARS_PER_CALL]}\n"
                "</ocr_text>"
            ),
        },
    ]


def split_ocr_text_into_chunks(
    raw_text: str, max_chars: int = MAX_CHARS_PER_CALL
) -> list[str]:
    lines = raw_text.splitlines()
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        addition = len(line) + 1
        if current and current_len + addition > max_chars:
            chunks.append("\n".join(current).strip())
            current = []
            current_len = 0
        current.append(line)
        current_len += addition

    if current:
        chunks.append("\n".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def split_text_in_half(raw_text: str) -> list[str]:
    lines = [line for line in raw_text.splitlines()]
    if len(lines) <= 1:
        midpoint = max(1, len(raw_text) // 2)
        return [raw_text[:midpoint].strip(), raw_text[midpoint:].strip()]
    midpoint = max(1, len(lines) // 2)
    return [
        "\n".join(lines[:midpoint]).strip(),
        "\n".join(lines[midpoint:]).strip(),
    ]


def correct_single_chunk_with_minimax(
    metadata: dict[str, Any],
    chunk: str,
    *,
    chunk_index: int,
    chunk_count: int,
    depth: int = 0,
) -> tuple[str, list[dict[str, Any]]]:
    for attempt in range(3):
        response_payload = call_minimax_text(
            build_ocr_correction_messages(
                metadata,
                chunk,
                chunk_index=chunk_index,
                chunk_count=chunk_count,
            ),
            temperature=0.05,
        )
        content = _extract_message_text(response_payload)
        parsed = _extract_json_object(content)
        if parsed and parsed.get("corrected_text"):
            return str(parsed["corrected_text"]).strip(), [
                {
                    "chunk_index": chunk_index,
                    "chunk_count": chunk_count,
                    "depth": depth,
                    "split": False,
                    "attempt": attempt + 1,
                    "notes": [],
                }
            ]

    if len(chunk) <= 400 or depth >= 3:
        raise RuntimeError(
            f"MiniMax did not return a usable corrected_text payload for chunk {chunk_index}/{chunk_count}."
        )

    left, right = split_text_in_half(chunk)
    corrected_parts: list[str] = []
    notes: list[dict[str, Any]] = [
        {
            "chunk_index": chunk_index,
            "chunk_count": chunk_count,
            "depth": depth,
            "split": True,
            "notes": [],
        }
    ]
    for part_offset, part in enumerate((left, right), start=1):
        if not part:
            continue
        corrected_text, child_notes = correct_single_chunk_with_minimax(
            metadata,
            part,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
            depth=depth + 1,
        )
        corrected_parts.append(corrected_text)
        notes.extend(child_notes)
    return "\n".join(part for part in corrected_parts if part).strip(), notes


def correct_ocr_text_chunks_with_minimax(
    metadata: dict[str, Any], raw_text: str
) -> tuple[str, list[dict[str, Any]]]:
    chunks = split_ocr_text_into_chunks(raw_text)
    corrected_chunks: list[str] = []
    chunk_notes: list[dict[str, Any]] = []
    total = len(chunks)

    for index, chunk in enumerate(chunks, start=1):
        corrected_text, notes = correct_single_chunk_with_minimax(
            metadata,
            chunk,
            chunk_index=index,
            chunk_count=total,
        )
        corrected_chunks.append(corrected_text)
        chunk_notes.extend(notes)

    return "\n\n".join(chunk for chunk in corrected_chunks if chunk), chunk_notes


def correct_ocr_text_with_minimax(canonical_id: str) -> dict[str, Any]:
    if not has_minimax_credentials():
        raise RuntimeError("MiniMax credentials are not configured.")

    target_document = None
    for document in iter_canonical_documents():
        if str(document.metadata.get("canonical_id") or "") == canonical_id:
            target_document = document
            break
    if target_document is None:
        raise ValueError(f"Unknown canonical_id: {canonical_id}")

    paths = ensure_corpus_layout()
    raw_ocr_path = paths.raw_root / "ocr" / f"{canonical_id}.txt"
    if not raw_ocr_path.exists():
        raise ValueError(f"Raw OCR text not found for {canonical_id}")

    raw_text = raw_ocr_path.read_text(encoding="utf-8")
    pre_assessment = assess_ocr_llm_need(raw_text)
    corrected_text, chunk_notes = correct_ocr_text_chunks_with_minimax(
        target_document.metadata,
        raw_text,
    )
    result = apply_extracted_text_to_document(
        canonical_id=canonical_id,
        raw_text=corrected_text,
        backend="minimax_text_correction",
        text_source="ocr",
        parse_confidence="medium",
    )
    post_assessment = assess_ocr_llm_need(corrected_text)

    correction_path = raw_ocr_path.with_suffix(".minimax.txt")
    correction_path.write_text(corrected_text, encoding="utf-8")
    sidecar_path = paths.manifests_root / f"{canonical_id}.minimax.json"
    sidecar_path.write_text(
        json.dumps(
            {
                "canonical_id": canonical_id,
                "generated_at": utc_now_iso(),
                "model": get_settings().minimax_model,
                "api_url": resolve_minimax_api_url(),
                "pre_assessment": pre_assessment,
                "post_assessment": post_assessment,
                "notes": chunk_notes,
                "corrected_text_path": correction_path.relative_to(
                    paths.root
                ).as_posix(),
                "apply_result": result,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        **result,
        "pre_assessment": pre_assessment,
        "post_assessment": post_assessment,
        "notes": chunk_notes,
        "corrected_text_path": correction_path.relative_to(paths.root).as_posix(),
        "sidecar_path": sidecar_path.relative_to(paths.root).as_posix(),
    }


def iter_minimax_repair_targets(mode: str = "recommended") -> list[dict[str, Any]]:
    paths = ensure_corpus_layout()
    targets: list[dict[str, Any]] = []
    for document in iter_canonical_documents():
        metadata = document.metadata
        canonical_id = str(metadata.get("canonical_id") or "")
        raw_ocr_path = paths.raw_root / "ocr" / f"{canonical_id}.txt"
        if not raw_ocr_path.exists():
            continue
        assessment = assess_ocr_llm_need(raw_ocr_path.read_text(encoding="utf-8"))
        recommendation = assessment.get("recommendation")
        if mode == "recommended" and recommendation != "recommended":
            continue
        if mode == "optional" and recommendation not in {"optional", "recommended"}:
            continue
        targets.append(
            {
                "canonical_id": canonical_id,
                "title": metadata.get("title") or canonical_id,
                "document_number": metadata.get("document_number") or "",
                "recommendation": recommendation,
                "reason": assessment.get("reason") or "",
            }
        )
    return targets
