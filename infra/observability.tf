# ─── LOGS ─────────────────────────────────────────────────────
# Short retention keeps parked cost near zero; the report notes 30-90 days
# as the production setting.
resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/aws/apigateway/${var.project_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-api-access-logs"
  }
}

resource "aws_cloudwatch_log_group" "services" {
  for_each = local.services

  name              = "/ecs/${var.project_name}-${each.key}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-${each.key}-logs"
  }
}

# ─── ALERTING ─────────────────────────────────────────────────
# Subscribe your email to this topic manually once (subscription requires
# an email-click confirmation Terraform cannot perform):
#   aws sns subscribe --topic-arn <alerts_topic_arn> --protocol email \
#     --notification-endpoint you@example.com
resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"

  tags = {
    Name = "${var.project_name}-alerts"
  }
}

# DLQ depth >= 1 — a single poisoned message must page immediately
# (backlog item 8; also the Week-3/7 poison-message demo evidence).
resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  alarm_name          = "${var.project_name}-orders-dlq-depth"
  alarm_description   = "Any message in the orders DLQ means a consumer failed 3 retries"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.orders_dlq.name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Name = "${var.project_name}-orders-dlq-depth"
  }
}

# Backlog >100 means consumers cannot keep up — the signal that triggers the
# autoscaling discussion in the testing week.
resource "aws_cloudwatch_metric_alarm" "orders_queue_depth" {
  alarm_name          = "${var.project_name}-orders-queue-depth"
  alarm_description   = "Orders queue backlog above 100 - inventory consumer is falling behind"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 100
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.orders.name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Name = "${var.project_name}-orders-queue-depth"
  }
}
