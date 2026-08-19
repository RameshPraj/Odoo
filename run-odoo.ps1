# Odoo 19 service management (Windows / PowerShell).
#
#   .\run-odoo.ps1 start              start in the background, wait until healthy
#   .\run-odoo.ps1 status             RUNNING / STOPPED / DEGRADED, with detail
#   .\run-odoo.ps1 logs-follow        tail the log
#   .\run-odoo.ps1 doctor             read-only diagnostic, PASS/WARN/FAIL
#   .\run-odoo.ps1 upgrade l10n_np_accounting -Db odoo19    (--db also accepted)
#
#   .\run-odoo.ps1 help               full command list, options and exit codes
#
# This is a developer/operator convenience layer, NOT a service manager. A
# background PowerShell-launched process has no supervision, no restart-on-crash
# and no boot integration. For production see docs/operations/ODOO_SERVICE_MANAGEMENT.md
# (Linux: systemd, deploy/odoo.service).
#
# Written for Windows PowerShell 5.1, which is what ships with Windows: no
# ternary operator, no ?? / ?., no && / || chain operators.

# Deliberately a *simple* param block: no [CmdletBinding()] and no [Parameter()]
# attributes. Either one turns this into an advanced script, which automatically
# gains the common parameters -- and -Debug's built-in alias is 'db', which
# collides with -Db below. Positional binding still works by declaration order.
param(
    [string] $Command,
    [string] $Target,

    # Explicit database. Required by every command that modifies one.
    [Alias('Database')]
    [string] $Db,

    # Line count for logs / errors. Declared [string], not [int], on purpose: see
    # the POSIX-flag normalisation below. With [int] here, `upgrade mod --db name`
    # fails during parameter binding with "Cannot convert value \"name\" to type
    # System.Int32" -- naming a parameter the user never typed, before any code of
    # ours can explain. Validated and converted a few lines down instead.
    [Alias('n')]
    [string] $Lines = '40',

    # start/dev: run attached to this console instead of in the background.
    [switch] $Foreground,

    # Override the start/stop wait, in seconds.
    [int] $Timeout = 0,

    [switch] $NoColor,

    # Deprecated compatibility flags. See Show-Help.
    [string] $Install,
    [string] $Update,
    [switch] $Shell,
    [switch] $Dev,
    [switch] $Help,

    # Internal. This script re-enters itself as a short-lived helper to deliver
    # Ctrl-C to Odoo's console; see Send-ConsoleCtrlC. Not for direct use.
    [int] $InternalCtrlCPid = 0,
    [int] $InternalCallerPid = 0
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

# ---------------------------------------------------------------------------
# Accept the POSIX flag spellings this file's own header advertises (OPS-7).
#
# PowerShell does not treat `--db` as a parameter name; it is just a positional
# string. So `upgrade l10n_np_accounting --db odoo19` -- the example at the top of
# this script, and the spelling run-odoo.sh uses -- bound '--db' to $Db and pushed
# 'odoo19' into $Lines, which failed to cast. The two scripts are documented as one
# interface, so the flag is now translated rather than rejected.
#
# Two shapes, depending on whether the verb takes a target:
#     upgrade <module> --db <name>   -> $Target=<module>  $Db='--db'  $Lines=<name>
#     test              --db <name>  -> $Target='--db'    $Db=<name>
# The second only ever appeared to work by luck: the tokens shift one place and the
# value happens to land in $Db, leaving '--db' sitting in $Target.
# ---------------------------------------------------------------------------
$PosixDbFlags = @('--db', '--database')
if ($Db -in $PosixDbFlags) {
    $Db = $Lines
    $Lines = '40'
} elseif ($Target -in $PosixDbFlags) {
    $Target = ''
}

# `--help` and `--version` are too commonly typed to answer with a lecture about
# flag spellings, and both have a verb here. Translate them.
if ($Command -in @('--help', '--version')) {
    $Command = $Command.TrimStart('-')
}

# Anything else starting with `--` is silently ignored by positional binding, which
# is worse than an error: `start --foreground` would land in $Target and simply not
# start in the foreground. Fail with the PowerShell spelling instead.
foreach ($token in @($Command, $Target, $Db, $Lines)) {
    if ($token -is [string] -and $token -like '--*') {
        Write-Host "Unknown option '$token'." -ForegroundColor Red
        Write-Host "  This is the PowerShell script; use -Db, -Lines, -Foreground, -Timeout, -NoColor." -ForegroundColor Yellow
        Write-Host "  The POSIX spellings belong to run-odoo.sh, except --db/--database which are accepted here." -ForegroundColor Yellow
        exit 2
    }
}

# A separate int rather than writing back into $Lines: that variable carries a
# [string] type constraint from param(), so assigning 40 to it silently coerces back
# to "40" and every later use would depend on implicit conversion.
$LineCount = 0
if (-not [int]::TryParse($Lines, [ref] $LineCount) -or $LineCount -lt 1) {
    Write-Host "-Lines must be a positive whole number; got '$Lines'." -ForegroundColor Red
    exit 2
}

# ---------------------------------------------------------------------------
# Internal helper mode: deliver Ctrl-C to another process's console.
#
# This runs FIRST, before anything else is set up, because it must be a bare
# short-lived process. It cannot print anything after FreeConsole() -- its
# inherited stdout handle is gone -- so it communicates by exit code only:
#     0  event delivered
#    10  could not attach: the target has no console we may attach to, so a
#        graceful stop is not available for it
#    11  refused: our own caller shares that console, and signalling it would
#        Ctrl-C the developer's shell
#    12  attach succeeded but GenerateConsoleCtrlEvent failed
# ---------------------------------------------------------------------------
if ($InternalCtrlCPid -gt 0) {
    Add-Type -Namespace OdooSvc -Name Kernel -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool FreeConsole();
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool AttachConsole(uint dwProcessId);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool GenerateConsoleCtrlEvent(uint dwCtrlEvent, uint dwProcessGroupId);
[DllImport("kernel32.dll", SetLastError=true)] public static extern uint GetConsoleProcessList(uint[] lpdwProcessList, uint dwProcessCount);
'@
    # AttachConsole fails with ACCESS_DENIED while we still hold our own console.
    [void][OdooSvc.Kernel]::FreeConsole()
    if (-not [OdooSvc.Kernel]::AttachConsole([uint32] $InternalCtrlCPid)) { exit 10 }

    # The interlock. If the target's console ever turns out to contain our
    # caller, a Ctrl-C to group 0 would hit the caller's shell too. Refusing
    # here turns that misconfiguration into a harmless failure instead of
    # interrupting the developer's terminal.
    if ($InternalCallerPid -gt 0) {
        $buffer = New-Object uint32[] 64
        $count = [OdooSvc.Kernel]::GetConsoleProcessList($buffer, 64)
        for ($i = 0; $i -lt $count; $i++) {
            if ($buffer[$i] -eq [uint32] $InternalCallerPid) {
                [void][OdooSvc.Kernel]::FreeConsole()
                exit 11
            }
        }
    }

    # Ignore the event ourselves, then raise it for the whole attached console.
    # Group must be 0: CTRL_C_EVENT cannot be targeted at a specific group.
    [void][OdooSvc.Kernel]::SetConsoleCtrlHandler([IntPtr]::Zero, $true)
    $sent = [OdooSvc.Kernel]::GenerateConsoleCtrlEvent(0, 0)
    [void][OdooSvc.Kernel]::FreeConsole()
    if ($sent) { exit 0 }
    exit 12
}

# ---------------------------------------------------------------------------
# Configuration. Resolution order for every value:
#   explicit parameter -> environment variable -> odoo.conf -> discovered default
# Nothing here is hard-coded that can be discovered instead.
# ---------------------------------------------------------------------------

$Root = $PSScriptRoot

function Get-Env([string] $name, [string] $fallback) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $fallback }
    return $value
}

$Conf      = Get-Env 'ODOO_CONF'    (Join-Path $Root 'odoo.conf')
$Python    = Get-Env 'ODOO_PYTHON'  (Join-Path $Root 'venv\Scripts\python.exe')
$LogDir    = Join-Path $Root 'logs'
$LogFile   = Get-Env 'ODOO_LOG'     (Join-Path $LogDir 'odoo.log')
$RuntimeDir = Join-Path $Root '.runtime'
$PidFile   = Get-Env 'ODOO_PIDFILE' (Join-Path $RuntimeDir 'odoo.pid')
$LockDir   = Join-Path $RuntimeDir 'start.lock'

# Note on stderr: a detached child cannot both have its own console (needed for
# a graceful Ctrl-C stop) and have its streams redirected -- redirection forces
# UseShellExecute=false, which shares the caller's console. Odoo configures
# logging in the second statement of main(), so virtually every real failure
# reaches --logfile anyway. The three that do not (an unreadable -c path, a
# failure to import odoo, and "Forced shutdown.") are diagnosed by
# `start -Foreground`, which the failure path suggests.

$StartTimeout = [int](Get-Env 'ODOO_START_TIMEOUT' '90')
$StopTimeout  = [int](Get-Env 'ODOO_STOP_TIMEOUT'  '30')
$LogMaxMB     = [int](Get-Env 'ODOO_LOG_MAX_MB'    '20')
$LogKeep      = [int](Get-Env 'ODOO_LOG_KEEP'      '5')

if ($Timeout -gt 0) { $StartTimeout = $Timeout; $StopTimeout = $Timeout }

# ---------------------------------------------------------------------------
# Output. Colour is decoration only -- every line is readable without it.
# ---------------------------------------------------------------------------

$UseColor = $true
if ($NoColor) { $UseColor = $false }
if (-not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable('NO_COLOR'))) { $UseColor = $false }

function Write-Tagged([string] $tag, [string] $message, [string] $color) {
    $line = "[$tag] $message"
    if ($UseColor) { Write-Host $line -ForegroundColor $color } else { Write-Host $line }
}
function Write-Ok   ([string] $m) { Write-Tagged 'OK'   $m 'Green' }
function Write-Warn ([string] $m) { Write-Tagged 'WARN' $m 'Yellow' }
function Write-Fail ([string] $m) { Write-Tagged 'FAIL' $m 'Red' }
function Write-Note ([string] $m) {
    if ($UseColor) { Write-Host $m -ForegroundColor DarkGray } else { Write-Host $m }
}
function Write-Field([string] $label, $value) {
    Write-Host ("{0,-12}{1}" -f ($label + ':'), $value)
}

# ---------------------------------------------------------------------------
# odoo.conf reader.
#
# Preserved from the previous version of this script: last occurrence wins,
# matching Odoo's own parsing. Values run to end-of-line and may contain
# spaces, so they are never quoted -- this project's addons_path contains
# "OneDrive - Verisk Analytics".
# ---------------------------------------------------------------------------

$script:ConfCache = $null

function Get-ConfValue([string] $key) {
    if (-not (Test-Path -LiteralPath $Conf)) { return $null }
    if ($null -eq $script:ConfCache) {
        $script:ConfCache = Get-Content -LiteralPath $Conf -Encoding UTF8
    }
    $found = $null
    foreach ($line in $script:ConfCache) {
        # Skip comments: Odoo's ConfigParser accepts both ; and #.
        if ($line -match '^\s*[;#]') { continue }
        if ($line -match "^\s*$([regex]::Escape($key))\s*=\s*(.+?)\s*$") {
            $found = $Matches[1]
        }
    }
    return $found
}

function Get-ConfInt([string] $key, [int] $fallback) {
    $raw = Get-ConfValue $key
    if ([string]::IsNullOrWhiteSpace($raw)) { return $fallback }
    $parsed = 0
    if ([int]::TryParse($raw.Trim(), [ref] $parsed)) { return $parsed }
    return $fallback
}

function Get-ConfBool([string] $key) {
    $raw = Get-ConfValue $key
    if ([string]::IsNullOrWhiteSpace($raw)) { return $false }
    return @('true', '1', 'yes', 'on') -contains $raw.Trim().ToLower()
}

function Get-AddonsDirs {
    $raw = Get-ConfValue 'addons_path'
    $dirs = @()
    if (-not [string]::IsNullOrWhiteSpace($raw)) {
        foreach ($entry in $raw.Split(',')) {
            $trimmed = $entry.Trim()
            if ($trimmed) { $dirs += $trimmed }
        }
    }
    return $dirs
}

function Get-HttpPort {
    $fromEnv = [Environment]::GetEnvironmentVariable('ODOO_HTTP_PORT')
    if (-not [string]::IsNullOrWhiteSpace($fromEnv)) { return [int] $fromEnv }
    return Get-ConfInt 'http_port' 8069
}

function Get-HttpHost {
    # http_interface is what Odoo binds. 0.0.0.0 is not connectable as a
    # destination, so probe loopback in that case.
    $iface = Get-ConfValue 'http_interface'
    if ([string]::IsNullOrWhiteSpace($iface)) { return '127.0.0.1' }
    $iface = $iface.Trim()
    if ($iface -eq '0.0.0.0' -or $iface -eq '::' -or $iface -eq 'False') { return '127.0.0.1' }
    return $iface
}

