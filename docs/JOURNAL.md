# Development Journal

## Session: Document-Handling Improvements (Validity, Provenance, Navigation)

**Date:** 2026-06-07
**Goal:** Improve how the app stores, surfaces, and navigates legal documents. Five slices (A-E), planned in `docs/IMPROVEMENT_PLAN.md`. Decisions: explicit frontmatter status (plus a clearly-labeled "referenced by newer documents" secondary signal, never an asserted validity), standalone backfill scripts, A+B verified before C/D/E.

### What Shipped

- **A - Legal validity status end-to-end.** The markdown schema already produced `status`/`effective_date`/`expiry_date` but the SQLite layer dropped them. Added the three columns (`SCHEMA`, the cheap startup `_ensure_document_columns`, and `import_documents`) plus `idx_documents_status`; `build_record_from_canonical_document` now reads them. The reader shows a validity badge (In force / Expired / Partially expired / Unknown), with "chưa đối chiếu" for bootstrap-sourced rows and effective/expiry dates when present. Archive cards show a status chip; the home page and `/api/search` gained a `status` filter. New `validity.py`; new `scripts/migrate_add_validity_columns.py` (idempotent, workspace-only, backfills from frontmatter).
- **B - OCR / low-confidence provenance banners.** `build_text_provenance_notice` drives a reader banner when `text_source` is `ocr`/`pdf`/`mixed` or `parse_confidence` is not `high`, pointing to the official source for verification.
- **C - Collapsible nested TOC + article deep-linking.** The outline now carries `section_type` + `depth` (`OUTLINE_DEPTHS`); the reader renders a collapsible tree (branch toggles at Phần/Chương depth) and a per-`Điều` "copy link" affordance that copies a deep link and updates the hash.
- **D - Body-level repeal/amend extraction.** `rebuild_relationship_graph` gained a second pass that scans a bounded body endmatter window (`_endmatter_window`) for repeal/amend clauses that live in "điều khoản thi hành" rather than the title. Confidence is downgraded one notch vs. title evidence, evidence text marks it as body-sourced, and a streaming cursor keeps memory bounded. Offline rebuild path only.
- **E - Lighter document projection.** Added `get_document_meta` (everything except `content`/`plain_content`) and repointed the metadata-only call sites (`/compare`, `/api/compare`, citation-preview source/target, compare-focus lookup). The reader body path keeps full `get_document`.

### Verification

- `uv run pytest` -> 29 passing (validity, body-relations, document-meta, outline-depth, plus the prior suites).
- `uv run python -m compileall src scripts` -> clean.
- Route smoke against `data/ui_test.sqlite`: validity badge, OCR notice, status filter, outline tree, and article anchor links confirmed in rendered HTML; compare routes work on the lighter projection. Citation-preview returns 404 only when no link exists between the pair (correct).
- `node --check static/app.js` + Jinja parse of all templates -> clean.

### Open Item (user action)

The validity columns are populated on import/rebuild. To backfill the existing
`~11.7 GB` workspace DB without a full rebuild: stop the dev server, then run
`uv run python scripts/migrate_add_validity_columns.py`. Most HF-bootstrap rows
stay `unknown` until official-source reconciliation provides a status; the reader
labels these honestly.

## Session: Search/Reader Correctness, Performance, And UX Pass

**Date:** 2026-06-05
**Goal:** Scale the prototype's search, reader, and citation logic to the real 153,926-document corpus, fix correctness bugs the larger corpus exposed, and add a focused test harness. Full plan and progress tracked in `docs/IMPROVEMENT_PLAN.md`.

### Context

The journal previously documented a `687`-document corpus. The workspace had grown to `153,926` canonical markdown files with an `~11.7 GB` derived SQLite. Code tuned for a `500`–`10k` prototype exposed a blocking bug and several per-request hotspots at this scale.

### What Shipped

- **P0 — blocking crash fixed.** `search.py` used `datetime.utcnow()` without importing `datetime`, so searching by document number (the identifier-first path, the most common legal lookup) raised `NameError` whenever it matched. Added the import (timezone-aware) and a regression test that reproduces the original failure.
- **Test harness.** Added `pytest` (dev dependency) and `tests/` with an in-memory fixture built from the real schema + import path. No test depends on the multi-GB DB. 17 tests passing.
- **P1 — search performance.**
  - Added `document_number_norm` column + `idx_documents_document_number_norm`, `idx_documents_issuing_authority`, `idx_documents_imported_at`.
  - Rewrote `search_identifier_documents` to be sargable (was wrapping the column in `REPLACE(UPPER(COALESCE(...)))` → full scan run twice).
  - `get_recent_documents` now orders by `imported_at` (the old `ORDER BY id DESC` was meaningless because `id` is a SHA256-derived hash).
  - Filter-free FTS counts no longer join the 150k-row base table.
  - Guarded the `documents_au` FTS trigger with `WHEN` so non-FTS column updates stop re-tokenizing every row.
  - Added `scripts/migrate_add_search_indexes.py` (idempotent, workspace-DB only, drops the heavy trigger during backfill, periodic WAL checkpoint).
