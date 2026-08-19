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

# --- transactional order outbox -> SQS ---

resource "aws_iam_role" "order_outbox_publisher" {
  name               = "${var.project_name}-order-outbox-publisher"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "order_outbox_publisher" {
  name = "stream-publish-and-state"
  role = aws_iam_role.order_outbox_publisher.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = local.lambda_logging_actions
        Resource = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-order-outbox-publisher:*"]
      },
      {
        Sid      = "Tracing"
        Effect   = "Allow"
        Action   = local.lambda_xray_actions
        Resource = ["*"]
      },
      {
        Sid    = "ReadOutboxStream"
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeStream",
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:ListStreams",
        ]
        Resource = [aws_dynamodb_table.order_outbox.stream_arn]
      },
      {
        Sid      = "ReadAndMarkOutbox"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = [aws_dynamodb_table.order_outbox.arn]
      },
      {
        Sid      = "PublishOrderCommand"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = [aws_sqs_queue.orders.arn, aws_sqs_queue.order_outbox_publisher_dlq.arn]
      },
      {
        Sid      = "PublishOrderDomainEvent"
        Effect   = "Allow"
        Action   = ["events:PutEvents"]
        Resource = [aws_cloudwatch_event_bus.orders.arn]
      },
    ]
  })
}

data "archive_file" "order_outbox_publisher" {
  type        = "zip"
  source_file = "${path.module}/../services/order-outbox-publisher/handler.py"
  output_path = "${path.module}/build/order-outbox-publisher.zip"
}

resource "aws_lambda_function" "order_outbox_publisher" {
  function_name    = "${var.project_name}-order-outbox-publisher"
  role             = aws_iam_role.order_outbox_publisher.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  filename         = data.archive_file.order_outbox_publisher.output_path
  source_code_hash = data.archive_file.order_outbox_publisher.output_base64sha256
  timeout          = 15
  memory_size      = 256
  publish          = true

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      APP_REGION              = var.aws_region
      ORDER_OUTBOX_TABLE_NAME = aws_dynamodb_table.order_outbox.name
      ORDERS_QUEUE_URL        = aws_sqs_queue.orders.url
      EVENT_BUS_NAME          = aws_cloudwatch_event_bus.orders.name
      LOG_LEVEL               = "INFO"
    }
  }

  tags = {
    Name = "${var.project_name}-order-outbox-publisher"
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
}

resource "aws_lambda_alias" "order_outbox_publisher" {
  name             = var.environment_name == "baseline" ? "development" : var.environment_name
  function_name    = aws_lambda_function.order_outbox_publisher.function_name
  function_version = aws_lambda_function.order_outbox_publisher.version

  lifecycle { ignore_changes = [function_version] }
}

resource "aws_cloudwatch_log_group" "order_outbox_publisher" {
  name              = "/aws/lambda/${aws_lambda_function.order_outbox_publisher.function_name}"
  retention_in_days = 7
}

resource "aws_lambda_event_source_mapping" "order_outbox_publisher" {
  event_source_arn                   = aws_dynamodb_table.order_outbox.stream_arn
  function_name                      = aws_lambda_alias.order_outbox_publisher.arn
  starting_position                  = "LATEST"
  batch_size                         = 10
  maximum_batching_window_in_seconds = 1
  maximum_retry_attempts             = 3
  bisect_batch_on_function_error     = true
  function_response_types            = ["ReportBatchItemFailures"]

  filter_criteria {
    filter {
      pattern = jsonencode({ eventName = ["INSERT"] })
    }
  }

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.order_outbox_publisher_dlq.arn
    }
  }

  depends_on = [aws_iam_role_policy.order_outbox_publisher]
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
  publish          = true
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
      FRONTEND_URL                = var.frontend_url
      POWERTOOLS_SERVICE_NAME     = "notification-lambda"
      POWERTOOLS_LOG_LEVEL        = "INFO"
    }
  }

  tags = {
    Name = "${var.project_name}-notification"
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
}

resource "aws_lambda_alias" "notification" {
  name             = var.environment_name == "baseline" ? "development" : var.environment_name
  function_name    = aws_lambda_function.notification.function_name
  function_version = aws_lambda_function.notification.version

  lifecycle { ignore_changes = [function_version] }
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
  qualifier     = aws_lambda_alias.notification.name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.order_confirmed.arn
}

