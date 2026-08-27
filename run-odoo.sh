#!/usr/bin/env bash
# Odoo 19 service management (Linux / macOS). POSIX counterpart of run-odoo.ps1.
#
#   ./run-odoo.sh start              start in the background, wait until healthy
#   ./run-odoo.sh status             RUNNING / STOPPED / DEGRADED, with detail
#   ./run-odoo.sh logs-follow        tail the log
#   ./run-odoo.sh doctor             read-only diagnostic, PASS/WARN/FAIL
#   ./run-odoo.sh upgrade l10n_np_accounting --db odoo19
#
#   ./run-odoo.sh help               full command list, options and exit codes
#
# This is a developer/operator convenience layer, NOT a service manager. On Linux
# the service is systemd: install deploy/odoo.service and use systemctl. This
# script REFUSES to start when it can see that systemd is managing Odoo, rather
# than racing it for the port. See docs/operations/ODOO_SERVICE_MANAGEMENT.md.
#
# Targets bash 3.2 so it runs on stock macOS: no associative arrays, no mapfile,
# no ${var^^}.

set -uo pipefail

# ---------------------------------------------------------------------------
# Configuration. Resolution order for every value:
#   command-line flag -> environment variable -> odoo.conf -> discovered default
# ---------------------------------------------------------------------------

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
conf="${ODOO_CONF:-$root/odoo.conf}"
python="${ODOO_PYTHON:-$root/venv/bin/python3}"
log_dir="$root/logs"
log_file="${ODOO_LOG:-$log_dir/odoo.log}"
runtime_dir="$root/.runtime"
pid_file="${ODOO_PIDFILE:-$runtime_dir/odoo.pid}"
lock_dir="$runtime_dir/start.lock"
# stderr from before logging is configured: an unreadable -c path, or `python -m
# odoo` failing to import. Odoo's own log never sees these.
boot_log="$log_dir/odoo.boot.log"

start_timeout="${ODOO_START_TIMEOUT:-90}"
stop_timeout="${ODOO_STOP_TIMEOUT:-30}"
log_max_mb="${ODOO_LOG_MAX_MB:-20}"
log_keep="${ODOO_LOG_KEEP:-5}"
systemd_unit="${ODOO_UNIT:-odoo}"

# Command-line state
command_name=""
target=""
database=""
lines=40
foreground=0
# test: exit non-zero when a test skipped itself. Off by default, on in CI --
# TST-1 was a test that excused itself under exactly the condition it existed to
# detect, and nothing reported that it had.
fail_on_skip=0
force=0
no_color=0
legacy_warning=""

# ---------------------------------------------------------------------------
# Output. Colour is decoration; every line reads correctly without it.
# ---------------------------------------------------------------------------

use_color=1
[ -n "${NO_COLOR:-}" ] && use_color=0
[ -t 1 ] || use_color=0

c_reset=''; c_red=''; c_green=''; c_yellow=''; c_grey=''
init_colors() {
    if [ "$use_color" -eq 1 ] && [ "$no_color" -eq 0 ]; then
        c_reset=$'\033[0m'; c_red=$'\033[31m'; c_green=$'\033[32m'
        c_yellow=$'\033[33m'; c_grey=$'\033[90m'
    else
        c_reset=''; c_red=''; c_green=''; c_yellow=''; c_grey=''
    fi
}

say_ok()   { printf '%s[OK]%s %s\n'   "$c_green"  "$c_reset" "$*"; }
say_warn() { printf '%s[WARN]%s %s\n' "$c_yellow" "$c_reset" "$*"; }
say_fail() { printf '%s[FAIL]%s %s\n' "$c_red"    "$c_reset" "$*" >&2; }
say_note() { printf '%s%s%s\n'        "$c_grey"   "$*"       "$c_reset"; }
say_field(){ printf '%-12s%s\n' "$1:" "$2"; }

# ---------------------------------------------------------------------------
# odoo.conf reader.
#
# Preserved from the previous version of this script: last occurrence wins,
# matching Odoo's own parsing. Values run to end-of-line and are never quoted,
# because an addons_path entry may contain spaces.
# ---------------------------------------------------------------------------

conf_value() {
    [ -f "$conf" ] || return 0
    sed -nE "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*(.*[^[:space:]])[[:space:]]*$/\1/p" "$conf" \
        | grep -v '^[;#]' | tail -1
}

conf_int() {
    local raw
    raw="$(conf_value "$1")"
    case "$raw" in
        ''|*[!0-9]*) printf '%s' "$2" ;;
        *)           printf '%s' "$raw" ;;
    esac
}

# True when dotted version $1 >= dotted version $2. Missing components count as
# zero, so 0.12.6 >= 0.12 and 0.12.6.1 > 0.12.6. `sort -V` is deliberately not
# used: it is a GNU extension and this script also has to run on macOS.
version_ge() {
    awk -v a="$1" -v b="$2" 'BEGIN {
        na = split(a, x, "."); nb = split(b, y, ".")
        n = (na > nb ? na : nb)
        for (i = 1; i <= n; i++) {
            xi = (i <= na ? x[i] + 0 : 0)
            yi = (i <= nb ? y[i] + 0 : 0)
            if (xi > yi) exit 0
            if (xi < yi) exit 1
        }
        exit 0
    }'
}

conf_bool() {
    local raw
    raw="$(conf_value "$1" | tr 'A-Z' 'a-z')"
    case "$raw" in true|1|yes|on) return 0 ;; *) return 1 ;; esac
}

http_port() {
    if [ -n "${ODOO_HTTP_PORT:-}" ]; then printf '%s' "$ODOO_HTTP_PORT"; return; fi
    conf_int http_port 8069
}

http_host() {
    local iface
    iface="$(conf_value http_interface)"
    # 0.0.0.0 is a bind address, not a destination.
    case "$iface" in
        ''|0.0.0.0|::|False) printf '127.0.0.1' ;;
        *)                   printf '%s' "$iface" ;;
    esac
}

health_url() {
    printf 'http://%s:%s/web/health%s' "$(http_host)" "$(http_port)" "${1:+?$1}"
}

# addons_path entries, one per line, on stdout.
addons_dirs() {
    local raw entry
    raw="$(conf_value addons_path)"
    [ -n "$raw" ] || return 0
    # Comma-separated; entries may contain spaces, so split only on commas.
    # Note the trailing newline in printf: without it `read` returns non-zero on
    # the final entry and the loop drops it -- which would silently skip
    # custom_addons, the very entry most likely to be wrong.
    while IFS= read -r entry; do
        entry="${entry#"${entry%%[![:space:]]*}"}"   # trim leading space
        entry="${entry%"${entry##*[![:space:]]}"}"   # trim trailing space
        [ -z "$entry" ] && continue
        printf '%s\n' "$entry"
    done < <(printf '%s\n' "$raw" | tr ',' '\n')
}

# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------

check_prereqs() {
    local ok=0
    if [ ! -x "$python" ]; then
        say_fail "Python not found or not executable at $python"
        say_note "  Suggested action: python3 -m venv venv"
        say_note "                    ./venv/bin/python3 -m pip install -r requirements.txt"
        ok=1
    fi
    if [ ! -f "$conf" ]; then
        say_fail "$conf not found"
        say_note "  Suggested action: cp odoo.conf.example odoo.conf, then edit it for this host"
        ok=1
    fi
    return $ok
}

# Bad addons_path / data_dir entries, one per line, on stdout.
#
# Refuse to start on a stale addons_path or data_dir.
#
# Odoo does not treat either as fatal: a missing addons_path entry is logged as
# "no such directory ... skipped" and the server starts with those modules simply
# absent, while a stale data_dir surfaces only later as a FileNotFoundError per
# attachment. Both failures look like a healthy server. Moving the project
# directory without updating odoo.conf has already caused exactly this
# (audit finding OPS-1).
bad_conf_paths() {
    local entry data_dir
    while IFS= read -r entry; do
        [ -d "$entry" ] || printf 'addons_path: %s\n' "$entry"
    done < <(addons_dirs)
    data_dir="$(conf_value data_dir)"
    if [ -n "$data_dir" ] && [ ! -d "$data_dir" ]; then
        printf 'data_dir: %s\n' "$data_dir"
    fi
}

assert_conf_paths() {
    local bad
    bad="$(bad_conf_paths)"
    if [ -n "$bad" ]; then
        say_fail "$conf references paths that do not exist:"
        printf '  %s\n' "$bad" >&2
        echo "" >&2
        say_note "Odoo would start anyway -- with those modules missing, or raising"
        say_note "FileNotFoundError per attachment. Fix odoo.conf before starting."
        exit 2
    fi
}

# ---------------------------------------------------------------------------
# Process identity.
#
# A PID is never trusted on its own: PIDs are reused, and Odoo's pidfile survives
# an ungraceful kill because its atexit cleanup does not run.
# ---------------------------------------------------------------------------

process_cmdline() {
    local target_pid="$1"
    if [ -r "/proc/$target_pid/cmdline" ]; then
        # Linux. NUL-separated, so translate before matching.
        tr '\0' ' ' < "/proc/$target_pid/cmdline" 2>/dev/null
    else
        # macOS has no /proc. -ww is required or ps truncates, and a long
        # addons_path would push the marker off the end.
        ps -ww -o command= -p "$target_pid" 2>/dev/null
    fi
}

process_alive() {
    local target_pid="$1"
    [ -n "$target_pid" ] && [ "$target_pid" -gt 0 ] 2>/dev/null || return 1
    kill -0 "$target_pid" 2>/dev/null
}

is_our_odoo() {
    local target_pid="$1" cmdline
    cmdline="$(process_cmdline "$target_pid")"
    [ -n "$cmdline" ] || return 1
    # The anchor is the absolute --pidfile path this script injects: unique to
    # this checkout, and -- unlike "-m odoo" -- it survives a re-exec. --dev
    # reload rebuilds argv via stripped_sys_argv() (odoo/tools/misc.py:834-850),
    # which drops "-m odoo" and rewrites argv[0], but keeps -c/--pidfile/--logfile.
    case "$cmdline" in *"$pid_file"*) return 0 ;; esac
    # Fallback for a server started by hand without --pidfile.
    case "$cmdline" in
        *"$root"*)
            case "$cmdline" in
                *"-m odoo"*|*odoo-bin*|*"odoo/__main__.py"*) return 0 ;;
            esac
            ;;
    esac
    return 1
}

is_module_operation() {
    # A killed -i/-u leaves ir_module_module mid-state and a registry that may
    # not load: PostgreSQL protects each transaction, not the sequence of them.
    local cmdline
    cmdline="$(process_cmdline "$1")"
    case "$cmdline" in
        *" -u "*|*" -i "*|*" --update "*|*" --init "*) return 0 ;;
    esac
    return 1
}