- **P2 — reader per-request work.** Cached `extract_sections` by content (was parsed 3× per page) and `build_runtime_citation_support` by content hash (was firing one SQL query per ambiguous mention on every view). Removed a duplicate target relation-graph query from the citation-preview route. Startup now self-heals existing DBs with a cheap column-only migration without triggering expensive index builds.
- **P3 — correctness.** Added an internal-id collision guard (`InternalIdCollisionError`) so a 60-bit hash collision fails loudly instead of silently overwriting a different document. Relation `confidence` now reflects the resolver's decision margin instead of hardcoded `"high"`. Unified the two divergent document-number regex families into `doc_number.py` (one template, ASCII + Unicode variants). Guarded `resolve_appwrite_placeholders` so it never makes the blocking HTTP call on the local/skip-remote path.
- **P4 — UX + docs.** Track/untrack updates optimistically (no full page reload). Citation hover gained a 140ms open-debounce. `renderBrief` now escapes server-provided fields. Reader tabs gained `IntersectionObserver` scroll-spy. Replaced the legacy `bootstrap_appwrite_to_sqlite.py` empty-state with the markdown-first command. Updated README corpus snapshot.

### Verification

- `uv run pytest` → 17 passing.
- `uv run python -m compileall src scripts` → clean.
- FastAPI route smoke against `data/ui_test.sqlite`: `/`, `/health`, `/documents/{id}`, `/tracking`, `/compare/{a}/{b}`, `/api/search`, `/api/tracked` all return 200; identifier search returns results; track toggle works.
- `node --check static/app.js` and Jinja parse of all templates → clean.

### Migration Run Status (open item)

The `document_number_norm` backfill on the `~11.7 GB` workspace DB is only partially applied (~27k/153,926). It was throttled by the running dev server holding a concurrent connection, which blocks WAL checkpoints. The guarded `documents_au` trigger was restored on the live DB so it is not degraded. The backfill is a user action: stop the dev server, then run `uv run python scripts/migrate_add_search_indexes.py` (idempotent, resumes). Not to be run against OCI/production. Until it finishes, document-number search works for backfilled rows and degrades gracefully (no crash) for the rest.

## Session: Executable PDF OCR Runtime

**Date:** 2026-04-15
**Goal:** Move from a PDF OCR queue to a real executable extraction path by combining direct PDF text extraction in the main app environment with a dedicated PaddleOCR runtime for scan-only legal PDFs.

### What Shipped

- Added `pypdf` and `pymupdf` to the main project for direct PDF text extraction.
- Created a dedicated OCR environment at `.venv-ocr/` using Python `3.13` because `paddlepaddle` is not available for `cp314` on Windows.
- Installed in `.venv-ocr/`:
  - `paddleocr`
  - `paddlepaddle`
  - `pymupdf`
- Added `scripts/paddleocr_extract_text.py` to:
  - render PDF pages with `PyMuPDF`
  - run `PaddleOCR` with a CPU-friendly configuration
  - emit UTF-8 JSON containing page text and combined OCR text
- Updated `src/vlegal_prototype/pdf_ocr.py` to:
  - download official PDF attachments
  - try direct extraction first with `PyMuPDF` or `pypdf`
  - fall back automatically to the dedicated PaddleOCR environment when extraction stays empty or low-confidence
  - apply extracted text back into canonical markdown and sync the manifest
- Added `scripts/process_pdf_attachments.py` as the user-facing command for the hybrid PDF processor.
- Added legal-structure normalization rules so OCR lines like `Churong` and `Điu` map into `Chương` and `Điều` for better markdown structure.

### Verification

- Confirmed the Government Portal law PDF for `vn-issued-vpcp-216529` is image-based:
  - no embedded text on sampled pages
  - one large image per page
- Verified PaddleOCR worked in the dedicated `.venv-ocr` environment using:
  - `lang='vi'`
  - `PP-OCRv5_mobile_det`
  - `latin_PP-OCRv5_mobile_rec`
  - CPU mode with `enable_mkldnn=False`
- Ran `uv run python scripts/process_pdf_attachments.py --canonical-id vn-issued-vpcp-216529` successfully.
- Verified the canonical markdown file now contains OCR-derived body content and frontmatter updates:
  - `text_source: ocr`
  - `parse_confidence: medium`
- Rebuilt a temporary SQLite index and verified the OCR-upgraded document is imported from markdown correctly.

## Session: MiniMax Text-Only OCR Repair And Corpus Expansion

