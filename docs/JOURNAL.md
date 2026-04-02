# Development Journal

## Session: Full-Corpus OCI Deployment + Legal Portal UI

**Date:** 2026-03-28 (continued into 2026-04-01)
**Goal:** Migrate V-Legal backend to OCI persistent VM with full 10K-document corpus, redesign UI to legal portal style, implement cross-reference hyperlinks.

---

## What Was Done

### OCI Persistent Deployment

- **Problem:** Demo deployment was ephemeral — 500 docs on Render free tier, no persistence.
- **Solution:** Migrated to OCI free-tier VM with bind-mounted `/opt/vlegal/data` directory.
- **Corpus:** `full_hf.sqlite` — 10,000 documents, ~1.5GB on disk.
- **Transfer:** Compressed with `tar.gz` (396MB), uploaded via `scp`, extracted on VM.
- **Verified:** health endpoint returns `{"status":"ok","documents":10000}`

### Docker Compose Fixes

- **Problem:** Named Docker volumes with `driver: local + bind opts` silently fail on containerd — empty 156KB file inside container instead of 1.5GB host file.
- **Fix:** Changed to direct bind mount syntax in `deploy/oci/docker-compose.yml`:
  ```yaml
  volumes:
    - /opt/vlegal/data:/app/data
  ```
- **Network:** Added `vnibb_default` external network so `vlegal-backend` container can communicate with `vnibb-caddy` (Caddy reverse proxy).

### Caddy Routing

- **Problem:** Caddy was routing to wrong container or wrong network.
- **Fix:** Updated `/srv/vnibb/deployment/Caddyfile` on VM to include:
  ```caddy
  vlegal.{$SITE_HOSTNAME} {
      encode gzip zstd
      reverse_proxy vlegal-backend:8000
  }
  ```
  Using container name `vlegal-backend:8000` instead of `127.0.0.1:8000` because they share the same Docker compose project network.
- **Domain:** `vlegal.{SITE_HOSTNAME}` via sslip.io wildcard — Let's Encrypt cert auto-provisioned.

### Cross-Reference Hyperlinks in Document Body

- **Problem:** Document body text contained Vietnamese legal references like `02/2007/TTLT-BCA-BLĐTBXH-BTC` that were not clickable.
- **Solution:** Built `inject_document_links()` post-processor in `structure.py` that:
  - Scans markdown-rendered HTML for document number patterns
  - Wraps matches in `<a class="doc-ref-link">` tags linking to `/documents/{id}`
  - Uses `DOC_NUMBER_PATTERN_V2` regex with full Vietnamese Unicode range `[\u00c0-\u1ef9]`
  - Handles truncated references via `_best_reference_match()` with prefix/suffix matching
- **Wiring:** `document_detail` route builds a citation map via `build_citation_map()`, then passes to `inject_document_links()`.

### Vietnamese Unicode Bug

- **Problem:** Regex `[A-Za-z0-9\-]+` stopped before the Vietnamese letter `Đ` in `BLĐTBXH`.
- **Fix:** Extended character class to include full Vietnamese range `[\u00c0-\u1ef9]`, which covers À-ỹ and Ā-ū.
- **Root cause:** `Đ` (U+0110) is not ASCII, so it broke the pattern match mid-token.

### UI Redesign — Legal Portal Style

- **Goal:** Match thuvienphapluat.vn formal legal portal aesthetic.
- **Changes to `templates/document.html`:**
  - Rewrote from complex 3-column portal to clean single-center-column layout
  - Sticky `doc-tabs` bar with orange `#c97517` active state
  - Red `#a11b1b` "MỤC LỤC VĂN BẢN" toggle
  - Compact right-side `doc-action-strip` with icon+label buttons
  - Noto Serif typography for legal content, Work Sans for interface chrome
  - Orange underlined `doc-ref-link` for cross-reference hyperlinks
  - Sticky narrow content column, no cluttered sidebar widgets

### Bootstrap Data Verified

After deploying full corpus and running bootstrap scripts:

| Data | Count |
|------|-------|
| Documents | 10,000 |
| Taxonomy subjects | 42 |
| Relations | 139 |
| Citation links | 11,194 |

---

## Problems Encountered

### 1. Named Volume Bug on Containerd

Docker named volumes with bind options silently fail on containerd runtime. The container saw a 156KB empty file instead of the 1.5GB database. Fix: use direct bind mount `- /opt/vlegal/data:/app/data`.

### 2. Vietnamese `Đ` in Document Numbers

`02/2007/TTLT-BCA-BLĐTBXH-BTC` was being extracted as `02/2007/TTLT-BCA-` because the regex `[A-Za-z0-9\-]+` doesn't include `Đ`. The space after the hyphen was being consumed. Fix: added `Đ` and full Vietnamese range to the character class.

### 3. Caddy Network Routing

`vlegal-backend` and `vnibb-caddy` were in different Docker compose projects. Caddy was proxying to `127.0.0.1:8000` but the backend wasn't on `127.0.0.1` — it was on the container's own network. Fix: use container name `vlegal-backend:8000` with the shared `vnibb_default` external network.

---

## Files Modified

| File | Change |
|------|--------|
| `deploy/oci/docker-compose.yml` | Bind mount + `vnibb_default` network |
| `deploy/oci/.env.example` | Added `VLEGAL_DATABASE_PATH=/app/data/full_hf.sqlite` |
| `DEPLOYMENT_OCI_VERCEL.md` | Added full-corpus OCI section + Caddy routing |
| `src/vlegal_prototype/app.py` | `build_citation_map()`, wired `inject_document_links()` |
| `src/vlegal_prototype/structure.py` | `DOC_NUMBER_PATTERN_V2`, `_strip_diacritics()`, `_best_reference_match()`, `inject_document_links()` |
| `templates/document.html` | Complete rewrite to document-first layout |
| `static/styles.css` | ~400 lines of `doc-*` CSS classes |

---

## Pending Work

- [ ] `JOURNAL.md` creation ← **Done this session**
- [ ] `README.md` update with OCI stats and cross-ref feature ← **Done this session**
- [ ] `deploy/oci/MAINTAIN.md` OCI maintenance documentation ← **This session**
- [ ] `scripts/oci_maintain.sh` maintenance script ← **This session**

---

## OCI VM State

- **Public URL:** configured on OCI VM via sslip.io subdomain
- **Container:** `vlegal-backend` on port 8000, attached to `vnibb_default`
- **Data:** `/opt/vlegal/data/full_hf.sqlite` (1.5GB)
- **Caddy:** `vnibb-caddy` routing configured via `SITE_HOSTNAME` env var
- **SSH:** see `.env` for connection details
