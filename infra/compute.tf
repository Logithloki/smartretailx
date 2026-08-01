# ─── ECR — immutable tags + keep-5 lifecycle (backlog item 9) ─
# force_delete so the Week-7 destroy/apply DR drill completes on
# non-empty repos (adversarial-review amendment).
resource "aws_ecr_repository" "services" {
  for_each = toset([
    "order-service",
    "inventory-service",
    "user-service",
    "product-service"
  ])

  name                 = "${var.project_name}/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "${var.project_name}-${each.key}"
  }
}

resource "aws_ecr_lifecycle_policy" "keep_5" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the 5 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = {
        type = "expire"
      }
    }]
  })
}

# ─── ECS CLUSTER (ADR-01: Fargate, $0 idle) ───────────────────
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.project_name}-cluster"
  }
}

# ─── INTERNAL ALB — gated on `live` (backlog items 1 + 5) ─────
# Private subnets, reachable only via the API Gateway VPC Link.
# NOTE (amendment): the Week-1-D4 API GW integration + routes must carry the
# same count as this listener — they reference its ARN.
resource "aws_lb" "main" {
  count              = var.live ? 1 : 0
  name               = "${var.project_name}-alb"
  internal           = true
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.private[*].id

  tags = {
    Name = "${var.project_name}-alb"
  }
}

# Target groups are free — not gated.
resource "aws_lb_target_group" "services" {
  for_each = {
    order     = "/v1/orders*"
    inventory = "/v1/inventory*"
    user      = "/v1/users*"
    product   = "/v1/products*"
  }

  name        = "${var.project_name}-${each.key}-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = {
    Name = "${var.project_name}-${each.key}-tg"
  }
}

resource "aws_lb_listener" "http" {
  count             = var.live ? 1 : 0
  load_balancer_arn = aws_lb.main[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "application/json"
      message_body = jsonencode({ error = "route not found" })
      status_code  = "404"
    }
  }

  tags = {
    Name = "${var.project_name}-listener"
  }
}

resource "aws_lb_listener_rule" "services" {
  for_each = var.live ? {
    order     = { pattern = "/v1/orders*", priority = 10 }
    inventory = { pattern = "/v1/inventory*", priority = 20 }
    user      = { pattern = "/v1/users*", priority = 30 }
    product   = { pattern = "/v1/products*", priority = 40 }
  } : {}

  listener_arn = aws_lb_listener.http[0].arn
  priority     = each.value.priority

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.services[each.key].arn
  }

  condition {
    path_pattern {
      values = [each.value.pattern]
    }
  }
}

# ─── API GATEWAY HTTP API v2 (ADR-02: −71% vs REST) ───────────
# VPC Link carries no hourly charge on HTTP APIs, so it is not gated —
# only the integration and routes are (they reference the ALB listener).

resource "aws_apigatewayv2_vpc_link" "main" {
  name               = "${var.project_name}-vpc-link"
  subnet_ids         = aws_subnet.private[*].id
  security_group_ids = [aws_security_group.vpc_link.id]

  tags = {
    Name = "${var.project_name}-vpc-link"
  }
}

# CORS (backlog item 18): without it the SPA fails in-browser while curl works.
# Week 5 D4 adds the CloudFront origin to var.cors_allow_origins.
resource "aws_apigatewayv2_api" "main" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"
  description   = "SmartRetailX public edge - JWT authorised, VPC Link to internal ALB"

  cors_configuration {
    allow_origins  = var.cors_allow_origins
    allow_methods  = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    allow_headers  = ["authorization", "content-type", "idempotency-key"]
    expose_headers = ["x-cache"]
    max_age        = 300
  }

  tags = {
    Name = "${var.project_name}-api"
  }
}

# Validates signature/issuer/audience against the Cognito JWKS.
# Group-based RBAC is enforced in service middleware, not here.
resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.main.id
  name             = "${var.project_name}-cognito-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.spa.id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
  }
}

resource "aws_apigatewayv2_integration" "alb" {
  count              = var.live ? 1 : 0
  api_id             = aws_apigatewayv2_api.main.id
  integration_type   = "HTTP_PROXY"
  integration_method = "ANY"
  integration_uri    = aws_lb_listener.http[0].arn
  connection_type    = "VPC_LINK"
  connection_id      = aws_apigatewayv2_vpc_link.main.id
}

locals {
  # Two route keys per service: the collection and everything beneath it.
  api_route_keys = var.live ? flatten([
    for svc in ["orders", "inventory", "users", "products"] : [
      "ANY /v1/${svc}",
      "ANY /v1/${svc}/{proxy+}"
    ]
  ]) : []
}

resource "aws_apigatewayv2_route" "services" {
  for_each = toset(local.api_route_keys)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.alb[0].id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit    = 50
    throttling_burst_limit   = 100
    detailed_metrics_enabled = true
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      ip               = "$context.identity.sourceIp"
      requestTime      = "$context.requestTime"
      httpMethod       = "$context.httpMethod"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
      responseLatency  = "$context.responseLatency"
      integrationError = "$context.integrationErrorMessage"
      authorizerError  = "$context.authorizer.error"
    })
  }

  tags = {
    Name = "${var.project_name}-api-default-stage"
  }
}
