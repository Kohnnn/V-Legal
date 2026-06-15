from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .corpus import (
    append_jsonl_record,
    emit_canonical_document,
    ensure_corpus_layout,
    load_jsonl_index,
    write_jsonl_records,
)
from .official_sources import fetch_source_snapshot
from .settings import get_settings


DEMUC_CODE_PATTERN = re.compile(r"Đề mục\s+([0-9.]+)", re.IGNORECASE)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"[ \t]+")
MULTILINE_PATTERN = re.compile(r"\n{3,}")
PHAPDIEN_MAIN_VIEW_URL = (
    "https://phapdien.moj.gov.vn/TraCuuPhapDien/MainBoPD.aspx#view=1&itemID={item_id}"
)
DOCUMENT_LIST_VIEW_URL = (
    "https://phapdien.moj.gov.vn/TraCuuPhapDien/MainBoPD.aspx#view=2&itemID={item_id}"
)
ATTACHMENT_EXTENSIONS = (".doc", ".docx", ".pdf", ".xls", ".xlsx")
STRUCTURAL_CLASS_PATTERN = re.compile(r"^p(?:Phan|Chuong|Muc|TieuMuc)$", re.IGNORECASE)


@dataclass(frozen=True)
class PhapDienBundle:
    zip_path: Path
    subjects: list[dict[str, Any]]
    topics: list[dict[str, Any]]
    tree_nodes: list[dict[str, Any]]
    demuc_html: dict[str, str]


class DemucHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict[str, Any]] = []
        self.blocks: list[dict[str, Any]] = []
        self.attachments: list[dict[str, str]] = []

    def _append_to_stack(self, value: str) -> None:
        for entry in self.stack:
            entry.setdefault("text_parts", []).append(value)

    def _append_to_matching_blocks(self, class_name: str, value: str) -> None:
        for entry in self.stack:
            if entry.get("attrs", {}).get("class") == class_name:
                entry.setdefault("text_parts", []).append(value)

    def _find_parent_block(self) -> dict[str, Any] | None:
        for entry in reversed(self.stack):
            if entry.get("tag") == "h3":
                return entry
            if entry.get("tag") == "p" and entry.get("attrs", {}).get("class"):
                return entry
        return None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attrs_dict = {key: value or "" for key, value in attrs}
        if normalized_tag == "br":
            self._append_to_stack("\n")
            return
        if normalized_tag == "p" and any(
            entry.get("attrs", {}).get("class") == "pNoiDung" for entry in self.stack
        ):
            self._append_to_matching_blocks("pNoiDung", "\n\n")
        self.stack.append(
            {
                "tag": normalized_tag,
                "attrs": attrs_dict,
                "text_parts": [],
                "links": [],
                "anchors": [],
            }
        )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br":
            self._append_to_stack("\n")

    def handle_data(self, data: str) -> None:
        if data:
            self._append_to_stack(data)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if not self.stack:
            return
        if self.stack[-1].get("tag") != normalized_tag:
            match_index = next(
                (
                    index
                    for index in range(len(self.stack) - 1, -1, -1)
                    if self.stack[index].get("tag") == normalized_tag
                ),
                -1,
            )
            if match_index == -1:
                return
            entry = self.stack.pop(match_index)
        else:
            entry = self.stack.pop()

        text = clean_fragment_text("".join(entry.get("text_parts", [])))
        attrs = entry.get("attrs", {})

        if normalized_tag == "a":
            href = attrs.get("href", "")
            anchor_name = attrs.get("name", "")
            if anchor_name and self.stack:
                self.stack[-1].setdefault("anchors", []).append(anchor_name)
            if href and text:
                link = {"href": href, "text": text}
                parent_block = self._find_parent_block()
                if parent_block:
                    parent_block.setdefault("links", []).append(link)
                elif href.lower().endswith(ATTACHMENT_EXTENSIONS):
                    self.attachments.append(link)
            return

        if normalized_tag == "h3" and text:
            self.blocks.append(
                {
                    "kind": "title",
                    "text": text,
                    "anchors": entry.get("anchors", []),
                    "links": entry.get("links", []),
                }
            )
            return

        if normalized_tag != "p" or not text:
            return

        class_name = attrs.get("class", "")
        if not class_name:
            return

        self.blocks.append(
            {
                "kind": class_name,
                "text": text,
                "anchors": entry.get("anchors", []),
                "links": entry.get("links", []),
            }
        )


