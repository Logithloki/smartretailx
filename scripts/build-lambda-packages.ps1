# Build vendored Lambda source directories for the WebSocket authorizer
# (the only Lambda in the repo that needs C-extension dependencies -
# pyjwt[crypto] pulls cryptography, which has native code).
#
# The pip flags force pip to fetch Linux ARM64 wheels regardless of the
# host OS - so this works from Windows, macOS, or Linux. Cross-platform
# wheel install is a normal pip capability, but it will FAIL for any
# package that does not publish a manylinux2014_aarch64 wheel. All the
# packages we depend on do.
#
# Run this before `terraform apply` if requirements.txt or handler.py
# has changed. Terraform's `archive_file` uses `source_dir` to pick up
# whatever this script produces.

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$authSrc = Join-Path $repo 'services/ws-authorizer-lambda'
$buildDir = Join-Path $repo 'infra/build/ws-authorizer-src'

Write-Host "==> Rebuilding $buildDir"
if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }
New-Item -ItemType Directory -Path $buildDir | Out-Null

Write-Host "==> pip install (Linux ARM64 wheels)"
python -m pip install `
    -r (Join-Path $authSrc 'requirements.txt') `
    --platform manylinux2014_aarch64 `
    --target $buildDir `
    --python-version 3.12 `
    --implementation cp `
    --only-binary=:all: `
    --upgrade `
    --quiet

Write-Host "==> Copy handler.py"
Copy-Item -Path (Join-Path $authSrc 'handler.py') -Destination $buildDir

Write-Host "==> Build complete: $buildDir"
Get-ChildItem $buildDir | Select-Object Name, Length | Format-Table -AutoSize