**Date:** 2026-04-15
**Goal:** Expand the markdown corpus substantially and add a MiniMax-based OCR repair path that works without image understanding by operating only on PaddleOCR text output.

### What Shipped

- Added `src/vlegal_prototype/minimax_text.py` with a MiniMax text-chat client and OCR repair workflow.
- Added `scripts/apply_minimax_ocr_correction.py` to run text-only MiniMax post-correction on OCR-backed legal documents.
- Added OCR quality assessment that decides whether an OCR LLM is:
  - `not_needed`
  - `optional`
  - `recommended`
- Added deterministic Vietnamese legal-domain OCR corrections before markdown mapping.

### Corpus Expansion

- Exported 300 Hugging Face bootstrap issued documents into canonical markdown.
- Imported the full official `Phap dien` ebook bundle:
  - `306` codified topic markdown files
  - `45` subjects
  - `69,398` tree nodes captured in raw extracted data
- Imported `80` Government Portal issued-document records across type groups:
  - laws / ordinances
  - decrees
  - decisions
  - circulars
- Rebuilt the main SQLite corpus from markdown.

### Current Corpus Counts

- `687` documents in SQLite
- by layer:
  - `381` issued
  - `306` phapdien
- by source system:
  - `301` `hf_bootstrap`
  - `306` `phapdien`
  - `80` `vanban_chinhphu`

### OCR LLM Decision

- For the current scanned Government Portal law, MiniMax post-correction is **recommended**.
- Conclusion for the architecture:
  - MiniMax image support is not required
  - PaddleOCR remains the image-to-text engine
  - MiniMax M2.7 is useful as a text-only repair stage after OCR on low-confidence scanned laws

## Session: PDF OCR Strategy And Mapping Scaffold

**Date:** 2026-04-15
**Goal:** Research OCR stacks suitable for Vietnamese government-law PDFs, document the best recommendation for this repo, and add a practical OCR queue plus markdown-mapping scaffold so PDF-backed corpus records can be upgraded later without changing the corpus contract.

### What Shipped

- Added `docs/PDF_OCR_STRATEGY.md` to document:
  - recommended OCR stack for Vietnamese legal PDFs
  - why `PaddleOCR + PP-StructureV3` is the primary recommendation
  - where `VietOCR`, `docTR`, and `Tesseract/OCRmyPDF` fit
  - how OCR output should map into the repository markdown schema
- Added `src/vlegal_prototype/pdf_ocr.py` to:
  - detect currently available PDF/OCR capabilities on the machine
  - recommend the best backend per PDF-backed corpus record
  - build a PDF OCR work queue from canonical markdown documents
  - map OCR text into legal markdown structure deterministically
  - apply OCR text back into an existing canonical markdown document and sync the manifest
- Added `scripts/build_pdf_ocr_queue.py` to emit:
  - `pdf_ocr_queue.jsonl`
  - `pdf_ocr_capabilities.json`
- Added `scripts/preview_pdf_ocr_mapping.py` to preview OCR-to-markdown conversion.
- Added `scripts/apply_pdf_ocr_text.py` to write OCR text back into a canonical record using the deterministic structure mapper.

### Environment Check

At the time of implementation, the local environment did not have the following tools installed:

- `tesseract`
- `ocrmypdf`
- `pdftotext`
- `PyMuPDF`
- `pypdf`
- `pdfplumber`
- `PaddleOCR`
- `VietOCR`
- `docTR`

The queue therefore recommends the target stack rather than executing OCR immediately.

### Verification

- `uv run python -m compileall src scripts`
- `uv run python scripts/build_pdf_ocr_queue.py`
- verified the queue identified the current PDF-backed Government Portal law record and recommended `paddleocr_ppstructure_plus_vietocr`
- ran the deterministic OCR text mapper on a legal-text sample and verified it emitted markdown headings for `Chương` and `Điều` while preserving clauses and endmatter

## Session: Government Portal Listing Importer

**Date:** 2026-04-15
**Goal:** Add a real importer for `vanban.chinhphu.vn` so the corpus can ingest official Government Portal issued-document listings into provisional markdown records and use those listings to backfill official provenance for existing issued files.

### What Shipped

- Added `src/vlegal_prototype/vncp.py` to:
  - fetch server-rendered Government Portal listing pages from `he-thong-van-ban`
  - parse list rows for `docid`, document number, issuance date, summary, and attachment links
  - fetch detail pages by `docid`
  - parse detail-page metadata such as document number, dates, type, issuer, signer, summary, and attached PDF links
  - emit provisional issued markdown records with `source_system = vanban_chinhphu`
  - backfill `official_source_*` fields into matching issued markdown records when a central issued record has no stronger official source yet
