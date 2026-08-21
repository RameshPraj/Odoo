# Troubleshooting

Symptom first. Every entry has been seen on this project, and each names the evidence rather than
guessing. Start with `doctor` — it is read-only and checks most of what follows in one pass.

## I installed an app but there is no way into it — no tile, nothing in the menus

**Cause, nine times out of ten: it has no app tile to find.** The app switcher lists **root menus**
(menuitems with no `parent=`). A module whose menus all hang off another module's tree contributes no
tile, however much it looks like an application. `application: True` in a manifest does **not** create
one — it only affects how the module is grouped in the Apps list.

So the question to ask is not "did it install" but "**which root menu does it live under**".

**Two real cases from this project**, both reported as missing apps and neither a defect:

| Installed | Where it actually is |
|---|---|
| **Account Financial Reports** (`account_financial_report`) | **Invoicing → Reporting → OCA accounting reports** — General Ledger, Journal Ledger, Trial Balance, Open Items, Aged Partner Balance, VAT Report |
| the same six, again | **Accounting Nepal → Reporting →** *Ledgers* (General Ledger, Trial Balance), *Partner Reports* (Aged Receivable/Payable, Open Items, Partner Ledger), *Taxes and Fiscal* (VAT Report (OCA)) |
| **eCommerce** (`website_sale`) | **Website → eCommerce** → Orders (Orders, Unpaid, Abandoned Carts, Customers) and Products. Settings live separately under **Website → Configuration → eCommerce** |

Those paths were read out of `load_menus()` for the admin user rather than guessed, which
is what the query below is for.

**For eCommerce specifically, a visible menu is not the same as a working shop.** Check
that products are actually published, because nothing else explains an empty storefront
more often:

```python
env['product.template'].search_count([('is_published', '=', True)])   # was 0 of 11 here
env['website'].search([]).mapped('name')
```

A product must be published before it appears in `/shop`. Installing `website_sale`
publishes nothing, so a fresh install has a complete, correctly-menued eCommerce app
and an empty shop.

Two things make the first one especially easy to miss. Community's accounting app is named
**"Invoicing"**, not "Accounting", so people scan past it; and this project *also* ships an
**Accounting Nepal** app, so the natural assumption is that anything accounting-related lives there.

**Diagnose it in one query** rather than hunting through the UI — in `run-odoo.ps1 shell`:

```python
menu = env.ref('account_financial_report.menu_oca_reports')   # the module's own xmlid
while menu:
    print(menu.complete_name, '| groups:', menu.group_ids.mapped('full_name'))
    menu = menu.parent_id
```

That prints the full path *and* every group gating any level of it, which is the other half of the
answer: a menu you have no group for is simply absent, with no error.

**If the path exists but you still cannot see it**, check the groups it named:

```python
user = env['res.users'].search([('login', '=', 'admin')])
env['ir.ui.menu'].with_user(user)._visible_menu_ids()      # what the client will draw
```

Use `_visible_menu_ids()`, not `search()`. `ir.ui.menu.search` does **not** filter by groups, so a
plain search reports every menu as present for every user and tells you nothing.

**The trap worth knowing about, on stock Community:** `account.menu_finance` and its Reporting
subtree are gated on `account.group_account_readonly` / `group_account_invoice`, and stock Community
ships **no way to hold** the first — it has no `privilege_id`, so it never appears on a user form.
The documented consequence is that nobody, administrator included, can see those menus.
`l10n_np_accounting/security/account_groups.xml` fixes it by giving the groups a privilege and making
Administrator imply Accountant, which is why they are visible here. On a database without that module,
this symptom is real and the fix is to grant the group.

## The server starts but no custom module is there

**Symptom.** Odoo runs, the web client loads, and the Nepal menus are missing. Attachments raise
`FileNotFoundError` while the server otherwise looks fine.

**Cause.** A stale `addons_path` or `data_dir` in `odoo.conf` — usually after moving the project
directory. Odoo treats neither as fatal: a missing `addons_path` entry is logged once as
`no such directory ... skipped` at INFO, and a stale `data_dir` surfaces only per attachment, because
`_file_read` catches `OSError` and returns `b''` (`odoo/addons/base/models/ir_attachment.py:151-155`).
**Both failures look like a healthy server.** This is audit finding **OPS-1**.

**Fix.** `run-odoo.ps1 config-check` / `./run-odoo.sh config-check`. Both scripts refuse to start when
any entry is missing and name it. Correct the absolute paths in `odoo.conf` — do **not** quote them,
even though this project's path contains a space.

## An idle server dies after about three minutes, exit code -1

**Symptom.** Windows only. The server exits with `-1` or `4294967295` with nothing in the log but
routine INFO lines. It happens while nothing is using it.

