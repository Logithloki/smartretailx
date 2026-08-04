#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

mkdir -p reports

echo -e "${GREEN}Starting Security Scans...${NC}"

echo -e "${YELLOW}Running bandit...${NC}"
if bandit -r services/ -f json -o reports/bandit-report.json; then
  echo -e "${GREEN}Bandit scan passed with no issues.${NC}"
else
  echo -e "${RED}Bandit found issues!${NC}"
fi
bandit -r services/ || true # Print human-readable output to stdout

echo -e "${YELLOW}Running pip-audit for services...${NC}"
for svc in services/*; do
  if [ -d "$svc" ] && [ -f "$svc/requirements.txt" ]; then
    echo "Scanning $svc..."
    pip-audit -r "$svc/requirements.txt" || true
  fi
done

echo -e "${YELLOW}-------------------------------------------------------"
echo -e "Instructions for Evidence:"
echo -e "1. Screenshot the bandit summary output (CRITICAL/HIGH/MEDIUM/LOW)."
echo -e "2. Document any findings and how they were handled/mitigated."
echo -e "3. Include reports/bandit-report.json in deliverables."
echo -e "-------------------------------------------------------${NC}"
