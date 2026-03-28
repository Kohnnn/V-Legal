# V-Legal Prototype

V-Legal is a prototype Vietnamese legal research product built around a clear roadmap:

1. ship a strong HF-dataset bootstrap prototype fast
2. layer in official-source trust and taxonomy from Phap dien, VBPL, and Van ban Chinh phu
3. grow into tracking, RAG, and eventually MCP/API workflows

The current build already supports:

- a local searchable legal archive
- a gazette-style document reader
- a grounded retrieval brief instead of unconstrained AI chat
- personal tracked-law behavior
- official Phap dien subject taxonomy in the browsing experience
- official-source lookup routes into VBPL and Van ban Chinh phu
- a first-pass document relationship graph for amended, replaced, and guided links
- a citation index for explicit cross-references between documents in the local corpus
- saved research views and a tracked-law workbench with alert-ready monitoring
- compare views for side-by-side cross-checking of related legal documents

## Product Direction

This prototype follows the design north star in `DESIGN.md`:

- document-first, not dashboard-first
- ivory-and-ink reading experience
- clear separation between legal content and interface chrome
- asymmetrical archive layout with research rails
- prepared for official-source authority layering

## Current Scope

### Data sources in the current prototype

- Hugging Face dataset: `th1nhng0/vietnamese-legal-documents`
- Official Phap dien subject taxonomy seeded from `https://phapdien.moj.gov.vn/TraCuuPhapDien/MainBoPD.aspx`

### Planned next source layers

- `phapdien.moj.gov.vn` for taxonomy and codified structure
- `vbpl.vn` for official metadata, scope, and legal search coverage
- `vanban.chinhphu.vn` for official text and PDF provenance

## What the app does today

### Archive experience

- full-text search over title and body content with SQLite FTS5
- filters for legal type, year, and issuing authority
- official subject browsing seeded from Phap dien
- recent-record and document-type side rails

### Reader experience

- centered gazette-style reading column
- metadata rail
- document outline rail
- cited-authorities panel grouped by link type
- referenced-by panel for inbound citations from other local documents
- local cross references
- official-source provenance panel with VBPL and VNCP routes
- relationship graph panel for inbound and outbound legal links
- grounded brief panel scoped to the current document
- compare links from citation and lifecycle panels into a dedicated cross-check view

### Official provenance layer

- every record gets a provenance profile computed from document number, legal type, and issuing authority
- archive cards show official-route badges where applicable
- document pages show a richer provenance panel for official cross-checking
- current official route templates use public search URLs, not hidden APIs

Current route templates used in the app:

- VBPL exact search:

```text
https://vbpl.vn/pages/vbpq-timkiem.aspx?type=0&s=1&SearchIn=Title,Title1&Keyword={query}
```

- VNCP search:

```text
https://vanban.chinhphu.vn/?pageid=473&q={query}
```

### Grounded retrieval

- retrieves relevant passages from the local corpus
- assembles a conservative brief from retrieved text only
- avoids pretending the prototype already has authoritative legal reasoning

### Citation index

- extracts explicit document references from titles, preambles, and article sections
- resolves citations by normalized document number against the local corpus
- groups citations into `amends`, `replaces`, `guides`, `implements`, `legal basis`, and general `cites`
- shows inbound and outbound citation panels in the reader for faster cross-checking

### Personal tracking

- lets users track laws directly from archive cards and document pages
- shows tracked laws on the archive page
- provides a `/tracking` workbench for alerts, watched dossiers, and saved research views

### Research workbench

- save archive filters as reusable research views
- open saved views as repeatable monitoring lenses
- surface tracked-law alerts from lifecycle links, citations, and newer same-subject documents
- bundle all of this into a lightweight single-user workflow suitable for the current free-tier deployment model

### Compare mode

- compare two local documents side by side through `/compare/{left_document_id}/{right_document_id}`
- prioritize explicit citation routes for lifecycle-style comparisons
- align sections using citations first, then label/content heuristics when appropriate
- expose unmatched sections to make version drift and missing coverage obvious
- add first-pass diff summaries and clause-level change labeling for aligned sections

