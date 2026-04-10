from __future__ import annotations

import re
import sqlite3
from html import escape

from .taxonomy import normalize_ascii


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
ARTICLE_PATTERN = re.compile(r"^((?:Điều|Dieu)\s+\d+[A-Za-z0-9\-./]*)", re.IGNORECASE)
ARTICLE_LINE_PATTERN = re.compile(
    r"^((?:Điều|Dieu)\s+\d+[A-Za-z0-9\-./]*)(?:[.:]\s*(.*))?$",
    re.IGNORECASE,
)
SECTION_PATTERN = re.compile(
    r"^((?:Mục|Muc)\s+[IVXLC0-9A-Za-z\-./]+.*)$", re.IGNORECASE
)
CHAPTER_PATTERN = re.compile(
    r"^((?:Chương|Chuong)\s+[IVXLC0-9A-Za-z\-./]+.*)$", re.IGNORECASE
)
PART_PATTERN = re.compile(r"^((?:Phần|Phan)\s+[IVXLC0-9A-Za-z\-./]+.*)$", re.IGNORECASE)
ROMAN_HEADING_PATTERN = re.compile(r"^([IVXLC]+)\.\s+(.+)$", re.IGNORECASE)
CLAUSE_PATTERN = re.compile(r"^(\d+\.)\s+(.*)$")
POINT_PATTERN = re.compile(r"^([a-zđ]\))\s+(.*)$", re.IGNORECASE)
DASH_PATTERN = re.compile(r"^([-–•])\s+(.*)$")
ANNEX_HEADING_PATTERN = re.compile(
    r"^(PHỤ LỤC|PHU LUC|QUY TRÌNH|QUY TRINH|QUY CHẾ|QUY CHE|DANH MỤC|DANH MUC|BIỂU MẪU|BIEU MAU|MẪU SỐ|MAU SO)\b",
    re.IGNORECASE,
)
ENDMATTER_PATTERN = re.compile(
    r"^(Nơi nhận|Noi nhan|KT\.|TM\.|TL\.|Q\.)\b",
    re.IGNORECASE,
)
ENDMATTER_CONTINUATION_PATTERN = re.compile(
    r"^(?:Điều|Dieu)\s+\d+\s*;",
    re.IGNORECASE,
)
ANNEX_META_PATTERN = re.compile(r"^([^:]{2,60}):\s*(.+)$")
SIGNATURE_NAME_PATTERN = re.compile(
    r"^(?P<title>.+?)\s+(?P<name>(?:[A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+){1,5}))$"
)
LEGAL_TYPE_PATTERN = re.compile(
    r"^(LUẬT|BỘ LUẬT|PHÁP LỆNH|LỆNH|NGHỊ QUYẾT|NGHỊ ĐỊNH|QUYẾT ĐỊNH|CHỈ THỊ|THÔNG TƯ(?: LIÊN TỊCH)?|THÔNG BÁO|THÔNG TRI|HƯỚNG DẪN|KẾ HOẠCH|KẾT LUẬN|QUY CHẾ(?: PHỐI HỢP)?|BÁO CÁO)$",
    re.IGNORECASE,
)
ENACTMENT_LINE_PATTERN = re.compile(
    r"^(LUẬT|NGHỊ ĐỊNH|NGHỊ QUYẾT|QUYẾT ĐỊNH|CHỈ THỊ|THÔNG TƯ|PHÁP LỆNH|LỆNH)\s*:?$",
    re.IGNORECASE,
)
NUMBER_BLOCK_PATTERN = re.compile(
    r"^(Số|So|Luật số|Nghị quyết số|Quyết định số|Thông tư số|Pháp lệnh số|Lệnh số)\b",
    re.IGNORECASE,
)
MOTTO_PATTERN = re.compile(
    r"^(.*?CỘNG H[ÒO]A XÃ HỘI CHỦ NGHĨA VIỆT NAM)\s+(Độc lập\s*-\s*Tự do\s*-\s*Hạnh phúc.*)$",
    re.IGNORECASE,
)
STAR_RUN_PATTERN = re.compile(r"\*{3,}")
TABLE_SEPARATOR_PATTERN = re.compile(r"^[|:\-\s]+$")
DISPLAY_HEADING_BREAK_PATTERN = re.compile(
    r"\s+(?=(PHẦN\s+[IVXLC0-9A-Za-z\-./]+|Phần\s+[IVXLC0-9A-Za-z\-./]+|CHƯƠNG\s+[IVXLC0-9A-Za-z\-./]+|Chương\s+[IVXLC0-9A-Za-z\-./]+|MỤC\s+[IVXLC0-9A-Za-z\-./]+|Mục\s+[IVXLC0-9A-Za-z\-./]+|Điều\s+\d+[A-Za-z0-9\-./]*[.:]?|RA\s+SẮC\s+LỆNH:|QUYẾT\s+ĐỊNH:|NGHỊ\s+QUYẾT:|THÔNG\s+TƯ:))"
)

