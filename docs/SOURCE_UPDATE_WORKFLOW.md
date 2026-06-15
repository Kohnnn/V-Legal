# Source Update Workflow

## Objective

Use official Vietnamese legal sources to keep the local markdown corpus current without depending on the Hugging Face dataset as the long-term update mechanism.

## Source Roles

| Corpus Layer | Primary Source | Secondary Source | Bootstrap / Reference |
| --- | --- | --- | --- |
| Issued documents | `vbpl.vn` | `vanban.chinhphu.vn` | `th1nhng0/vietnamese-legal-documents` |
| Codified topic layer | `phapdien.moj.gov.vn` ebook zip and topic tree | live `Phap dien` pages | `VN-Law-Advisor` crawler ideas |
| UI benchmark | none | none | `thuvienphapluat.vn` |

## Why Not Depend On The Hugging Face Dataset

The dataset is valuable for bootstrap and backfill, but it is still a third-party snapshot.

Long-term update authority should come from:

- the national legal database at `vbpl.vn`
- the Government text system at `vanban.chinhphu.vn`
- the Ministry of Justice `Phap dien` corpus

## Run Modes

## Bootstrap

Use the Hugging Face dataset once to create a large initial local corpus quickly.

Bootstrap outputs:

- canonical markdown files
- raw HTML snapshots
- missing-content report
- provisional trust labels where needed

## Daily Incremental Refresh

Purpose:

- detect newly published records
- detect changed HTML or metadata on official sources
- pull fresh PDFs or attachments
- create provisional government-first records when necessary

Practical Government Portal path:

- use server-rendered `he-thong-van-ban` listings for legal-doc discovery
- crawl filtered listing buckets such as laws, decrees, decisions, and circulars
- fetch detail pages by `docid`
- emit provisional markdown records when the detail page exposes metadata plus attachment links but not inline full text

## Periodic Reconciliation

Purpose:

- reconcile provisional `vanban.chinhphu.vn` records to VBPL IDs
- refresh `Phap dien` trees and codified topic mappings
- harvest official `vbpl.vn` links embedded inside `Phap dien` topic content and backfill them into matching issued markdown records
- rerun relationship and citation extraction against the markdown corpus
- rebuild SQLite indexes when emitted markdown changed

## Pipeline Steps

1. discover candidate documents from official sources
2. fetch raw payloads and save them under `data/corpus/raw/`
3. hash the raw payloads
4. compare raw hashes with previous manifests
5. normalize changed or new payloads into canonical markdown
6. hash emitted markdown
7. update manifests and conflict logs
8. rebuild SQLite indexes only for changed documents when possible

## Reconciliation Rules

## VBPL vs `vanban.chinhphu.vn`

- if VBPL has a record, VBPL is the primary legal-record source
- if `vanban.chinhphu.vn` publishes first, create a provisional issued record
- once VBPL exposes the same document, reconcile to the VBPL canonical ID and retain the original government snapshot as provenance

## `Phap dien`

- treat the downloadable ebook zip as the preferred bulk snapshot when available
- treat live pages as a secondary check for structure or freshness
- link `Phap dien` nodes back to issued documents when identifiers and text evidence allow it

## PDF-Only Documents

- keep the official PDF immediately
- create a record with metadata and `text_source: pdf`
- queue OCR and structural repair separately
- do not pretend PDF-only documents are fully parsed until text quality is acceptable

## Missing Or Conflicting Cases

Write a review record whenever:

- metadata conflicts across official sources
- the same document number maps to multiple candidate source IDs
- the markdown emitter changes drastically compared with the prior version
- the parser confidence falls below the acceptable threshold

## Outputs

The updater should emit:

- updated markdown files
- updated raw snapshots
- `documents.jsonl` manifest changes
- conflict and manual-review logs
- a changed-document list that can drive SQLite rebuilds

## What Counts As Self-Updating

The corpus should be considered self-updating when the normal operating path is:

- official-source discovery
- official-source fetch
- deterministic markdown regeneration
- derived-index rebuild

The Hugging Face dataset can still be used for disaster recovery, backfill, or regression checks, but not as the only current-state source.
