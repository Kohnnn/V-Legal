# V-Legal Improvement Plan (2026-06)

## Why This Plan Exists

The journal documented a `687`-document prototype. The workspace corpus has grown far beyond that:

- `153,926` canonical markdown files under `data/corpus/markdown/`
- `corpus_summary.json`: `153,926` documents, years `1925`–`2026`, last import `2026-04-20`
- Derived SQLite at `data/corpus/sqlite/vlegal.sqlite` is `~11.7 GB`

The search, reader, and citation code was tuned for a `500`–`10k` prototype. At `150k` documents that code exposes correctness bugs and per-request hotspots. This plan scales the existing logic to the real corpus and fixes the bugs the larger corpus surfaced.

## Constraints

- All database writes target the **workspace** DB only: `data/corpus/sqlite/vlegal.sqlite`.
- Do **not** modify `deploy/`, `render.yaml`, `netlify.toml`, or OCI configs. Do not deploy.
- The migration is additive (new columns/indexes), idempotent, and reversible.
- Verification: focused `pytest` against a small temp DB plus route smoke checks. No reliance on the `11.7 GB` DB for tests.

## Phases

### Phase 0 — Test harness + P0 crash fix
- Add `pytest` dev dependency and a `tests/` package with an in-memory/temp-DB fixture built from `initialize_database` + a few `import_documents` rows.
- Fix `search.py`: `datetime.utcnow()` is used at `search.py:251` but `datetime` is never imported. Searching by document number (the identifier-first path) raises `NameError`. Reproduced live with query `22/2012/QH13`.
- Regression test: identifier search returns results without raising.

### Phase 1 — Search speed at 150k docs
- Add `document_number_norm` column + `idx_documents_document_number_norm`.
- Add `idx_documents_issuing_authority`.
- Rewrite `search_identifier_documents` to use the sargable normalized column instead of `REPLACE(UPPER(COALESCE(document_number,'')),'-','/')`.
- `get_recent_documents`: order by `imported_at DESC, issuance_date DESC` (current `id DESC` is meaningless because `id` is a SHA256-derived hash).
- FTS "has-more" probing (fetch `page_size+1`) to avoid the second COUNT MATCH on the common path.
- `scripts/migrate_add_search_indexes.py`: standalone, idempotent, operates only on `VLEGAL_DATABASE_PATH`. Backfills `document_number_norm`, creates indexes, runs `ANALYZE`.

### Phase 2 — Reader per-request work
- Cache `extract_sections` per content hash (parsed `>=3x` per page today).
- Fold deterministic runtime citation resolution into the offline index; cache the per-document runtime support so the reader stops firing one SQL query per ambiguous mention on every load.
- Lighten citation hover: stop running a full `build_compare_view` diff inside `api_citation_preview`; remove the duplicate `get_document_relation_graph` call.
- Cache rendered display HTML keyed on `(content_hash, citation_map_hash)`.

### Phase 3 — Correctness
- Internal-ID collision guard in `import_documents` (60-bit SHA-derived id can silently upsert-overwrite a different `canonical_id`).
- Relations: carry real confidence from the scoring margin instead of hardcoded `"high"`.
- Unify the document-number regex so citation badges and clickable links agree.
- Guard `resolve_appwrite_placeholders` so it never makes the 30s blocking HTTP call on the local/skip-remote path.

### Phase 4 — UX + docs
- Track/untrack: optimistic JS update instead of full `window.location.reload()`.
- Citation hover: open-debounce + abort in-flight requests.
- Escape server text in `renderBrief`; audit `| safe` usages.
- Scroll-spy active states on reader tabs/outline.
- Fix legacy `bootstrap_appwrite_to_sqlite.py` empty-state reference in `index.html`.
- Update `README` corpus counts and append a `JOURNAL.md` session entry.

## Progress

- [x] Phase 0 — pytest harness added (`tests/`), `datetime` import fixed in `search.py`, regression test reproduces and guards the original crash.
- [x] Phase 1 (code) — `document_number_norm` column + `idx_documents_document_number_norm`, `idx_documents_issuing_authority`, `idx_documents_imported_at` added to schema and to the idempotent `_ensure_schema_migrations`. `search_identifier_documents` rewritten to be sargable. `get_recent_documents` orders by `imported_at`. Filter-free FTS count no longer joins the base table. `documents_au` FTS trigger now guarded with `WHEN`. `scripts/migrate_add_search_indexes.py` written (idempotent, workspace-DB only).
  - **Migration run status:** partially applied to the workspace DB (~27k/153,926 rows backfilled). Throttled by the running dev server holding a concurrent connection (blocks WAL checkpoint). Guarded `documents_au` trigger restored on the live DB so it is not degraded. Remaining backfill is a user action (below).