- Added `scripts/import_vncp_listing.py` to import listing rows from Government Portal buckets such as:
  - `typegroupid=3` for laws and ordinances
  - `typegroupid=4` for decrees
  - `typegroupid=5` for decisions
  - `typegroupid=6` for circulars
- Added Government Portal settings in `src/vlegal_prototype/settings.py`.

### Verification

- `uv run python -m compileall src scripts`
- `uv run python scripts/import_vncp_listing.py --typegroupid 3 --limit 1`
- `uv run python scripts/rebuild_sqlite_from_markdown.py --limit 5 --reset --skip-postprocess` with a temporary SQLite path
- Verified the imported record `vn-issued-vpcp-216529` contains:
  - `document_number: 150/2025/QH15`
  - `source_system: vanban_chinhphu`
  - `text_source: pdf`
  - the official Government Portal detail URL
  - the official attached PDF URL in markdown frontmatter and body
- Verified the rebuilt SQLite index exposes that imported Government Portal URL for retrieval and cross-checking.

### OCR LLM Decision

- Added document-level OCR LLM assessment into the OCR sidecar output.
- For the current scanned Government Portal law `vn-issued-vpcp-216529`, the assessment is:
  - `recommendation: recommended`
  - reason: substantial OCR corruption still remains after deterministic correction, especially in Vietnamese legal phrasing and heading repair
- Conclusion:
  - a dedicated OCR LLM is **not required for the whole pipeline**
  - but it **is recommended for low-confidence scanned laws like this one** after the deterministic OCR pass

## Session: VBPL Provenance Bridge From Phap Dien

**Date:** 2026-04-15
**Goal:** Strengthen official provenance for the issued-document markdown corpus even though direct `vbpl.vn` crawling is unreliable from this environment, by harvesting the official `vbpl.vn` links already embedded inside the imported `Phap dien` content.

### What Shipped

- Added `src/vlegal_prototype/vbpl.py` to:
  - parse official `vbpl.vn` links and metadata from `Phap dien` `Nguồn VBPL` reference blocks
  - build `vbpl_reference_mentions.jsonl`
  - build `vbpl_reference_documents.jsonl`
  - backfill `official_source_system`, `official_source_document_id`, and `official_source_url` into matching issued markdown files by exact normalized document number
  - sync those official-source fields back into `documents.jsonl`
- Added `scripts/backfill_vbpl_references.py` to run the harvest and backfill flow.
- Added targeted HF export support in `src/vlegal_prototype/hf_ingest.py` and `scripts/export_hf_markdown_corpus.py` via repeated `--document-id` flags.
- Updated `src/vlegal_prototype/corpus.py` so markdown frontmatter now supports optional official-source fields and SQLite rebuild prefers `official_source_url` for the document `url`.
- Updated `src/vlegal_prototype/phapdien.py` so re-importing a topic prunes stale legacy duplicate codified entries by `source_document_id`.

### Verification

- Located the HF bootstrap record for `55/2010/QH12` and exported it with `scripts/export_hf_markdown_corpus.py --document-id 25495`.
- Ran `uv run python scripts/backfill_vbpl_references.py --overwrite`.
- Verified the issued markdown file `vn-issued-hf-25495--55-2010-qh12.md` now contains:
  - `official_source_system: vbpl`
  - `official_source_document_id: 25495`
  - `official_source_url: https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=25495#Chuong_I_Dieu_1`
- Rebuilt a temporary SQLite index from markdown and verified the resulting document row exposes the official VBPL URL through the app-facing `url` field.

## Session: Official Phap Dien Connector

**Date:** 2026-04-15
**Goal:** Add the first real official-source corpus connector by importing the Ministry of Justice `Phap dien` ebook bundle into codified markdown files that can live alongside the issued-document corpus.

### What Shipped

- Added `VLEGAL_PHAPDIEN_EBOOK_URL` in `src/vlegal_prototype/settings.py` for the official ebook zip source.
- Added `src/vlegal_prototype/phapdien.py` to:
  - download the official `BoPhapDienDienTu.zip` bundle
  - extract `jdChuDe`, `jdDeMuc`, and `jdAllTree` from `jsonData.js`
  - preserve extracted subject, topic, and tree JSON under the corpus raw layer
  - parse `demuc/*.html` files from the ebook bundle
  - emit codified markdown files under `data/corpus/markdown/phapdien/`
  - record `Phap dien` manifests including subject, topic, and tree-node counts
- Added `scripts/import_phapdien_corpus.py` to import one or all `Phap dien` đề mục entries from the official ebook bundle.
- Updated `src/vlegal_prototype/corpus.py` so canonical IDs for the codified layer follow the documented shape `vn-phapdien-<item_id>`.
- Updated `src/vlegal_prototype/structure.py` so article labels that contain Vietnamese letters such as `NĐ` are parsed correctly instead of truncating at `Đ`.
- Updated `README.md` with the `Phap dien` import command and environment variable.