PROMULGATOR_KEYWORDS = (
    "QUỐC HỘI",
    "ỦY BAN THƯỜNG VỤ QUỐC HỘI",
    "CHÍNH PHỦ",
    "THỦ TƯỚNG CHÍNH PHỦ",
    "BỘ TRƯỞNG",
    "LIÊN BỘ",
    "ỦY BAN NHÂN DÂN",
    "HỘI ĐỒNG NHÂN DÂN",
    "CHỦ TỊCH NƯỚC",
    "TÒA ÁN NHÂN DÂN TỐI CAO",
    "VIỆN KIỂM SÁT NHÂN DÂN TỐI CAO",
)

PREAMBLE_PREFIXES = (
    "can cu",
    "chieu theo",
    "xet",
    "theo de nghi",
    "sau khi",
)

ANNEX_META_LABELS = {
    "ma so tthc",
    "quy trinh thuc hien",
    "thoi han giai quyet tthc",
    "co quan thuc hien",
    "doi tuong thuc hien",
    "cach thuc thuc hien",
    "phi le phi",
}

SIGNATURE_TITLE_SUFFIXES = (
    "PHÓ CHỦ TỊCH",
    "CHỦ TỊCH",
    "PHÓ GIÁM ĐỐC",
    "GIÁM ĐỐC",
    "PHÓ TỔNG GIÁM ĐỐC",
    "TỔNG GIÁM ĐỐC",
    "THỨ TRƯỞNG",
    "BỘ TRƯỞNG",
)
EMBEDDED_PREAMBLE_PATTERN = re.compile(
    r"\s+(Căn cứ|Chiếu theo|Xét|Theo đề nghị|Sau khi|CAN CU|CHIEU THEO|XET|THEO DE NGHI|SAU KHI)\b",
    re.IGNORECASE,
)
EMBEDDED_ENACTMENT_PATTERN = re.compile(
    r"\s+(RA SẮC LỆNH:|RA SAC LENH:|QUYẾT ĐỊNH:|QUYET DINH:|NGHỊ QUYẾT:|NGHI QUYET:|THÔNG TƯ:|THONG TU:|LUẬT:|LUAT:)\b",
    re.IGNORECASE,
)

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


def clean_display_line(value: str) -> str:
    cleaned = STAR_RUN_PATTERN.sub("", value)
    cleaned = re.sub(r"\s*\|\s*", " | ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -\t")
    return cleaned.strip()


def split_display_paragraphs(markdown_content: str) -> list[str]:
    normalized_content = DISPLAY_HEADING_BREAK_PATTERN.sub(
        "\n\n", markdown_content.replace("\r\n", "\n").replace("\r", "\n")
    )
    paragraphs: list[str] = []
    current: list[str] = []
    for raw_line in normalized_content.split("\n"):
        if raw_line.strip():
            current.append(raw_line.rstrip())
            continue
        if current:
            paragraphs.append("\n".join(current).strip())
            current = []
    if current:
        paragraphs.append("\n".join(current).strip())
    return paragraphs


def split_official_pair(value: str) -> tuple[str, str] | None:
    cleaned = clean_display_line(value)
    if "|" not in cleaned:
        return None
    left, right = [part.strip() for part in cleaned.split("|", 1)]
    if not left or not right:
        return None
    return left, right


def split_motto(value: str) -> tuple[str, str | None]:
    cleaned = clean_display_line(value)
    if "Độc lập" in cleaned:
        title, subtitle = cleaned.split("Độc lập", 1)
        return title.strip(), f"Độc lập {subtitle.strip()}".strip()
    match = MOTTO_PATTERN.match(cleaned)
    if match:
        return match.group(1).strip(), clean_display_line(match.group(2))
    return cleaned, None


def is_legal_type_line(value: str) -> bool:
    return bool(LEGAL_TYPE_PATTERN.match(clean_display_line(value)))


