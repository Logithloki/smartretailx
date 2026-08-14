from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


class ImmutableReleaseContractTests(unittest.TestCase):
    def test_mandatory_workflows_do_not_soft_fail_or_force_old_task_definitions(self):
        text = "\n".join(path.read_text(encoding="utf-8") for path in WORKFLOWS.rglob("*.yml"))
        self.assertNotIn("continue-on-error", text)
        self.assertNotIn("--force-new-deployment", text)
        self.assertNotIn("@master", text)

    def test_build_repository_identity_matches_terraform(self):
        build = (WORKFLOWS / "reusable-container-build.yml").read_text(encoding="utf-8")
        terraform = (ROOT / "infra" / "compute.tf").read_text(encoding="utf-8")
        self.assertIn('${{ inputs.project_name }}/${{ inputs.service }}-service', build)
        self.assertIn('name                 = "${var.project_name}/${each.key}"', terraform)

    def test_deployment_registers_digest_task_revision_and_waits(self):
        deploy = (WORKFLOWS / "reusable-deploy-ecs.yml").read_text(encoding="utf-8")
        self.assertIn("@${{ inputs.image_digest }}", deploy)
        self.assertIn("register-task-definition", deploy)
        self.assertIn("ecs wait services-stable", deploy)
        self.assertIn("rolloutState", deploy)

    def test_terraform_accepts_only_sha256_release_digests(self):
        variables = (ROOT / "infra" / "variables.tf").read_text(encoding="utf-8")
        compute = (ROOT / "infra" / "compute.tf").read_text(encoding="utf-8")
        self.assertIn('variable "service_image_digests"', variables)
        self.assertIn('^sha256:[0-9a-f]{64}$', variables)
        self.assertIn("@${var.service_image_digests[each.key]}", compute)

    def test_release_manifest_records_all_four_service_digests(self):
        release = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
        for field in (
            "order_service_digest",
            "inventory_service_digest",
            "product_service_digest",
            "user_service_digest",
        ):
            self.assertIn(field, release)

    def test_reusable_deploy_ecs_uses_allowlist_rather_than_denylist(self):
        deploy = (WORKFLOWS / "reusable-deploy-ecs.yml").read_text(encoding="utf-8")
        self.assertNotIn("del(.taskDefinitionArn", deploy)
        self.assertIn("runtimePlatform", deploy)
        self.assertIn("containerDefinitions", deploy)
        self.assertIn("with_entries(select(.value != null))", deploy)

    def test_ecs_task_definition_allowlist_sanitization(self):
        allowlist = {
            "family",
            "taskRoleArn",
            "executionRoleArn",
            "networkMode",
            "containerDefinitions",
            "volumes",
            "placementConstraints",
            "requiresCompatibilities",
            "cpu",
            "memory",
            "tags",
            "pidMode",
            "ipcMode",
            "proxyConfiguration",
            "inferenceAccelerators",
            "ephemeralStorage",
            "runtimePlatform",
            "enableFaultInjection",
        }

        response_only_fields = [
            "taskDefinitionArn",
            "revision",
            "status",
            "requiresAttributes",
            "compatibilities",
            "registeredAt",
            "registeredBy",
            "deregisteredAt",
            "deleteRequestedAt",
        ]

        digest_hash = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
        account_id = "123456789012"
        project_name = "smartretailx"

        for service in ["order", "inventory", "product", "user"]:
            container_name = f"{service}-service"
            mock_describe_response = {
                "taskDefinitionArn": f"arn:aws:ecs:eu-west-1:{account_id}:task-definition/{project_name}-{service}:5",
                "family": f"{project_name}-{service}",
                "taskRoleArn": f"arn:aws:iam::{account_id}:role/{project_name}-{service}-task-role",
                "executionRoleArn": f"arn:aws:iam::{account_id}:role/{project_name}-ecs-execution-role",
                "networkMode": "awsvpc",
                "revision": 5,
                "status": "ACTIVE",
                "containerDefinitions": [
                    {
                        "name": container_name,
                        "image": f"{account_id}.dkr.ecr.eu-west-1.amazonaws.com/{project_name}/{container_name}:old-tag",
                        "essential": True,
                        "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
                        "environment": [{"name": "ENV", "value": "production"}],
                        "secrets": [],
                        "logConfiguration": {"logDriver": "awslogs"},
                    },
                    {
                        "name": "adot-collector",
                        "image": "public.ecr.aws/aws-observability/aws-otel-collector:v0.42.0",
                        "essential": False,
                        "logConfiguration": {"logDriver": "awslogs"},
                    },
                ],
                "cpu": "512",
                "memory": "1024",
                "runtimePlatform": {
                    "operatingSystemFamily": "LINUX",
                    "cpuArchitecture": "ARM64",
                },
                "volumes": [],
                "requiresAttributes": [{"name": "com.amazonaws.ecs.capability.logging-driver.awslogs"}],
                "compatibilities": ["EC2", "FARGATE"],
                "registeredAt": "2026-08-14T09:00:00.000Z",
                "registeredBy": f"arn:aws:iam::{account_id}:user/deployer",
                "deregisteredAt": "2026-08-14T10:00:00.000Z",
                "deleteRequestedAt": "2026-08-14T10:05:00.000Z",
            }

            # Apply allowlist filtering (mirroring jq logic)
            rendered = {
                k: v
                for k, v in mock_describe_response.items()
                if k in allowlist and v is not None
            }

            # Update targeted application image digest
            target_image = f"{account_id}.dkr.ecr.eu-west-1.amazonaws.com/{project_name}/{container_name}@{digest_hash}"
            for c in rendered["containerDefinitions"]:
                if c["name"] == container_name:
                    c["image"] = target_image

            # 1 & 2: Ensure response-only fields are stripped
            for field in response_only_fields:
                self.assertNotIn(field, rendered, f"Field '{field}' should be stripped for service '{service}'")

            # 3: Ensure legitimate fields are retained
            self.assertEqual(rendered["family"], f"{project_name}-{service}")
            self.assertEqual(rendered["networkMode"], "awsvpc")
            self.assertEqual(rendered["cpu"], "512")
            self.assertEqual(rendered["memory"], "1024")

            # 4: Ensure application image is pinned to exact sha256 digest
            app_container = next(c for c in rendered["containerDefinitions"] if c["name"] == container_name)
            self.assertEqual(app_container["image"], target_image)

            # 5: Ensure sidecar is unchanged
            sidecar = next(c for c in rendered["containerDefinitions"] if c["name"] == "adot-collector")
            self.assertEqual(sidecar["image"], "public.ecr.aws/aws-observability/aws-otel-collector:v0.42.0")

            # 6: Ensure ARM64 runtimePlatform is preserved
            self.assertEqual(rendered["runtimePlatform"], {"operatingSystemFamily": "LINUX", "cpuArchitecture": "ARM64"})


if __name__ == "__main__":
    unittest.main()

