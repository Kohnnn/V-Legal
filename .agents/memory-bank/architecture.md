# Architecture

## Current Prototype Shape

- `scripts/bootstrap_hf_dataset.py`
  - streams the Hugging Face dataset
  - normalizes metadata and content
  - chunks long texts into passages
  - stores everything in local SQLite

- `scripts/bootstrap_phapdien_taxonomy.py`
  - loads the official Phap dien subject list
  - supports live refresh with seed fallback

- `scripts/prepare_demo_bundle.py`
  - builds a compact archive bundle for free-tier deployment

- `data/vlegal.sqlite`
  - `documents` table for metadata + raw markdown
  - `passages` table for retrieval chunks
  - `tracked_documents` table for local follow/save behavior
  - `taxonomy_subjects` table for official subject taxonomy
  - `document_subjects` table for document-topic links
  - `document_relations` table for amended / replaced / guided links
  - `document_sections` table for title / preamble / article-level reader structure
  - `citation_mentions` table for raw detected legal references
  - `citation_links` table for resolved cross-document citations
  - `research_views` table for saved single-user legal filters
  - FTS5 virtual tables for fast search

- `src/vlegal_prototype/app.py`
  - FastAPI app
  - server-rendered archive and gazette-style reader pages
  - JSON APIs for search, grounded brief generation, and tracking

- `src/vlegal_prototype/provenance.py`
  - classifies issuer scope and document family
  - builds public official-source lookup routes for VBPL and Van ban Chinh phu
  - feeds provenance badges on archive cards and the provenance panel in the reader

- `src/vlegal_prototype/relations.py`
  - extracts document-to-document links from the local corpus
  - stores graph edges for amended / replaced / guided relationships
  - powers the relationship graph panel and related-document prioritization

- `src/vlegal_prototype/citations.py`
  - extracts explicit document citations from titles and section text
  - resolves them against local documents by normalized document number
  - powers `Cited authorities` and `Referenced by` panels

- `src/vlegal_prototype/research.py`
  - stores and loads saved research views
  - converts saved filters back into live archive queries

- `src/vlegal_prototype/compare.py`
  - builds side-by-side compare views between two local documents
  - uses explicit citations first and section heuristics second
  - adds first-pass diff summaries and clause-level change labeling
  - powers `/compare/{left}/{right}` and the compare API

- `src/vlegal_prototype/tracking.py`
  - turns tracked documents into a workbench alert queue
  - combines lifecycle links, citations, and same-subject updates into monitoring signals

- `src/vlegal_prototype/structure.py`
  - derives section structure and reader anchors from legal text
  - keeps section anchors aligned with citation panels and outline navigation

- `templates/` + `static/`
  - editorial-style frontend focused on scanability, document reading, and law tracking

## Why FastAPI + Jinja Instead of a Heavier Frontend Stack

- faster to ship from an empty workspace
- keeps ingestion and runtime in one language
- avoids premature frontend complexity before the corpus model is stable
- still gives enough control for a polished interface

## Data Strategy

Current source:

- HF dataset for rapid bootstrap

Planned source layering:

1. HF corpus for fast prototype coverage
2. Phap dien for subject taxonomy and codified structure
3. VBPL for official legal metadata and central/local coverage
4. Van ban Chinh phu for direct official text/PDF provenance

## RAG Strategy For The Prototype

- retrieval-first
- conservative answer generation
- citation-grounded brief instead of open-ended chat

This keeps the prototype useful without pretending it already has authoritative legal reasoning.

## UI Direction

- follows `DESIGN.md` and the Stitch references under a document-first "scholarly archive" aesthetic
- serif content layer for legal text, sans-serif utility layer for controls and metadata
- archive page with asymmetrical rails for tracking and source-planning context
- centered gazette-style reader with side metadata, outline, grounded brief, and local cross references

## Deployment Shape

- `render.yaml` prepares a Render free web service deployment
- `Dockerfile` prepares a container image with a prebuilt SQLite archive bundle
- the deployment bundle defaults to 500 HF records so startup and disk use stay lightweight
- tracked-law writes remain preview-grade on pure free-tier SQLite hosting because runtime filesystem changes are not durable