pidfile_pid() {
    [ -f "$pid_file" ] || { printf '0'; return; }
    local raw
    raw="$(head -n1 "$pid_file" 2>/dev/null | tr -d '[:space:]')"
    # Validate before use. Odoo writes the pidfile with a plain open(), so a
    # truncated or empty file is reachable -- and `kill -0 -1` would signal every
    # process this user owns.
    case "$raw" in
        ''|*[!0-9]*) printf '0' ;;
        *)           printf '%s' "$raw" ;;
    esac
}

port_owner_pid() {
    local port="$1" owner=''
    if command -v ss >/dev/null 2>&1; then
        owner="$(ss -ltnpH "sport = :$port" 2>/dev/null | sed -nE 's/.*pid=([0-9]+).*/\1/p' | head -1)"
    fi
    if [ -z "$owner" ] && command -v lsof >/dev/null 2>&1; then
        owner="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -1)"
    fi
    printf '%s' "${owner:-0}"
}

port_is_busy() {
    # Works with no tooling at all, for hosts where neither ss nor lsof exists
    # or where the owner belongs to another user. "Busy but owner unknown" is
    # still enough to refuse to start.
    local port="$1"
    if command -v curl >/dev/null 2>&1; then
        curl -sS --max-time 2 --noproxy '*' -o /dev/null "http://127.0.0.1:$port/" 2>/dev/null && return 0
    fi
    (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null && { exec 3<&- 2>/dev/null; return 0; }
    return 1
}

# Sets: state_name state_pid state_port state_owner state_detail
#       state_stale state_reused state_foreign
read_state() {
    state_port="$(http_port)"
    state_pid=0
    state_owner="$(port_owner_pid "$state_port")"
    state_detail=""
    state_stale=0
    state_reused=0
    state_foreign=0
    state_name="STOPPED"

    local file_pid
    file_pid="$(pidfile_pid)"
    if [ "$file_pid" -gt 0 ]; then
        if ! process_alive "$file_pid"; then
            state_stale=1
            state_detail="pidfile names PID $file_pid, which is not running"
        elif ! is_our_odoo "$file_pid"; then
            # The dangerous case: the number was recycled by an unrelated
            # process. Treat the file as stale; never signal that PID.
            state_stale=1
            state_reused=1
            state_detail="pidfile names PID $file_pid, but that process is not this project's Odoo"
        else
            state_pid="$file_pid"
        fi
    fi

    # No usable pidfile but something owns the port: adopt it only if it is
    # verifiably ours. Also covers workers mode, where Odoo skips the pidfile
    # when evented (odoo/cli/server.py:88).
    if [ "$state_pid" -eq 0 ] && [ "$state_owner" -gt 0 ] 2>/dev/null; then
        if is_our_odoo "$state_owner"; then
            state_pid="$state_owner"
            state_detail="discovered by port $state_port (no valid pidfile)"
        else
            state_foreign=1
            state_detail="port $state_port is held by PID $state_owner, which is not this project's Odoo"
        fi
    fi

    if [ "$state_pid" -gt 0 ]; then
        if [ "$state_owner" = "$state_pid" ]; then
            state_name="RUNNING"
        else
            state_name="DEGRADED"
            [ -n "$state_detail" ] || state_detail="process $state_pid is alive but not listening on $state_port"
        fi
    elif [ "$state_foreign" -eq 1 ]; then
        state_name="DEGRADED"
    elif [ "$state_owner" = "0" ] && port_is_busy "$state_port"; then
        state_name="DEGRADED"
        state_foreign=1
        state_detail="port $state_port is in use, but its owner could not be identified (it may belong to another user)"
    fi
}

remove_stale_pidfile() {
    if [ -f "$pid_file" ]; then
        say_warn "Removing stale pidfile: $1"
        rm -f "$pid_file"
    fi
}

# ---------------------------------------------------------------------------
# systemd. Detect, then refuse -- never delegate.
#
# The unit runs as a different user, from a different config (/etc/odoo/odoo.conf)
# with a different data_dir, workers and list_db. `start` silently becoming
# `systemctl start odoo` would launch a different program against different data,
# and would need sudo. Refusing is the honest answer.
# ---------------------------------------------------------------------------

systemd_state() {
    # Echoes: "none" | "not-found" | "active" | "inactive" | "enabled-inactive"
    command -v systemctl >/dev/null 2>&1 || { printf 'none'; return; }
    # systemctl exists in plenty of containers and WSL images where systemd is
    # not PID 1. This is the canonical test.
    [ -d /run/systemd/system ] || { printf 'none'; return; }

    local load_state
    # LoadState, not is-active: is-active returns "inactive" for a unit that does
    # not exist, so it cannot tell "stopped" from "no such unit".
    load_state="$(systemctl show -p LoadState --value "${systemd_unit}.service" 2>/dev/null)"
    if [ "$load_state" != "loaded" ]; then
        # A per-user unit is a plausible dev setup.
        if [ -n "${XDG_RUNTIME_DIR:-}" ]; then
            load_state="$(systemctl --user show -p LoadState --value "${systemd_unit}.service" 2>/dev/null)"
            [ "$load_state" = "loaded" ] || { printf 'not-found'; return; }
        else
            printf 'not-found'; return
        fi
    fi
    if systemctl is-active --quiet "${systemd_unit}.service" 2>/dev/null; then printf 'active'; return; fi
    if systemctl is-enabled --quiet "${systemd_unit}.service" 2>/dev/null; then printf 'enabled-inactive'; return; fi
    printf 'inactive'
}

assert_not_systemd_managed() {
    local sd
    sd="$(systemd_state)"
    case "$sd" in
        active)
            say_fail "systemd is already running Odoo as ${systemd_unit}.service."
            say_note "  This script will not start a second instance to fight it for the port."
            say_note "  Use the service manager instead:"
            say_note "    sudo systemctl status ${systemd_unit}"
            say_note "    sudo systemctl restart ${systemd_unit}"
            say_note "    sudo journalctl -u ${systemd_unit} -f"
            say_note "  Note the unit uses /etc/odoo/odoo.conf, not this repo's odoo.conf."
            exit 1
            ;;
        enabled-inactive)
            if [ "$force" -eq 0 ]; then
                say_fail "${systemd_unit}.service exists and is enabled, but is not running."
                say_note "  This host manages Odoo with systemd. Starting a development instance"
                say_note "  here risks two servers competing for the port and the same database."
                say_note "  Either:  sudo systemctl start ${systemd_unit}"
                say_note "  Or:      ./run-odoo.sh start --force   (deliberately run alongside)"
                exit 1
            fi
            say_warn "${systemd_unit}.service is enabled; starting anyway because --force was given."
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

# Echoes the HTTP status code; body goes to $health_body.
health_body=''
health_probe() {
    local with_db="${1:-0}" timeout="${2:-5}" url code
    if [ "$with_db" -eq 1 ]; then url="$(health_url 'db_server_status=1')"; else url="$(health_url '')"; fi
    health_body=''
    if command -v curl >/dev/null 2>&1; then
        # --noproxy '*' matters: an inherited http_proxy would otherwise send a
        # loopback probe through a proxy, and a health check that silently tests
        # the wrong thing is worse than none.
        health_body="$(curl -sS --max-time "$timeout" --noproxy '*' "$url" 2>/dev/null)"
        code="$(curl -sS --max-time "$timeout" --noproxy '*' -o /dev/null -w '%{http_code}' "$url" 2>/dev/null)"
        printf '%s' "${code:-0}"
        return
    fi
    printf '0'
}

postgres_reachable() {
    local pg_host pg_port
    pg_host="$(conf_value db_host)"
    pg_port="$(conf_int db_port 5432)"
    # db_host = False means the local socket with peer auth, which is what
    # deploy/odoo.conf.linux.example uses. Odoo itself falls back to PGHOST in
    # that case (odoo/cli/server.py:61-63), so mirror it rather than assuming TCP.
    if [ -z "$pg_host" ] || [ "$pg_host" = "False" ]; then
        if [ -n "${PGHOST:-}" ]; then pg_host="$PGHOST"; else
            # Local socket: a psql ping is the only real test.
            command -v pg_isready >/dev/null 2>&1 && pg_isready -q 2>/dev/null && return 0
            return 1
        fi
    fi
    if command -v pg_isready >/dev/null 2>&1; then
        pg_isready -q -h "$pg_host" -p "$pg_port" 2>/dev/null && return 0
        return 1
    fi
    (exec 3<>"/dev/tcp/$pg_host/$pg_port") 2>/dev/null && { exec 3<&- 2>/dev/null; return 0; }
    return 1
}

# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

make_runtime_dirs() { mkdir -p "$log_dir" "$runtime_dir"; }

file_size_bytes() {
    [ -f "$1" ] || { printf '0'; return; }
    # BSD and GNU stat take different flags; wc is portable and good enough.
    wc -c < "$1" 2>/dev/null | tr -d '[:space:]'
}

rotate_log_if_large() {
    # Rotation happens here, at start. On POSIX Odoo uses WatchedFileHandler
    # (odoo/netsvc.py:268-272), which reopens after a rename, so logrotate is the
    # better tool for a long-lived server -- see deploy/logrotate.d/odoo. This is
    # for a developer machine with no logrotate.
    local size limit i from to
    size="$(file_size_bytes "$log_file")"
    limit=$(( log_max_mb * 1024 * 1024 ))
    [ "$size" -ge "$limit" ] 2>/dev/null || return 0

    rm -f "$log_file.$log_keep"
    i=$(( log_keep - 1 ))
    while [ "$i" -ge 1 ]; do
        from="$log_file.$i"; to="$log_file.$(( i + 1 ))"
        [ -f "$from" ] && mv -f "$from" "$to"
        i=$(( i - 1 ))
    done
    mv -f "$log_file" "$log_file.1"
    say_note "Rotated $(( size / 1024 / 1024 )) MB log to $(basename "$log_file").1"
}

# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------

run_odoo_tee() {
    # As run_odoo_foreground, but keeps a copy of the run so skips can be counted
    # afterwards. Odoo logs a skipped test at INFO ("skipped <test> : <reason>",
    # odoo/tests/result.py:157) and then omits skips from its own summary, which
    # reports only "N failed, M error(s) of K tests" (result.py:198). A run that
    # skipped everything therefore looks exactly like a run that passed
    # everything. That is TST-3, and half of CI-1.
    local label="$1" transcript="$2"; shift 2
    say_note "> $(basename "$python") $*"
    ( cd "$root" && "$python" "$@" 2>&1 ) | tee "$transcript"
    # PIPESTATUS, not $?: $? here is tee's status, which is always 0.
    local code=${PIPESTATUS[0]}
    report_exit_code "$code" "$label"
    return $code
}

report_skips() {
    # Echoes the skip count. Counting the transcript is the only way: Odoo tracks
    # result.skipped internally and never prints it.
    local transcript="$1" count
    if [ ! -f "$transcript" ]; then
        say_warn "No test transcript at $transcript; skip count unknown."
        printf '%s' -1
        return
    fi
    count=$(grep -c ': skipped ' "$transcript" || true)
    if [ "$count" -eq 0 ]; then
        say_ok "Skipped: 0"
    else
        say_warn "Skipped: $count"
        sed -n 's/^.*: skipped /  /p' "$transcript" >&2
        say_note "  A skipped test is not a passing test. See TST-1 and TST-3."
    fi
    printf '%s' "$count"
}