function Get-HealthUrl([string] $query) {
    $url = "http://$(Get-HttpHost):$(Get-HttpPort)/web/health"
    if ($query) { $url = $url + '?' + $query }
    return $url
}

# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------

function Test-Prereqs {
    # Returns $true when the environment can run Odoo at all. Exit code 2
    # territory: a dependency or configuration problem, not an operational one.
    $ok = $true
    if (-not (Test-Path -LiteralPath $Python)) {
        Write-Fail "Python not found at $Python"
        Write-Note "  Suggested action: py -3.12 -m venv venv"
        Write-Note "                    .\venv\Scripts\python.exe -m pip install -r requirements.txt"
        $ok = $false
    }
    if (-not (Test-Path -LiteralPath $Conf)) {
        Write-Fail "$Conf not found"
        Write-Note "  Suggested action: copy odoo.conf.example odoo.conf, then edit it for this host"
        $ok = $false
    }
    return $ok
}

function Get-BadConfPaths {
    # Refuse to start on a stale addons_path or data_dir.
    #
    # Odoo treats neither as fatal: a missing addons_path entry is logged as
    # "no such directory ... skipped" and the server starts with those modules
    # simply absent, while a stale data_dir surfaces only later as a
    # FileNotFoundError per attachment. Both failures look like a healthy
    # server. Moving the project directory without updating odoo.conf has
    # already caused exactly this (audit finding OPS-1).
    $bad = @()
    foreach ($entry in Get-AddonsDirs) {
        if (-not (Test-Path -LiteralPath $entry -PathType Container)) {
            $bad += "addons_path: $entry"
        }
    }
    $dataDir = Get-ConfValue 'data_dir'
    if ($dataDir -and -not (Test-Path -LiteralPath $dataDir -PathType Container)) {
        $bad += "data_dir: $dataDir"
    }
    return $bad
}

function Assert-ConfPaths {
    $bad = @(Get-BadConfPaths)
    if ($bad.Count -gt 0) {
        Write-Fail "$Conf references paths that do not exist:"
        foreach ($entry in $bad) { Write-Host "  $entry" }
        Write-Host ""
        Write-Note "Odoo would start anyway -- with those modules missing, or raising"
        Write-Note "FileNotFoundError per attachment. Fix odoo.conf before starting."
        exit 2
    }
}

# ---------------------------------------------------------------------------
# Process identity.
#
# A PID is never trusted on its own: PIDs are reused, and Odoo's pidfile
# survives an ungraceful kill because its atexit cleanup does not run. Every
# PID is verified to be *this project's* Odoo before it is reported or signalled.
# Get-Process -Id proves only that something with that number exists.
# ---------------------------------------------------------------------------

function Get-ProcessInfo([int] $procId) {
    if ($procId -le 0) { return $null }
    try {
        return Get-CimInstance Win32_Process -Filter "ProcessId = $procId" -ErrorAction Stop
    } catch {
        return $null
    }
}

function Test-CommandLineContains($cmdline, [string] $needle) {
    if ([string]::IsNullOrWhiteSpace($cmdline)) { return $false }
    if ([string]::IsNullOrWhiteSpace($needle)) { return $false }
    # IndexOf, not -like: a Windows path may contain [ or ], which -like would
    # interpret as a character class and silently fail to match.
    return ([string] $cmdline).IndexOf($needle, [StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Test-IsOurOdoo($proc) {
    if ($null -eq $proc) { return $false }
    # The anchor is the absolute --pidfile path this script injects. It is
    # unique to this checkout, and -- unlike "-m odoo" -- it survives a re-exec:
    # --dev reload and the watchdog both rebuild argv via stripped_sys_argv()
    # (odoo/tools/misc.py:834-850), which drops "-m odoo" and rewrites argv[0]
    # to odoo/__main__.py, but preserves -c, --pidfile and --logfile.
    if (Test-CommandLineContains $proc.CommandLine $PidFile) { return $true }

    # Fallback for a server someone started by hand without --pidfile. Both
    # halves are needed: "-m odoo" alone would match another checkout, and the
    # repo root alone matches any python running from this tree.
    if (-not (Test-CommandLineContains $proc.CommandLine $Root)) { return $false }
    if ($proc.CommandLine -notmatch '(?i)(^|["\s])(-m\s+odoo|odoo-bin|odoo\\__main__\.py)') { return $false }
    return $true
}

function Test-IsModuleOperation($proc) {
    # A killed -i/-u leaves ir_module_module mid-state and a registry that may
    # not load: PostgreSQL protects each transaction, not the sequence of them.
    if ($null -eq $proc) { return $false }
    return ($proc.CommandLine -match '(?i)(^|\s)(-u|-i|--update|--init)(\s|=)')
}

function Get-PidFilePid {
    if (-not (Test-Path -LiteralPath $PidFile)) { return 0 }
    $raw = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($raw)) { return 0 }
    $parsed = 0
    if ([int]::TryParse($raw.Trim(), [ref] $parsed)) { return $parsed }
    return 0
}

function Get-PortOwnerPid([int] $port) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop
        if ($conns) { return [int](@($conns)[0].OwningProcess) }
    } catch {
        # Get-NetTCPConnection is absent on some SKUs; netstat always is not.
        $line = (netstat -ano | Select-String -Pattern "LISTENING" | Select-String -Pattern ":$port\s" | Select-Object -First 1)
        if ($line) {
            $fields = ($line.Line -split '\s+') | Where-Object { $_ }
            $candidate = $fields[$fields.Count - 1]
            $parsed = 0
            if ([int]::TryParse($candidate, [ref] $parsed)) { return $parsed }
        }
    }
    return 0
}

function Get-OdooState {
    # The state machine. Two independent signals -- the pidfile and the port
    # owner -- reconciled into one verdict.
    $port      = Get-HttpPort
    $filePid   = Get-PidFilePid
    $portPid   = Get-PortOwnerPid $port
    $fileProc  = Get-ProcessInfo $filePid
    $portProc  = Get-ProcessInfo $portPid

    $state = [ordered] @{
        State        = 'STOPPED'
        Pid          = 0
        Port         = $port
        PortOwnerPid = $portPid
        StalePidFile = $false
        PidReused    = $false
        PortForeign  = $false
        Detail       = ''
    }

    if ($filePid -gt 0) {
        if ($null -eq $fileProc) {
            $state.StalePidFile = $true
            $state.Detail = "pidfile names PID $filePid, which is not running"
        } elseif (-not (Test-IsOurOdoo $fileProc)) {
            # The dangerous case: the number was recycled by an unrelated
            # process. Treat the file as stale; never signal that PID.
            $state.StalePidFile = $true
            $state.PidReused    = $true
            $state.Detail = "pidfile names PID $filePid, but that process is '$($fileProc.Name)', not this project's Odoo"
        } else {
            $state.Pid = $filePid
        }
    }

    # No usable pidfile, but something owns the port: adopt it only if it is
    # verifiably ours. This covers a server started by hand, and Linux workers
    # where Odoo skips the pidfile in evented mode.
    if ($state.Pid -eq 0 -and $portPid -gt 0) {
        if (Test-IsOurOdoo $portProc) {
            $state.Pid = $portPid
            $state.Detail = "discovered by port $port (no valid pidfile)"
        } else {
            $state.PortForeign = $true
            $name = 'unknown'
            if ($null -ne $portProc) { $name = $portProc.Name }
            $state.Detail = "port $port is held by PID $portPid ($name), which is not this project's Odoo"
        }
    }

    if ($state.Pid -gt 0) {
        if ($portPid -eq $state.Pid) {
            $state.State = 'RUNNING'
        } else {
            # Alive and ours, but not serving: still starting, or wedged.
            $state.State = 'DEGRADED'
            if (-not $state.Detail) { $state.Detail = "process $($state.Pid) is alive but not listening on $port" }
        }
    } elseif ($state.PortForeign) {
        $state.State = 'DEGRADED'
    }

    return $state
}

