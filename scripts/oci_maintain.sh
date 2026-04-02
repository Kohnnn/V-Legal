#!/bin/bash
# V-Legal OCI Maintenance Script
# Usage: ./oci_maintain.sh [command]
#
# Commands:
#   status     - Check container and database status
#   logs       - View container logs (last 50 lines)
#   restart    - Restart the backend container
#   rebuild    - Rebuild and redeploy the container
#   backup     - Create a timestamped database backup
#   health     - Run health checks
#   bootstrap  - Run full bootstrap (taxonomy + relations + citations)
#   stats      - Show database statistics

set -e

CONTAINER="vlegal-backend"
DATA_DIR="/opt/vlegal/data"
DB_PATH="$DATA_DIR/full_hf.sqlite"
APP_DIR="/home/ubuntu/V-Legal"
COMPOSE_FILE="$APP_DIR/deploy/oci/docker-compose.yml"
ENV_FILE="$APP_DIR/deploy/oci/.env"

command="$1"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

case "$command" in
    status)
        log "=== Container Status ==="
        docker ps | grep -E "vlegal|caddy" || echo "No V-Legal containers running"

        log "=== Database ==="
        if [ -f "$DB_PATH" ]; then
            SIZE=$(du -h "$DB_PATH" | cut -f1)
            COUNT=$(docker exec $CONTAINER uv run python -c "
                import sqlite3
                conn = sqlite3.connect('/app/data/full_hf.sqlite')
                c = conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0]
                print(c)
                conn.close()
            " 2>/dev/null || echo "N/A")
            echo "Database: $DB_PATH (${SIZE}, ${COUNT} docs)"
        else
            echo "Database not found at $DB_PATH"
        fi

        log "=== Disk Usage ==="
        df -h "$DATA_DIR" | tail -1
        ;;

    logs)
        log "=== Container Logs (last 50 lines) ==="
        docker logs $CONTAINER --tail 50
        ;;

    restart)
        log "Restarting $CONTAINER..."
        docker restart $CONTAINER
        sleep 3
        log "Done. Health: $(curl -s http://127.0.0.1:8000/health 2>/dev/null || echo 'FAILED')"
        ;;

    rebuild)
        log "Rebuilding and redeploying..."
        cd "$APP_DIR"
        docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build
        sleep 5
        log "Done. Health: $(curl -s http://127.0.0.1:8000/health 2>/dev/null || echo 'FAILED')"
        ;;

    backup)
        if [ ! -f "$DB_PATH" ]; then
            echo "Database not found at $DB_PATH"
            exit 1
        fi
        TIMESTAMP=$(date +%Y%m%d-%H%M%S)
        BACKUP_PATH="${DB_PATH}.backup-${TIMESTAMP}"
        log "Backing up database to $BACKUP_PATH..."
        sudo cp "$DB_PATH" "$BACKUP_PATH"
        log "Backup complete: $BACKUP_PATH"
        echo ""
        log "Available backups:"
        ls -lh "${DB_PATH}.backup-"* 2>/dev/null | tail -5
        ;;

    health)
        log "=== Local Health ==="
        LOCAL=$(curl -s http://127.0.0.1:8000/health 2>/dev/null || echo '{"error":"failed"}')
        echo "Local:  $LOCAL"

        log "=== Public Health ==="
        PUBLIC=$(curl -s https://vlegal.213.35.101.237.sslip.io/health 2>/dev/null || echo '{"error":"failed"}')
        echo "Public: $PUBLIC"
        ;;

    bootstrap)
        log "Running full bootstrap..."
        log "1. Taxonomy..."
        docker exec $CONTAINER uv run python scripts/bootstrap_phapdien_taxonomy.py --seed-only

        log "2. Relationship graph..."
        docker exec $CONTAINER uv run python scripts/bootstrap_relationship_graph.py

        log "3. Citation index..."
        docker exec $CONTAINER uv run python scripts/bootstrap_citation_index.py

        log "Bootstrap complete."
        ;;

    stats)
        log "=== Database Statistics ==="
        docker exec $CONTAINER uv run python -c "
import sqlite3
conn = sqlite3.connect('/app/data/full_hf.sqlite')

def count(table):
    c = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    print(f'  {table}: {c:,}')

print('Documents:')
count('documents')

print('Taxonomy:')
count('taxonomy_subjects')

print('Relations:')
count('document_relations')

print('Citations:')
count('citation_links')

conn.close()
"
        ;;

    *)
        echo "V-Legal OCI Maintenance Script"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  status    - Check container and database status"
        echo "  logs      - View container logs (last 50 lines)"
        echo "  restart   - Restart the backend container"
        echo "  rebuild   - Rebuild and redeploy the container"
        echo "  backup    - Create a timestamped database backup"
        echo "  health    - Run health checks (local + public)"
        echo "  bootstrap - Run full bootstrap (taxonomy + relations + citations)"
        echo "  stats     - Show database statistics"
        echo ""
        ;;
esac
