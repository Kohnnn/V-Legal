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

## Step 6: Put A Domain In Front Of The Backend

Recommended:

- point a subdomain like `api.your-domain.com` to the OCI VM
- use Caddy as reverse proxy

Example Caddy setup:

1. copy `deploy/oci/Caddyfile.example`
2. replace `api.your-domain.com`
3. run Caddy on the VM

Simple Caddy file:

```caddy
api.your-domain.com {
    encode gzip
    reverse_proxy 127.0.0.1:8000
}
```

This gives you:

- HTTPS
- stable API origin for Vercel

## Step 7: Configure The Vercel Frontend

In Vercel, set your frontend env var to the OCI backend base URL.

Typical example:

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
