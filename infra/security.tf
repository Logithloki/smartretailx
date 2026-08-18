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

# Order Service: atomically writes orders + outbox and manages idempotency.
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
        Sid      = "ProductPricingReadModel"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:BatchGetItem"]
        Resource = [aws_dynamodb_table.products.arn]
      },
      {
        Sid    = "PromotionPricingReadModel"
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:Query"]
        Resource = [
          aws_dynamodb_table.promotions.arn,
          "${aws_dynamodb_table.promotions.arn}/index/enabled-startsAt-index"
        ]
      },
      {
        Sid      = "OrderOutboxTable"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem"]
        Resource = [aws_dynamodb_table.order_outbox.arn]
      },
      {
        # Orders: no DeleteItem. Orders are financial records - the same
        # reasoning that removed TTL from this table (backlog item 7) says the
        # service should not be able to delete one either.
        Sid    = "OrdersTable"
        Effect = "Allow"
        Action = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query", "dynamodb:Scan"]
        Resource = [
          aws_dynamodb_table.orders.arn,
          "${aws_dynamodb_table.orders.arn}/index/*"
        ]
      },
      {
        # Idempotency: DeleteItem IS required - IdempotencyStore.release()
        # drops a claim when order creation fails, so an honest retry is not
        # wedged at 409 forever. Query is not used, so it is not granted.
        Sid    = "IdempotencyTable"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem"
        ]
        Resource = [aws_dynamodb_table.idempotency.arn]
      },
      {
        # Saga compensation receiver.
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = [aws_sqs_queue.order_events.arn]
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
        "cognito-idp:AdminListGroupsForUser",
        "cognito-idp:AdminDeleteUser",
        "cognito-idp:ListUsers"
      ]
      Resource = [aws_cognito_user_pool.main.arn]
    }]
  })
}

# Product Service: catalogue reads plus admin CRUD (backlog item 28).
resource "aws_iam_role" "product_task" {
  name               = "${var.project_name}-product-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "product_task" {
  role = aws_iam_role.product_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Reads span the base table and the category-index GSI.
        Sid    = "ProductReads"
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"]
        Resource = [
          aws_dynamodb_table.products.arn,
          "${aws_dynamodb_table.products.arn}/index/*"
        ]
      },
      {
        Sid      = "PromotionReadsAndWrites"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = [aws_dynamodb_table.promotions.arn, "${aws_dynamodb_table.promotions.arn}/index/*"]
      },
      {
        # Writes go to the base table only - a GSI cannot be written directly,
        # so granting index/* here would be a permission that does nothing.
        Sid      = "ProductAdminWrites"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
        Resource = [aws_dynamodb_table.products.arn]
      }
    ]
  })
}

# ─── LAMBDA EXECUTION ROLES ───────────────────────────────────

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# ─── ADOT sidecar permissions on every service task role ────
#
# The collector runs inside the task and inherits the task role's
# credentials via IMDS. Rather than duplicating the same policy block
# on all four inline task policies (order / inventory / user /
# product), attach the AWS-managed policies once per role via a map.
#
# Why managed policies here (a break from the "spell it out" default):
# these two exactly describe "what an ADOT collector needs" and are
# maintained by AWS - if a future ADOT release wants a new API call,
# the managed policy is updated centrally. A hand-rolled equivalent
# would drift.
#
#   AWSXrayWriteOnlyAccess -> PutTraceSegments, PutTelemetryRecords,
#                             GetSamplingRules, GetSamplingTargets.
#   CloudWatchAgentServerPolicy -> PutMetricData + CW Logs write path
#                                  used by the EMF exporter.
locals {
  adot_task_roles = {
    order     = aws_iam_role.order_task.name
    inventory = aws_iam_role.inventory_task.name
    user      = aws_iam_role.user_task.name
    product   = aws_iam_role.product_task.name
  }
  adot_managed_policies = [
    "arn:aws:iam::aws:policy/AWSXrayWriteOnlyAccess",
    "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy",
  ]
}

resource "aws_iam_role_policy_attachment" "adot_task_policies" {
  for_each = {
    for pair in flatten([
      for svc, role in local.adot_task_roles : [
        for arn in local.adot_managed_policies : {
          key  = "${svc}-${basename(arn)}"
          role = role
          arn  = arn
        }
      ]
    ]) : pair.key => pair
  }

  role       = each.value.role
  policy_arn = each.value.arn
}

# Written out rather than attaching AWSLambdaBasicExecutionRole so the report's
# least-privilege matrix shows real grants instead of a managed-policy name.
locals {
  lambda_logging_actions = [
    "logs:CreateLogGroup",
    "logs:CreateLogStream",
    "logs:PutLogEvents",
  ]
  # Powertools Tracer needs these; without them tracing fails silently and the
  # service map simply has a hole where the Lambda should be.
  lambda_xray_actions = [
    "xray:PutTraceSegments",
    "xray:PutTelemetryRecords",
  ]
}

