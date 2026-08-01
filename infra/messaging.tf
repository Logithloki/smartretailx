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