function Remove-StalePidFile([string] $why) {
    if (Test-Path -LiteralPath $PidFile) {
        Write-Warn "Removing stale pidfile: $why"
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

function Invoke-HealthProbe([switch] $WithDb, [int] $TimeoutSec = 5) {
    # /web/health is auth='none' and save_session=False
    # (odoo/addons/web/controllers/home.py:172), so polling it neither needs a
    # login nor litters data_dir/sessions. With db_server_status it also opens a
    # 'postgres' connection and answers 500 when PostgreSQL is unreachable --
    # which tests the credentials Odoo itself uses, not a guess at them.
    $query = ''
    if ($WithDb) { $query = 'db_server_status=1' }
    $url = Get-HealthUrl $query
    $result = @{ Ok = $false; Status = 0; Body = ''; Error = '' }

    # HttpWebRequest with Proxy explicitly nulled, rather than
    # Invoke-WebRequest. On a managed corporate machine the system proxy can be
    # configured to intercept even 127.0.0.1, and Windows PowerShell 5.1 has no
    # -NoProxy switch to opt out. A health check that silently probes a proxy
    # instead of the local server is worse than no health check.
    try {
        $request = [System.Net.HttpWebRequest]::Create($url)
        $request.Proxy = $null
        $request.Timeout = $TimeoutSec * 1000
        $request.ReadWriteTimeout = $TimeoutSec * 1000
        $request.Method = 'GET'
        $response = $request.GetResponse()
        try {
            $result.Status = [int] $response.StatusCode
            $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
            try { $result.Body = $reader.ReadToEnd() } finally { $reader.Close() }
            $result.Ok = ($result.Status -eq 200)
        } finally { $response.Close() }
    } catch [System.Net.WebException] {
        $result.Error = $_.Exception.Message
        # A 500 is a *successful* probe reporting a real failure: /web/health
        # answers 500 when db_server_status is requested and PostgreSQL is down.
        $webResponse = $_.Exception.Response
        if ($null -ne $webResponse) {
            try {
                $result.Status = [int] $webResponse.StatusCode
                $reader = New-Object System.IO.StreamReader($webResponse.GetResponseStream())
                try { $result.Body = $reader.ReadToEnd() } finally { $reader.Close() }
            } catch { }
        }
    } catch {
        $result.Error = $_.Exception.Message
    }
    return $result
}

function Test-PostgresReachable {
    # Direct probe, for when Odoo is down and /web/health cannot answer.
    # A TCP connect is enough to distinguish "PostgreSQL absent" from "Odoo
    # absent", and needs no client binary or credentials.
    $pgHost = Get-ConfValue 'db_host'
    $pgPort = Get-ConfInt 'db_port' 5432
    if ([string]::IsNullOrWhiteSpace($pgHost) -or $pgHost.Trim() -eq 'False') { $pgHost = 'localhost' }
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($pgHost.Trim(), $pgPort, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(3000, $false)) { return $false }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

# ---------------------------------------------------------------------------
# Log handling
# ---------------------------------------------------------------------------

function New-RuntimeDirs {
    foreach ($dir in @($LogDir, $RuntimeDir)) {
        if (-not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
    }
}

function Rotate-LogIfLarge {
    # Rotation happens HERE, at start, because it cannot happen later: with a
    # logfile configured, Odoo picks logging.FileHandler on Windows
    # (odoo/netsvc.py:266-272) rather than the WatchedFileHandler it uses on
    # POSIX, and a FileHandler never reopens. An open file also cannot be
    # renamed on Windows. So the only safe moment is before Odoo opens it.
    if (-not (Test-Path -LiteralPath $LogFile)) { return }
    $sizeMB = (Get-Item -LiteralPath $LogFile).Length / 1MB
    if ($sizeMB -lt $LogMaxMB) { return }

    $oldest = "$LogFile.$LogKeep"
    if (Test-Path -LiteralPath $oldest) { Remove-Item -LiteralPath $oldest -Force }
    for ($i = $LogKeep - 1; $i -ge 1; $i--) {
        $from = "$LogFile.$i"
        $to   = "$LogFile.$($i + 1)"
        if (Test-Path -LiteralPath $from) { Move-Item -LiteralPath $from -Destination $to -Force }
    }
    Move-Item -LiteralPath $LogFile -Destination "$LogFile.1" -Force
    Write-Note "Rotated $([math]::Round($sizeMB, 1)) MB log to $(Split-Path -Leaf $LogFile).1"
}

function Get-LogTail([int] $count) {
    if (-not (Test-Path -LiteralPath $LogFile)) { return @() }
    return @(Get-Content -LiteralPath $LogFile -Tail $count -ErrorAction SilentlyContinue)
}

# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------

function Get-BaseArgs {
    # Always -c: every value Odoo needs comes from odoo.conf, so there is one
    # source of truth and no drift between this script and the server.
    return @('-m', 'odoo', '-c', $Conf)
}

function Assert-ArgvContains([string[]] $argv, [string[]] $required) {
    # A refusal is always better than running the wrong Odoo command against a
    # named database. See the note at the call sites.
    foreach ($token in $required) {
        if ($argv -notcontains $token) {
            Write-Fail "Internal error: the command line built for Odoo is missing '$token'."
            Write-Note "  Built: $($argv -join ' ')"
            Write-Note "  Refusing to run it rather than risk the wrong operation."
            exit 2
        }
    }
}

function Invoke-Odoo([string[]] $odooArgs, [string] $label) {
    # Foreground execution, exit code propagated verbatim.
    #
    # Set-Location is load-bearing: Odoo is NOT pip-installed into the venv, so
    # `python -m odoo` resolves only because the working directory is the repo
    # root. The previous version of this script computed $root but never used it
    # for cwd, so it silently depended on wherever the caller happened to be.
    Push-Location -LiteralPath $Root
    # Odoo writes its entire log to stderr. With $ErrorActionPreference = 'Stop'
    # in force, PowerShell wraps every one of those lines in an ErrorRecord
    # (NativeCommandError) and can treat it as terminating -- so a perfectly
    # healthy run looks like a page of red errors. Relax it around the native
    # call only; $LASTEXITCODE remains the authority on success, since a native
    # command's failure never trips $ErrorActionPreference anyway.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        Write-Note "> $(Split-Path -Leaf $Python) $($odooArgs -join ' ')"
        & $Python @odooArgs
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
        Pop-Location
    }
    Report-ExitCode $code $label
    return $code
}

function Report-ExitCode([int] $code, [string] $label) {
    # A native command's failure does not trip $ErrorActionPreference, so
    # without this the server vanishing looks like a clean exit.
    if ($code -eq 0) { return }
    Write-Host ""
    Write-Warn "$label exited with code $code."

    # -1 (0xFFFFFFFF) is the wall-clock watchdog killing the server: its
    # reload() is os.kill(pid, SIGHUP), and Odoo shims SIGHUP to -1 on
    # Windows, where os.kill means TerminateProcess. See limit_time_real in
    # odoo.conf.
    if ($code -eq -1 -or $code -eq 4294967295) {
        Write-Note "This is the limit_time_real watchdog terminating the process,"
        Write-Note "not a crash in your code. Set 'limit_time_real = 0' in odoo.conf."
    }
}

# ---------------------------------------------------------------------------
# Validation of user-supplied values
# ---------------------------------------------------------------------------

function Assert-Db([string] $name, [string] $operation) {
    if ([string]::IsNullOrWhiteSpace($name)) {
        Write-Fail "$operation modifies a database and needs an explicit -Db."
        Write-Note "  Suggested action: .\run-odoo.ps1 $operation <module> -Db <database>"
        Write-Note "  There is deliberately no default: this project is heading for"
        Write-Note "  database-per-tenant, where an implicit target is a data-loss bug."
        Write-Note "  Read-only listing: .\run-odoo.ps1 db-list"
        exit 2
    }
    if ($name -notmatch '^[A-Za-z0-9_-]+$') {
        Write-Fail "Refusing database name '$name': expected only letters, digits, underscore and hyphen."
        exit 2
    }
    return $name
}

function Assert-Module([string] $name) {
    if ([string]::IsNullOrWhiteSpace($name)) {
        Write-Fail "No module named. Usage: .\run-odoo.ps1 $Command <module> -Db <database>"
        exit 2
    }
    if ($name -notmatch '^[a-z][a-z0-9_]*$') {
        Write-Fail "Refusing module name '$name': Odoo module names are lowercase, digits and underscores."
        exit 2
    }
    # Search only the configured addons_path. A glob over the repo root would
    # wrongly accept l10n_ne/, which is a translation toolkit and not an addon.
    foreach ($dir in Get-AddonsDirs) {
        if (Test-Path -LiteralPath (Join-Path $dir "$name\__manifest__.py")) { return $name }
    }
    Write-Fail "Module '$name' has no __manifest__.py in any addons_path entry."
    Write-Note "  Searched:"
    foreach ($dir in Get-AddonsDirs) { Write-Note "    $dir" }
    Write-Note "  Available custom modules: .\run-odoo.ps1 addons-check"
    exit 2
}

# ---------------------------------------------------------------------------
# start / stop / restart
# ---------------------------------------------------------------------------

function Enter-StartLock {
    # mkdir is atomic, so two concurrent starts cannot both win. A lock older
    # than the start timeout is assumed abandoned.
    if (Test-Path -LiteralPath $LockDir) {
        $age = (Get-Date) - (Get-Item -LiteralPath $LockDir).CreationTime
        if ($age.TotalSeconds -lt ($StartTimeout + 30)) {
            Write-Fail "Another start is in progress (lock: $LockDir, age $([int]$age.TotalSeconds)s)."
            Write-Note "  Suggested action: wait, or remove the lock if you are certain it is abandoned."
            exit 1
        }
        Write-Warn "Removing abandoned start lock ($([int]$age.TotalSeconds)s old)"
        Remove-Item -LiteralPath $LockDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Path $LockDir -Force | Out-Null
}

function Exit-StartLock {
    if (Test-Path -LiteralPath $LockDir) {
        Remove-Item -LiteralPath $LockDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-Start([switch] $DevMode) {
    if (-not (Test-Prereqs)) { exit 2 }
    Assert-ConfPaths

    $state = Get-OdooState
    if ($state.State -eq 'RUNNING') {
        Write-Fail "Odoo is already running (PID $($state.Pid), port $($state.Port))."
        Write-Note "  Suggested action: .\run-odoo.ps1 restart"
        exit 1
    }
    if ($state.State -eq 'DEGRADED' -and $state.Pid -gt 0) {
        Write-Fail "Odoo process $($state.Pid) is alive but not serving. $($state.Detail)"
        Write-Note "  Suggested action: .\run-odoo.ps1 stop, then start again."
        exit 1
    }
    if ($state.PortForeign) {
        Write-Fail "Port $($state.Port) is already in use."
        $proc = Get-ProcessInfo $state.PortOwnerPid
        if ($null -ne $proc) {
            Write-Host "  Process: PID $($proc.ProcessId)  $($proc.Name)"
            # CommandLine is unreadable for a process owned by another user, so
            # only print the line when there is something in it.
            if (-not [string]::IsNullOrWhiteSpace($proc.CommandLine)) {
                Write-Host "  Command: $($proc.CommandLine)"
            }
        }
        Write-Note "  Suggested action: stop that process, or set ODOO_HTTP_PORT / http_port to a free port."
        exit 1
    }
    if ($state.StalePidFile) {
        Remove-StalePidFile $state.Detail
    }

    # gevent_port matters too: Odoo binds it for websockets, and a conflict
    # there fails at runtime rather than at startup.
    $geventPort = Get-ConfInt 'gevent_port' 0
    if ($geventPort -gt 0) {
        $owner = Get-PortOwnerPid $geventPort
        if ($owner -gt 0) {
            Write-Warn "gevent_port $geventPort is already in use by PID $owner; websockets may fail."
        }
    }

    New-RuntimeDirs
    Rotate-LogIfLarge

    $odooArgs = Get-BaseArgs
    # --pidfile ONLY for the long-running commands. setup_pid_file() runs
    # unconditionally in odoo/cli/server.py:117, even under --stop-after-init,
    # so giving it to a one-shot test/upgrade would overwrite a live server's
    # pidfile and then atexit-delete it, leaving status blind to a running server.
    $odooArgs += @('--pidfile', $PidFile)
    $odooArgs += @('--logfile', $LogFile)
    if ($DevMode) { $odooArgs += @('--dev', 'reload,qweb,xml') }

    if ($Foreground) {
        Write-Note "Foreground mode: Ctrl-C stops the server. Logs also go to $LogFile"
        $code = Invoke-Odoo $odooArgs 'Odoo'
        exit $code
    }

    Enter-StartLock
    try {
        Write-Note "> $(Split-Path -Leaf $Python) $($odooArgs -join ' ')"
        # Record the log size before spawning. The "log tail" for a failed start
        # is then exactly the bytes appended after this offset -- no line-count
        # guessing, and no confusion with the previous run's output.
        $logOffset = 0
        if (Test-Path -LiteralPath $LogFile) { $logOffset = (Get-Item -LiteralPath $LogFile).Length }

        $launchedPid = Start-OdooDetached $odooArgs
        if ($launchedPid -le 0) { exit 1 }
        $started = Wait-ForHealthy $launchedPid $logOffset
    } finally {
        Exit-StartLock
    }

    if (-not $started) { exit 1 }

    $state = Get-OdooState
    Write-Ok "Odoo started"
    Write-Host ""
    Write-Field 'URL'    (Get-HealthUrl).Replace('/web/health', '')
    Write-Field 'PID'    $state.Pid
    Write-Field 'Config' (Resolve-RelativePath $Conf)
    Write-Field 'Logs'   (Resolve-RelativePath $LogFile)
    $dbName = Get-ConfValue 'db_name'
    if ($dbName) { Write-Field 'Database' $dbName }
    exit 0
}

function Start-OdooDetached([string[]] $odooArgs) {
    # Launch with the child getting its OWN console, window hidden.
    #
    # This specific combination is what makes a graceful stop possible later:
    # Ctrl-C can only be delivered to a console we can AttachConsole to, and a
    # process started with `Start-Process -WindowStyle Hidden` has none --
    # verified on this machine, where AttachConsole returned ACCESS_DENIED for
    # such a child. CREATE_NEW_CONSOLE gives it one; SW_HIDE keeps the window off
    # screen; and the new console does NOT contain this shell, so a Ctrl-C to it
    # cannot reach the developer's terminal.
    #
    # Deliberately NOT CREATE_NEW_PROCESS_GROUP (which disables Ctrl-C for the
    # whole group) and NOT DETACHED_PROCESS (which leaves no console at all).
    #
    # PowerShell 5.1 cannot set process creation flags, so the spawn goes through
    # the venv Python that is already a hard requirement here.
    #
    # argv travels as base64-encoded JSON. Plain JSON does not survive the trip:
    # PowerShell 5.1 does not escape embedded double quotes when it builds a
    # native command line, so the quotes are eaten by the CRT parser and Python
    # sees a truncated string. Base64 contains no quotes, spaces or backslashes,
    # which matters doubly here because the repo path has a space AND a hyphen.
    # NOTE: this Python source must contain NO double quotes. It is passed via
    # `-c`, and PowerShell 5.1 hands native commands a command line in which
    # embedded double quotes are consumed by the CRT parser -- a literal
    # "utf-8" arrived as a bare `utf` and raised NameError. b64decode().decode()
    # already defaults to UTF-8, so none are needed.
    $spawner = @'
import base64, json, subprocess, sys
argv = json.loads(base64.b64decode(sys.argv[1]).decode())
cwd = base64.b64decode(sys.argv[2]).decode()
info = subprocess.STARTUPINFO()
info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
info.wShowWindow = 0                       # SW_HIDE
child = subprocess.Popen(argv, creationflags=0x00000010,  # CREATE_NEW_CONSOLE
                         startupinfo=info, close_fds=True, cwd=cwd)
print(child.pid)
'@
    $json = (@($Python) + $odooArgs) | ConvertTo-Json -Compress
    $payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
    $cwdArg  = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Root))
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $Python -c $spawner $payload $cwdArg 2>&1
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Could not spawn Odoo:"
        @($output) | ForEach-Object { Write-Host "  $_" }
        return 0
    }
    $spawnedPid = 0
    foreach ($line in @($output)) {
        $candidate = 0
        if ([int]::TryParse(([string] $line).Trim(), [ref] $candidate)) { $spawnedPid = $candidate }
    }
    if ($spawnedPid -le 0) {
        Write-Fail "Spawner did not report a PID. Output: $($output -join ' ')"
        return 0
    }
    return $spawnedPid
}

function Send-ConsoleCtrlC([int] $procId) {
    # Re-enter this script as a disposable helper. FreeConsole/AttachConsole are
    # per-process, so doing this in a child leaves our own console intact.
    $self = $PSCommandPath
    if ([string]::IsNullOrWhiteSpace($self)) { $self = Join-Path $Root 'run-odoo.ps1' }

    # The script path must be quoted explicitly. Start-Process joins
    # -ArgumentList with spaces without reliably quoting elements that contain
    # them, and this repo's path contains a space -- powershell.exe then looked
    # for a file called "C:\Users\...\OneDrive" and exited -196608, which
    # presented as "could not deliver Ctrl-C" and sent every stop down the
    # force-kill path after a pointless 30-second wait.
    $arguments = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', ('"' + $self + '"'),
        '-InternalCtrlCPid', $procId,
        '-InternalCallerPid', $PID
    )
    $helper = Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -Wait -PassThru `
                            -ArgumentList $arguments
    return $helper.ExitCode
}

function Wait-ForHealthy([int] $launchedPid, [long] $logOffset) {
    # Two phases, because the pidfile appears late. odoo/cli/server.py:95-119
    # runs parse_config -> check_postgres_user -> report_configuration ->
    # _create_empty_database (which CONNECTS to PostgreSQL) and only then
    # setup_pid_file(). So the single commonest local failure -- db_port pointing
    # at the wrong PostgreSQL cluster -- kills the process before any pidfile
    # exists. Phase A catches that in about a second instead of waiting out the
    # whole timeout.
    Write-Note "Waiting up to ${StartTimeout}s for Odoo to become healthy..."

    # --- Phase A: the pidfile appears -------------------------------------
    $phaseADeadline = (Get-Date).AddSeconds([Math]::Min(25, $StartTimeout))
    $serverPid = 0
    while ((Get-Date) -lt $phaseADeadline) {
        if (-not (Test-ProcessAlive $launchedPid)) {
            Write-Fail "Odoo exited during startup, before it wrote a pidfile."
            Write-Note "  That means it failed in configuration or while connecting to PostgreSQL,"
            Write-Note "  which happens before the pidfile is written."
            Show-StartupFailureDetail $logOffset
            return $false
        }
        $candidate = Get-PidFilePid
        if ($candidate -gt 0 -and (Test-ProcessAlive $candidate)) { $serverPid = $candidate; break }
        Start-Sleep -Milliseconds 250
    }
    if ($serverPid -eq 0) {
        Write-Fail "No pidfile appeared at $(Resolve-RelativePath $PidFile) within 25s."
        Show-StartupFailureDetail $logOffset
        return $false
    }
    Write-Ok "Server process running (PID $serverPid)"

    # --- Phase B: HTTP healthy, and the registry loaded -------------------
    # /web/health has to resolve a registry to build the routing map, so a 200
    # already implies the registry loaded. The log line is still checked because
    # it is the unambiguous confirmation, and it costs nothing to read.
    $deadline = (Get-Date).AddSeconds($StartTimeout)
    $httpUp = $false
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-ProcessAlive $serverPid)) {
            Write-Fail "Odoo exited during startup (PID $serverPid)."
            Show-StartupFailureDetail $logOffset
            return $false
        }
        if (-not $httpUp) {
            $probe = Invoke-HealthProbe -TimeoutSec 4
            if ($probe.Ok) { $httpUp = $true; Write-Ok "HTTP responding on port $(Get-HttpPort)" }
        }
        if ($httpUp) {
            # Anchor string from odoo/modules/loading.py:584.
            foreach ($line in (Get-LogTail 400)) {
                if ($line -like '*Modules loaded.*') {
                    Write-Ok "Modules loaded"
                    return $true
                }
            }
        }
        Start-Sleep -Milliseconds 700
    }

    if ($httpUp) {
        # Serving but the confirmation never appeared: report ready with a caveat
        # rather than failing a server that is demonstrably answering requests.
        Write-Warn "HTTP is responding but 'Modules loaded.' did not appear in the log."
        Write-Note "  The server is serving requests. Check .\run-odoo.ps1 errors if it misbehaves."
        return $true
    }
    Write-Fail "Odoo did not become healthy within ${StartTimeout}s."
    Show-StartupFailureDetail $logOffset
    Write-Note "  Suggested action: .\run-odoo.ps1 errors, or raise ODOO_START_TIMEOUT."
    return $false
}

function Test-ProcessAlive([int] $procId) {
    if ($procId -le 0) { return $false }
    return ($null -ne (Get-ProcessInfo $procId))
}

function Show-StartupFailureDetail([long] $logOffset) {
    # Exactly the bytes this run appended, so nothing from the previous start is
    # mistaken for the current failure.
    if (Test-Path -LiteralPath $LogFile) {
        $stream = $null
        try {
            $stream = [System.IO.File]::Open($LogFile, [System.IO.FileMode]::Open,
                                             [System.IO.FileAccess]::Read,
                                             [System.IO.FileShare]::ReadWrite)
            if ($stream.Length -gt $logOffset) {
                $stream.Seek($logOffset, [System.IO.SeekOrigin]::Begin) | Out-Null
                $reader = New-Object System.IO.StreamReader($stream)
                $text = $reader.ReadToEnd()
                Write-Host ""
                Write-Host "--- log output from this start attempt ---"
                Write-Host $text.TrimEnd()
            } else {
                Write-Host ""
                Write-Warn "This start attempt wrote nothing to the log."
                Write-Note "  That is the signature of a failure before logging was configured:"
                Write-Note "  an unreadable -c path, or 'python -m odoo' failing to import."
                Write-Note "  Reproduce it visibly with: .\run-odoo.ps1 start -Foreground"
            }
        } catch {
            Write-Warn "Could not read the log: $($_.Exception.Message)"
        } finally {
            if ($null -ne $stream) { $stream.Dispose() }
        }
    }
}

function Invoke-Stop {
    # Every decision lives in Invoke-StopInline so that `restart` and `stop`
    # cannot drift apart. This is only the exit-code wrapper.
    exit (Invoke-StopInline)
}

function Stop-OdooProcess([int] $procId) {
    # The escalation ladder. Returns 0 on success.
    #
    # Rung 1 is genuinely graceful: Ctrl-C reaches CPython's default SIGINT
    # handler, which raises KeyboardInterrupt in the main thread -- and that
    # thread is sitting in time.sleep() inside ThreadedServer.run()
    # (odoo/service/server.py:756-762), which catches it and calls self.stop().
    # Odoo's atexit then removes the pidfile, which is why the pidfile
    # DISAPPEARING is treated below as proof that the clean path ran.
    #
    # Deliberately not attempted: CTRL_BREAK, which Odoo never handles and whose
    # CPython default (SIGBREAK at SIG_DFL) terminates abruptly; and
    # `taskkill` without /F, whose graceful path looks for a top-level window,
    # and a console app's window belongs to conhost.exe, not to python.exe.
    Write-Note "Stopping PID $procId (Ctrl-C, then force after ${StopTimeout}s)..."

    $ctrlResult = Send-ConsoleCtrlC $procId
    if ($ctrlResult -eq 0) {
        Write-Note "  Ctrl-C delivered to the server's console."
    } elseif ($ctrlResult -eq 10) {
        Write-Warn "  Server has no attachable console, so it cannot be asked to stop gracefully."
        Write-Note "  That happens when it was started by something other than this script."
    } elseif ($ctrlResult -eq 11) {
        Write-Warn "  Refused to send Ctrl-C: this shell shares that console, and signalling"
        Write-Note "  it would interrupt your terminal. Falling through to a forced stop."
    } else {
        Write-Warn "  Could not deliver Ctrl-C (helper exit $ctrlResult)."
    }

    # If Ctrl-C could not be delivered at all, there is nothing to wait for:
    # go straight to the forced stop instead of burning the whole timeout.
    if ($ctrlResult -ne 0) {
        Write-Note "  Nothing was signalled, so there is no graceful shutdown to wait for."
        return (Stop-OdooForcibly $procId)
    }

    # Wait for either the pidfile to vanish (atexit ran: provably clean) or the
    # process to die.
    $deadline = (Get-Date).AddSeconds($StopTimeout)
    $secondSignalAt = (Get-Date).AddSeconds([Math]::Max(3, [int]($StopTimeout * 0.6)))
    $secondSent = $false
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-ProcessAlive $procId)) {
            if (-not (Test-Path -LiteralPath $PidFile)) {
                Write-Ok "Odoo stopped cleanly (PID $procId; it removed its own pidfile)"
            } else {
                Write-Ok "Odoo stopped (PID $procId)"
            }
            Reap-LauncherStub $procId
            Clear-StoppedState
            return 0
        }
        if (-not $secondSent -and (Get-Date) -gt $secondSignalAt -and $ctrlResult -eq 0) {
            # A second quit signal takes Odoo's forced path: quit_signals_received
            # > 1 calls os._exit(0) (odoo/service/server.py:471-476). Faster, but
            # it skips atexit, so the pidfile survives and we clean it below.
            Write-Note "  Still shutting down; sending a second Ctrl-C to force it."
            $null = Send-ConsoleCtrlC $procId
            $secondSent = $true
        }
        Start-Sleep -Milliseconds 400
    }

    Write-Warn "Graceful stop timed out after ${StopTimeout}s."
    return (Stop-OdooForcibly $procId)
}

function Stop-OdooForcibly([int] $procId) {
    Write-Warn "Terminating PID $procId."
    Write-Note "  This is TerminateProcess. PostgreSQL is ACID so the database stays"
    Write-Note "  consistent, and an interrupted attachment write is left unreferenced"
    Write-Note "  and collected by Odoo's filestore GC -- but nothing is flushed, and a"
    Write-Note "  mail being handed to SMTP may be re-sent by the next cron pass."
    try {
        Stop-Process -Id $procId -Force -ErrorAction Stop
    } catch {
        Write-Fail "Could not terminate PID ${procId}: $($_.Exception.Message)"
        return 1
    }
    Start-Sleep -Milliseconds 800
    if (Test-ProcessAlive $procId) {
        Write-Fail "PID $procId is still running after a force kill."
        return 1
    }
    Write-Ok "Odoo terminated (PID $procId)"
    Reap-LauncherStub $procId
    Clear-StoppedState
    return 0
}

function Reap-LauncherStub([int] $serverPid) {
    # venv\Scripts\python.exe is venvlauncher.exe -- byte-identical to the base
    # interpreter's venv launcher stub -- not Python. It spawns the real
    # interpreter and waits on it, so there are always TWO processes and the
    # pidfile names the child. The stub normally exits by itself once the child
    # goes; this only cleans up if it did not.
    $stubs = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
               Where-Object { (Test-CommandLineContains $_.CommandLine $PidFile) -and $_.ProcessId -ne $serverPid })
    foreach ($stub in $stubs) {
        if (Test-ProcessAlive $stub.ProcessId) {
            Write-Note "  Reaping the venv launcher stub (PID $($stub.ProcessId))."
            Stop-Process -Id $stub.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Clear-StoppedState {
    # Odoo's atexit removes the pidfile on a clean exit but not after a force
    # kill, so tidy up rather than leaving evidence that looks like a crash.
    if (Test-Path -LiteralPath $PidFile) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    }
    Exit-StartLock
}

function Invoke-Restart {
    Write-Host "--- status ---"
    $before = Get-OdooState
    Write-Host "  $($before.State)$(if ($before.Pid) { " (PID $($before.Pid))" } else { '' })"

    if ($before.State -ne 'STOPPED') {
        Write-Host ""
        Write-Host "--- stop ---"
        # Run stop in-process but without letting it exit this script.
        $stopCode = Invoke-StopInline
        if ($stopCode -ne 0) {
            Write-Fail "Shutdown failed, so no new instance was started."
            Write-Note "  Fix the reason above and try again; starting now would risk two servers."
            exit $stopCode
        }
        $after = Get-OdooState
        if ($after.State -ne 'STOPPED') {
            Write-Fail "Odoo still reports $($after.State) after stopping. Refusing to start a second instance."
            exit 1
        }
        Write-Ok "Verified stopped"
    }

    Write-Host ""
    Write-Host "--- start ---"
    Invoke-Start
}

function Invoke-StopInline {
    # Returns an exit code instead of exiting, so restart can verify between
    # stopping and starting.
    $state = Get-OdooState

    if ($state.PidReused) {
        # The most important refusal in this script.
        Write-Fail "Refusing to stop anything: $($state.Detail)"
        Write-Note "  The pidfile is stale and its number has been reused. Killing that PID"
        Write-Note "  would terminate an unrelated process."
        Write-Note "  Suggested action: delete $(Resolve-RelativePath $PidFile) once you have"
        Write-Note "  confirmed Odoo is not running."
        return 1
    }
    if ($state.PortForeign -and $state.Pid -eq 0) {
        Write-Fail "Not stopping: $($state.Detail)"
        Write-Note "  That process was not started by this script and is not ours to kill."
        return 1
    }
    if ($state.Pid -eq 0) {
        if ($state.StalePidFile) { Remove-StalePidFile $state.Detail }
        Write-Ok "Odoo is not running."
        return 0
    }

    # Never force-kill a module install or upgrade. Those interleave DDL,
    # ir_module_module state writes and asset writes across several commits;
    # PostgreSQL protects each transaction but not the sequence, so an
    # interrupted upgrade can leave state = 'to upgrade' and a registry that
    # will not load.
    $proc = Get-ProcessInfo $state.Pid
    if (Test-IsModuleOperation $proc) {
        Write-Fail "PID $($state.Pid) is running a module install or upgrade."
        Write-Note "  Refusing to stop it: an interrupted -i/-u can leave a module stuck in"
        Write-Note "  'to upgrade' and a registry that will not load. Let it finish."
        Write-Note "  Command: $($proc.CommandLine)"
        return 1
    }

    return (Stop-OdooProcess $state.Pid)
}

# ---------------------------------------------------------------------------
# status / health / info
# ---------------------------------------------------------------------------

function Resolve-RelativePath([string] $path) {
    if ([string]::IsNullOrWhiteSpace($path)) { return '' }
    if ($path.StartsWith($Root)) {
        $relative = $path.Substring($Root.Length).TrimStart('\', '/')
        if ($relative) { return $relative }
    }
    return $path
}

function Get-GitInfo {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($null -eq $git) { return $null }
    Push-Location -LiteralPath $Root
    try {
        $branch = (& git rev-parse --abbrev-ref HEAD 2>$null)
        $commit = (& git rev-parse --short HEAD 2>$null)
        $dirty  = @(& git status --porcelain 2>$null).Count
        if ([string]::IsNullOrWhiteSpace($branch)) { return $null }
        $suffix = ' (clean)'
        if ($dirty -gt 0) { $suffix = " ($dirty uncommitted)" }
        return "$branch @ $commit$suffix"
    } catch {
        return $null
    } finally {
        Pop-Location
    }
}

function Get-OdooVersion {
    # Parsed from release.py rather than by importing Odoo: status must be fast
    # and must work even when the venv is broken.
    $releaseFile = Join-Path $Root 'odoo\release.py'
    if (-not (Test-Path -LiteralPath $releaseFile)) { return 'unknown' }
    $content = Get-Content -LiteralPath $releaseFile -Raw
    if ($content -match "version_info\s*=\s*\((\d+),\s*(\d+)") {
        return "$($Matches[1]).$($Matches[2])"
    }
    return 'unknown'
}

function Get-PythonVersion {
    if (-not (Test-Path -LiteralPath $Python)) { return 'not found' }
    try {
        $out = & $Python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null
        if ($out) { return ([string] $out).Trim() }
    } catch { }
    return 'unknown'
}

function Show-Status {
    $state = Get-OdooState
    $label = $state.State
    if ($label -eq 'RUNNING')  { Write-Ok   "Odoo is RUNNING" }
    if ($label -eq 'STOPPED')  { Write-Warn "Odoo is STOPPED" }
    if ($label -eq 'DEGRADED') { Write-Fail "Odoo is DEGRADED" }
    if ($state.Detail) { Write-Host "  $($state.Detail)" }
    Write-Host ""

    if ($state.Pid -gt 0) {
        Write-Field 'PID' $state.Pid
        $proc = Get-ProcessInfo $state.Pid
        if ($null -ne $proc -and $null -ne $proc.CreationDate) {
            $uptime = (Get-Date) - $proc.CreationDate
            Write-Field 'Uptime' ("{0}d {1}h {2}m {3}s" -f $uptime.Days, $uptime.Hours, $uptime.Minutes, $uptime.Seconds)
            Write-Field 'Started' $proc.CreationDate
        }
    }
    Write-Field 'Port'    "$(Get-HttpPort) (interface $(Get-HttpHost))"
    Write-Field 'Odoo'    (Get-OdooVersion)
    Write-Field 'Python'  "$(Get-PythonVersion)  ($(Resolve-RelativePath $Python))"
    Write-Field 'Config'  (Resolve-RelativePath $Conf)
    Write-Field 'Logs'    (Resolve-RelativePath $LogFile)
    Write-Field 'PidFile' (Resolve-RelativePath $PidFile)

    $dbName = Get-ConfValue 'db_name'
    $dbHost = Get-ConfValue 'db_host'
    $dbPort = Get-ConfInt 'db_port' 5432
    if ([string]::IsNullOrWhiteSpace($dbHost)) { $dbHost = '(local socket)' }
    Write-Field 'Database' "$dbName at $dbHost`:$dbPort"

    Write-Host 'Addons:'
    foreach ($dir in Get-AddonsDirs) {
        $marker = 'ok'
        if (-not (Test-Path -LiteralPath $dir -PathType Container)) { $marker = 'MISSING' }
        Write-Host ("  [{0}] {1}" -f $marker, $dir)
    }

    $git = Get-GitInfo
    if ($git) { Write-Field 'Git' $git }

    Write-Host ""
    if ($state.State -eq 'RUNNING') {
        $probe = Invoke-HealthProbe -WithDb
        if ($probe.Ok) { Write-Ok "Health: $($probe.Body)" } else { Write-Fail "Health: HTTP $($probe.Status) $($probe.Error)" }
    } else {
        Write-Note "Health: not probed (server is not running)"
    }

    if ($state.State -eq 'RUNNING') { exit 0 }
    exit 1
}

function Invoke-Health {
    # Exit codes are the contract for automation:
    #   0 healthy   1 unhealthy   2 configuration/dependency problem
    if (-not (Test-Prereqs)) { exit 2 }
    if (@(Get-BadConfPaths).Count -gt 0) {
        Write-Fail "Configuration references missing paths (run config-check)."
        exit 2
    }

    $state = Get-OdooState
    if ($state.PidReused)   { Write-Fail $state.Detail; exit 1 }
    if ($state.PortForeign) { Write-Fail $state.Detail; exit 1 }
    if ($state.Pid -eq 0)   { Write-Fail "No Odoo process for this project is running."; exit 1 }
    Write-Ok "Process alive (PID $($state.Pid))"

    $portPid = Get-PortOwnerPid (Get-HttpPort)
    if ($portPid -ne $state.Pid) {
        Write-Fail "Port $(Get-HttpPort) is not being served by PID $($state.Pid)."
        exit 1
    }
    Write-Ok "Listening on port $(Get-HttpPort)"

    $probe = Invoke-HealthProbe -WithDb
    if (-not $probe.Ok) {
        Write-Fail "HTTP $(Get-HealthUrl 'db_server_status=1') returned $($probe.Status) $($probe.Error)"
        if ($probe.Status -eq 500) {
            Write-Note "  500 from this endpoint means Odoo cannot reach PostgreSQL."
        }
        exit 1
    }
    Write-Ok "HTTP endpoint responding"
    if ($probe.Body -like '*"db_server_status": true*' -or $probe.Body -like '*"db_server_status":true*') {
        Write-Ok "PostgreSQL reachable (as reported by Odoo)"
    }

    # A fatal traceback during startup can coexist with a serving HTTP port.
    $fatal = @(@(Get-LogTail 200) | Where-Object { $_ -match 'CRITICAL|Failed to load registry|Traceback \(most recent call last\)' })
    if ($fatal.Count -gt 0) {
        Write-Warn "Log contains $($fatal.Count) critical line(s); run: .\run-odoo.ps1 errors"
    } else {
        Write-Ok "No fatal errors in the recent log"
    }

    Write-Host ""
    Write-Ok "Healthy"
    exit 0
}

function Show-Info {
    # Sanitized summary for pasting into a bug report. Deliberately never reads
    # db_password or admin_passwd -- see the redaction note below.
    Write-Host "Odoo 19 project summary"
    Write-Host "======================="
    Write-Field 'Root'    $Root
    Write-Field 'Odoo'    (Get-OdooVersion)
    Write-Field 'Python'  "$(Get-PythonVersion)  ($(Resolve-RelativePath $Python))"
    Write-Field 'Shell'   "PowerShell $($PSVersionTable.PSVersion) ($($PSVersionTable.PSEdition))"
    Write-Field 'OS'      "$([Environment]::OSVersion.VersionString)"
    Write-Field 'Config'  (Resolve-RelativePath $Conf)
    Write-Field 'Logs'    (Resolve-RelativePath $LogFile)
    Write-Field 'PidFile' (Resolve-RelativePath $PidFile)
    Write-Field 'DataDir' (Resolve-RelativePath (Get-ConfValue 'data_dir'))
    Write-Host ""
    Write-Host "Server"
    Write-Field '  HTTP'    "$(Get-HttpHost):$(Get-HttpPort)"
    Write-Field '  Gevent'  (Get-ConfInt 'gevent_port' 0)
    Write-Field '  Workers' (Get-ConfInt 'workers' 0)
    Write-Field '  Watchdog' "limit_time_real = $(Get-ConfInt 'limit_time_real' 120)"
    Write-Host ""
    Write-Host "Database"
    $dbHost = Get-ConfValue 'db_host'
    if ([string]::IsNullOrWhiteSpace($dbHost)) { $dbHost = '(local socket / PGHOST)' }
    Write-Field '  Host'    "$dbHost`:$(Get-ConfInt 'db_port' 5432)"
    Write-Field '  User'    (Get-ConfValue 'db_user')
    Write-Field '  Default' (Get-ConfValue 'db_name')
    Write-Field '  list_db' (Get-ConfValue 'list_db')
    $dbfilter = Get-ConfValue 'dbfilter'
    if ([string]::IsNullOrWhiteSpace($dbfilter)) { $dbfilter = '(unset -- every database is selectable)' }
    Write-Field '  dbfilter' $dbfilter
    # Passwords are never printed. `info` output is routinely pasted into
    # tickets and chat, which is exactly how credentials leak.
    Write-Note "  (db_password and admin_passwd are deliberately not shown)"
    Write-Host ""
    Write-Host "Addons"
    foreach ($dir in Get-AddonsDirs) {
        $count = 0
        if (Test-Path -LiteralPath $dir -PathType Container) {
            $count = @(Get-ChildItem -LiteralPath $dir -Directory -ErrorAction SilentlyContinue |
                       Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName '__manifest__.py') }).Count
        }
        Write-Host ("  {0,-5} modules  {1}" -f $count, $dir)
    }
    $git = Get-GitInfo
    if ($git) { Write-Host ""; Write-Field 'Git' $git }
    Write-Host ""
    $state = Get-OdooState
    Write-Field 'State' $state.State
    exit 0
}

# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------

function Show-Logs {
    if (-not (Test-Path -LiteralPath $LogFile)) {
        Write-Warn "No log file at $LogFile"
        Write-Note "  Odoo only writes one when started through this script (which passes --logfile),"
        Write-Note "  because odoo.conf leaves 'logfile' unset."
        exit 1
    }
    Get-Content -LiteralPath $LogFile -Tail $LineCount
    exit 0
}

function Show-LogsFollow {
    if (-not (Test-Path -LiteralPath $LogFile)) {
        Write-Warn "No log file at $LogFile -- start Odoo first."
        exit 1
    }
    Write-Note "Following $LogFile (Ctrl-C to stop)"
    Get-Content -LiteralPath $LogFile -Tail $LineCount -Wait
}

function Show-Errors {
    if (-not (Test-Path -LiteralPath $LogFile)) {
        Write-Warn "No log file at $LogFile"
        exit 1
    }
    # Tracebacks are multi-line, so matching lines alone loses the useful part.
    # Print a small trailing context window for each hit.
    $all = @(Get-Content -LiteralPath $LogFile)
    $pattern = 'WARNING|ERROR|CRITICAL|Traceback \(most recent call last\)'
    $hits = @()
    for ($i = 0; $i -lt $all.Count; $i++) {
        if ($all[$i] -match $pattern) { $hits += $i }
    }
    if ($hits.Count -eq 0) {
        Write-Ok "No WARNING, ERROR, CRITICAL or Traceback lines in $(Resolve-RelativePath $LogFile)"
        exit 0
    }
    $show = $hits
    if ($hits.Count -gt $LineCount) { $show = $hits[($hits.Count - $LineCount)..($hits.Count - 1)] }
    Write-Note "$($hits.Count) matching line(s); showing the last $($show.Count) with context"
    Write-Host ""
    $lastPrinted = -1
    foreach ($index in $show) {
        $from = $index
        $to   = [Math]::Min($index + 6, $all.Count - 1)
        if ($from -le $lastPrinted) { $from = $lastPrinted + 1 }
        if ($from -gt $to) { continue }
        if ($lastPrinted -ge 0 -and $from -gt $lastPrinted + 1) { Write-Host "  ..." }
        for ($j = $from; $j -le $to; $j++) {
            # Only continuation lines follow a Traceback; stop at the next
            # timestamped record so unrelated INFO noise is not pulled in.
            if ($j -gt $index -and $all[$j] -match '^\d{4}-\d{2}-\d{2} ') { break }
            Write-Host $all[$j]
            $lastPrinted = $j
        }
    }
    exit 0
}