resource "aws_iam_role" "notification_lambda" {
  name               = "${var.project_name}-notification-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "notification_lambda" {
  role = aws_iam_role.notification_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = local.lambda_logging_actions
        Resource = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-notification:*"]
      },
      {
        Sid      = "Tracing"
        Effect   = "Allow"
        Action   = local.lambda_xray_actions
        Resource = ["*"] # X-Ray write actions do not support resource scoping
      },
      {
        # Powertools Idempotency reads, writes and deletes its own records.
        Sid    = "IdempotencyStore"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem"
        ]
        Resource = [aws_dynamodb_table.idempotency.arn]
      },
      {
        Sid      = "SendEmail"
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = ["*"]
        Condition = {
          # Scopes sending to our own From address, so a compromised function
          # cannot send as anyone else in the account.
          StringEquals = { "ses:FromAddress" = var.ses_sender_email }
        }
      }
    ]
  })
}

resource "aws_iam_role" "reconciliation_lambda" {
  name               = "${var.project_name}-reconciliation-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "reconciliation_lambda" {
  role = aws_iam_role.reconciliation_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = local.lambda_logging_actions
        Resource = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-stock-reconciliation:*"]
      },
      {
        Sid      = "Tracing"
        Effect   = "Allow"
        Action   = local.lambda_xray_actions
        Resource = ["*"]
      },
      {
        # Read-only on orders. Reconciliation reports anomalies; it must not be
        # able to "fix" a financial record by rewriting it.
        Sid      = "ScanOrders"
        Effect   = "Allow"
        Action   = ["dynamodb:Scan", "dynamodb:Query"]
        Resource = [aws_dynamodb_table.orders.arn, "${aws_dynamodb_table.orders.arn}/index/*"]
      },
      {
        Sid      = "RaiseAlert"
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = [aws_sns_topic.alerts.arn]
      }
    ]
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
    Statement = [
      {
        Sid    = "ParkAndRestoreServices"
        Effect = "Allow"
        Action = ["ecs:UpdateService"]
        Resource = [
          for name, _ in local.services :
          "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:service/${var.project_name}-cluster/${var.project_name}-${name}-service"
        ]
      },
      {
        Sid      = "InvokeReconciliation"
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = [aws_lambda_alias.reconciliation.arn]
      }
    ]
  })
}

# ─── WEBSOCKET LAMBDA DATA ACCESS (backlog item 33) ───────────
#
# The connect / disconnect / push Lambdas have their basic execution roles
# defined in lambdas.tf (assume + logs + tracing). The actual data grants
# live here so the least-privilege matrix stays in one place with the
# ECS task role policies.
#
# Split (matches the least-privilege discussion in the report):
#   connect      -> PutItem only on websocket-connections (writes its own row)
#   disconnect   -> DeleteItem only (removes its own row; no read needed)
#   push         -> Query on userId-index (customer-scoped fan-out lookup) +
#                   DeleteItem on the table (inline pruning of stale rows) PLUS
#                   execute-api:ManageConnections on the WSS stage ARN

resource "aws_iam_role_policy" "ws_connect_lambda_data" {
  name = "websocket-connections-put"
  role = aws_iam_role.ws_connect_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "RecordConnection"
      Effect   = "Allow"
      Action   = ["dynamodb:PutItem"]
      Resource = [aws_dynamodb_table.websocket_connections.arn]
    }]
  })
}

resource "aws_iam_role_policy" "ws_disconnect_lambda_data" {
  name = "websocket-connections-delete"
  role = aws_iam_role.ws_disconnect_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "RemoveConnection"
      Effect   = "Allow"
      Action   = ["dynamodb:DeleteItem"]
      Resource = [aws_dynamodb_table.websocket_connections.arn]
    }]
  })
}

resource "aws_iam_role_policy" "ws_push_lambda_data" {
  name = "websocket-connections-read-plus-manage"
  role = aws_iam_role.ws_push_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadOwnedConnections"
        Effect   = "Allow"
        Action   = ["dynamodb:Query"]
        Resource = ["${aws_dynamodb_table.websocket_connections.arn}/index/userId-index"]
      },
      {
        Sid      = "ReadPublicConnectionIds"
        Effect   = "Allow"
        Action   = ["dynamodb:Scan"]
        Resource = [aws_dynamodb_table.websocket_connections.arn]
      },
      {
        # Stale rows (410 GoneException) are pruned inline.
        Sid      = "PruneStaleConnection"
        Effect   = "Allow"
        Action   = ["dynamodb:DeleteItem"]
        Resource = [aws_dynamodb_table.websocket_connections.arn]
      },
      {
        # ManageConnections is the API-Gateway-side permission for
        # postToConnection / getConnection / deleteConnection. Resource
        # scoping uses the execute-api ARN of THIS API's stage only, so a
        # compromised push Lambda cannot reach into another API in the
        # account.
        Sid      = "PostToConnection"
        Effect   = "Allow"
        Action   = ["execute-api:ManageConnections"]
        Resource = ["arn:aws:execute-api:${var.aws_region}:${data.aws_caller_identity.current.account_id}:${aws_apigatewayv2_api.ws.id}/*/POST/@connections/*"]
      },
    ]
  })
}

