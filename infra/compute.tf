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

  # SPA -> CloudFront -> HTTP API is same-origin from the browser's view
  # (CloudFront proxies /api/*), so no CORS preflight fires on that path.
  # This list only covers direct-to-API access from `var.cors_allow_origins`
  # (localhost:5173 during Vite dev, plus anything the operator passes in
  # via -var). Referencing aws_cloudfront_distribution here would create a
  # cycle (CF -> API GW origin -> CF domain in CORS) and buys nothing,
  # since the SPA never hits execute-api directly in prod.
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

  # CW-1 defect: every /v1/* call reached the ALB but fell through to the
  # default 404. A private integration's URI is a listener ARN, which has no
  # path component, so API Gateway does not forward the original path unless
  # told to. `overwrite:path` is the only key that sets the backend path;
  # $request.path is the full request path minus the stage name.
  # Ref: docs.aws.amazon.com/apigateway/latest/developerguide/http-api-parameter-mapping.html
  request_parameters = {
    "overwrite:path" = "$request.path"
  }
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

locals {
  # Every service validates the Cognito JWT itself (fail-closed): the HTTP API
  # authorizer checks signature and audience, middleware checks cognito:groups.
  common_environment = {
    ENV                   = "production"
    APP_REGION            = var.aws_region
    COGNITO_USER_POOL_ID  = aws_cognito_user_pool.main.id
    COGNITO_APP_CLIENT_ID = aws_cognito_user_pool_client.spa.id
    COGNITO_ISSUER        = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
    LOG_LEVEL             = "INFO"
  }

  services = {
    order = {
      task_role_arn = aws_iam_role.order_task.arn
      environment = {
        ORDERS_TABLE_NAME      = aws_dynamodb_table.orders.name
        IDEMPOTENCY_TABLE_NAME = aws_dynamodb_table.idempotency.name
        ORDERS_QUEUE_URL       = aws_sqs_queue.orders.url
        # Saga outcome receiver. Without these two the order is placed and the
        # command published, but nothing ever moves it out of PENDING - the
        # consumer thread simply never starts.
        ORDER_EVENTS_QUEUE_URL        = aws_sqs_queue.order_events.url
        COMPENSATION_CONSUMER_ENABLED = "true"
      }
      secrets = {}
    }

    inventory = {
      task_role_arn = aws_iam_role.inventory_task.arn
      environment = {
        ORDERS_QUEUE_URL = aws_sqs_queue.orders.url
        SNS_TOPIC_ARN    = aws_sns_topic.order_confirmed.arn
        # Without this the queue fills and no order is ever decided.
        CONSUMER_ENABLED = "true"
        DB_HOST          = aws_rds_cluster.inventory.endpoint
        # Derived rather than relying on the app default happening to match
        # Aurora's port.
        DB_PORT = tostring(aws_rds_cluster.inventory.port)
        DB_NAME = aws_rds_cluster.inventory.database_name
        DB_USER = aws_rds_cluster.inventory.master_username
      }
      # Password is pulled from the RDS-managed secret at task start —
      # it never appears in the task definition, state, or an env var value.
      secrets = {
        DB_PASSWORD = "${aws_rds_cluster.inventory.master_user_secret[0].secret_arn}:password::"
      }
    }

    user = {
      task_role_arn = aws_iam_role.user_task.arn
      environment   = {}
      secrets       = {}
    }

    product = {
      task_role_arn = aws_iam_role.product_task.arn
      environment = {
        PRODUCTS_TABLE_NAME = aws_dynamodb_table.products.name
        CACHE_TTL_SECONDS   = "30"
      }
      secrets = {}
    }
  }
}

