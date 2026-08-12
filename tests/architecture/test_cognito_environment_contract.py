"""Static safety contract for environment-specific Cognito behavior."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CognitoEnvironmentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.variables = (ROOT / "infra" / "variables.tf").read_text(encoding="utf-8")
        cls.security = (ROOT / "infra" / "security.tf").read_text(encoding="utf-8")

    def test_environment_and_auto_confirm_are_explicit_inputs(self) -> None:
        self.assertIn('variable "environment_name"', self.variables)
        self.assertIn('variable "enable_cognito_auto_confirm"', self.variables)
        self.assertIn("default     = false", self.variables)

    def test_staging_and_production_filter_localhost_callbacks(self) -> None:
        self.assertIn("cognito_frontend_callback_urls", self.security)
        self.assertIn('["staging", "production"]', self.security)
        self.assertIn('!startswith(url, "http://localhost")', self.security)
        self.assertIn("local.cognito_frontend_callback_urls", self.security)

    def test_auto_confirm_hook_is_gated_by_environment(self) -> None:
        self.assertIn('dynamic "lambda_config"', self.security)
        self.assertIn("var.enable_cognito_auto_confirm", self.security)
        self.assertIn('["sandbox", "development", "test"]', self.variables)


if __name__ == "__main__":
    unittest.main()