### Verification

- `uv run python -m compileall src scripts`
- `uv run python scripts/import_phapdien_corpus.py --limit 1 --topic-id 0cf69ad9-6f29-4ee4-8e16-2c3aa65c3a52`
- `uv run python scripts/rebuild_sqlite_from_markdown.py --limit 3 --reset --skip-postprocess` with a temporary SQLite path
- Verified outputs:
  - official ebook zip snapshot stored under `data/corpus/raw/phapdien/`
  - extracted `subjects.json`, `topics.json`, and `tree_nodes.json`
  - codified markdown file for `An toàn thực phẩm`
  - sidecar with chapter and article extraction plus citation mentions

## Session: Markdown Corpus Pipeline Implementation

**Date:** 2026-04-14
**Goal:** Implement the first runnable markdown-first corpus pipeline so the repo can export canonical markdown files, generate structure sidecars, rebuild SQLite from markdown, and store raw official-source snapshots locally.

### What Shipped

- Added corpus runtime settings in `src/vlegal_prototype/settings.py`:
  - `corpus_root`
  - optional AI schema sidecar settings
- Added source-stream helpers in `src/vlegal_prototype/hf_ingest.py` so exporters can access raw source payloads plus prepared records.
- Extended `src/vlegal_prototype/db.py` so imported documents can carry markdown-corpus metadata:
  - `canonical_id`
  - `source_system`
  - `source_document_id`
  - `document_layer`
  - `text_source`
  - `parse_confidence`
  - `corpus_path`
- Added `src/vlegal_prototype/corpus.py` to implement:
  - `data/corpus/` path management
  - canonical IDs and internal stable numeric IDs
  - YAML frontmatter rendering and parsing
  - markdown body emission from imported records
  - deterministic structure sidecars with section and citation extraction
  - markdown manifest helpers
  - markdown-to-SQLite record conversion
- Added `src/vlegal_prototype/ai_schema.py` to scaffold optional AI schema reinforcement via a provider hook:
  - disabled by default
  - only intended for low-confidence or OCR-style documents
- Added `src/vlegal_prototype/official_sources.py` to fetch and store raw official-source snapshots under the corpus raw layer.
- Added `scripts/export_hf_markdown_corpus.py` to export the Hugging Face bootstrap corpus into canonical markdown files plus manifests and sidecars.
- Added `scripts/rebuild_sqlite_from_markdown.py` to rebuild the local SQLite corpus from canonical markdown files.
- Added `scripts/snapshot_official_source.py` to store a raw source snapshot from `vbpl`, `vanban_chinhphu`, or `phapdien`.
- Updated `src/vlegal_prototype/structure.py` so markdown headings like `##### Dieu 1 ...` are classified as article sections instead of generic headings.
- Updated `README.md` with the new markdown-first scripts, commands, and environment variables.

### Verification

- `uv run python -m compileall src scripts`
- `uv run python scripts/export_hf_markdown_corpus.py --limit 2 --reset`
- `uv run python scripts/rebuild_sqlite_from_markdown.py --limit 2 --reset` with `VLEGAL_DATABASE_PATH=data/corpus/sqlite/test_markdown.sqlite`
- Verified generated outputs:
  - canonical markdown files under `data/corpus/markdown/`
  - structure sidecars under `data/corpus/manifests/sidecars/`
  - document manifest entries in `data/corpus/manifests/documents.jsonl`

## Session: Full Markdown Corpus Documentation Pivot

**Date:** 2026-04-14
**Goal:** Repoint the repo documentation from the focused-corpus plus Appwrite prototype toward a full local-first markdown corpus of Vietnamese law, and document when optional AI parsing is actually needed.

### What Shipped

- Rewrote `README.md` around the new target architecture:
  - markdown as the source of truth
  - SQLite as a derived local index
  - official-source provenance from `vbpl.vn`, `vanban.chinhphu.vn`, and `phapdien.moj.gov.vn`
  - Appwrite marked as transitional legacy rather than target architecture
- Added `docs/FULL_MARKDOWN_PORT_PLAN.md` to document the phase-by-phase plan for the markdown port.
- Added `docs/CORPUS_ARCHITECTURE.md` to define the local-first corpus layout, canonical layers, identity model, and SQLite's derived role.
- Added `docs/MARKDOWN_SCHEMA.md` to define canonical file paths, frontmatter, body structure, and fidelity rules.
- Added `docs/SOURCE_UPDATE_WORKFLOW.md` to document source precedence, official-source refresh, reconciliation rules, and self-update behavior.
- Added `docs/AI_PARSING_POLICY.md` to document that AI parsing is optional, not required for phase 1, and best reserved for OCR and malformed-document repair queues.
- Marked `docs/FOCUSED_CORPUS_SCOPE.md` as an archived direction note.
- Marked `docs/DEPLOYMENT_NETLIFY_APPWRITE.md` as an archived deployment path.

