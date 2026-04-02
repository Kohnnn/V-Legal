# OCI Backend Maintenance Guide

This document covers common maintenance tasks for the V-Legal backend running on the OCI free-tier VM.

## VM Access

```bash
[see your .env for SSH connection string]
```

## Container Management

### Check container status

```bash
docker ps | grep vlegal
```

### Restart the backend container

```bash
docker restart vlegal-backend
```

### View logs

```bash
# All logs
docker logs vlegal-backend

# Last 50 lines
docker logs vlegal-backend --tail 50

# Follow in real time
docker logs vlegal-backend -f
```

### Rebuild and redeploy

```bash
cd /home/ubuntu/V-Legal
docker compose -f deploy/oci/docker-compose.yml --env-file deploy/oci/.env up -d --build
```

### Stop the container

```bash
docker stop vlegal-backend
```

## Health Checks

### Local health check

```bash
curl http://127.0.0.1:8000/health
```

### Public health check

```bash
curl https://vlegal.[your-site-hostname]/health
```

Expected response:

```json
{"status":"ok","documents":10000}
```

### Check specific routes

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/documents/1
curl http://127.0.0.1:8000/tracking
```

## Data Management

### Database location

```
/opt/vlegal/data/full_hf.sqlite
```

### Backup the database

```bash
# Create a timestamped backup
sudo cp /opt/vlegal/data/full_hf.sqlite /opt/vlegal/data/full_hf.sqlite.backup-$(date +%Y%m%d-%H%M%S)

# List backups
ls -lh /opt/vlegal/data/full_hf.sqlite.backup-*
```

### Restore from backup

```bash
# Stop container first
docker stop vlegal-backend

# Restore
sudo cp /opt/vlegal/data/full_hf.sqlite.backup-YYYYMMDD-HHMMSS /opt/vlegal/data/full_hf.sqlite

# Start container
docker start vlegal-backend
```

### Check database size

```bash
ls -lh /opt/vlegal/data/full_hf.sqlite
```

### Query document count directly

```bash
docker exec vlegal-backend uv run python -c "
import sqlite3
conn = sqlite3.connect('/app/data/full_hf.sqlite')
cursor = conn.execute('SELECT COUNT(*) FROM documents')
print(cursor.fetchone()[0])
conn.close()
"
```

## Bootstrap / Rebuild Scripts

Run these inside the container using `docker exec vlegal-backend uv run python scripts/...`

### Seed taxonomy (official Phap dien subjects)

```bash
docker exec vlegal-backend uv run python scripts/bootstrap_phapdien_taxonomy.py --seed-only
```

### Rebuild relationship graph

```bash
docker exec vlegal-backend uv run python scripts/bootstrap_relationship_graph.py
```

### Rebuild citation index

```bash
docker exec vlegal-backend uv run python scripts/bootstrap_citation_index.py
```

### Full rebuild order

```bash
docker exec vlegal-backend uv run python scripts/bootstrap_phapdien_taxonomy.py --seed-only
docker exec vlegal-backend uv run python scripts/bootstrap_relationship_graph.py
docker exec vlegal-backend uv run python scripts/bootstrap_citation_index.py
```

## Expanding the Corpus

### Add more documents

```bash
# Get current count first
CURRENT=$(docker exec vlegal-backend uv run python -c "
import sqlite3
conn = sqlite3.connect('/app/data/full_hf.sqlite')
c = conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0]
print(c)
conn.close()
")
echo "Current count: $CURRENT"

# Import next batch (e.g., 5000 more)
docker exec vlegal-backend uv run python scripts/bootstrap_hf_dataset.py --skip $CURRENT --limit 5000
```

### Check import progress

```bash
docker logs vlegal-backend --tail 20 | grep -E "(Importing|Inserted|ERROR)"
```

## Caddy / Reverse Proxy

### Check Caddy status

```bash
docker ps | grep caddy
```

### View Caddy logs

```bash
docker logs vnibb-caddy --tail 50
```

### Restart Caddy (after Caddyfile changes)

```bash
docker restart vnibb-caddy
```

### Verify Caddy routing

```bash
curl -I https://vlegal.[your-site-hostname]/health
```

Should return `HTTP/2 200`.

### Caddyfile location

```
/srv/vnibb/deployment/Caddyfile
```

Edit this file to add/modify routes, then `docker restart vnibb-caddy`.

## System Resource Monitoring

### Disk usage

```bash
df -h /opt/vlegal
```

### Memory usage

```bash
free -h
```

### Docker disk usage

```bash
docker system df
```

## Updating the App Code

### Pull latest from git

```bash
cd /home/ubuntu/V-Legal
git pull
```

### Then rebuild

```bash
docker compose -f deploy/oci/docker-compose.yml --env-file deploy/oci/.env up -d --build
```

## Common Issues

### Container won't start

```bash
# Check logs
docker logs vlegal-backend

# Verify env file exists
cat /home/ubuntu/V-Legal/deploy/oci/.env

# Verify data directory exists
ls -la /opt/vlegal/data/
```

### Database file is empty or wrong size

The named volume bug can cause this. Verify:

```bash
ls -lh /opt/vlegal/data/full_hf.sqlite
```

Should be ~1.5GB. If it's tiny (bytes), the bind mount is broken.

### Caddy returns 502

The backend is not reachable from Caddy. Check:

```bash
# Is backend running?
docker ps | grep vlegal

# Can Caddy reach it?
docker exec vnibb-caddy curl -s http://vlegal-backend:8000/health

# Is network correct?
docker network inspect vnibb_default | grep vlegal
```

### Slow responses

Check resource usage and consider restarting:

```bash
docker restart vlegal-backend
```
