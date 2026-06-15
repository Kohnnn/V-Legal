# AI Parsing Policy

## Short Answer

No, an AI API is not required to get the first useful markdown corpus working.

The first implementation should be deterministic and source-faithful:

- fetch official content
- preserve raw snapshots
- convert known HTML patterns into markdown
- rebuild SQLite indexes from markdown

That gets the project moving without introducing model drift into canonical legal text.

## When AI Is Helpful

AI becomes useful once the deterministic path is already working and the main remaining failures are low-confidence cases.

Good uses:

- OCR cleanup for scanned PDFs
- structural repair when a source HTML block is malformed
- table or annex normalization when deterministic rules fail
- duplicate-record reconciliation suggestions for human review
- extracting likely headings from noisy PDF text before deterministic validation

## AI Schema Reinforcement

There is one high-value use of AI that fits this repo well: a **schema reinforcement layer**.

This means AI does not replace the canonical markdown body. Instead, it produces a derived structural interpretation that makes parsing, inline references, and cross-checking easier.

Good reinforcement outputs:

- normalized header fields inferred from noisy source layout
- detected structural blocks such as authority, motto, number line, title, preamble, article, clause, point, annex, signature, and `Noi nhan`
- candidate anchors for `Phan`, `Chuong`, `Muc`, and `Dieu`
- candidate inline reference spans and target document numbers
- candidate relationship cues such as amends, replaces, guides, or implements
- parser confidence and ambiguity notes for human or rule-based review

The key rule is:

- canonical markdown remains deterministic and source-faithful
- AI emits a sidecar interpretation that can be accepted, rejected, or merged by later validation steps

This is often better than letting AI rewrite the source text directly.

## When AI Must Not Be Authoritative

AI should not be the canonical source of legal wording.

Bad uses:

- inventing missing legal text
- paraphrasing statutes into the canonical markdown body
- inferring effective status without source evidence
- rewriting clause numbering or article structure based only on model judgment
- deciding source precedence without manifestable evidence

## Recommended Adoption Order

1. deterministic HTML-to-markdown exporter
2. deterministic markdown-to-SQLite index rebuild
3. official-source incremental updater
4. OCR queue for PDF-only documents
5. optional AI-assisted repair on the OCR and malformed-source queue

## If You Want To Use Minimax

Your Minimax API can help later, but it should be optional and tightly scoped.

The safest way to introduce it is:

- keep canonical source snapshots on disk
- run AI only on documents marked `pdf`, `ocr`, `mixed`, or `low` confidence
- store AI outputs as derived artifacts or candidate repairs
- validate or review the result before it replaces canonical markdown
- log the model name, prompt version, and timestamp in provenance metadata

Recommended artifact shape:

- canonical markdown file under `data/corpus/markdown/...`
- raw source snapshot under `data/corpus/raw/...`
- AI sidecar JSON under `data/corpus/manifests/` or a sibling path such as `.ai.json`

That sidecar can contain:

- structural spans
- normalized metadata candidates
- inline citation candidates
- confidence scores
- unresolved ambiguities

This gives the app a richer parse surface without making model output the legal source of truth.

## Recommended Policy For This Repo

- do not require Minimax for the phase-1 markdown exporter
- reserve Minimax for phase-2 or phase-3 repair queues
- keep AI output behind an explicit feature flag
- never let AI be the only path to a usable legal record when an official HTML source exists
- prefer AI sidecar structure extraction over AI-authored canonical markdown

## Practical Decision

If you want the fastest path to a reliable system:

- do not block implementation on an AI API right now
- build the deterministic corpus pipeline first
- wire Minimax only after the project has clear OCR and malformed-document queues that justify it
