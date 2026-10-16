#!/usr/bin/env bash
# Checks a running stack through its gateway: the web app, both services and the
# path split between them. Usage: stack-check.sh [base url]
set -euo pipefail

BASE=${1:-http://localhost:8080}
API=$BASE/api/v1
BODY=$(mktemp)
trap 'rm -f "$BODY"' EXIT

# Health goes to transit; an unauthenticated /users/me answering 401 shows accounts is up.
for i in $(seq 1 90); do
  curl -sf "$API/health" >/dev/null &&
    [[ $(curl -s -o /dev/null -w '%{http_code}' "$API/users/me") == 401 ]] && break
  [[ $i -lt 90 ]] || { echo "FAIL: stack not ready after 180s"; exit 1; }
  sleep 2
done

TOKEN=
expect() {
  local want=$1 method=$2 path=$3 data=${4:-}
  local args=(-s -o "$BODY" -w '%{http_code}' -X "$method" "$BASE$path")
  [[ -n $TOKEN ]] && args+=(-H "Authorization: Bearer $TOKEN")
  [[ -n $data ]] && args+=(-H 'Content-Type: application/json' -d "$data")
  local got
  got=$(curl "${args[@]}" || true)
  if [[ $got != "$want" ]]; then
    echo "FAIL: $method $path: expected $want, got $got"
    head -c 500 "$BODY"; echo
    exit 1
  fi
  echo "ok   $method $path -> $got"
}

expect 200 GET /
expect 200 GET /map
expect 200 GET /api/v1/stations
expect 200 GET /api/v1/lines
expect 200 GET '/api/v1/route/plan?start_lat=36.7997&start_lon=10.1897&end_lat=36.8092&end_lon=10.1340&objective=fastest'
if command -v jq >/dev/null 2>&1; then
  [[ $(jq '.itineraries | length' "$BODY") -gt 0 ]] || { echo "FAIL: no itinerary from Tunis Marine to Le Bardo"; exit 1; }
else
  python -c "import sys,json; d=json.load(open('$BODY')); sys.exit(0 if len(d.get('itineraries',[]))>0 else 1)" || { echo "FAIL: no itinerary from Tunis Marine to Le Bardo"; exit 1; }
fi

EMAIL="stack-$(date +%s)@example.com"
expect 201 POST /api/v1/auth/register "{\"email\":\"$EMAIL\",\"password\":\"test123456\",\"display_name\":\"Stack\"}"
expect 200 POST /api/v1/auth/login "{\"email\":\"$EMAIL\",\"password\":\"test123456\"}"
if command -v jq >/dev/null 2>&1; then
  TOKEN=$(jq -r .token "$BODY")
else
  TOKEN=$(python -c "import sys,json; d=json.load(open('$BODY')); print(d.get('token',''))")
fi
expect 200 GET /api/v1/users/me
expect 201 POST /api/v1/favorites '{"kind":"station","ref_id":"test_station","label":"Test Station"}'
expect 200 GET /api/v1/favorites

echo "Stack check passed"