def is_enactment_line(value: str) -> bool:
    cleaned = clean_display_line(value)
    if ENACTMENT_LINE_PATTERN.match(cleaned):
        return True
    normalized = normalize_ascii(cleaned).upper().rstrip(": ")
    return normalized in {
        "LUAT",
        "NGHI DINH",
        "NGHI QUYET",
        "QUYET DINH",
        "CHI THI",
        "THONG TU",
        "PHAP LENH",
        "LENH",
        "RA SAC LENH",
    }


def is_preamble_start(value: str) -> bool:
    lowered = normalize_ascii(clean_display_line(value)).lower()
    return lowered.startswith(PREAMBLE_PREFIXES)


def is_uppercaseish(value: str) -> bool:
    letters = [char for char in clean_display_line(value) if char.isalpha()]
    if not letters:
        return False
    uppercase_count = sum(1 for char in letters if char.isupper())
    return uppercase_count / len(letters) >= 0.72


def is_promulgator_line(value: str) -> bool:
    cleaned = clean_display_line(value)
    upper = cleaned.upper()
    return is_uppercaseish(cleaned) and any(
        keyword in upper for keyword in PROMULGATOR_KEYWORDS
    )


def is_endmatter_paragraph(value: str) -> bool:
    cleaned = clean_display_line(value)
    return bool(ENDMATTER_PATTERN.match(cleaned))


def is_annex_heading(value: str) -> bool:
    cleaned = clean_display_line(value)
    if parse_annex_meta_line(cleaned):
        return False
    return bool(ANNEX_HEADING_PATTERN.match(cleaned)) and len(cleaned.split()) >= 4


def is_endmatter_continuation(value: str) -> bool:
    cleaned = clean_display_line(value)
    if not cleaned:
        return False
    if is_endmatter_paragraph(cleaned):
        return True
    if ENDMATTER_CONTINUATION_PATTERN.match(cleaned):
        return True
    if "|" in cleaned:
        return True
    return is_uppercaseish(cleaned) and len(cleaned.split()) <= 14


def parse_annex_meta_line(value: str) -> tuple[str, str] | None:
    cleaned = clean_display_line(value)
    match = ANNEX_META_PATTERN.match(cleaned)
    if not match:
        return None
    label = match.group(1).strip()
    body = match.group(2).strip()
    if not body:
        return None
    normalized_label = normalize_ascii(label).lower()
    if normalized_label not in ANNEX_META_LABELS:
        return None
    return label, body


def split_preamble_clauses(value: str) -> list[str]:
    collapsed = clean_display_line(value)
    pieces = re.split(
        r"(?=(?:Căn cứ|Chiếu theo|Xét|Theo đề nghị|Sau khi|CAN CU|CHIEU THEO|XET|THEO DE NGHI|SAU KHI))",
        collapsed,
    )
    clauses = [piece.strip() for piece in pieces if piece.strip()]
    return clauses or [collapsed]


def split_embedded_preamble_paragraph(value: str) -> tuple[str, str | None]:
    cleaned = clean_display_line(value)
    match = EMBEDDED_PREAMBLE_PATTERN.search(cleaned)
    if not match:
        match = EMBEDDED_ENACTMENT_PATTERN.search(cleaned)
    if not match or match.start() < 48:
        return cleaned, None

    title_part = cleaned[: match.start()].strip(" ;:")
    preamble_part = cleaned[match.start() :].strip()
    if len(title_part.split()) < 4 or not preamble_part:
        return cleaned, None
    return title_part, preamble_part


def build_section_anchor_lookup(markdown_content: str) -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = {}
    for section in extract_sections(markdown_content):
        if section["section_type"] == "title":
            continue
        lookup.setdefault(section["label"], []).append(section["anchor"])
    return lookup


def consume_section_anchor(
    anchor_lookup: dict[str, list[str]], label: str
) -> str | None:
    anchors = anchor_lookup.get(label, [])
    if not anchors:
        return None
    return anchors.pop(0)


def render_lines_html(value: str) -> str:
    lines = [
        clean_display_line(line)
        for line in value.splitlines()
        if clean_display_line(line)
    ]
    return "<br>".join(escape(line) for line in lines)


