# PDF OCR Strategy

## Goal

Convert official Vietnamese law PDFs into canonical markdown that follows the repository schema:

- preserve legal wording faithfully
- recover legal structure such as `Phần`, `Chương`, `Mục`, `Điều`, khoản, and điểm
- keep provenance explicit
- support vectorless RAG from markdown-derived SQLite indexes

## Key Principle

Do not OCR blindly.

The pipeline should prefer:

1. direct PDF text extraction when the PDF is digital-born
2. layout-aware OCR when the PDF is image-based or low-yield
3. optional AI repair only after deterministic OCR and structure mapping

## Recommended Stack

## Best Overall Fit

Recommended stack for Vietnamese government-law PDFs:

- `PaddleOCR` for OCR and layout parsing
- specifically `PP-OCRv5` plus `PP-StructureV3`
- optional `VietOCR` for line-level Vietnamese recognition repair on low-confidence spans

Why:

- strong multilingual OCR support
- explicit document parsing support with structured `Markdown` and `JSON` output
- designed for irregular scanned documents and document-layout scenarios
- a better fit for legal PDFs than plain OCR engines that only return lines

## Strong Alternative

- `docTR`

Why:

- clean nested OCR output structure
- good document OCR ergonomics
- suitable fallback when PaddleOCR is not available

Tradeoff:

- less directly aligned to the repo's desired markdown/document-structure workflow than PaddleOCR's document-parsing stack

## Vietnamese Recognition Specialist

- `VietOCR`

Why:

- focused on Vietnamese text recognition
- useful after detection/layout segmentation when specific line recognition quality matters

Tradeoff:

- not a full document-layout parser by itself
- best used as a secondary recognizer, not the whole document pipeline

## Baseline / Fallback Only

- `Tesseract` with Vietnamese language data
- `OCRmyPDF` as a wrapper around Tesseract

Why not primary:

- weaker layout understanding
- weaker legal-structure recovery
- more manual cleanup needed for article/clause mapping

## Recommended Order Of Operations

1. try direct extraction from the PDF
2. if extraction is empty or low-quality, run layout-aware OCR
3. normalize OCR text
4. map OCR text into the markdown schema deterministically
5. optionally run AI structure reinforcement on low-confidence outputs

## Direct Extraction Before OCR

Try these first for digital-born PDFs:

- `PyMuPDF`
- `pypdf`
- `pdfplumber`
- `pdftotext`

These often work well for official government PDFs that contain embedded text instead of scanned page images.

## Structure Mapping Rules

OCR output should be mapped into markdown using deterministic legal-text rules.

Headings:

- `##` for `Phần`
- `###` for `Chương`
- `####` for `Mục`
- `#####` for `Điều`

Keep these literal when present:

- authority block
- motto block
- number block
- `Căn cứ ...` preamble
- enactment line such as `QUYẾT ĐỊNH:` or `NGHỊ QUYẾT:`
- `Nơi nhận`
- signature lines

Clauses and points stay as plain lines:

- `1. ...`
- `a) ...`

## Where AI Helps

AI should not replace canonical legal text.

Best use after OCR:

- repair noisy low-confidence spans
- infer likely headings from damaged scans
- recover reading order when OCR/layout engines disagree
- produce sidecar structure candidates for review

## When A Dedicated OCR LLM Is Actually Needed

You do **not** need a dedicated OCR LLM for every PDF.

Use this order:

1. direct PDF extraction
2. deterministic OCR
3. deterministic legal-structure mapping
4. OCR LLM only if corruption remains materially high

For this repo, a dedicated OCR LLM becomes justified when:

- scan-based PDFs still have many corrupted legal tokens after deterministic correction
- article and chapter recovery is incomplete or unstable
- Vietnamese diacritics are degraded enough to hurt retrieval or legal reading
- page headers or reading order still pollute the canonical markdown heavily

If OCR output is already structurally usable and only needs light cleanup, a dedicated OCR LLM is optional, not required.

## MiniMax Without Image Support

MiniMax M2.7 not having image recognition is not a blocker for this repo.

Use this split:

1. `PyMuPDF` or `pypdf` for embedded text when possible
2. `PaddleOCR` in the dedicated OCR runtime for scanned/image PDFs
3. MiniMax M2.7 on the extracted OCR text only

What MiniMax should do:

- repair Vietnamese legal phrasing
- restore diacritics where context makes them obvious
- repair headings like `Chương`, `Điều`, `Mục`, `Phần`
- preserve numbering and legal structure
- return corrected text or corrected structural hints, not rewritten law text

What MiniMax should not do:

- infer unreadable text that is not supported by OCR evidence
- replace provenance
- become the primary OCR engine

## Current Recommendation For This Repo

Short-term:

- keep the importer deterministic
- queue PDF-backed records for OCR
- map OCR text into markdown with local regex and section rules

Preferred future install:

- `PaddleOCR`
- `VietOCR`
- one direct-PDF text extractor such as `PyMuPDF`

## Current Repo Support

The repo now provides:

- `scripts/build_pdf_ocr_queue.py`
- `scripts/preview_pdf_ocr_mapping.py`
- `scripts/apply_pdf_ocr_text.py`
- `scripts/process_pdf_attachments.py`

These let you:

- discover which corpus records need OCR
- inspect the recommended backend per record
- preview how OCR text maps into the markdown schema
- apply OCR text back into a canonical markdown document
- run a hybrid direct-extract plus OCR fallback flow on official PDF attachments

## Runtime Separation On Windows

For this repo, the practical Windows setup is:

- main app and corpus pipeline on Python `3.14`
- dedicated OCR runtime on Python `3.13` in `.venv-ocr/`

Reason:

- `paddleocr` can install on the app environment,
- but `paddlepaddle` CPU wheels are currently available for `cp312` and `cp313`, not `cp314`

So the repo uses a dedicated OCR subprocess environment for scan-based PDF extraction while keeping the main app runtime current.

## Practical Recommendation

For your law corpus, the best production path is:

1. `PyMuPDF` or `pdfplumber` for embedded-text PDFs
2. `PaddleOCR PP-StructureV3` for scanned/image PDFs
3. `VietOCR` only where Vietnamese line recognition still needs repair
4. Minimax or another LLM only as a sidecar structure-repair pass for low-confidence cases
