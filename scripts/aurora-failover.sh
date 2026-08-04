#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

CLUSTER_ID="smartretailx-inventory"

echo -e "${GREEN}Starting Aurora Failover Test for cluster $CLUSTER_ID...${NC}"

echo -e "${YELLOW}Getting current cluster status...${NC}"
CURRENT_WRITER=$(aws rds describe-db-clusters --db-cluster-identifier "$CLUSTER_ID" --query 'DBClusters[0].DBClusterMembers[?IsClusterWriter==`true`].DBInstanceIdentifier' --output text)
echo -e "Current Writer: ${GREEN}$CURRENT_WRITER${NC}"

echo -e "${RED}Triggering failover...${NC}"
aws rds failover-db-cluster --db-cluster-identifier "$CLUSTER_ID"

echo -e "${YELLOW}Polling cluster status (every 10s for up to 3 mins)...${NC}"
for i in {1..18}; do
  sleep 10
  STATUS=$(aws rds describe-db-clusters --db-cluster-identifier "$CLUSTER_ID" --query 'DBClusters[0].Status' --output text)
  NEW_WRITER=$(aws rds describe-db-clusters --db-cluster-identifier "$CLUSTER_ID" --query 'DBClusters[0].DBClusterMembers[?IsClusterWriter==`true`].DBInstanceIdentifier' --output text)
  
  echo "Status: $STATUS | Writer: $NEW_WRITER"
  
  if [ "$STATUS" == "available" ] && [ "$NEW_WRITER" != "$CURRENT_WRITER" ]; then
    echo -e "${GREEN}Failover complete! New writer is $NEW_WRITER.${NC}"
    break
  fi
done

echo -e "${YELLOW}-------------------------------------------------------"
echo -e "Instructions for Evidence:"
echo -e "1. Screenshot RDS Events console showing failover start/complete."
echo -e "2. Screenshot cluster status showing the new writer."
echo -e "-------------------------------------------------------${NC}"
