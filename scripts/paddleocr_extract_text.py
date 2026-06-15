from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import fitz
from paddleocr import PaddleOCR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run PaddleOCR in the dedicated OCR environment and emit extracted text as JSON."
    )
    parser.add_argument("--pdf-file", required=True, help="PDF file to OCR.")
    parser.add_argument(
        "--lang",
        default="vi",
        help="PaddleOCR language key. Default is vi.",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.5,
        help="PDF render scale for OCR. Default is 1.5.",
    )
    parser.add_argument(
        "--quality",
        default="fast",
        choices=["fast", "high"],
        help="OCR quality preset. 'fast' uses lighter models, 'high' uses stronger defaults.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Optional maximum number of leading pages to OCR.",
    )
    return parser.parse_args()


def sort_lines(result: dict) -> list[dict]:
    if not isinstance(result, dict):
        result = getattr(result, "json", None) or getattr(result, "res", None) or {}
    rec_boxes = result.get("rec_boxes")
    rec_texts = result.get("rec_texts") or []
    rec_scores = result.get("rec_scores") or []
    if not rec_texts and "res" in result and isinstance(result["res"], dict):
        return sort_lines(result["res"])
    if rec_boxes is None:
        return [
            {"text": text, "score": score, "x": 0.0, "y": float(index)}
            for index, (text, score) in enumerate(zip(rec_texts, rec_scores), start=1)
        ]

    items: list[dict] = []
    for box, text, score in zip(rec_boxes, rec_texts, rec_scores):
        if not text or not text.strip():
            continue
        if hasattr(box, "shape") and len(getattr(box, "shape", ())) == 1:
            xs = [float(box[0])]
            ys = [float(box[1])]
        else:
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
        items.append(
            {
                "text": text.strip(),
                "score": float(score),
                "x": min(xs),
                "y": min(ys),
            }
        )
    items.sort(key=lambda item: (round(item["y"] / 18), item["y"], item["x"]))
    return items


def render_pdf_page(
    pdf_path: Path, page_index: int, output_path: Path, scale: float
) -> None:
    document = fitz.open(pdf_path)
    page = document[page_index]
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    pixmap.save(output_path)
    document.close()


def main() -> None:
    args = parse_args()
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ.setdefault("FLAGS_use_mkldnn", "0")

    pdf_path = Path(args.pdf_file)
    document = fitz.open(pdf_path)
    page_count = len(document)
    document.close()
    page_limit = min(page_count, args.max_pages) if args.max_pages else page_count

    ocr_kwargs = {
        "lang": args.lang,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        "device": "cpu",
        "enable_hpi": False,
        "enable_mkldnn": False,
        "cpu_threads": 1,
    }
    if args.quality == "fast":
        ocr_kwargs.update(
            {
                "text_detection_model_name": "PP-OCRv5_mobile_det",
                "text_recognition_model_name": "latin_PP-OCRv5_mobile_rec",
            }
        )
    ocr = PaddleOCR(**ocr_kwargs)

    pages: list[dict] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        for page_index in range(page_limit):
            image_path = temp_root / f"page-{page_index + 1}.png"
            render_pdf_page(pdf_path, page_index, image_path, args.scale)
            result = ocr.predict(str(image_path))[0]
            lines = sort_lines(result)
            page_text = "\n".join(item["text"] for item in lines if item["text"])
            average_score = (
                sum(item["score"] for item in lines) / len(lines) if lines else 0.0
            )
            pages.append(
                {
                    "page_index": page_index + 1,
                    "line_count": len(lines),
                    "average_score": average_score,
                    "text": page_text,
                }
            )

    raw_text = "\n\n".join(page["text"] for page in pages if page["text"].strip())
    payload = {
        "backend": "paddleocr_subprocess",
        "page_count": page_count,
        "processed_page_count": page_limit,
        "pages": pages,
        "raw_text": raw_text,
    }
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
