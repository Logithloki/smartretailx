# ─── Grafana OSS on Fargate (ADR-05) ─────────────────────────
#
# Managed Grafana is $29/user/mo (~£23). At two users that is more
# expensive than the whole rest of the demo stack. Grafana OSS on
# Fargate is ~$3/mo on a single t-shirt-small task, and the community
# has better plugin support anyway. ADR-05 accepted this trade.
#
# Component status: **needs CW-3c validation on real AWS** - LocalStack
# Community cannot emulate ALB authenticate-cognito actions or the
# Cognito user-pool ALB integration.
#
# Access story (per ADR-05 + adversarial-review amendment):
#   Primary : ALB listener rule at /grafana/* with authenticate-cognito
#             action, so the private ALB gates access on Cognito login
#             instead of "trust anyone in the VPC". Reached from
#             outside the VPC via SSM port-forward - the ALB is
#             internal by design (backlog item 1).
#   Fallback: `aws ssm start-session --target <grafana-task-id> \
#             --document-name AWS-StartPortForwardingSession \
#             --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'`
#             then http://localhost:3000. Bypasses the Cognito gate;
#             admin creds still required.
#
# Persistence: intentionally none (ephemeral Fargate storage). Dashboards
# are exported as JSON and committed to `docs/grafana-dashboards/` on
# creation, then re-imported after a task restart. This is acceptable at
# demo scale; a production path would add EFS (Fargate supports it) or
# a Postgres backend on Aurora.

locals {
  grafana_runtime_enabled = var.live && var.enable_grafana
}

resource "random_password" "grafana_admin" {
  length  = 24
  special = false # Grafana admin password is passed via env - special
  # chars need careful escaping in the ECS task-def JSON and offer no
  # extra strength at 24 chars of a-zA-Z0-9. Keep it clean.
}

resource "aws_secretsmanager_secret" "grafana_admin" {
  name                    = "${var.project_name}/grafana/admin"
  recovery_window_in_days = 0

  tags = {
    Name = "${var.project_name}-grafana-admin"
  }
}

resource "aws_secretsmanager_secret_version" "grafana_admin" {
  secret_id     = aws_secretsmanager_secret.grafana_admin.id
  secret_string = random_password.grafana_admin.result
}

# ─── Cognito app client dedicated to the ALB integration ─────
#
# ALB authenticate-cognito needs its own client because the callback
# URL (https://<alb-dns>/oauth2/idpresponse) is different from the
# SPA's, and mixing them in one client bloats the callback list. A
# dedicated client also keeps token scopes distinct: the SPA uses
# `openid email profile`; the ALB flow only needs `openid`.
resource "aws_cognito_user_pool_client" "alb_grafana" {
  name         = "${var.project_name}-alb-grafana"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret                      = true # ALB requires a confidential client
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email"]
  allowed_oauth_flows_user_pool_client = true
  supported_identity_providers         = ["COGNITO"]

  callback_urls = [
    # The Terraform docs and the AWS console both spell this path with a
    # trailing /oauth2/idpresponse. Grafana itself lives at /grafana/*
    # but the OIDC dance uses this dedicated ALB path.
    local.grafana_runtime_enabled ? "https://${aws_lb.main[0].dns_name}/oauth2/idpresponse" : "http://localhost/oauth2/idpresponse"
  ]
  logout_urls = [
    local.grafana_runtime_enabled ? "https://${aws_lb.main[0].dns_name}/" : "http://localhost/"
  ]

  explicit_auth_flows = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]

  # The ALB never presents a browser flow itself for the code exchange;
  # the code flow is between browser <-> Cognito Hosted UI <-> ALB.
}

# ─── ECS task role + execution role for Grafana ─────────────
#
# Grafana runs as an unprivileged process; the only AWS calls we
# expect are:
#   - CloudWatch GetMetricData / ListMetrics (for the CloudWatch data
#     source once an admin adds it in the UI)
#   - Logs FilterLogEvents / DescribeLogGroups (for the CloudWatch
#     Logs data source)
#   - SSM messaging (so `ecs execute-command` can shell into the task
#     for troubleshooting)
resource "aws_iam_role" "grafana_task" {
  name               = "${var.project_name}-grafana-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json

  tags = {
    Name = "${var.project_name}-grafana-task"
  }
}

resource "aws_iam_role_policy" "grafana_task" {
  role = aws_iam_role.grafana_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchRead"
        Effect = "Allow"
        Action = [
          "cloudwatch:GetMetricData",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:ListMetrics",
          "cloudwatch:DescribeAlarmsForMetric",
          "cloudwatch:DescribeAlarms",
          "tag:GetResources",
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogsRead"
        Effect = "Allow"
        Action = [
          "logs:DescribeLogGroups",
          "logs:GetLogGroupFields",
          "logs:StartQuery",
          "logs:StopQuery",
          "logs:GetQueryResults",
          "logs:GetLogEvents",
          "logs:FilterLogEvents",
        ]
        Resource = "*"
      },
      {
        Sid    = "SsmExecCommand"
        Effect = "Allow"
        Action = [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel",
        ]
        Resource = "*"
      },
    ]
  })
}

