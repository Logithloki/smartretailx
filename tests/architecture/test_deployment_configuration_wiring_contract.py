"""Guard environment-scoped deployment configuration wiring."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
CALLERS = ("release.yml", "baseline-release.yml", "promote.yml", "production.yml")


def _workflow(name: str) -> dict:
    with (WORKFLOWS / name).open(encoding="utf-8") as source:
        workflow = yaml.safe_load(source)
    assert isinstance(workflow, dict)
    return workflow


def _workflow_inputs(name: str) -> dict:
    workflow = _workflow(name)
    trigger = workflow.get(True, workflow.get("on", {}))
    return trigger["workflow_call"]["inputs"]


def _workflow_secrets(name: str) -> dict:
    workflow = _workflow(name)
    trigger = workflow.get(True, workflow.get("on", {}))
    return trigger["workflow_call"].get("secrets", {})


def _deployment_jobs(callee: str) -> list[tuple[str, dict]]:
    return [
        (caller_name, job)
        for caller_name in CALLERS
        for job in _workflow(caller_name).get("jobs", {}).values()
        if isinstance(job, dict) and job.get("uses") == f"./.github/workflows/{callee}"
    ]


def test_reusable_deployments_resolve_environment_settings_inside_bound_jobs() -> None:
    """A caller cannot read an Environment before its reusable job attaches it."""
    expected = {
        "reusable-deploy-ecs.yml": {
            "inputs": {"service", "image_reference", "environment_name", "run_migration"},
            "variables": {
                "DEPLOY_ROLE_ARN": "${{ vars.SMARTRETAILX_DEPLOY_ROLE_ARN }}",
                "PROJECT_NAME": "${{ vars.SMARTRETAILX_PROJECT_NAME }}",
                "ECS_CLUSTER_NAME": "${{ vars.SMARTRETAILX_ECS_CLUSTER_NAME }}",
            },
        },
        "reusable-deploy-lambda.yml": {
            "inputs": {"component", "function_suffix", "release_run_id", "environment_name"},
            "variables": {
                "DEPLOY_ROLE_ARN": "${{ vars.SMARTRETAILX_DEPLOY_ROLE_ARN }}",
                "PROJECT_NAME": "${{ vars.SMARTRETAILX_PROJECT_NAME }}",
            },
        },
        "reusable-deploy-frontend.yml": {
            "inputs": {"release_run_id", "release_id", "environment_name"},
            "variables": {
                "DEPLOY_ROLE_ARN": "${{ vars.SMARTRETAILX_DEPLOY_ROLE_ARN }}",
                "SPA_BUCKET": "${{ vars.SMARTRETAILX_SPA_BUCKET }}",
                "DISTRIBUTION_ID": "${{ vars.SMARTRETAILX_DISTRIBUTION_ID }}",
                "PUBLIC_URL": "${{ vars.SMARTRETAILX_PUBLIC_URL }}",
                "WEBSOCKET_URL": "${{ vars.SMARTRETAILX_WEBSOCKET_URL }}",
                "COGNITO_AUTHORITY": "${{ vars.SMARTRETAILX_COGNITO_AUTHORITY }}",
                "COGNITO_DOMAIN": "${{ vars.SMARTRETAILX_COGNITO_DOMAIN }}",
                "COGNITO_CLIENT_ID": "${{ vars.SMARTRETAILX_COGNITO_CLIENT_ID }}",
            },
        },
    }

    for name, contract in expected.items():
        workflow = _workflow(name)
        assert set(_workflow_inputs(name)) == contract["inputs"]
        deploy_job = workflow["jobs"]["deploy"]
        assert deploy_job["environment"] == "${{ inputs.environment_name }}"
        for variable, expression in contract["variables"].items():
            assert deploy_job["env"][variable] == expression


def test_frontend_runtime_config_uses_jq_variables_and_rejects_missing_values() -> None:
    """Release runtime config must not silently become an all-null JSON object."""
    steps = _workflow("reusable-deploy-frontend.yml")["jobs"]["deploy"]["steps"]
    materialize = next(
        step["run"]
        for step in steps
        if step.get("name") == "Materialize validated runtime configuration beside immutable SPA"
    )

    assert (
        "'{apiBaseUrl:$apiBaseUrl,websocketUrl:$websocketUrl,"
        "cognitoAuthority:$cognitoAuthority,cognitoDomain:$cognitoDomain,"
        "cognitoClientId:$cognitoClientId,redirectUri:$redirectUri,"
        "logoutUri:$logoutUri,environment:$environment,releaseId:$releaseId}'"
        in materialize
    )
    assert "all(.[]; type == \"string\" and length > 0)" in materialize


def test_smoke_and_contract_jobs_read_selected_environment_variables_and_secrets() -> None:
    """Smoke, browser and API checks consume the Environment bound by their own jobs."""
    smoke = _workflow("reusable-smoke-tests.yml")
    assert set(_workflow_inputs("reusable-smoke-tests.yml")) == {"environment_name"}
    assert _workflow_secrets("reusable-smoke-tests.yml") == {}
    assert smoke["jobs"]["smoke"]["environment"] == "${{ inputs.environment_name }}"
    smoke_env = smoke["jobs"]["smoke"]["env"]
    assert smoke_env["SMOKE_USERNAME"] == "${{ secrets.SMOKE_USERNAME }}"
    assert smoke_env["SMOKE_PASSWORD"] == "${{ secrets.SMOKE_PASSWORD }}"
    assert smoke_env["COGNITO_AUTHORITY"] == "${{ vars.SMARTRETAILX_COGNITO_AUTHORITY }}"
    assert smoke_env["COGNITO_CLIENT_ID"] == "${{ vars.SMARTRETAILX_COGNITO_CLIENT_ID }}"
    assert "ACCESS_TOKEN" not in smoke_env
    assert smoke_env["FRONTEND_URL"] == "${{ vars.SMARTRETAILX_PUBLIC_URL }}"
    assert smoke_env["API_BASE_URL"] == "${{ vars.SMARTRETAILX_PUBLIC_URL }}"
    assert smoke_env["WEBSOCKET_URL"] == "${{ vars.SMARTRETAILX_WEBSOCKET_URL }}"

    assert smoke["permissions"] == {"id-token": "write", "contents": "read"}
    steps = smoke["jobs"]["smoke"]["steps"]
    configure = next(step for step in steps if "configure-aws-credentials" in step.get("uses", ""))
    assert configure["with"]["role-to-assume"] == "${{ vars.SMARTRETAILX_DEPLOY_ROLE_ARN }}"
    fresh_token = next(
        step["run"]
        for step in steps
        if step.get("name") == "Obtain fresh Cognito smoke access token"
    )
    assert "./scripts/obtain-smoke-access-token.sh" in fresh_token
    assert 'echo "ACCESS_TOKEN_PRESENT=true"' in fresh_token
    assert 'echo "$ACCESS_TOKEN"' not in fresh_token

    smoke_request = next(
        step["run"]
        for step in steps
        if step.get("name") == "Frontend, authenticated API, Saga and WebSocket smoke"
    )
    assert 'Authorization: Bearer $ACCESS_TOKEN' in smoke_request
    assert "SMOKE_ACCESS_TOKEN" not in (WORKFLOWS / "reusable-smoke-tests.yml").read_text(
        encoding="utf-8"
    )

    promote_smoke = _workflow("promote.yml")["jobs"]["smoke"]
    assert promote_smoke["with"]["environment_name"] == "${{ inputs.environment }}"
    # secrets: inherit is required so the environment-bound reusable job can
    # read SMOKE_USERNAME / SMOKE_PASSWORD from the GitHub Environment.
    # Environment vars propagate via the job's environment: binding, but
    # environment secrets do not reach reusable workflow jobs without
    # inheritance from the caller.
    assert promote_smoke.get("secrets") == "inherit"

    browser = _workflow("reusable-browser-e2e.yml")["jobs"]["e2e"]
    assert set(_workflow_inputs("reusable-browser-e2e.yml")) == {"environment_name"}
    assert browser["environment"] == "${{ inputs.environment_name }}"
    assert browser["env"]["E2E_BASE_URL"] == "${{ vars.SMARTRETAILX_PUBLIC_URL }}"
    assert browser["env"]["E2E_CUSTOMER_USERNAME"] == "${{ secrets.CUSTOMER_USERNAME }}"

    api_workflow = _workflow("reusable-api-tests.yml")
    api = api_workflow["jobs"]["newman"]
    assert set(_workflow_inputs("reusable-api-tests.yml")) == {"environment_name"}
    assert api["environment"] == "${{ inputs.environment_name }}"
    api_env = api["env"]
    assert api_env["API_BASE_URL"] == "${{ vars.SMARTRETAILX_PUBLIC_URL }}"
    # Persistent JWTs are banned; api-tests mints per-role tokens at runtime.
    assert "CUSTOMER_TOKEN" not in api_env
    assert "ADMIN_TOKEN" not in api_env
    assert api_env["CUSTOMER_USERNAME"] == "${{ secrets.CUSTOMER_USERNAME }}"
    assert api_env["CUSTOMER_PASSWORD"] == "${{ secrets.CUSTOMER_PASSWORD }}"
    assert api_env["ADMIN_USERNAME"] == "${{ secrets.ADMIN_USERNAME }}"
    assert api_env["ADMIN_PASSWORD"] == "${{ secrets.ADMIN_PASSWORD }}"
    assert api_env["COGNITO_AUTHORITY"] == "${{ vars.SMARTRETAILX_COGNITO_AUTHORITY }}"
    assert api_env["COGNITO_CLIENT_ID"] == "${{ vars.SMARTRETAILX_COGNITO_CLIENT_ID }}"
    assert api_workflow["permissions"] == {"id-token": "write", "contents": "read"}
    api_steps = api["steps"]
    configure = next(step for step in api_steps if "configure-aws-credentials" in step.get("uses", ""))
    assert configure["with"]["role-to-assume"] == "${{ vars.SMARTRETAILX_DEPLOY_ROLE_ARN }}"
    customer_mint = next(
        step for step in api_steps
        if step.get("name") == "Obtain fresh Cognito customer access token"
    )
    admin_mint = next(
        step for step in api_steps
        if step.get("name") == "Obtain fresh Cognito admin access token"
    )
    assert "./scripts/obtain-cognito-token.sh CUSTOMER" in customer_mint["run"]
    assert "./scripts/obtain-cognito-token.sh ADMIN" in admin_mint["run"]
    api_source = (WORKFLOWS / "reusable-api-tests.yml").read_text(encoding="utf-8")
    assert "secrets.CUSTOMER_TOKEN" not in api_source
    assert "secrets.ADMIN_TOKEN" not in api_source


def test_callers_pass_only_release_data_and_the_target_environment_to_reusable_jobs() -> None:
    """No caller evaluates Environment variables or secrets before a child job binds it."""
    allowed_inputs = {
        "reusable-deploy-ecs.yml": {"service", "image_reference", "environment_name", "run_migration"},
        "reusable-deploy-lambda.yml": {
            "component",
            "function_suffix",
            "release_run_id",
            "environment_name",
        },
        "reusable-deploy-frontend.yml": {"release_run_id", "release_id", "environment_name"},
        "reusable-smoke-tests.yml": {"environment_name"},
        "reusable-browser-e2e.yml": {"environment_name"},
        "reusable-api-tests.yml": {"environment_name"},
    }

    # Reusables that read environment SECRETS from their bound Environment
    # require secrets: inherit at the caller; environment vars do not.
    inheriting_reusables = {
        "reusable-smoke-tests.yml",
        "reusable-browser-e2e.yml",
        "reusable-api-tests.yml",
    }
    for reusable, expected_inputs in allowed_inputs.items():
        jobs = _deployment_jobs(reusable)
        assert jobs, f"{reusable} must have a release caller"
        for caller_name, job in jobs:
            supplied_inputs = set(job.get("with", {}))
            assert supplied_inputs <= expected_inputs, f"{caller_name}:{reusable}"
            assert {"environment_name"} <= supplied_inputs, f"{caller_name}:{reusable}"
            if reusable in inheriting_reusables:
                assert job.get("secrets") == "inherit", f"{caller_name}:{reusable}"
            else:
                assert job.get("secrets", {}) == {}, f"{caller_name}:{reusable}"
            assert "vars.SMARTRETAILX_" not in repr(job.get("with", {})), (
                f"{caller_name}:{reusable} evaluates an Environment variable too early"
            )


def test_environment_bound_reusables_support_every_promotion_target() -> None:
    """The same callable jobs bind their target dynamically, not to development."""
    promote = _workflow("promote.yml")
    environments = promote[True]["workflow_dispatch"]["inputs"]["environment"]["options"]
    assert environments == ["development", "test", "staging"]

    for reusable in (
        "reusable-deploy-ecs.yml",
        "reusable-deploy-lambda.yml",
        "reusable-deploy-frontend.yml",
        "reusable-smoke-tests.yml",
        "reusable-browser-e2e.yml",
        "reusable-api-tests.yml",
    ):
        workflow = _workflow(reusable)
        job = next(iter(workflow["jobs"].values()))
        assert job["environment"] == "${{ inputs.environment_name }}"

    production_call = _workflow("production.yml")["jobs"]["ecs"]
    assert production_call["with"]["environment_name"] == "production"


def test_smoke_uses_a_runtime_token_minted_by_the_environment_deploy_role() -> None:
    """An expired persisted JWT must not be able to break an authenticated promotion."""
    smoke_source = (WORKFLOWS / "reusable-smoke-tests.yml").read_text(encoding="utf-8")
    deploy_policy = (ROOT / "infra" / "oidc.tf").read_text(encoding="utf-8")

    assert "SMOKE_ACCESS_TOKEN" not in smoke_source
    assert "SMOKE_USERNAME" in smoke_source
    assert "SMOKE_PASSWORD" in smoke_source
    assert "admin-initiate-auth" in (ROOT / "scripts" / "obtain-smoke-access-token.sh").read_text(
        encoding="utf-8"
    )
    assert '"cognito-idp:AdminInitiateAuth"' in deploy_policy
    assert "Resource = [aws_cognito_user_pool.main.arn]" in deploy_policy