def parse_table_block(value: str) -> tuple[list[str], list[list[str]]] | None:
    raw_lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(raw_lines) < 2:
        return None
    if not all(line.count("|") >= 2 for line in raw_lines[:2]):
        return None

    rows: list[list[str]] = []
    for line in raw_lines:
        if line.count("|") < 2:
            return None
        cells = [cell.strip() for cell in line.split("|")]
        while cells and not cells[0]:
            cells.pop(0)
        while cells and not cells[-1]:
            cells.pop()
        if len(cells) < 2:
            continue
        if all(TABLE_SEPARATOR_PATTERN.match(cell or "") for cell in cells):
            continue
        rows.append(cells)

    if len(rows) < 2:
        return None

    header = rows[0]
    body = [
        row for row in rows[1:] if len(row) == len(header) and any(cell for cell in row)
    ]
    if not body:
        return None
    return header, body


def render_table_block(value: str) -> str | None:
    parsed = parse_table_block(value)
    if not parsed:
        return None
    header, body = parsed
    html_parts = ['<div class="law-table-wrap"><table class="law-table"><thead><tr>']
    for cell in header:
        html_parts.append(f"<th>{escape(clean_display_line(cell))}</th>")
    html_parts.append("</tr></thead><tbody>")
    for row in body:
        html_parts.append("<tr>")
        for cell in row:
            html_parts.append(f"<td>{escape(clean_display_line(cell))}</td>")
        html_parts.append("</tr>")
    html_parts.append("</tbody></table></div>")
    return "".join(html_parts)


def consume_annex_meta_block(
    body_paragraphs: list[str], start_index: int
) -> tuple[list[tuple[str, str]], int]:
    items: list[tuple[str, str]] = []
    next_index = start_index
    while next_index < len(body_paragraphs):
        parsed = parse_annex_meta_line(body_paragraphs[next_index])
        if not parsed:
            break
        items.append(parsed)
        next_index += 1
    return items, next_index


def render_annex_meta_block(items: list[tuple[str, str]]) -> str:
    html_parts = ['<section class="law-annex-meta">']
    for label, value in items:
        html_parts.append('<div class="law-annex-meta__row">')
        html_parts.append(f'<dt class="law-annex-meta__label">{escape(label)}</dt>')
        html_parts.append(f'<dd class="law-annex-meta__value">{escape(value)}</dd>')
        html_parts.append("</div>")
    html_parts.append("</section>")
    return "".join(html_parts)


def consume_endmatter_block(
    body_paragraphs: list[str], start_index: int
) -> tuple[list[str], int]:
    consumed = [body_paragraphs[start_index]]
    next_index = start_index + 1
    while next_index < len(body_paragraphs):
        raw_paragraph = body_paragraphs[next_index]
        paragraph = clean_display_line(raw_paragraph)
        if not paragraph:
            break
        first_line = clean_display_line(raw_paragraph.splitlines()[0])
        if (
            parse_table_block(raw_paragraph)
            or is_annex_heading(paragraph)
            or is_enactment_line(paragraph)
        ):
            break
        detected = detect_section(first_line)
        if detected and not is_endmatter_continuation(paragraph):
            break
        if not is_endmatter_continuation(paragraph):
            break
        consumed.append(raw_paragraph)
        next_index += 1
    return consumed, next_index


def split_signature_title_lines(value: str) -> list[str]:
    cleaned = clean_display_line(value)
    upper = cleaned.upper()
    if upper.startswith(("KT.", "TM.", "TL.", "Q.")):
        for suffix in SIGNATURE_TITLE_SUFFIXES:
            if upper.endswith(suffix):
                split_at = len(cleaned) - len(suffix)
                prefix = cleaned[:split_at].strip()
                suffix_line = cleaned[split_at:].strip()
                if prefix and suffix_line and prefix != suffix_line:
                    return [prefix, suffix_line]
    return [cleaned]


def parse_signature_line(value: str) -> tuple[list[str], str | None]:
    cleaned = clean_display_line(value)
    match = SIGNATURE_NAME_PATTERN.match(cleaned)
    if not match:
        return split_signature_title_lines(cleaned), None
    title = match.group("title").strip()
    name = match.group("name").strip()
    return split_signature_title_lines(title), name