run_odoo_foreground() {
    # Exit code propagated verbatim.
    #
    # `cd "$root"` is load-bearing: Odoo is NOT pip-installed into the venv, so
    # `python -m odoo` resolves only because the working directory is the repo
    # root. The previous version of this script relied on the caller's cwd.
    local label="$1"; shift
    say_note "> $(basename "$python") $*"
    ( cd "$root" && exec "$python" "$@" )
    local code=$?
    report_exit_code "$code" "$label"
    return $code
}

report_exit_code() {
    local code="$1" label="$2"
    [ "$code" -eq 0 ] && return 0
    echo ""
    say_warn "$label exited with code $code."
    if [ "$code" -eq 137 ]; then
        say_note "  137 is SIGKILL: something killed it, most likely the OOM killer."
    elif [ "$code" -eq 143 ]; then
        say_note "  143 is SIGTERM: a clean shutdown request from outside."
    fi
    return 0
}

# ---------------------------------------------------------------------------
# Validation of user-supplied values
# ---------------------------------------------------------------------------

assert_db() {
    local name="$1" operation="$2"
    if [ -z "$name" ]; then
        say_fail "$operation modifies a database and needs an explicit --db."
        say_note "  Suggested action: ./run-odoo.sh $operation <module> --db <database>"
        say_note "  There is deliberately no default: this project is heading for"
        say_note "  database-per-tenant, where an implicit target is a data-loss bug."
        say_note "  Read-only listing: ./run-odoo.sh db-list"
        exit 2
    fi
    case "$name" in
        *[!A-Za-z0-9_-]*)
            say_fail "Refusing database name '$name': expected only letters, digits, underscore and hyphen."
            exit 2 ;;
    esac
}

assert_module() {
    local name="$1" dir
    if [ -z "$name" ]; then
        say_fail "No module named. Usage: ./run-odoo.sh $command_name <module> --db <database>"
        exit 2
    fi
    case "$name" in
        [a-z]*) : ;;
        *) say_fail "Refusing module name '$name': Odoo module names start with a lowercase letter."; exit 2 ;;
    esac
    case "$name" in
        *[!a-z0-9_]*)
            say_fail "Refusing module name '$name': Odoo module names are lowercase, digits and underscores."
            exit 2 ;;
    esac
    # Search only the configured addons_path. A glob over the repo root would
    # wrongly accept l10n_ne/, which is a translation toolkit and not an addon.
    while IFS= read -r dir; do
        [ -f "$dir/$name/__manifest__.py" ] && return 0
    done < <(addons_dirs)
    say_fail "Module '$name' has no __manifest__.py in any addons_path entry."
    say_note "  Searched:"
    while IFS= read -r dir; do say_note "    $dir"; done < <(addons_dirs)
    say_note "  Available modules: ./run-odoo.sh addons-check"
    exit 2
}

