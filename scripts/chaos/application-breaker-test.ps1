$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$python = Join-Path $root ".venv\Scripts\python.exe"
& $python -m pytest -q `
  (Join-Path $root "services\inventory-service\tests\test_resilience.py") `
  --basetemp (Join-Path $root ".pytest-tmp\breaker") -p no:cacheprovider
exit $LASTEXITCODE
