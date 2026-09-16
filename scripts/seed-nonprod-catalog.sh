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
  development|test|staging)
    ;;
  *)
    echo "REFUSED: seed-nonprod-catalog.sh must never run for '$ENVIRONMENT_NAME'" >&2
    exit 2
    ;;
esac

# Canonical synthetic catalogue.  Values intentionally mirror the LocalStack
# fixture so developer laptops and non-production environments demonstrate
# the same behaviour.  Stock quantities are generous enough for browser E2E
# and API contract flows to CONFIRM orders.  Descriptions are per-product
# so the UI no longer shows the same placeholder on every card.
readarray -t CATALOGUE <<'CATALOG'
prod-laptop-001|MacBook Pro 14|1299.99|Electronics|50|14-inch Apple Silicon laptop with 16 GB unified memory, 512 GB SSD and Liquid Retina XDR display.
prod-mouse-002|Magic Mouse|79.99|Accessories|150|Wireless multi-touch mouse with rechargeable battery and 30-day standby.
prod-monitor-003|4K Monitor 27inch|599.99|Electronics|40|27-inch 4K UHD IPS display with HDR400, USB-C 90 W power delivery and factory colour calibration.
prod-keyboard-004|Mechanical Keyboard|149.99|Accessories|200|Full-size mechanical keyboard with hot-swappable switches, per-key RGB backlighting and USB-C connectivity.
prod-headset-005|Noise Cancelling Headphones|349.99|Electronics|80|Over-ear noise cancelling headphones with 30-hour battery life, spatial audio and travel case.
prod-tablet-006|iPad Air 11|799.99|Electronics|35|11-inch Liquid Retina display with M2 chip, 128 GB storage and Apple Pencil support.
prod-charger-007|USB-C Fast Charger|39.99|Accessories|300|65 W GaN USB-C charger with dual-port output and foldable prongs for travel.
prod-webcam-008|HD Webcam Pro|129.99|Electronics|3|1080p HD webcam with built-in ring light, auto-focus and noise-reducing dual microphone.
prod-stand-009|Laptop Stand Aluminium|49.99|Accessories|0|Adjustable aluminium laptop stand with ventilated design and cable management channel.
prod-speaker-010|Portable Bluetooth Speaker|89.99|Electronics|120|IPX7 waterproof Bluetooth 5.3 speaker with 20-hour battery and 360-degree sound.
prod-hub-011|USB-C Hub 7-in-1|59.99|Accessories|4|7-in-1 USB-C hub with HDMI 4K, SD card reader, 3x USB-A and 100 W pass-through charging.
prod-cable-012|Braided USB-C Cable 2m|14.99|Accessories|500|Nylon braided USB-C to USB-C cable rated for 100 W PD and 10 Gbps data transfer.
prod-ssd-013|Portable SSD 1TB|109.99|Electronics|25|1 TB external NVMe SSD with USB-C, 1050 MB/s read speed and shock-resistant casing.
prod-earbuds-014|Wireless Earbuds Pro|179.99|Electronics|2|Active noise cancelling true wireless earbuds with 8-hour playtime and wireless charging case.
prod-mousepad-015|Desk Mat XL|29.99|Accessories|0|Extra-large 900x400 mm desk mat with stitched edges, non-slip rubber base and water-resistant surface.
prod-tracker-016|Bluetooth Tracker 4-Pack|99.99|Accessories|60|Ultra-thin Bluetooth item trackers with replaceable battery, crowd-find network and 60 m range.
prod-router-017|Wi-Fi 6E Mesh Router|249.99|Electronics|15|Tri-band Wi-Fi 6E mesh router covering 5000 sq ft with 2.5 Gbps wired backhaul port.
prod-powerbank-018|Power Bank 20000mAh|44.99|Accessories|1|20000 mAh portable power bank with 65 W USB-C output, LED display and airline-approved capacity.
prod-stylus-019|Digital Stylus Pen|69.99|Accessories|90|Pressure-sensitive digital stylus with tilt support, magnetic attachment and USB-C quick charge.
prod-camera-020|Action Camera 4K|199.99|Electronics|5|4K 60fps action camera with electronic image stabilisation, 10 m waterproofing and voice control.
CATALOG

http_upsert_product() {
  local id="$1" name="$2" price="$3" category="$4" description="$5"
  local body
  body=$(python3 -c 'import json,sys; print(json.dumps({"productId":sys.argv[1],"productName":sys.argv[2],"price":sys.argv[3],"category":sys.argv[4],"description":sys.argv[5]}))' \
    "$id" "$name" "$price" "$category" "$description")
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
      put_body=$(python3 -c 'import json,sys; print(json.dumps({"productName":sys.argv[1],"price":sys.argv[2],"category":sys.argv[3],"description":sys.argv[4]}))' \
        "$name" "$price" "$category" "$description")
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
  IFS='|' read -r id name price category qty description <<<"$row"
  http_upsert_product "$id" "$name" "$price" "$category" "$description"
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
