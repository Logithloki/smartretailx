#!/usr/bin/env bash
# Sends an intentionally invalid contract to TEST/STAGING and verifies DLQ arrival.
set -euo pipefail
: "${TARGET_ENV:?TARGET_ENV must be test or staging}"
: "${QUEUE_URL:?QUEUE_URL is required}"
: "${DLQ_URL:?DLQ_URL is required}"
[[ "$TARGET_ENV" == test || "$TARGET_ENV" == staging ]] || exit 2
[[ "${CONFIRM_CHAOS:-}" == "SEND_POISON_MESSAGE" ]] || { echo "Set CONFIRM_CHAOS=SEND_POISON_MESSAGE"; exit 2; }

before=$(aws sqs get-queue-attributes --queue-url "$DLQ_URL" \
  --attribute-names ApproximateNumberOfMessages --query 'Attributes.ApproximateNumberOfMessages' --output text)
aws sqs send-message --queue-url "$QUEUE_URL" --message-body '{"invalid":"contract"}' >/dev/null

deadline=$((SECONDS + 300))
while (( SECONDS < deadline )); do
  after=$(aws sqs get-queue-attributes --queue-url "$DLQ_URL" \
    --attribute-names ApproximateNumberOfMessages --query 'Attributes.ApproximateNumberOfMessages' --output text)
  if (( after > before )); then
    jq -n --arg environment "$TARGET_ENV" --argjson before "$before" --argjson after "$after" \
      '{status:"PASS",environment,before,after}'
    exit 0
  fi
  sleep 10
done
echo "Poison message did not reach the DLQ within five minutes" >&2
exit 1