## Architecture

### Stack

- FastAPI
- Jinja templates
- custom CSS/JS
- SQLite + FTS5
- Hugging Face `datasets` streaming loader

### Key files

- `src/vlegal_prototype/app.py` - web app entrypoint
- `src/vlegal_prototype/db.py` - SQLite schema and low-level DB helpers
- `src/vlegal_prototype/hf_ingest.py` - HF dataset normalization and passage chunking
- `src/vlegal_prototype/search.py` - archive search and retrieval helpers
- `src/vlegal_prototype/answering.py` - grounded brief generation
- `src/vlegal_prototype/taxonomy.py` - Phap dien taxonomy bootstrap and subject matching
- `src/vlegal_prototype/provenance.py` - official-source route inference and provenance badges
- `src/vlegal_prototype/relations.py` - relationship graph extraction and document-link queries
- `src/vlegal_prototype/citations.py` - citation extraction, resolution, and citation graph queries
- `src/vlegal_prototype/research.py` - saved research view helpers
- `src/vlegal_prototype/compare.py` - side-by-side document cross-check and section alignment helpers
- `src/vlegal_prototype/structure.py` - document section extraction and reader anchor generation
- `src/vlegal_prototype/tracking.py` - tracked-law alert generation and workbench summaries
- `scripts/bootstrap_hf_dataset.py` - import HF corpus into SQLite
- `scripts/bootstrap_phapdien_taxonomy.py` - import official subject taxonomy
- `scripts/bootstrap_citation_index.py` - rebuild explicit cross-document citations
- `scripts/bootstrap_relationship_graph.py` - rebuild document-to-document links from the local corpus
- `scripts/prepare_demo_bundle.py` - build a free-tier-friendly deployable demo bundle

## Local Development

### Prerequisites

- Python 3.12+
- `uv`

This repo works locally with newer Python versions too, but `3.12+` is the deployment-safe baseline.

### Install dependencies

```bash
uv sync
```

### Bootstrap a starter corpus

Import a fast local sample:

```bash
uv run python scripts/bootstrap_hf_dataset.py --limit 500 --reset
uv run python scripts/bootstrap_phapdien_taxonomy.py --seed-only
```

### Run the app

```bash
uv run uvicorn vlegal_prototype.app:app --reload --app-dir src
```

Open:

- `http://127.0.0.1:8000`

### Useful bootstrap commands

Import 2,000 docs from the beginning:

```bash
uv run python scripts/bootstrap_hf_dataset.py --limit 2000 --reset
```

Continue after the first 2,000 docs:

```bash
uv run python scripts/bootstrap_hf_dataset.py --skip 2000 --limit 2000
```

Refresh taxonomy from the checked-in official seed:

```bash
uv run python scripts/bootstrap_phapdien_taxonomy.py --seed-only
```

Rebuild the relationship graph after importing more records:

```bash
uv run python scripts/bootstrap_relationship_graph.py
```

Rebuild the explicit citation index after importing more records:

```bash
uv run python scripts/bootstrap_citation_index.py
```

Attempt a live taxonomy refresh from Phap dien and fall back to the seed if needed:

```bash
uv run python scripts/bootstrap_phapdien_taxonomy.py
```

Build the same small bundle intended for free-tier deployment:

```bash
uv run python scripts/prepare_demo_bundle.py --limit 500 --seed-only-taxonomy
```

## Database Notes

The local database lives at:

- `data/vlegal.sqlite`

Main tables:

- `documents`
- `passages`
- `tracked_documents`
- `taxonomy_subjects`
- `document_subjects`
- `document_relations`
- `document_sections`
- `citation_mentions`
- `citation_links`
- `research_views`

## Environment Variables

All app settings use the `VLEGAL_` prefix.

You can start from:

- `.env.example`

Common ones:

- `VLEGAL_ENVIRONMENT` - `development` or `production`
- `VLEGAL_DATABASE_PATH` - custom SQLite path
- `VLEGAL_DATASET_NAME` - alternate HF dataset id
- `VLEGAL_DEFAULT_IMPORT_LIMIT` - default import limit for HF bootstrap
- `VLEGAL_SEARCH_PAGE_SIZE` - archive page size
- `VLEGAL_ANSWER_PASSAGE_LIMIT` - grounded brief retrieval depth
- `VLEGAL_PHAPDIEN_MAIN_URL` - override the Phap dien source URL

## Deployment

## Recommended free-tier deployment target

The repo is prepared for a Render free web service because:

- FastAPI runs well as a simple Python web service
- the demo bundle can be built once during deploy
- a 500-document SQLite archive stays small enough for a free preview

### Render files included

- `render.yaml`
- `Dockerfile`
- `.dockerignore`

### Render free-tier strategy used here

To stay within free-tier constraints, the deployment bundle is intentionally small:

- only `500` HF documents are bundled by default
- Phap dien taxonomy comes from a checked-in official seed, so deploys do not depend on live crawling
- the bundled SQLite database is created at build time, not regenerated on every request

### Important free-tier limitations

Render free web services spin down when idle and use an ephemeral filesystem for runtime changes.

That means:

- the bundled archive data prepared during build is fine for a preview
- runtime edits to local SQLite can be lost after restart, redeploy, or spin-down
- tracked-law state is therefore preview-grade only on a pure free-tier SQLite deploy
- saved research views and workbench alert state are also preview-grade under the same constraint

If you want durable tracking later, move tracked state to a managed database.

### Deploy to Render

1. Push this repo to GitHub.
2. Create a new Render Web Service.
3. Let Render detect `render.yaml`, or configure the same commands manually.
4. Deploy.

Default Render config in this repo:

- plan: `free`
- build command:

```bash
pip install uv && uv sync --frozen && uv run python scripts/prepare_demo_bundle.py --limit 500 --seed-only-taxonomy
```

- start command:

```bash
uv run uvicorn vlegal_prototype.app:app --app-dir src --host 0.0.0.0 --port $PORT
```

### Deploy with Docker

Build locally:

```bash
docker build -t v-legal-prototype .
```

Run locally:

```bash
docker run -p 8000:8000 v-legal-prototype
```

The Docker image also prepares the small demo bundle at build time.

## Free-Tier Sizing Guidance

The current demo deployment profile is intentionally conservative:

- `500` docs instead of the full HF dataset
- local SQLite instead of a heavier search cluster
- no external vector DB
- server-rendered frontend instead of a heavier SPA stack

This keeps:

- build time lower
- runtime RAM lower
- disk footprint smaller
- cold-start recovery simpler

If you increase the corpus size, do it gradually and measure memory and startup time before keeping it in a free plan.

## Trust Model

This prototype is useful for search and UX validation, but it is not yet a fully authoritative legal status engine.

Current limitations:

- HF corpus is a bootstrap corpus, not the final source of truth
- effective status, amendment graph, and official consolidation are not complete yet
- VBPL and VNCP links are currently public search-route helpers, not guaranteed direct canonical detail links for every record
- relationship graph links are heuristic and currently based on the imported local corpus, so sparse or missing links are expected in small demo bundles
- citation resolution currently depends on local corpus coverage and exact/near-exact document number matching, so unresolved references still occur
- tracked-law alerts currently derive from local graph/citation/same-subject signals and are meant as monitoring aids, not authoritative legal-status notifications
- compare alignment is strongest when explicit citations exist; heuristic section matching is still intentionally conservative and incomplete
- grounded brief output must still be checked against official sources

## Memory Bank

Project memory is tracked in:

- `.agents/memory-bank/README.md`
- `.agents/memory-bank/project-brief.md`
- `.agents/memory-bank/architecture.md`
- `.agents/memory-bank/decisions.md`
- `.agents/memory-bank/progress.md`
- `.agents/memory-bank/roadmap.md`

## Suggested Next Build Step

The next implementation step after this state is:

1. add richer compare intelligence for old/current/amended documents, including diff summaries and clause-level change labeling

That is the best follow-up now that the first compare workflow, workbench, citation index, provenance layer, and lifecycle graph are already in place.