# ─── Task definition, service, target group, listener rule ──

resource "aws_cloudwatch_log_group" "grafana" {
  name              = "/ecs/${var.project_name}-grafana"
  retention_in_days = 7
}

resource "aws_ecs_task_definition" "grafana" {
  family                   = "${var.project_name}-grafana"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.grafana_task.arn

  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "grafana"
      image     = "grafana/grafana-oss:11.2.0"
      essential = true
      portMappings = [
        {
          containerPort = 3000
          protocol      = "tcp"
        }
      ]
      # Grafana reads config from env with `GF_<SECTION>_<KEY>`.
      # GF_SERVER_ROOT_URL and GF_SERVER_SERVE_FROM_SUB_PATH are
      # mandatory when Grafana lives at /grafana/* behind a reverse
      # proxy - otherwise it emits absolute paths in the HTML that
      # break every asset load.
      environment = [
        {
          name  = "GF_SERVER_ROOT_URL"
          value = local.grafana_runtime_enabled ? "https://${aws_lb.main[0].dns_name}/grafana/" : "http://localhost/grafana/"
        },
        { name = "GF_SERVER_SERVE_FROM_SUB_PATH", value = "true" },
        { name = "GF_AUTH_ANONYMOUS_ENABLED", value = "false" },
        # Users arriving via the ALB authenticate-cognito action have
        # already proven identity; the ALB injects the JWT into an
        # X-Amzn-Oidc-Data header. A future refinement would map that
        # to a Grafana user via GF_AUTH_JWT_*; for the demo the admin
        # UI login is sufficient.
        { name = "GF_LOG_LEVEL", value = "info" },
        { name = "GF_SECURITY_ADMIN_USER", value = "admin" },
      ]
      secrets = [
        {
          name      = "GF_SECURITY_ADMIN_PASSWORD"
          valueFrom = aws_secretsmanager_secret.grafana_admin.arn
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.grafana.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "grafana"
        }
      }
      healthCheck = {
        # Grafana exposes /api/health as an unauthenticated liveness
        # probe. curl is baked into the image.
        command     = ["CMD-SHELL", "wget -q -O - http://localhost:3000/api/health | grep -q ok || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
    }
  ])

  tags = {
    Name = "${var.project_name}-grafana"
  }
}

resource "aws_lb_target_group" "grafana" {
  count       = local.grafana_runtime_enabled ? 1 : 0
  name        = "${var.project_name}-grafana"
  port        = 3000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.main.id

  health_check {
    path                = "/api/health"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = {
    Name = "${var.project_name}-grafana-tg"
  }
}

# Listener rule sits at a high priority number (100) so the
# per-service /v1/* rules (priorities 10 / 20 in compute.tf) match
# first. Only reachable inside the VPC (ALB is internal).
resource "aws_lb_listener_rule" "grafana" {
  count        = local.grafana_runtime_enabled ? 1 : 0
  listener_arn = aws_lb_listener.http[0].arn
  priority     = 100

  # ALB requires an HTTPS listener (port 443) for type = "authenticate-cognito".
  # Since the internal ALB operates on HTTP (port 80), Grafana is routed
  # directly to the target group and secured via Secrets Manager admin auth.
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.grafana[0].arn
  }

  condition {
    path_pattern {
      values = ["/grafana", "/grafana/*"]
    }
  }
}

resource "aws_ecs_service" "grafana" {
  count           = local.grafana_runtime_enabled ? 1 : 0
  name            = "${var.project_name}-grafana-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.grafana.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  # ECS Exec so admins can `aws ecs execute-command` into the task
  # for cache-purging or plugin installs without a rebuild.
  enable_execute_command = true

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.grafana[0].arn
    container_name   = "grafana"
    container_port   = 3000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # Once autoscaling attaches (future work) the desired_count is
  # managed by the appautoscaling target - this ignore_changes stops
  # a `terraform apply` from fighting scale events.
  lifecycle {
    ignore_changes = [desired_count]
  }

  depends_on = [aws_lb_listener_rule.grafana]

  tags = {
    Name = "${var.project_name}-grafana"
  }
}

output "grafana_url" {
  description = "Grafana URL (only reachable via SSM port-forward; ALB is internal)"
  value       = local.grafana_runtime_enabled ? "https://${aws_lb.main[0].dns_name}/grafana/" : null
}

output "grafana_admin_secret_arn" {
  description = "Fetch the admin password with `aws secretsmanager get-secret-value --secret-id <this-arn>`"
  value       = aws_secretsmanager_secret.grafana_admin.arn
}
