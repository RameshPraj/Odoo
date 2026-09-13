# Starts the rootless Podman WSL machine used exclusively for local staging.
# Scheduled by the "Odoo Staging - Start Podman" Windows Task Scheduler task.
# Container restart policies then restore odoo-staging-db and odoo-staging.

$ErrorActionPreference = 'Stop'
$podman = Join-Path $env:LOCALAPPDATA 'Programs\Podman\podman.exe'

if (-not (Test-Path -LiteralPath $podman)) {
    throw "Podman CLI was not found at $podman"
}

$machineStatus = & $podman machine list --format '{{.Name}} {{.Running}}'
if ($machineStatus -match '^odoo-staging\*?\s+true$') {
    exit 0
}

& $podman machine start odoo-staging
if ($LASTEXITCODE -ne 0) {
    throw "Unable to start the odoo-staging Podman machine (exit code $LASTEXITCODE)."
}
