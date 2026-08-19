# Odoo service management

One operational interface across Windows and POSIX: `run-odoo.ps1` and `run-odoo.sh` accept the same
verbs, resolve configuration the same way, and return the same exit codes.

**They are a developer/operator convenience layer, not a service manager.** A backgrounded process has
no supervision, no restart-on-crash and no boot integration. On Linux the service is systemd —
`deploy/odoo.service`, documented in [`deploy/README.md`](../../deploy/README.md) — and `run-odoo.sh`
**refuses to start** when it can see that unit is active rather than racing it for the port.

## Quick start

```powershell
.\run-odoo.ps1 start                  # background, waits until healthy
.\run-odoo.ps1 status
.\run-odoo.ps1 logs-follow
.\run-odoo.ps1 stop
```
```bash
./run-odoo.sh start
./run-odoo.sh status
./run-odoo.sh logs-follow
./run-odoo.sh stop
```

Prerequisites: the venv (`py -3.12 -m venv venv` then
`.\venv\Scripts\python.exe -m pip install -r requirements.txt`), a readable `odoo.conf` copied from
`odoo.conf.example`, and a reachable PostgreSQL. `doctor` checks all of it and changes nothing.

## Commands

| Command | Does | Needs a database? |
|---|---|---|
| `start` | Starts in the background and waits until genuinely healthy | no |
| `stop` | Graceful stop, then force after the stop timeout | no |
| `restart` | `status` → `stop` → **verify stopped** → `start` | no |
| `status` | `RUNNING` / `STOPPED` / `DEGRADED`, with PID, uptime, ports, paths, git | no |
| `health` | Real probes; exit code is the contract for automation | no |
| `logs` | Last `-n` lines (default 40) | no |
| `logs-follow` | Streams until Ctrl-C | no |
| `errors` | Recent `WARNING`/`ERROR`/`CRITICAL`/`Traceback` with trailing context | no |
| `doctor` | ~40 read-only checks, each `PASS`/`WARN`/`FAIL`, with a summary | no |
| `info` | Sanitized summary for a bug report | no |
| `config-check` | Validates paths **and** hands the file to Odoo's own parser | no |
| `addons-check` | Lists and validates every `addons_path` entry | no |
| `version` | Odoo, Python, shell, git | no |
| `dev` | `--dev reload,qweb,xml` | no |
| `shell` | Odoo shell with `env` bound | optional |
| `clean` | Removes `__pycache__`, `*.pyc` and rotated logs — nothing else | no |
| `db-list` | **Read-only** list of databases with size and connections | no |
| `install <module>` | Installs a module | **yes** |
| `upgrade <module>` | Upgrades a module | **yes** |
| `test` | Tests every custom module | **yes** |
| `test-module <module>` | Tests one module | **yes** |

### Options

| PowerShell | Bash | Meaning |
|---|---|---|
| `-Db <name>` | `--db <name>` | Target database. Required by `install`/`upgrade`/`test`/`test-module` |
| `-n`, `-Lines <n>` | `-n`, `--lines <n>` | Lines for `logs`/`errors` |
| `-Foreground` | `--foreground` | `start`/`dev` attach to this console instead of detaching |
| `-Timeout <s>` | `--timeout <s>` | Override both the start and stop waits |
| `-NoColor` | `--no-color` | Disable colour (also honours `NO_COLOR`) |
| — | `--force` | Start even though a systemd unit is enabled |
| — | `--unit <name>` | systemd unit name (default `odoo`) |
| `-h`, `-Help` | `-h`, `--help` | Help |

Deprecated but still working, because [`deploy/README.md`](../../deploy/README.md) documents them:
`-Install`/`-i`, `-Update`/`-u`, `-Shell`/`-s`, `-Dev`/`-d`. They now **inherit the database rule** and
print a one-line deprecation.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success, or healthy |
| `1` | Operational failure — unhealthy, not running, stop failed, refused |
| `2` | Usage, configuration or dependency problem |