# ---------------------------------------------------------------------------
# doctor -- read-only. It changes nothing, by design.
# ---------------------------------------------------------------------------

$script:DoctorPass = 0
$script:DoctorWarn = 0
$script:DoctorFail = 0

function Doctor-Pass([string] $m) { $script:DoctorPass++; Write-Tagged 'PASS' $m 'Green' }
function Doctor-Warn([string] $m) { $script:DoctorWarn++; Write-Tagged 'WARN' $m 'Yellow' }
function Doctor-Fail([string] $m) { $script:DoctorFail++; Write-Tagged 'FAIL' $m 'Red' }

# Odoo's floor: below this it logs "Upgrade Wkhtmltopdf" and sets state
# 'upgrade' (ir_actions_report.py:110-113).
$script:WkMinVersion = [version] '0.12.0'
# What Odoo's own wiki recommends, and what deploy/README.md requires.
$script:WkWantVersion = [version] '0.12.6'

function Find-Wkhtmltopdf {
    <#
        Locate the binary the way Odoo does, not the way a shell does.

        find_in_path() searches $PATH and then APPENDS config['bin_path']
        (odoo/tools/misc.py:142-146), so a binary already on PATH wins and
        bin_path is only a fallback. Checking PATH alone would report "not
        found" on a working portable install; checking bin_path alone would
        name the wrong binary on a system-wide one.

        Returns a hashtable @{ Path; From } or $null.
    #>
    $onPath = Get-Command wkhtmltopdf -ErrorAction SilentlyContinue
    if ($null -ne $onPath) {
        return @{ Path = $onPath.Source; From = 'PATH' }
    }
    $binPath = Get-ConfValue 'bin_path'
    if (-not [string]::IsNullOrWhiteSpace($binPath)) {
        # Odoo treats 'None' as unset (misc.py:144).
        $binPath = $binPath.Trim()
        if ($binPath -ne 'None') {
            $candidate = Join-Path $binPath 'wkhtmltopdf.exe'
            if (Test-Path -LiteralPath $candidate) {
                return @{ Path = $candidate; From = 'bin_path in odoo.conf' }
            }
        }
    }
    return $null
}

