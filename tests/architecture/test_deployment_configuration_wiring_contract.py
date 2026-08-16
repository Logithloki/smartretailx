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
            "inputs": {"service", "image_digest", "environment_name", "run_migration"},
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
    assert _workflow_secrets("reusable-smoke-tests.yml") == {
        "SMOKE_ACCESS_TOKEN": {"required": True}
    }
    assert smoke["jobs"]["smoke"]["environment"] == "${{ inputs.environment_name }}"
    smoke_env = smoke["jobs"]["smoke"]["env"]
    assert smoke_env["ACCESS_TOKEN"] == "${{ secrets.SMOKE_ACCESS_TOKEN }}"
    assert smoke_env["FRONTEND_URL"] == "${{ vars.SMARTRETAILX_PUBLIC_URL }}"
    assert smoke_env["API_BASE_URL"] == "${{ vars.SMARTRETAILX_PUBLIC_URL }}"
    assert smoke_env["WEBSOCKET_URL"] == "${{ vars.SMARTRETAILX_WEBSOCKET_URL }}"
    validate = smoke["jobs"]["smoke"]["steps"][0]["run"]
    assert 'echo "ACCESS_TOKEN_PRESENT=true"' in validate
    assert 'echo "ACCESS_TOKEN_PRESENT=false"' in validate
    assert 'echo "$ACCESS_TOKEN"' not in validate

    smoke_request = smoke["jobs"]["smoke"]["steps"][1]["run"]
    assert 'ACCESS_TOKEN="${ACCESS_TOKEN#Bearer }"' in smoke_request
    assert 'Authorization: Bearer $ACCESS_TOKEN' in smoke_request

    promote_smoke = _workflow("promote.yml")["jobs"]["smoke"]
    assert promote_smoke["with"]["environment_name"] == "${{ inputs.environment }}"
    assert promote_smoke["secrets"] == {
        "SMOKE_ACCESS_TOKEN": "${{ secrets.SMOKE_ACCESS_TOKEN }}"
    }

    browser = _workflow("reusable-browser-e2e.yml")["jobs"]["e2e"]
    assert set(_workflow_inputs("reusable-browser-e2e.yml")) == {"environment_name"}
    assert browser["environment"] == "${{ inputs.environment_name }}"
    assert browser["env"]["E2E_BASE_URL"] == "${{ vars.SMARTRETAILX_PUBLIC_URL }}"
    assert browser["env"]["E2E_CUSTOMER_USERNAME"] == "${{ secrets.CUSTOMER_USERNAME }}"

    api = _workflow("reusable-api-tests.yml")["jobs"]["newman"]
    assert set(_workflow_inputs("reusable-api-tests.yml")) == {"environment_name"}
    assert api["environment"] == "${{ inputs.environment_name }}"
    api_env = api["env"]
    assert api_env["API_BASE_URL"] == "${{ vars.SMARTRETAILX_PUBLIC_URL }}"
    assert api_env["CUSTOMER_TOKEN"] == "${{ secrets.CUSTOMER_TOKEN }}"
    assert api_env["ADMIN_TOKEN"] == "${{ secrets.ADMIN_TOKEN }}"


def test_callers_pass_only_release_data_and_the_target_environment_to_reusable_jobs() -> None:
    """No caller evaluates Environment variables or secrets before a child job binds it."""
    allowed_inputs = {
        "reusable-deploy-ecs.yml": {"service", "image_digest", "environment_name", "run_migration"},
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

    for reusable, expected_inputs in allowed_inputs.items():
        jobs = _deployment_jobs(reusable)
        assert jobs, f"{reusable} must have a release caller"
        for caller_name, job in jobs:
            supplied_inputs = set(job.get("with", {}))
            assert supplied_inputs <= expected_inputs, f"{caller_name}:{reusable}"
            assert {"environment_name"} <= supplied_inputs, f"{caller_name}:{reusable}"
            expected_secrets = (
                {"SMOKE_ACCESS_TOKEN": "${{ secrets.SMOKE_ACCESS_TOKEN }}"}
                if (caller_name, reusable) == ("promote.yml", "reusable-smoke-tests.yml")
                else {}
            )
            assert job.get("secrets", {}) == expected_secrets, f"{caller_name}:{reusable}"
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
