# Project Brief

## Product Name

V-Legal

## Goal

Build a modern Vietnamese legal research product that is easier to trust, easier to search, and easier to extend than legacy portals.

## Current Phase

Phase 1 prototype: bootstrap with the Hugging Face dataset `th1nhng0/vietnamese-legal-documents`.

## Why This Phase First

- lets us stand up search and document UX quickly
- creates a retrieval baseline before building official crawlers
- gives us room to validate schema, filters, and document detail design

## Prototype Success Criteria

- searchable local corpus
- strong archive index and gazette-style document page
- basic metadata filtering
- grounded answer brief that cites retrieved passages
- personal law tracking workflow
- official subject taxonomy from Phap dien visible in the product
- first-pass relationship graph for amended, replaced, and guided links
- explicit citation and reference panels for cross-checking related legal documents
- saved research views and workbench alerts for repeat monitoring
- a compare mode for side-by-side legal cross-checking
- ingestion path that can later be swapped from HF corpus to official sources

## Near-Term Follow-Up

1. add official-source ingestion for Phap dien taxonomy
2. add canonical document provenance and status fields
3. add amendment and relationship graph
4. expand tracking into alerts and saved research views
5. add MCP/API surface after the corpus is stable
