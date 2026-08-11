# SmartRetailX

Production-practice, demo-scale retail platform for COMP60010. The system uses a React SPA, Cognito Hosted UI authorization-code + PKCE, four FastAPI services on ARM64 ECS Fargate, DynamoDB/Aurora polyglot persistence, and a reliable event-driven order Saga.

Canonical public API: `/v1/*`. Infrastructure region: `eu-west-1`. Default infrastructure posture: `live=false` (parked; retained edge/storage resources still cost money).

## Local development

```powershell
docker compose up --build --wait
```

Compose starts LocalStack, PostgreSQL 16, a one-shot Alembic migration, and the four services. Never use local unsigned test JWT behavior as evidence of production Cognito validation.

Run service tests with `make test` on a Unix shell, or invoke each service's pytest suite from the repository virtual environment. Frontend checks:

```powershell
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

## Architecture and delivery

- [Architecture and pipeline](docs/architecture-and-pipeline.md)
- [Deployment and evidence handbook](docs/deployment-handbook.md)
- [Environment/state profiles](infra/environments/README.md)
- [Postman/Newman suite](postman/README.md)
- [Diagram reconciliation](docs/diagram-change-list.md)
- [Evidence index](docs/evidence-index.md)

The formal lifecycle builds one immutable release on protected `main`, then promotes the same digests/checksums through development, test, staging, a reviewed production Terraform plan, production approval, deployment, verification, and rollback if unhealthy. Sandbox is isolated and never promotes automatically.

## AWS safety

Do not run `terraform apply`, `terraform destroy`, or mutating AWS commands without reviewing the target and plan. Persistent-resource deletion in production is blocked by both resource protection and the production plan guard. Park non-production through `scripts/set-live.ps1`, which plans first and requires an exact typed confirmation.
