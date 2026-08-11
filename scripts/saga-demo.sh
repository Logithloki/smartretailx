#!/usr/bin/env bash
# Local end-to-end saga demo (Week 3 Day 5 gate).
#
#   docker compose up -d --build
#   ./scripts/saga-demo.sh
#
# Proves both directions of the choreographed saga (ADR-06) against LocalStack
# and Postgres 16 - no AWS involved:
#
#   HAPPY  order -> SQS -> inventory reserves in Postgres -> SNS order-confirmed
#          -> order-events -> order flips PENDING to CONFIRMED
#   COMP   order for more stock than exists -> SNS order-rejected
#          -> order flips PENDING to REJECTED with a reason, stock untouched
set -uo pipefail

ORDER=http://localhost:8001
INVENTORY=http://localhost:8002
ADMIN_TOKEN="$(python - <<'PY'
import jwt
print(jwt.encode({"sub": "demo-admin", "cognito:username": "admin",
                  "cognito:groups": ["customer", "admin"]}, "unused", algorithm="HS256"))
PY
)"
AUTH=(-H "Authorization: Bearer $ADMIN_TOKEN")

say() { printf '\n=== %s ===\n' "$1"; }
status_of() { curl -s "$ORDER/v1/orders/$1" "${AUTH[@]}" | python -c "import sys,json;d=json.load(sys.stdin);print(d['status'], '|', d.get('statusReason') or '-')"; }
stock_of()  { curl -s "$INVENTORY/v1/inventory/$1" "${AUTH[@]}" | python -c "import sys,json;print(json.load(sys.stdin)['quantity'])" 2>/dev/null || echo "n/a"; }

place_order() { # product qty -> orderId (exits on anything but 201)
  local body http
  body="$(curl -s -w '\n%{http_code}' -X POST "$ORDER/v1/orders" \
    -H "Content-Type: application/json" "${AUTH[@]}" \
    -d "{\"items\":[{\"productId\":\"$1\",\"quantity\":$2}]}")"
  http="$(printf '%s' "$body" | tail -n1)"
  body="$(printf '%s' "$body" | sed '$d')"
  if [ "$http" != "201" ]; then
    echo "FAILED: POST /v1/orders returned $http: $body" >&2
    exit 1
  fi
  printf '%s' "$body" | python -c "import sys,json;print(json.load(sys.stdin)['orderId'])"
}

wait_for_status() { # orderId expected
  for _ in $(seq 1 30); do
    current="$(curl -s "$ORDER/v1/orders/$1" "${AUTH[@]}" | python -c "import sys,json;print(json.load(sys.stdin)['status'])")"
    [ "$current" = "$2" ] && return 0
    sleep 1
  done
  return 1
}

say "0. seed stock"
curl -s -X PATCH "$INVENTORY/v1/inventory/prod-laptop-001" -H "Content-Type: application/json" \
  "${AUTH[@]}" -d '{"quantity":10}' >/dev/null
echo "prod-laptop-001 stock = $(stock_of prod-laptop-001)"

say "1. HAPPY PATH - order 3 of 10"
HAPPY="$(place_order prod-laptop-001 3)"
echo "created $HAPPY -> $(status_of "$HAPPY")"
if wait_for_status "$HAPPY" CONFIRMED; then
  echo "settled  $HAPPY -> $(status_of "$HAPPY")"
  echo "stock now = $(stock_of prod-laptop-001)  (expected 7)"
else
  echo "FAILED: $HAPPY never reached CONFIRMED (last: $(status_of "$HAPPY"))"; exit 1
fi

# 50, not 999: a single line item is capped at 100 by Pydantic, so 999 would
# be refused at the edge with 422 and never reach the saga at all.
say "2. COMPENSATION PATH - order 50 of 7"
REJECTED="$(place_order prod-laptop-001 50)"
echo "created $REJECTED -> $(status_of "$REJECTED")"
if wait_for_status "$REJECTED" REJECTED; then
  echo "settled  $REJECTED -> $(status_of "$REJECTED")"
  echo "stock now = $(stock_of prod-laptop-001)  (expected 7, untouched)"
else
  echo "FAILED: $REJECTED never reached REJECTED (last: $(status_of "$REJECTED"))"; exit 1
fi

say "3. summary"
curl -s "$ORDER/v1/orders" "${AUTH[@]}" \
  | python -c "
import sys, json
for o in json.load(sys.stdin)['orders']:
    print(f\"{o['orderId']}  {o['status']:<10} {o.get('statusReason') or ''}\")"

say "SAGA DEMO PASSED - both directions"
