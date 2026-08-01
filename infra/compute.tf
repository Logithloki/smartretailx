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
