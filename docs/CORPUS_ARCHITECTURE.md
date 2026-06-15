# Corpus Architecture

## Intent

The target architecture is a local-first legal corpus where the filesystem stores the canonical markdown documents and SQLite stores only derived indexes needed by the app.

## Source Of Truth

The source of truth should live under `data/corpus/`.

```text
data/corpus/
  markdown/
    issued/
      central/
      local/
    phapdien/
  raw/
    vbpl/
    chinhphu/
    phapdien/
  manifests/
    documents.jsonl
    source_runs.jsonl
    conflicts.jsonl
  sqlite/
    vlegal.sqlite
```

## Corpus Layers

## Issued Layer

This layer contains promulgated legal documents as they were officially issued.

- laws
- codes
- ordinances
- decrees
- decisions
- circulars
- resolutions
- directives
- local legal documents

Each source document is its own markdown file.

## Codified `Phap dien` Layer

This layer contains topic-oriented codified material from `phapdien.moj.gov.vn`.

- subjects (`Chu de`)
- topics (`De muc`)
- tree nodes
- codified article groupings

This is a separate layer because it represents an organized legal view of still-effective norms, not the original promulgation artifact.

## Raw Snapshot Layer

This layer stores raw source payloads used to generate markdown.

- HTML snapshots from VBPL
- HTML or PDF snapshots from `vanban.chinhphu.vn`
- ebook zip files and extracted trees from `Phap dien`
- optional Hugging Face bootstrap snapshots

Raw snapshots let the pipeline be audited and re-run without re-fetching every source immediately.

## Manifest Layer

This layer records provenance and update state.

- canonical IDs
- source URLs
- source hashes
- emitted markdown hashes
- update timestamps
- source precedence decisions
- duplicate or conflict records
- manual-review queues
- optional AI sidecar interpretations for low-confidence or structure-recovery workflows

## Canonical Identity

Every markdown file should have a stable canonical ID.

Recommended prefixes:

- `vn-issued-vbpl-<id>` for VBPL-backed promulgated documents
- `vn-issued-vpcp-<id>` for provisional `vanban.chinhphu.vn` documents before VBPL reconciliation
- `vn-phapdien-<item_id>` for codified `Phap dien` nodes

Canonical IDs should not depend only on the document number because some records are inconsistent, duplicated, or missing the number in source metadata.

## Derived SQLite Role

SQLite should remain useful, but it is not the canonical corpus.

SQLite is responsible for:

- full-text search
- passage indexing
- citation indexes
- relationship indexes
- compare support
- retrieval profiles for vectorless RAG

SQLite should be rebuildable entirely from `data/corpus/markdown/` plus the manifests.

## Appwrite Status

Appwrite is out of scope for the corpus architecture.

- no document text should depend on Appwrite
- no user-data workflow should block local corpus work
- any remaining Appwrite code is transitional legacy and should not drive future architecture decisions

## Trust Model

Trust should be explicit.

- `official_primary`: document emitted from VBPL or `Phap dien` primary artifacts
- `official_secondary`: document emitted from `vanban.chinhphu.vn` when used as a freshness bridge
- `bootstrap_only`: document emitted from the Hugging Face dataset before an official refresh confirms it
- `manual_review`: document exists but needs review because parsing confidence, source mismatch, or OCR quality is too low

## Relationship Between Corpus And App

The app should move toward this flow:

1. source adapters fetch raw official data
2. deterministic normalizers emit markdown files
3. optional AI schema reinforcement emits sidecar structure for hard cases
4. markdown parsers and validators rebuild SQLite indexes
5. FastAPI renders and searches against SQLite while linking back to markdown provenance

This keeps the product fast locally while making the corpus portable outside the app.