function Test-Wkhtmltopdf {
    <#
        Grade the PDF engine. Presence is not enough: an UNPATCHED Qt build
        reports state 'ok' to Odoo (is_patched_qt is read at
        ir_actions_report.py:106 but never changes the state) and then silently
        drops --header-html and --footer-html. Nothing in Odoo warns about it,
        so this is the only place it can be caught.
    #>
    $found = Find-Wkhtmltopdf
    if ($null -eq $found) {
        Doctor-Warn ("wkhtmltopdf not found on PATH or via bin_path: every PDF report degrades to " +
                     "HTML with 'Unable to find Wkhtmltopdf on this system'. See deploy/README.md section 1.")
        return
    }
    $where = "$($found.Path) (via $($found.From))"

    $out = ''
    try { $out = [string](& $found.Path --version 2>$null) } catch { $out = '' }
    if ([string]::IsNullOrWhiteSpace($out)) {
        Doctor-Fail "wkhtmltopdf at $where does not answer --version; Odoo reports state 'broken' and PDF rendering fails."
        return
    }
    $out = $out.Trim()

    # Odoo parses the first run of digits and dots (ir_actions_report.py:108),
    # so match what it matches rather than inventing a stricter pattern.
    $m = [regex]::Match($out, '[0-9]+(\.[0-9]+)+')
    $ver = $null
    if (-not ($m.Success -and [version]::TryParse($m.Value, [ref] $ver))) {
        Doctor-Fail "wkhtmltopdf at $where reports no parseable version ('$out'); Odoo reports state 'broken'."
        return
    }

    $patched = $out -match '(?i)\(with patched qt\)'
    if ($ver -lt $script:WkMinVersion) {
        Doctor-Fail ("wkhtmltopdf $ver at $where is below Odoo's minimum $($script:WkMinVersion); " +
                     "Odoo reports state 'upgrade'. See deploy/README.md section 1.")
    } elseif (-not $patched) {
        Doctor-Fail ("wkhtmltopdf $ver at $where does not report '(with patched qt)'. Odoo will still " +
                     "call it, but headers and footers are silently dropped. See deploy/README.md section 1.")
    } elseif ($ver -lt $script:WkWantVersion) {
        Doctor-Warn ("wkhtmltopdf $ver at $where is patched-Qt but below the recommended " +
                     "$($script:WkWantVersion); Odoo accepts it. See deploy/README.md section 1.")
    } else {
        Doctor-Pass "wkhtmltopdf $ver (with patched qt) at $where"
    }
}

function Test-LooksProductionLike {
    # No single setting proves it, so judge on several. Any one of these on a
    # developer machine would be unusual; together they mean "this is a server".
    $signals = @()
    if ((Get-ConfInt 'workers' 0) -gt 0)      { $signals += 'workers > 0' }
    if (Get-ConfBool 'proxy_mode')            { $signals += 'proxy_mode = True' }
    $iface = Get-ConfValue 'http_interface'
    if ($iface -and $iface.Trim() -ne '127.0.0.1' -and $iface.Trim() -ne 'localhost') { $signals += "http_interface = $iface" }
    $listDb = Get-ConfValue 'list_db'
    if ($listDb -and -not (Get-ConfBool 'list_db')) { $signals += 'list_db = False' }
    return $signals
}

function Invoke-Doctor {
    Write-Host "Odoo 19 doctor -- read-only diagnostic"
    Write-Host "======================================"
    Write-Host ""

    $prodSignals = @(Test-LooksProductionLike)
    $isProdLike  = ($prodSignals.Count -gt 0)
    if ($isProdLike) {
        Write-Warn "This host looks production-like: $($prodSignals -join ', ')"
        Write-Note "  Dev-only settings are graded FAIL rather than WARN below."
        Write-Host ""
    }

    # --- interpreter and environment -------------------------------------
    Write-Host "Python and virtual environment"
    if (Test-Path -LiteralPath $Python) {
        Doctor-Pass "Interpreter present: $(Resolve-RelativePath $Python)"
        $pyVersion = Get-PythonVersion
        # Odoo declares its own supported range; read it rather than hard-coding.
        $releaseFile = Join-Path $Root 'odoo\release.py'
        $minVersion = ''
        $maxVersion = ''
        if (Test-Path -LiteralPath $releaseFile) {
            $releaseText = Get-Content -LiteralPath $releaseFile -Raw
            if ($releaseText -match 'MIN_PY_VERSION\s*=\s*\((\d+),\s*(\d+)\)') { $minVersion = "$($Matches[1]).$($Matches[2])" }
            if ($releaseText -match 'MAX_PY_VERSION\s*=\s*\((\d+),\s*(\d+)\)') { $maxVersion = "$($Matches[1]).$($Matches[2])" }
        }
        if ($minVersion -and $maxVersion) {
            $current = [version] (($pyVersion -split '\.')[0..1] -join '.')
            if ($current -lt [version] $minVersion) {
                Doctor-Fail "Python $pyVersion is below Odoo's MIN_PY_VERSION ($minVersion)"
            } elseif ($current -gt [version] $maxVersion) {
                Doctor-Warn "Python $pyVersion is above Odoo's MAX_PY_VERSION ($maxVersion); Odoo will warn at startup"
            } else {
                Doctor-Pass "Python $pyVersion is within Odoo's declared range $minVersion-$maxVersion"
            }
        } else {
            Doctor-Warn "Python $pyVersion (could not read MIN/MAX_PY_VERSION from odoo/release.py)"
        }
        # `python -m pip`, never pip.exe: this venv's Scripts\*.exe wrappers
        # embed the interpreter path from where the venv was first created,
        # which for this tree was the old Downloads location.
        $pipOut = & $Python -m pip --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $pipOut) { Doctor-Pass "pip: $(([string]$pipOut).Trim())" }
        else { Doctor-Fail "python -m pip failed" }
    } else {
        Doctor-Fail "Interpreter missing: $Python"
    }

    # --- Odoo importability ----------------------------------------------
    Write-Host ""
    Write-Host "Odoo"
    if (Test-Path -LiteralPath (Join-Path $Root 'odoo\__main__.py')) {
        Doctor-Pass "Entry point present: odoo\__main__.py (python -m odoo)"
    } else {
        Doctor-Fail "odoo\__main__.py missing -- python -m odoo will not work"
    }
    if (Test-Path -LiteralPath $Python) {
        Push-Location -LiteralPath $Root
        try {
            $verOut = & $Python -c "import odoo.release as r; print(r.version)" 2>&1
            if ($LASTEXITCODE -eq 0) {
                Doctor-Pass "Odoo imports: version $(([string]@($verOut)[0]).Trim())"
            } else {
                Doctor-Fail "import odoo failed: $(@($verOut)[0])"
            }
        } finally { Pop-Location }
    }
    foreach ($package in @('nepali_datetime', 'psycopg2', 'lxml', 'babel')) {
        if (-not (Test-Path -LiteralPath $Python)) { break }
        $null = & $Python -c "import $package" 2>&1
        if ($LASTEXITCODE -eq 0) { Doctor-Pass "Python package present: $package" }
        else { Doctor-Fail "Python package missing: $package  (pip install -r requirements.txt)" }
    }

    # --- configuration ----------------------------------------------------
    Write-Host ""
    Write-Host "Configuration"
    if (Test-Path -LiteralPath $Conf) {
        Doctor-Pass "Config present: $(Resolve-RelativePath $Conf)"
    } else {
        Doctor-Fail "Config missing: $Conf"
    }
    $bad = @(Get-BadConfPaths)
    if ($bad.Count -eq 0) {
        Doctor-Pass "Every addons_path entry and data_dir exists"
    } else {
        foreach ($entry in $bad) { Doctor-Fail "Missing path -- $entry" }
        Write-Note "    This is audit finding OPS-1: Odoo starts anyway, with modules"
        Write-Note "    silently absent or attachments raising FileNotFoundError."
    }

    # OPS-2: the database manager is reachable with a default master password.
    $adminPw = Get-ConfValue 'admin_passwd'
    $listDbOn = Get-ConfBool 'list_db'
    $weakPasswords = @('admin', 'CHANGE_ME', 'CHANGE-ME', 'odoo', 'master', 'password')
    $isWeak = ($null -ne $adminPw) -and ($weakPasswords -contains $adminPw.Trim())
    if ($isWeak -and $listDbOn) {
        $message = "admin_passwd is a default value AND list_db is True -- the database manager is exposed (OPS-2)"
        if ($isProdLike) { Doctor-Fail $message } else { Doctor-Warn "$message. Acceptable on a dev box; must not ship." }
    } elseif ($isWeak) {
        Doctor-Warn "admin_passwd is a default value (OPS-2). list_db is False, which limits the exposure."
    } else {
        Doctor-Pass "admin_passwd is not one of the known default values"
    }

    # OPS-4: the wall-clock watchdog.
    $limitTimeReal = Get-ConfInt 'limit_time_real' 120
    if ($limitTimeReal -eq 0) {
        $message = "limit_time_real = 0 -- the runaway-request watchdog is disabled (OPS-4)"
        if ($isProdLike) {
            Doctor-Fail "$message. One tenant's infinite loop consumes a thread permanently."
        } else {
            Doctor-Warn "$message. Correct on Windows, where the watchdog's reload() is TerminateProcess. Must not ship."
        }
    } else {
        Doctor-Pass "limit_time_real = $limitTimeReal (watchdog active)"
    }

    $dbfilter = Get-ConfValue 'dbfilter'
    if ([string]::IsNullOrWhiteSpace($dbfilter)) {
        if ($isProdLike) { Doctor-Fail "dbfilter is unset: any client can select any database" }
        else { Doctor-Warn "dbfilter is unset: any client can select any database. Fine locally." }
    } else {
        Doctor-Pass "dbfilter = $dbfilter"
    }

    if ([string]::IsNullOrWhiteSpace((Get-ConfValue 'logfile'))) {
        Doctor-Warn "odoo.conf sets no logfile: Odoo logs to stderr. This script passes --logfile, so logs land in $(Resolve-RelativePath $LogFile) -- but a hand-started server's output is lost."
    } else {
        Doctor-Pass "logfile is set in odoo.conf"
    }

    # --- addons -----------------------------------------------------------
    Write-Host ""
    Write-Host "Addons"
    $dirs = @(Get-AddonsDirs)
    if ($dirs.Count -eq 0) {
        Doctor-Fail "addons_path is empty or unreadable"
    }
    foreach ($dir in $dirs) {
        if (Test-Path -LiteralPath $dir -PathType Container) {
            $count = @(Get-ChildItem -LiteralPath $dir -Directory -ErrorAction SilentlyContinue |
                       Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName '__manifest__.py') }).Count
            if ($count -gt 0) { Doctor-Pass "$count modules in $dir" }
            else { Doctor-Warn "No modules found in $dir" }
        } else {
            Doctor-Fail "addons_path entry does not exist: $dir"
        }
    }

    # --- filesystem -------------------------------------------------------
    Write-Host ""
    Write-Host "Filesystem"
    $dataDir = Get-ConfValue 'data_dir'
    if ($dataDir -and (Test-Path -LiteralPath $dataDir -PathType Container)) {
        # Writability is what matters, and it cannot be inferred from ACLs
        # alone. Probing with a temporary file is the only reliable test -- and
        # it is the one write doctor performs, immediately undone.
        $probeFile = Join-Path $dataDir ".doctor-write-probe"
        try {
            Set-Content -LiteralPath $probeFile -Value 'probe' -Encoding utf8 -ErrorAction Stop
            Remove-Item -LiteralPath $probeFile -Force -ErrorAction SilentlyContinue
            Doctor-Pass "data_dir is writable: $(Resolve-RelativePath $dataDir)"
        } catch {
            Doctor-Fail "data_dir is not writable: $dataDir"
        }
    } elseif ($dataDir) {
        Doctor-Fail "data_dir does not exist: $dataDir"
    }

    foreach ($dir in @($LogDir, $RuntimeDir)) {
        if (Test-Path -LiteralPath $dir) { Doctor-Pass "Directory present: $(Resolve-RelativePath $dir)" }
        else { Doctor-Warn "Directory absent (created on first start): $(Resolve-RelativePath $dir)" }
    }

    if (Test-Path -LiteralPath $LogFile) {
        $sizeMB = [math]::Round((Get-Item -LiteralPath $LogFile).Length / 1MB, 1)
        if ($sizeMB -ge $LogMaxMB) { Doctor-Warn "Log is ${sizeMB} MB; it will be rotated on the next start (threshold ${LogMaxMB} MB)" }
        else { Doctor-Pass "Log size ${sizeMB} MB (rotates at ${LogMaxMB} MB, keeping $LogKeep)" }
    }

    try {
        $drive = Get-PSDrive -Name (Split-Path -Qualifier $Root).TrimEnd(':') -ErrorAction Stop
        $freeGB = [math]::Round($drive.Free / 1GB, 1)
        if ($freeGB -lt 2) { Doctor-Fail "Only ${freeGB} GB free on $($drive.Name): -- PostgreSQL and the filestore need headroom" }
        elseif ($freeGB -lt 10) { Doctor-Warn "${freeGB} GB free on $($drive.Name):" }
        else { Doctor-Pass "${freeGB} GB free on $($drive.Name):" }
    } catch {
        Doctor-Warn "Could not determine free disk space"
    }

    # --- PostgreSQL -------------------------------------------------------
    Write-Host ""
    Write-Host "PostgreSQL"
    $psql = Find-Psql
    if ($psql) {
        $psqlVersion = & $psql --version 2>$null
        Doctor-Pass "Client: $(Resolve-RelativePath $psql) ($(([string]$psqlVersion).Trim()))"
    } else {
        Doctor-Warn "No psql client found; db-list will not work. Odoo itself does not need it."
    }
    $dbPort = Get-ConfInt 'db_port' 5432
    if (Test-PostgresReachable) {
        Doctor-Pass "TCP connect succeeds on $(Get-ConfValue 'db_host'):$dbPort"
        # Two clusters on one machine is a real trap here: 5432 and 5433 are
        # different major versions, and hitting the wrong one looks like an
        # empty database rather than an error.
        # Version-numbered directories only: siblings like psqlODBC are drivers,
        # not clusters, and counting them makes the warning look wrong.
        $installs = @(Get-ChildItem "$env:ProgramFiles\PostgreSQL" -Directory -ErrorAction SilentlyContinue |
                      Where-Object { $_.Name -match '^\d+$' })
        if ($installs.Count -gt 1) {
            Doctor-Warn "$($installs.Count) PostgreSQL versions installed ($(($installs | Select-Object -ExpandProperty Name) -join ', ')). odoo.conf uses port $dbPort -- confirm that is the intended cluster, because a wrong port looks like an empty database rather than an error."
        }
    } else {
        Doctor-Fail "Cannot reach PostgreSQL at $(Get-ConfValue 'db_host'):$dbPort"
    }

    # --- tooling ----------------------------------------------------------
    Write-Host ""
    Write-Host "Optional tooling"
    foreach ($tool in @('git', 'node', 'npm')) {
        $found = Get-Command $tool -ErrorAction SilentlyContinue
        if ($null -ne $found) { Doctor-Pass "$tool present: $($found.Source)" }
        else { Doctor-Warn "$tool not on PATH" }
    }
    Test-Wkhtmltopdf
    $chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
                "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe") |
              Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($chrome) { Doctor-Pass "Chrome present (needed by the JavaScript test suite)" }
    else { Doctor-Warn "Chrome not found; JS tests (tests/test_js_unit.py) will fail" }

    # --- runtime state ----------------------------------------------------
    Write-Host ""
    Write-Host "Runtime state"
    $state = Get-OdooState
    if ($state.PidReused) {
        Doctor-Fail "Stale pidfile whose PID has been reused by '$((Get-ProcessInfo (Get-PidFilePid)).Name)'. stop would refuse; delete $(Resolve-RelativePath $PidFile)."
    } elseif ($state.StalePidFile) {
        Doctor-Warn "Stale pidfile: $($state.Detail). Removed automatically on the next start."
    } elseif (Test-Path -LiteralPath $PidFile) {
        Doctor-Pass "Pidfile is valid (PID $($state.Pid))"
    } else {
        Doctor-Pass "No pidfile (server not started through this script)"
    }
    if (Test-Path -LiteralPath $LockDir) {
        Doctor-Warn "Start lock present: $(Resolve-RelativePath $LockDir). A start may be in progress, or it was abandoned."
    }

    $httpPort = Get-HttpPort
    $owner = Get-PortOwnerPid $httpPort
    if ($owner -eq 0) {
        Doctor-Pass "Port $httpPort is free"
    } elseif ($owner -eq $state.Pid) {
        Doctor-Pass "Port $httpPort is served by this project's Odoo (PID $owner)"
    } else {
        $ownerProc = Get-ProcessInfo $owner
        $ownerName = 'unknown'
        if ($null -ne $ownerProc) { $ownerName = $ownerProc.Name }
        Doctor-Fail "Port $httpPort is held by PID $owner ($ownerName), which is not this project's Odoo"
    }

    # --- git --------------------------------------------------------------
    Write-Host ""
    Write-Host "Repository"
    $git = Get-GitInfo
    if ($git) {
        Doctor-Pass "Git: $git"
        Push-Location -LiteralPath $Root
        try {
            $remotes = @(& git remote 2>$null)
            if ($remotes.Count -eq 0) {
                Doctor-Warn "No git remote configured -- commits exist only on this disk (audit finding SUP-2)"
            } else {
                Doctor-Pass "Git remote(s): $($remotes -join ', ')"
            }
            $dirty = @(& git status --porcelain 2>$null)
            if ($dirty.Count -gt 0) { Doctor-Warn "$($dirty.Count) uncommitted change(s)" }
            else { Doctor-Pass "Working tree clean" }
        } finally { Pop-Location }
    } else {
        Doctor-Warn "Not a git repository, or git is unavailable"
    }

    # --- summary ----------------------------------------------------------
    Write-Host ""
    Write-Host "Summary"
    Write-Host "-------"
    Write-Host "  PASS $script:DoctorPass   WARN $script:DoctorWarn   FAIL $script:DoctorFail"
    Write-Host ""
    if ($script:DoctorFail -gt 0) {
        Write-Fail "$script:DoctorFail check(s) failed."
        exit 2
    }
    if ($script:DoctorWarn -gt 0) {
        Write-Ok "No failures. $script:DoctorWarn warning(s) -- review them, they are not necessarily problems here."
        exit 0
    }
    Write-Ok "All checks passed."
    exit 0
}