### Verification

- Reviewed the new docs and README for consistency with the current repo state.
- Confirmed the documentation now distinguishes clearly between:
  - current prototype implementation
  - target markdown-first architecture
  - legacy focused/Appwrite paths

## Session: Focused Economy Corpus Rebuild

**Date:** 2026-04-05
**Goal:** Re-scope the live OCI corpus around economy, finance, and industry-sector legal research, document the inclusion rules, and rebuild the production SQLite corpus from that focused scope.

### What Shipped

- Added `docs/FOCUSED_CORPUS_SCOPE.md` to document the focused corpus rules for:
  - economy, finance, banking, securities, tax, customs, investment, procurement, and trade
  - business-facing labor and commercial regulation
  - sector regulation such as real estate, land, construction, energy, transport, telecom, healthcare, pharmaceuticals, and agriculture
  - issuer weighting for central ministries, conditional inclusion for `Chính phủ` / `Thủ tướng` / `Quốc hội` / `UBND`, and heavy filtering for clearly public-law issuers such as `Bộ Công an`, `Bộ Nội vụ`, and `Bộ Quốc phòng`
- Added `scripts/bootstrap_hf_focused_corpus.py` to rebuild the local SQLite corpus from Hugging Face using a positive inclusion model instead of a broad all-law import.
- Updated `README.md` to:
  - describe the corpus as focused economy/finance/industry rather than a generic full-law mirror
  - document `bootstrap_hf_focused_corpus.py --reset`
  - point readers to `docs/FOCUSED_CORPUS_SCOPE.md`
  - fix the Appwrite environment variable names to the repo's `VLEGAL_APPWRITE_*` settings
- Rebuilt the live OCI corpus in place from a clean SQLite file because the VM did not have enough free disk for a safe side-by-side second database.
- The focused selector chose `88,962` cached documents and excluded `57,895` out-of-scope records plus `6,563` records that had no cached HTML content.
- The rebuilt live corpus is now serving `88,962` focused documents on OCI.
- The focused lifecycle graph rebuilt successfully with `11,369` relation links.
- The focused citation graph finished rebuilding with `636,769` citation links.
- Redeployed `vlegal-frontend` to Netlify production through the Netlify CLI after the OCI corpus rebuild.

### OCI Runtime Note

- The focused citation index rebuild was substantially slower than the document import and relation pass on this corpus size.
- The app stayed healthy on the new focused database while the citation pass completed in the background.

### Verification

- `uv run python -m compileall scripts/bootstrap_hf_focused_corpus.py`
- OCI `/health` returns `{"status":"ok","documents":88962}` on the rebuilt focused corpus
- The live SQLite count matches the focused selection size after import completes: `88,962`
- Final focused graph counts on OCI:
  - `11,369` relations
  - `636,769` citation links
- Netlify production redeploy completed:
  - production URL: `https://vlegal-frontend.netlify.app`
  - unique deploy URL: `https://69d25abe3b0b3d74449075db--vlegal-frontend.netlify.app`

## Session: Legal Reader Redesign Foundation

**Date:** 2026-04-02
**Goal:** Move the reader closer to an official Vietnamese legal-document experience, clean up compare flow, and record the phased implementation plan in the repo.

### What Shipped

- Added `docs/LEGAL_READER_IMPLEMENTATION_PLAN.md` to document the UX findings, the redesign rationale, and the phased delivery plan.
- Added a display-only legal document parser in `src/vlegal_prototype/structure.py`.
- The reader now detects and renders:
  - issuing authority block
  - national motto block
  - document number and date line
  - legal type and centered title block
  - preamble clauses such as `Căn cứ ...`
  - enactment lines such as `QUYẾT ĐỊNH:`
  - structured article and clause display for `Điều`, khoản, and điểm
- Kept the old markdown path as a safe fallback when the richer parser cannot confidently structure the content.
- Rebuilt `templates/document.html` so the legal document becomes the center of the page and research tools move to the side rail.
- Updated reader styling in `static/styles.css` toward a more formal legal-page layout.
- Fixed compare flow in `static/app.js` and `templates/index.html`:
  - exactly two selected documents
  - visible left/right compare slots
  - named selections instead of raw document IDs
- Removed self-compare behavior from the document reader and replaced it with a best-related compare target when available.
- Added mention-level inline citation preview support:
  - new `GET /api/citation-preview/{source_document_id}/{target_document_id}` endpoint
  - preview payload includes reference context, target document summary, inferred target section when available, lifecycle signals, and incoming mentions from other documents
  - the reader now opens a hover card on desktop and a tap sheet on mobile for inline legal references
