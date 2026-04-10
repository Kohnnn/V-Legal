from __future__ import annotations

import re
from collections import Counter


STOPWORDS = {
    "và",
    "của",
    "là",
    "cho",
    "về",
    "theo",
    "trong",
    "được",
    "các",
    "những",
    "một",
    "khi",
    "để",
    "với",
    "hay",
    "tại",
    "đến",
    "này",
    "đó",
    "what",
    "which",
    "when",
    "where",
    "that",
    "from",
    "have",
    "about",
    "into",
    "your",
    "will",
    "does",
    "with",
    "this",
    "please",
}

WORD_PATTERN = re.compile(r"[0-9A-Za-zÀ-ỹ]+", re.UNICODE)
SENTENCE_PATTERN = re.compile(r"(?<=[.;:!?])\s+")


def extract_terms(question: str) -> set[str]:
    return {
        token.lower()
        for token in WORD_PATTERN.findall(question)
        if len(token) >= 3 and token.lower() not in STOPWORDS
    }


def sentence_score(sentence: str, terms: set[str]) -> float:
    lowered = sentence.lower()
    overlap = sum(1 for term in terms if term in lowered)
    density = overlap / max(len(sentence.split()), 1)
    return overlap + density


def build_grounded_brief(question: str, passages: list[dict]) -> dict:
    if not passages:
        return {
            "headline": "No grounded match found in the current local corpus.",
            "summary": "Try a more specific question, an exact document number, or a narrower legal filter.",
            "findings": [],
            "sources": [],
            "disclaimer": "Prototype mode: this brief only reflects the currently imported local corpus.",
        }

    query_terms = extract_terms(question)
    document_frequency = Counter(passage["document_id"] for passage in passages)

    candidates: list[tuple[float, str, dict]] = []
    for passage in passages:
        for sentence in SENTENCE_PATTERN.split(passage["text"]):
            cleaned = sentence.strip()
            if len(cleaned) < 60:
                continue
            candidates.append((sentence_score(cleaned, query_terms), cleaned, passage))

    candidates.sort(key=lambda item: item[0], reverse=True)

    findings = []
    used_sentences: set[str] = set()
    for _, sentence, passage in candidates:
        if sentence in used_sentences:
            continue
        findings.append(
            {
                "text": sentence,
                "citation": {
                    "document_id": passage["document_id"],
                    "title": passage["title"],
                    "heading": passage.get("heading")
                    or f"Passage {passage['ordinal']}",
                },
            }
        )
        used_sentences.add(sentence)
        if len(findings) == 3:
            break

    source_documents = []
    seen_documents: set[int] = set()
    for passage in passages:
        if passage["document_id"] in seen_documents:
            continue
        source_documents.append(
            {
                "document_id": passage["document_id"],
                "title": passage["title"],
                "document_number": passage["document_number"],
                "legal_type": passage["legal_type"],
                "issuance_date": passage["issuance_date"],
                "url": passage["url"],
            }
        )
        seen_documents.add(passage["document_id"])
        if len(source_documents) == 4:
            break

    return {
        "headline": "Grounded brief from the current corpus",
        "summary": (
            "This prototype assembled an evidence brief from the most relevant retrieved passages. "
            f"It surfaced {len(findings)} key finding(s) across {len(document_frequency)} source document(s)."
        ),
        "findings": findings,
        "sources": source_documents,
        "disclaimer": (
            "Prototype mode: verify all findings against official sources before relying on them. "
            "This brief is grounded in the locally imported corpus, not yet the official-source pipeline."
        ),
    }