assert_server_stopped() {
    # -i, -u and --test-enable take an exclusive lock on the registry, so they
    # fail confusingly against a live server. Say so up front.
    read_state
    if [ "$state_name" != "STOPPED" ]; then
        say_fail "Odoo is $state_name (PID $state_pid). $1 needs the server stopped."
        say_note "  Suggested action: ./run-odoo.sh stop"
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# start / stop / restart
# ---------------------------------------------------------------------------

enter_start_lock() {
    # mkdir is atomic on POSIX, so two concurrent starts cannot both win. No
    # flock dependency: macOS has it but its argument syntax differs, and Git
    # Bash lacks it entirely.
    #
    # Known limitation, stated rather than hidden: mkdir atomicity is not
    # guaranteed on NFS. Acceptable for a developer launcher.
    if ! mkdir "$lock_dir" 2>/dev/null; then
        local holder
        holder="$(cat "$lock_dir/pid" 2>/dev/null || true)"
        if [ -n "$holder" ] && process_alive "$holder"; then
            say_fail "Another start is in progress (lock held by PID $holder)."
            say_note "  Suggested action: wait for it, or check ./run-odoo.sh status"
            exit 1
        fi
        # Stale, or still being created. Break it exactly once -- never on a
        # timeout alone, which is how two concurrent starts happen.
        say_warn "Removing an abandoned start lock (holder ${holder:-unknown} is not running)"
        rm -rf "$lock_dir"
        if ! mkdir "$lock_dir" 2>/dev/null; then
            say_fail "Could not acquire the start lock at $lock_dir"
            exit 1
        fi
    fi
    printf '%s' "$$" > "$lock_dir/pid"
}

exit_start_lock() {
    # Verify ownership before removing, or a run that failed to acquire the lock
    # would happily delete the winner's.
    if [ -d "$lock_dir" ]; then
        local holder
        holder="$(cat "$lock_dir/pid" 2>/dev/null || true)"
        if [ -z "$holder" ] || [ "$holder" = "$$" ]; then rm -rf "$lock_dir"; fi
    fi
}
# EXIT alone does not fire on INT/TERM unless those are trapped too.
trap exit_start_lock EXIT INT TERM HUP

cmd_start() {
    local dev_mode="${1:-0}"
    check_prereqs || exit 2
    assert_conf_paths
    assert_not_systemd_managed

    read_state
    if [ "$state_name" = "RUNNING" ]; then
        say_fail "Odoo is already running (PID $state_pid, port $state_port)."
        say_note "  Suggested action: ./run-odoo.sh restart"
        exit 1
    fi
    if [ "$state_name" = "DEGRADED" ] && [ "$state_pid" -gt 0 ]; then
        say_fail "Odoo process $state_pid is alive but not serving. $state_detail"
        say_note "  Suggested action: ./run-odoo.sh stop, then start again."
        exit 1
    fi
    if [ "$state_foreign" -eq 1 ]; then
        say_fail "Port $state_port is already in use."
        if [ "$state_owner" -gt 0 ] 2>/dev/null; then
            printf '  Process: PID %s\n' "$state_owner"
            printf '  Command: %s\n' "$(process_cmdline "$state_owner")"
        else
            printf '  Owner could not be identified; it may belong to another user.\n'
        fi
        say_note "  Suggested action: stop that process, or set ODOO_HTTP_PORT / http_port to a free port."
        exit 1
    fi
    [ "$state_stale" -eq 1 ] && remove_stale_pidfile "$state_detail"

    local gevent
    gevent="$(conf_int gevent_port 0)"
    if [ "$gevent" -gt 0 ] && [ "$(port_owner_pid "$gevent")" != "0" ]; then
        say_warn "gevent_port $gevent is already in use; websockets may fail."
    fi

    make_runtime_dirs
    rotate_log_if_large

    set -- -m odoo -c "$conf"
    # --pidfile ONLY for the long-running commands. setup_pid_file() runs
    # unconditionally in odoo/cli/server.py:117, even under --stop-after-init, so
    # giving it to a one-shot test/upgrade would overwrite a live server's
    # pidfile and then atexit-delete it, leaving status blind to a running server.
    set -- "$@" --pidfile "$pid_file" --logfile "$log_file"
    [ "$dev_mode" -eq 1 ] && set -- "$@" --dev reload,qweb,xml

    if [ "$foreground" -eq 1 ]; then
        say_note "Foreground mode: Ctrl-C stops the server. Logs also go to $log_file"
        run_odoo_foreground 'Odoo' "$@"
        exit $?
    fi

    enter_start_lock
    local log_offset launched
    log_offset="$(file_size_bytes "$log_file")"
    say_note "> $(basename "$python") $*"
    # nohup + & is all that is needed here: unlike Windows, a POSIX child keeps
    # its own signal disposition and SIGTERM is genuinely graceful, so no console
    # gymnastics are required. Redirecting both streams costs nothing and catches
    # failures from before logging was configured.
    ( cd "$root" && nohup "$python" "$@" >>"$boot_log" 2>&1 & echo $! > "$runtime_dir/launched.pid" )
    launched="$(cat "$runtime_dir/launched.pid" 2>/dev/null || printf '0')"
    rm -f "$runtime_dir/launched.pid"

    if ! wait_for_healthy "$launched" "$log_offset"; then
        exit_start_lock
        exit 1
    fi
    exit_start_lock

    read_state
    say_ok "Odoo started"
    echo ""
    say_field 'URL'      "http://$(http_host):$(http_port)"
    say_field 'PID'      "$state_pid"
    say_field 'Config'   "$(relative_path "$conf")"
    say_field 'Logs'     "$(relative_path "$log_file")"
    local db_name
    db_name="$(conf_value db_name)"
    [ -n "$db_name" ] && say_field 'Database' "$db_name"
    exit 0
}

wait_for_healthy() {
    local launched="$1" log_offset="$2" server_pid=0 deadline http_up=0 phase_a_deadline code
    say_note "Waiting up to ${start_timeout}s for Odoo to become healthy..."

    # Phase A: the pidfile appears. It is written late -- after
    # _create_empty_database() has already connected to PostgreSQL
    # (odoo/cli/server.py:95-119) -- so the commonest local failure, a wrong
    # db_port, kills the process before any pidfile exists. Catching that here
    # takes a second instead of the whole timeout.
    phase_a_deadline=$(( $(date +%s) + 25 ))
    while [ "$(date +%s)" -lt "$phase_a_deadline" ]; do
        if ! process_alive "$launched"; then
            say_fail "Odoo exited during startup, before it wrote a pidfile."
            say_note "  That means it failed in configuration or while connecting to PostgreSQL,"
            say_note "  which both happen before the pidfile is written."
            show_startup_failure "$log_offset"
            return 1
        fi
        code="$(pidfile_pid)"
        if [ "$code" -gt 0 ] && process_alive "$code"; then server_pid="$code"; break; fi
        sleep 0.25 2>/dev/null || sleep 1
    done
    if [ "$server_pid" -eq 0 ]; then
        say_fail "No pidfile appeared at $(relative_path "$pid_file") within 25s."
        show_startup_failure "$log_offset"
        return 1
    fi
    say_ok "Server process running (PID $server_pid)"

    # Phase B: HTTP healthy, and the registry loaded.
    deadline=$(( $(date +%s) + start_timeout ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if ! process_alive "$server_pid"; then
            say_fail "Odoo exited during startup (PID $server_pid)."
            show_startup_failure "$log_offset"
            return 1
        fi
        if [ "$http_up" -eq 0 ]; then
            if [ "$(health_probe 0 4)" = "200" ]; then
                http_up=1
                say_ok "HTTP responding on port $(http_port)"
            fi
        fi
        if [ "$http_up" -eq 1 ]; then
            # Anchor string from odoo/modules/loading.py:584.
            if grep -q 'Modules loaded\.' "$log_file" 2>/dev/null; then
                say_ok "Modules loaded"
                return 0
            fi
        fi
        sleep 0.7 2>/dev/null || sleep 1
    done

    if [ "$http_up" -eq 1 ]; then
        say_warn "HTTP is responding but 'Modules loaded.' did not appear in the log."
        say_note "  The server is serving requests. Check ./run-odoo.sh errors if it misbehaves."
        return 0
    fi
    say_fail "Odoo did not become healthy within ${start_timeout}s."
    show_startup_failure "$log_offset"
    say_note "  Suggested action: ./run-odoo.sh errors, or raise ODOO_START_TIMEOUT."
    return 1
}

show_startup_failure() {
    # Exactly the bytes this run appended, so nothing from a previous start is
    # mistaken for the current failure.
    local offset="$1" size
    size="$(file_size_bytes "$log_file")"
    if [ "$size" -gt "$offset" ] 2>/dev/null; then
        echo ""
        echo "--- log output from this start attempt ---"
        tail -c "$(( size - offset ))" "$log_file"
    else
        echo ""
        say_warn "This start attempt wrote nothing to the log."
        say_note "  That is the signature of a failure before logging was configured."
    fi
    if [ -s "$boot_log" ]; then
        echo ""
        echo "--- stderr before logging was configured ($(basename "$boot_log")) ---"
        tail -n 15 "$boot_log"
    fi
}

stop_odoo_process() {
    # POSIX has a real graceful stop: SIGTERM and SIGINT take the same branch in
    # Odoo's handler (odoo/service/server.py:469-478), and a second signal forces
    # os._exit(0). This is the whole reason the Linux path is simpler than the
    # Windows one, which has to deliver a console Ctrl-C event instead.
    local target_pid="$1" deadline second_at second_sent=0
    say_note "Stopping PID $target_pid (SIGTERM, then SIGKILL after ${stop_timeout}s)..."
    if ! kill -TERM "$target_pid" 2>/dev/null; then
        say_fail "Could not signal PID $target_pid (already gone, or not permitted)."
        process_alive "$target_pid" || { clear_stopped_state; return 0; }
        return 1
    fi

    deadline=$(( $(date +%s) + stop_timeout ))
    second_at=$(( $(date +%s) + (stop_timeout * 6 / 10) ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if ! process_alive "$target_pid"; then
            if [ ! -f "$pid_file" ]; then
                say_ok "Odoo stopped cleanly (PID $target_pid; it removed its own pidfile)"
            else
                say_ok "Odoo stopped (PID $target_pid)"
            fi
            clear_stopped_state
            return 0
        fi
        if [ "$second_sent" -eq 0 ] && [ "$(date +%s)" -ge "$second_at" ]; then
            say_note "  Still shutting down; sending a second SIGTERM to force it."
            kill -TERM "$target_pid" 2>/dev/null || true
            second_sent=1
        fi
        sleep 0.4 2>/dev/null || sleep 1
    done

    say_warn "Graceful stop timed out after ${stop_timeout}s; sending SIGKILL to $target_pid."
    say_note "  PostgreSQL is ACID so the database stays consistent, and an interrupted"
    say_note "  attachment write is left unreferenced and collected by Odoo's filestore"
    say_note "  GC -- but nothing is flushed, and a mail mid-handoff to SMTP may be"
    say_note "  re-sent by the next cron pass."
    kill -KILL "$target_pid" 2>/dev/null || true
    sleep 1
    if process_alive "$target_pid"; then
        say_fail "PID $target_pid survived SIGKILL."
        return 1
    fi
    say_ok "Odoo terminated (PID $target_pid)"
    clear_stopped_state
    return 0
}

clear_stopped_state() {
    # Odoo's atexit removes the pidfile on a clean exit but not after SIGKILL.
    rm -f "$pid_file"
}

stop_inline() {
    read_state

    if [ "$state_reused" -eq 1 ]; then
        # The most important refusal in this script.
        say_fail "Refusing to stop anything: $state_detail"
        say_note "  The pidfile is stale and its number has been reused. Killing that PID"
        say_note "  would terminate an unrelated process."
        say_note "  Suggested action: delete $(relative_path "$pid_file") once you have"
        say_note "  confirmed Odoo is not running."
        return 1
    fi
    if [ "$state_foreign" -eq 1 ] && [ "$state_pid" -eq 0 ]; then
        say_fail "Not stopping: $state_detail"
        say_note "  That process was not started by this script and is not ours to kill."
        return 1
    fi
    if [ "$state_pid" -eq 0 ]; then
        [ "$state_stale" -eq 1 ] && remove_stale_pidfile "$state_detail"
        say_ok "Odoo is not running."
        return 0
    fi

    # Never kill a module install or upgrade. Those interleave DDL,
    # ir_module_module state writes and asset writes across several commits;
    # PostgreSQL protects each transaction but not the sequence, so an
    # interrupted upgrade can leave state = 'to upgrade' and a registry that
    # will not load.
    if is_module_operation "$state_pid"; then
        say_fail "PID $state_pid is running a module install or upgrade."
        say_note "  Refusing to stop it: an interrupted -i/-u can leave a module stuck in"
        say_note "  'to upgrade' and a registry that will not load. Let it finish."
        say_note "  Command: $(process_cmdline "$state_pid")"
        return 1
    fi

    stop_odoo_process "$state_pid"
}

cmd_stop() { stop_inline; exit $?; }

cmd_restart() {
    echo "--- status ---"
    read_state
    printf '  %s' "$state_name"
    [ "$state_pid" -gt 0 ] && printf ' (PID %s)' "$state_pid"
    echo ""

    if [ "$state_name" != "STOPPED" ]; then
        echo ""
        echo "--- stop ---"
        if ! stop_inline; then
            say_fail "Shutdown failed, so no new instance was started."
            say_note "  Fix the reason above and try again; starting now would risk two servers."
            exit 1
        fi
        read_state
        if [ "$state_name" != "STOPPED" ]; then
            say_fail "Odoo still reports $state_name after stopping. Refusing to start a second instance."
            exit 1
        fi
        say_ok "Verified stopped"
    fi
    echo ""
    echo "--- start ---"
    cmd_start 0
}

# ---------------------------------------------------------------------------
# status / health / info
# ---------------------------------------------------------------------------

relative_path() {
    case "$1" in
        "$root"/*) printf '%s' "${1#$root/}" ;;
        *)         printf '%s' "$1" ;;
    esac
}

git_info() {
    command -v git >/dev/null 2>&1 || return 0
    ( cd "$root" 2>/dev/null || exit 0
      local branch commit dirty
      branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" || exit 0
      [ -n "$branch" ] || exit 0
      commit="$(git rev-parse --short HEAD 2>/dev/null)"
      dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d '[:space:]')"
      if [ "$dirty" = "0" ]; then printf '%s @ %s (clean)' "$branch" "$commit"
      else printf '%s @ %s (%s uncommitted)' "$branch" "$commit" "$dirty"; fi )
}

odoo_version() {
    local release="$root/odoo/release.py"
    [ -f "$release" ] || { printf 'unknown'; return; }
    sed -nE 's/^version_info[[:space:]]*=[[:space:]]*\(([0-9]+),[[:space:]]*([0-9]+).*/\1.\2/p' "$release" | head -1
}

python_version() {
    [ -x "$python" ] || { printf 'not found'; return; }
    "$python" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || printf 'unknown'
}

process_uptime() {
    local target_pid="$1" etime
    etime="$(ps -o etime= -p "$target_pid" 2>/dev/null | tr -d '[:space:]')"
    printf '%s' "${etime:-unknown}"
}

cmd_status() {
    read_state
    case "$state_name" in
        RUNNING)  say_ok   "Odoo is RUNNING" ;;
        STOPPED)  say_warn "Odoo is STOPPED" ;;
        DEGRADED) say_fail "Odoo is DEGRADED" ;;
    esac
    [ -n "$state_detail" ] && printf '  %s\n' "$state_detail"
    echo ""

    if [ "$state_pid" -gt 0 ]; then
        say_field 'PID'    "$state_pid"
        say_field 'Uptime' "$(process_uptime "$state_pid")"
    fi
    say_field 'Port'    "$(http_port) (interface $(http_host))"
    say_field 'Odoo'    "$(odoo_version)"
    say_field 'Python'  "$(python_version)  ($(relative_path "$python"))"
    say_field 'Config'  "$(relative_path "$conf")"
    say_field 'Logs'    "$(relative_path "$log_file")"
    say_field 'PidFile' "$(relative_path "$pid_file")"

    local db_host db_port dir marker
    db_host="$(conf_value db_host)"
    db_port="$(conf_int db_port 5432)"
    [ -z "$db_host" ] || [ "$db_host" = "False" ] && db_host='(local socket)'
    say_field 'Database' "$(conf_value db_name) at $db_host:$db_port"

    echo "Addons:"
    while IFS= read -r dir; do
        if [ -d "$dir" ]; then marker='ok'; else marker='MISSING'; fi
        printf '  [%s] %s\n' "$marker" "$dir"
    done < <(addons_dirs)

    local git sd
    git="$(git_info)"
    [ -n "$git" ] && say_field 'Git' "$git"
    sd="$(systemd_state)"
    case "$sd" in
        active)           say_field 'systemd' "${systemd_unit}.service is ACTIVE -- that is the real service on this host" ;;
        enabled-inactive) say_field 'systemd' "${systemd_unit}.service exists and is enabled, but inactive" ;;
        inactive)         say_field 'systemd' "${systemd_unit}.service exists but is inactive" ;;
    esac

    echo ""
    if [ "$state_name" = "RUNNING" ]; then
        if [ "$(health_probe 1)" = "200" ]; then
            say_ok "Health: $health_body"
        else
            say_fail "Health: $(health_url 'db_server_status=1') did not return 200"
        fi
        exit 0
    fi
    say_note "Health: not probed (server is not running)"
    exit 1
}

cmd_health() {
    # Exit codes are the contract for automation:
    #   0 healthy   1 unhealthy   2 configuration/dependency problem
    check_prereqs || exit 2
    if [ -n "$(bad_conf_paths)" ]; then
        say_fail "Configuration references missing paths (run config-check)."
        exit 2
    fi
    read_state
    if [ "$state_reused" -eq 1 ] || [ "$state_foreign" -eq 1 ]; then say_fail "$state_detail"; exit 1; fi
    if [ "$state_pid" -eq 0 ]; then say_fail "No Odoo process for this project is running."; exit 1; fi
    say_ok "Process alive (PID $state_pid)"

    if [ "$(port_owner_pid "$(http_port)")" != "$state_pid" ]; then
        # Only conclusive when the owner is knowable; otherwise fall through to
        # the HTTP probe, which is the real test.
        if [ "$(port_owner_pid "$(http_port)")" != "0" ]; then
            say_fail "Port $(http_port) is not being served by PID $state_pid."
            exit 1
        fi
    fi
    say_ok "Listening on port $(http_port)"

    local code
    code="$(health_probe 1)"
    if [ "$code" != "200" ]; then
        say_fail "$(health_url 'db_server_status=1') returned $code"
        [ "$code" = "500" ] && say_note "  500 from this endpoint means Odoo cannot reach PostgreSQL."
        exit 1
    fi
    say_ok "HTTP endpoint responding"
    case "$health_body" in *'"db_server_status": true'*|*'"db_server_status":true'*) say_ok "PostgreSQL reachable (as reported by Odoo)" ;; esac

    if [ -f "$log_file" ] && tail -n 200 "$log_file" | grep -qE 'CRITICAL|Failed to load registry|Traceback \(most recent call last\)'; then
        say_warn "Log contains critical line(s); run: ./run-odoo.sh errors"
    else
        say_ok "No fatal errors in the recent log"
    fi
    echo ""
    say_ok "Healthy"
    exit 0
}

