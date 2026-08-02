# ─── WEBSOCKET API v2 (real-time order status) ───────────────
#
# Purpose: browser sees PENDING -> CONFIRMED/REJECTED flip live once the
# saga settles. Together with EventBridge Pipes (pipes.tf) this is the
# real-time-updates story for Task 4 of the marking brief.
#
# Authorizer design (see G.1.2 in the guide + adversarial-review amendment):
# WebSocket APIs do NOT support JWT authorizers - that path is HTTP/REST v1
# only. We use a REQUEST authorizer Lambda that reads the token from the
# query string, since browsers cannot set an Authorization header on the
# WebSocket upgrade. Validation logic mirrors srx_common.auth so behaviour
# is uniform across the HTTP and WebSocket edges.
#
# Component status: **needs CW-3a validation on real AWS** - LocalStack
# Community cannot emulate API Gateway v2 WebSocket APIs (CLAUDE.md).
#
# Gating: the WebSocket API resource itself is free at rest (mirrors how
# the HTTP API in compute.tf is not count-gated); the stage, routes,
# integrations, and invoke permissions ARE gated so the endpoint has no
# reachable surface while parked.

resource "aws_apigatewayv2_api" "ws" {
  name                       = "${var.project_name}-ws"
  protocol_type              = "WEBSOCKET"
  description                = "Real-time order status push - EventBridge -> Lambda -> postToConnection"
  route_selection_expression = "$request.body.action"

  tags = {
    Name = "${var.project_name}-ws"
  }
}

# ─── Authorizer Lambda (validates Cognito JWT off the query string) ──

data "archive_file" "ws_authorizer" {
  type        = "zip"
  source_file = "${path.module}/../services/ws-authorizer-lambda/handler.py"
  output_path = "${path.module}/build/ws-authorizer-lambda.zip"
}

resource "aws_iam_role" "ws_authorizer_lambda" {
  name               = "${var.project_name}-ws-authorizer-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Authorizer role only needs logs + tracing; no data access. Everything
# else is scoped to the connect / disconnect / push roles (backlog 33 IAM).
resource "aws_iam_role_policy" "ws_authorizer_lambda" {
  role = aws_iam_role.ws_authorizer_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = local.lambda_logging_actions
        Resource = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-ws-authorizer:*"]
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

# PyJWT is not in the Powertools layer; the authorizer needs its own zip
# with dependencies. Terraform can build the zip if a `pip install -t` step
# is baked into a `null_resource`, but that couples plan to a working local
# pip - for the assignment we rely on the CI job (or a manual
# `pip install -r requirements.txt -t services/ws-authorizer-lambda`) to
# vendor dependencies alongside handler.py before apply. Documented in the
# CW-3a runbook so it isn't discovered at the checkpoint window.
resource "aws_lambda_function" "ws_authorizer" {
  function_name    = "${var.project_name}-ws-authorizer"
  role             = aws_iam_role.ws_authorizer_lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  filename         = data.archive_file.ws_authorizer.output_path
  source_code_hash = data.archive_file.ws_authorizer.output_base64sha256
  timeout          = 10
  memory_size      = 256

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      APP_REGION            = var.aws_region
      COGNITO_ISSUER        = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
      COGNITO_APP_CLIENT_ID = aws_cognito_user_pool_client.spa.id
      LOG_LEVEL             = "INFO"
    }
  }

  tags = {
    Name = "${var.project_name}-ws-authorizer"
  }
}

resource "aws_cloudwatch_log_group" "ws_authorizer" {
  name              = "/aws/lambda/${aws_lambda_function.ws_authorizer.function_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-ws-authorizer-logs"
  }
}

# API Gateway must be allowed to invoke the authorizer. source_arn is the
# authorizer resource ARN pattern; a wildcard would allow any authorizer in
# the account to invoke this function.
resource "aws_lambda_permission" "ws_authorizer_invoke" {
  statement_id  = "AllowInvokeFromWebSocketAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ws_authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ws.execution_arn}/authorizers/*"
}

