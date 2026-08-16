variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Project name used as prefix for all resources"
  type        = string
  default     = "smartretailx"
}

variable "environment_name" {
  description = "Logical environment. The existing shared stack remains baseline; new isolated roots use sandbox/development/test/staging/production."
  type        = string
  default     = "baseline"

  validation {
    condition = contains(
      ["baseline", "sandbox", "development", "test", "staging", "production"],
      var.environment_name,
    )
    error_message = "environment_name must be baseline, sandbox, development, test, staging, or production."
  }
}

variable "enable_cognito_auto_confirm" {
  description = "Attach the pre-sign-up auto-confirm hook. Never permitted in staging or production."
  type        = bool
  default     = false

  validation {
    condition = !var.enable_cognito_auto_confirm || contains(
      ["sandbox", "development", "test"],
      var.environment_name,
    )
    error_message = "Cognito auto-confirm may be enabled only in sandbox, development, or test."
  }
}

variable "live" {
  description = "true = full billable stack; false = parked (~GBP 0). Gates NAT, ALB, and (later) ECS desired counts."
  type        = bool
  default     = false
}

variable "enable_grafana" {
  description = "Run the optional Grafana ECS service and ALB attachments when the stack is live."
  type        = bool
  default     = false
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Two availability zones for multi-AZ deployment"
  type        = list(string)
  default     = ["eu-west-1a", "eu-west-1b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private microservices subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "data_subnet_cidrs" {
  description = "CIDR blocks for data tier subnets"
  type        = list(string)
  default     = ["10.0.20.0/24", "10.0.21.0/24"]
}

# Week 5 D4 appends the CloudFront distribution URL to all three of these
# once the SPA is deployed. Vite's dev server is the local default.
variable "frontend_callback_urls" {
  description = "Cognito hosted-UI callback URLs (authorization-code + PKCE)"
  type        = list(string)
  default     = ["http://localhost:5173", "http://localhost:5173/callback"]
}

variable "frontend_logout_urls" {
  description = "Cognito hosted-UI post-logout redirect URLs"
  type        = list(string)
  default     = ["http://localhost:5173"]
}

variable "cors_allow_origins" {
  description = "Origins allowed to call the HTTP API from a browser"
  type        = list(string)
  default     = ["http://localhost:5173"]
}

variable "service_image_references" {
  description = "Complete central ECR repository@sha256 references keyed by order, inventory, product, and user. A live stack requires all four."
  type        = map(string)
  default     = {}

  validation {
    condition = alltrue([
      for reference in values(var.service_image_references) : can(regex("^[0-9]+\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/smartretailx/(order|inventory|product|user)-service@sha256:[0-9a-f]{64}$", reference))
    ])
    error_message = "Every service image reference must be a central smartretailx repository@sha256:<64 lowercase hex> value."
  }
}

variable "ses_sender_email" {
  description = "From address for order notifications. Empty disables the SES identity. Set it, apply, then click the verification link AWS emails to that address - SES will not send until you do."
  type        = string
  default     = ""
}

variable "notification_fallback_email" {
  description = "Recipient used when an order event carries no userEmail. Must also be SES-verified while the account is in the sandbox."
  type        = string
  default     = ""
}

# The GitHub repository whose workflows can assume the deploy role via
# OIDC. Format is "owner/repo". Kept as a variable (rather than baked in)
# so a fork or an owner rename does not require editing infra code; also
# so a future markbook contributor can point their fork at their own
# short-lived deploy role without touching this file.
variable "github_repo" {
  description = "GitHub repo (owner/name) allowed to assume the OIDC deploy role"
  type        = string
  default     = "Logithloki/smartretailx"
}

variable "service_desired_count" {
  description = "Baseline tasks per application service when live. The live gate and autoscaling floor still force 0 while parked; environment profiles may override this value."
  type        = number
  default     = 1
}