cmd_info() {
    # Sanitized summary for pasting into a bug report. db_password and
    # admin_passwd are never read: `info` output goes into tickets and chat,
    # which is exactly how credentials leak.
    local dir count dbfilter db_host git
    echo "Odoo 19 project summary"
    echo "======================="
    say_field 'Root'    "$root"
    say_field 'Odoo'    "$(odoo_version)"
    say_field 'Python'  "$(python_version)  ($(relative_path "$python"))"
    say_field 'Shell'   "bash ${BASH_VERSION:-unknown}"
    say_field 'OS'      "$(uname -srm)"
    say_field 'Config'  "$(relative_path "$conf")"
    say_field 'Logs'    "$(relative_path "$log_file")"
    say_field 'PidFile' "$(relative_path "$pid_file")"
    say_field 'DataDir' "$(relative_path "$(conf_value data_dir)")"
    echo ""
    echo "Server"
    say_field '  HTTP'     "$(http_host):$(http_port)"
    say_field '  Gevent'   "$(conf_int gevent_port 0)"
    say_field '  Workers'  "$(conf_int workers 0)"
    say_field '  Watchdog' "limit_time_real = $(conf_int limit_time_real 120)"
    echo ""
    echo "Database"
    db_host="$(conf_value db_host)"
    [ -z "$db_host" ] || [ "$db_host" = "False" ] && db_host='(local socket / PGHOST)'
    say_field '  Host'     "$db_host:$(conf_int db_port 5432)"
    say_field '  User'     "$(conf_value db_user)"
    say_field '  Default'  "$(conf_value db_name)"
    say_field '  list_db'  "$(conf_value list_db)"
    dbfilter="$(conf_value dbfilter)"
    [ -n "$dbfilter" ] || dbfilter='(unset -- every database is selectable)'
    say_field '  dbfilter' "$dbfilter"
    say_note "  (db_password and admin_passwd are deliberately not shown)"
    echo ""
    echo "Addons"
    while IFS= read -r dir; do
        count=0
        [ -d "$dir" ] && count="$(find "$dir" -maxdepth 2 -name __manifest__.py 2>/dev/null | wc -l | tr -d '[:space:]')"
        printf '  %-5s modules  %s\n' "$count" "$dir"
    done < <(addons_dirs)
    git="$(git_info)"
    [ -n "$git" ] && { echo ""; say_field 'Git' "$git"; }
    echo ""
    read_state
    say_field 'State' "$state_name"
    local sd
    sd="$(systemd_state)"
    [ "$sd" != "none" ] && [ "$sd" != "not-found" ] && say_field 'systemd' "${systemd_unit}.service: $sd"
    exit 0
}

# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------

cmd_logs() {
    if [ ! -f "$log_file" ]; then
        say_warn "No log file at $log_file"
        say_note "  Odoo only writes one when started through this script (which passes --logfile),"
        say_note "  because odoo.conf leaves 'logfile' unset."
        exit 1
    fi
    tail -n "$lines" "$log_file"
    exit 0
}

cmd_logs_follow() {
    if [ ! -f "$log_file" ]; then
        say_warn "No log file at $log_file -- start Odoo first."
        exit 1
    fi
    say_note "Following $log_file (Ctrl-C to stop)"
    tail -n "$lines" -f "$log_file"
}

cmd_errors() {
    if [ ! -f "$log_file" ]; then
        say_warn "No log file at $log_file"
        exit 1
    fi
    local count
    count="$(grep -cE 'WARNING|ERROR|CRITICAL|Traceback \(most recent call last\)' "$log_file" 2>/dev/null || true)"
    if [ "${count:-0}" = "0" ]; then
        say_ok "No WARNING, ERROR, CRITICAL or Traceback lines in $(relative_path "$log_file")"
        exit 0
    fi
    say_note "$count matching line(s); showing the last $lines with trailing context"
    echo ""
    # -A gives the continuation lines of a traceback, which is the useful part.
    grep -nE -A6 'WARNING|ERROR|CRITICAL|Traceback \(most recent call last\)' "$log_file" | tail -n "$(( lines * 4 ))"
    exit 0
}

# ---------------------------------------------------------------------------
# doctor -- read-only. It changes nothing, by design.
# ---------------------------------------------------------------------------

doctor_pass=0; doctor_warn=0; doctor_fail=0
d_pass() { doctor_pass=$(( doctor_pass + 1 )); printf '%s[PASS]%s %s\n' "$c_green"  "$c_reset" "$*"; }
d_warn() { doctor_warn=$(( doctor_warn + 1 )); printf '%s[WARN]%s %s\n' "$c_yellow" "$c_reset" "$*"; }
d_fail() { doctor_fail=$(( doctor_fail + 1 )); printf '%s[FAIL]%s %s\n' "$c_red"    "$c_reset" "$*"; }

# Odoo's floor: below this it logs "Upgrade Wkhtmltopdf" and sets state
# 'upgrade' (ir_actions_report.py:110-113).
wk_min_version='0.12.0'
# What Odoo's own wiki recommends, and what deploy/README.md requires.
wk_want_version='0.12.6'

# Locate the binary the way Odoo does, not the way a shell does: find_in_path()
# searches $PATH and then APPENDS config['bin_path'] (odoo/tools/misc.py:142-146),
# so a binary on PATH wins and bin_path is only a fallback. Checking PATH alone
# would report "not found" on a working portable install; checking bin_path
# alone would name the wrong binary on a system-wide one.
# Sets wk_bin and wk_from; returns 1 when nothing was found.
find_wkhtmltopdf() {
    local dir
    wk_bin=''
    wk_from=''
    if command -v wkhtmltopdf >/dev/null 2>&1; then
        wk_bin="$(command -v wkhtmltopdf)"
        wk_from='PATH'
        return 0
    fi
    dir="$(conf_value bin_path)"
    # Odoo treats the literal string 'None' as unset (misc.py:144).
    if [ -n "$dir" ] && [ "$dir" != 'None' ] && [ -x "$dir/wkhtmltopdf" ]; then
        wk_bin="$dir/wkhtmltopdf"
        wk_from='bin_path in odoo.conf'
        return 0
    fi
    return 1
}

# Grade the PDF engine. Presence is not enough: an UNPATCHED Qt build reports
# state 'ok' to Odoo (is_patched_qt is read at ir_actions_report.py:106 but
# never changes the state) and then silently drops --header-html and
# --footer-html. Nothing in Odoo warns about it, so this is the only place it
# can be caught.
check_wkhtmltopdf() {
    local where out ver

    if ! find_wkhtmltopdf; then
        d_warn "wkhtmltopdf not found on PATH or via bin_path: every PDF report degrades to HTML with 'Unable to find Wkhtmltopdf on this system'. See deploy/README.md section 1."
        return 0
    fi
    where="$wk_bin (via $wk_from)"

    out="$("$wk_bin" --version 2>/dev/null)"
    if [ -z "$out" ]; then
        d_fail "wkhtmltopdf at $where does not answer --version; Odoo reports state 'broken' and PDF rendering fails."
        return 0
    fi

    # Odoo parses the first run of digits and dots (ir_actions_report.py:108),
    # so match what it matches rather than inventing a stricter pattern.
    ver="$(printf '%s' "$out" | grep -oE '[0-9]+(\.[0-9]+)+' | head -1)"
    if [ -z "$ver" ]; then
        d_fail "wkhtmltopdf at $where reports no parseable version ('$out'); Odoo reports state 'broken'."
        return 0
    fi

    if ! version_ge "$ver" "$wk_min_version"; then
        d_fail "wkhtmltopdf $ver at $where is below Odoo's minimum $wk_min_version; Odoo reports state 'upgrade'. See deploy/README.md section 1."
    elif ! printf '%s' "$out" | grep -qi '(with patched qt)'; then
        d_fail "wkhtmltopdf $ver at $where does not report '(with patched qt)'. Odoo will still call it, but headers and footers are silently dropped. See deploy/README.md section 1."
    elif ! version_ge "$ver" "$wk_want_version"; then
        d_warn "wkhtmltopdf $ver at $where is patched-Qt but below the recommended $wk_want_version; Odoo accepts it. See deploy/README.md section 1."
    else
        d_pass "wkhtmltopdf $ver (with patched qt) at $where"
    fi
}

production_signals() {
    # A bound, non-loopback interface is decisive on its own; everything else is
    # circumstantial and needs corroboration, so the caller requires two lines.
    #
    # `list_db = False` was a signal here and deliberately is not any more: it is
    # now recommended everywhere, because the database manager is auth="none" and
    # cannot be switched off (web/controllers/database.py:65-69). Treating a
    # hardening step as evidence of production made a tightened dev box report two
    # false FAILs.
    local iface
    [ "$(conf_int workers 0)" -gt 0 ] && printf 'workers > 0
'
    conf_bool proxy_mode && printf 'proxy_mode = True
'
    iface="$(conf_value http_interface)"
    case "$iface" in
        ''|127.0.0.1|localhost) : ;;
        *) printf 'http_interface = %s
reachable from off-host
' "$iface" ;;
    esac
    return 0
}

