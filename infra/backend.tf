# ─── REMOTE STATE (Week 1 Day 1 — laptop-loss insurance) ─────
#
# Enable AFTER creating the bucket (one-time bootstrap, run manually):
#
#   aws s3api create-bucket --bucket smartretailx-tfstate-322551984077 \
#     --region eu-west-1 --create-bucket-configuration LocationConstraint=eu-west-1
#   aws s3api put-bucket-versioning --bucket smartretailx-tfstate-322551984077 \
#     --versioning-configuration Status=Enabled
#   aws s3api put-public-access-block --bucket smartretailx-tfstate-322551984077 \
#     --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
#
# Then uncomment the block below and run:  terraform init -migrate-state
#
# terraform {
#   backend "s3" {
#     bucket       = "smartretailx-tfstate-322551984077"
#     key          = "smartretailx/terraform.tfstate"
#     region       = "eu-west-1"
#     use_lockfile = true
#   }
# }
