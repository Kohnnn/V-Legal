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
            "summary": "Try a more specific question, a document number, or import a larger dataset sample first.",
            "findings": [],
            "sources": [],
            "disclaimer": "Prototype mode: this brief only reflects the currently imported local corpus.",
        }

    query_terms = extract_terms(question)
    best_document = passages[0]
    document_frequency = Counter(passage["document_id"] for passage in passages)
    dominant_document_id, _ = document_frequency.most_common(1)[0]
    dominant_document = next(
        passage
        for passage in passages
        if passage["document_id"] == dominant_document_id
    )

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
        "headline": f"Strongest signal in the current corpus: {dominant_document['title']}",
        "summary": (
            "This prototype assembled an evidence brief from the most relevant retrieved passages. "
            f"The closest match surfaced from {best_document['legal_type'] or 'a legal document'} "
            f"issued by {best_document['issuing_authority'] or 'an issuing authority'}"
            + (
                f" on {best_document['issuance_date']}"
                if best_document.get("issuance_date")
                else ""
            )
            + "."
        ),
        "findings": findings,
        "sources": source_documents,
        "disclaimer": (
            "Prototype mode: verify all findings against official sources before relying on them. "
            "This brief is grounded in the locally imported corpus, not yet the official-source pipeline."
        ),
    }