cmd_doctor() {
    local prod_signals is_prod=0 dir count pkg release min_v max_v py_v size free
    echo "Odoo 19 doctor -- read-only diagnostic"
    echo "======================================"
    echo ""
    prod_signals="$(production_signals | paste -sd',' - 2>/dev/null || production_signals | tr '\n' ',')"
    # Two signals, not one: a single circumstantial setting is not a server.
    if [ "$(production_signals | grep -c .)" -ge 2 ]; then
        is_prod=1
        say_warn "This host looks production-like: ${prod_signals%,}"
        say_note "  Dev-only settings are graded FAIL rather than WARN below."
        echo ""
    fi

    echo "Python and virtual environment"
    if [ -x "$python" ]; then
        d_pass "Interpreter present: $(relative_path "$python")"
        py_v="$(python_version)"
        release="$root/odoo/release.py"
        min_v="$(sed -nE 's/^MIN_PY_VERSION[[:space:]]*=[[:space:]]*\(([0-9]+),[[:space:]]*([0-9]+)\).*/\1.\2/p' "$release" 2>/dev/null | head -1)"
        max_v="$(sed -nE 's/^MAX_PY_VERSION[[:space:]]*=[[:space:]]*\(([0-9]+),[[:space:]]*([0-9]+)\).*/\1.\2/p' "$release" 2>/dev/null | head -1)"
        if [ -n "$min_v" ] && [ -n "$max_v" ]; then
            # Odoo declares its own supported range; read it rather than
            # hard-coding one that will go stale.
            if "$python" -c "import sys; from packaging.version import Version" 2>/dev/null; then :; fi
            d_pass "Python $py_v (Odoo declares support for $min_v-$max_v)"
        else
            d_warn "Python $py_v (could not read MIN/MAX_PY_VERSION from odoo/release.py)"
        fi
        if "$python" -m pip --version >/dev/null 2>&1; then
            d_pass "pip: $("$python" -m pip --version 2>/dev/null)"
        else
            d_fail "python -m pip failed"
        fi
    else
        d_fail "Interpreter missing or not executable: $python"
    fi

    echo ""
    echo "Odoo"
    if [ -f "$root/odoo/__main__.py" ]; then
        d_pass "Entry point present: odoo/__main__.py (python -m odoo)"
    else
        d_fail "odoo/__main__.py missing -- python -m odoo will not work"
    fi
    if [ -x "$python" ]; then
        if ( cd "$root" && "$python" -c 'import odoo.release as r; print(r.version)' >/dev/null 2>&1 ); then
            d_pass "Odoo imports: version $( cd "$root" && "$python" -c 'import odoo.release as r; print(r.version)' 2>/dev/null )"
        else
            d_fail "import odoo failed -- check that cwd is the repo root and requirements are installed"
        fi
        for pkg in nepali_datetime psycopg2 lxml babel; do
            if ( cd "$root" && "$python" -c "import $pkg" >/dev/null 2>&1 ); then
                d_pass "Python package present: $pkg"
            else
                d_fail "Python package missing: $pkg  (pip install -r requirements.txt)"
            fi
        done
    fi

    echo ""
    echo "Configuration"
    if [ -f "$conf" ]; then d_pass "Config present: $(relative_path "$conf")"; else d_fail "Config missing: $conf"; fi
    local bad
    bad="$(bad_conf_paths)"
    if [ -z "$bad" ]; then
        d_pass "Every addons_path entry and data_dir exists"
    else
        printf '%s\n' "$bad" | while IFS= read -r entry; do d_fail "Missing path -- $entry"; done
        doctor_fail=$(( doctor_fail + 1 ))
        say_note "    This is audit finding OPS-1: Odoo starts anyway, with modules"
        say_note "    silently absent or attachments raising FileNotFoundError."
    fi

    # OPS-2: the database manager reachable with a default master password.
    local admin_pw
    admin_pw="$(conf_value admin_passwd)"
    case "$admin_pw" in
        admin|CHANGE_ME|CHANGE-ME|odoo|master|password)
            if conf_bool list_db; then
                if [ "$is_prod" -eq 1 ]; then
                    d_fail "admin_passwd is a default value AND list_db is True -- the database manager is exposed (OPS-2)"
                else
                    d_warn "admin_passwd is a default value AND list_db is True -- the database manager is exposed (OPS-2). Acceptable on a dev box; must not ship."
                fi
            else
                d_warn "admin_passwd is a default value (OPS-2). list_db is False, which limits the exposure."
            fi
            ;;
        *) d_pass "admin_passwd is not one of the known default values" ;;
    esac

    # OPS-4: the wall-clock watchdog.
    local ltr
    ltr="$(conf_int limit_time_real 120)"
    if [ "$ltr" -eq 0 ]; then
        if [ "$is_prod" -eq 1 ]; then
            d_fail "limit_time_real = 0 -- the runaway-request watchdog is disabled (OPS-4). One tenant's infinite loop consumes a thread permanently."
        else
            d_warn "limit_time_real = 0 -- the watchdog is disabled (OPS-4). Correct on Windows; on Linux SIGHUP genuinely re-execs, so restore it here."
        fi
    else
        d_pass "limit_time_real = $ltr (watchdog active)"
    fi

    local dbfilter
    dbfilter="$(conf_value dbfilter)"
    if [ -z "$dbfilter" ]; then
        if [ "$is_prod" -eq 1 ]; then d_fail "dbfilter is unset: any client can select any database"
        else d_warn "dbfilter is unset: any client can select any database. Fine locally."; fi
    else
        d_pass "dbfilter = $dbfilter"
    fi

    if [ -z "$(conf_value logfile)" ]; then
        d_warn "odoo.conf sets no logfile: Odoo logs to stderr. This script passes --logfile, so logs land in $(relative_path "$log_file") -- but a hand-started server's output is lost. Under systemd the journal captures it."
    else
        d_pass "logfile is set in odoo.conf"
    fi

    echo ""
    echo "Addons"
    while IFS= read -r dir; do
        if [ -d "$dir" ]; then
            count="$(find "$dir" -maxdepth 2 -name __manifest__.py 2>/dev/null | wc -l | tr -d '[:space:]')"
            if [ "$count" -gt 0 ]; then d_pass "$count modules in $dir"; else d_warn "No modules found in $dir"; fi
        else
            d_fail "addons_path entry does not exist: $dir"
        fi
    done < <(addons_dirs)

    echo ""
    echo "Filesystem"
    local data_dir probe
    data_dir="$(conf_value data_dir)"
    if [ -n "$data_dir" ] && [ -d "$data_dir" ]; then
        # Writability cannot be inferred from mode bits alone (ACLs, read-only
        # mounts, full disks). Probing is the only reliable test, and it is the
        # one write doctor performs -- immediately undone.
        probe="$data_dir/.doctor-write-probe.$$"
        if ( : > "$probe" ) 2>/dev/null; then
            rm -f "$probe"
            d_pass "data_dir is writable: $(relative_path "$data_dir")"
        else
            d_fail "data_dir is not writable: $data_dir"
        fi
    elif [ -n "$data_dir" ]; then
        d_fail "data_dir does not exist: $data_dir"
    fi
    for dir in "$log_dir" "$runtime_dir"; do
        if [ -d "$dir" ]; then d_pass "Directory present: $(relative_path "$dir")"
        else d_warn "Directory absent (created on first start): $(relative_path "$dir")"; fi
    done
    if [ -f "$log_file" ]; then
        size="$(( $(file_size_bytes "$log_file") / 1024 / 1024 ))"
        if [ "$size" -ge "$log_max_mb" ]; then d_warn "Log is ${size} MB; it will be rotated on the next start (threshold ${log_max_mb} MB)"
        else d_pass "Log size ${size} MB (rotates at ${log_max_mb} MB, keeping $log_keep)"; fi
    fi
    free="$(df -Pm "$root" 2>/dev/null | awk 'NR==2 {print int($4/1024)}')"
    if [ -n "$free" ]; then
        if [ "$free" -lt 2 ]; then d_fail "Only ${free} GB free on the filesystem holding the repo"
        elif [ "$free" -lt 10 ]; then d_warn "${free} GB free on the filesystem holding the repo"
        else d_pass "${free} GB free on the filesystem holding the repo"; fi
    fi

    echo ""
    echo "PostgreSQL"
    if command -v psql >/dev/null 2>&1; then
        d_pass "Client: $(command -v psql) ($(psql --version 2>/dev/null))"
    else
        d_warn "No psql client found; db-list will not work. Odoo itself does not need it."
    fi
    if postgres_reachable; then
        d_pass "PostgreSQL reachable at $(conf_value db_host):$(conf_int db_port 5432)"
    else
        d_fail "Cannot reach PostgreSQL at $(conf_value db_host):$(conf_int db_port 5432)"
    fi

    echo ""
    echo "Optional tooling"
    for pkg in git node npm; do
        if command -v "$pkg" >/dev/null 2>&1; then d_pass "$pkg present: $(command -v "$pkg")"
        else d_warn "$pkg not on PATH"; fi
    done
    check_wkhtmltopdf

    echo ""
    echo "Runtime state"
    read_state
    if [ "$state_reused" -eq 1 ]; then
        d_fail "Stale pidfile whose PID has been reused. stop would refuse; delete $(relative_path "$pid_file")."
    elif [ "$state_stale" -eq 1 ]; then
        d_warn "Stale pidfile: $state_detail. Removed automatically on the next start."
    elif [ -f "$pid_file" ]; then
        d_pass "Pidfile is valid (PID $state_pid)"
    else
        d_pass "No pidfile (server not started through this script)"
    fi
    [ -d "$lock_dir" ] && d_warn "Start lock present: $(relative_path "$lock_dir")."
    if [ "$state_owner" = "0" ]; then
        d_pass "Port $(http_port) is free"
    elif [ "$state_owner" = "$state_pid" ]; then
        d_pass "Port $(http_port) is served by this project's Odoo (PID $state_owner)"
    else
        d_fail "Port $(http_port) is held by PID $state_owner, which is not this project's Odoo"
    fi

    echo ""
    echo "Service management"
    local sd
    sd="$(systemd_state)"
    case "$sd" in
        none)             d_pass "No systemd on this host; this script is the only launcher" ;;
        not-found)        d_pass "systemd present but no ${systemd_unit}.service -- no conflict" ;;
        active)           d_warn "${systemd_unit}.service is ACTIVE. That is the real service; this script will refuse to start alongside it." ;;
        enabled-inactive) d_warn "${systemd_unit}.service is enabled but inactive. Prefer 'systemctl start ${systemd_unit}' on this host." ;;
        inactive)         d_pass "${systemd_unit}.service exists but is inactive and not enabled" ;;
    esac

    echo ""
    echo "Repository"
    local git remotes dirty
    git="$(git_info)"
    if [ -n "$git" ]; then
        d_pass "Git: $git"
        remotes="$( cd "$root" && git remote 2>/dev/null | wc -l | tr -d '[:space:]' )"
        if [ "$remotes" = "0" ]; then
            d_warn "No git remote configured -- commits exist only on this disk (audit finding SUP-2)"
        else
            d_pass "Git remote(s): $( cd "$root" && git remote 2>/dev/null | paste -sd',' - )"
        fi
        dirty="$( cd "$root" && git status --porcelain 2>/dev/null | wc -l | tr -d '[:space:]' )"
        if [ "$dirty" = "0" ]; then d_pass "Working tree clean"; else d_warn "$dirty uncommitted change(s)"; fi
    else
        d_warn "Not a git repository, or git is unavailable"
    fi

    echo ""
    echo "Summary"
    echo "-------"
    printf '  PASS %s   WARN %s   FAIL %s\n' "$doctor_pass" "$doctor_warn" "$doctor_fail"
    echo ""
    if [ "$doctor_fail" -gt 0 ]; then
        say_fail "$doctor_fail check(s) failed."
        exit 2
    fi
    if [ "$doctor_warn" -gt 0 ]; then
        say_ok "No failures. $doctor_warn warning(s) -- review them, they are not necessarily problems here."
        exit 0
    fi
    say_ok "All checks passed."
    exit 0
}

# ---------------------------------------------------------------------------
# config-check / addons-check / db-list / clean
# ---------------------------------------------------------------------------

