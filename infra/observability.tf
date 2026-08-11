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
  name              = "${var.project_name}-alerts"
  kms_master_key_id = "alias/aws/sns"

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

resource "aws_cloudwatch_metric_alarm" "order_outbox_publisher_dlq_depth" {
  alarm_name          = "${var.project_name}-order-outbox-publisher-dlq-depth"
  alarm_description   = "An order command exhausted DynamoDB Stream publisher retries"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.order_outbox_publisher_dlq.name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
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

resource "aws_cloudwatch_metric_alarm" "orders_queue_age" {
  alarm_name          = "${var.project_name}-orders-oldest-message"
  alarm_description   = "Oldest order command has waited more than five minutes"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 300
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = aws_sqs_queue.orders.name }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# Per-service deployment alarm consumed directly by ECS. One unhealthy target
# during a rollout is sufficient to stop and roll back the revision.
resource "aws_cloudwatch_metric_alarm" "service_unhealthy_targets" {
  for_each = local.services

  alarm_name          = "${var.project_name}-${each.key}-unhealthy-targets"
  alarm_description   = "ECS deployment target for ${each.key} is unhealthy"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.live ? aws_lb.main[0].arn_suffix : "parked"
    TargetGroup  = aws_lb_target_group.services[each.key].arn_suffix
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_server_errors" {
  alarm_name          = "${var.project_name}-api-5xx"
  alarm_description   = "HTTP API server error rate is non-zero for two minutes"
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiId = aws_apigatewayv2_api.main.id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name          = "${var.project_name}-api-p95-latency"
  alarm_description   = "HTTP API p95 latency exceeded two seconds"
  namespace           = "AWS/ApiGateway"
  metric_name         = "Latency"
  extended_statistic  = "p95"
  period              = 60
  evaluation_periods  = 3
  datapoints_to_alarm = 2
  threshold           = 2000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { ApiId = aws_apigatewayv2_api.main.id }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "aurora_connections" {
  alarm_name          = "${var.project_name}-aurora-connections"
  alarm_description   = "Aurora connection count is unexpectedly high for demo sizing"
  namespace           = "AWS/RDS"
  metric_name         = "DatabaseConnections"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { DBClusterIdentifier = aws_rds_cluster.inventory.cluster_identifier }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

locals {
  operational_lambdas = {
    notification           = aws_lambda_function.notification.function_name
    reconciliation         = aws_lambda_function.reconciliation.function_name
    order_outbox_publisher = aws_lambda_function.order_outbox_publisher.function_name
    ws_connect             = aws_lambda_function.ws_connect.function_name
    ws_disconnect          = aws_lambda_function.ws_disconnect.function_name
    ws_push                = aws_lambda_function.ws_push.function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = local.operational_lambdas

  alarm_name          = "${var.project_name}-${each.key}-lambda-errors"
  alarm_description   = "${each.key} Lambda reported errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_dashboard" "operations" {
  dashboard_name = "${var.project_name}-operations"
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "HTTP API requests, 4XX and 5XX"
          region = var.aws_region
          view   = "timeSeries"
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiId", aws_apigatewayv2_api.main.id, { stat = "Sum" }],
            [".", "4xx", ".", ".", { stat = "Sum" }],
            [".", "5xx", ".", ".", { stat = "Sum" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 25
        width  = 12
        height = 6
        properties = {
          title  = "DynamoDB requests and throttling"
          region = var.aws_region
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", aws_dynamodb_table.orders.name, { stat = "Sum" }],
            [".", "ConsumedWriteCapacityUnits", ".", aws_dynamodb_table.orders.name, { stat = "Sum" }],
            [".", "ThrottledRequests", ".", aws_dynamodb_table.orders.name, { stat = "Sum" }],
            [".", "SystemErrors", ".", aws_dynamodb_table.orders.name, { stat = "Sum" }],
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", aws_dynamodb_table.products.name, { stat = "Sum" }],
            [".", "ConsumedWriteCapacityUnits", ".", aws_dynamodb_table.products.name, { stat = "Sum" }],
            [".", "ThrottledRequests", ".", aws_dynamodb_table.products.name, { stat = "Sum" }],
            [".", "SystemErrors", ".", aws_dynamodb_table.products.name, { stat = "Sum" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 25
        width  = 12
        height = 6
        properties = {
          title  = "Queue depth and oldest message age"
          region = var.aws_region
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.orders.name],
            [".", "ApproximateAgeOfOldestMessage", ".", aws_sqs_queue.orders.name],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "HTTP API latency percentiles"
          region = var.aws_region
          metrics = [
            ["AWS/ApiGateway", "Latency", "ApiId", aws_apigatewayv2_api.main.id, { stat = "p50" }],
            ["...", { stat = "p90" }],
            ["...", { stat = "p95" }],
            ["...", { stat = "p99" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 7
        properties = {
          title  = "ECS CPU by service"
          region = var.aws_region
          metrics = [for name, _ in local.services :
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.services[name].name]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 7
        properties = {
          title  = "ECS memory by service"
          region = var.aws_region
          metrics = [for name, _ in local.services :
            ["AWS/ECS", "MemoryUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.services[name].name]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 13
        width  = 12
        height = 6
        properties = {
          title  = "Queue backlog and DLQs"
          region = var.aws_region
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.orders.name],
            [".", ".", ".", aws_sqs_queue.orders_dlq.name],
            [".", ".", ".", aws_sqs_queue.order_outbox_publisher_dlq.name],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 13
        width  = 12
        height = 6
        properties = {
          title  = "Lambda errors and throttles"
          region = var.aws_region
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", local.operational_lambdas.notification],
            [".", "Throttles", ".", local.operational_lambdas.notification],
            ["AWS/Lambda", "Errors", "FunctionName", local.operational_lambdas.reconciliation],
            [".", "Throttles", ".", local.operational_lambdas.reconciliation],
            ["AWS/Lambda", "Errors", "FunctionName", local.operational_lambdas.order_outbox_publisher],
            [".", "Throttles", ".", local.operational_lambdas.order_outbox_publisher],
            ["AWS/Lambda", "Errors", "FunctionName", local.operational_lambdas.ws_connect],
            [".", "Throttles", ".", local.operational_lambdas.ws_connect],
            ["AWS/Lambda", "Errors", "FunctionName", local.operational_lambdas.ws_disconnect],
            [".", "Throttles", ".", local.operational_lambdas.ws_disconnect],
            ["AWS/Lambda", "Errors", "FunctionName", local.operational_lambdas.ws_push],
            [".", "Throttles", ".", local.operational_lambdas.ws_push],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 19
        width  = 24
        height = 6
        properties = {
          title  = "Aurora capacity, connections and latency"
          region = var.aws_region
          metrics = [
            ["AWS/RDS", "ServerlessDatabaseCapacity", "DBClusterIdentifier", aws_rds_cluster.inventory.cluster_identifier],
            [".", "DatabaseConnections", ".", "."],
            [".", "CommitLatency", ".", "."],
          ]
        }
      },
    ]
  })
}
