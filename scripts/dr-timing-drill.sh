#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

echo -e "${RED}======================================================================${NC}"
echo -e "${RED}WARNING: THIS SCRIPT WILL DESTROY AND RECREATE THE ENTIRE INFRASTRUCTURE!${NC}"
echo -e "${RED}THIS MUST BE THE ABSOLUTE LAST TEST RUN IN WEEK 7!${NC}"
echo -e "${RED}======================================================================${NC}"

read -p "Are you sure you want to proceed? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "Aborting."
  exit 0
fi

pushd ../infra >/dev/null

START_TIME=$(date +%s)
echo -e "${YELLOW}Starting Destroy at $(date)...${NC}"

terraform destroy -auto-approve -var="live=false"
DESTROY_TIME=$(date +%s)
DESTROY_DUR=$((DESTROY_TIME - START_TIME))

echo -e "${GREEN}Destroy completed in $DESTROY_DUR seconds.${NC}"

echo -e "${YELLOW}Starting Apply at $(date)...${NC}"
terraform apply -auto-approve -var="live=true"
APPLY_TIME=$(date +%s)
APPLY_DUR=$((APPLY_TIME - DESTROY_TIME))

TOTAL_RTO=$((APPLY_TIME - START_TIME))
RTO_MIN=$((TOTAL_RTO / 60))
RTO_SEC=$((TOTAL_RTO % 60))

echo -e "${GREEN}Apply completed in $APPLY_DUR seconds.${NC}"

echo -e "${YELLOW}======================================================================${NC}"
echo -e "${GREEN}DR RTO = $RTO_MIN minutes $RTO_SEC seconds${NC}"
echo -e "${YELLOW}======================================================================${NC}"

popd >/dev/null

echo -e "${YELLOW}-------------------------------------------------------"
echo -e "Instructions for Evidence:"
echo -e "1. Screenshot the final RTO output."
echo -e "2. Include the terraform output logs if required."
echo -e "-------------------------------------------------------${NC}"
