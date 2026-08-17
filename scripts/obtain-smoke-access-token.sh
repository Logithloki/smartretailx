#!/usr/bin/env bash
# Mint one short-lived Cognito access token for a single CI smoke job.
# The durable username/password remain GitHub Environment secrets; the token
# is masked and written only to the current job's GITHUB_ENV file.
set -euo pipefail

: "${SMOKE_USERNAME:?SMOKE_USERNAME must be supplied by the bound GitHub Environment}"
: "${SMOKE_PASSWORD:?SMOKE_PASSWORD must be supplied by the bound GitHub Environment}"
: "${COGNITO_AUTHORITY:?COGNITO_AUTHORITY must be supplied by the bound GitHub Environment}"
: "${COGNITO_CLIENT_ID:?COGNITO_CLIENT_ID must be supplied by the bound GitHub Environment}"
: "${GITHUB_ENV:?GITHUB_ENV is required when minting a CI smoke token}"

user_pool_id="${COGNITO_AUTHORITY%/}"
user_pool_id="${user_pool_id##*/}"
[[ "$user_pool_id" == *_* ]] || { echo "Invalid Cognito authority" >&2; exit 1; }

auth_parameters="$(jq -nc \
  --arg username "$SMOKE_USERNAME" \
  --arg password "$SMOKE_PASSWORD" \
  '{USERNAME:$username,PASSWORD:$password}')"
access_token="$(aws cognito-idp admin-initiate-auth \
  --user-pool-id "$user_pool_id" \
  --client-id "$COGNITO_CLIENT_ID" \
  --auth-flow ADMIN_USER_PASSWORD_AUTH \
  --auth-parameters "$auth_parameters" \
  --region "${AWS_REGION:-eu-west-1}" \
  --query 'AuthenticationResult.AccessToken' \
  --output text \
  --no-cli-pager)"

[[ -n "$access_token" && "$access_token" != "None" ]] || {
  echo "Cognito did not return an access token" >&2
  exit 1
}

echo "::add-mask::$access_token"
printf 'ACCESS_TOKEN=%s\n' "$access_token" >> "$GITHUB_ENV"
