#!/usr/bin/env bash
# Route matrix - proves API GW -> VPC Link -> internal ALB path routing for all
# four services, bare path and sub-path. Added after the CW-1 routing defect.
#
#   export SRX_TEST_PASSWORD='...'
#   ./scripts/route-matrix.sh
#
# Reading the results:
#   404  routing STILL BROKEN - request reached the ALB and hit its default
#        rule, meaning the path was not forwarded (the CW-1 defect).
#   503  routing WORKS - a listener rule matched, but the target group has no
#        healthy task yet. Correct before that service's image is deployed.
#   200/201  routing works and the service is live.
#   401  no/!invalid token (expected only in the auth section).
#   403  authenticated but wrong group - RBAC middleware working.
set -uo pipefail

API="$(terraform -chdir=infra output -raw api_endpoint)"
API="${API%/}" # $default stage invoke_url carries a trailing slash

TOKEN="${SRX_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
  : "${SRX_TEST_PASSWORD:?Set SRX_TEST_PASSWORD, or pre-set SRX_TOKEN}"
  TOKEN="$(./scripts/get-jwt.sh "${SRX_USER:-customer@example.com}")"
fi

code() { # method path -> status code
  curl -s -o /dev/null -w '%{http_code}' -X "$1" \
    -H "Authorization: Bearer $TOKEN" "${API}$2"
}

printf '%-8s %-34s %s\n' METHOD PATH STATUS
printf '%-8s %-34s %s\n' ------ ---- ------

for svc in orders inventory users products; do
  printf '%-8s %-34s %s\n' GET "/v1/${svc}"     "$(code GET "/v1/${svc}")"
  printf '%-8s %-34s %s\n' GET "/v1/${svc}/smoke-test-id" "$(code GET "/v1/${svc}/smoke-test-id")"
done

echo
echo "auth wall (no token / bad token):"
printf '%-8s %-34s %s\n' GET "/v1/products (none)" \
  "$(curl -s -o /dev/null -w '%{http_code}' "${API}/v1/products")"
printf '%-8s %-34s %s\n' GET "/v1/products (bad)" \
  "$(curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer not.a.jwt' "${API}/v1/products")"

echo
echo "unrouted path (should be 404 from the ALB default rule - proves the"
echo "default action still works and 404s above would be real faults):"
printf '%-8s %-34s %s\n' GET "/v1/nonexistent" "$(code GET "/v1/nonexistent")"
