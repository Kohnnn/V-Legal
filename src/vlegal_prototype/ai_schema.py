from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .settings import get_settings


JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_payload(value: str) -> dict | None:
    text = (value or "").strip()
    if not text:
        return None
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


def _build_prompt(record: dict, markdown_body: str, deterministic_sidecar: dict) -> str:
    sidecar_summary = {
        "parse_confidence": deterministic_sidecar.get("parse_confidence"),
        "counts": deterministic_sidecar.get("counts", {}),
        "first_blocks": deterministic_sidecar.get("structural_blocks", [])[:12],
        "first_mentions": deterministic_sidecar.get("citation_mentions", [])[:24],
    }
    prompt_payload = {
        "task": "Reinforce the schema of a Vietnamese legal markdown document without rewriting the law text.",
        "rules": [
            "Do not paraphrase or rewrite the canonical legal text.",
            "Infer structure only.",
            "Return JSON only.",
            "Use these top-level keys exactly: normalized_metadata, blocks, citations, confidence, notes.",
            "Keep notes short and factual.",
        ],
        "document": {
            "title": record.get("title") or "",
            "document_number": record.get("document_number") or "",
            "legal_type": record.get("legal_type") or "",
            "issuing_authority": record.get("issuing_authority") or "",
            "text_source": record.get("text_source") or "",
            "parse_confidence": record.get("parse_confidence") or "",
        },
        "deterministic_sidecar": sidecar_summary,
        "markdown_excerpt": markdown_body[:16000],
    }
    return json.dumps(prompt_payload, ensure_ascii=False)


def maybe_generate_ai_schema_interpretation(
    record: dict, markdown_body: str, deterministic_sidecar: dict
) -> dict | None:
    settings = get_settings()
    if not settings.enable_ai_schema_sidecar:
        return None
    if settings.ai_schema_provider not in {"openai_compatible", "minimax"}:
        return None
    if not settings.ai_schema_endpoint or not settings.ai_schema_model:
        return None
    if not settings.ai_schema_api_key:
        return None

    text_source = (record.get("text_source") or "").lower()
    parse_confidence = (record.get("parse_confidence") or "").lower()
    if text_source not in {"pdf", "ocr", "mixed"} and parse_confidence != "low":
        return None

    payload = {
        "model": settings.ai_schema_model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": "You extract structure from Vietnamese legal documents. Return JSON only.",
            },
            {
                "role": "user",
                "content": _build_prompt(record, markdown_body, deterministic_sidecar),
            },
        ],
    }
    request = Request(
        settings.ai_schema_endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.ai_schema_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.ai_schema_timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None

    choices = response_payload.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "\n".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    if not isinstance(content, str):
        return None
    parsed = _extract_json_payload(content)
    if not parsed:
        return None
    return {
        "provider": settings.ai_schema_provider,
        "model": settings.ai_schema_model,
        "endpoint": settings.ai_schema_endpoint,
        "interpretation": parsed,
    }