# ---------------------------------------------------------------------------
# config-check / addons-check / db-list / clean
# ---------------------------------------------------------------------------

function Invoke-ConfigCheck {
    if (-not (Test-Path -LiteralPath $Conf)) {
        Write-Fail "$Conf not found"
        exit 2
    }
    Write-Ok "Config readable: $(Resolve-RelativePath $Conf)"
    $bad = @(Get-BadConfPaths)
    if ($bad.Count -gt 0) {
        Write-Fail "$Conf references paths that do not exist:"
        foreach ($entry in $bad) { Write-Host "  $entry" }
        Write-Host ""
        Write-Note "Odoo would start anyway -- with those modules missing, or raising"
        Write-Note "FileNotFoundError per attachment. Fix odoo.conf before starting."
        exit 2
    }
    Write-Ok "Every addons_path entry and data_dir exists"

    # Let Odoo parse its own config: this catches syntax and value errors that
    # a regex reader cannot, and it is the same code path the server uses.
    if (Test-Path -LiteralPath $Python) {
        Push-Location -LiteralPath $Root
        try {
            $output = & $Python -c "from odoo.tools import config; config.parse_config(['-c', r'$Conf']); print('parsed')" 2>&1
            if ($LASTEXITCODE -eq 0) { Write-Ok "Odoo parses the config without error" }
            else {
                Write-Fail "Odoo rejected the config:"
                @($output) | ForEach-Object { Write-Host "  $_" }
                exit 2
            }
        } finally { Pop-Location }
    }
    Write-Host ""
    Write-Field 'HTTP'     "$(Get-HttpHost):$(Get-HttpPort)"
    Write-Field 'Database' (Get-ConfValue 'db_name')
    Write-Field 'DataDir'  (Get-ConfValue 'data_dir')
    exit 0
}

function Invoke-AddonsCheck {
    $dirs = @(Get-AddonsDirs)
    if ($dirs.Count -eq 0) { Write-Fail "addons_path is empty"; exit 2 }
    $failed = $false
    foreach ($dir in $dirs) {
        if (-not (Test-Path -LiteralPath $dir -PathType Container)) {
            Write-Fail "Missing: $dir"
            $failed = $true
            continue
        }
        $modules = @(Get-ChildItem -LiteralPath $dir -Directory -ErrorAction SilentlyContinue |
                     Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName '__manifest__.py') } |
                     Select-Object -ExpandProperty Name | Sort-Object)
        Write-Ok "$($modules.Count) modules in $dir"
        # List only the project's own modules; 685 stock names are noise.
        if ($modules.Count -le 40) {
            foreach ($m in $modules) { Write-Host "    $m" }
        } else {
            Write-Note "    (listing suppressed: $($modules.Count) modules)"
        }
    }
    if ($failed) { exit 2 }
    exit 0
}

function Find-Psql {
    $override = [Environment]::GetEnvironmentVariable('ODOO_PSQL')
    if (-not [string]::IsNullOrWhiteSpace($override)) {
        if (Test-Path -LiteralPath $override) { return $override }
        return $null
    }
    $onPath = Get-Command psql -ErrorAction SilentlyContinue
    if ($null -ne $onPath) { return $onPath.Source }
    # Newest first. Some installations here have a bin\ with no psql.exe at
    # all, so test for the file rather than the directory.
    $candidates = @(Get-ChildItem "$env:ProgramFiles\PostgreSQL" -Directory -ErrorAction SilentlyContinue |
                    Sort-Object { [int]($_.Name -replace '\D', '0') } -Descending)
    foreach ($dir in $candidates) {
        $candidate = Join-Path $dir.FullName 'bin\psql.exe'
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

function Invoke-DbList {
    # Read-only, and deliberately not routed through Odoo's database manager:
    # /web/database/* exists to create, duplicate, drop and restore, and this
    # command must not be able to do any of that even by accident.
    $psql = Find-Psql
    if ($null -eq $psql) {
        Write-Fail "No psql client found."
        Write-Note "  Set ODOO_PSQL to its full path, or add it to PATH."
        exit 2
    }
    $dbHost = Get-ConfValue 'db_host'
    if ([string]::IsNullOrWhiteSpace($dbHost) -or $dbHost.Trim() -eq 'False') { $dbHost = 'localhost' }
    $dbPort = Get-ConfInt 'db_port' 5432
    $dbUser = Get-ConfValue 'db_user'
    $password = Get-ConfValue 'db_password'

    Write-Note "Databases visible to '$dbUser' at $dbHost`:$dbPort (read-only)"
    Write-Host ""
    # PGPASSWORD in the child environment, never on the command line, where it
    # would be visible in the process list to every user on the machine.
    $previous = [Environment]::GetEnvironmentVariable('PGPASSWORD')
    if ($password) { [Environment]::SetEnvironmentVariable('PGPASSWORD', $password) }
    try {
        $query = @"
SELECT d.datname, pg_size_pretty(pg_database_size(d.datname)),
       (SELECT count(*) FROM pg_stat_activity a WHERE a.datname = d.datname)
  FROM pg_database d
 WHERE NOT d.datistemplate AND d.datallowconn
 ORDER BY d.datname
"@
        $rows = & $psql -h $dbHost.Trim() -p $dbPort -U $dbUser -d postgres -Atc $query -P pager=off
        $code = $LASTEXITCODE
    } finally {
        [Environment]::SetEnvironmentVariable('PGPASSWORD', $previous)
    }
    if ($code -ne 0) {
        Write-Fail "psql exited with code $code"
        exit 1
    }
    Write-Host ("{0,-28} {1,10} {2,12}" -f 'DATABASE', 'SIZE', 'CONNECTIONS')
    foreach ($row in @($rows)) {
        if ([string]::IsNullOrWhiteSpace($row)) { continue }
        $parts = $row -split '\|'
        Write-Host ("{0,-28} {1,10} {2,12}" -f $parts[0], $parts[1], $parts[2])
    }
    Write-Host ""
    $dbfilter = Get-ConfValue 'dbfilter'
    if ([string]::IsNullOrWhiteSpace($dbfilter)) {
        Write-Warn "dbfilter is unset, so Odoo will serve any of these to any client."
    } else {
        Write-Note "dbfilter = $dbfilter (Odoo only serves databases matching this)"
    }
    Write-Note "This command cannot create, drop or restore a database. That is deliberate."
    exit 0
}

function Invoke-Clean {
    # Scope is deliberately narrow: build artefacts and rotated logs only.
    # Nothing here touches .odoo_data, the filestore, sessions or a database.
    Write-Note "Removing __pycache__, *.pyc and rotated logs. Nothing else."
    $state = Get-OdooState
    if ($state.State -eq 'RUNNING') {
        Write-Warn "Odoo is running; removing __pycache__ under it is safe but pointless until restart."
    }
    $removed = 0
    foreach ($dir in Get-AddonsDirs) {
        if (-not (Test-Path -LiteralPath $dir)) { continue }
        # Only inside addons_path, so a mistyped config cannot widen the sweep.
        $caches = @(Get-ChildItem -LiteralPath $dir -Directory -Recurse -Filter '__pycache__' -ErrorAction SilentlyContinue)
        foreach ($cache in $caches) {
            Remove-Item -LiteralPath $cache.FullName -Recurse -Force -ErrorAction SilentlyContinue
            $removed++
        }
    }
    Write-Ok "Removed $removed __pycache__ director$(if ($removed -eq 1) { 'y' } else { 'ies' })"

    $rotated = @(Get-ChildItem -LiteralPath $LogDir -Filter 'odoo.log.*' -ErrorAction SilentlyContinue)
    foreach ($file in $rotated) { Remove-Item -LiteralPath $file.FullName -Force -ErrorAction SilentlyContinue }
    Write-Ok "Removed $($rotated.Count) rotated log file(s)"
    Write-Note "Left untouched: $(Resolve-RelativePath (Get-ConfValue 'data_dir')), the current log, and every database."
    exit 0
}

# ---------------------------------------------------------------------------
# module operations and tests -- all require an explicit database
# ---------------------------------------------------------------------------

function Get-CustomModules {
    # The project's own modules: everything in an addons_path entry that is not
    # the stock odoo\addons tree.
    $stock = (Join-Path $Root 'odoo\addons')
    $names = @()
    foreach ($dir in Get-AddonsDirs) {
        if ($dir -eq $stock) { continue }
        if (-not (Test-Path -LiteralPath $dir -PathType Container)) { continue }
        $names += @(Get-ChildItem -LiteralPath $dir -Directory -ErrorAction SilentlyContinue |
                    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName '__manifest__.py') } |
                    Select-Object -ExpandProperty Name)
    }
    return ($names | Sort-Object -Unique)
}

