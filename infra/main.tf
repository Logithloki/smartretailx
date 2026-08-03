terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
  required_version = ">= 1.5.0"
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project = var.project_name
    }
  }
}

# CloudFront + WAFv2 for CloudFront must be managed in us-east-1 (it is a
# global service whose configuration lives in Northern Virginia, regardless
# of where the origins are). The rest of the stack stays in eu-west-1.
# Any resource that needs the us-east-1 endpoint sets `provider = aws.us_east_1`.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project = var.project_name
    }
  }
}

# Used to make the Cognito hosted-UI domain prefix globally unique.
data "aws_caller_identity" "current" {}
