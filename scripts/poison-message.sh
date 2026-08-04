#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

QUEUE_NAME="smartretailx-orders"
DLQ_NAME="smartretailx-orders-dlq"

echo -e "${GREEN}Starting Poison Message Test...${NC}"

echo -e "${YELLOW}Getting Queue URLs...${NC}"
QUEUE_URL=$(aws sqs get-queue-url --queue-name "$QUEUE_NAME" --query 'QueueUrl' --output text)
DLQ_URL=$(aws sqs get-queue-url --queue-name "$DLQ_NAME" --query 'QueueUrl' --output text)

echo -e "${YELLOW}Sending malformed message to $QUEUE_NAME...${NC}"
# Malformed JSON (missing required fields)
MESSAGE_BODY='{"orderId": "123", "status": "PENDING"}'

aws sqs send-message --queue-url "$QUEUE_URL" --message-body "$MESSAGE_BODY"

echo -e "${YELLOW}Waiting for message to appear in DLQ (up to 60s)...${NC}"
FOUND=false
for i in {1..6}; do
  sleep 10
  echo "Polling DLQ..."
  MESSAGES=$(aws sqs receive-message --queue-url "$DLQ_URL" --max-number-of-messages 1 --query 'Messages' --output text)
  if [ "$MESSAGES" != "None" ] && [ -n "$MESSAGES" ]; then
    echo -e "${GREEN}Poison message received in DLQ!${NC}"
    FOUND=true
    break
  fi
done

if [ "$FOUND" = false ]; then
  echo -e "${RED}Message did not appear in DLQ within 60 seconds.${NC}"
fi

echo -e "${YELLOW}Checking CloudWatch alarm state for DLQ...${NC}"
ALARM_STATE=$(aws cloudwatch describe-alarms --alarm-names "${DLQ_NAME}-alarm" --query 'MetricAlarms[0].StateValue' --output text || echo "UNKNOWN")
echo -e "DLQ Alarm State: ${RED}$ALARM_STATE${NC}"

echo -e "${GREEN}Poison message test complete.${NC}"
echo -e "${YELLOW}-------------------------------------------------------"
echo -e "Instructions for Evidence:"
echo -e "1. Screenshot the SQS Console showing the message in the DLQ."
echo -e "2. Screenshot the CloudWatch alarm state for the DLQ alarm."
echo -e "-------------------------------------------------------${NC}"