resource "aws_sns_topic_subscription" "notification" {
  topic_arn = aws_sns_topic.order_confirmed.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_alias.notification.arn

  # All customer-facing milestones are worth an email. The loadTest clause is
  # amendment 21: k6 stamps loadTest=true, and SES sandbox allows ~1 msg/sec
  # and ~200/day - filtering server-side means the Lambda is never invoked.
  filter_policy = jsonencode({
    eventType = ["order-confirmed", "order-rejected", "order-cancelled"]
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
  publish          = true
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

  lifecycle { ignore_changes = [filename, source_code_hash] }
}

resource "aws_lambda_alias" "reconciliation" {
  name             = var.environment_name == "baseline" ? "development" : var.environment_name
  function_name    = aws_lambda_function.reconciliation.function_name
  function_version = aws_lambda_function.reconciliation.version

  lifecycle { ignore_changes = [function_version] }
}

resource "aws_cloudwatch_log_group" "reconciliation" {
  name              = "/aws/lambda/${aws_lambda_function.reconciliation.function_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-reconciliation-logs"
  }
}

# ─── WebSocket Lambdas (connect / disconnect / push) ─────────
#
# Basic execution roles + logs + tracing live here so the Lambda resources
# themselves are self-contained. The DynamoDB and execute-api:ManageConnections
# grants (backlog item 33) live in security.tf alongside every other IAM
# policy - kept out of lambdas.tf so this file stays about function config.
#
# All three needs CW-3a validation on real AWS: LocalStack Community cannot
# emulate WebSocket APIs (CLAUDE.md cost-guardrails).

# --- shared assume role + basic policy generators (log + xray) ---

resource "aws_iam_role" "ws_connect_lambda" {
  name               = "${var.project_name}-ws-connect-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "ws_connect_lambda_basics" {
  name = "logs-and-tracing"
  role = aws_iam_role.ws_connect_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = local.lambda_logging_actions
        Resource = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-ws-connect:*"]
      },
      {
        Sid      = "Tracing"
        Effect   = "Allow"
        Action   = local.lambda_xray_actions
        Resource = ["*"]
      },
    ]
  })
}

resource "aws_iam_role" "ws_disconnect_lambda" {
  name               = "${var.project_name}-ws-disconnect-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "ws_disconnect_lambda_basics" {
  name = "logs-and-tracing"
  role = aws_iam_role.ws_disconnect_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = local.lambda_logging_actions
        Resource = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-ws-disconnect:*"]
      },
      {
        Sid      = "Tracing"
        Effect   = "Allow"
        Action   = local.lambda_xray_actions
        Resource = ["*"]
      },
    ]
  })
}

resource "aws_iam_role" "ws_push_lambda" {
  name               = "${var.project_name}-ws-push-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "ws_push_lambda_basics" {
  name = "logs-and-tracing"
  role = aws_iam_role.ws_push_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = local.lambda_logging_actions
        Resource = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-ws-push:*"]
      },
      {
        Sid      = "Tracing"
        Effect   = "Allow"
        Action   = local.lambda_xray_actions
        Resource = ["*"]
      },
    ]
  })
}

# --- $connect ---

data "archive_file" "ws_connect" {
  type        = "zip"
  source_file = "${path.module}/../services/ws-connect-lambda/handler.py"
  output_path = "${path.module}/build/ws-connect-lambda.zip"
}

resource "aws_lambda_function" "ws_connect" {
  function_name    = "${var.project_name}-ws-connect"
  role             = aws_iam_role.ws_connect_lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  filename         = data.archive_file.ws_connect.output_path
  source_code_hash = data.archive_file.ws_connect.output_base64sha256
  timeout          = 5 # $connect must be fast or the browser upgrade fails
  memory_size      = 256
  publish          = true

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      APP_REGION           = var.aws_region
      WS_CONNECTIONS_TABLE = aws_dynamodb_table.websocket_connections.name
      LOG_LEVEL            = "INFO"
    }
  }

  tags = {
    Name = "${var.project_name}-ws-connect"
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
}

resource "aws_lambda_alias" "ws_connect" {
  name             = var.environment_name == "baseline" ? "development" : var.environment_name
  function_name    = aws_lambda_function.ws_connect.function_name
  function_version = aws_lambda_function.ws_connect.version

  lifecycle { ignore_changes = [function_version] }
}