- Extended citation previews with focused compare evidence from the strongest lifecycle-linked document when meaningful.
- Rebuilt and restarted the OCI backend container with the new reader and citation-preview logic.
- Fixed the public frontend proxy path by:
  - pointing Netlify redirects at the public Caddy-backed V-Legal host instead of the closed `:8000` port
  - adding `static/_redirects` so manual Netlify deploys reliably preserve proxy rules
  - redeploying `vlegal-frontend` and verifying public document and API routes
- Compressed the landing page into a tighter archive front page:
  - compact hero/search band
  - newly issued list promoted above the archive index
  - legal categories promoted above secondary tools
  - tracking, saved research, and ask-the-corpus moved into a tighter right rail
- Refined the in-text citation reading experience:
  - added source-side citation quotes to the preview payload
  - added a pinned citation "reading companion" card in the document side rail
  - added clearer inline citation states for resolved, section-aware, lifecycle-aware, active, and pinned references
- Updated the Hugging Face ingest path for the current `th1nhng0/vietnamese-legal-documents` dataset:
  - default dataset setting now points at the current corpus
  - importer now reads `metadata.parquet` plus `content.parquet` through a local SQLite content cache keyed by document id
  - added `--target-total` to `scripts/bootstrap_hf_full_corpus.py` so OCI imports can stop at a practical corpus size like 80k docs
- Strengthened citation mapping for cross-reference quality:
  - broader article/clause/point reference extraction around cited document numbers
  - target article resolution now falls back through article-level matching
  - citation rebuild now stores `target_section_id` when the cited provision can be resolved
- Tightened the landing page further:
  - reduced the hero to two core stats only
  - moved legal categories directly under search
  - reduced the latest-records block to two items
  - reduced hero and showcase spacing again
- Added section-level cross-reference badges directly inside the legal reader so cited hotspots surface at the article heading, not only in the outline rail.
- Improved citation and database robustness for the larger live corpus:
  - SQLite connections now use a longer timeout plus `busy_timeout`, `synchronous = NORMAL`, and in-memory temp storage
  - document-number matching now supports historical references such as `sắc lệnh số 63`, `91-SL`, and similar contextual forms
  - target matching now uses document-number aliases and legal-type hints during resolution
  - relation and citation rebuilds can now map more historical references that previously failed strict parsing
- Added identifier-first search behavior for document-number and numeric queries so lookups like `79` prefer legal identifiers before falling back to concept search.
- Hardened the reader parser for sloppy raw documents by:
  - splitting embedded preamble/enactment text out of oversized title blocks
  - accepting accentless structural headings like `Dieu`, `Chuong`, `Phan`, and `Muc` during display parsing

### Verification

- `uv run python -m compileall src scripts`
- parsed `templates/document.html` and `templates/index.html` successfully with Jinja
- rendered a sample SQLite document through the new display parser and verified that the authority, motto, number/date line, legal type, title, preamble, and article structure are emitted as structured HTML

---

## Session: Full-Corpus OCI Deployment + Legal Portal UI

**Date:** 2026-03-28 (continued into 2026-04-01)
**Goal:** Migrate V-Legal backend to OCI persistent VM with full 10K-document corpus, redesign UI to legal portal style, implement cross-reference hyperlinks.

---

## What Was Done

### OCI Persistent Deployment

- **Problem:** Demo deployment was ephemeral — 500 docs on Render free tier, no persistence.
- **Solution:** Migrated to OCI free-tier VM with bind-mounted `/opt/vlegal/data` directory.
- **Corpus:** `full_hf.sqlite` — 10,000 documents, ~1.5GB on disk.
- **Transfer:** Compressed with `tar.gz` (396MB), uploaded via `scp`, extracted on VM.
- **Verified:** health endpoint returns `{"status":"ok","documents":10000}`

### Docker Compose Fixes

- **Problem:** Named Docker volumes with `driver: local + bind opts` silently fail on containerd — empty 156KB file inside container instead of 1.5GB host file.
- **Fix:** Changed to direct bind mount syntax in `deploy/oci/docker-compose.yml`:
  ```yaml
  volumes:
    - /opt/vlegal/data:/app/data
  ```
- **Network:** Added `vnibb_default` external network so `vlegal-backend` container can communicate with `vnibb-caddy` (Caddy reverse proxy).

### Caddy Routing

- **Problem:** Caddy was routing to wrong container or wrong network.
- **Fix:** Updated `/srv/vnibb/deployment/Caddyfile` on VM to include:
  ```caddy
  vlegal.{$SITE_HOSTNAME} {
      encode gzip zstd
      reverse_proxy vlegal-backend:8000
  }
  ```
  Using container name `vlegal-backend:8000` instead of `127.0.0.1:8000` because they share the same Docker compose project network.