def render_endmatter_block(paragraphs: list[str]) -> str:
    lines = [
        clean_display_line(item) for item in paragraphs if clean_display_line(item)
    ]
    recipients: list[str] = []
    signature_lines: list[str] = []

    for line in lines:
        if "|" in line:
            left, right = [part.strip() for part in line.split("|", 1)]
            if left:
                recipients.append(left)
            if right:
                signature_lines.append(right)
            continue
        recipients.append(line)

    if len(recipients) >= 2 and normalize_ascii(recipients[0]).lower().startswith(
        "noi nhan"
    ):
        recipients = [f"{recipients[0]} {recipients[1]}", *recipients[2:]]

    html_parts = ['<section class="law-document__endmatter">']
    for line in recipients:
        html_parts.append(f'<p class="law-document__endmatter-line">{escape(line)}</p>')
    if signature_lines:
        html_parts.append('<div class="law-document__signature-block">')
        for line in signature_lines:
            title_lines, signer_name = parse_signature_line(line)
            for title_line in title_lines:
                html_parts.append(
                    f'<p class="law-document__signature-line">{escape(title_line)}</p>'
                )
            if signer_name:
                html_parts.append(
                    f'<p class="law-document__signature-name">{escape(signer_name)}</p>'
                )
        html_parts.append("</div>")
    html_parts.append("</section>")
    return "".join(html_parts)


def render_body_paragraph(value: str, *, variant: str = "body") -> str:
    lines = [
        clean_display_line(line)
        for line in value.splitlines()
        if clean_display_line(line)
    ]
    if not lines:
        return ""

    first_line = lines[0]
    remaining_lines = lines[1:]

    for pattern, css_class in (
        (CLAUSE_PATTERN, "law-clause"),
        (POINT_PATTERN, "law-point"),
        (DASH_PATTERN, "law-dash"),
    ):
        match = pattern.match(first_line)
        if match:
            body_lines = [match.group(2), *remaining_lines]
            body_html = "<br>".join(escape(line) for line in body_lines if line)
            return (
                f'<p class="{css_class}"><span class="{css_class}__label">'
                f"{escape(match.group(1))}</span><span>{body_html}</span></p>"
            )

    body_html = "<br>".join(escape(line) for line in lines)
    css_class = "law-article__lead" if variant == "lead" else "law-paragraph"
    return f'<p class="{css_class}">{body_html}</p>'


def render_section_badge(
    anchor: str | None,
    label: str,
    section_citation_counts: dict[str, int],
    section_citation_labels: dict[str, int],
) -> str:
    total = section_citation_counts.get(anchor or "", 0)
    if total <= 0:
        total = section_citation_labels.get(label, 0)
    if total <= 0:
        return ""
    label = f"{total} cross-ref" if total == 1 else f"{total} cross-refs"
    return (
        '<div class="law-section-meta">'
        f'<span class="law-ref-badge" data-section-anchor="{escape(anchor or "")}">{escape(label)}</span>'
        "</div>"
    )


