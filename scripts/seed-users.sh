#!/usr/bin/env bash
# Seed one customer + one admin test user into the Terraform-managed Cognito pool.
#
# The password is read from the environment and never stored in the repo:
#   export SRX_TEST_PASSWORD='<12+ chars, upper/lower/digit/symbol>'
#   ./scripts/seed-users.sh
#
# Safe to re-run: existing users are left alone, group membership re-applied.
set -euo pipefail

: "${SRX_TEST_PASSWORD:?Set SRX_TEST_PASSWORD in your shell first (never commit it)}"

REGION="${AWS_REGION:-eu-west-1}"
POOL_ID="$(terraform -chdir=infra output -raw cognito_user_pool_id)"

CUSTOMER_EMAIL="${SRX_CUSTOMER_EMAIL:-customer@smartretailx.test}"
ADMIN_EMAIL="${SRX_ADMIN_EMAIL:-admin@smartretailx.test}"

seed_user() {
  local email="$1" group="$2"

  if aws cognito-idp admin-get-user \
      --user-pool-id "$POOL_ID" --username "$email" --region "$REGION" >/dev/null 2>&1; then
    echo "user exists, skipping create: $email"
  else
    aws cognito-idp admin-create-user \
      --user-pool-id "$POOL_ID" \
      --username "$email" \
      --user-attributes Name=email,Value="$email" Name=email_verified,Value=true \
      --message-action SUPPRESS \
      --region "$REGION" >/dev/null
    echo "created: $email"
  fi

  # Permanent password so the user is CONFIRMED (no FORCE_CHANGE_PASSWORD prompt
  # mid-demo). Value comes from the environment, never from this file.
  aws cognito-idp admin-set-user-password \
    --user-pool-id "$POOL_ID" \
    --username "$email" \
    --password "$SRX_TEST_PASSWORD" \
    --permanent \
    --region "$REGION"

  aws cognito-idp admin-add-user-to-group \
    --user-pool-id "$POOL_ID" \
    --username "$email" \
    --group-name "$group" \
    --region "$REGION"
  echo "  -> group: $group"
}

seed_user "$CUSTOMER_EMAIL" customer
seed_user "$ADMIN_EMAIL"    admin

echo
echo "Seeded into pool $POOL_ID"
echo "Get a token with: ./scripts/get-jwt.sh $CUSTOMER_EMAIL"
