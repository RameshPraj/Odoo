# Start the local Odoo 19 server (PowerShell).
#
#   .\run-odoo.ps1                     # start the server
#   .\run-odoo.ps1 -Install account    # install/reinstall a module, then exit
#   .\run-odoo.ps1 -Update account     # upgrade a module after editing it, then exit
#   .\run-odoo.ps1 -Shell              # interactive Python shell with `env` bound
#   .\run-odoo.ps1 -Dev                # start with auto-reload + no asset cache
#
param(
    [string] $Install,
    [string] $Update,
    [switch] $Shell,
    [switch] $Dev
)

$ErrorActionPreference = "Stop"
$root   = $PSScriptRoot
$python = Join-Path $root "venv\Scripts\python.exe"
$conf   = Join-Path $root "odoo.conf"

if (-not (Test-Path $python)) { throw "venv not found at $python -- run: py -3.12 -m venv venv" }
if (-not (Test-Path $conf))   { throw "$conf not found -- copy odoo.conf.example and edit it for this host" }

# Refuse to start on a stale addons_path or data_dir.
#
# Odoo treats neither as fatal: a missing addons_path entry is logged as
# "no such directory ... skipped" and the server starts with those modules simply
# absent, while a stale data_dir surfaces only later as a FileNotFoundError per
# attachment. Both failures look like a healthy server. Moving the project
# directory without updating odoo.conf has already caused exactly this.
function Get-ConfValue([string] $key) {
    # Last occurrence wins, matching Odoo's own parsing. Values run to
    # end-of-line and may contain spaces, so they are never quoted.
    $line = Select-String -Path $conf -Pattern "^\s*$key\s*=\s*(.+?)\s*$" |
            Select-Object -Last 1
    if ($line) { return $line.Matches[0].Groups[1].Value }
    return $null
}

$badPaths = @()
$addonsPath = Get-ConfValue "addons_path"
if ($addonsPath) {
    # Comma-separated; entries may contain spaces, so split only on commas.
    foreach ($entry in $addonsPath.Split(',')) {
        $entry = $entry.Trim()
        if ($entry -and -not (Test-Path -LiteralPath $entry -PathType Container)) {
            $badPaths += "addons_path: $entry"
        }
    }
}
$dataDir = Get-ConfValue "data_dir"
if ($dataDir -and -not (Test-Path -LiteralPath $dataDir -PathType Container)) {
    $badPaths += "data_dir: $dataDir"
}

if ($badPaths.Count -gt 0) {
    Write-Host "$conf references paths that do not exist:" -ForegroundColor Red
    $badPaths | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "Odoo would start anyway -- with those modules missing, or raising" -ForegroundColor Yellow
    Write-Host "FileNotFoundError per attachment. Fix odoo.conf before starting." -ForegroundColor Yellow
    exit 1
}

$cmd  = @("-m", "odoo")
if ($Shell) { $cmd += "shell" }
$cmd += @("-c", $conf)

if ($Install) { $cmd += @("-i", $Install, "--stop-after-init") }
if ($Update)  { $cmd += @("-u", $Update,  "--stop-after-init") }
if ($Dev)     { $cmd += @("--dev", "reload,qweb,xml") }

Write-Host "> python $($cmd -join ' ')" -ForegroundColor DarkGray
if (-not ($Install -or $Update -or $Shell)) {
    Write-Host "  http://localhost:8069   (admin / admin)" -ForegroundColor Cyan
}
& $python @cmd
$code = $LASTEXITCODE

# A native command's failure does not trip $ErrorActionPreference, so without
# this the server vanishing looks like a clean exit.
if ($code -ne 0) {
    Write-Host ""
    Write-Host "Odoo exited with code $code." -ForegroundColor Yellow

    # -1 (0xFFFFFFFF) is the wall-clock watchdog killing the server: its
    # reload() is os.kill(pid, SIGHUP), and Odoo shims SIGHUP to -1 on
    # Windows, where os.kill means TerminateProcess. See limit_time_real in
    # odoo.conf.
    if ($code -eq -1 -or $code -eq 4294967295) {
        Write-Host "This is the limit_time_real watchdog terminating the process," -ForegroundColor Yellow
        Write-Host "not a crash in your code. Set 'limit_time_real = 0' in odoo.conf." -ForegroundColor Yellow
    }
}
exit $code
