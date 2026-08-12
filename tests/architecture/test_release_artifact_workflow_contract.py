"""Guard immutable-release artifact paths and ARM64 scan platform selection."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        workflow = yaml.safe_load(source)
    assert isinstance(workflow, dict)
    return workflow


def _release_steps() -> list[dict]:
    release = _workflow(WORKFLOWS / "release.yml")
    return release["jobs"]["package-portable-artifacts"]["steps"]


def _container_build_steps() -> list[dict]:
    workflow = _workflow(WORKFLOWS / "reusable-container-build.yml")
    return workflow["jobs"]["build"]["steps"]


def test_release_packager_places_spa_archive_where_the_packaging_step_reads_it() -> None:
    """A release must carry the SPA archive and its matching checksum into release/."""
    steps = _release_steps()
    spa_build = next(step["run"] for step in steps if step.get("name", "").startswith("Build immutable SPA"))
    lambda_package = next(
        step["run"]
        for step in steps
        if step.get("name", "").startswith("Package Lambda source artifacts")
    )

    assert "tar -C dist -czf smartretailx-spa.tgz ." in spa_build
    assert "sha256sum smartretailx-spa.tgz > smartretailx-spa.tgz.sha256" in spa_build
    assert "cp frontend/smartretailx-spa.tgz frontend/smartretailx-spa.tgz.sha256 release/" in lambda_package


def test_trivy_scans_the_arm64_image_variant_produced_by_the_release_build() -> None:
    """An ARM64-only immutable image must not be resolved as the runner's AMD64 variant."""
    trivy_steps = [
        step
        for step in _container_build_steps()
        if step.get("uses", "").startswith("aquasecurity/trivy-action@")
    ]

    assert len(trivy_steps) == 2
    for step in trivy_steps:
        assert step["env"] == {"TRIVY_PLATFORM": "linux/arm64"}
