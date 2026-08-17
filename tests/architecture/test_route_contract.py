"""Architecture contract for the public SmartRetailX API prefix.

The edge, application clients and executable test tooling must agree on one
canonical prefix. Keeping this as a repository-level test catches route drift
before a CloudFront deployment turns it into a blanket 404.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _runtime_text_files() -> list[Path]:
    files = [
        ROOT / "infra" / "frontend.tf",
        ROOT / "infra" / "compute.tf",
        ROOT / "frontend" / "package.json",
        ROOT / "frontend" / ".env.example",
    ]
    files.extend((ROOT / "k6-tests").glob("*.js"))
    files.extend(path for path in (ROOT / "scripts").glob("*") if path.is_file())
    return files


class PublicRouteContractTests(unittest.TestCase):
    def test_cloudfront_exposes_only_v1_api_behavior(self) -> None:
        source = (ROOT / "infra" / "frontend.tf").read_text(encoding="utf-8")

        api_behaviors = re.findall(r'path_pattern\s*=\s*"([^\"]+)"', source)

        self.assertEqual(api_behaviors, ["/v1/*"])

    def test_runtime_callers_never_use_legacy_api_prefix(self) -> None:
        violations: list[str] = []

        for path in _runtime_text_files():
            source = path.read_text(encoding="utf-8")
            if "/api/v1" in source or "/api/*" in source:
                violations.append(str(path.relative_to(ROOT)))

        self.assertEqual(
            violations,
            [],
            "legacy /api routing remains in: " + ", ".join(violations),
        )

    def test_http_api_routes_are_versioned(self) -> None:
        source = (ROOT / "infra" / "compute.tf").read_text(encoding="utf-8")

        self.assertIn('"ANY /v1/${svc}"', source)
        self.assertIn('"ANY /v1/${svc}/{proxy+}"', source)
        self.assertNotIn('"ANY /api/', source)

    def test_cloudfront_does_not_remap_api_errors_to_spa_fallback(self) -> None:
        """A distribution-wide custom_error_response would silently rewrite
        FastAPI 403s (RBAC denials) into 200 /index.html responses and mask
        real authorization decisions.  SPA client-side routing must instead
        rely on a viewer-request CloudFront Function on the default (S3)
        behaviour so /v1/* API responses pass through verbatim."""
        source = (ROOT / "infra" / "frontend.tf").read_text(encoding="utf-8")
        self.assertNotIn("custom_error_response", source)
        self.assertIn("aws_cloudfront_function", source)
        self.assertIn("spa_router", source)
        # The function must attach ONLY to the default (S3) behaviour, never
        # to the /v1/* API behaviour.
        default_block_start = source.index("default_cache_behavior")
        v1_block_start = source.index('path_pattern           = "/v1/*"')
        default_block = source[default_block_start:v1_block_start]
        v1_block = source[v1_block_start:]
        self.assertIn("function_association", default_block)
        # Ensure the /v1/* block does not attach the router function.
        v1_block_end = v1_block.index("\n  }\n")
        self.assertNotIn("function_association", v1_block[:v1_block_end])


if __name__ == "__main__":
    unittest.main()