def clean_fragment_text(value: str) -> str:
    text = value.replace("\xa0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = WHITESPACE_PATTERN.sub(" ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = MULTILINE_PATTERN.sub("\n\n", text)
    return text.strip()


def strip_html(value: str) -> str:
    return clean_fragment_text(HTML_TAG_PATTERN.sub(" ", value))


def extract_js_array(script_text: str, variable_name: str) -> list[dict[str, Any]]:
    token = f"var {variable_name}"
    start = script_text.find(token)
    if start == -1:
        raise RuntimeError(f"Could not locate {variable_name} in Phap dien bundle")
    array_start = script_text.find("[", start)
    if array_start == -1:
        raise RuntimeError(f"Could not locate array start for {variable_name}")

    depth = 0
    in_string = False
    escape = False
    for index in range(array_start, len(script_text)):
        char = script_text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "[":
            depth += 1
            continue
        if char == "]":
            depth -= 1
            if depth == 0:
                payload = script_text[array_start : index + 1]
                return json.loads(payload)
    raise RuntimeError(f"Could not parse JSON array for {variable_name}")


def extract_bundle_snapshot(*, timeout: int = 120) -> PhapDienBundle:
    settings = get_settings()
    snapshot = fetch_source_snapshot(
        source_system="phapdien",
        source_document_id="ebook",
        source_url=settings.phapdien_ebook_url,
        timeout=timeout,
    )
    paths = ensure_corpus_layout()
    extract_root = paths.raw_root / "phapdien" / "ebook_extracted"
    extract_root.mkdir(parents=True, exist_ok=True)

    demuc_html: dict[str, str] = {}
    with zipfile.ZipFile(snapshot.path) as archive:
        json_text = archive.read("jsonData.js").decode("utf-8-sig", errors="ignore")
        subjects = extract_js_array(json_text, "jdChuDe")
        topics = extract_js_array(json_text, "jdDeMuc")
        tree_nodes = extract_js_array(json_text, "jdAllTree")

        (extract_root / "jsonData.js").write_text(json_text, encoding="utf-8")
        (extract_root / "subjects.json").write_text(
            json.dumps(subjects, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (extract_root / "topics.json").write_text(
            json.dumps(topics, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (extract_root / "tree_nodes.json").write_text(
            json.dumps(tree_nodes, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        for name in archive.namelist():
            if not name.startswith("demuc/") or not name.endswith(".html"):
                continue
            topic_id = Path(name).stem.lower()
            html = archive.read(name).decode("utf-8-sig", errors="ignore")
            demuc_html[topic_id] = html

    append_jsonl_record(
        paths.source_runs_manifest,
        {
            "kind": "phapdien_ebook_extracted",
            "zip_path": snapshot.path.relative_to(paths.root).as_posix(),
            "subjects_count": len(subjects),
            "topics_count": len(topics),
            "tree_nodes_count": len(tree_nodes),
            "demuc_html_count": len(demuc_html),
        },
    )
    return PhapDienBundle(
        zip_path=snapshot.path,
        subjects=subjects,
        topics=topics,
        tree_nodes=tree_nodes,
        demuc_html=demuc_html,
    )


def parse_demuc_html(
    html: str,
) -> tuple[str, list[dict[str, Any]], list[dict[str, str]]]:
    parser = DemucHTMLParser()
    parser.feed(html)
    title = ""
    for block in parser.blocks:
        if block["kind"] == "title":
            title = block["text"]
            break
    return title, parser.blocks, parser.attachments


def build_phapdien_markdown_content(blocks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        kind = block["kind"]
        text = block["text"]
        if kind == "title":
            index += 1
            continue

        if STRUCTURAL_CLASS_PATTERN.match(kind):
            combined_text = text
            if (
                kind == "pChuong"
                and index + 1 < len(blocks)
                and blocks[index + 1]["kind"] == "pChuong"
                and not blocks[index + 1]["text"].startswith("Chương")
            ):
                combined_text = f"{text} {blocks[index + 1]['text']}".strip()
                index += 1
            lines.extend([combined_text, ""])
        elif kind == "pDieu":
            lines.extend([text, ""])
        elif kind == "pGhiChu":
            lines.extend([f"Nguồn VBPL: {text}", ""])
        elif kind == "pNoiDung":
            normalized_text = text.replace("\n\n", "\n\n")
            lines.extend([normalized_text, ""])
        elif kind == "pChiDan":
            lines.extend([f"Liên quan pháp điển: {text}", ""])
        else:
            lines.extend([text, ""])
        index += 1
    return clean_fragment_text("\n".join(lines)).replace("\n", "\n")


def extract_demuc_code(title_text: str) -> str:
    match = DEMUC_CODE_PATTERN.search(title_text)
    if not match:
        return ""
    return match.group(1)


def build_phapdien_record(
    *,
    subject: dict[str, Any],
    topic: dict[str, Any],
    tree_nodes: list[dict[str, Any]],
    html: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    title_text, blocks, attachments = parse_demuc_html(html)
    demuc_code = extract_demuc_code(title_text)
    topic_title = title_text
    if demuc_code:
        topic_title = title_text.split("\n")[-1].strip() or title_text
    topic_source_url = PHAPDIEN_MAIN_VIEW_URL.format(item_id=topic["Value"])
    tree_node_count = len(tree_nodes)
    record = {
        "title": topic_title or topic["Text"],
        "document_number": demuc_code,
        "url": topic_source_url,
        "legal_type": "Đề mục pháp điển",
        "legal_sectors": subject["Text"],
        "issuing_authority": "Bộ Tư pháp",
        "issuance_date": "",
        "signers": "",
        "content": build_phapdien_markdown_content(blocks),
        "source": topic_source_url,
        "text_source": "html",
        "status": "codified",
        "scope": "phapdien",
        "attachments": [attachment["href"] for attachment in attachments],
        "phapdien_topics": [subject["Text"], topic["Text"]],
    }
    extra_manifest = {
        "subject_id": subject["Value"],
        "subject_name": subject["Text"],
        "topic_id": topic["Value"],
        "topic_name": topic["Text"],
        "document_list_url": DOCUMENT_LIST_VIEW_URL.format(item_id=topic["Value"]),
        "tree_node_count": tree_node_count,
        "attachment_count": len(attachments),
    }
    return record, extra_manifest


def _remove_manifest_artifacts(paths, entry: dict[str, Any]) -> None:
    for key in ("markdown_path", "raw_path", "sidecar_path"):
        value = entry.get(key)
        if not value:
            continue
        path = paths.root / value
        if path.exists():
            path.unlink()


def import_phapdien_corpus(
    *, limit: int | None = None, topic_ids: set[str] | None = None, timeout: int = 120
) -> dict[str, Any]:
    paths = ensure_corpus_layout()
    bundle = extract_bundle_snapshot(timeout=timeout)
    manifest_index = load_jsonl_index(paths.documents_manifest)

    subject_index = {item["Value"].lower(): item for item in bundle.subjects}
    tree_by_topic: dict[str, list[dict[str, Any]]] = {}
    for node in bundle.tree_nodes:
        tree_by_topic.setdefault(node["DeMucID"].lower(), []).append(node)

    exported = 0
    for topic in sorted(
        bundle.topics, key=lambda item: (item.get("ChuDe", ""), item.get("STT", ""))
    ):
        topic_id = str(topic["Value"]).lower()
        if topic_ids and topic_id not in topic_ids:
            continue
        html = bundle.demuc_html.get(topic_id)
        if not html:
            continue
        subject = subject_index.get(str(topic.get("ChuDe", "")).lower())
        if not subject:
            continue
        tree_nodes = tree_by_topic.get(topic_id, [])
        record, extra_manifest = build_phapdien_record(
            subject=subject,
            topic=topic,
            tree_nodes=tree_nodes,
            html=html,
        )
        manifest_entry = emit_canonical_document(
            record,
            source_system="phapdien",
            source_document_id=topic["Value"],
            raw_snapshot=html,
            raw_snapshot_extension=".html",
            source_url=record["url"],
            document_layer="phapdien",
            trust_level="official_primary",
        )
        stale_ids = [
            canonical_id
            for canonical_id, existing in manifest_index.items()
            if existing.get("document_layer") == "phapdien"
            and str(existing.get("source_document_id") or "").lower() == topic_id
            and canonical_id != manifest_entry["canonical_id"]
        ]
        for stale_id in stale_ids:
            _remove_manifest_artifacts(paths, manifest_index[stale_id])
            del manifest_index[stale_id]
        manifest_index[manifest_entry["canonical_id"]] = {
            **manifest_entry,
            **extra_manifest,
        }
        exported += 1
        if exported % 25 == 0:
            print(f"Exported {exported} Phap dien topic markdown files...")
        if limit is not None and exported >= limit:
            break

    write_jsonl_records(
        paths.documents_manifest,
        sorted(manifest_index.values(), key=lambda item: item["canonical_id"]),
    )
    append_jsonl_record(
        paths.source_runs_manifest,
        {
            "kind": "phapdien_import_finished",
            "exported_count": exported,
            "subjects_count": len(bundle.subjects),
            "topics_count": len(bundle.topics),
            "tree_nodes_count": len(bundle.tree_nodes),
            "zip_path": bundle.zip_path.relative_to(paths.root).as_posix(),
        },
    )
    return {
        "exported_count": exported,
        "subjects_count": len(bundle.subjects),
        "topics_count": len(bundle.topics),
        "tree_nodes_count": len(bundle.tree_nodes),
    }
