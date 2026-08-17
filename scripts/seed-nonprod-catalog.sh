#!/usr/bin/env bash
# Idempotently seed the SmartRetailX product catalogue and matching inventory
# stock for a non-production environment.
#
# Uses the same admin HTTP surface that the SmartRetailX application exposes
# in production (POST/PUT /v1/products, PATCH /v1/inventory/{id}).  This
# proves the admin surface works end-to-end and avoids introducing any new
# infrastructure or bypass path into the databases.
#
# Guards on ENVIRONMENT_NAME: refuses to run against production, baseline or
# development.  A regression test locks this guard.
#
# Required environment (all supplied by the bound GitHub Environment):
#   ENVIRONMENT_NAME  - 'test' or 'staging'
#   API_BASE_URL      - CloudFront/API base URL for the environment
#   ADMIN_TOKEN       - short-lived admin Cognito access token (already minted
#                       by ./scripts/obtain-cognito-token.sh ADMIN)
set -euo pipefail

: "${ENVIRONMENT_NAME:?ENVIRONMENT_NAME is required}"
: "${API_BASE_URL:?API_BASE_URL is required}"
: "${ADMIN_TOKEN:?ADMIN_TOKEN is required}"

case "$ENVIRONMENT_NAME" in
  test|staging)
    ;;
  *)
    echo "REFUSED: seed-nonprod-catalog.sh must never run for '$ENVIRONMENT_NAME'" >&2
    exit 2
    ;;
esac

# Canonical synthetic catalogue.  Values intentionally mirror the LocalStack
# fixture so developer laptops and non-production environments demonstrate
# the same behaviour.  Stock quantities are generous enough for browser E2E
# and API contract flows to CONFIRM orders.
readarray -t CATALOGUE <<'CATALOG'
prod-laptop-001|MacBook Pro 14|1299.99|Electronics|50
prod-mouse-002|Magic Mouse|79.99|Accessories|150
prod-monitor-003|4K Monitor 27inch|599.99|Electronics|40
prod-keyboard-004|Mechanical Keyboard|149.99|Accessories|200
prod-headset-005|Noise Cancelling Headphones|349.99|Electronics|80
CATALOG

http_upsert_product() {
  local id="$1" name="$2" price="$3" category="$4"
  local body
  body=$(printf '{"productId":"%s","productName":"%s","price":"%s","category":"%s"}' \
    "$id" "$name" "$price" "$category")
  # Try POST first (idempotent-friendly), fall back to PUT if it already exists.
  local status
  status=$(curl --silent --show-error --output /tmp/seed-body -w "%{http_code}" \
    -X POST "$API_BASE_URL/v1/products" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    --data-binary "$body")
  case "$status" in
    201) echo "  product created: $id" ;;
    409|400)
      # Already exists (or existed) -> PUT the same body to converge.
      local put_body
      put_body=$(printf '{"productName":"%s","price":"%s","category":"%s"}' \
        "$name" "$price" "$category")
      local put_status
      put_status=$(curl --silent --show-error --output /tmp/seed-body -w "%{http_code}" \
        -X PUT "$API_BASE_URL/v1/products/$id" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        --data-binary "$put_body")
      case "$put_status" in
        200) echo "  product converged: $id" ;;
        *) echo "  ERROR: PUT /v1/products/$id returned $put_status"; cat /tmp/seed-body; exit 1 ;;
      esac
      ;;
    *) echo "  ERROR: POST /v1/products returned $status for $id"; cat /tmp/seed-body; exit 1 ;;
  esac
}

http_upsert_stock() {
  local id="$1" quantity="$2"
  local body
  body=$(printf '{"quantity":%s}' "$quantity")
  local status
  status=$(curl --silent --show-error --output /tmp/seed-body -w "%{http_code}" \
    -X PATCH "$API_BASE_URL/v1/inventory/$id" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    --data-binary "$body")
  case "$status" in
    200) echo "  stock converged: $id => $quantity" ;;
    *) echo "  ERROR: PATCH /v1/inventory/$id returned $status"; cat /tmp/seed-body; exit 1 ;;
  esac
}

echo "Seeding canonical catalogue into environment: $ENVIRONMENT_NAME"
for row in "${CATALOGUE[@]}"; do
  IFS='|' read -r id name price category qty <<<"$row"
  http_upsert_product "$id" "$name" "$price" "$category"
  http_upsert_stock   "$id" "$qty"
done
echo "Seed complete."

# Validate the seed by asking the same public catalogue endpoint that smoke
# and browser E2E use.  Never dump customer-derived attributes.
seen=$(curl --silent --show-error \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_BASE_URL/v1/products?limit=100" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('products',[])))")
echo "Post-seed catalogue product count: $seen"
[[ "$seen" -ge 5 ]] || { echo "ERROR: expected >=5 products, saw $seen"; exit 1; }
