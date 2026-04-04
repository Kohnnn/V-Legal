# AGENTS.md

## Purpose
This repository is a Python 3.12+ FastAPI prototype for Vietnamese legal research.
Agentic coding agents should optimize for small, clear changes that preserve the current document-first product direction.

## Rule Sources
- Checked for `.cursor/rules/`, `.cursorrules`, and `.github/copilot-instructions.md`.
- None are present in `D:\Projects\V-Legal`.
- Follow this file, `README.md`, `DESIGN.md`, and existing code patterns.

## Repository Shape
- App entrypoint: `src/vlegal_prototype/app.py`
- Settings: `src/vlegal_prototype/settings.py`
- Database/schema: `src/vlegal_prototype/db.py`
- Search/retrieval: `src/vlegal_prototype/search.py`
- Comparison logic: `src/vlegal_prototype/compare.py`
- Taxonomy/bootstrap: `src/vlegal_prototype/taxonomy.py`
- Relations: `src/vlegal_prototype/relations.py`
- Citations: `src/vlegal_prototype/citations.py`
- Structure/display: `src/vlegal_prototype/structure.py`
- Appwrite client: `src/vlegal_prototype/appwrite_client.py`
- Answering/brief generation: `src/vlegal_prototype/answering.py`
- Provenance: `src/vlegal_prototype/provenance.py`
- Tracking: `src/vlegal_prototype/tracking.py`
- Dataset ingest: `src/vlegal_prototype/hf_ingest.py`
- Frontend assets: `static/styles.css`, `static/app.js`
- Templates: `templates/*.html`
- Bootstrap scripts: `scripts/*.py`
- Local database: `data/vlegal.sqlite`

## Environment And Tooling
- Python baseline is `3.12+`.
- Dependency manager and runner is `uv`.
- Packaging is defined in `pyproject.toml` with setuptools.
- No dedicated lint config in `pyproject.toml`.
- No checked-in pytest suite yet.

## Setup Commands
- Install dependencies: `uv sync`
- Run the app locally: `uv run uvicorn vlegal_prototype.app:app --reload --app-dir src`
- Run the app in deploy-like mode: `uv run uvicorn vlegal_prototype.app:app --app-dir src --host 0.0.0.0 --port 8000`

## Data Bootstrap Commands
- Fast local sample: `uv run python scripts/bootstrap_hf_dataset.py --limit 500 --reset` then `uv run python scripts/bootstrap_phapdien_taxonomy.py --seed-only`
- Larger sample import: `uv run python scripts/bootstrap_hf_dataset.py --limit 2000 --reset`
- Continue import from an offset: `uv run python scripts/bootstrap_hf_dataset.py --skip 2000 --limit 2000`
- Rebuild official taxonomy links: `uv run python scripts/bootstrap_phapdien_taxonomy.py --seed-only`
- Rebuild relationship graph: `uv run python scripts/bootstrap_relationship_graph.py`
- Rebuild citation index: `uv run python scripts/bootstrap_citation_index.py`
- Prepare the preview demo bundle: `uv run python scripts/prepare_demo_bundle.py --limit 500 --seed-only-taxonomy`

## Build, Lint, And Test Commands
No formal `build` script or lint task. Use practical verification commands:
- Install/sync dependencies: `uv sync`
- Syntax check all Python modules: `uv run python -m compileall src scripts`
- Local smoke test: `uv run uvicorn vlegal_prototype.app:app --reload --app-dir src`
- Preview-bundle smoke test: `uv run python scripts/prepare_demo_bundle.py --limit 500 --seed-only-taxonomy` then `uv run uvicorn vlegal_prototype.app:app --app-dir src`
- Health check: `curl http://127.0.0.1:8000/health`

Once pytest is installed, single-test patterns:
- Run a specific test file: `uv run python -m pytest tests/test_search.py -q`
- Run a specific test function: `uv run python -m pytest tests/test_search.py -k test_search_documents -q`
- Run all tests with verbose output: `uv run python -m pytest tests/ -v`
- Run with coverage (if added): `uv run python -m pytest tests/ --cov=vlegal_prototype --cov-report=term-missing`

When adding new tests, prefer lightweight pytest coverage around helper modules before full end-to-end coverage. Place tests in `tests/` directory mirroring the `src/` structure (e.g., `tests/test_search.py` for `src/vlegal_prototype/search.py`).