# ─── COGNITO — the ONLY user pool (backlog item 2) ────────────
# Defined exclusively in Terraform; the Week-1 console-created pool is gone.
# Free tier covers this demo's MAU, so it is not gated on `live`.

locals {
  cognito_restrict_localhost = contains(["staging", "production"], var.environment_name)
  cognito_frontend_callback_urls = local.cognito_restrict_localhost ? [
    for url in var.frontend_callback_urls : url
    if !startswith(url, "http://localhost") && !startswith(url, "http://127.0.0.1")
  ] : var.frontend_callback_urls
  cognito_frontend_logout_urls = local.cognito_restrict_localhost ? [
    for url in var.frontend_logout_urls : url
    if !startswith(url, "http://localhost") && !startswith(url, "http://127.0.0.1")
  ] : var.frontend_logout_urls
}

resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-users"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "Welcome to SmartRetailX - Your Verification Code"
    email_message        = "<h2>Welcome to SmartRetailX!</h2><p>Thank you for creating an account with us. To complete your registration, please use the following 6-digit verification code:</p><h3 style='color: #059669; font-size: 24px; letter-spacing: 2px;'>{####}</h3><p>If you did not request this code, please safely ignore this email.</p><br><p>Best regards,<br><strong>The SmartRetailX Team</strong></p>"
  }

  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  # PR A: switch MFA from OFF to OPTIONAL so individual users can enrol a
  # TOTP authenticator via Profile > Security in a later PR.  OPTIONAL
  # means:
  #   - a user who has NOT called SetUserMFAPreference remains
  #     non-MFA-enrolled and continues to authenticate exactly as before,
  #   - a user who opts in with an authenticator app must present a TOTP
  #     code on every subsequent sign-in.
  # CI users (see scripts/obtain-cognito-token.sh) never call
  # SetUserMFAPreference so they stay non-MFA-enrolled.
  mfa_configuration = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
  }

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

  dynamic "lambda_config" {
    for_each = var.enable_cognito_auto_confirm ? [1] : []
    content {
      pre_sign_up = aws_lambda_function.cognito_auto_confirm.arn
    }
  }

  tags = {
    Name = "${var.project_name}-users"
  }
}

# ─── Cognito Pre-SignUp Auto-Confirm & SES Registration Lambda ───
#
# PR B narrows the auto-confirm rule.
#
# Before PR B: the Lambda auto-confirmed EVERY signup on the Test pool, so
# ordinary Sign Up would land as CONFIRMED without an email verification
# code and Test could not exercise the real production-like verification
# flow.
#
# After PR B: only synthetic CI/E2E identities that match the explicit
# pattern below are auto-confirmed.  Ordinary human signups on Test now
# behave exactly like Staging (UNCONFIRMED, real Cognito email, /verify-email
# UX exercised).
#
# Deliberately narrow: the pattern is limited to the exact
# `ci-{role}-{env}@example.com` shape used by the runtime-mint scripts, so
# broader `@example.com` or `ci-*` collisions cannot bypass verification.
#
# Terraform stamps CI_AUTO_CONFIRM_PATTERN into the Lambda source at plan
# time so the pattern lives in one place; changing it requires a Terraform
# apply, not a runtime environment variable.
data "archive_file" "cognito_auto_confirm_zip" {
  type        = "zip"
  output_path = "${path.module}/cognito_auto_confirm.zip"
  source {
    content = replace(<<-EOF
import os
import re
import boto3

ses_client = boto3.client('ses', region_name=os.environ.get('AWS_REGION', 'eu-west-1'))

# Only the exact synthetic CI/E2E identity shape the runtime-mint scripts
# create is auto-confirmed.  Anything else - including any real customer
# who happens to sign up with an @example.com address - goes through the
# normal Cognito email-verification flow.
CI_AUTO_CONFIRM_PATTERN = re.compile(
    r'^ci-(smoke|customer|admin)-(development|test|staging)@example\.com$'
)

def handler(event, context):
    email = (event.get('request', {}) or {}).get('userAttributes', {}).get('email', '') or ''
    if CI_AUTO_CONFIRM_PATTERN.fullmatch(email):
        event['response']['autoConfirmUser'] = True
        event['response']['autoVerifyEmail'] = True
        try:
            ses_client.verify_email_identity(EmailAddress=email)
            print(f'CI auto-confirm: dispatched SES verification to {email}')
        except Exception as e:
            print(f'CI auto-confirm: SES verify_email_identity failed for {email}: {e}')
    # Non-matching addresses: return the event unmodified so Cognito sends
    # its own 6-digit verification code (this is the desired production
    # behaviour on both Dev and Staging).
    return event
EOF
    , "\r\n", "\n")
    filename = "index.py"
  }
}