# ─── TASK DEFINITIONS — ARM64 Graviton (ADR-08, −20% compute) ─
resource "aws_ecs_task_definition" "services" {
  for_each = local.services

  family                   = "${var.project_name}-${each.key}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  # Bumped to 512 CPU / 1024 memory (from 256 / 512) when the ADOT
  # collector sidecar landed. Fargate CPU/memory combos are discrete:
  # 512 CPU pairs with 1024/2048/3072/4096 MB. 1024 gives ~256 MB
  # headroom for the app (typical FastAPI RSS ~150-200 MB) + ~64 MB
  # for the collector + kernel + margins. If the app OOMs, jump to
  # 2048 - do not go back to 512 without removing the sidecar first.
  cpu                = 512
  memory             = 1024
  execution_role_arn = aws_iam_role.ecs_execution.arn
  task_role_arn      = each.value.task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([
    {
      name      = "${each.key}-service"
      image     = "${aws_ecr_repository.services["${each.key}-service"].repository_url}:${var.image_tag}"
      essential = true

      portMappings = [{
        containerPort = 8000
        protocol      = "tcp"
      }]

      # OTEL_EXPORTER_OTLP_ENDPOINT points the service's OpenTelemetry
      # SDK at the ADOT sidecar on localhost (same task = same
      # loopback). Powertools Tracer uses the AWS X-Ray SDK today so
      # this env var is mostly forward-compatible with a future
      # OTel-SDK migration, but the ADOT collector also scrapes
      # /metrics if we ever add that endpoint. Setting it now costs
      # nothing and stops a viva question "where's the OTel config?"
      environment = [
        for k, v in merge(
          local.common_environment,
          {
            POWERTOOLS_SERVICE_NAME     = "${each.key}-service"
            OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4317"
            OTEL_SERVICE_NAME           = "${var.project_name}-${each.key}"
            OTEL_RESOURCE_ATTRIBUTES    = "service.name=${var.project_name}-${each.key},service.namespace=${var.project_name},deployment.environment=production"
          },
          each.value.environment
        ) : { name = k, value = tostring(v) }
      ]

      secrets = [
        for k, v in each.value.secrets : { name = k, valueFrom = v }
      ]

      # dependsOn ensures the app doesn't try to emit spans before the
      # sidecar is listening on 4317. HEALTHY (not just STARTED) so the
      # collector is actually ready to receive.
      dependsOn = [{
        containerName = "adot-collector"
        condition     = "HEALTHY"
      }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.services[each.key].name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    },

    # ─── ADOT collector sidecar (backlog item observability) ──
    # AWS Distro for OpenTelemetry. Ships a preset ECS config at
    # /etc/ecs/ecs-default-config.yaml that fans OTLP receives out to
    # X-Ray (traces) + CloudWatch EMF (metrics). Runs as a sidecar in
    # the same task so the app talks to it over loopback (no cross-
    # container network cost, no service discovery).
    {
      name      = "adot-collector"
      image     = "public.ecr.aws/aws-observability/aws-otel-collector:v0.42.0"
      essential = false # A collector crash MUST NOT kill the app - it
      # only carries telemetry. Losing spans is preferable to losing
      # requests during a demo.

      command = ["--config=/etc/ecs/ecs-default-config.yaml"]

      # Health check: the collector exposes an HTTP health-check
      # extension on 13133 when the default config is used.
      healthCheck = {
        command     = ["CMD-SHELL", "wget -q -O - http://localhost:13133/ || exit 1"]
        interval    = 15
        timeout     = 5
        retries     = 3
        startPeriod = 20
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.services[each.key].name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "adot"
        }
      }
    },
  ])

  tags = {
    Name = "${var.project_name}-${each.key}-task"
  }
}

# ─── ECS SERVICES — desired count gated on `live` ─────────────
# depends_on the gated egress route so tasks never start before NAT exists
# on unpark (amendment 22 — otherwise the first image pull fails).
# NOTE: when Application Auto Scaling attaches in Week 7, add
#   lifecycle { ignore_changes = [desired_count] }
# here and park via the appautoscaling target's min_capacity instead.
resource "aws_ecs_service" "services" {
  for_each = local.services

  name            = "${var.project_name}-${each.key}-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.services[each.key].arn
  desired_count   = var.live ? var.service_desired_count : 0
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  # ECS rejects a target group that has no load balancer, so the attachment
  # follows the same gate as the ALB itself.
  dynamic "load_balancer" {
    for_each = var.live ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.services[each.key].arn
      container_name   = "${each.key}-service"
      container_port   = 8000
    }
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_route.private_egress]

  tags = {
    Name = "${var.project_name}-${each.key}-service"
  }
}

# ─── EVENTBRIDGE SCHEDULER — nightly park / morning restore ───
# Created DISABLED; enable from Week 4 as a safety net for a forgotten park.
# Timezone is explicit: the default is UTC, which would fire 00:00 at 05:30
# local (amendment 24).
resource "aws_scheduler_schedule" "park" {
  for_each = local.services

  name                         = "${var.project_name}-park-${each.key}"
  description                  = "Scale ${each.key} to 0 tasks overnight"
  state                        = "DISABLED"
  schedule_expression          = "cron(0 0 * * ? *)"
  schedule_expression_timezone = "Asia/Colombo"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ecs:updateService"
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({
      Cluster      = aws_ecs_cluster.main.name
      Service      = "${var.project_name}-${each.key}-service"
      DesiredCount = 0
    })
  }
}

resource "aws_scheduler_schedule" "restore" {
  for_each = local.services

  name                         = "${var.project_name}-restore-${each.key}"
  description                  = "Scale ${each.key} back up in the morning"
  state                        = "DISABLED"
  schedule_expression          = "cron(0 8 * * ? *)"
  schedule_expression_timezone = "Asia/Colombo"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ecs:updateService"
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({
      Cluster      = aws_ecs_cluster.main.name
      Service      = "${var.project_name}-${each.key}-service"
      DesiredCount = 1
    })
  }
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
    # `path` and `integrationStatus` were added after CW-1: without the path
    # in the log there was no way to tell a routing fault from a backend fault
    # without re-running the request.
    format = jsonencode({
      requestId         = "$context.requestId"
      ip                = "$context.identity.sourceIp"
      requestTime       = "$context.requestTime"
      httpMethod        = "$context.httpMethod"
      path              = "$context.path"
      routeKey          = "$context.routeKey"
      status            = "$context.status"
      integrationStatus = "$context.integrationStatus"
      responseLatency   = "$context.responseLatency"
      integrationError  = "$context.integrationErrorMessage"
      authorizerError   = "$context.authorizer.error"
    })
  }

  tags = {
    Name = "${var.project_name}-api-default-stage"
  }
}
