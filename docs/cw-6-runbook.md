# CW-6 Runbook: Observability, Auth & UI
**Budget:** ~2 hours, ≈ £0.50.
**Screenshots:** `60-…` series in `assignment-screenshots/`.

This runbook covers the final application features, UI enhancements, and observability requirements (Grafana/X-Ray/Global Tables) built in Week 6.

## 1. Auth & UI Evidence (60–62)

- [ ] **Screenshot `60-cognito-email.png`**:
  Open your email inbox (e.g., Gmail) and take a screenshot of the **Native Cognito 6-Digit Verification Code** email. Ensure the custom subject line ("Welcome to SmartRetailX - Your Verification Code") and the HTML styling are visible.

- [ ] **Screenshot `61-admin-users.png`**:
  Log into the SmartRetailX web app as an **Admin** user (using the Quick Demo Admin login or an account added to the `admin` Cognito group). Navigate to the **Admin: Users** tab (`/admin/users`). Take a screenshot showing the list of registered users pulled from Cognito.

- [ ] **Screenshot `62-delete-account.png`**:
  While logged into the web app (as either a customer or admin), click the **Delete Account** button in the top right. Take a screenshot of the confirmation dialog or the immediate aftermath to prove GDPR self-service compliance.

## 2. Observability & Global Table (63–65)

- [ ] **Screenshot `63-grafana.png`**:
  Access Grafana via the CloudFront URL. Show the provisioned dashboard displaying ECS CPU/Memory, API Gateway 5xx errors, or SQS queue depth.

- [ ] **Screenshot `64-xray-map.png`**:
  Open the AWS Console → CloudWatch → X-Ray Traces → Service Map. Ensure the map shows the full flow from API Gateway → Order Service → DynamoDB → SQS. Take a screenshot of this graph; it is a critical piece of evidence for Task 7.

- [ ] **Screenshot `65-global-table.png`**:
  Open the AWS Console → DynamoDB → Tables → `smartretailx-products`. Go to the **Global Tables** tab. Take a screenshot showing both the `eu-west-1` and `ap-south-1` regions listed as Active replicas.

## 3. Park the Stack
- [ ] Run `terraform apply -var="live=false"` to park the stack.
- [ ] Verify NAT Gateway and ALB are destroyed in the AWS Console.
- [ ] Update `docs/cost-ledger.md` with today's session duration and cost.
- [ ] Commit and push to GitHub.
