#!/usr/bin/env bash
# Safe TEST/STAGING ECS task-loss exercise. This script is never called by PR
# or production workflows and requires an explicit per-run confirmation.
set -euo pipefail

: "${TARGET_ENV:?TARGET_ENV must be test or staging}"
: "${BASE_URL:?BASE_URL must be the HTTPS CloudFront URL}"
: "${AUTH_TOKEN:?AUTH_TOKEN must be a short-lived customer access token}"
: "${CLUSTER_NAME:?CLUSTER_NAME is required}"
: "${PROJECT_NAME:?PROJECT_NAME is required}"

[[ "$TARGET_ENV" == test || "$TARGET_ENV" == staging ]] || { echo "Chaos is permitted only in test/staging"; exit 2; }
[[ "$BASE_URL" == https://* ]] || { echo "BASE_URL must use HTTPS"; exit 2; }
[[ "${CONFIRM_CHAOS:-}" == "STOP_ONE_ECS_TASK" ]] || { echo "Set CONFIRM_CHAOS=STOP_ONE_ECS_TASK"; exit 2; }

service="$PROJECT_NAME-product-service"
mkdir -p evidence/chaos
started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
task=$(aws ecs list-tasks --cluster "$CLUSTER_NAME" --service-name "$service" \
  --desired-status RUNNING --query 'taskArns[0]' --output text)
[[ "$task" == arn:* ]] || { echo "No running $service task"; exit 1; }

BASE_URL="$BASE_URL" AUTH_TOKEN="$AUTH_TOKEN" K6_PROFILE=smoke \
  k6 run --summary-export evidence/chaos/k6-summary.json k6-tests/load-test.js &
k6_pid=$!

# Poll for traffic rather than treating a fixed sleep as readiness.
for attempt in {1..30}; do
  if curl --fail --silent -H "Authorization: Bearer $AUTH_TOKEN" "$BASE_URL/v1/products" >/dev/null; then break; fi
  sleep 2
done

aws ecs stop-task --cluster "$CLUSTER_NAME" --task "$task" \
  --reason "Approved SmartRetailX $TARGET_ENV resilience evidence" >/dev/null

deadline=$((SECONDS + 180))
recovered=false
while (( SECONDS < deadline )); do
  state=$(aws ecs describe-services --cluster "$CLUSTER_NAME" --services "$service" \
    --query 'services[0].[runningCount,desiredCount]' --output text)
  read -r running desired <<<"$state"
  if [[ "$running" -eq "$desired" && "$desired" -gt 0 ]] && \
     curl --fail --silent -H "Authorization: Bearer $AUTH_TOKEN" "$BASE_URL/v1/products" >/dev/null; then
    recovered=true
    break
  fi
  sleep 5
done

wait "$k6_pid"
test "$recovered" = true
finished=$(date -u +%Y-%m-%dT%H:%M:%SZ)
jq -n --arg environment "$TARGET_ENV" --arg task "$task" --arg started "$started" \
  --arg finished "$finished" '{status:"PASS",environment,stoppedTask:task,started,finished}' \
  > evidence/chaos/task-recovery.json
