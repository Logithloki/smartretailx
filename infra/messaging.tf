# ─── EVENT ROUTING (viva answer): commands → SQS · domain events →
#     EventBridge · fan-out → SNS ────────────────────────────────

resource "aws_sqs_queue" "orders_dlq" {
  name                      = "${var.project_name}-orders-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true

  tags = {
    Name = "${var.project_name}-orders-dlq"
  }
}

resource "aws_sqs_queue" "orders" {
  name                       = "${var.project_name}-orders-queue"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20 # long polling (backlog item 8)
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.orders_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "${var.project_name}-orders-queue"
  }
}

resource "aws_sqs_queue" "order_outbox_publisher_dlq" {
  name                      = "${var.project_name}-order-outbox-publisher-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true

  tags = {
    Name = "${var.project_name}-order-outbox-publisher-dlq"
  }
}

resource "aws_sns_topic" "order_confirmed" {
  name              = "${var.project_name}-order-confirmed"
  kms_master_key_id = "alias/aws/sns"

  tags = {
    Name = "${var.project_name}-order-confirmed"
  }
}

# ─── SES SENDER IDENTITY ──────────────────────────────────────
# The baseline root is the canonical Terraform owner. Other environments use
# the supplied verified address as shared account/region infrastructure and do
# not import, create, or delete the identity from their own state.
#
# The account is in the SES SANDBOX, which means: verified senders only AND
# verified recipients only, ~200 messages/day, 1/sec. So the customer address
# used in the CW-4 demo must be verified too - a real inbox you control, not
# the @example.com seed default. Requesting production access is a separate
# AWS support ticket and is deliberately out of scope (amendment 21 also keeps
# k6 away from this path).
resource "aws_ses_email_identity" "sender" {
  count = var.environment_name == "baseline" && var.ses_sender_email != "" ? 1 : 0
  email = var.ses_sender_email

  lifecycle {
    prevent_destroy = true
  }
}

# ─── SAGA COMPENSATION RECEIVER (ADR-06) ──────────────────────
# Inventory announces the outcome on SNS; the Order Service consumes it here
# and moves the order to its terminal state.
#
# Both event types are subscribed (guide correction GC-1, docs/guide-corrections.md):
# this queue is the only route by which an order leaves PENDING, so filtering to
# order-rejected alone would strand every successful order.
resource "aws_sqs_queue" "order_events" {
  name                       = "${var.project_name}-order-events"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.orders_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "${var.project_name}-order-events"
  }
}

resource "aws_sqs_queue_policy" "order_events" {
  queue_url = aws_sqs_queue.order_events.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "sns.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.order_events.arn
      Condition = {
        ArnEquals = { "aws:SourceArn" = aws_sns_topic.order_confirmed.arn }
      }
    }]
  })
}

resource "aws_sns_topic_subscription" "order_events" {
  topic_arn = aws_sns_topic.order_confirmed.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.order_events.arn

  # Server-side filtering: messages that do not match never reach the queue,
  # so the consumer is not billed or woken for traffic it would discard.
  # Week 7 adds loadTest exclusion here to keep k6 runs out of SES.
  filter_policy = jsonencode({
    eventType = ["order-confirmed", "order-rejected", "order-cancelled"]
  })
}