def build_document_display_html(
    markdown_content: str,
    citation_map: dict[str, int] | None = None,
    section_citation_counts: dict[str, int] | None = None,
    section_citation_labels: dict[str, int] | None = None,
) -> str | None:
    paragraphs = split_display_paragraphs(markdown_content)
    if not paragraphs:
        return None

    citation_map = citation_map or {}
    section_citation_counts = section_citation_counts or {}
    section_citation_labels = section_citation_labels or {}
    anchor_lookup = build_section_anchor_lookup(markdown_content)
    header: dict[str, str | list[str] | None] = {
        "authority_left": None,
        "motto_title": None,
        "motto_subtitle": None,
        "number_left": None,
        "number_right": None,
        "legal_type": None,
        "promulgator": None,
        "title_lines": [],
    }
    preamble_clauses: list[str] = []
    intro_paragraphs: list[str] = []

    if paragraphs:
        first_paragraph_lines = [
            line for line in paragraphs[0].splitlines() if clean_display_line(line)
        ]
        consumed_header_lines = 0

        if first_paragraph_lines:
            authority_pair = split_official_pair(first_paragraph_lines[0])
            if authority_pair:
                header["authority_left"] = authority_pair[0]
                motto_title, motto_subtitle = split_motto(authority_pair[1])
                header["motto_title"] = motto_title
                header["motto_subtitle"] = motto_subtitle
                consumed_header_lines = 1

        if len(first_paragraph_lines) > consumed_header_lines:
            number_pair = split_official_pair(
                first_paragraph_lines[consumed_header_lines]
            )
            if number_pair and (
                NUMBER_BLOCK_PATTERN.match(number_pair[0])
                or "ngày" in number_pair[1].lower()
            ):
                header["number_left"] = number_pair[0]
                header["number_right"] = number_pair[1]
                consumed_header_lines += 1

        if consumed_header_lines:
            remaining_lines = [
                line
                for line in paragraphs[0].splitlines()[consumed_header_lines:]
                if line.strip()
            ]
            if remaining_lines:
                paragraphs[0] = "\n".join(remaining_lines)
            else:
                paragraphs.pop(0)

    index = 0
    if index < len(paragraphs) and not header["authority_left"]:
        authority_pair = split_official_pair(paragraphs[index])
        if authority_pair:
            header["authority_left"] = authority_pair[0]
            motto_title, motto_subtitle = split_motto(authority_pair[1])
            header["motto_title"] = motto_title
            header["motto_subtitle"] = motto_subtitle
            index += 1

    if index < len(paragraphs) and not header["number_left"]:
        number_pair = split_official_pair(paragraphs[index])
        if number_pair and (
            NUMBER_BLOCK_PATTERN.match(number_pair[0])
            or "ngày" in number_pair[1].lower()
        ):
            header["number_left"] = number_pair[0]
            header["number_right"] = number_pair[1]
            index += 1

    if index < len(paragraphs) and is_legal_type_line(paragraphs[index]):
        header["legal_type"] = clean_display_line(paragraphs[index]).upper()
        index += 1

    title_lines: list[str] = []
    while index < len(paragraphs):
        paragraph = clean_display_line(paragraphs[index])
        paragraph, embedded_preamble = split_embedded_preamble_paragraph(paragraph)
        if embedded_preamble:
            paragraphs[index] = paragraph
            paragraphs.insert(index + 1, embedded_preamble)
        first_line = clean_display_line(paragraphs[index].splitlines()[0])
        if (
            detect_section(first_line)
            or is_enactment_line(paragraph)
            or is_preamble_start(paragraph)
        ):
            break
        if title_lines and is_promulgator_line(paragraph):
            header["promulgator"] = paragraph
            index += 1
            break
        if not title_lines:
            title_lines.append(paragraph)
            index += 1
            continue
        if (
            is_uppercaseish(paragraph)
            and len(title_lines) < 2
            and len(paragraph.split()) >= 4
        ):
            title_lines.append(paragraph)
            index += 1
            continue
        break
    header["title_lines"] = title_lines

    while index < len(paragraphs):
        paragraph = clean_display_line(paragraphs[index])
        first_line = clean_display_line(paragraphs[index].splitlines()[0])
        if detect_section(first_line):
            break
        if is_enactment_line(paragraph):
            intro_paragraphs.append(paragraph.rstrip(":") + ":")
            index += 1
            break
        if is_preamble_start(paragraph):
            preamble_clauses.extend(split_preamble_clauses(paragraph))
        elif is_promulgator_line(paragraph) and not header["promulgator"]:
            header["promulgator"] = paragraph
        else:
            intro_paragraphs.append(paragraph)
        index += 1

    body_paragraphs = paragraphs[index:]
    has_display_scaffold = any(
        [
            header["authority_left"],
            header["number_left"],
            header["legal_type"],
            header["title_lines"],
            body_paragraphs,
        ]
    )
    if not has_display_scaffold:
        return None

    html_parts = ['<div class="law-document">']

    if header["authority_left"] or header["motto_title"]:
        html_parts.append('<header class="law-document__masthead">')
        if header["authority_left"]:
            html_parts.append(
                '<div class="law-document__authority">'
                f"<p>{escape(str(header['authority_left']))}</p>"
                "</div>"
            )
        if header["motto_title"]:
            html_parts.append('<div class="law-document__motto">')
            html_parts.append(
                f'<p class="law-document__motto-title">{escape(str(header["motto_title"]))}</p>'
            )
            if header["motto_subtitle"]:
                html_parts.append(
                    f'<p class="law-document__motto-subtitle">{escape(str(header["motto_subtitle"]))}</p>'
                )
            html_parts.append("</div>")
        html_parts.append("</header>")

    if header["number_left"] or header["number_right"]:
        html_parts.append('<div class="law-document__register-line">')
        if header["number_left"]:
            html_parts.append(
                f'<p class="law-document__register">{escape(str(header["number_left"]))}</p>'
            )
        if header["number_right"]:
            html_parts.append(
                f'<p class="law-document__date">{escape(str(header["number_right"]))}</p>'
            )
        html_parts.append("</div>")

    if header["legal_type"] or header["title_lines"] or header["promulgator"]:
        html_parts.append('<div class="law-document__title-block">')
        if header["legal_type"]:
            html_parts.append(
                f'<p class="law-document__legal-type">{escape(str(header["legal_type"]))}</p>'
            )
        for line in header["title_lines"] or []:
            html_parts.append(
                f'<h1 class="law-document__title">{escape(str(line))}</h1>'
            )
        if header["promulgator"]:
            html_parts.append(
                f'<p class="law-document__promulgator">{escape(str(header["promulgator"]))}</p>'
            )
        html_parts.append("</div>")

    if preamble_clauses or intro_paragraphs:
        html_parts.append('<section class="law-document__preamble">')
        for clause in preamble_clauses:
            html_parts.append(
                f'<p class="law-document__preamble-clause">{escape(clause)}</p>'
            )
        for paragraph in intro_paragraphs:
            css_class = (
                "law-document__enactment"
                if is_enactment_line(paragraph)
                else "law-document__preamble-copy"
            )
            html_parts.append(f'<p class="{css_class}">{escape(paragraph)}</p>')
        html_parts.append("</section>")

    html_parts.append('<div class="law-document__body">')
    current_article_open = False
    body_index = 0

    while body_index < len(body_paragraphs):
        raw_paragraph = body_paragraphs[body_index]
        paragraph = clean_display_line(raw_paragraph)
        if not paragraph:
            body_index += 1
            continue

        first_line = clean_display_line(raw_paragraph.splitlines()[0])
        detected = detect_section(first_line)
        article_match = ARTICLE_LINE_PATTERN.match(first_line)

        if article_match:
            if current_article_open:
                html_parts.append("</article>")
            article_label = article_match.group(1).strip()
            article_anchor = consume_section_anchor(anchor_lookup, article_label)
            html_parts.append('<article class="law-article">')
            if article_anchor:
                html_parts.append(
                    f'<a id="{article_anchor}" class="anchor-target"></a>'
                )
            section_badge = render_section_badge(
                article_anchor,
                article_label,
                section_citation_counts,
                section_citation_labels,
            )
            html_parts.append(
                '<header class="law-article__header">'
                f'<h2 class="law-article__label">{escape(article_label)}</h2>'
                f"{section_badge}"
                "</header>"
            )
            lead_lines: list[str] = []
            if article_match.group(2):
                lead_lines.append(article_match.group(2).strip())
            lead_lines.extend(raw_paragraph.splitlines()[1:])
            lead_text = "\n".join(line for line in lead_lines if line.strip())
            if lead_text:
                html_parts.append(render_body_paragraph(lead_text, variant="lead"))
            current_article_open = True
            body_index += 1
            continue

        if detected and detected[0] in {"part", "chapter", "section", "heading"}:
            if current_article_open:
                html_parts.append("</article>")
                current_article_open = False
            label = detected[1]
            anchor = consume_section_anchor(anchor_lookup, label)
            subtitle = None
            if body_index + 1 < len(body_paragraphs):
                next_paragraph = clean_display_line(body_paragraphs[body_index + 1])
                next_first_line = clean_display_line(
                    body_paragraphs[body_index + 1].splitlines()[0]
                )
                if (
                    next_paragraph
                    and not detect_section(next_first_line)
                    and not is_enactment_line(next_paragraph)
                    and is_uppercaseish(next_paragraph)
                ):
                    subtitle = next_paragraph
                    body_index += 1
            html_parts.append(
                f'<section class="law-heading-block law-heading-block--{detected[0]}">'
            )
            if anchor:
                html_parts.append(f'<a id="{anchor}" class="anchor-target"></a>')
            section_badge = render_section_badge(
                anchor,
                label,
                section_citation_counts,
                section_citation_labels,
            )
            html_parts.append(
                f'<p class="law-heading-block__label">{escape(label)}</p>'
            )
            if subtitle:
                html_parts.append(
                    f'<h2 class="law-heading-block__title">{escape(subtitle)}</h2>'
                )
            if section_badge:
                html_parts.append(section_badge)
            html_parts.append("</section>")
            body_index += 1
            continue

        roman_heading_match = ROMAN_HEADING_PATTERN.match(first_line)
        if roman_heading_match and not current_article_open:
            html_parts.append(
                '<section class="law-heading-block law-heading-block--roman">'
                f'<h3 class="law-heading-block__title">{escape(paragraph)}</h3>'
                "</section>"
            )
            body_index += 1
            continue

        if current_article_open and is_endmatter_paragraph(paragraph):
            html_parts.append("</article>")
            current_article_open = False
            endmatter_paragraphs, next_index = consume_endmatter_block(
                body_paragraphs, body_index
            )
            html_parts.append(render_endmatter_block(endmatter_paragraphs))
            body_index = next_index
            continue

        if is_annex_heading(paragraph):
            if current_article_open:
                html_parts.append("</article>")
                current_article_open = False
            subtitle = None
            if body_index + 1 < len(body_paragraphs):
                next_paragraph = clean_display_line(body_paragraphs[body_index + 1])
                next_first_line = clean_display_line(
                    body_paragraphs[body_index + 1].splitlines()[0]
                )
                if (
                    next_paragraph
                    and not detect_section(next_first_line)
                    and not is_annex_heading(next_paragraph)
                    and not is_endmatter_paragraph(next_paragraph)
                    and not parse_table_block(body_paragraphs[body_index + 1])
                    and len(next_paragraph.split()) >= 4
                    and len(next_paragraph) <= 240
                ):
                    subtitle = next_paragraph
                    body_index += 1
            html_parts.append(
                '<section class="law-heading-block law-heading-block--annex">'
            )
            html_parts.append(
                f'<p class="law-heading-block__label">{escape(paragraph)}</p>'
            )
            if subtitle:
                html_parts.append(
                    f'<h2 class="law-heading-block__title">{escape(subtitle)}</h2>'
                )
            html_parts.append("</section>")
            body_index += 1
            continue

        annex_meta_items, next_index = consume_annex_meta_block(
            body_paragraphs, body_index
        )
        if annex_meta_items:
            html_parts.append(render_annex_meta_block(annex_meta_items))
            body_index = next_index
            continue

        table_html = render_table_block(raw_paragraph)
        if table_html:
            html_parts.append(table_html)
            body_index += 1
            continue

        if current_article_open:
            html_parts.append(render_body_paragraph(raw_paragraph))
        else:
            html_parts.append(
                f'<p class="law-document__intro-paragraph">{render_lines_html(raw_paragraph)}</p>'
            )
        body_index += 1

    if current_article_open:
        html_parts.append("</article>")

    html_parts.append("</div>")
    html_parts.append("</div>")
    rendered_html = "".join(html_parts)
    return inject_document_links(rendered_html, citation_map)


