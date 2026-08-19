#!/usr/bin/env bash
# Bash equivalent of scripts/build-lambda-packages.ps1 for Linux CI runners.
#
# The ws-authorizer Lambda ships PyJWT[crypto], which depends on the
# `cryptography` wheel with native C code. terraform's `data.archive_file`
# reads infra/build/ws-authorizer-src/ during plan and apply, so that
# directory must exist and contain the handler + Linux ARM64 wheels
# BEFORE any `terraform plan` runs.
#
# This script is the CI equivalent of the local PowerShell one. Idempotent
# (nukes and rebuilds the target directory).

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
auth_src="$repo_root/services/ws-authorizer-lambda"
build_dir="$repo_root/infra/build/ws-authorizer-src"

echo "==> Rebuilding $build_dir"
rm -rf "$build_dir"
mkdir -p "$build_dir"

echo "==> pip install (Linux ARM64 wheels)"
python -m pip install \
    -r "$auth_src/requirements.txt" \
    --platform manylinux2014_aarch64 \
    --target "$build_dir" \
    --python-version 3.12 \
    --implementation cp \
    --only-binary=:all: \
    --upgrade \
    --quiet

echo "==> Copy handler.py"
cp "$auth_src/handler.py" "$build_dir/"

echo "==> Build complete: $build_dir"
ls -la "$build_dir" | head
