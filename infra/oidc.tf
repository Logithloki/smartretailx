# ─── GitHub Actions OIDC federation (backlog item 10) ────────
#
# Removes the long-lived AWS_ACCESS_KEY_ID from GitHub secrets - required
# for the assignment ("delete stored AWS access keys" in the CLAUDE.md
# fix backlog). Instead, GitHub's own OIDC IdP mints a short-lived JWT
# for each workflow run, and we let it exchange that JWT for a temporary
# IAM role (aws-actions/configure-aws-credentials handles the STS
# AssumeRoleWithWebIdentity call).
#
# Component status: **needs CW-3b validation on real AWS** - the OIDC
# provider registration and the STS trust chain only work end-to-end
# once a workflow actually runs against real AWS. LocalStack does not
# support GitHub-federated OIDC.

# ─── The IdP registration ─────────────────────────────────────
#
# AWS validates GitHub through its trusted root CA library, so configured
# thumbprints are retained but not used for GitHub certificate verification.
# This provider was originally created with the legacy thumbprint below; AWS
# retains that value when the argument is removed, so declaring the retained
# value prevents perpetual drift without recreating the OIDC provider.
resource "aws_iam_openid_connect_provider" "github" {
  # IAM OIDC providers are account-global. Baseline owns this singleton;
  # isolated runtime stacks reference it instead of attempting a duplicate.
  count = var.environment_name == "baseline" ? 1 : 0

  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["ab9d0263244dd0326eb67015705a667e79cfe998"]

  tags = {
    Name = "${var.project_name}-github-oidc"
  }
}

# ─── The role GitHub Actions assumes ─────────────────────────
#
# The trust policy is the security-critical piece. Two sub-conditions
# are mandatory; miss either one and you have opened your account to
# anyone with a GitHub Actions workflow:
#
#   1. token.actions.githubusercontent.com:aud MUST equal sts.amazonaws.com
#      - This is what `configure-aws-credentials` uses as the audience,
#        and dropping it would let a token intended for any other AWS
#        account or third-party service be replayed against us.
#   2. token.actions.githubusercontent.com:sub MUST equal the repository's
#      exact GitHub Environment subject. GitHub changes the subject to
#      `repo:owner/repo:environment:name` when a job declares an environment.
#      This lets GitHub Environment reviewers and branch restrictions remain
#      the authoritative deployment gate, including for production.
locals {
  github_deploy_environment = var.environment_name == "baseline" ? "development" : var.environment_name
  github_oidc_provider_arn = var.environment_name == "baseline" ? (
    aws_iam_openid_connect_provider.github[0].arn
  ) : data.aws_iam_openid_connect_provider.github[0].arn

  # The deploy role only needs the predictable names of the Lambda functions
  # that CI promotes. Keep these as strings so the IAM policy does not depend
  # on Lambda resource archives, hashes, or Terraform function resources.
  gha_deploy_lambda_names = [
    "${var.project_name}-notification",
    "${var.project_name}-stock-reconciliation",
    "${var.project_name}-order-outbox-publisher",
    "${var.project_name}-ws-authorizer",
    "${var.project_name}-ws-connect",
    "${var.project_name}-ws-disconnect",
    "${var.project_name}-ws-push",
  ]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.environment_name == "baseline" ? 0 : 1
  arn   = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
}

moved {
  from = aws_iam_openid_connect_provider.github
  to   = aws_iam_openid_connect_provider.github[0]
}

resource "aws_iam_role" "gha_deploy" {
  name = "${var.project_name}-gha-deploy"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.github_oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:environment:${local.github_deploy_environment}"
        }
      }
    }]
  })

  # Short session for defence in depth. Even if a workflow leaks its
  # credentials, they expire in 60 min.
  max_session_duration = 3600

  tags = {
    Name = "${var.project_name}-gha-deploy"
  }
}

# Build-once role: main may push immutable artifacts, but cannot deploy them.
resource "aws_iam_role" "gha_release" {
  name = "${var.project_name}-gha-release"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.github_oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:ref:refs/heads/main"
        }
      }
    }]
  })

  max_session_duration = 3600

  tags = {
    Name = "${var.project_name}-gha-release"
  }
}

moved {
  from = aws_iam_role_policy.gha_release
  to   = aws_iam_role_policy.gha_release[0]
}

# Builds publish only to the baseline-owned central ECR repositories. Isolated
# environments consume already-built digest references, so they must not have
# an ECR publishing policy (and therefore cannot render Resource = []).
resource "aws_iam_role_policy" "gha_release" {
  count = var.environment_name == "baseline" ? 1 : 0
  name  = "gha-release"
  role  = aws_iam_role.gha_release.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrAuth"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "ImmutableEcrRelease"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:CompleteLayerUpload",
          "ecr:GetDownloadUrlForLayer",
          "ecr:InitiateLayerUpload",
          "ecr:PutImage",
          "ecr:UploadLayerPart",
          "ecr:DescribeRepositories",
          "ecr:DescribeImages",
        ]
        Resource = [for repository in aws_ecr_repository.services : repository.arn]
      },
    ]
  })
}

# Read-only planning is deliberately separate from deployment. The only
# writes allowed are the S3 lockfile operations Terraform needs while reading
# remote state; this role cannot apply infrastructure changes.
resource "aws_iam_role" "gha_terraform_plan" {
  name = "${var.project_name}-gha-terraform-plan"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.github_oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:ref:refs/heads/main"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "gha_terraform_plan_readonly" {
  role       = aws_iam_role.gha_terraform_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "gha_terraform_plan_state_lock" {
  name = "terraform-state-read-and-lock"
  role = aws_iam_role.gha_terraform_plan.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:GetBucketVersioning"]
        Resource = "arn:aws:s3:::smartretailx-tfstate-322551984077"
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = [
          "arn:aws:s3:::smartretailx-tfstate-322551984077/smartretailx/terraform.tfstate",
          "arn:aws:s3:::smartretailx-tfstate-322551984077/smartretailx/terraform.tfstate.tflock",
          "arn:aws:s3:::smartretailx-tfstate-322551984077/smartretailx/*/terraform.tfstate",
          "arn:aws:s3:::smartretailx-tfstate-322551984077/smartretailx/*/terraform.tfstate.tflock",
        ]
      },
    ]
  })
}

