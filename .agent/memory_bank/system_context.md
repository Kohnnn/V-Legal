# System Context: V-Legal

## Tech Stack
- **Core**: Python (FastAPI)
- **Database**: SQLite (Local)
- **Frontend**: Jinja2 Templates + Vanilla CSS (Aesthetics focused on scholary archive)
- **Search**: SQLite FTS5 Virtual Tables
- **Dataset**: Hugging Face `th1nhng0/vietnamese-legal-documents` (Initial bootstrapping)
- **Deployment**: Render (Docker-based)

## Design Patterns & Architecture
- **Server-Side Rendering (SSR)**: Archive and gazette-style reader pages are server-rendered.
- **RESTful APIs**: JSON APIs for search, grounded brief generation, and tracking.
- **Provenance Layer**: Official official-source search routes (VBPL, Van ban Chinh phu).
- **Retrieval-Augmented Generation (RAG)**: Retrieval-first, grounded answers with citations.
- **Schema**:
    - `documents`: Metadata + raw markdown.
    - `passages`: Retrieval chunks.
    - `tracked_documents`: Local follow/save behavior.
    - `taxonomy_subjects`: Official subject taxonomy list.
    - `document_relations`: Graph edges for amended/replaced/guided links.
    - `citation_index`: Resolved cross-document citations.
- **Compare Mode**: Side-by-side comparison using citations and clause-level heuristics.

## Design Rules
- **Aesthetic**: Scholarly archive / Gazette style.
- **Typography**: Serif for legal text, Sans-serif for metadata and controls.
- **Layout**: Asymmetrical rails on archive, centered reader with side panels.
- **Responsive**: Mobile-friendly document reading experience.
