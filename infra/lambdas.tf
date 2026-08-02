# ─── LAMBDAS ──────────────────────────────────────────────────
# Kept in their own file rather than compute.tf: the Fargate services and the
# event-driven Lambdas have different lifecycles and reviewing them together
# was getting unwieldy.
#
# All functions are ARM64 for the same reason the Fargate tasks are (ADR-08),
# and all use the AWS-published Powertools layer instead of vendoring the
# dependency into each zip - smaller artefacts and one version to bump.

locals {
  # Official AWS layer. Account 017000801446 is AWS's, not ours.
  powertools_layer = "arn:aws:lambda:${var.aws_region}:017000801446:layer:AWSLambdaPowertoolsPythonV3-python312-arm64:4"
}

# ─── Notification Lambda (SNS -> SES) ─────────────────────────

data "archive_file" "notification" {
  type        = "zip"
  source_file = "${path.module}/../services/notification-lambda/handler.py"
  output_path = "${path.module}/build/notification-lambda.zip"
}

resource "aws_lambda_function" "notification" {
  function_name    = "${var.project_name}-notification"
  role             = aws_iam_role.notification_lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  filename         = data.archive_file.notification.output_path
  source_code_hash = data.archive_file.notification.output_base64sha256
  timeout          = 15
  memory_size      = 256
  layers           = [local.powertools_layer]

  # X-Ray on: this is what puts the notification hop on the service map.
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      APP_REGION                  = var.aws_region
      IDEMPOTENCY_TABLE_NAME      = aws_dynamodb_table.idempotency.name
      SES_SENDER_EMAIL            = var.ses_sender_email
      NOTIFICATION_FALLBACK_EMAIL = var.notification_fallback_email
      POWERTOOLS_SERVICE_NAME     = "notification-lambda"
      POWERTOOLS_LOG_LEVEL        = "INFO"
    }
  }

  tags = {
    Name = "${var.project_name}-notification"
  }
}

resource "aws_cloudwatch_log_group" "notification" {
  name              = "/aws/lambda/${aws_lambda_function.notification.function_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-notification-logs"
  }
}

resource "aws_lambda_permission" "notification_sns" {
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notification.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.order_confirmed.arn
}

resource "aws_sns_topic_subscription" "notification" {
  topic_arn = aws_sns_topic.order_confirmed.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.notification.arn

  # Both outcomes are worth an email. The loadTest clause is amendment 21:
  # Week 7's k6 order-path runs stamp loadTest=true, and SES sandbox allows
  # ~1 msg/sec and ~200/day - a 50-VU test would throttle SES and flood the
  # inbox. Filtering server-side means the Lambda is never even invoked.
  filter_policy = jsonencode({
    eventType = ["order-confirmed", "order-rejected"]
    loadTest  = [{ exists = false }]
  })
}

# ─── Stock reconciliation Lambda (scheduled) ──────────────────

data "archive_file" "reconciliation" {
  type        = "zip"
  source_file = "${path.module}/../services/reconciliation-lambda/handler.py"
  output_path = "${path.module}/build/reconciliation-lambda.zip"
}

resource "aws_lambda_function" "reconciliation" {
  function_name    = "${var.project_name}-stock-reconciliation"
  role             = aws_iam_role.reconciliation_lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  filename         = data.archive_file.reconciliation.output_path
  source_code_hash = data.archive_file.reconciliation.output_base64sha256
  timeout          = 60
  memory_size      = 256
  layers           = [local.powertools_layer]

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      APP_REGION              = var.aws_region
      ORDERS_TABLE_NAME       = aws_dynamodb_table.orders.name
      ALERTS_TOPIC_ARN        = aws_sns_topic.alerts.arn
      STALE_PENDING_MINUTES   = "30"
      POWERTOOLS_SERVICE_NAME = "stock-reconciliation"
      POWERTOOLS_LOG_LEVEL    = "INFO"
    }
  }

  tags = {
    Name = "${var.project_name}-stock-reconciliation"
  }
}

resource "aws_cloudwatch_log_group" "reconciliation" {
  name              = "/aws/lambda/${aws_lambda_function.reconciliation.function_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-reconciliation-logs"
  }
}

# Daily at 00:00 Asia/Colombo (amendment 24 - the default is UTC, which would
# fire this at 05:30 local). ENABLED, unlike the park/restore pair: this one
# only reads and reports, so it is safe to leave running.
resource "aws_scheduler_schedule" "stock_reconciliation" {
  name                         = "${var.project_name}-stock-reconciliation"
  description                  = "Flags orders stuck in PENDING - a saga that did not complete"
  state                        = "ENABLED"
  schedule_expression          = "cron(0 0 * * ? *)"
  schedule_expression_timezone = "Asia/Colombo"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.reconciliation.arn
    role_arn = aws_iam_role.scheduler.arn
  }
}