resource "aws_iam_role" "cognito_auto_confirm_role" {
  name = "${var.project_name}-cognito-auto-confirm-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "cognito_auto_confirm_ses" {
  name = "${var.project_name}-cognito-ses-verify-policy"
  role = aws_iam_role.cognito_auto_confirm_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ses:VerifyEmailIdentity", "ses:GetIdentityVerificationAttributes"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "cognito_auto_confirm_logs" {
  role       = aws_iam_role.cognito_auto_confirm_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "cognito_auto_confirm" {
  filename         = data.archive_file.cognito_auto_confirm_zip.output_path
  function_name    = "${var.project_name}-cognito-auto-confirm"
  role             = aws_iam_role.cognito_auto_confirm_role.arn
  handler          = "index.handler"
  runtime          = "python3.12"
  source_code_hash = data.archive_file.cognito_auto_confirm_zip.output_base64sha256
}

resource "aws_lambda_permission" "cognito_auto_confirm_perm" {
  statement_id  = "AllowCognitoInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cognito_auto_confirm.function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = aws_cognito_user_pool.main.arn
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

  # Hosted UI redirects live at two homes:
  #   - localhost:5173 during Vite dev (backlog 27 SPA scaffold)
  #   - the CloudFront distribution domain in prod
  # Cognito requires every URL used in an auth-code flow to be pre-registered,
  # so the SPA cannot receive the callback on a URL not in this list.
  callback_urls = concat(
    local.cognito_frontend_callback_urls,
    [
      "https://${aws_cloudfront_distribution.main.domain_name}/callback",
      "https://${aws_cloudfront_distribution.main.domain_name}/",
    ],
  )
  logout_urls = concat(
    local.cognito_frontend_logout_urls,
    ["https://${aws_cloudfront_distribution.main.domain_name}/"],
  )

  explicit_auth_flows = [
    # Server-side CI runtime-mint scripts (obtain-smoke-access-token.sh /
    # obtain-cognito-token.sh) call AdminInitiateAuth with a dedicated
    # deploy role.  This flow is not available to the SPA.
    "ALLOW_ADMIN_USER_PASSWORD_AUTH",
    # PR A: SRP authentication for the custom React sign-in page.  The
    # password never leaves the browser in cleartext; SRP is the AWS-
    # recommended browser client flow.  Amplify Auth v6 uses this flow
    # by default when we pass authFlowType: "USER_SRP_AUTH".
    "ALLOW_USER_SRP_AUTH",
    # Refresh-token flow for both the SPA and CI scripts.
    "ALLOW_REFRESH_TOKEN_AUTH",
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

# ─── Cognito Hosted UI Customization ─────────────────────────
resource "aws_cognito_user_pool_ui_customization" "main" {
  client_id    = aws_cognito_user_pool_client.spa.id
  user_pool_id = aws_cognito_user_pool.main.id

  css = replace(<<-EOF
.background-customizable {
  background-color: #fafafa !important;
  font-family: 'Plus Jakarta Sans', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
}

.banner-customizable {
  background-color: #ffffff !important;
  border-bottom: 1px solid #e4e4e7 !important;
  padding: 16px 0 !important;
}

.label-customizable {
  color: #09090b !important;
  font-weight: 600 !important;
  font-size: 13px !important;
}

.textDescription-customizable {
  color: #52525b !important;
  font-size: 13px !important;
  padding-top: 6px !important;
}

.inputField-customizable {
  border-radius: 8px !important;
  border: 1px solid #cbd5e1 !important;
  color: #09090b !important;
  padding: 10px 14px !important;
  font-size: 14px !important;
  background-color: #ffffff !important;
}

.inputField-customizable:focus {
  border-color: #09090b !important;
  box-shadow: 0 0 0 3px rgba(9, 9, 11, 0.08) !important;
  background-color: #ffffff !important;
}

.submitButton-customizable {
  background-color: #09090b !important;
  border-radius: 8px !important;
  font-weight: 700 !important;
  font-size: 14px !important;
  color: #ffffff !important;
  border: none !important;
  padding: 11px !important;
  letter-spacing: 0.3px !important;
}

.submitButton-customizable:hover {
  background-color: #18181b !important;
}

.redirect-customizable {
  color: #09090b !important;
  font-weight: 600 !important;
  text-decoration: none !important;
}
EOF
  , "\r\n", "\n")
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
