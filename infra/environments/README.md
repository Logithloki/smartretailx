# Environment profiles and isolated state

The existing shared stack remains the `baseline` environment at the original
`smartretailx/terraform.tfstate` key. These profiles create new namespaces and
state keys without renaming or moving baseline resources.

The existing stack must be released through `.github/workflows/baseline-release.yml`,
which uses the root backend and validates baseline sentinel addresses before it
can plan. The isolated `.github/workflows/production.yml` path and
`smartretailx/production/terraform.tfstate` are future-stack design only; they
must never be used to update the existing baseline. No state copy, migration or
import connects these lineages.

Run plans from `infra/`:

```bash
terraform init -reconfigure -backend-config=environments/development/backend.hcl
terraform plan -var-file=environments/development/terraform.tfvars.json
```

Never reuse a backend key between profiles. All non-production profiles default
to `live=false`; unpark only for a bounded validation window and park afterward.
Module extraction is deliberately a later state-migration change: it requires
`moved` blocks and a reviewed zero-replacement plan against the baseline state.
