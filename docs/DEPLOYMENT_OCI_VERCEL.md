# OCI Backend + Vercel Frontend Guide

This is the recommended deployment shape if you want:

- frontend on Vercel
- backend on OCI free tier
- more durable full-data backend than free app hosts

## Recommended Architecture

- `Vercel` hosts the frontend
- `OCI VM` hosts the FastAPI backend
- backend serves API routes and can still serve pages directly if needed
- data lives on the OCI VM under `data/`

This is a much better fit than a fully free ephemeral app host when you want a larger legal corpus.

## What You Need On OCI

- 1 OCI Always Free VM
- Ubuntu 22.04 or similar
- Docker + Docker Compose plugin
- an open port strategy:
  - either direct public port access, or
  - reverse proxy with domain, recommended

## Backend Requirements Already Added

The backend now supports cross-origin frontend access through:

- `VLEGAL_CORS_ALLOWED_ORIGINS`

Use this for your Vercel frontend origin, for example:

```env
VLEGAL_CORS_ALLOWED_ORIGINS=https://your-frontend.vercel.app,http://localhost:3000
```

## Files Added For OCI

- `deploy/oci/docker-compose.yml`
- `deploy/oci/.env.example`
- `deploy/oci/Caddyfile.example`

## Step 1: Prepare The OCI VM

SSH into your VM and install Docker.

Example high-level flow:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 git
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
```

Reconnect your SSH session after adding your user to the docker group.

## Step 2: Clone The Repo

```bash
git clone <your-repo-url>
cd V-Legal
```

## Step 3: Create The OCI Env File

Copy:

- `deploy/oci/.env.example`

to:

- `deploy/oci/.env`

Then set the important values:

```env
PORT=8000
VLEGAL_ENVIRONMENT=production
VLEGAL_PUBLIC_BASE_URL=https://api.your-domain.com
VLEGAL_CORS_ALLOWED_ORIGINS=https://your-frontend.vercel.app,http://localhost:3000
VLEGAL_DATABASE_PATH=/app/data/vlegal.sqlite
```

If you have multiple Vercel preview domains, add them comma-separated.

## Step 4: Build And Run The Backend

From the repo root:

```bash
docker compose -f deploy/oci/docker-compose.yml --env-file deploy/oci/.env up -d --build
```

This will:

- build the Docker image
- create the `500`-document demo bundle during build
- start the backend on port `8000`

## Step 5: Verify The Backend

From the OCI VM:

```bash
curl http://127.0.0.1:8000/health
```

You should get JSON like:

```json
{"status":"ok","documents":500}
```

Also test:

- `/tracking`
- `/compare/447330/367747`

## Step 6: Route V-Legal Through The Existing Caddy Proxy

The OCI VM already runs `vnibb-caddy` (Caddy) on ports 80/443. V-Legal can share that Caddy by adding a subdomain block.

The Caddyfile lives at `/srv/vnibb/deployment/Caddyfile` on the VM (mounted into the `vnibb-caddy` container).

### 6a. Update The Caddyfile

Add this block to the existing Caddyfile:

```caddy
vlegal.{$SITE_HOSTNAME} {
    encode gzip zstd
    reverse_proxy vlegal-backend:8000
}
```

`$SITE_HOSTNAME` is already set in the Caddy container's environment (e.g. `213.35.101.237.sslip.io`).

Then restart Caddy:

```bash
docker restart vnibb-caddy
```

This provisions a Let's Encrypt certificate for `vlegal.{$SITE_HOSTNAME}` automatically and adds HTTPS.

### 6b. Make The Network Connection Persistent

The `vlegal-backend` container must be on the same Docker network as Caddy. Update `deploy/oci/docker-compose.yml` to include the external `vnibb_default` network:

```yaml
services:
  vlegal-backend:
    ...
    networks:
      - vnibb_default

networks:
  vnibb_default:
    external: true
```

Then on every deploy, the container will be on the correct network.

### 6c. Verify

```bash
curl https://vlegal.213.35.101.237.sslip.io/health
# {"status":"ok","documents":10000}
```

Public URL: `https://vlegal.213.35.101.237.sslip.io`

This gives you:

- HTTPS with auto-provisioned certificate
- stable API origin for frontend
- `http://` redirects to `https://` automatically

## Step 7: Configure The Vercel Frontend

In Vercel, set your frontend env var to the V-Legal backend public URL.

```env
NEXT_PUBLIC_API_BASE_URL=https://vlegal.213.35.101.237.sslip.io
```

Or for a custom domain, use:

```env
NEXT_PUBLIC_API_BASE_URL=https://api.your-domain.com
```

Then make the frontend call:

- `/api/search`
- `/api/ask`
- `/api/citations/{id}`
- `/api/relations/{id}`
- `/api/compare/{left}/{right}`
- `/api/tracked`
- `/api/tracked/{id}`

## Step 8: Open OCI Network Rules

On OCI, allow inbound traffic for:

- `80`
- `443`

If you expose the app directly without Caddy, also allow:

- `8000`

But using a reverse proxy on `80/443` is better.

## Persistent Data Notes

Compared with Render free, OCI is much better because:

- your VM filesystem is not ephemeral in the same way
- tracked laws and saved research views can persist
- you can grow the corpus more safely

But you should still:

- back up `data/vlegal.sqlite`
- not rely on a single VM forever

## Upgrading Beyond The Demo Bundle

Right now the Docker build still uses:

- `VLEGAL_BOOTSTRAP_LIMIT=500`

For a bigger backend on OCI, you have two options.

### Option A: keep Docker build small, import later on the VM

This is safer.

Start with the working backend, then run:

```bash
docker exec -it vlegal-backend uv run python scripts/bootstrap_hf_dataset.py --skip 500 --limit 5000
```

Repeat in chunks.

### Option B: build a larger image

You can change the compose build arg:

```yaml
args:
  VLEGAL_BOOTSTRAP_LIMIT: 5000
```

But this makes build time and image size larger.

My recommendation: `Option A`.

## Recommended First OCI Flow

1. deploy the current `500`-doc backend
2. connect the Vercel frontend
3. verify CORS works
4. expand the corpus gradually on the OCI VM
5. later decide whether to stay on SQLite or move to Postgres

## Full-Corpus OCI Deployment (Persistent Disk)

This section covers deploying with the full `full_hf.sqlite` corpus on a persistent volume.

### Architecture Summary

- Backend on OCI free tier VM
- Data directory: `/opt/vlegal/data` on a bind-mounted host path
- SQLite database `full_hf.sqlite` (10,000 documents, ~0 taxonomy subjects) lives on persistent disk
- Docker compose uses a named volume that binds to `/opt/vlegal/data` on the host

### Step 1: Create The Data Directory On OCI

SSH into your VM and create the data directory:

```bash
sudo mkdir -p /opt/vlegal/data
sudo chown -R $(whoami):$(whoami) /opt/vlegal/data
```

### Step 2: Copy `full_hf.sqlite` To OCI

From your **local** machine (adjust the path to your OCI VM):

```bash
# Using scp directly via OCI_SSH_CONNECT env var reference
scp data/full_hf.sqlite user@your-oci-vm:/opt/vlegal/data/full_hf.sqlite
```

Or if `OCI_SSH_CONNECT` is set in your shell:

```bash
HOST=$(echo $OCI_SSH_CONNECT | cut -d@ -f2)
scp data/full_hf.sqlite $OCI_SSH_CONNECT:/opt/vlegal/data/full_hf.sqlite
```

### Step 3: Seed Taxonomy And Rebuild Graphs On OCI

The `full_hf.sqlite` has no taxonomy subjects. Run these inside the container:

```bash
# Start the container first
docker compose -f deploy/oci/docker-compose.yml --env-file deploy/oci/.env up -d

# Seed taxonomy from official source
docker exec vlegal-backend uv run python scripts/bootstrap_phapdien_taxonomy.py --seed-only

# Rebuild relationship graph
docker exec vlegal-backend uv run python scripts/bootstrap_relationship_graph.py

# Rebuild citation index
docker exec vlegal-backend uv run python scripts/bootstrap_citation_index.py
```

This seeds 42 official taxonomy subjects and rebuilds the relationship + citation graphs on the full corpus.

### Step 4: Configure The OCI Env File

Create `deploy/oci/.env`:

```env
PORT=8000
VLEGAL_ENVIRONMENT=production
VLEGAL_PUBLIC_BASE_URL=https://api.your-domain.com
VLEGAL_CORS_ALLOWED_ORIGINS=https://your-frontend.vercel.app,http://localhost:3000
VLEGAL_DATABASE_PATH=/app/data/full_hf.sqlite
```

### Step 5: Run

```bash
docker compose -f deploy/oci/docker-compose.yml --env-file deploy/oci/.env up -d --build
```

Verify:

```bash
curl http://127.0.0.1:8000/health
```

You should see `"documents": 10000` in the response.

### Step 6: Domain / Reverse Proxy

Use Caddy as described in the earlier section. Example `Caddyfile`:

```caddy
api.your-domain.com {
    encode gzip
    reverse_proxy 127.0.0.1:8000
}
```

### Upgrading The Corpus Later

To add more documents to the persistent SQLite:

```bash
docker exec vlegal-backend uv run python scripts/bootstrap_hf_dataset.py --skip 10000 --limit 5000
```

The `--skip 10000` starts after the existing 10,000 documents.

### Backing Up

Back up the persistent SQLite regularly:

```bash
# On OCI VM
sudo cp /opt/vlegal/data/full_hf.sqlite /opt/vlegal/data/full_hf.sqlite.backup-$(date +%Y%m%d)
```

## Troubleshooting

### Frontend gets CORS errors

Check:

- `VLEGAL_CORS_ALLOWED_ORIGINS`
- exact Vercel domain spelling
- whether you are calling `https` from the frontend

### Backend works on VM but not publicly

Check:

- OCI security list / NSG rules
- VM firewall
- reverse proxy config
- DNS record

### Saved views or tracked laws do not persist

Check that the data volume is mounted:

- `../../data:/app/data`

and that `VLEGAL_DATABASE_PATH=/app/data/vlegal.sqlite` is set.

### Need larger corpus later

Do not rebuild from scratch every time.

Import incrementally on the running VM.

## Recommended Positioning For This Stack

- Vercel = frontend delivery
- OCI = durable-ish backend preview / prototype backend

This is the best current architecture for your project without a bigger rewrite.