# ─── Deploy permissions ───────────────────────────────────────
#
# Scoped to exactly what the pipeline in .github/workflows/deploy.yml
# needs and nothing more. Each Sid documents which pipeline step
# consumes it, so an audit can prove least privilege quickly.
resource "aws_iam_role_policy" "gha_deploy" {
  name = "gha-deploy"
  role = aws_iam_role.gha_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      var.environment_name == "baseline" ? [
        # ─── ECR push (buildx step) ──────────────────────────────
        # GetAuthorizationToken must be * per the ECR API contract;
        # repository actions remain scoped to the central repositories.
        {
          Sid      = "EcrAuth"
          Effect   = "Allow"
          Action   = ["ecr:GetAuthorizationToken"]
          Resource = "*"
        },
        {
          Sid    = "EcrPush"
          Effect = "Allow"
          Action = [
            "ecr:BatchCheckLayerAvailability",
            "ecr:BatchGetImage",
            "ecr:CompleteLayerUpload",
            "ecr:GetDownloadUrlForLayer",
            "ecr:InitiateLayerUpload",
            "ecr:PutImage",
            "ecr:UploadLayerPart",
            "ecr:DescribeRepositories",
            "ecr:DescribeImages",
          ]
          Resource = [for r in aws_ecr_repository.services : r.arn]
        },
      ] : [],
      [

        # ─── ECS update-service (deploy step) ────────────────────
        # UpdateService + DescribeServices only - no create / delete
        # (Terraform owns the topology; CI only rolls new task defs).
        {
          Sid    = "EcsDeploy"
          Effect = "Allow"
          Action = [
            "ecs:UpdateService",
            "ecs:DescribeServices",
            "ecs:DescribeTaskDefinition",
            "ecs:RegisterTaskDefinition",
            "ecs:RunTask",
            "ecs:ListTasks",
            "ecs:DescribeTasks",
          ]
          Resource = "*"
        },
        # PassRole is needed so RegisterTaskDefinition can attach the
        # execution + per-service task roles to the new revision.
        # Restricted to the exact roles those tasks run under - passing
        # any IAM role in the account would let a leaked pipeline token
        # escalate to admin.
        {
          Sid    = "EcsPassRoles"
          Effect = "Allow"
          Action = ["iam:PassRole"]
          Resource = [
            aws_iam_role.ecs_execution.arn,
            aws_iam_role.order_task.arn,
            aws_iam_role.inventory_task.arn,
            aws_iam_role.user_task.arn,
            aws_iam_role.product_task.arn,
          ]
          Condition = {
            StringEquals = {
              "iam:PassedToService" = "ecs-tasks.amazonaws.com"
            }
          }
        },

        # ─── S3 sync for the SPA bucket (frontend deploy) ───────
        # ListBucket at bucket level, object-level actions at /*.
        {
          Sid    = "SpaSync"
          Effect = "Allow"
          Action = [
            "s3:ListBucket",
            "s3:GetBucketLocation",
          ]
          Resource = [aws_s3_bucket.spa.arn]
        },
        {
          Sid    = "SpaObjects"
          Effect = "Allow"
          Action = [
            "s3:PutObject",
            "s3:GetObject",
            "s3:DeleteObject",
            "s3:PutObjectAcl",
          ]
          Resource = ["${aws_s3_bucket.spa.arn}/*"]
        },

        # ─── CloudFront invalidation (post-deploy) ──────────────
        # CreateInvalidation is the *only* action the pipeline runs;
        # scoped to the one distribution.
        {
          Sid      = "CloudFrontInvalidate"
          Effect   = "Allow"
          Action   = ["cloudfront:CreateInvalidation"]
          Resource = [aws_cloudfront_distribution.main.arn]
        },
        # Deployment verification checks whether the service alarm namespace is
        # currently in ALARM. DescribeAlarms requires wildcard resource scope.
        {
          Sid      = "CloudWatchDeploymentVerification"
          Effect   = "Allow"
          Action   = ["cloudwatch:DescribeAlarms"]
          Resource = "*"
        },
        {
          Sid    = "LambdaVersionPromotion"
          Effect = "Allow"
          Action = [
            "lambda:GetAlias",
            "lambda:CreateAlias",
            "lambda:UpdateAlias",
            "lambda:GetFunctionConfiguration",
            "lambda:UpdateFunctionCode",
            "lambda:PublishVersion",
          ]
          Resource = flatten([
            for function_name in local.gha_deploy_lambda_names : [
              "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${function_name}",
              "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${function_name}:*",
            ]
          ])
        },
      ],
    )
  })
}

output "github_oidc_role_arn" {
  description = "Role ARN for GitHub Actions to assume via OIDC (paste into workflow's role-to-assume)"
  value       = aws_iam_role.gha_deploy.arn
}

output "github_release_role_arn" {
  description = "Main-branch build-only role ARN for immutable ECR releases"
  value       = aws_iam_role.gha_release.arn
}

output "github_terraform_plan_role_arn" {
  description = "Main-branch read-only Terraform planning role ARN"
  value       = aws_iam_role.gha_terraform_plan.arn
}