resource "aws_cloudwatch_log_group" "ws_connect" {
  name              = "/aws/lambda/${aws_lambda_function.ws_connect.function_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-ws-connect-logs"
  }
}

# API Gateway must be allowed to invoke each route's integration Lambda.
# source_arn scopes it to this WebSocket API's routes only.
resource "aws_lambda_permission" "ws_connect_invoke" {
  count         = var.live ? 1 : 0
  statement_id  = "AllowInvokeFromWebSocketConnect"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ws_connect.function_name
  qualifier     = aws_lambda_alias.ws_connect.name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ws.execution_arn}/*/$connect"
}

# --- $disconnect ---

data "archive_file" "ws_disconnect" {
  type        = "zip"
  source_file = "${path.module}/../services/ws-disconnect-lambda/handler.py"
  output_path = "${path.module}/build/ws-disconnect-lambda.zip"
}

resource "aws_lambda_function" "ws_disconnect" {
  function_name    = "${var.project_name}-ws-disconnect"
  role             = aws_iam_role.ws_disconnect_lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  filename         = data.archive_file.ws_disconnect.output_path
  source_code_hash = data.archive_file.ws_disconnect.output_base64sha256
  timeout          = 5
  memory_size      = 256
  publish          = true

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      APP_REGION           = var.aws_region
      WS_CONNECTIONS_TABLE = aws_dynamodb_table.websocket_connections.name
      LOG_LEVEL            = "INFO"
    }
  }

  tags = {
    Name = "${var.project_name}-ws-disconnect"
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
}

resource "aws_lambda_alias" "ws_disconnect" {
  name             = var.environment_name == "baseline" ? "development" : var.environment_name
  function_name    = aws_lambda_function.ws_disconnect.function_name
  function_version = aws_lambda_function.ws_disconnect.version

  lifecycle { ignore_changes = [function_version] }
}

resource "aws_cloudwatch_log_group" "ws_disconnect" {
  name              = "/aws/lambda/${aws_lambda_function.ws_disconnect.function_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-ws-disconnect-logs"
  }
}

# Serves both $disconnect and $default routes (see websocket.tf).
resource "aws_lambda_permission" "ws_disconnect_invoke" {
  count         = var.live ? 1 : 0
  statement_id  = "AllowInvokeFromWebSocketDisconnectOrDefault"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ws_disconnect.function_name
  qualifier     = aws_lambda_alias.ws_disconnect.name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ws.execution_arn}/*"
}

# --- push (EventBridge -> postToConnection) ---

data "archive_file" "ws_push" {
  type        = "zip"
  source_file = "${path.module}/../services/ws-push-lambda/handler.py"
  output_path = "${path.module}/build/ws-push-lambda.zip"
}

resource "aws_lambda_function" "ws_push" {
  function_name    = "${var.project_name}-ws-push"
  role             = aws_iam_role.ws_push_lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  filename         = data.archive_file.ws_push.output_path
  source_code_hash = data.archive_file.ws_push.output_base64sha256
  timeout          = 15
  memory_size      = 256
  publish          = true

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      APP_REGION           = var.aws_region
      WS_CONNECTIONS_TABLE = aws_dynamodb_table.websocket_connections.name
      # The apigatewaymanagementapi endpoint is the WSS API's stage-scoped
      # HTTPS callback URL. Empty when parked - the Lambda is never invoked
      # in that state anyway (the EventBridge rule is also gated).
      WS_CALLBACK_ENDPOINT = var.live ? "https://${aws_apigatewayv2_api.ws.id}.execute-api.${var.aws_region}.amazonaws.com/${aws_apigatewayv2_stage.ws[0].name}" : ""
      LOG_LEVEL            = "INFO"
    }
  }

  tags = {
    Name = "${var.project_name}-ws-push"
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
}

resource "aws_lambda_alias" "ws_push" {
  name             = var.environment_name == "baseline" ? "development" : var.environment_name
  function_name    = aws_lambda_function.ws_push.function_name
  function_version = aws_lambda_function.ws_push.version

  lifecycle { ignore_changes = [function_version] }
}

resource "aws_cloudwatch_log_group" "ws_push" {
  name              = "/aws/lambda/${aws_lambda_function.ws_push.function_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-ws-push-logs"
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
    arn      = aws_lambda_alias.reconciliation.arn
    role_arn = aws_iam_role.scheduler.arn
  }
}
