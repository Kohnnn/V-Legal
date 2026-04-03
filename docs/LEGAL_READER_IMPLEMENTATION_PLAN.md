# Legal Reader Implementation Plan

## Context

V-Legal already has useful legal research primitives:

- full-text search over imported documents
- document section extraction for `Phần`, `Chương`, `Mục`, and `Điều`
- citation indexing between local documents
- lifecycle relation inference such as `amends`, `replaces`, and `guides`
- a section-aware compare engine

The current product gap is not the absence of research logic. The gap is presentation and interaction.

Today the reader still renders most legal text as generic markdown. Compare selection is confusing. Inline legal references are clickable, but they do not yet behave like legal research citations with context.

## Core Problems

### 1. The reader does not look or behave like an official legal document

The corpus already contains header and body conventions close to official Vietnamese legal pages:

- issuing authority line
- national motto block
- document number and date line
- centered legal type and title
- preamble clauses such as `Căn cứ ...`
- enactment line such as `QUYẾT ĐỊNH:`
- body hierarchy with `Phần`, `Chương`, `Mục`, `Điều`, khoản, and điểm

The app currently flattens most of this into paragraphs.

### 2. Compare flow loses trust

The existing compare bar allows more than two selections, shows raw document IDs instead of document identities, and the document reader links to self-compare. That makes a serious legal workflow feel unreliable.

### 3. Inline citations are too shallow

The current inline citation layer only turns document numbers into links. It does not yet expose:

- cited section inside the target document
- whether the citation is an amendment, replacement, guidance, implementation, or general citation
- whether the current document has been updated or replaced by a newer document
- whether the current document is mentioned by other local documents

## Product Direction

The redesign should follow `DESIGN.md` and move closer to the VanBanPhapLuat reading model:

- document-first, not dashboard-first
- strong legal page hierarchy
- quieter interface chrome
- marginal tools instead of dominant cards
- clearer compare and citation workflows

## Delivery Plan

### Phase 1: Ship the legal reader foundation

Scope:

- add a display-only legal document parser layered on top of raw stored content
- preserve the current indexing and compare pipeline
- render official-style header, title, preamble, and article structure in the reader
- keep markdown fallback for documents with weak parse confidence
- fix compare selection to a strict two-document workflow
- remove self-compare behavior from the document page
- show relation groups more clearly so users can see newer, older, and related documents

Files primarily involved:

- `src/vlegal_prototype/structure.py`
- `src/vlegal_prototype/app.py`
- `templates/document.html`
- `static/styles.css`
- `static/app.js`
- `templates/index.html`

### Phase 2: Ship inline legal citation context

Scope:

- add mention-level citation preview data
- preserve the exact inline citation identity with `data-*` attributes
- expose document preview details for citation hovers or mobile tap sheets
- surface whether a cited document is later amended, replaced, guided, or referenced by other documents

Likely backend additions:

- mention-level citation API
- compact document preview payload for hover cards
- target-section resolution in citation links where possible

### Phase 3: Ship section-aware legal change review

Scope:

- connect inline citations and relation items to section-aware compare summaries
- highlight whether language is expanded, reduced, rewritten, or unchanged
- expose the strongest comparison target automatically for amendment or replacement relationships

## Implementation Constraints

### Keep raw corpus and current schema stable

The safest path is additive:

- keep raw `content`
- keep `extract_sections()` for indexing and compare
- keep current SQLite schema intact for now
- add a display parser only for rendering

### Preserve fallback behavior

The corpus is inconsistent. Not every document follows the same header and body pattern. The reader must fall back safely when parsing confidence is low.

## What This Session Ships

This session ships the first foundation slice:

- documented reader and interaction plan
- legal document display parser with safe fallback
- reader redesign toward official legal page structure
- compare selection cleanup and removal of self-compare behavior
- clearer relation and citation grouping in the reader

## Follow-up Work

The next highest-value slice after this foundation is inline citation hover cards with section-aware context.
