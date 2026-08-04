#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

mkdir -p reports

echo -e "${GREEN}Starting Coverage Report Generation...${NC}"

SUMMARY_FILE="reports/coverage-summary.txt"
echo "Service | Statements | Missed | Coverage %" > "$SUMMARY_FILE"
echo "------------------------------------------" >> "$SUMMARY_FILE"

SERVICES=(
  "services/product-service"
  "services/order-service"
  "services/inventory-service"
  "services/auth-service"
  "services/payment-service"
  "services/notification-service"
  "services/user-service"
  "services/cart-service"
  "services/search-service"
  "services/review-service"
  "common"
)

for svc in "${SERVICES[@]}"; do
  if [ -d "$svc" ]; then
    echo -e "${YELLOW}Testing $svc...${NC}"
    pushd "$svc" >/dev/null
    # Run pytest and output coverage to terminal and HTML
    if pytest --cov=. --cov-report=term --cov-report=html > coverage_out.txt || true; then
      TOTAL_LINE=$(grep -E "^TOTAL" coverage_out.txt || echo "TOTAL 0 0 0%")
      STMT=$(echo "$TOTAL_LINE" | awk '{print $2}')
      MISS=$(echo "$TOTAL_LINE" | awk '{print $3}')
      COV=$(echo "$TOTAL_LINE" | awk '{print $4}')
      
      echo "$(basename "$svc") | $STMT | $MISS | $COV" >> "../$SUMMARY_FILE"
      mv htmlcov "../reports/$(basename "$svc")-htmlcov"
    fi
    rm -f coverage_out.txt
    popd >/dev/null
  fi
done

cat "$SUMMARY_FILE"

echo -e "${YELLOW}-------------------------------------------------------"
echo -e "Instructions for Evidence:"
echo -e "1. Screenshot the coverage summary table."
echo -e "2. Include the reports/ HTML coverage directories in deliverables if required."
echo -e "-------------------------------------------------------${NC}"
