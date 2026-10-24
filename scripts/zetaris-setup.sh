#!/usr/bin/env bash
# Wire RecoveryPact to a local Zetaris platform bundle (zetaris-platform.zip). Idempotent.
#
#   1. creates the rp-bridge network and attaches the Zetaris driver and UI to it
#   2. copies the change-calendar CSV into the Zetaris file root
#   3. starts RecoveryPact with the Zetaris overlay
#   4. registers the three business sources in Zetaris and runs a federated join
#
# Needs ZETARIS_EMAIL and ZETARIS_PASSWORD in .env (the bundle default is
# admin@zetaris.com / Zetaris1@ until you change it).
set -euo pipefail
cd "$(dirname "$0")/.."

DRIVER=${ZETARIS_DRIVER_CONTAINER:-zetaris-driver-1}
UI=${ZETARIS_UI_CONTAINER:-zetaris-ui-1}

for c in "$DRIVER" "$UI"; do
  docker inspect "$c" >/dev/null 2>&1 || { echo "Zetaris container $c is not running. Start the Zetaris bundle first."; exit 1; }
done

docker network inspect rp-bridge >/dev/null 2>&1 || docker network create rp-bridge >/dev/null
for c in "$DRIVER" "$UI"; do
  docker network connect rp-bridge "$c" 2>/dev/null || true
done
echo "network rp-bridge: $DRIVER, $UI attached"

docker exec "$DRIVER" mkdir -p /home/zetaris/customer-data/shared/recoverypact
docker cp seed/business/change_calendar.csv "$DRIVER":/home/zetaris/customer-data/shared/recoverypact/change_calendar.csv
echo "calendar CSV copied into the Zetaris file root"

docker compose -f compose.yaml -f compose.zetaris.yaml up -d --build
# Attach by container name only (no "api"/"postgres" aliases that would shadow Zetaris's own).
for svc in postgres api; do
  cid=$(docker compose ps -q "$svc")
  docker network connect rp-bridge "$cid" 2>/dev/null || true
done
echo "waiting for the API..."
for _ in $(seq 1 60); do
  docker compose exec -T api python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')" 2>/dev/null && break
  sleep 2
done

docker compose exec -T api python -m app.integrations.zetaris.setup
# The Unified Semantic Layer recovery_business and its data-quality rules (usl.sql). Use it with
# ZETARIS_QUERY_LAYER=usl in .env: registry answers then carry Zetaris's DQ verdict (invariant I9).
docker compose exec -T api python -m app.integrations.zetaris.setup --usl
echo "done: open http://localhost:${UI_PORT:-8080} and check the Zetaris chip says 'live federation'"