## Manual Verification Targets
- `/`
- `/tracking`
- one `/documents/{id}` page
- one `/compare/{left_document_id}/{right_document_id}` page
- `/health`

## Python Style Guidelines
- Keep `from __future__ import annotations` at the top of Python modules that already use it.
- Group imports as standard library, third-party, then local package imports.
- Prefer module-level constants for regexes, labels, SQL, and configuration-like values.
- Use type hints everywhere practical; the codebase prefers built-in generics like `list[dict]`, unions like `str | None`, and pipe syntax for unions.
- Match existing typing style rather than introducing heavy abstractions such as `TypedDict`, `Protocol`, or custom generic wrappers unless clearly needed.
- Prefer small, pure helper functions for normalization, parsing, matching, and formatting.
- Keep functions synchronous unless FastAPI integration or I/O pressure clearly requires async.
- Return plain `dict`, `list`, `set`, and `sqlite3.Row`-derived structures when that matches surrounding code.
- Use `BaseModel` only at API boundaries where request validation is helpful.
- Use `Field(...)` constraints for request payload validation when the route already follows that pattern.

## Naming And Formatting
- Modules/files: `snake_case`
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- CSS classes: BEM-like names such as `site-header__inner` and `meta-chip--soft`
- Template block names and `data-*` attributes should stay descriptive and literal
- Follow existing Black-style formatting even though Black is not configured explicitly
- Prefer multiline imports and function calls when a line becomes crowded
- Keep SQL in triple-quoted strings with uppercase SQL keywords and aligned indentation
- Keep long f-strings readable; split them instead of creating dense one-liners
- Prefer early returns for guard clauses
- Avoid unnecessary comments; most modules are readable through naming and structure

## Database And SQL Conventions
- Use `sqlite3` directly; do not introduce an ORM without a strong reason
- Preserve `connection.row_factory = sqlite3.Row` behavior
- Use parameterized SQL with `?` placeholders; never string-format user input into SQL
- Use `with connection:` for grouped writes
- Keep schema changes centralized in `src/vlegal_prototype/db.py` unless the project adopts migrations later
- Preserve FTS5 tables, triggers, and foreign key behavior when editing schema code

## Error Handling Guidelines
- Raise `HTTPException` in route handlers for user-facing HTTP errors such as missing records
- Return booleans for simple success/failure helpers when the surrounding code already expects that pattern
- Use conservative fallbacks for external-source integration; taxonomy bootstrap intentionally falls back from live HTML to seed data
- Catch broad exceptions only at boundary points where fallback behavior is intentional
- Prefer explicit, user-readable error messages over generic failures
- Do not silently swallow errors unless a fallback is part of the product behavior

## FastAPI And Backend Conventions
- Keep routes in `app.py` thin: gather inputs, call helper functions, assemble template or JSON responses
- Put domain logic in helper modules such as `search.py`, `compare.py`, `taxonomy.py`, `relations.py`, and `citations.py`
- Reuse the dependency-injected DB connection pattern from `get_db()`
- Maintain the current split between HTML routes and `/api/...` JSON routes
- Preserve startup initialization behavior for database setup, taxonomy seeding, and graph rebuilds

## Frontend And Template Conventions
- Preserve the document-first, scholarly visual direction described in `DESIGN.md`
- Prefer Noto Serif for legal content and Work Sans for interface chrome
- Reuse existing CSS custom properties in `:root` before adding new raw color values
- Avoid generic dashboard styling, rounded-corner SaaS cards, and bright modern-app palettes
- Prefer tonal layering, spacing, and typography over hard borders
- Keep JavaScript framework-free unless there is a compelling reason to add a build system
- In `static/app.js`, use plain DOM APIs, `async`/`await`, and graceful UI fallback on fetch failures
- Use Jinja templates for server-rendered views, keep context names explicit, and avoid moving business logic into templates

## Scope Control For Agents
- Make the smallest change that solves the task
- Do not invent new infrastructure, background workers, or external services unless requested
- Do not replace SQLite, FastAPI, Jinja, or the framework-free frontend without explicit direction
- Preserve the current preview-grade deployment model unless the task is specifically about deployment architecture

## Recommended Agent Workflow
1. Read the relevant module and one nearby caller before editing
2. Check whether `README.md`, `DESIGN.md`, or deployment docs already define the behavior
3. Make the smallest coherent change
4. Run `uv run python -m compileall src scripts`
5. If behavior changed, run the app and manually verify the impacted route
6. Update docs when commands, behavior, or architecture expectations change