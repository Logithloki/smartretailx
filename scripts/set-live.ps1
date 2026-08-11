param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("sandbox", "development", "test", "staging", "production")]
  [string]$Environment,
  [Parameter(Mandatory = $true)]
  [ValidateSet("park", "unpark")]
  [string]$Action
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$infra = Join-Path $root "infra"
$live = $Action -eq "unpark"
$confirmation = "$($Action.ToUpperInvariant())-$($Environment.ToUpperInvariant())"

Push-Location $infra
try {
  terraform init -reconfigure -backend-config="environments/$Environment/backend.hcl"
  terraform plan -var-file="environments/$Environment/terraform.tfvars.json" `
    -var="live=$($live.ToString().ToLowerInvariant())" -out="live-$Environment.tfplan"
  $entered = Read-Host "Review the plan above, then type $confirmation to apply it"
  if ($entered -cne $confirmation) { throw "Confirmation did not match; nothing was applied" }
  terraform apply "live-$Environment.tfplan"
}
finally {
  Pop-Location
}
