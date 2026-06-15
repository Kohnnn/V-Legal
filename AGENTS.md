# AGENTS.md

## What This Repo Is
- Python `>=3.12` FastAPI + Jinja app for a local-first Vietnamese legal corpus viewer.
- Current architecture is in transition: canonical markdown under `data/corpus/` is the source of truth; SQLite is derived and rebuildable.
- Appwrite code remains for legacy/transitional paths, but it is not the target data architecture.

## High-Value Entry Points
- Web app/routes/startup: `src/vlegal_prototype/app.py`
- Settings/env loading: `src/vlegal_prototype/settings.py`
- SQLite schema/import/queries: `src/vlegal_prototype/db.py`
- Canonical markdown corpus helpers: `src/vlegal_prototype/corpus.py`
- Search/retrieval: `src/vlegal_prototype/search.py`
- Legal structure parsing/display: `src/vlegal_prototype/structure.py`
- Citations/relations/taxonomy: `src/vlegal_prototype/citations.py`, `relations.py`, `taxonomy.py`
- OCR/PDF pipeline: `src/vlegal_prototype/pdf_ocr.py`, `scripts/paddleocr_extract_text.py`, `scripts/process_pdf_attachments.py`
- UI: `templates/*.html`, `static/styles.css`, `static/app.js`

## Commands Agents Should Not Guess
- Install/sync deps: `uv sync`
- Run app normally: `uv run uvicorn vlegal_prototype.app:app --reload --app-dir src`
- Run local full-corpus app without remote/startup maintenance: `uv run python scripts/run_local_site.py`
- Override local app port: set `VLEGAL_LOCAL_PORT=8002` before `scripts/run_local_site.py`
- Syntax verification: `uv run python -m compileall src scripts`
- Health check: `curl http://127.0.0.1:8000/health`
- Rebuild SQLite from markdown: `uv run python scripts/rebuild_sqlite_from_markdown.py --reset`
- Rebuild SQLite quickly while skipping taxonomy/relations/citations: `uv run python scripts/rebuild_sqlite_from_markdown.py --reset --skip-postprocess`
- Rebuild archive home cache for the full local app: `uv run python scripts/build_archive_home_cache.py`
- Rebuild taxonomy subject links for the full local app: `uv run python scripts/build_taxonomy_links.py`

## Data And Runtime Gotchas
- Default settings point at `data/corpus/sqlite/vlegal.sqlite` and `data/corpus/`; do not assume the old `data/vlegal.sqlite` path.
- `scripts/run_local_site.py` forces `VLEGAL_DATABASE_PATH=data/corpus/sqlite/vlegal.sqlite`, `VLEGAL_SKIP_STARTUP_MAINTENANCE=true`, and `VLEGAL_SKIP_REMOTE_USER_DATA=true`.
- Startup maintenance can be expensive on the full corpus; prefer `scripts/run_local_site.py` for local verification unless testing startup behavior itself.
- SQLite is derived from markdown; after changing canonical markdown, import/rebuild SQLite before judging app behavior.
- Archive landing data uses `data/corpus/manifests/archive_home_cache.json`; rebuild it after corpus-wide archive/index changes.
- Taxonomy cards depend on `document_subjects`; rebuild via `scripts/build_taxonomy_links.py` after taxonomy or full-corpus import changes.

## Markdown-First Corpus Workflow
- Export bootstrap markdown sample: `uv run python scripts/export_hf_markdown_corpus.py --limit 500 --reset`
- Rebuild derived SQLite after export: `uv run python scripts/rebuild_sqlite_from_markdown.py --reset`
- Import Phap dien codified markdown: `uv run python scripts/import_phapdien_corpus.py` or add `--limit 1 --topic-id <id>` for a focused test.
- Import Government Portal listings: `uv run python scripts/import_vncp_listing.py --typegroupid 3 --limit 1`
- Backfill VBPL provenance from Phap dien references: `uv run python scripts/backfill_vbpl_references.py`

## OCR/PDF Notes
- PDF-backed VNCP records may be image scans; direct PyMuPDF extraction can return zero text even when the PDF is valid.
- PaddleOCR runs in the dedicated `.venv-ocr/` Python environment because Paddle CPU wheels may not match the main Python runtime.
- Use bounded OCR for scan-heavy PDFs when full-document OCR is too slow: `uv run python scripts/process_pdf_attachments.py --canonical-id <id> --backend paddleocr_subprocess --max-ocr-pages 1 --sync-sqlite`.
- Empty OCR extraction should fail rather than overwrite markdown with an empty body.
- MiniMax is text-only post-correction after OCR, not an image/PDF OCR engine.

## Verification Targets
- For route-affecting changes, manually check `/`, `/health`, one `/documents/{id}`, `/tracking`, and one `/compare/{left_id}/{right_id}` when relevant.
- No pytest suite is currently configured in the repo; use `compileall` plus focused route/script smoke tests.

## Style And Architecture Constraints
- Keep FastAPI routes thin; move domain logic into helper modules such as `search.py`, `compare.py`, `taxonomy.py`, `relations.py`, `citations.py`, `corpus.py`, and `pdf_ocr.py`.
- Use `sqlite3` directly; keep schema changes centralized in `src/vlegal_prototype/db.py`.
- Preserve SQLite FTS5 tables, triggers, and `connection.row_factory = sqlite3.Row` behavior.
- Keep frontend framework-free: plain Jinja, CSS, and DOM APIs in `static/app.js`.
- Preserve the document-first scholarly design from `DESIGN.md`: Noto Serif for legal content, Work Sans for UI chrome, ivory/ink palette, tonal layering over SaaS-style cards.
- Prefer small synchronous helpers and plain `dict`/`list`/`sqlite3.Row` structures unless an existing API boundary already uses `BaseModel`.
- Keep `from __future__ import annotations` in Python modules that already use it.

## Source Priority
- Trust executable config/scripts over prose when they conflict.
- `README.md` documents the current markdown-first direction; `docs/FOCUSED_CORPUS_SCOPE.md` and `docs/DEPLOYMENT_NETLIFY_APPWRITE.md` are legacy direction notes.
- Existing repo-local instruction sources checked: no `.cursor/rules/`, `.cursorrules`, `.github/copilot-instructions.md`, or `opencode.json` are present.
