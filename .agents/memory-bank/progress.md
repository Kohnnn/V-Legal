# Progress Log

## 2026-03-28

- reviewed the repo, legal sites, and HF dataset to define the prototype direction
- chose an authoritative-search-first roadmap: search -> grounded brief -> official-source ingestion -> MCP
- initialized a new V-Legal prototype workspace
- created the memory bank under `.agents/memory-bank`
- built a FastAPI + SQLite + HF-ingestion prototype from scratch
- added local HF ingestion via `scripts/bootstrap_hf_dataset.py`
- implemented search, document detail, and grounded brief endpoints
- imported a 50-document starter sample into `data/vlegal.sqlite`
- ran smoke checks for `/health`, `/`, `/documents/{id}`, and `/api/search`
- reviewed `DESIGN.md` and the Stitch reference directions
- redesigned the app into a document-first archive and gazette-style reader
- added local tracked-law behavior with a `tracked_documents` table and tracking API
- verified the refreshed UI and tracking flow with FastAPI smoke tests and browser snapshots
- expanded the local corpus from 50 to 500 documents for a more realistic browsing surface
- loaded official Phap dien subject taxonomy and linked documents to those subjects where possible
- added free-tier deployment prep with `render.yaml`, `Dockerfile`, and a compact demo bundle script
- rewrote the README into a fuller build, data, and deployment guide
- added an official-source provenance layer with public VBPL and Van ban Chinh phu search routes
- exposed provenance badges in the archive and a provenance panel in the reader
- verified provenance behavior with smoke tests and browser snapshots
- added a first-pass relationship graph for amended, replaced, and guided document links
- integrated graph rebuilding into import and demo-bundle scripts
- exposed relationship graph sections on document pages and prioritized direct graph neighbors in related records
- added section-aware citation extraction and a resolved citation index over the local corpus
- exposed `Cited authorities` and `Referenced by` panels in the document reader
- integrated citation rebuilding into import and demo-bundle scripts and rebuilt the 500-document local bundle with 80 citation links
- added saved research views and a `/tracking` workbench for repeatable legal monitoring
- built alert-ready tracked-law signals using lifecycle links, citations, and newer same-subject documents
- integrated the workbench into the archive UI and updated docs for the new monitoring workflow
- added a `/compare/{left}/{right}` workflow for side-by-side cross-checking between related documents
- linked compare actions from citation, lifecycle, and workbench alert surfaces
- tuned compare alignment to prefer explicit citations for lifecycle-style document pairs
- added first-pass diff summaries and clause-level change labeling in compare mode
