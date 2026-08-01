#!/usr/bin/env bash
# Print an access token for a seeded test user (checkpoint-window smoke tests).
#
#   export SRX_TEST_PASSWORD='...'
#   TOKEN=$(./scripts/get-jwt.sh customer@smartretailx.test)
#   curl -H "Authorization: Bearer $TOKEN" "$(terraform -chdir=infra output -raw api_endpoint)/v1/products"
#
# The token is short-lived (60 min) — never paste it into the repo, the report,
# or a screenshot. Redact the Authorization header in any captured evidence.
set -euo pipefail

: "${SRX_TEST_PASSWORD:?Set SRX_TEST_PASSWORD in your shell first}"

USERNAME="${1:?usage: get-jwt.sh <email> [id|access]}"
TOKEN_TYPE="${2:-access}"

REGION="${AWS_REGION:-eu-west-1}"
POOL_ID="$(terraform -chdir=infra output -raw cognito_user_pool_id)"
CLIENT_ID="$(terraform -chdir=infra output -raw cognito_app_client_id)"

case "$TOKEN_TYPE" in
  access) FIELD="AuthenticationResult.AccessToken" ;;
  id)     FIELD="AuthenticationResult.IdToken" ;;
  *)      echo "token type must be 'id' or 'access'" >&2; exit 1 ;;
esac

aws cognito-idp admin-initiate-auth \
  --user-pool-id "$POOL_ID" \
  --client-id "$CLIENT_ID" \
  --auth-flow ADMIN_USER_PASSWORD_AUTH \
  --auth-parameters "USERNAME=${USERNAME},PASSWORD=${SRX_TEST_PASSWORD}" \
  --region "$REGION" \
  --query "$FIELD" \
  --output text