- [x] Phase 2 — `extract_sections` cached by content (was parsed 3x/page). `build_runtime_citation_support` cached by content hash (was firing per-mention SQL on every view). Duplicate target relation-graph query removed from the citation-preview route. Startup now self-heals existing DBs via a cheap column-only migration (`_ensure_document_columns`) without running expensive index builds.
- [x] Phase 3 — internal-id collision guard (`InternalIdCollisionError`) in `import_documents` (batch + DB). Relation `confidence` now reflects the resolver's decision margin instead of hardcoded `"high"`. Document-number regexes unified in `doc_number.py` (one template, ASCII + Unicode variants) so citation badges and clickable links use the same structural rules. `resolve_appwrite_placeholders` no longer makes the blocking HTTP call on the skip-remote/local path and uses a 5s timeout.
- [x] Phase 4 — track/untrack updates optimistically in `app.js` (no full reload; keeps scroll + pinned citations); track buttons carry `data-active-class`/`data-label-*` across `document.html`, `index.html`, `research_view.html`. Citation hover gained a 140ms open-debounce so skating across a dense article does not fire a request per link. `renderBrief` now escapes all server-provided fields (module-scope `escapeHtmlValue`). Reader tabs gained `IntersectionObserver` scroll-spy active states. Legacy `bootstrap_appwrite_to_sqlite.py` empty-state replaced with the markdown-first `rebuild_sqlite_from_markdown.py` command.

## Test + Verification Summary

- `uv run pytest` — 17 tests passing across: identifier search regression, search index normalization/recency, reader caching, runtime-citation caching, internal-id collision guard, doc-number pattern parity, relation confidence.
- `uv run python -m compileall src scripts` — clean.
- FastAPI route smoke (`/`, `/health`, `/documents/{id}`, `/tracking`, `/compare/{a}/{b}`, `/api/search`, `/api/tracked`) against `data/ui_test.sqlite` — all 200, identifier search returns results, track toggle works.
- `node --check static/app.js` and Jinja parse of all templates — clean.

## Migration Runbook (user action)

The workspace DB (`data/corpus/sqlite/vlegal.sqlite`, ~11.7 GB) still needs the
remaining `document_number_norm` backfill:

1. Stop the local dev server (free port 8000) so no connection blocks WAL checkpoints.
2. Run: `uv run python scripts/migrate_add_search_indexes.py`
   - Resumes automatically (only fills `NULL` norms).
   - Drops the heavy `documents_au` FTS trigger during the backfill, then recreates the guarded version.
   - Creates the new indexes, then runs `ANALYZE`.
3. Restart the server. Until the backfill finishes, document-number search works for already-backfilled rows and degrades gracefully (no crash) for the rest.

Do NOT run this against OCI/production. It targets `VLEGAL_DATABASE_PATH` only.

---

# Document-Handling Improvements (Phases A-E)

