# Markdown Schema

## Purpose

This document defines the canonical file format for the local legal corpus.

The format must be:

- easy to diff in git or local history tools
- easy to parse deterministically
- faithful to the legal text
- explicit about provenance and confidence

## Path Rules

Recommended path patterns:

```text
data/corpus/markdown/issued/central/2025/vn-issued-vbpl-213327--64-2025-qh15.md
data/corpus/markdown/issued/local/lam-dong/2026/vn-issued-vbpl-217569--18-2026-qd-ubnd.md
data/corpus/markdown/phapdien/vn-phapdien-0cf69ad9-6f29-4ee4-8e16-2c3aa65c3a52.md
```

Rules:

- use the canonical ID in every filename
- append a short slug when available for readability
- partition issued documents by jurisdiction and year
- keep `Phap dien` files in a separate tree from promulgated documents

## Frontmatter

Every canonical file should begin with YAML frontmatter.

Minimum required fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Markdown schema version |
| `canonical_id` | Stable internal ID |
| `document_layer` | `issued` or `phapdien` |
| `title` | Official title |
| `document_number` | Official number if present |
| `document_type` | Luat, Nghi dinh, Quyet dinh, Thong tu, etc. |
| `issuing_authority` | Official issuing body |
| `issuance_date` | Issuance date in ISO format where possible |
| `effective_date` | Effective date if known |
| `expiry_date` | Expiry date if known |
| `status` | In force, expired, partially expired, unknown |
| `language` | Usually `vi` |
| `source_system` | `vbpl`, `vanban_chinhphu`, `phapdien`, or `hf_bootstrap` |
| `source_document_id` | Source-native ID |
| `source_url` | Canonical source URL |
| `source_hash` | Hash of the raw source snapshot |
| `markdown_hash` | Hash of the emitted markdown body |
| `text_source` | `html`, `pdf`, `ocr`, or `mixed` |
| `parse_confidence` | `high`, `medium`, or `low` |
| `updated_at` | Last local regeneration timestamp |
|

Common optional fields:

| Field | Meaning |
| --- | --- |
| `official_journal` | Cong bao or journal source |
| `scope` | Central, provincial, municipal, etc. |
| `signers` | Signer names or titles |
| `legal_sectors` | Source metadata sectors |
| `attachments` | Attached PDF or annex files |
| `provisional` | Whether the record is pending reconciliation |
| `supersedes` | Known earlier canonical IDs |
| `superseded_by` | Known later canonical IDs |
| `phapdien_topics` | Linked codified topics |
| `official_source_system` | Official source system used for cross-check, such as `vbpl` |
| `official_source_document_id` | Official source-native identifier used for cross-check |
| `official_source_url` | Official source URL for provenance and app linking |

## Example Frontmatter

```yaml
---
schema_version: 1
canonical_id: vn-issued-vbpl-213327
document_layer: issued
title: Luat Ban hanh van ban quy pham phap luat
document_number: 64/2025/QH15
document_type: Luat
issuing_authority: Quoc hoi
issuance_date: 2025-06-01
effective_date: 2025-07-01
expiry_date:
status: in_force
language: vi
source_system: vbpl
source_document_id: 213327
source_url: https://vbpl.vn/...
source_hash: sha256:...
markdown_hash: sha256:...
text_source: html
parse_confidence: high
updated_at: 2026-04-14T10:30:00Z
---
```

## Body Structure

The body should preserve the legal hierarchy explicitly.

Recommended heading mapping:

- `#` document title
- `##` `Phan`
- `###` `Chuong`
- `####` `Muc`
- `#####` `Dieu`

Clauses and points should remain literal text lines:

```markdown
##### Dieu 1. Pham vi dieu chinh

1. Luat nay quy dinh ...

a) Truong hop thu nhat ...

b) Truong hop thu hai ...
```

## Preamble And Header Blocks

Keep official header material in the body when it is part of the authoritative text.

Examples:

- issuing authority block
- national motto block
- number and date block
- enactment formula such as `QUYET DINH:` or `NGHI QUYET:`
- `Can cu ...` preamble clauses

Do not paraphrase or collapse these into metadata only.

## Annexes And Tables

Rules:

- use normal markdown tables when the structure survives cleanly
- if a table is too complex, preserve it as an HTML block inside the markdown file
- if a form or scanned annex is only available as PDF, keep an attachment reference and mark `text_source: pdf` or `ocr`

## Endmatter

Preserve:

- `Noi nhan`
- signature titles
- signer names
- storage or archive notes

Endmatter often carries provenance and execution context, so it should not be discarded.

## Fidelity Rules

- do not rewrite legal wording for readability
- do not silently normalize away article numbers, clause numbers, or point labels
- do not invent headings not present in the source unless they are clearly structural wrappers inserted by the pipeline
- if the parser is uncertain, preserve more raw structure and lower the confidence flag instead of guessing
