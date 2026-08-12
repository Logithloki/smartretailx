# Architecture diagram reconciliation

The draw.io request-lifecycle labels were corrected to `/v1/*`, Hosted UI PKCE, runtime config, transactional outboxes, user-scoped WebSocket delivery, and OTel/CloudWatch. Before final report export, visually verify these remaining edits:

1. Show five isolated state profiles; keep sandbox outside the DEV → TEST → STAGING → PROD lane.
2. Show build once: four ARM64 digests, versioned Lambda ZIP/aliases, immutable SPA/runtime config, manifest/SBOM.
3. Put production Terraform plan before the manual approval, then exact-plan apply.
4. Label `pybreaker/tenacity` as application breaker and ECS rollback/alarms as deployment breaker.
5. Show order DynamoDB transaction/outbox stream publisher and inventory Aurora inbox/outbox transaction.
6. Label WebSocket lookup `userId-index`; do not show broadcast fan-out.
7. Make CloudWatch the primary dashboard. Mark Grafana optional/prototype.
8. Mark eu-central-1 DR **DESIGNED / NOT DEPLOYED**; keep Mumbai products-only Global Table as APAC expansion, not DR.
9. Show production 2× tasks/service and Aurora writer+reader; lower environments demo-sized/parkable.
10. Do not add Route 53: no custom domain exists.