Second pass, focused on how the app stores, surfaces, and navigates legal
documents. Same guardrails as above: workspace DB only, additive/idempotent
migrations, each phase verified with pytest + route smoke. Decisions taken:
explicit frontmatter status (with a clearly-labeled secondary "referenced by
newer documents" signal, never an asserted validity), standalone backfill
scripts, and A+B verified before C/D/E.

## Phase A - Legal validity status end-to-end

**Gap:** `build_frontmatter_metadata` emits `status`/`effective_date`/`expiry_date`
(`corpus.py:375-377`) but `build_record_from_canonical_document` drops them and
the `documents` table has no columns for them, so validity never reaches the app.

- Add `status` (default `unknown`), `effective_date`, `expiry_date` columns to
  `documents`; add to `SCHEMA`, `_ensure_document_columns`, and `import_documents`.
  Add `idx_documents_status`.
- `build_record_from_canonical_document` reads the three fields from frontmatter.
- Reader: validity badge (In force / Expired / Partially expired / Unknown) plus
  effective/expiry dates; honest "unverified (bootstrap)" treatment.
- Archive cards: status chip.
- Search: optional `status` filter in `search_documents` + `/api/search`.
- `scripts/migrate_add_validity_columns.py`: idempotent, workspace-only backfill
  from existing markdown frontmatter (no full rebuild).

## Phase B - OCR / low-confidence provenance banners

**Gap:** `text_source` (`ocr`/`pdf`/`mixed`) and `parse_confidence` (`low`/`medium`)
are stored but never surfaced.

- Reader banner when `text_source in {ocr, pdf}` or `parse_confidence != high`,
  linking to the official/source URL.
- Archive cards: subtle OCR / low-confidence tag.

## Phase C - Collapsible nested TOC + article deep-linking

- Outline carries `section_type` + depth (Phan=1, Chuong=2, Muc=3, Dieu=4).
- Collapsible tree in `document.html` + `app.js` (framework-free).
- Per-`Dieu` copy-link / cite affordance using existing anchors.

## Phase D - Body-level repeal/amend extraction

**Gap:** `rebuild_relationship_graph` reads only `title`, missing body-level
"dieu khoan thi hanh" repeals.

- Scan endmatter/body for repeal/amend statements via `extract_relation_candidates`
  + unified `doc_number.py` patterns; reconcile with citation-derived links; carry
  real confidence + evidence source (title vs body). Offline rebuild path only.

## Phase E - Lighter `get_document` projection

**Gap:** `get_document`/`get_documents_by_ids` use `SELECT *` (full bodies) even
for metadata-only needs (compare loads ~5 bodies/request).

- Add `get_document_meta` (no `content`/`plain_content`); repoint metadata-only
  call sites; keep full fetch for the reader body.

## Progress (Phases A-E)

- [x] Phase A - `status`/`effective_date`/`expiry_date` columns added to `SCHEMA`, `_ensure_document_columns` (cheap startup migration), and `import_documents`; `idx_documents_status` added. `build_record_from_canonical_document` reads them from frontmatter. Reader shows a validity badge (with "chưa đối chiếu" for bootstrap sources) + effective/expiry dates; archive cards show a status chip; home + `/api/search` gained a `status` filter (`STATUS_FILTER_TOKENS`). `scripts/migrate_add_validity_columns.py` backfills from markdown frontmatter (idempotent, workspace-only). New module `validity.py`.
- [x] Phase B - `build_text_provenance_notice` drives a reader banner for `text_source in {ocr,pdf,mixed}` or `parse_confidence != high`, linking to the official/source URL. Severity-styled (`doc-provenance-notice`).
- [x] Phase C - outline carries `section_type` + `depth` (`OUTLINE_DEPTHS`); reader renders a collapsible nested tree (`initDocOutlineTree`) and per-`Điều` copy-link affordance (`initArticleAnchorLinks`, renders where the display parser assigns an anchor). New CSS for tree + anchor link.
- [x] Phase D - `rebuild_relationship_graph` adds a second pass scanning a bounded body endmatter window (`_endmatter_window`) for repeal/amend clauses, with downgraded confidence (`_downgrade_confidence`) and body evidence text. Streaming cursor keeps memory bounded; offline rebuild only.
- [x] Phase E - `get_document_meta` (no `content`/`plain_content`) added; `/compare`, `/api/compare`, citation-preview source/target, and compare-focus lookup repointed to it. Reader body path keeps full `get_document`.

## Test + Verification Summary (Phases A-E)

- `uv run pytest` - 29 tests passing (adds validity, body-relations, document-meta, outline-depth).
- `uv run python -m compileall src scripts` - clean.
- Route smoke against `data/ui_test.sqlite`: `/`, `/health`, `/documents/{id}`, `/tracking`, `/compare`, `/api/compare`, `/?status=in_force`, `/api/search`, `/api/citation-preview` behave correctly (preview 404 only when no link exists between the pair). Validity badge, OCR notice, status filter option, outline tree, and article anchor links confirmed present in rendered HTML.
- `node --check static/app.js` + Jinja parse of all templates - clean.

## Validity Backfill Runbook (user action)

The new validity columns are populated on import/rebuild. To backfill the
existing workspace DB without a full rebuild:

1. Stop the local dev server (frees WAL checkpoints).
2. `uv run python scripts/migrate_add_validity_columns.py`
   - Adds the columns if missing, backfills `status`/`effective_date`/`expiry_date`
     from each row's canonical markdown frontmatter, creates `idx_documents_status`,
     drops/recreates the guarded `documents_au` trigger around the backfill, then `ANALYZE`.

Most HF-bootstrap rows will remain `unknown` until official-source reconciliation
provides a status; the reader labels these honestly as not yet reconciled.