function Assert-ServerStopped([string] $operation) {
    # -i, -u and --test-enable all take an exclusive lock on the registry, so
    # they fail confusingly against a live server. Say so up front.
    $state = Get-OdooState
    if ($state.State -ne 'STOPPED') {
        Write-Fail "Odoo is $($state.State) (PID $($state.Pid)). $operation needs the server stopped."
        Write-Note "  Suggested action: .\run-odoo.ps1 stop"
        exit 1
    }
}

function Invoke-ModuleOperation([string] $flag, [string] $module, [string] $database, [string] $verb) {
    if (-not (Test-Prereqs)) { exit 2 }
    Assert-ConfPaths
    $module   = Assert-Module $module
    $database = Assert-Db $database $verb
    Assert-ServerStopped $verb

    Write-Warn "$verb '$module' in database '$database'. This modifies that database."
    $odooArgs = (Get-BaseArgs) + @('-d', $database, $flag, $module, '--stop-after-init')
    # Cheap self-check. An earlier version of this line read `Get-BaseArgs + @(...)`,
    # which PowerShell parses as CALLING Get-BaseArgs with '+' as an argument --
    # so the flags vanished and this silently started a plain server against the
    # named database instead of upgrading anything.
    Assert-ArgvContains $odooArgs @($flag, $module, '-d', $database, '--stop-after-init')
    # No --pidfile here: setup_pid_file() runs even with --stop-after-init, so
    # passing it would clobber a running server's pidfile.
    $code = Invoke-Odoo $odooArgs "$verb $module"
    if ($code -eq 0) { Write-Ok "$verb complete: $module in $database" }
    exit $code
}

function Invoke-Test([string] $module, [string] $database) {
    if (-not (Test-Prereqs)) { exit 2 }
    Assert-ConfPaths

    $modules = @()
    if ([string]::IsNullOrWhiteSpace($module)) {
        $modules = @(Get-CustomModules)
        if ($modules.Count -eq 0) { Write-Fail "No custom modules found to test."; exit 2 }
    } else {
        $modules = @((Assert-Module $module))
    }
    $database = Assert-Db $database 'test'
    Assert-ServerStopped 'test'

    # -u is what makes post_install tests run for these modules; --test-tags
    # scopes the run to them. Both are needed: --test-enable alone would run
    # nothing for modules that are already up to date.
    $tags = ($modules | ForEach-Object { "/$_" }) -join ','
    $odooArgs = (Get-BaseArgs) + @('-d', $database, '-u', ($modules -join ','),
                                   '--test-enable', '--test-tags', $tags, '--stop-after-init')

    Assert-ArgvContains $odooArgs @('-u', '--test-enable', '--test-tags', '-d', $database, '--stop-after-init')
    Write-Warn "Testing $($modules.Count) module(s) in database '$database'. -u modifies that database."
    Write-Note "  Modules: $($modules -join ', ')"
    $code = Invoke-Odoo $odooArgs 'test run'
    Write-Host ""
    if ($code -eq 0) {
        Write-Ok "Tests passed"
    } else {
        # Never soften this: a non-zero code here means failing tests.
        Write-Fail "Tests FAILED (exit $code). Odoo's exit code is propagated unchanged."
        Write-Note "  Detail: .\run-odoo.ps1 errors"
    }
    exit $code
}

# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------

function Show-Help {
    Write-Host @"
Odoo 19 service management (Windows)

USAGE
  .\run-odoo.ps1 <command> [target] [options]

SERVICE
  start                 Start in the background and wait until healthy
  stop                  Graceful stop, then force after -Timeout seconds
  restart               status -> stop -> verify stopped -> start -> health
  status                RUNNING / STOPPED / DEGRADED, with operational detail
  health                Real probes. Exit 0 healthy, 1 unhealthy, 2 misconfigured

LOGS
  logs                  Last -n lines (default $LineCount)
  logs-follow           Stream the log until Ctrl-C
  errors                Recent WARNING/ERROR/CRITICAL/Traceback, with context

DIAGNOSTICS
  doctor                Comprehensive read-only check. Changes nothing
  info                  Sanitized runtime summary for a bug report
  config-check          Validate odoo.conf, including Odoo's own parser
  addons-check          List and validate every addons_path entry
  version               Odoo, Python and PowerShell versions

DEVELOPMENT
  dev                   Foreground with --dev reload,qweb,xml
  shell                 Odoo shell with 'env' bound
  clean                 Remove __pycache__, *.pyc and rotated logs only

DATABASE (each requires -Db; there is no default)
  db-list               Read-only list of databases. Cannot create or drop
  install <module>      Install a module          -Db <database>
  upgrade <module>      Upgrade a module          -Db <database>
  test                  Test every custom module  -Db <database>
  test-module <module>  Test one module           -Db <database>

OPTIONS
  -Db <name>            Target database. Required by install/upgrade/test
  -n, -Lines <count>    Lines for logs/errors (default $LineCount)
  -Foreground           start/dev: attach to this console instead of detaching
  -Timeout <seconds>    Override the start ($StartTimeout s) and stop ($StopTimeout s) waits
  -NoColor              Disable colour (also honours the NO_COLOR variable)
  -h, -Help             This text

DATABASE SAFETY
  * install, upgrade, test and test-module refuse to run without -Db.
    There is deliberately no default and no "all databases" mode: this project
    is heading for database-per-tenant, where an implicit target is a data-loss
    bug rather than a convenience.
  * db-list is read-only and does not use Odoo's database manager.
  * No command creates, drops, duplicates or restores a database.
  * clean touches only __pycache__ and rotated logs -- never data_dir, the
    filestore, or a database.
  * A process is only ever signalled after its command line is verified to
    belong to this project. A stale pidfile whose PID has been reused is
    reported and refused, never killed.

EXIT CODES
  0   Success, or healthy
  1   Operational failure -- unhealthy, not running, stop failed
  2   Usage, configuration or dependency problem
      install/upgrade/test/dev/shell return Odoo's own exit code unchanged, so a
      failing test suite is never masked. On Windows, -1 (4294967295) is the
      limit_time_real watchdog, not a crash.

ENVIRONMENT OVERRIDES
  ODOO_CONF             Config file          (default: odoo.conf)
  ODOO_PYTHON           Interpreter          (default: venv\Scripts\python.exe)
  ODOO_LOG              Log file             (default: logs\odoo.log)
  ODOO_PIDFILE          Pid file             (default: .runtime\odoo.pid)
  ODOO_HTTP_PORT        Port to probe        (default: http_port from odoo.conf)
  ODOO_START_TIMEOUT    Start wait, seconds  (default: 90)
  ODOO_STOP_TIMEOUT     Stop wait, seconds   (default: 30)
  ODOO_LOG_MAX_MB       Rotate above this    (default: 20)
  ODOO_LOG_KEEP         Generations to keep  (default: 5)
  ODOO_PSQL             psql path            (default: discovered)
  NO_COLOR              Any value disables colour

DEPRECATED
  -Install <module>     Use: install <module> -Db <database>
  -Update <module>      Use: upgrade <module> -Db <database>
  -Shell                Use: shell
  -Dev                  Use: dev
  These still work but now require -Db where they modify a database.

EXAMPLES
  .\run-odoo.ps1 start
  .\run-odoo.ps1 status
  .\run-odoo.ps1 logs-follow -n 100
  .\run-odoo.ps1 doctor
  .\run-odoo.ps1 upgrade l10n_np_accounting -Db odoo19
  .\run-odoo.ps1 test -Db odoo19

THIS IS NOT A SERVICE MANAGER
  A background process started here has no supervision, no restart on crash and
  no boot integration. On Linux the service is systemd (deploy/odoo.service).
  See docs\operations\ODOO_SERVICE_MANAGEMENT.md.
"@
}

function Show-Version {
    Write-Field 'Odoo'       (Get-OdooVersion)
    Write-Field 'Python'     (Get-PythonVersion)
    Write-Field 'PowerShell' "$($PSVersionTable.PSVersion) ($($PSVersionTable.PSEdition))"
    $git = Get-GitInfo
    if ($git) { Write-Field 'Git' $git }
    exit 0
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

# Deprecated flag forms, mapped onto the verbs. Kept working because
# deploy/README.md documents them and they are in people's shell history.
if ($Help) { Show-Help; exit 0 }
if ($Install) {
    Write-Warn "-Install is deprecated; use: .\run-odoo.ps1 install $Install -Db <database>"
    Invoke-ModuleOperation '-i' $Install $Db 'install'
}
if ($Update) {
    Write-Warn "-Update is deprecated; use: .\run-odoo.ps1 upgrade $Update -Db <database>"
    Invoke-ModuleOperation '-u' $Update $Db 'upgrade'
}
if ($Shell -and [string]::IsNullOrWhiteSpace($Command)) {
    Write-Warn "-Shell is deprecated; use: .\run-odoo.ps1 shell"
    $Command = 'shell'
}
if ($Dev -and [string]::IsNullOrWhiteSpace($Command)) {
    Write-Warn "-Dev is deprecated; use: .\run-odoo.ps1 dev"
    $Command = 'dev'
}

if ([string]::IsNullOrWhiteSpace($Command)) {
    # Bare invocation used to start the server in the foreground. Requiring an
    # explicit verb is worth the small friction: 'start' now detaches, and
    # silently changing what a bare call does would be worse than a prompt.
    Write-Warn "No command given."
    Write-Note "  A bare .\run-odoo.ps1 used to start the server in the foreground."
    Write-Note "  Now: 'start' (background) or 'dev' / 'start -Foreground' (attached)."
    Write-Host ""
    Show-Help
    exit 2
}

switch ($Command.ToLower()) {
    'start'         { Invoke-Start }
    'stop'          { Invoke-Stop }
    'restart'       { Invoke-Restart }
    'status'        { Show-Status }
    'health'        { Invoke-Health }
    'logs'          { Show-Logs }
    'logs-follow'   { Show-LogsFollow }
    'tail'          { Show-LogsFollow }
    'errors'        { Show-Errors }
    'info'          { Show-Info }
    'doctor'        { Invoke-Doctor }
    'config-check'  { Invoke-ConfigCheck }
    'addons-check'  { Invoke-AddonsCheck }
    'db-list'       { Invoke-DbList }
    'clean'         { Invoke-Clean }
    'version'       { Show-Version }
    'help'          { Show-Help; exit 0 }
    'dev' {
        # Always foreground on Windows, and not negotiable.
        #
        # --dev reload restarts by calling _reexec() (odoo/service/server.py:1526),
        # and on Windows the CRT's execve spawns a NEW process and _exits the old
        # one: the PID changes, atexit is skipped, and the pidfile is rewritten by
        # the replacement. A detached dev server would therefore churn PIDs behind
        # this script's back and race itself for the port on every file save.
        # On POSIX os.execve preserves the PID, which is why run-odoo.sh can
        # detach it -- a legitimate divergence, not an inconsistency.
        if ($Foreground) { } else {
            Write-Note "dev runs in the foreground on Windows: --dev reload re-execs with a new"
            Write-Note "PID, which a detached supervisor cannot track. Ctrl-C to stop."
        }
        $script:Foreground = $true
        Invoke-Start -DevMode
    }
    'shell' {
        if (-not (Test-Prereqs)) { exit 2 }
        Assert-ConfPaths
        # The shell attaches to a database, so it takes -Db when given, but it
        # is read-write by nature and not required to name one: odoo.conf's
        # db_name applies, exactly as it does for an interactive session today.
        $odooArgs = @('-m', 'odoo', 'shell', '-c', $Conf)
        if ($Db) { $odooArgs += @('-d', (Assert-Db $Db 'shell')) }
        exit (Invoke-Odoo $odooArgs 'shell')
    }
    'install'       { Invoke-ModuleOperation '-i' $Target $Db 'install' }
    'upgrade'       { Invoke-ModuleOperation '-u' $Target $Db 'upgrade' }
    'update'        { Invoke-ModuleOperation '-u' $Target $Db 'upgrade' }
    'test'          { Invoke-Test '' $Db }
    'test-module'   { Invoke-Test $Target $Db }
    default {
        Write-Fail "Unknown command: $Command"
        Write-Host ""
        Show-Help
        exit 2
    }
}
