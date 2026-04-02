from __future__ import annotations

import re
import sqlite3


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
ARTICLE_PATTERN = re.compile(r"^(Điều\s+\d+[A-Za-z0-9\-./]*)", re.IGNORECASE)
SECTION_PATTERN = re.compile(r"^(Mục\s+[IVXLC0-9A-Za-z\-./]+.*)$", re.IGNORECASE)
CHAPTER_PATTERN = re.compile(r"^(Chương\s+[IVXLC0-9A-Za-z\-./]+.*)$", re.IGNORECASE)
PART_PATTERN = re.compile(r"^(Phần\s+[IVXLC0-9A-Za-z\-./]+.*)$", re.IGNORECASE)

DOC_NUMBER_IN_TEXT_PATTERN = re.compile(
    r"\b(\d{1,4}[a-z]?(?:/\d{2,4})?/[A-Za-z0-9\u00c0-\u1ef9\-]+(?:/[A-Za-z0-9\u00c0-\u1ef9\-]+)*)\b"
)


def slugify_anchor(value: str) -> str:
    anchor = value.lower().strip()
    anchor = re.sub(r"[^0-9a-z\u00c0-\u1ef9\s-]", "", anchor)
    anchor = re.sub(r"\s+", "-", anchor)
    return anchor or "section"


def detect_section(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line:
        return None

    heading_match = HEADING_PATTERN.match(raw_line)
    if heading_match:
        return ("heading", heading_match.group(2).strip())

    article_match = ARTICLE_PATTERN.match(line)
    if article_match:
        return ("article", article_match.group(1).strip())

    chapter_match = CHAPTER_PATTERN.match(line)
    if chapter_match:
        return ("chapter", chapter_match.group(1).strip())

    part_match = PART_PATTERN.match(line)
    if part_match:
        return ("part", part_match.group(1).strip())

    section_match = SECTION_PATTERN.match(line)
    if section_match:
        return ("section", section_match.group(1).strip())

    return None


def extract_sections(markdown_content: str) -> list[dict]:
    lines = markdown_content.splitlines()
    sections: list[dict] = [
        {
            "ordinal": 0,
            "section_type": "title",
            "label": "Tiêu đề",
            "anchor": "tieu-de",
            "text": "",
        }
    ]

    current_type = "preamble"
    current_label = "Mở đầu"
    current_lines: list[str] = []
    anchor_counts: dict[str, int] = {}
    ordinal = 1

    def build_anchor(label: str) -> str:
        base = slugify_anchor(label)
        anchor_counts[base] = anchor_counts.get(base, 0) + 1
        return f"{base}-{anchor_counts[base]}"

    def flush_current() -> None:
        nonlocal ordinal, current_lines
        text = "\n".join(current_lines).strip()
        if not text:
            current_lines = []
            return
        anchor = build_anchor(current_label)
        sections.append(
            {
                "ordinal": ordinal,
                "section_type": current_type,
                "label": current_label,
                "anchor": anchor,
                "text": text,
            }
        )
        ordinal += 1
        current_lines = []

    for raw_line in lines:
        section_match = detect_section(raw_line)
        if section_match:
            next_type, next_label = section_match
            flush_current()
            current_type = next_type
            current_label = next_label
            current_lines = [raw_line]
            continue
        current_lines.append(raw_line)

    flush_current()
    return sections


def prepare_document_markup(markdown_content: str) -> tuple[str, list[dict]]:
    sections = extract_sections(markdown_content)
    section_iter = iter(
        [section for section in sections if section["section_type"] != "title"]
    )
    next_section = next(section_iter, None)
    lines: list[str] = []

    for raw_line in markdown_content.splitlines():
        if next_section:
            detected = detect_section(raw_line)
            if detected and detected[1] == next_section["label"]:
                lines.append(
                    f'<a id="{next_section["anchor"]}" class="anchor-target"></a>'
                )
                next_section = next(section_iter, None)
        lines.append(raw_line)

    outline = [
        {"heading": section["label"], "anchor": section["anchor"]}
        for section in sections
        if section["section_type"]
        in {"heading", "chapter", "part", "section", "article"}
    ]
    return "\n".join(lines), outline


DOC_NUMBER_PATTERN_V2 = re.compile(
    r"\b([0-9]{1,4}[a-z]?(?:/[0-9]{2,4})?(?:/[A-Za-z0-9\u00c0-\u1ef9\-]+){1,10})\b"
)


def _extract_raw_references(text: str) -> list[tuple[str, int, int]]:
    refs = []
    for m in DOC_NUMBER_PATTERN_V2.finditer(text):
        refs.append((m.group(1), m.start(), m.end()))
    return refs


def _strip_diacritics(s: str) -> str:
    import unicodedata

    stripped = "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )
    return stripped.rstrip("-,. ").lower()


def _best_reference_match(
    raw: str, citation_map: dict[str, int]
) -> tuple[str, int] | None:
    normalized = _strip_diacritics(raw)
    if normalized in citation_map:
        return normalized, citation_map[normalized]
    for key, target_id in citation_map.items():
        if len(key) >= 6 and (
            normalized.startswith(key + "/") or key.startswith(normalized + "/")
        ):
            return key, target_id
    return None


def inject_document_links(html: str, citation_map: dict[str, int]) -> str:
    if not citation_map:
        return html

    refs = _extract_raw_references(html)
    replacements: list[tuple[tuple[int, int], str]] = []
    seen_positions: set[int] = set()

    for raw, start, end in refs:
        if start in seen_positions:
            continue
        match = _best_reference_match(raw, citation_map)
        if match:
            normalized, target_id = match
            seen_positions.add(start)
            replacements.append(
                (
                    (start, end),
                    f'<a href="/documents/{target_id}" class="doc-ref-link" title="{raw}">{raw}</a>',
                )
            )

    result = list(html)
    offset = 0
    for (start, end), replacement in sorted(replacements, key=lambda x: x[0][0]):
        for i in range(end - 1, start - 1, -1):
            if i < len(result):
                result.pop(i)
        for i, ch in enumerate(replacement):
            result.insert(start + i, ch)
        offset += len(replacement) - (end - start)

    return "".join(result)