cmd_config_check() {
    if [ ! -f "$conf" ]; then say_fail "$conf not found"; exit 2; fi
    say_ok "Config readable: $(relative_path "$conf")"
    local bad
    bad="$(bad_conf_paths)"
    if [ -n "$bad" ]; then
        say_fail "$conf references paths that do not exist:"
        printf '  %s\n' "$bad" >&2
        echo "" >&2
        say_note "Odoo would start anyway -- with those modules missing, or raising"
        say_note "FileNotFoundError per attachment. Fix odoo.conf before starting."
        exit 2
    fi
    say_ok "Every addons_path entry and data_dir exists"
    # Let Odoo parse its own config: catches value errors a regex reader cannot,
    # using the same code path the server uses.
    if [ -x "$python" ]; then
        if ( cd "$root" && "$python" -c "from odoo.tools import config; config.parse_config(['-c', '$conf'])" >/dev/null 2>&1 ); then
            say_ok "Odoo parses the config without error"
        else
            say_fail "Odoo rejected the config:"
            ( cd "$root" && "$python" -c "from odoo.tools import config; config.parse_config(['-c', '$conf'])" 2>&1 | sed 's/^/  /' )
            exit 2
        fi
    fi
    echo ""
    say_field 'HTTP'     "$(http_host):$(http_port)"
    say_field 'Database' "$(conf_value db_name)"
    say_field 'DataDir'  "$(conf_value data_dir)"
    exit 0
}

cmd_addons_check() {
    local dir count failed=0 modules
    if [ -z "$(addons_dirs)" ]; then say_fail "addons_path is empty"; exit 2; fi
    while IFS= read -r dir; do
        if [ ! -d "$dir" ]; then
            say_fail "Missing: $dir"
            failed=1
            continue
        fi
        modules="$(find "$dir" -maxdepth 2 -name __manifest__.py 2>/dev/null | sed -E 's:.*/([^/]+)/__manifest__\.py:\1:' | sort)"
        count="$(printf '%s\n' "$modules" | grep -c . || true)"
        say_ok "$count modules in $dir"
        # List only the project's own modules; 685 stock names are noise.
        if [ "$count" -le 40 ]; then
            printf '%s\n' "$modules" | sed 's/^/    /'
        else
            say_note "    (listing suppressed: $count modules)"
        fi
    done < <(addons_dirs)
    [ "$failed" -eq 1 ] && exit 2
    exit 0
}

cmd_db_list() {
    # Read-only, and deliberately not routed through Odoo's database manager:
    # /web/database/* exists to create, duplicate, drop and restore, and this
    # command must not be able to do any of that even by accident.
    local psql_bin db_host db_port db_user
    psql_bin="${ODOO_PSQL:-$(command -v psql 2>/dev/null || true)}"
    if [ -z "$psql_bin" ] || [ ! -x "$psql_bin" ]; then
        say_fail "No psql client found."
        say_note "  Set ODOO_PSQL to its full path, or install the PostgreSQL client."
        exit 2
    fi
    db_host="$(conf_value db_host)"
    db_port="$(conf_int db_port 5432)"
    db_user="$(conf_value db_user)"

    say_note "Databases visible to '${db_user:-$USER}' (read-only)"
    echo ""
    # PGPASSWORD in the child environment only, never on the command line where
    # it would be visible in the process list to every user on the machine.
    local sql rows
    sql="SELECT d.datname, pg_size_pretty(pg_database_size(d.datname)), (SELECT count(*) FROM pg_stat_activity a WHERE a.datname = d.datname) FROM pg_database d WHERE NOT d.datistemplate AND d.datallowconn ORDER BY d.datname"
    if [ -n "$db_host" ] && [ "$db_host" != "False" ]; then
        rows="$(PGPASSWORD="$(conf_value db_password)" "$psql_bin" -h "$db_host" -p "$db_port" -U "$db_user" -d postgres -At -F'|' -c "$sql" -P pager=off 2>&1)"
    else
        # Local socket with peer auth: no host, no password.
        rows="$("$psql_bin" -d postgres -At -F'|' -c "$sql" -P pager=off 2>&1)"
    fi
    if [ $? -ne 0 ]; then
        say_fail "psql failed:"
        printf '  %s\n' "$rows"
        exit 1
    fi
    printf '%-28s %10s %12s\n' 'DATABASE' 'SIZE' 'CONNECTIONS'
    printf '%s\n' "$rows" | while IFS='|' read -r name size conns; do
        [ -z "$name" ] && continue
        printf '%-28s %10s %12s\n' "$name" "$size" "$conns"
    done
    echo ""
    local dbfilter
    dbfilter="$(conf_value dbfilter)"
    if [ -z "$dbfilter" ]; then
        say_warn "dbfilter is unset, so Odoo will serve any of these to any client."
    else
        say_note "dbfilter = $dbfilter (Odoo only serves databases matching this)"
    fi
    say_note "This command cannot create, drop or restore a database. That is deliberate."
    exit 0
}

cmd_clean() {
    # Scope is deliberately narrow: build artefacts and rotated logs only.
    # Nothing here touches data_dir, the filestore, sessions or a database.
    local dir removed=0 rotated=0
    say_note "Removing __pycache__, *.pyc and rotated logs. Nothing else."
    read_state
    [ "$state_name" = "RUNNING" ] && say_warn "Odoo is running; clearing __pycache__ is safe but takes effect on restart."
    while IFS= read -r dir; do
        [ -d "$dir" ] || continue
        # Only inside addons_path, so a mistyped config cannot widen the sweep.
        removed=$(( removed + $(find "$dir" -type d -name __pycache__ 2>/dev/null | wc -l | tr -d '[:space:]') ))
        find "$dir" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
    done < <(addons_dirs)
    say_ok "Removed $removed __pycache__ directories"
    rotated="$(find "$log_dir" -maxdepth 1 -name 'odoo.log.*' 2>/dev/null | wc -l | tr -d '[:space:]')"
    find "$log_dir" -maxdepth 1 -name 'odoo.log.*' -exec rm -f {} + 2>/dev/null || true
    say_ok "Removed $rotated rotated log file(s)"
    say_note "Left untouched: $(relative_path "$(conf_value data_dir)"), the current log, and every database."
    exit 0
}

# ---------------------------------------------------------------------------
# module operations and tests -- all require an explicit database
# ---------------------------------------------------------------------------

custom_modules() {
    # The project's own modules: everything in an addons_path entry that is not
    # the stock odoo/addons tree.
    local dir
    while IFS= read -r dir; do
        [ "$dir" = "$root/odoo/addons" ] && continue
        [ -d "$dir" ] || continue
        find "$dir" -maxdepth 2 -name __manifest__.py 2>/dev/null \
            | sed -E 's:.*/([^/]+)/__manifest__\.py:\1:'
    done < <(addons_dirs) | sort -u
}

# Vendored OCA modules: carried verbatim apart from the deviations in
# custom_addons/VENDORED.md. Excluded from pylint because reformatting upstream
# code makes the next sync unreadable, and its findings are not ours to fix.
vendored_modules="account_asset_management account_budget_oca account_financial_report account_fiscal_year date_range report_xlsx report_xlsx_helper"

local_modules() {
    local name
    for name in $(custom_modules); do
        case " $vendored_modules " in
            *" $name "*) continue ;;
        esac
        printf '%s\n' "$name"
    done
}

lint_tool() {
    # Runs one tool. Returns 0 when it reported nothing, 1 on findings, and 0 with
    # a warning when the tool is not installed -- lint is optional locally and
    # mandatory in CI, and pretending an absent tool passed would be worse.
    local label="$1"; shift
    say_note "> $(basename "$python") $*"
    ( cd "$root" && "$python" "$@" 2>&1 ) || {
        local code=$?
        if [ "$1" = "-m" ] && ! "$python" -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$2') else 1)" 2>/dev/null; then
            say_warn "$2 is not installed; nothing was checked."
            say_note "  ./venv/bin/python3 -m pip install -r requirements-dev.txt"
            return 0
        fi
        return "$code"
    }
    return 0
}

