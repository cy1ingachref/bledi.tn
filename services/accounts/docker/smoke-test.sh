#!/usr/bin/env bash
# Boots the given bledi-server image next to a throwaway Postgres and checks the
# API guarantees end to end. Usage: smoke-test.sh <image>
set -euo pipefail

IMAGE=${1:?usage: smoke-test.sh <image>}
NAME=bledi-smoke-$$
PORT=${SMOKE_PORT:-3000}
API=http://localhost:$PORT/api/v1
# Throwaway credentials for an ephemeral container, not secrets.
PGPASSWORD=smoke-only
APP_PASSWORD=bledi-smoke-only

cleanup() {
  status=$?
  if [[ $status -ne 0 ]]; then
    echo "--- server logs"
    docker logs "$NAME-api" 2>&1 | tail -50 || true
  fi
  docker rm -f "$NAME-api" "$NAME-db" >/dev/null 2>&1 || true
  docker network rm "$NAME" >/dev/null 2>&1 || true
  rm -f "$BODY"
  exit "$status"
}
BODY=$(mktemp)
trap cleanup EXIT

docker network create "$NAME" >/dev/null
docker run -d --name "$NAME-db" --network "$NAME" \
  -e POSTGRES_PASSWORD="$PGPASSWORD" postgres:16-alpine >/dev/null

for i in $(seq 1 60); do
  docker exec "$NAME-db" pg_isready -U postgres -h localhost >/dev/null 2>&1 && break
  [[ $i -lt 60 ]] || { echo "FAIL: postgres not ready after 60s"; exit 1; }
  sleep 1
done

# The app connects as a non-superuser that owns its database, as in production.
docker exec -i "$NAME-db" psql -v ON_ERROR_STOP=1 -U postgres -h localhost >/dev/null <<SQL
CREATE ROLE bledi LOGIN PASSWORD '$APP_PASSWORD';
CREATE DATABASE bledi OWNER bledi;
SQL

docker run -d --name "$NAME-api" --network "$NAME" -p "$PORT:3000" \
  -e DATABASE_URL="postgres://bledi:$APP_PASSWORD@$NAME-db:5432/bledi" \
  -e JWT_SECRET=smoke-only-jwt-secret-not-used-anywhere-real \
  "$IMAGE" >/dev/null

for i in $(seq 1 30); do
  curl -sf "$API/health" >/dev/null && break
  [[ $(docker inspect -f '{{.State.Running}}' "$NAME-api") == true ]] || { echo "FAIL: server exited"; exit 1; }
  [[ $i -lt 30 ]] || { echo "FAIL: server not healthy after 30s"; exit 1; }
  sleep 1
done

TOKEN=

# expect <status> <method> <path> [json body]
expect() {
  local want=$1 method=$2 path=$3 data=${4:-}
  local args=(-s -o "$BODY" -w '%{http_code}' -X "$method" "$API$path")
  [[ -n $TOKEN ]] && args+=(-H "Authorization: Bearer $TOKEN")
  [[ -n $data ]] && args+=(-H 'Content-Type: application/json' -d "$data")
  local got
  got=$(curl "${args[@]}" || true)
  if [[ $got != "$want" ]]; then
    echo "FAIL: $method $path: expected $want, got $got"
    cat "$BODY"; echo
    exit 1
  fi
  echo "ok   $method $path -> $got"
}

expect 401 GET /memories
expect 200 GET /health
expect 404 GET /stations

EMAIL=smoke@example.com
PASSWORD=test123456
expect 201 POST /auth/register "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"display_name\":\"Smoke Test\"}"
expect 200 POST /auth/login "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}"
TOKEN=$(jq -r .token "$BODY")

expect 200 GET /users/me
expect 200 GET /memories

MEMORY='{"lat":36.8,"lon":10.2,"title":"Smoke","media_url":"https://example.com/img.jpg","media_type":"image","visibility":"public","unlock_radius_m":200}'
expect 201 POST /memories "$MEMORY"
MEMORY_ID=$(jq -r .id "$BODY")

expect 200 GET '/memories/nearby?lat=36.8&lon=10.2&radius_m=1000'
if grep -q media_url "$BODY"; then echo "FAIL: nearby exposed media_url"; exit 1; fi

# ~1.1 km north of the pin, outside its 200 m radius.
expect 403 POST "/memories/$MEMORY_ID/unlock" '{"lat":36.81,"lon":10.2}'
if grep -q media_url "$BODY"; then echo "FAIL: a denied unlock leaked media_url"; exit 1; fi

expect 400 GET '/memories/nearby?lat=36.8&lon=10.2&radius_m=999999'
expect 400 POST /memories '{"lat":48.8566,"lon":2.3522,"media_url":"https://example.com/x.jpg","media_type":"image","visibility":"public","unlock_radius_m":200}'

expect 201 POST /favorites '{"kind":"station","ref_id":"test_station","label":"Test Station"}'
expect 200 GET /favorites

EXPIRES=$(date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%SZ)
expect 201 POST /location-shares "{\"lat\":36.8,\"lon\":10.2,\"accuracy_m\":10.0,\"is_active\":true,\"expires_at\":\"$EXPIRES\"}"
expect 400 POST /location-shares '{"lat":36.8,"lon":10.2,"accuracy_m":10.0,"is_active":true}'

echo "Smoke test passed"