- **Domain:** `vlegal.{SITE_HOSTNAME}` via sslip.io wildcard — Let's Encrypt cert auto-provisioned.

### Cross-Reference Hyperlinks in Document Body

- **Problem:** Document body text contained Vietnamese legal references like `02/2007/TTLT-BCA-BLĐTBXH-BTC` that were not clickable.
- **Solution:** Built `inject_document_links()` post-processor in `structure.py` that:
  - Scans markdown-rendered HTML for document number patterns
  - Wraps matches in `<a class="doc-ref-link">` tags linking to `/documents/{id}`
  - Uses `DOC_NUMBER_PATTERN_V2` regex with full Vietnamese Unicode range `[\u00c0-\u1ef9]`
  - Handles truncated references via `_best_reference_match()` with prefix/suffix matching
- **Wiring:** `document_detail` route builds a citation map via `build_citation_map()`, then passes to `inject_document_links()`.

### Vietnamese Unicode Bug

- **Problem:** Regex `[A-Za-z0-9\-]+` stopped before the Vietnamese letter `Đ` in `BLĐTBXH`.
- **Fix:** Extended character class to include full Vietnamese range `[\u00c0-\u1ef9]`, which covers À-ỹ and Ā-ū.
- **Root cause:** `Đ` (U+0110) is not ASCII, so it broke the pattern match mid-token.

### UI Redesign — Legal Portal Style

- **Goal:** Match thuvienphapluat.vn formal legal portal aesthetic.
- **Changes to `templates/document.html`:**
  - Rewrote from complex 3-column portal to clean single-center-column layout
  - Sticky `doc-tabs` bar with orange `#c97517` active state
  - Red `#a11b1b` "MỤC LỤC VĂN BẢN" toggle
  - Compact right-side `doc-action-strip` with icon+label buttons
  - Noto Serif typography for legal content, Work Sans for interface chrome
  - Orange underlined `doc-ref-link` for cross-reference hyperlinks
  - Sticky narrow content column, no cluttered sidebar widgets

### Bootstrap Data Verified

After deploying full corpus and running bootstrap scripts:

| Data | Count |
|------|-------|
| Documents | 10,000 |
| Taxonomy subjects | 42 |
| Relations | 139 |
| Citation links | 11,194 |

---

## Problems Encountered

### 1. Named Volume Bug on Containerd

Docker named volumes with bind options silently fail on containerd runtime. The container saw a 156KB empty file instead of the 1.5GB database. Fix: use direct bind mount `- /opt/vlegal/data:/app/data`.

### 2. Vietnamese `Đ` in Document Numbers

`02/2007/TTLT-BCA-BLĐTBXH-BTC` was being extracted as `02/2007/TTLT-BCA-` because the regex `[A-Za-z0-9\-]+` doesn't include `Đ`. The space after the hyphen was being consumed. Fix: added `Đ` and full Vietnamese range to the character class.

### 3. Caddy Network Routing

`vlegal-backend` and `vnibb-caddy` were in different Docker compose projects. Caddy was proxying to `127.0.0.1:8000` but the backend wasn't on `127.0.0.1` — it was on the container's own network. Fix: use container name `vlegal-backend:8000` with the shared `vnibb_default` external network.

---

## Files Modified

| File | Change |
|------|--------|
| `deploy/oci/docker-compose.yml` | Bind mount + `vnibb_default` network |
| `deploy/oci/.env.example` | Added `VLEGAL_DATABASE_PATH=/app/data/full_hf.sqlite` |
| `DEPLOYMENT_OCI_VERCEL.md` | Added full-corpus OCI section + Caddy routing |
| `src/vlegal_prototype/app.py` | `build_citation_map()`, wired `inject_document_links()` |
| `src/vlegal_prototype/structure.py` | `DOC_NUMBER_PATTERN_V2`, `_strip_diacritics()`, `_best_reference_match()`, `inject_document_links()` |
| `templates/document.html` | Complete rewrite to document-first layout |
| `static/styles.css` | ~400 lines of `doc-*` CSS classes |

---

## Pending Work

- [ ] `JOURNAL.md` creation ← **Done this session**
- [ ] `README.md` update with OCI stats and cross-ref feature ← **Done this session**
- [ ] `deploy/oci/MAINTAIN.md` OCI maintenance documentation ← **This session**
- [ ] `scripts/oci_maintain.sh` maintenance script ← **This session**

---

## OCI VM State

- **Public URL:** configured on OCI VM via sslip.io subdomain
- **Container:** `vlegal-backend` on port 8000, attached to `vnibb_default`
- **Data:** `/opt/vlegal/data/full_hf.sqlite` (1.5GB)
- **Caddy:** `vnibb-caddy` routing configured via `SITE_HOSTNAME` env var
- **SSH:** see `.env` for connection details
