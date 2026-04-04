# Development Journal

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