# The authorizer itself is a resource on the API; the routes reference it
# via `authorizer_id`. Not count-gated (free at rest); the routes below are.
resource "aws_apigatewayv2_authorizer" "ws_connect" {
  api_id                            = aws_apigatewayv2_api.ws.id
  name                              = "${var.project_name}-ws-cognito"
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = aws_lambda_function.ws_authorizer.invoke_arn
  identity_sources                  = ["route.request.querystring.token"]
  authorizer_result_ttl_in_seconds  = 0
  authorizer_payload_format_version = "1.0" # WebSocket authorizers use payload v1 only
}

# ─── Integrations (AWS_PROXY -> connect/disconnect/default Lambdas) ──
# The connect/disconnect/push Lambdas are added in the next commit (Week 5
# chunk 1 commit 3) - these integrations forward-reference them. Terraform
# validate at the end of the chunk proves the graph is consistent.

resource "aws_apigatewayv2_integration" "ws_connect" {
  count              = var.live ? 1 : 0
  api_id             = aws_apigatewayv2_api.ws.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.ws_connect.invoke_arn
  integration_method = "POST"
}

resource "aws_apigatewayv2_integration" "ws_disconnect" {
  count              = var.live ? 1 : 0
  api_id             = aws_apigatewayv2_api.ws.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.ws_disconnect.invoke_arn
  integration_method = "POST"
}

# $default receives any message the client sends that does not match a
# specific action route. We do not currently accept client -> server
# messages (order status is server-push only), but $default MUST exist or
# API Gateway rejects deploy - so it points at a shared no-op that returns
# 200 immediately. Reuses ws_disconnect handler for simplicity (both are
# no-op-shaped from the client's perspective); a dedicated handler is
# tracked as a future refinement.
resource "aws_apigatewayv2_integration" "ws_default" {
  count              = var.live ? 1 : 0
  api_id             = aws_apigatewayv2_api.ws.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.ws_disconnect.invoke_arn
  integration_method = "POST"
}

# ─── Routes ─────────────────────────────────────────────────

resource "aws_apigatewayv2_route" "ws_connect" {
  count              = var.live ? 1 : 0
  api_id             = aws_apigatewayv2_api.ws.id
  route_key          = "$connect"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.ws_connect.id
  target             = "integrations/${aws_apigatewayv2_integration.ws_connect[0].id}"
}

# $disconnect and $default are NOT authenticated - API Gateway generates
# $disconnect internally on close (there is no bearer token to check), and
# $default only fires once a connection already exists (already authorised
# by $connect). This matches AWS's own reference architecture.
resource "aws_apigatewayv2_route" "ws_disconnect" {
  count     = var.live ? 1 : 0
  api_id    = aws_apigatewayv2_api.ws.id
  route_key = "$disconnect"
  target    = "integrations/${aws_apigatewayv2_integration.ws_disconnect[0].id}"
}

resource "aws_apigatewayv2_route" "ws_default" {
  count     = var.live ? 1 : 0
  api_id    = aws_apigatewayv2_api.ws.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.ws_default[0].id}"
}

# ─── Stage ──────────────────────────────────────────────────
# Stage name "prod" - WebSocket clients connect to
# wss://<api-id>.execute-api.<region>.amazonaws.com/prod?token=<JWT>
resource "aws_apigatewayv2_stage" "ws" {
  count       = var.live ? 1 : 0
  api_id      = aws_apigatewayv2_api.ws.id
  name        = "prod"
  auto_deploy = true

  # These references force stage deployment to include the routes. Without
  # them a stage created before the routes exist stays empty.
  depends_on = [
    aws_apigatewayv2_route.ws_connect,
    aws_apigatewayv2_route.ws_disconnect,
    aws_apigatewayv2_route.ws_default,
  ]

  default_route_settings {
    throttling_rate_limit    = 50
    throttling_burst_limit   = 100
    detailed_metrics_enabled = true
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.ws_access.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      ip               = "$context.identity.sourceIp"
      requestTime      = "$context.requestTime"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
      connectionId     = "$context.connectionId"
      eventType        = "$context.eventType"
      responseLatency  = "$context.responseLatency"
      integrationError = "$context.integrationErrorMessage"
      authorizerError  = "$context.authorizer.error"
    })
  }

  tags = {
    Name = "${var.project_name}-ws-prod"
  }
}

resource "aws_cloudwatch_log_group" "ws_access" {
  name              = "/aws/apigateway/${var.project_name}-ws"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-ws-access-logs"
  }
}
