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
# thumbprint_list is deliberately EMPTY. As of July 2023 AWS validates
# GitHub's OIDC token by trusting the certificate authority directly, so
# the once-mandatory thumbprint has become a no-op. Passing a stale one
# is worse than leaving it out - if GitHub rotates the cert (they did in
# 2023) a hard-coded thumbprint stops accepting tokens. Terraform still
# requires the argument, so we pass an empty list.
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = []

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
#   2. token.actions.githubusercontent.com:sub MUST match repo:<owner>/<repo>:*
#      - GitHub's `sub` claim is the ONLY reliable way to scope trust
#        to a specific repository. StringLike with `:*` matches every
#        branch / tag / environment in the repo but does NOT match a
#        fork or a differently named repo (`sub` is not user-controllable).
#      - The pattern is `repo:<owner>/<repo>:*` - a bare `<owner>/<repo>`
#        will not match because GitHub's `sub` always has a trailing
#        context (`:ref:refs/heads/main`, `:environment:prod`, etc).
#      - A tighter production pattern would pin `:ref:refs/heads/main`
#        so only default-branch pushes can deploy; kept as `:*` for
#        Week 5 to let PR builds validate the pipeline end-to-end.
#
# Common bug: using `StringEquals` for the sub condition. The literal
# `sub` value is never `repo:<owner>/<repo>:*` - the `:*` is a wildcard,
# so the condition operator MUST be StringLike.
resource "aws_iam_role" "gha_deploy" {
  name = "${var.project_name}-gha-deploy"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:*"
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
    Statement = [
      # ─── ECR push (buildx step) ──────────────────────────────
      # GetAuthorizationToken must be * per the ECR API contract;
      # everything else is scoped to the six service repositories.
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
    ]
  })
}

output "github_oidc_role_arn" {
  description = "Role ARN for GitHub Actions to assume via OIDC (paste into workflow's role-to-assume)"
  value       = aws_iam_role.gha_deploy.arn
}
