#!/usr/bin/env bash
# Mint one short-lived Cognito access token for a single CI job role.
# The durable username/password remain GitHub Environment secrets; the
# token is masked and written only to the current job's GITHUB_ENV file
# under the environment variable name "<ROLE>_TOKEN".
#
# Usage: obtain-cognito-token.sh <ROLE>
#   ROLE is the uppercase role prefix (e.g. CUSTOMER, ADMIN, SMOKE).
#   The script reads <ROLE>_USERNAME and <ROLE>_PASSWORD from the
#   environment and writes <ROLE>_TOKEN back to GITHUB_ENV.
set -euo pipefail

role="${1:?ROLE argument is required (e.g. CUSTOMER, ADMIN)}"
role="${role^^}"

user_var="${role}_USERNAME"
pass_var="${role}_PASSWORD"
token_var="${role}_TOKEN"

: "${!user_var:?${user_var} must be supplied by the bound GitHub Environment}"
: "${!pass_var:?${pass_var} must be supplied by the bound GitHub Environment}"
: "${COGNITO_AUTHORITY:?COGNITO_AUTHORITY must be supplied by the bound GitHub Environment}"
: "${COGNITO_CLIENT_ID:?COGNITO_CLIENT_ID must be supplied by the bound GitHub Environment}"
: "${GITHUB_ENV:?GITHUB_ENV is required when minting a CI Cognito token}"

user_pool_id="${COGNITO_AUTHORITY%/}"
user_pool_id="${user_pool_id##*/}"
[[ "$user_pool_id" == *_* ]] || { echo "Invalid Cognito authority" >&2; exit 1; }

auth_parameters="$(jq -nc \
  --arg username "${!user_var}" \
  --arg password "${!pass_var}" \
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
  echo "Cognito did not return an access token for ${role}" >&2
  exit 1
}

echo "::add-mask::$access_token"
printf '%s=%s\n' "$token_var" "$access_token" >> "$GITHUB_ENV"