**Cause.** The wall-clock watchdog. In the threaded server `thread.start_time` is stamped once per TCP
*connection*, not per request, so a browser holding a keep-alive connection accrues wall-clock time with
no request in flight — the tell is a flagged thread reported as `(db:n/a) (uid:n/a) (url:n/a)`. Past
`limit_time_real` the watchdog calls `reload()`, which is `os.kill(pid, SIGHUP)`; Odoo shims `SIGHUP` to
`-1` on Windows (`odoo/service/server.py:40`), and `os.kill` with `-1` on Windows is
`TerminateProcess`. The watchdog does not reload the server, it kills it.

**Fix.** `limit_time_real = 0` in `odoo.conf`, which this project already sets. Both scripts explain the
exit code when they see it. On **Linux** `SIGHUP` genuinely re-execs, so restore the watchdog there —
that is finding **OPS-4**, and `doctor` grades it `FAIL` on a production-like host.

## `python -m odoo` says `No module named odoo`

**Cause.** Odoo is **not** pip-installed into this venv. `python -m odoo` resolves only because the
current working directory is the repo root.

**Fix.** Both scripts now set the working directory explicitly. If you are invoking Odoo by hand,
`cd` to the repo root first. The old `run-odoo.ps1` computed the root but never used it for the working
directory, so it silently depended on wherever you happened to be.

## Port 8069 is already in use

**Symptom.** `start` refuses and names the owning process.

**Diagnosis.** `status` distinguishes three cases: our own server already running (use `restart`), our
server alive but not serving (`DEGRADED` — `stop` then `start`), and a **foreign** process holding the
port. In the last case the scripts refuse and do not kill it, because it cannot be proven to be ours.

**Fix.** Stop the other process, or set `ODOO_HTTP_PORT` / `http_port` to a free port. Note
`gevent_port` (8072) too — a conflict there fails at runtime rather than at startup, so `start` only
warns about it.

## `stop` refuses: "pidfile names PID N, but that process is not this project's Odoo"

**This is correct behaviour, not a bug.** Odoo's pidfile self-cleans through `atexit` on a graceful exit
but not after a force kill, so a stale file can outlive the server — and the operating system will
eventually reissue that PID to something unrelated. Killing it would terminate an innocent process.

**Fix.** Confirm Odoo is not running (`status`), then delete `.runtime/odoo.pid`. `start` removes a stale
pidfile automatically; only `stop` refuses, because only `stop` would signal it.

## `stop` refuses: "PID N is running a module install or upgrade"

**Also correct.** `-i`/`-u` interleave DDL, `ir_module_module.state` writes and asset writes across
several commits. PostgreSQL protects each transaction but not the sequence, so an interrupted upgrade can
leave a module stuck in `to upgrade` and a registry that will not load.

**Fix.** Let it finish. If it is genuinely wedged, expect to repair `ir_module_module.state` by hand
afterwards, and take a `pg_dump` first.

## Windows: `stop` says it could not deliver Ctrl-C

**Cause.** Graceful stop on Windows requires an attachable console, which `start` arranges with
`CREATE_NEW_CONSOLE`. A server started some other way — by hand, or by an editor's run button — may have
no console, so there is nothing to signal.

**Effect.** The script says so and falls back to `TerminateProcess`. The database stays consistent
(PostgreSQL is ACID) and an interrupted attachment write is left unreferenced for the filestore GC. The
one real risk is a mail interrupted between the SMTP handoff and its commit, which the next cron pass
re-sends.

**Fix.** Start through the script.

## Tests hang, or `--test-tags` matches nothing, from Git Bash on Windows

**Cause.** MSYS/Git Bash rewrites an argument that begins with `/` into a Windows path, so
`--test-tags /nepali_calendar_core` arrives as `--test-tags C:/Program Files/Git/nepali_calendar_core`
and matches nothing. The test run then reports success over zero tests.

**Fix.** Use PowerShell, or `MSYS_NO_PATHCONV=1`, or the `--test-tags=/module` equals form. The
`test`/`test-module` verbs build the tag list themselves, so this only bites hand-rolled commands.

## `db-list` fails, or Odoo sees an empty database

**Cause.** This machine has several PostgreSQL clusters on different ports: **5433 is PostgreSQL 17,
which `odoo.conf` uses, while 5432 is a separate PostgreSQL 10 instance.** A client that omits `-p`
silently hits the wrong cluster, where the database simply does not exist — which looks like an empty
database rather than an error.

**Fix.** Always pass the port from `odoo.conf`. `db-list` does. `doctor` warns when it sees more than one
installed version. Note also that some `PostgreSQL\<version>\bin` directories here contain no
`psql.exe`; `ODOO_PSQL` overrides discovery.

## `pip` behaves oddly, or points at the wrong interpreter

**Cause.** This venv was created in a previous location — `venv/pyvenv.cfg` still records
`C:\Users\i81129\Downloads\odoo-19.0\venv` — so the generated `Scripts\*.exe` wrappers embed the old
absolute interpreter path.

**Fix.** Use `venv\Scripts\python.exe -m pip`, never `pip.exe`. `doctor` does. Never key anything off
`pyvenv.cfg`'s `command` line.

