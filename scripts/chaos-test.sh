#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

if [ -z "${AUTH_TOKEN:-}" ]; then
  echo -e "${RED}Error: AUTH_TOKEN environment variable is required.${NC}"
  echo "Usage: AUTH_TOKEN=your_token CLUSTER_NAME=smartretailx-cluster ./chaos-test.sh"
  exit 1
fi

CLUSTER_NAME=${CLUSTER_NAME:-smartretailx-cluster}
echo -e "${GREEN}Starting Chaos Test on cluster ${CLUSTER_NAME}...${NC}"

# Get task ARN
echo -e "${YELLOW}Finding running tasks for product-service...${NC}"
TASKS=$(aws ecs list-tasks --cluster "$CLUSTER_NAME" --family product-service --desired-status RUNNING --query 'taskArns' --output text)

if [ -z "$TASKS" ] || [ "$TASKS" = "None" ]; then
  echo -e "${RED}No running tasks found for product-service in $CLUSTER_NAME.${NC}"
  exit 1
fi

FIRST_TASK=$(echo "$TASKS" | awk '{print $1}')
echo -e "${GREEN}Found task: $FIRST_TASK${NC}"

echo -e "${YELLOW}Starting background k6 load test...${NC}"
# Simulate k6 background load test
cat << 'EOF' > /tmp/chaos-k6.js
import http from 'k6/http';
export let options = { vus: 5, duration: '60s' };
export default function() {
  http.get('http://localhost/api/v1/products', { headers: { 'Authorization': 'Bearer ' + __ENV.AUTH_TOKEN } });
}
EOF

AUTH_TOKEN=$AUTH_TOKEN k6 run /tmp/chaos-k6.js &
K6_PID=$!

echo -e "${YELLOW}Waiting 15 seconds for load to stabilize...${NC}"
sleep 15

echo -e "${RED}KILLING ECS TASK: $FIRST_TASK...${NC}"
aws ecs stop-task --cluster "$CLUSTER_NAME" --task "$FIRST_TASK" --reason "Chaos Test"

echo -e "${YELLOW}Monitoring for 45 seconds...${NC}"
sleep 45

wait $K6_PID || true

echo -e "${GREEN}Chaos test complete.${NC}"
echo -e "${YELLOW}-------------------------------------------------------"
echo -e "Instructions for Evidence:"
echo -e "1. Screenshot CloudWatch ECS task count timeline showing the dip and recovery."
echo -e "2. Screenshot ALB healthy host count showing the replacement task registering."
echo -e "-------------------------------------------------------${NC}"