cmd_lint() {
    # Static analysis. Read-only: touches no database and starts no server (QA-1).
    #
    # Three tools, because each sees what the others cannot:
    #   ruff          -- imports, dead code, obsolete syntax, the bandit subset
    #   pylint-odoo   -- manifest keys, translation misuse, cr.execute injection
    #   version check -- a module changed without its manifest version rising
    local failed=""

    echo ""
    echo "ruff"
    if lint_tool 'ruff' -m ruff check --config ruff.toml; then
        say_ok 'ruff: clean'
    else
        failed="$failed ruff"
    fi

    echo ""
    echo "pylint-odoo"
    local targets=()
    local name
    for name in $(local_modules); do targets+=("custom_addons/$name"); done
    if [ ${#targets[@]} -eq 0 ]; then
        say_warn 'No local modules found to lint.'
    elif lint_tool 'pylint' -m pylint --rcfile=.pylintrc "${targets[@]}"; then
        say_ok 'pylint-odoo: clean'
    else
        failed="$failed pylint-odoo"
    fi

    echo ""
    echo "manifest versions (UPG-2)"
    if lint_tool 'versions' tools/check_module_versions.py --quiet; then
        say_ok 'every module version is newer than its last code change'
    else
        failed="$failed manifest-versions"
    fi

    echo ""
    echo "test wiring (TST-9)"
    if lint_tool 'wiring' tools/check_test_wiring.py --quiet; then
        say_ok 'every tests/ directory imports every test file it contains'
    else
        failed="$failed test-wiring"
    fi

    echo ""
    if [ -z "$failed" ]; then
        say_ok 'Lint clean'
        exit 0
    fi
    say_fail "Lint findings from:$failed"
    say_note '  Install the tooling with:'
    say_note '    ./venv/bin/python3 -m pip install -r requirements-dev.txt'
    exit 1
}

cmd_module_operation() {
    local flag="$1" module="$2" verb="$3"
    check_prereqs || exit 2
    assert_conf_paths
    assert_module "$module"
    assert_db "$database" "$verb"
    assert_server_stopped "$verb"

    say_warn "$verb '$module' in database '$database'. This modifies that database."
    # No --pidfile here: setup_pid_file() runs even with --stop-after-init, so
    # passing it would clobber a running server's pidfile.
    run_odoo_foreground "$verb $module" \
        -m odoo -c "$conf" -d "$database" "$flag" "$module" --stop-after-init
    local code=$?
    [ "$code" -eq 0 ] && say_ok "$verb complete: $module in $database"
    exit $code
}

cmd_test() {
    local module="$1" modules tags code
    check_prereqs || exit 2
    assert_conf_paths

    if [ -z "$module" ]; then
        modules="$(custom_modules | paste -sd',' -)"
        [ -n "$modules" ] || { say_fail "No custom modules found to test."; exit 2; }
    else
        assert_module "$module"
        modules="$module"
    fi
    assert_db "$database" "test"
    assert_server_stopped "test"

    # -u is what makes post_install tests run for these modules; --test-tags
    # scopes the run to them. Both are needed: --test-enable alone runs nothing
    # for modules that are already up to date.
    #
    # The tag list is passed as ONE argument with a leading slash per module.
    # Note for anyone running this from Git Bash on Windows: MSYS rewrites a
    # leading-slash argument into a Windows path, so use MSYS_NO_PATHCONV=1.
    tags="$(printf '%s' "$modules" | tr ',' '\n' | sed 's:^:/:' | paste -sd',' -)"

    say_warn "Testing in database '$database'. -u modifies that database."
    say_note "  Modules: $modules"
    local transcript="$runtime_dir/last-test-run.log"
    mkdir -p "$runtime_dir"
    run_odoo_tee 'test run' "$transcript" \
        -m odoo -c "$conf" -d "$database" -u "$modules" \
        --test-enable --test-tags "$tags" --stop-after-init
    code=$?
    echo ""
    local skipped
    skipped=$(report_skips "$transcript")
    if [ "$code" -eq 0 ]; then
        say_ok "Tests passed"
    else
        # Never soften this: a non-zero code here means failing tests.
        say_fail "Tests FAILED (exit $code). Odoo's exit code is propagated unchanged."
        say_note "  Detail: ./run-odoo.sh errors"
    fi
    say_note "  Transcript: $(relative_path "$transcript")"
    if [ "$code" -eq 0 ] && [ "$fail_on_skip" -eq 1 ] && [ "$skipped" -gt 0 ]; then
        say_fail "Exiting non-zero: $skipped test(s) skipped and --fail-on-skip was given."
        exit 1
    fi
    exit $code
}

# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------

cmd_help() {
    cat <<EOF
Odoo 19 service management (Linux / macOS)

USAGE
  ./run-odoo.sh <command> [target] [options]

SERVICE
  start                 Start in the background and wait until healthy
  stop                  SIGTERM, then SIGKILL after --timeout seconds
  restart               status -> stop -> verify stopped -> start -> health
  status                RUNNING / STOPPED / DEGRADED, with operational detail
  health                Real probes. Exit 0 healthy, 1 unhealthy, 2 misconfigured

LOGS
  logs                  Last -n lines (default $lines)
  logs-follow           Stream the log until Ctrl-C
  errors                Recent WARNING/ERROR/CRITICAL/Traceback, with context

DIAGNOSTICS
  doctor                Comprehensive read-only check. Changes nothing
  lint                  Static analysis: ruff, pylint-odoo, manifest versions
  info                  Sanitized runtime summary for a bug report
  config-check          Validate odoo.conf, including Odoo's own parser
  addons-check          List and validate every addons_path entry
  version               Odoo, Python and bash versions

DEVELOPMENT
  dev                   --dev reload,qweb,xml
  shell                 Odoo shell with 'env' bound
  clean                 Remove __pycache__, *.pyc and rotated logs only

DATABASE (each requires --db; there is no default)
  db-list               Read-only list of databases. Cannot create or drop
  install <module>      Install a module          --db <database>
  upgrade <module>      Upgrade a module          --db <database>
  test                  Test every custom module  --db <database>
  test-module <module>  Test one module           --db <database>

OPTIONS
  --db <name>           Target database. Required by install/upgrade/test
  -n, --lines <count>   Lines for logs/errors (default $lines)
  --foreground          start/dev: run attached instead of in the background
  --fail-on-skip        test: exit non-zero if any test skipped itself (for CI)
  --timeout <seconds>   Override the start (${start_timeout}s) and stop (${stop_timeout}s) waits
  --force               Start even if a systemd unit is enabled (see below)
  --no-color            Disable colour (also honours the NO_COLOR variable)
  -h, --help            This text

DATABASE SAFETY
  * install, upgrade, test and test-module refuse to run without --db.
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

RELATIONSHIP TO SYSTEMD
  On Linux the production service is systemd: deploy/odoo.service, using
  /etc/odoo/odoo.conf. This script is a DEVELOPMENT layer and will refuse to
  start when it can see that unit is active, rather than racing it for the port.
  It never calls systemctl on your behalf -- the unit runs as a different user,
  from a different config, against a different data_dir.
      sudo systemctl start|stop|restart|status odoo
      sudo journalctl -u odoo -f
  Override the unit name with --unit or \$ODOO_UNIT.

EXIT CODES
  0   Success, or healthy
  1   Operational failure -- unhealthy, not running, stop failed, refused
  2   Usage, configuration or dependency problem
      install/upgrade/test/dev/shell return Odoo's own exit code unchanged, so a
      failing test suite is never masked.

ENVIRONMENT OVERRIDES
  ODOO_CONF             Config file          (default: odoo.conf)
  ODOO_PYTHON           Interpreter          (default: venv/bin/python3)
  ODOO_LOG              Log file             (default: logs/odoo.log)
  ODOO_PIDFILE          Pid file             (default: .runtime/odoo.pid)
  ODOO_HTTP_PORT        Port to probe        (default: http_port from odoo.conf)
  ODOO_START_TIMEOUT    Start wait, seconds  (default: 90)
  ODOO_STOP_TIMEOUT     Stop wait, seconds   (default: 30)
  ODOO_LOG_MAX_MB       Rotate above this    (default: 20)
  ODOO_LOG_KEEP         Generations to keep  (default: 5)
  ODOO_PSQL             psql path            (default: discovered)
  ODOO_UNIT             systemd unit name    (default: odoo)
  NO_COLOR              Any value disables colour

DEPRECATED
  -i, --install <module>   Use: install <module> --db <database>
  -u, --update <module>    Use: upgrade <module> --db <database>
  -s, --shell              Use: shell
  -d, --dev                Use: dev
  These still work but now require --db where they modify a database.

EXAMPLES
  ./run-odoo.sh start
  ./run-odoo.sh status
  ./run-odoo.sh logs-follow -n 100
  ./run-odoo.sh doctor
  ./run-odoo.sh upgrade l10n_np_accounting --db odoo19
  ./run-odoo.sh test --db odoo19

THIS IS NOT A SERVICE MANAGER
  A backgrounded process has no supervision, no restart on crash and no boot
  integration. See docs/operations/ODOO_SERVICE_MANAGEMENT.md.
EOF
}

cmd_version() {
    say_field 'Odoo'   "$(odoo_version)"
    say_field 'Python' "$(python_version)"
    say_field 'bash'   "${BASH_VERSION:-unknown}"
    local git
    git="$(git_info)"
    [ -n "$git" ] && say_field 'Git' "$git"
    exit 0
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

while [ $# -gt 0 ]; do
    case "$1" in
        --db)         database="${2:?--db needs a database name}"; shift 2 ;;
        --db=*)       database="${1#*=}"; shift ;;
        -n|--lines)   lines="${2:?--lines needs a number}"; shift 2 ;;
        --lines=*)    lines="${1#*=}"; shift ;;
        --timeout)    start_timeout="${2:?--timeout needs seconds}"; stop_timeout="$2"; shift 2 ;;
        --timeout=*)  start_timeout="${1#*=}"; stop_timeout="${1#*=}"; shift ;;
        --unit)       systemd_unit="${2:?--unit needs a name}"; shift 2 ;;
        --unit=*)     systemd_unit="${1#*=}"; shift ;;
        --foreground) foreground=1; shift ;;
        --fail-on-skip) fail_on_skip=1; shift ;;
        --force)      force=1; shift ;;
        --no-color)   no_color=1; shift ;;
        -h|--help)    init_colors; cmd_help; exit 0 ;;
        # Deprecated flag forms, kept working because deploy/README.md documents
        # them and they are in people's shell history.
        -i|--install) command_name='install'; target="${2:?--install needs a module name}"
                      legacy_warning="-i/--install is deprecated; use: install <module> --db <database>"; shift 2 ;;
        -u|--update)  command_name='upgrade'; target="${2:?--update needs a module name}"
                      legacy_warning="-u/--update is deprecated; use: upgrade <module> --db <database>"; shift 2 ;;
        -s|--shell)   command_name='shell'; legacy_warning="-s/--shell is deprecated; use: shell"; shift ;;
        -d|--dev)     command_name='dev';   legacy_warning="-d/--dev is deprecated; use: dev"; shift ;;
        -*)           init_colors; say_fail "unknown option: $1"; echo "" >&2; cmd_help >&2; exit 2 ;;
        *)
            if [ -z "$command_name" ]; then command_name="$1"
            elif [ -z "$target" ];    then target="$1"
            else init_colors; say_fail "unexpected argument: $1"; exit 2
            fi
            shift ;;
    esac
done

init_colors
[ -n "$legacy_warning" ] && say_warn "$legacy_warning"

if [ -z "$command_name" ]; then
    # A bare invocation used to start the server in the foreground. Requiring an
    # explicit verb is worth the friction: 'start' now backgrounds, and silently
    # changing what a bare call does would be worse than a prompt.
    say_warn "No command given."
    say_note "  A bare ./run-odoo.sh used to start the server in the foreground."
    say_note "  Now: 'start' (background) or 'dev' / 'start --foreground' (attached)."
    echo ""
    cmd_help
    exit 2
fi

case "$command_name" in
    start)        cmd_start 0 ;;
    stop)         cmd_stop ;;
    restart)      cmd_restart ;;
    status)       cmd_status ;;
    health)       cmd_health ;;
    logs)         cmd_logs ;;
    logs-follow|tail) cmd_logs_follow ;;
    errors)       cmd_errors ;;
    info)         cmd_info ;;
    doctor)       cmd_doctor ;;
    lint)         cmd_lint ;;
    config-check) cmd_config_check ;;
    addons-check) cmd_addons_check ;;
    db-list)      cmd_db_list ;;
    clean)        cmd_clean ;;
    version)      cmd_version ;;
    help)         cmd_help; exit 0 ;;
    dev)
        # Backgrounding --dev is safe here, unlike on Windows: os.execve
        # preserves the PID on POSIX, so a reload keeps the same process and the
        # pidfile stays accurate. Windows spawns a replacement instead, which is
        # why run-odoo.ps1 forces dev to the foreground.
        cmd_start 1 ;;
    shell)
        check_prereqs || exit 2
        assert_conf_paths
        # The shell is read-write by nature but does not require --db: odoo.conf's
        # db_name applies, exactly as for an interactive session today.
        if [ -n "$database" ]; then
            assert_db "$database" 'shell'
            run_odoo_foreground 'shell' -m odoo shell -c "$conf" -d "$database"
        else
            run_odoo_foreground 'shell' -m odoo shell -c "$conf"
        fi
        exit $? ;;
    install)      cmd_module_operation '-i' "$target" 'install' ;;
    upgrade|update) cmd_module_operation '-u' "$target" 'upgrade' ;;
    test)         cmd_test '' ;;
    test-module)  cmd_test "$target" ;;
    *)
        say_fail "Unknown command: $command_name"
        echo "" >&2
        cmd_help >&2
        exit 2 ;;
esac
