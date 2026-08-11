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
        build = (WORKFLOWS / "reusable" / "container-build.yml").read_text(encoding="utf-8")
        terraform = (ROOT / "infra" / "compute.tf").read_text(encoding="utf-8")
        self.assertIn('${{ inputs.project_name }}/${{ inputs.service }}-service', build)
        self.assertIn('name                 = "${var.project_name}/${each.key}"', terraform)

    def test_deployment_registers_digest_task_revision_and_waits(self):
        deploy = (WORKFLOWS / "reusable" / "deploy-ecs.yml").read_text(encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
