# ─── SECURITY GROUPS ──────────────────────────────────────────

# VPC Link ENIs (API Gateway HTTP API → internal ALB). The VPC Link itself
# lands in Week 1 Day 4; its SG exists now so the ALB can be scoped to it.
resource "aws_security_group" "vpc_link" {
  name        = "${var.project_name}-vpc-link-sg"
  description = "API Gateway VPC Link ENIs"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-vpc-link-sg"
  }
}

# Internal ALB: accepts traffic ONLY from the VPC Link SG (backlog item 1 —
# never from the internet; the public-ingress SG was the auth-bypass flaw).
resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-sg"
  description = "Internal ALB - accepts traffic from API Gateway VPC Link only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.vpc_link.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-alb-sg"
  }
}

resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-tasks-sg"
  description = "ECS Fargate tasks - accepts traffic from ALB only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-ecs-tasks-sg"
  }
}

resource "aws_security_group" "aurora" {
  name        = "${var.project_name}-aurora-sg"
  description = "Aurora - accepts PostgreSQL from ECS tasks only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-aurora-sg"
  }
}

# ─── IAM — one shared execution role + four least-privilege task roles ────
# (backlog item 4; matrix documented in the report)

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role: image pull + logs + injecting the RDS-managed DB secret
# into the inventory task via `secrets.valueFrom` (never plaintext env).
resource "aws_iam_role" "ecs_execution" {
  name               = "${var.project_name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "read-aurora-managed-secret"
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_rds_cluster.inventory.master_user_secret[0].secret_arn]
    }]
  })
}

# Order Service: orders + idempotency tables, publish commands to SQS.
resource "aws_iam_role" "order_task" {
  name               = "${var.project_name}-order-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "order_task" {
  role = aws_iam_role.order_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query"]
        Resource = [
          aws_dynamodb_table.orders.arn,
          "${aws_dynamodb_table.orders.arn}/index/*",
          aws_dynamodb_table.idempotency.arn
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = [aws_sqs_queue.orders.arn]
      }
    ]
  })
}

# Inventory Service: consume order commands, publish domain events.
resource "aws_iam_role" "inventory_task" {
  name               = "${var.project_name}-inventory-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "inventory_task" {
  role = aws_iam_role.inventory_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = [aws_sqs_queue.orders.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = [aws_sns_topic.order_confirmed.arn]
      }
    ]
  })
}

# User Service: cognito-idp admin APIs scoped to this pool only.
resource "aws_iam_role" "user_task" {
  name               = "${var.project_name}-user-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "user_task" {
  role = aws_iam_role.user_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "cognito-idp:AdminGetUser",
        "cognito-idp:AdminUpdateUserAttributes",
        "cognito-idp:AdminListGroupsForUser",
        "cognito-idp:ListUsers"
      ]
      Resource = [aws_cognito_user_pool.main.arn]
    }]
  })
}

# Product Service: read-only on products table + its GSI.
resource "aws_iam_role" "product_task" {
  name               = "${var.project_name}-product-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "product_task" {
  role = aws_iam_role.product_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"]
      Resource = [
        aws_dynamodb_table.products.arn,
        "${aws_dynamodb_table.products.arn}/index/*"
      ]
    }]
  })
}

# EventBridge Scheduler: may only change the desired count of this
# project's four services, nothing else in ECS.
data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.project_name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "scheduler" {
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["ecs:UpdateService"]
      Resource = [
        for name, _ in local.services :
        "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:service/${var.project_name}-cluster/${var.project_name}-${name}-service"
      ]
    }]
  })
}

# ─── COGNITO — the ONLY user pool (backlog item 2) ────────────
# Defined exclusively in Terraform; the Week-1 console-created pool is gone.
# Free tier covers this demo's MAU, so it is not gated on `live`.

resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-users"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # MFA is OFF for the demo; report documents it as a one-flag scale-up
  # (production practices at demo sizing — lecturer ruling).
  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = false # customers self-register (UI scope H.2)
  }

  tags = {
    Name = "${var.project_name}-users"
  }
}

# Hosted UI needs a domain or the login page simply does not exist
# (backlog item 19). Prefix must be globally unique.
resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.project_name}-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.main.id
}

# Public SPA client: authorization-code + PKCE, no secret to leak in a browser.
resource "aws_cognito_user_pool_client" "spa" {
  name         = "${var.project_name}-spa"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]

  callback_urls = var.frontend_callback_urls
  logout_urls   = var.frontend_logout_urls

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_ADMIN_USER_PASSWORD_AUTH", # scripts/get-jwt.sh for CW smoke tests
    "ALLOW_REFRESH_TOKEN_AUTH"
  ]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  prevent_user_existence_errors = "ENABLED"
}

# RBAC groups. The HTTP API JWT authorizer validates signature/claims only —
# the `cognito:groups` claim is enforced in each service's middleware.
resource "aws_cognito_user_group" "admin" {
  name         = "admin"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Product CRUD and stock adjustment"
  precedence   = 1
}

resource "aws_cognito_user_group" "customer" {
  name         = "customer"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Browse products, place and view own orders"
  precedence   = 10
}
