# Deployment Guide

This guide covers the safest way to deploy the current V-Legal prototype as a preview app.

If you plan to run frontend on Vercel and backend on OCI, use the dedicated guide:

- `DEPLOYMENT_OCI_VERCEL.md`

The repo is already prepared for:

- Render free web service
- Docker-based deployment

The current deployment shape is intentionally conservative:

- small `500`-document bundle
- SQLite database built at deploy time
- no external database required
- good for demo / preview / internal review

It is not yet a durable production setup for user data.

## Best Option Right Now

Use Render free for the first public preview.

Why:

- lowest setup friction
- `render.yaml` is already included
- build process already creates the demo bundle
- easy to redeploy from GitHub

## What To Expect On Free Tier

The current free-tier deployment is preview-grade.

That means:

- the app can sleep when idle
- cold starts are normal
- tracked laws and saved research views are stored in local SQLite
- local SQLite changes can be lost after restart or redeploy on ephemeral hosting

So the app is good for:

- demos
- design review
- feature validation
- internal testing

It is not yet good for:

- durable user accounts
- persistent alerts
- long-term saved workspaces

## Pre-Deploy Checklist

Before deploying, verify locally:

```bash
uv sync
uv run python scripts/prepare_demo_bundle.py --limit 500 --seed-only-taxonomy
uv run uvicorn vlegal_prototype.app:app --app-dir src
```

Open:

- `http://127.0.0.1:8000`

Check these pages:

- `/`
- `/tracking`
- one `/documents/{id}` page
- one `/compare/{left}/{right}` page
- `/health`

If local preview works, deploying should be straightforward.

## Deploy To Render

### 1. Push the repo to GitHub

From your local repo:

```bash
git status
git add .
git commit -m "Prepare deployment guide and preview workflow"
git push
```

If you do not want to commit yet, you can still deploy later after pushing when ready.

### 2. Create a Render web service

In Render:

1. Sign in to Render
2. Click `New +`
3. Choose `Web Service`
4. Connect your GitHub repo
5. Select this repository

### 3. Let Render use `render.yaml`

This repo already includes:

- `render.yaml`

Current config:

- runtime: `python`
- plan: `free`
- health check: `/health`
- build command:

```bash
pip install uv && uv sync --frozen && uv run python scripts/prepare_demo_bundle.py --limit 500 --seed-only-taxonomy
```

- start command:

```bash
uv run uvicorn vlegal_prototype.app:app --app-dir src --host 0.0.0.0 --port $PORT
```

### 4. Set environment variables

Minimum recommended values:

- `VLEGAL_ENVIRONMENT=production`
- `PYTHON_VERSION=3.12.8`

Optional overrides:

- `VLEGAL_SEARCH_PAGE_SIZE=12`
- `VLEGAL_ANSWER_PASSAGE_LIMIT=6`

You do not need secrets for the current preview deployment.

### 5. Deploy

Start the deploy and wait for:

- dependency install
- demo bundle creation
- service start
- `/health` passing

### 6. Verify after deploy

Open the deployed app and check:

- home page loads
- `/tracking` loads
- tracked-law button works for the current session
- compare page opens
- `/health` returns JSON

## Render Troubleshooting

### Build takes too long

Keep the bundle at `500` docs.

Do not raise the bundle size until the preview is stable.

### App starts but pages are empty

Check Render logs and confirm the build step ran:

```bash
uv run python scripts/prepare_demo_bundle.py --limit 500 --seed-only-taxonomy
```

### Tracking or saved views disappear

That is expected on ephemeral free-tier storage.

This is not a bug in the current preview architecture.

### Cold starts feel slow

That is normal on free tier.

## Deploy With Docker

Use Docker when you want:

- local parity with deploy
- another container host later
- a portable image

### Build locally

```bash
docker build -t v-legal-prototype .
```

### Run locally

```bash
docker run -p 8000:8000 v-legal-prototype
```

Then open:

- `http://127.0.0.1:8000`

### Build with a different bundle size

Keep this small unless you have tested memory and startup time.

```bash
docker build --build-arg VLEGAL_BOOTSTRAP_LIMIT=500 -t v-legal-prototype .
```

## Recommended Deploy Workflow

For now, use this cycle:

1. build and verify locally
2. push to GitHub
3. deploy to Render free
4. verify `/`, `/tracking`, `/documents/{id}`, `/compare/{left}/{right}`, `/health`
5. collect feedback

## When To Upgrade Beyond Free Tier

Move beyond the current preview setup when you need any of these:

- durable tracked laws
- persistent saved research views
- real user workspaces
- larger corpus size
- faster cold starts
- official-source sync jobs

At that point, the next step is usually:

1. persistent database
2. background jobs for ingestion/rebuilds
3. durable alert/event storage

## Recommended First Public Positioning

If you share the deployed app now, describe it as:

- `preview`
- `prototype`
- `HF-bootstrap legal research demo`

Do not position it yet as:

- authoritative legal status engine
- durable personal legal workspace
- complete replacement for official Vietnamese legal databases

## Quick Commands

Local preflight:

```bash
uv sync
uv run python scripts/prepare_demo_bundle.py --limit 500 --seed-only-taxonomy
uv run uvicorn vlegal_prototype.app:app --app-dir src
```

Docker:

```bash
docker build -t v-legal-prototype .
docker run -p 8000:8000 v-legal-prototype
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```
