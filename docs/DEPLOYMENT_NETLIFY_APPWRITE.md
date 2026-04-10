# V-Legal Deployment Guide

**Stack:** Netlify (frontend) + OCI VM FastAPI (backend) + Appwrite (user data)

**What goes where:**

| Layer | Host | Content |
|-------|------|---------|
| Frontend | Netlify | Edge proxy + static assets |
| Backend API | OCI VM | FastAPI — serves legal docs, search, compare, citation graph |
| User data | Appwrite | Tracked documents, research views, anonymous user sessions |

Auth/login is deferred. User identity is a browser-generated UUID persisted in `localStorage` and mirrored in a first-party cookie.

---

## Part 1: Appwrite Setup

### 1.1 Create a Free Appwrite Account

Sign up at [cloud.appwrite.io](https://cloud.appwrite.io).

### 1.2 Install Appwrite CLI

```bash
npm install -g appwrite-cli
appwrite login
```

### 1.3 Create a New Appwrite Project

In the Appwrite Console, create a project. Get the project ID from Settings.

Initialize the CLI in your project directory:

```bash
appwrite init project
# Enter your project ID when prompted
```

### 1.4 Create the User Data Database

```bash
# Create a database for V-Legal user data
appwrite tables-db create-table \
    --database-id "vlegal" \
    --name "vlegal_user_data"
```

### 1.5 Create Collections

#### 1.5.1 Tracked Documents

```bash
appwrite tables-db create-table \
    --database-id "vlegal" \
    --table-id "tracked_documents" \
    --name "tracked_documents" \
    --permissions 'read("users")' 'create("users")' 'delete("users")'
```

Add columns:

```bash
# User ID (anonymous UUID)
appwrite tables-db create-varchar-column \
    --database-id "vlegal" --table-id "tracked_documents" \
    --key "user_id" --size 64 --required true

# Document ID (from OCI corpus)
appwrite tables-db create-integer-column \
    --database-id "vlegal" --table-id "tracked_documents" \
    --key "document_id" --required true

# Tracked at (ISO timestamp)
appwrite tables-db create-datetime-column \
    --database-id "vlegal" --table-id "tracked_documents" \
    --key "tracked_at" --required false

# Document title (denormalized for display)
appwrite tables-db create-varchar-column \
    --database-id "vlegal" --table-id "tracked_documents" \
    --key "document_title" --size 512 --required false

# Document number (denormalized)
appwrite tables-db create-varchar-column \
    --database-id "vlegal" --table-id "tracked_documents" \
    --key "document_number" --size 255 --required false
```

Create index for fast lookups:

```bash
appwrite tables-db create-column-index \
    --database-id "vlegal" --table-id "tracked_documents" \
    --key "user_id" --type "key"
```

#### 1.5.2 Research Views

```bash
appwrite tables-db create-table \
    --database-id "vlegal" \
    --table-id "research_views" \
    --name "research_views" \
    --permissions 'read("users")' 'create("users")' 'update("users")' 'delete("users")'
```

Add columns:

```bash
# User ID
appwrite tables-db create-varchar-column \
    --database-id "vlegal" --table-id "research_views" \
    --key "user_id" --size 64 --required true

# View name
appwrite tables-db create-varchar-column \
    --database-id "vlegal" --table-id "research_views" \
    --key "name" --size 255 --required true

# Search query string
appwrite tables-db create-varchar-column \
    --database-id "vlegal" --table-id "research_views" \
    --key "query" --size 512 --required false

# Topic slug filter
appwrite tables-db create-varchar-column \
    --database-id "vlegal" --table-id "research_views" \
    --key "topic_slug" --size 128 --required false

# Legal type filter
appwrite tables-db create-varchar-column \
    --database-id "vlegal" --table-id "research_views" \
    --key "legal_type" --size 64 --required false

# Year filter
appwrite tables-db create-integer-column \
    --database-id "vlegal" --table-id "research_views" \
    --key "year" --required false

# Issuing authority filter
appwrite tables-db create-varchar-column \
    --database-id "vlegal" --table-id "research_views" \
    --key "issuer" --size 255 --required false

# Created at
appwrite tables-db create-datetime-column \
    --database-id "vlegal" --table-id "research_views" \
    --key "created_at" --required false
```

Create index:

```bash
appwrite tables-db create-column-index \
    --database-id "vlegal" --table-id "research_views" \
    --key "user_id" --type "key"
```

### 1.6 Get Your Appwrite Config

From the Appwrite Console → Settings:

- **Project ID**
- **API Endpoint** (e.g. `https://cloud.appwrite.io/v1`)

---

## Part 2: OCI Backend (No Changes Needed)

Your FastAPI backend on OCI VM is already running with the full corpus.

You only need to add Appwrite as a new dependency so the backend can proxy user data:

```bash
# On OCI VM, install Appwrite Python SDK
docker exec vlegal-backend uv add appwrite
docker restart vlegal-backend
```

Or add to your local `pyproject.toml` before rebuilding:

```toml
appwrite = "^6.0.0"
```

### Environment Variables for OCI Backend

Set these in `deploy/oci/.env`:

```env
VLEGAL_APPWRITE_ENDPOINT=https://cloud.appwrite.io/v1
VLEGAL_APPWRITE_PROJECT_ID=your_project_id
VLEGAL_APPWRITE_DATABASE_ID=vlegal
VLEGAL_APPWRITE_API_KEY=your_api_key
```

---

## Part 3: Generate Type-Safe Appwrite SDK

From your local machine with the Appwrite CLI configured:

```bash
appwrite generate --language typescript --output ./src/generated
```

This generates `types.ts`, `databases.ts`, and `constants.ts`.

For Python backend, generate the Python SDK:

```bash
appwrite generate --language python --output ./src/generated
```

### Appwrite SDK Usage

**Frontend (browser identity only):**

The current frontend does not call Appwrite directly. It keeps a stable anonymous id in first-party storage and sends that id to the FastAPI backend.

```javascript
function getUserId() {
  let uid = localStorage.getItem("vlegal_user_id");
  if (!uid) {
    uid = crypto.randomUUID();
    localStorage.setItem("vlegal_user_id", uid);
  }
  return uid;
}

fetch("/api/tracked/123", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "x-user-id": getUserId(),
  },
  credentials: "same-origin",
  body: JSON.stringify({ tracked: true }),
});
```

**Backend (proxy for tracked documents):**

The current app keeps Appwrite credentials on the FastAPI backend and proxies tracked-law and research-view calls server-side.

```python
# src/vlegal_prototype/appwrite_client.py
from vlegal_prototype.appwrite_client import get_tables_db

tdb = get_tables_db()
```

---

## Part 4: Netlify Frontend

### 4.1 Prepare the Frontend Build

The current Netlify setup is proxy-only.

Netlify does not pre-render the Jinja templates into static HTML. Instead, it:

1. publishes the `static/` directory for assets and fallback redirect rules
2. proxies document and API routes to the public OCI backend

The repo already includes a working `netlify.toml` for this shape.

Add a `netlify.toml` at the repo root:

```toml
[build]
  command = "echo 'Jinja app served by OCI backend - Netlify acts as proxy/edge'"
  publish = "static"

[[redirects]]
  from = "/api/*"
  to = "https://your-public-oci-host.example.com/api/:splat"
  status = 200

[[redirects]]
  from = "/*"
  to = "https://your-public-oci-host.example.com/:splat"
  status = 200
```

This makes Netlify a pure proxy/edge layer in front of your OCI backend.

### 4.2 Deploy to Netlify

```bash
# Install Netlify CLI
npm install -g netlify-cli

# Login
netlify login

# Deploy
netlify deploy --prod --dir .
```

Or connect via GitHub in the Netlify UI.

### 4.3 Set Environment Variables in Netlify

No Netlify runtime environment variables are required for the current proxy-only frontend.

The current site behavior is driven by `netlify.toml` redirects and the OCI backend configuration.

If you later parameterize the backend origin in a build step, you can add custom frontend env vars then.

For the current repo, focus on the backend env vars instead:

```env
VLEGAL_PUBLIC_BASE_URL=https://your-oci-backend-url.com
VLEGAL_CORS_ALLOWED_ORIGINS=https://your-netlify-url.netlify.app
```

---

## Part 5: Migrating Tracked Documents from SQLite to Appwrite

If you already have tracked documents in the OCI SQLite and want to move them to Appwrite:

```bash
# Export from SQLite on OCI VM
docker exec vlegal-backend uv run python -c "
import sqlite3, json
conn = sqlite3.connect('/app/data/full_hf.sqlite')
rows = conn.execute('SELECT user_id, document_id, document_title, document_number, tracked_at FROM tracked_documents').fetchall()
for r in rows:
    print(json.dumps(r))
conn.close()
" > tracked_export.json
```

Then use the Appwrite CLI to bulk import, or write a small migration script.

---

## Part 6: Architecture Summary

```
Browser (Netlify CDN)
  |
  |  Static assets + edge redirects
  |  First-party user id cookie / mirrored localStorage id
  |
  +---> OCI FastAPI (port 8000) ---------> SQLite (focused corpus)
  |         |                                  |
  |         |  /api/search                      |
  |         |  /api/documents/{id}              |
  |         |  /api/compare/{l}/{r}             |
  |         |  /api/citations/{id}              |
  |         |  /api/relations/{id}              |
  |                                           |
  +---> Appwrite (user data) <----------------+
            tracked_documents
            research_views
```

---

## Part 7: Environment Variable Reference

### OCI Backend `.env`

```env
PORT=8000
VLEGAL_ENVIRONMENT=production
VLEGAL_PUBLIC_BASE_URL=https://your-oci-backend-url.com
VLEGAL_DATABASE_PATH=/app/data/full_hf.sqlite
VLEGAL_CORS_ALLOWED_ORIGINS=https://your-netlify-url.netlify.app

# Appwrite (server-side)
VLEGAL_APPWRITE_ENDPOINT=https://cloud.appwrite.io/v1
VLEGAL_APPWRITE_PROJECT_ID=your_project_id
VLEGAL_APPWRITE_DATABASE_ID=vlegal
VLEGAL_APPWRITE_API_KEY=your_api_key
```

### Netlify Environment Variables

```env
# None required for the current proxy-only setup.
```

---

## Troubleshooting

### Appwrite CORS errors

In Appwrite Console → Users → Settings, add your Netlify domain to allowed origins.

### Backend can't reach Appwrite

Verify the `VLEGAL_APPWRITE_*` variables are set correctly on the OCI backend:

```bash
docker exec vlegal-backend env | grep VLEGAL_APPWRITE
```

### Tracked documents not showing

Check that the anonymous user ID is being persisted and sent correctly. Open browser DevTools and verify:

- the `vlegal_user_id` cookie exists
- `localStorage["vlegal_user_id"]` exists
- requests to `/api/tracked/...` include the `x-user-id` header

### Netlify 404 on page reload

Keep the redirect rules in both places used by this repo:

- `netlify.toml` for the primary site configuration
- `static/_redirects` for manual Netlify deploys that rely on the publish directory contents

The fallback `_redirects` file should include:

```
/*    /index.html   200
```
