# ─── EVENT ROUTING (viva answer): commands → SQS · domain events →
#     EventBridge · fan-out → SNS ────────────────────────────────

resource "aws_sqs_queue" "orders_dlq" {
  name                      = "${var.project_name}-orders-dlq"
  message_retention_seconds = 1209600

  tags = {
    Name = "${var.project_name}-orders-dlq"
  }
}

resource "aws_sqs_queue" "orders" {
  name                       = "${var.project_name}-orders-queue"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20 # long polling (backlog item 8)

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.orders_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "${var.project_name}-orders-queue"
  }
}

resource "aws_sns_topic" "order_confirmed" {
  name = "${var.project_name}-order-confirmed"

  tags = {
    Name = "${var.project_name}-order-confirmed"
  }
}

# ─── SAGA COMPENSATION RECEIVER (ADR-06) ──────────────────────
# Inventory announces the outcome on SNS; the Order Service consumes it here
# and moves the order to its terminal state.
#
# The guide's Week 2 text filters on order-rejected alone, written before the
# publisher existed. Nothing else in the design sets CONFIRMED, so both event
# types are subscribed - the Week 3 Day 5 saga demo needs the confirm path too.
resource "aws_sqs_queue" "order_events" {
  name                       = "${var.project_name}-order-events"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20

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
    eventType = ["order-confirmed", "order-rejected"]
  })
}
