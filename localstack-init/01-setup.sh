#!/bin/bash
echo "Initialising SmartRetailX local AWS resources..."

awslocal dynamodb create-table \
  --table-name smartretailx-orders \
  --attribute-definitions AttributeName=orderId,AttributeType=S \
  --key-schema AttributeName=orderId,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --stream-specification StreamEnabled=true,StreamViewType=NEW_AND_OLD_IMAGES \
  --region eu-west-1

awslocal dynamodb create-table \
  --table-name smartretailx-products \
  --attribute-definitions AttributeName=productId,AttributeType=S \
  --key-schema AttributeName=productId,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region eu-west-1

awslocal dynamodb create-table \
  --table-name smartretailx-idempotency \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region eu-west-1

awslocal dynamodb create-table \
  --table-name smartretailx-websocket-connections \
  --attribute-definitions AttributeName=connectionId,AttributeType=S \
  --key-schema AttributeName=connectionId,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region eu-west-1

awslocal sqs create-queue \
  --queue-name smartretailx-orders-dlq \
  --region eu-west-1

awslocal sqs create-queue \
  --queue-name smartretailx-orders-queue \
  --attributes '{"RedrivePolicy":"{\"deadLetterTargetArn\":\"arn:aws:sqs:eu-west-1:000000000000:smartretailx-orders-dlq\",\"maxReceiveCount\":\"3\"}"}' \
  --region eu-west-1

awslocal sns create-topic \
  --name smartretailx-order-confirmed \
  --region eu-west-1

awslocal s3 mb s3://smartretailx-assets --region eu-west-1
awslocal s3 mb s3://smartretailx-audit-logs --region eu-west-1

awslocal dynamodb put-item --table-name smartretailx-products --region eu-west-1 \
  --item '{"productId":{"S":"prod-laptop-001"},"productName":{"S":"MacBook Pro 14"},"price":{"N":"1299.99"},"stockQuantity":{"N":"50"},"category":{"S":"Electronics"}}'

awslocal dynamodb put-item --table-name smartretailx-products --region eu-west-1 \
  --item '{"productId":{"S":"prod-mouse-002"},"productName":{"S":"Magic Mouse"},"price":{"N":"79.99"},"stockQuantity":{"N":"150"},"category":{"S":"Accessories"}}'

awslocal dynamodb put-item --table-name smartretailx-products --region eu-west-1 \
  --item '{"productId":{"S":"prod-monitor-003"},"productName":{"S":"4K Monitor 27inch"},"price":{"N":"599.99"},"stockQuantity":{"N":"40"},"category":{"S":"Electronics"}}'

awslocal dynamodb put-item --table-name smartretailx-products --region eu-west-1 \
  --item '{"productId":{"S":"prod-keyboard-004"},"productName":{"S":"Mechanical Keyboard"},"price":{"N":"149.99"},"stockQuantity":{"N":"200"},"category":{"S":"Accessories"}}'

awslocal dynamodb put-item --table-name smartretailx-products --region eu-west-1 \
  --item '{"productId":{"S":"prod-headset-005"},"productName":{"S":"Noise Cancelling Headphones"},"price":{"N":"349.99"},"stockQuantity":{"N":"80"},"category":{"S":"Electronics"}}'

echo "SmartRetailX local environment ready"