# Full Markdown Port Plan

## Goal

Port Vietnamese law into a local-first markdown corpus where:

- every promulgated document becomes a structured markdown file
- the filesystem is the canonical corpus
- SQLite is a rebuildable search and retrieval index
- official-source provenance is preserved for every document
- vectorless RAG and app parsing operate on markdown, not on a remote database

This direction is inspired by `legalize-es`, but Vietnam needs a two-layer model:

- an issued-document layer built from official promulgated texts
- a codified `Phap dien` layer built from the Ministry of Justice topic tree

Those two layers should be linked, not collapsed into a single synthetic source.

## Non-Goals

- Appwrite is not part of the target corpus architecture.
- Embeddings are not required for the first usable system.
- AI parsing is not required for the first usable markdown export.
- The first milestone does not require full legal consolidation of every historical amendment into a single rewritten text.

## Principles

- Markdown is the source of truth.
- Raw source snapshots are retained for provenance and debugging.
- SQLite is derived data and can be rebuilt at any time.
- Official sources win over third-party mirrors.
- Deterministic parsing comes before AI-assisted repair.
- Every transformation must be traceable back to a source URL, source snapshot, and content hash.

## Phases

## Phase 1: Canonical Corpus Contract

- define the on-disk corpus layout under `data/corpus/`
- define canonical document IDs and file naming rules
- define YAML frontmatter and markdown body rules
- define source precedence and trust levels
- mark the current focused-corpus and Appwrite direction as legacy

Deliverable:

- stable corpus contract docs that the exporter and app can both target

## Phase 2: Bootstrap Exporter

- use `th1nhng0/vietnamese-legal-documents` only as a bootstrap and backfill source
- export every HTML-backed document into canonical markdown
- store original HTML snapshots alongside emitted markdown
- emit manifest files for hashes, source metadata, and missing-content cases

Deliverable:

- a local markdown corpus that can be parsed without Appwrite

## Phase 3: Official Source Connectors

- add a VBPL adapter for metadata, legal status, relationships, and HTML content when available
- add a `vanban.chinhphu.vn` adapter for freshness and official PDF attachments
- add a `Phap dien` adapter using the downloadable ebook zip and topic tree metadata
- preserve source-specific raw snapshots in `data/corpus/raw/`

Deliverable:

- self-update no longer depends on the Hugging Face dataset staying current

## Phase 4: Incremental Update Workflow

- detect new and changed documents from official sources
- hash raw source payloads and emitted markdown
- support provisional records when `vanban.chinhphu.vn` publishes before VBPL catches up
- reconcile provisional government records to VBPL records once the official legal-portal entry exists
- track missing HTML, PDF-only, and manual-review cases separately

Deliverable:

- repeatable local updates without a full corpus rebuild every time

## Phase 5: Rebuild Local Indexes From Markdown

- parse markdown into sections, passages, and citations
- rebuild SQLite FTS and retrieval profiles from markdown
- rebuild relation and citation layers from markdown plus source metadata
- keep the app working against SQLite while treating it as disposable derived state

Deliverable:

- vectorless RAG and the app consume markdown-derived indexes rather than raw HF content

## Phase 6: Reader And UX Modernization

- make the reader and navigation feel closer to `thuvienphapluat.vn`
- keep the document-first design language from `DESIGN.md`
- add better provenance, related-effect views, raw-PDF access, and compare workflows
- use `Phap dien` topics as a first-class navigation layer

Deliverable:

- a modern legal research UI on top of a local-first markdown corpus

## Hard Problems

- many older documents are PDF-only or image-scan only
- the same document can appear across VBPL and `vanban.chinhphu.vn` with different metadata completeness
- `Phap dien` is codified by topic, not a direct one-file-per-promulgated-document mirror
- amendment history and current-in-force consolidation are not the same artifact
- tables, forms, appendices, and signatures are structurally inconsistent across sources

## Milestone Order

The recommended delivery order is:

1. corpus contract
2. markdown bootstrap exporter
3. markdown-to-SQLite rebuild path
4. official-source update adapters
5. AI-assisted OCR and repair only where deterministic parsing is not enough

## Success Criteria

- the corpus can be regenerated locally without Appwrite
- each law document exists as a structured markdown file with provenance
- the app can parse and retrieve from markdown-derived SQLite indexes
- official-source refresh can update the local corpus incrementally
- AI usage is optional and never the only way to obtain a correct canonical document
