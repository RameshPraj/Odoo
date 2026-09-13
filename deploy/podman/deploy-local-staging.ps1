# Deploy a tested GHCR image to the dedicated local Podman staging instance.
# Used only by the trusted, self-hosted `odoo-staging` Actions runner.

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^ghcr\.io/.+:[0-9a-f]{40}$')]
    [string]$Image
)

$ErrorActionPreference = 'Stop'
$podman = Join-Path $env:LOCALAPPDATA 'Programs\Podman\podman.exe'
$stagingName = 'odoo-staging'
$healthUrl = 'http://127.0.0.1:18069/web/health?db=odoo_staging'

if (-not (Test-Path -LiteralPath $podman)) {
    throw "Podman CLI was not found at $podman"
}

& "$PSScriptRoot\start-local-staging.ps1"
& $podman pull $Image
if ($LASTEXITCODE -ne 0) {
    throw "Unable to pull the immutable staging image $Image"
}

$previousImage = & $podman inspect $stagingName --format '{{.Config.Image}}'
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($previousImage)) {
    throw "The existing $stagingName container could not be inspected. Refusing deployment."
}

function Start-StagingContainer([string]$ContainerImage) {
    & $podman run --detach --name $stagingName --network odoo-staging-net `
        --publish 127.0.0.1:18069:8069 `
        --label app=odoo --label environment=staging `
        --restart unless-stopped --security-opt no-new-privileges --cap-drop all `
        --secret odoo-staging-config,target=/etc/odoo/odoo.conf,uid=10001,gid=10001,mode=0440 `
        --volume odoo-staging-filestore:/var/lib/odoo:U $ContainerImage
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to start $stagingName with $ContainerImage"
    }
}

function Test-StagingHealth {
    foreach ($attempt in 1..30) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                return $true
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

& $podman stop $stagingName
& $podman rm $stagingName
try {
    Start-StagingContainer $Image
    if (-not (Test-StagingHealth)) {
        throw "The new staging image did not become healthy."
    }
    Write-Host "Staging deployment succeeded: $Image"
} catch {
    $deploymentError = $_
    Write-Warning "Staging deployment failed; restoring $previousImage."
    & $podman rm --force $stagingName 2>$null
    Start-StagingContainer $previousImage
    if (-not (Test-StagingHealth)) {
        throw "Staging rollback also failed after: $deploymentError"
    }
    throw $deploymentError
}
