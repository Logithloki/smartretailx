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

variable "live" {
  description = "true = full billable stack; false = parked (~GBP 0). Gates NAT, ALB, and (later) ECS desired counts."
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

variable "image_tag" {
  description = "Container image tag the task definitions point at. ECR tags are IMMUTABLE, so bump this default in the SAME commit as the buildx push - never rely on passing -var at apply time."
  type        = string
  default     = "v0.2.0"
}

# Why the default matters more than it looks: `make park` runs
# `terraform apply -var="live=false"` with no image_tag, so the default wins and
# is written into a fresh task-definition revision. A stale default therefore
# silently rewrites the deployed tag on every park. That already happened once:
# v0.2.0 was applied, a park rewrote the task defs back to v0.1.0, and v0.1.0
# no longer exists in ECR - so the next unpark would have failed its image pull
# and tripped the deployment circuit breaker.

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
  description = "Tasks per service when live. Stays 0 until Week 2 pushes real images to ECR - a live service pointing at an absent image churns failed pulls and trips the deployment circuit breaker. Guide correction GC-2, see docs/guide-corrections.md."
  type        = number
  default     = 0
}