## `start` times out but the server seems fine

**Cause.** The gate requires HTTP 200 **and** `Modules loaded.` in the log. A cold asset build or a
first-run registry can exceed 90 seconds.

**Fix.** Raise `ODOO_START_TIMEOUT`. If HTTP answered but the log line never appeared, `start` reports
that specifically and treats the server as up, because it is demonstrably serving requests.

## `start` fails and wrote nothing to the log

**Cause.** The failure happened before logging was configured — an unreadable `-c` path, or `python -m
odoo` failing to import. Odoo configures logging in the second statement of `main()`, so almost
everything else lands in the log file.

**Fix.** Reproduce it visibly: `run-odoo.ps1 start -Foreground` or `./run-odoo.sh start --foreground`.
On POSIX, also check `logs/odoo.boot.log`, which captures the detached child's stderr. Windows cannot
capture that stream and keep the console needed for a graceful stop, so `-Foreground` is the tool there.

## `./run-odoo.sh start` refuses because of systemd

**Cause.** `odoo.service` is active or enabled on this host. That unit is the real service; it runs as a
different user, from `/etc/odoo/odoo.conf`, with a different `data_dir`.

**Fix.** Use `sudo systemctl start|stop|restart|status odoo` and `sudo journalctl -u odoo -f`. To run a
development instance deliberately alongside it, `--force` — but expect contention for the port and, if
both configs name the same database, for the database too.

## The log has grown to gigabytes

**Cause.** Odoo has no size-based rotation at any point, and `WatchedFileHandler`/`FileHandler` only
append. This is finding **OPS-6**.

**Fix.** On Linux install [`deploy/logrotate.d/odoo`](../../deploy/logrotate.d/odoo). On Windows the
scripts rotate at start above `ODOO_LOG_MAX_MB` (20 MB by default, keeping 5); rotating a *running*
server there means stop → rename → start, because an open file cannot be renamed. `clean` removes
rotated generations.

## JavaScript tests fail immediately

**Cause.** They drive a real headless Chrome (`odoo/tests/common.py`). No Chrome, no JS tests.

**Fix.** Install Chrome; `doctor` reports whether one was found. `websocket-client` must also be
installed, and the asset bundles pre-built — a cold build can exceed the browser timeout.

## "Unable to find Wkhtmltopdf on this system. The report will be shown in html."

**Cause.** `wkhtmltopdf` is absent. Odoo does not fail — it degrades: `install` state means the
client refuses to download a PDF and renders the report as HTML instead
(`reports/utils.js:73`). The same notification appears for a `broken` binary.

**Fix.** Install it and set `bin_path` — see [`deploy/README.md`](../../deploy/README.md) §1, which
now carries a Windows procedure. Run `doctor` afterwards; it grades the binary rather than merely
finding it.

**If installing it appears to change nothing**, you have hit one of two caches:

| Cache | Where | Clear it by |
|---|---|---|
| `_wkhtml()` is `@functools.lru_cache(1)` | `ir_actions_report.py:88` | **restarting the server** |
| `downloadReport.wkhtmltopdfStatusProm` | `web/.../reports/utils.js:70` | **reloading the browser tab** |

Both. Restarting alone leaves an already-open tab showing the old message.

## PDF renders, but headers and footers are missing

**Cause.** The binary is an **unpatched-Qt** build. Odoo detects this (`is_patched_qt`,
`ir_actions_report.py:106`) but does not act on it — the state is still `ok`, so nothing warns you.
`--header-html` and `--footer-html` are simply ignored. It surfaces as an error only when merging
multiple documents (`:624-628`).

**Fix.** Replace it with a patched build. `wkhtmltopdf --version` must print `(with patched qt)`;
`doctor` now **fails** on this rather than warning.

## PDF renders, but dates are Gregorian where they should be Bikram Sambat

**Cause.** BS in reports comes from a QWeb field-converter override
(`nepali_calendar_core/models/ir_qweb_fields.py:34-76`), so it only reaches dates emitted through
`t-field`, or `t-out` with `t-options={'widget': 'date'}`. A template that calls `.strftime()` or
prints a raw value bypasses it entirely. Several `account_financial_report` templates do — see
**BS-8** in [`BACKLOG.md`](../project-review/BACKLOG.md) for the specific list.

Note also that printed output follows the **company** setting (`bs_report_output`, `bs_digits`), not
the reader's personal preference, by design: a printed invoice must not change depending on who
pressed Print.

## Everything looks fine but a change never took effect

Worth knowing, because it has caught people here before:

- Chart-of-account and tax-tag templates apply **when a company adopts the chart**, not on `-u`. A live
  database can therefore be stale while the template file is correct.
- Translations under the vendored core are destroyed by the only upgrade path (finding **SUP-3**),
  leaving a half-Nepali UI; code strings revert to English while database-stored translations survive.
- `-u` does not re-run a migration whose module version was not bumped.
