# Decisions

## 2026-03-28 - Use HF corpus first

Reason:

- fastest path to a working prototype
- enough metadata to validate search UX
- avoids blocking on official crawler engineering

## 2026-03-28 - Use SQLite + FTS5 locally

Reason:

- zero external infrastructure
- simple setup for prototype iteration
- enough for search, filters, and chunk retrieval

## 2026-03-28 - Use grounded briefs instead of unconstrained AI answers

Reason:

- no secret API key required
- safer during early corpus validation
- still demonstrates the future RAG workflow

## 2026-03-28 - Use FastAPI server-rendered UI for v1

Reason:

- empty repo, so speed matters
- one-language stack reduces friction
- can still support a distinct, modern interface

## 2026-03-28 - Pivot UI to the "Scholarly Archive" system

Reason:

- the first pass worked functionally but felt too generic
- `DESIGN.md` gave a clearer document-first visual system
- the Stitch references validated three important product surfaces: archive index, gazette reader, and tracked-law portfolio

## 2026-03-28 - Add local tracked-law behavior before official-source ingestion

Reason:

- it directly supports the original product goal of personal law tracking
- it gives the prototype a more differentiated workflow than plain search
- it fits naturally with the Stitch portfolio concept while staying HF-first

## 2026-03-28 - Add Phap dien subject taxonomy before deeper official-source ingestion

Reason:

- it gives the archive an official Vietnamese legal browsing structure early
- it improves the product beyond keyword-only search without waiting for full official-text ingestion
- it is a high-leverage bridge between the HF bootstrap corpus and later authority-layer work

## 2026-03-28 - Target a free-tier-ready deployment bundle

Reason:

- the user wants the prototype deployable without immediately paying for infra
- a prebuilt 500-document SQLite bundle is small enough for preview hosting
- build-time bundling avoids repeated runtime HF downloads on cold start

## 2026-03-28 - Use public official search routes before full canonical-source ingestion

Reason:

- it gives users an immediate way to cross-check records against VBPL and Van ban Chinh phu
- it improves trust without blocking on deeper crawler/parser work
- it keeps the provenance layer lightweight and compatible with free-tier deployment

## 2026-03-28 - Start relationship graph with heuristic local-corpus extraction

Reason:

- the product needs legal change-tracking signals before full official consolidation is available
- heuristic links for amended, replaced, and guided relationships are enough to prove the workflow
- sparse but high-precision graph links are better than dense low-trust links in the current prototype stage

## 2026-03-28 - Add explicit citation index before broader same-matter clustering

Reason:

- explicit citations are closer to the core legal research value than generic similarity
- article and preamble citations are easier to trust and explain to users than black-box relatedness
- they create the right foundation for later same-matter, lifecycle, and comparison features

## 2026-03-28 - Build saved views and alert-ready tracking before compare mode

Reason:

- the user needs repeated cross-check workflows, not only one-off document reading
- saved views and tracked-law alerts make the prototype feel like an actual legal monitoring tool
- they reuse the new citation and lifecycle signals without needing heavier diff or compare infrastructure yet

## 2026-03-28 - Start compare mode as citation-first, not diff-first

Reason:

- explicit citation routes are more reliable than naive paragraph diffs in the current corpus
- many pairs are amendment acts versus base texts, so generic same-article matching can be misleading
- a conservative compare view is more valuable now than a noisy full-text diff