DOC_NUMBER_PATTERN_V2 = re.compile(
    r"\b([0-9]{1,4}[a-z]?(?:[/-][0-9]{2,4})?(?:[/-][A-Za-z0-9\u00c0-\u1ef9]*[A-Za-z\u00c0-\u1ef9][A-Za-z0-9\u00c0-\u1ef9]*)+)\b"
)
CONTEXTUAL_DOC_REFERENCE_PATTERN_V2 = re.compile(
    r"\b(?:Sắc lệnh|Pháp lệnh|Nghị định|Nghị quyết|Quyết định|Chỉ thị|Thông tư(?: liên tịch)?|Lệnh|Luật|Bộ luật)\s*số\s*([0-9]{1,4}(?:[/-][0-9]{2,4})?(?:[/-][A-Za-z0-9\u00c0-\u1ef9\-]+)?)\b",
    re.IGNORECASE,
)


def _extract_raw_references(text: str) -> list[tuple[str, int, int]]:
    refs = []
    for m in DOC_NUMBER_PATTERN_V2.finditer(text):
        refs.append((m.group(1), m.start(), m.end()))
    for m in CONTEXTUAL_DOC_REFERENCE_PATTERN_V2.finditer(text):
        refs.append((m.group(1), m.start(1), m.end(1)))
    refs.sort(key=lambda item: (item[1], -(item[2] - item[1])))
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
                    (
                        f'<a href="/documents/{target_id}" class="doc-ref-link" '
                        f'data-target-document-id="{target_id}" '
                        f'data-reference="{escape(raw)}" title="{raw}">{raw}</a>'
                    ),
                )
            )

    result = list(html)
    for (start, end), replacement in sorted(
        replacements, key=lambda item: item[0][0], reverse=True
    ):
        for i in range(end - 1, start - 1, -1):
            if i < len(result):
                result.pop(i)
        for i, ch in enumerate(replacement):
            result.insert(start + i, ch)

    return "".join(result)