`install`, `upgrade`, `test`, `test-module`, `dev` and `shell` return **Odoo's own exit code
unchanged**, so a failing test suite is never masked. On Windows, `-1` (`4294967295`) is the
`limit_time_real` watchdog, not a crash — see [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

## Configuration

Resolution order for every value: **CLI flag → environment variable → `odoo.conf` → discovered
default.** Nothing that can be discovered is hard-coded.

| Variable | Default |
|---|---|
| `ODOO_CONF` | `odoo.conf` |
| `ODOO_PYTHON` | `venv\Scripts\python.exe` / `venv/bin/python3` |
| `ODOO_LOG` | `logs/odoo.log` |
| `ODOO_PIDFILE` | `.runtime/odoo.pid` |
| `ODOO_HTTP_PORT` | `http_port` from `odoo.conf`, else 8069 |
| `ODOO_START_TIMEOUT` | 90 seconds |
| `ODOO_STOP_TIMEOUT` | 30 seconds |
| `ODOO_LOG_MAX_MB` | 20 — rotate at start above this size |
| `ODOO_LOG_KEEP` | 5 generations |
| `ODOO_PSQL` | discovered; on Windows the newest `C:\Program Files\PostgreSQL\*\bin\psql.exe` |
| `ODOO_UNIT` | `odoo` (bash only) |
| `NO_COLOR` | any value disables colour |

Read from `odoo.conf` itself, last-occurrence-wins to match Odoo's own parsing: `addons_path`,
`data_dir`, `http_port`, `http_interface`, `gevent_port`, `db_host`, `db_port`, `db_user`, `db_name`,
`workers`, `limit_time_real`, `list_db`, `dbfilter`, `logfile`, `bin_path`.

`bin_path` is a **directory** appended to `$PATH` when Odoo resolves an external binary
(`find_in_path`, `odoo/tools/misc.py:142-146`) — in practice, `wkhtmltopdf`. `doctor` searches `PATH`
first and `bin_path` second, the same order Odoo does, so it grades the binary Odoo will actually
call. It can only be set in the config file, never on the command line (`FileOnlyOption`,
`config.py:208`).

**There is deliberately no default-database variable.** See below.

## Database safety

The project is heading for database-per-tenant, where an implicit target is a data-loss bug rather
than a convenience. So:

- `install`, `upgrade`, `test` and `test-module` **refuse to run without an explicit database.** There
  is no default and no "all databases" mode.
- Database names are validated against `^[A-Za-z0-9_-]+$` and passed as an argv element, never
  interpolated into a shell string.
- Module names are validated against `^[a-z][a-z0-9_]*$` **and** the existence of
  `<addons_path entry>/<name>/__manifest__.py`. Only `addons_path` is searched — a glob over the repo
  root would wrongly accept `l10n_ne/`, which is a translation toolkit, not an addon.
- `db-list` is **read-only**: a `pg_database` catalogue query through `psql`, never Odoo's database
  manager. `/web/database/*` exists to create, duplicate, drop and restore, and these scripts must not
  be able to do any of that even by accident.
- **No command creates, drops, duplicates or restores a database.** There is no `backup` verb either;
  see [`PRODUCTION_READINESS.md`](../project-review/PRODUCTION_READINESS.md#backup-and-restore),
  which records that no backup exists yet.
- `clean` removes only `__pycache__`, `*.pyc` and rotated logs, and only inside `addons_path`. It never
  touches `data_dir`, the filestore, sessions or a database.
- `PGPASSWORD` is exported into the child environment for `psql`, never placed on a command line where
  the process list would expose it to every user on the machine.
- `info`, `status`, `config-check` and `doctor` never print `db_password` or `admin_passwd`.

### Process safety

A process is signalled **only** after its command line is verified to belong to this checkout. The
anchor is the absolute `--pidfile` path the script injects: unique per checkout, and — unlike
`-m odoo` — it survives a `--dev reload` re-exec, which rebuilds argv and drops `-m odoo` entirely.

Odoo's pidfile self-cleans via `atexit` on a graceful exit but **not** after a force kill, so a
lingering file is real evidence of an ungraceful death. Every reading of it is validated:

| Pidfile | Process | Port | Verdict | `stop` does |
|---|---|---|---|---|
| absent | — | free | `STOPPED` | nothing, exit 0 |
| absent | — | busy, not ours | `DEGRADED` | **refuses** — not ours to kill |
| present | dead | free | `STOPPED` (stale) | removes the file, exit 0 |
| present | alive, **not ours** | any | `STOPPED` (PID reused) | **refuses to kill**, exit 1 |
| present | alive, ours | listening | `RUNNING` | graceful stop |
| present | alive, ours | not listening | `DEGRADED` | graceful stop |

The fourth row is the one that matters: a recycled PID is reported and refused, never killed.
`stop` also refuses when the target's command line shows `-i`/`-u`, because an interrupted module
upgrade can leave `ir_module_module.state = 'to upgrade'` and a registry that will not load —
PostgreSQL protects each transaction, not the sequence of them.

## How `start` decides it is healthy

Not a fixed sleep. Two phases, with a liveness check on every iteration:

1. **The pidfile appears.** Odoo writes it late — after `_create_empty_database()` has already
   connected to PostgreSQL (`odoo/cli/server.py:95-119`) — so the commonest local failure, a wrong
   `db_port`, kills the process *before* any pidfile exists. Catching that here takes a second instead
   of the full timeout.
2. **`/web/health` returns 200 and `Modules loaded.` is in the log.** Both, because Odoo spawns HTTP
   before it loads the registry: `http_spawn()` at `odoo/service/server.py:655` versus
   `preload_registries()` at `:708`.

If the process dies at any point, `start` stops waiting immediately and prints **exactly the log bytes
that this attempt appended** — recorded by offset before the spawn, so nothing from the previous run
is mistaken for the current failure.

`/web/health` (`odoo/addons/web/controllers/home.py:172`) is `auth='none'` and `save_session=False`, so
polling it needs no login and does not litter `data_dir/sessions`. With `?db_server_status=1` it also
opens a `postgres` connection and answers 500 when PostgreSQL is unreachable — which tests the
credentials Odoo actually uses rather than a guess at them.

> **Correction to the audit.** [`PRODUCTION_READINESS.md`](../project-review/PRODUCTION_READINESS.md)
> records "Health check | None — **no endpoint**, no probe". The endpoint exists and always did; Odoo 19
> ships `/web/health`. What was missing was a *probe*. `health` is now that probe.

## Stopping: the platforms genuinely differ

**POSIX** has a real graceful stop. `SIGTERM` and `SIGINT` take the same branch in Odoo's handler
(`odoo/service/server.py:469-478`); a second signal forces `os._exit(0)`; `SIGKILL` is the last resort
after `ODOO_STOP_TIMEOUT`.

**Windows** has no `SIGTERM`. Odoo instead installs a console control handler
(`odoo/service/server.py:649-651`), and that handler acts only on codes `2` and `15` — while console
events are `CTRL_C=0`, `CTRL_BREAK=1`, `CTRL_CLOSE=2`. So:

- `CTRL_BREAK` is **not** an option: Odoo ignores it, and CPython's default `SIGBREAK` disposition
  terminates the process abruptly.
- `taskkill` without `/F` is **not** an option: its graceful path looks for a top-level window, and a
  console application's window belongs to `conhost.exe`, not to `python.exe`.
- `CTRL_C` **does** work, because Odoo's handler declines it and CPython's own `SIGINT` handler then
  raises `KeyboardInterrupt` in the main thread — which is sitting in `time.sleep()` inside
  `ThreadedServer.run()` (`:756-762`), where it is caught and `self.stop()` runs.

Delivering it requires a console to attach to, so `start` launches Odoo with **`CREATE_NEW_CONSOLE` +
`SW_HIDE`**: a real console, no visible window, and — verified on this machine — one that does *not*
contain the calling shell. `stop` then re-enters the script as a disposable helper which does
`FreeConsole` → `AttachConsole(pid)` → **verify the caller is not in `GetConsoleProcessList`** →
`SetConsoleCtrlHandler(NULL, TRUE)` → `GenerateConsoleCtrlEvent(CTRL_C_EVENT, 0)`.

That interlock is why this is safe: if the child ever shared the caller's console, the helper refuses
instead of Ctrl-C'ing the developer's terminal.

Success is confirmed by **the pidfile disappearing**, which proves Odoo's `atexit` ran — and therefore
that `logging.shutdown()` and `sql_db.close_all()` ran too. A forced kill is announced loudly and the
script cleans the pidfile itself.

**What an ungraceful kill actually costs**, so the fallback is not mysterious: PostgreSQL is ACID, so
the database stays consistent. An attachment interrupted mid-write is never committed and is therefore
unreferenced, which Odoo's filestore GC collects — garbage, not corruption. Sessions are written with
`os.replace`, which is atomic. The one real at-least-once hazard is outbound mail: a message
interrupted between the SMTP handoff and its commit is re-sent by the next cron pass.

## Logs

`logfile` is unset in `odoo.conf`, so a hand-started Odoo logs to stderr and the output is lost unless
the caller redirects it — which is why `.odoo_data/` accumulated nine hand-redirected log files. These
scripts pass `--logfile` so Odoo owns `logs/odoo.log` and appends across restarts.

Rotation differs, because Odoo's handler choice differs by platform (`odoo/netsvc.py:266-272`):

- **POSIX** gets `WatchedFileHandler`, which reopens after a rename. Use logrotate — a config is
  shipped at [`deploy/logrotate.d/odoo`](../../deploy/logrotate.d/odoo). Do **not** use `copytruncate`;
  it loses lines and is unnecessary here.
- **Windows** gets a plain `FileHandler`, which never reopens, and an open file cannot be renamed. So
  the script rotates **at start**, before Odoo opens the file, keeping `ODOO_LOG_KEEP` generations
  above `ODOO_LOG_MAX_MB`. Rotating a *running* server on Windows means stop → rename → start.

Odoo has no size-based rotation of its own at any point. A long-lived instance with `logfile` set grows
without bound; that is finding **OPS-6** in
[`BACKLOG.md`](../project-review/BACKLOG.md).

## Testing

`test -Db <name>` on PowerShell, `test --db <name>` on the shell script, is the single command that
runs every custom module's suite — the gap recorded as finding **CI-1**, "neither launcher passes
`--test-enable`; there is no single command that runs all eight suites."

Spell the flag per shell. `run-odoo.ps1` does **not** parse the POSIX `--db`; PowerShell binds the
value positionally to `[int] $Lines` and fails with a cast error naming a parameter you did not use.
That is finding **OPS-7**.

It runs **326 tests across 17 modules** and, as of 2026-08-19, **exits 0** — `0 failed, 0 errors`. So
a red run now means something: treat any failure as yours until proved otherwise.

That was not true before 2026-08-19. Until then 15 `date_range` tests errored for a structural reason
(**TST-8**, now fixed): the module depends only on `web`, so its `at_install` tests ran before
`account` was in the registry, and creating a company cascaded a `res.partner` INSERT that omitted
account's NOT NULL `autopost_bills` column. If those errors ever return, the cause is that the
`post_install` tags on `date_range/tests/` were lost — most likely by a vendored-module update. See
`custom_addons/VENDORED.md`.

Both `-u` and `--test-tags` are needed: `--test-enable` alone runs nothing for modules already up to
date, so the modules are updated and the run is scoped to their tags. This modifies the named database,
which is why it demands one explicitly, and it requires the server stopped because `-u` takes an
exclusive registry lock.

The JavaScript suites need a real Chrome; `doctor` reports whether one is present.

## Relationship to systemd

`deploy/odoo.service` is the production service on Linux. It runs as user `odoo`, from
`/etc/odoo/odoo.conf`, with a different `data_dir`, `workers` and `list_db`.

`run-odoo.sh` therefore **detects and refuses** rather than delegating:

| systemd state | `start` does |
|---|---|
| No systemd, or no such unit | proceeds |
| Unit **active** | refuses, exit 1, prints the `systemctl` commands |
| Unit enabled but inactive | refuses unless `--force` |

It never calls `systemctl` on your behalf. Silently turning `start` into `systemctl start odoo` would
launch a different program against different data and would need `sudo` — root escalation inside a
development launcher is its own bug. Detection uses `LoadState` rather than `is-active`, because
`is-active` reports `inactive` for a unit that does not exist and so cannot tell "stopped" from "no such
unit"; it also requires `/run/systemd/system` to exist, since `systemctl` is present in plenty of
containers where systemd is not PID 1.

The port check runs regardless, so a wrong `--unit` guess still cannot cause two servers.

## Recommended production enhancements

These scripts deliberately stop short of being a service manager. What is still missing:

| Item | Why |
|---|---|
| **Windows service wrapper** | Not implemented and not faked. If Odoo must run as a Windows service, wrap it with NSSM or `sc.exe` and manage it there; a hidden background process survives no logoff policy and no reboot |
| **OPS-3** systemd hardening | `ProtectSystem=strict` with explicit `ReadWritePaths`, plus `PrivateDevices`, `RestrictAddressFamilies`, `SystemCallFilter`, `MemoryMax`, `UMask`; service account shell to `nologin` |
| **OPS-5** crash-loop bound | `Restart=on-failure` with `RestartSec=5s` and no `StartLimitBurst` is an indefinite crash loop |
| **OPS-4** restore the watchdog on Linux | `limit_time_real = 0` is correct on Windows and wrong on a server |
| **CI-2** a shared artefact | Dev (Windows, `workers=0`) and prod (Linux, systemd) share none, and `run-odoo.sh` has still never run on Linux |
| Monitoring | [`PRODUCTION_READINESS.md`](../project-review/PRODUCTION_READINESS.md) already prescribes the set: an HTTP health check (now available as `health`), a `data_dir` assertion, an `i18n_extra` file count, a non-zero-VAT check, a rendered-statement check, and per-tenant request/error rates |

## Known limitations

- **`run-odoo.sh` has never run on Linux.** It was written against verified Odoo source behaviour and
  syntax-checked with `bash -n`, and its read-only and refusal paths were exercised in Git Bash — but
  `venv/bin/python3`, `ss`, `lsof`, `psql` and `systemctl` are all absent on the development machine, so
  `start`/`stop`/`health` are unexercised there. **CI-2** stays open.
- Windows `stop` depends on the server having been started **by this script**. A server started another
  way may have no attachable console, in which case `stop` says so and falls back to a forced kill.
- `doctor` grades `wkhtmltopdf` on what the binary reports about **itself** — version and
  `(with patched qt)` — searching `PATH` and then `bin_path`, the order Odoo uses. It cannot verify
  provenance, and upstream publishes no checksum for the Windows build to compare against.
- `status`, `doctor` and `info` write to the console rather than the pipeline, so they are for humans.
  The machine-readable contract is the **exit code**; `logs` and `db-list` do write to stdout.
- Neither script rotates a *running* server's log on Windows, and neither prunes `.odoo_data`.
- Multi-worker Linux deployments (`workers > 0`) run Odoo evented, where `setup_pid_file()` is skipped
  (`odoo/cli/server.py:88`); `status` then falls back to identifying the process by port owner.
