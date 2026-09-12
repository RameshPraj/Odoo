# Host runbook — the Linux deployment at `/var/www/hosts/odoo19`

What this particular host actually runs, how to operate it, and the traps that cost time when it
was built. [`deploy/README.md`](../../deploy/README.md) describes the *reference* layout
(`/opt/odoo`, a dedicated `odoo` user, `/etc/odoo/odoo.conf`). **This host does not use that
layout**, and the differences are deliberate; they are listed in
[What differs from `deploy/README.md`](#what-differs-from-deployreadmemd).

Built 2026-09-11/12. Every fact below was verified on the box, not assumed.

## The stack

| | |
|---|---|
| OS | Ubuntu 24.04.5 LTS (noble), 2 cores, 3.8 GB RAM |
| Python | **3.14.7**, built from source with PGO, `altinstall` to `/usr/local/bin/python3.14` |
| System Python | 3.12.3, **untouched** — `/usr/bin/python3` must stay 3.12 |
| venv | `./venv` (where `run-odoo.sh` probes for it) |
| PostgreSQL | **18.6** from PGDG, cluster `18/main`, **port 5432** |
| DB role | `odoo` — CREATEDB, **not** superuser, scram-sha-256 over loopback |
| Database | `odoo19`, all 19 custom modules installed |
| wkhtmltopdf | 0.12.6.1 **(with patched qt)** at `/usr/local/bin` |
| Web | Apache reverse proxy, **HTTPS on 443** (self-signed), 80 redirects to it |
| Odoo bind | `127.0.0.1:8069` only — never exposed directly |
| Service | systemd unit `odoo.service`, runs as `ubuntu`, enabled at boot |
| Config | `./odoo.conf` (untracked; holds the DB and admin passwords) |

Python 3.14.7 is at the top of the supported range: `odoo/release.py` declares
`MIN_PY_VERSION = (3, 10)` and `MAX_PY_VERSION = (3, 14)`. Every pin in `requirements.txt`
installs as-is on 3.14 — nothing needed changing. `cryptography` ships a stable-ABI (`abi3`)
wheel so it needs no Rust; `gevent`, `psycopg2`, `MarkupSafe`, `python-ldap`, `rjsmin`,
`ofxparse` and `docopt` compile from source successfully.

## Operating it

systemd owns the service. `run-odoo.sh start` deliberately refuses while the unit is active
(`assert_not_systemd_managed`) rather than race it for port 8069.

```bash
sudo systemctl start|stop|restart odoo
sudo systemctl status odoo
sudo journalctl -u odoo -f        # startup and crash output only
./run-odoo.sh logs-follow         # the application log
./run-odoo.sh doctor              # read-only; still works under systemd
```

**Use `restart`, not `reload`.** See [the `ExecReload` trap](#4-execreload-sighup-is-broken-under-python--m-odoo).

> `run-odoo.sh`'s refusal message ends with *"the unit uses `/etc/odoo/odoo.conf`, not this repo's
> `odoo.conf`"*. That sentence is hardcoded for the reference layout and is **untrue here** — this
> host's unit points at the repo's own `odoo.conf`. Both read the same file.

Database work still goes through `run-odoo.sh`, with the server stopped and the database named
explicitly:

```bash
sudo systemctl stop odoo
./run-odoo.sh install <module> --db odoo19
./run-odoo.sh upgrade <module> --db odoo19
./run-odoo.sh test --db odoo19
sudo systemctl start odoo
```

## Traps

Each of these cost real time. They are ordered by how easy they are to hit.

### 1. Never start Odoo with `sudo`

`check_root_user()` (`odoo/cli/server.py:31-34`) only writes a warning to stderr — it does **not**
refuse. A root-started Odoo writes root-owned filestore entries, sessions and pidfile, after which
`run-odoo.sh stop` fails with *"port 8069 is in use, but its owner could not be identified"* and
later non-root runs break on files they cannot read. Recovery:

```bash
sudo ./run-odoo.sh stop
sudo chown -R ubuntu:ubuntu .odoo_data .runtime logs
```

### 2. apt's wkhtmltopdf is the wrong build

`apt install wkhtmltopdf` gives 0.12.6 **without patched Qt**. `run-odoo.sh doctor` *fails* on it
(not warns), because unpatched Qt silently drops report headers and footers with nothing in the
log explaining why. Use the jammy `.deb` 0.12.6.1-3 from `wkhtmltopdf/packaging` — no noble build
exists. Its `libssl3` / `libpng16-16` dependencies resolve on noble only because the t64 packages
declare `Provides:` for the old names. Verify on the host: `wkhtmltopdf --version` must print
`(with patched qt)`.

### 3. `workers = 0` changes which port serves the websocket

`odoo.conf` sets `workers = 0` — the reference template's `(cores * 2) + 1` = 5 would badly
overcommit 3.8 GB at ~1 GB each, and `--test-enable` runs in-process anyway.

Consequence: Odoo only opens the dedicated `gevent_port` (8072) in **multiprocessing** mode. The
threaded server serves `/websocket` on the main HTTP port. The Apache vhost therefore proxies
`/websocket` to **8069**. Pointing it at 8072 under `workers = 0` gives
`AH00957: ws: attempt to connect to 127.0.0.1:8072 failed` and a 503 on every websocket request.

**If `workers` is ever raised above 0, the vhost must be changed back to 8072** or it breaks the
other way. The coupling is commented in `/etc/apache2/sites-available/odoo19.conf`.

### 4. `ExecReload` (SIGHUP) is broken under `python -m odoo`

`deploy/odoo.service` ships `ExecReload=/bin/kill -HUP $MAINPID`. Odoo *does* handle SIGHUP — it
logs `Initiating server reload` — but the re-exec then dies with:

```
ImportError: attempted relative import with no known parent package
```

`_reexec()` (`odoo/service/server.py:1526`) rebuilds the command from `sys.argv` via
`stripped_sys_argv()` (`odoo/tools/misc.py:834-850`), which **drops `-m odoo` and rewrites
`argv[0]`** — a mechanism `run-odoo.sh:260-263` already documents for a different reason. Under
`-m odoo`, `argv[0]` is the path to `odoo/__main__.py`, so the re-exec runs that file directly
instead of as a module and its relative imports fail.

`Restart=on-failure` **masks** this: `systemctl reload` appears to work while logging a traceback
and adding ~5s of downtime. This host's unit therefore has **no `ExecReload`**, so `reload` fails
fast and harmlessly. Use `restart`.

`setup/odoo` is not a usable alternative entry point: run as `python3 setup/odoo`, `sys.path[0]`
becomes `setup/` and `import odoo.cli` fails.

### 5. `Requires=postgresql.service` does not guarantee a database

On Ubuntu/PGDG, `postgresql.service` is a `Type=oneshot` wrapper that reports "exited" as soon as
it has queued the cluster. Depend on the real cluster unit — `postgresql@18-main.service` — or
Odoo can start before PostgreSQL accepts connections on boot.

### 6. `logfile` in `odoo.conf` silently defeats skip reporting

`run_odoo_tee` tees **stdout** to `.runtime/last-test-run.log`, but with `logfile` set, Odoo logs
to that file instead — so the transcript holds no log lines at all (220 bytes on this host) and
`report_skips()` finds **0 skips when 5 really occurred**. `--fail-on-skip` is defeated the same
way, so CI relying on it would never catch a skipped suite.

This is exactly the TST-3 / CI-1 blind spot the script exists to close: *a run that skipped
everything looks identical to a run that passed everything*. **Read skips from `logs/odoo.log`,
not the transcript:**

```bash
grep -a ': skipped ' logs/odoo.log
```

Unresolved tension: `doctor` *warns* when `logfile` is unset, so satisfying doctor breaks skip
reporting. Either `report_skips()` should read the configured logfile, or `logfile` should be
unset during test runs.

### 7. Never pipe `run-odoo.sh start`

The nohup'd daemon ends up a direct child of the script, so a pipeline (`start | tail`) never sees
EOF and hangs forever even though the server is up and healthy. Redirect to a file instead. If it
happens, `kill` the wrapper PID only — the daemon reparents to init and keeps serving.

### 8. A readiness check must test the HTTP status

`curl -o /dev/null` exits 0 on a 502/503, so `until curl ...; do sleep; done` returns the instant
Apache answers with a proxy error. Test the code:

```bash
until [ "$(curl -sk -o /dev/null -w '%{http_code}' https://<host>/web/health)" = "200" ]; do sleep 3; done
```

Getting this wrong also sends signals during startup: a SIGHUP arriving before Odoo installs its
handler in `start()` (`odoo/service/server.py:644`) hits the kernel default and kills the process
outright (`code=killed, signal=HUP`).

## TLS and the reverse proxy

Apache terminates TLS; Odoo never faces the internet. Vhost:
`/etc/apache2/sites-available/odoo19.conf` (the stock `000-default.conf` is disabled).

- Certificate: **self-signed**, `/etc/ssl/certs/odoo19-selfsigned.crt`, key `0640 root:ssl-cert`,
  valid to 2036. Browsers show a warning; it protects against passive interception only.
- `subjectAltName=IP:<addr>` is **mandatory**, not decorative — browsers dropped CN-based name
  matching, and for an IP the SAN must be the `IP:` form.
- `RequestHeader set X-Forwarded-Proto "https"` on the 443 vhost, with `proxy_mode = True` in
  `odoo.conf`. Left as `http`, Odoo emits `http://` redirects that bounce users out of TLS.
  Verify: `curl -sk -o /dev/null -w '%{redirect_url}' https://<host>/` must print an `https://`
  target.
- **No HSTS**, deliberately: with a self-signed cert it turns the click-through warning into a
  hard block with no bypass, locking everyone out. Add it only with a trusted certificate.
- `/.well-known/acme-challenge/` is served from `/var/www/acme` and excluded from the redirect, so
  moving to a real certificate needs no port-80 changes.

`web.base.url` must match the public scheme. It is recorded at first startup and was `http://`
until corrected; a stale value sends password-reset links to plain HTTP. It is now
`https://<host>` with `web.base.url.freeze = True` so an admin login cannot silently reset it.

### Replacing the self-signed certificate

Let's Encrypt **does** now issue certificates for bare IP addresses (generally available
2026-01-15; Certbot 5.4+). The lifetime is a mandatory ~160 hours, so renewal must be reliable,
and the apache plugin does not support IPs — use `--webroot` with a `--deploy-hook`:

```
certbot certonly --preferred-profile shortlived --webroot \
  --webroot-path /var/www/acme --ip-address <addr>
```

A domain remains the more forgiving option (90-day certs). `nip.io` / `sslip.io` are **not** a
workaround: neither is on the Public Suffix List, so Let's Encrypt's per-registered-domain rate
limit is shared across the whole domain and is effectively exhausted.

## Changing a user's password

Not via **"My Odoo.com Account"** in the avatar menu — that is `odooAccountItem`
(`odoo/addons/web/static/src/webclient/user_menu/user_menu_items.js:76`), which opens
`accounts.odoo.com` and has nothing to do with local users.

- **Your own:** avatar → *My Preferences* → **Security** tab → *Change password*. Odoo asks for
  your current password first (`@check_identity`, valid 10 minutes).
- **Someone else's, as admin:** Settings → Users & Companies → Users → open the user → **Security**
  tab → *Change password*.

Both buttons share the label; Odoo swaps which renders via `invisible="id != uid"` /
`invisible="id == uid"` (`res_users_views.xml:207-210`).

## What differs from `deploy/README.md`

| | Reference layout | This host |
|---|---|---|
| Install path | `/opt/odoo` | `/var/www/hosts/odoo19` (the checkout itself) |
| Service user | dedicated `odoo` | `ubuntu` — already owns the venv, filestore and repo |
| Config | `/etc/odoo/odoo.conf` | `./odoo.conf` in the repo (untracked) |
| `data_dir` | `/var/lib/odoo` | `./.odoo_data` |
| Logs | journal | `./logs/odoo.log`, so `run-odoo.sh logs`/`errors` keep working |
| `workers` | `(cores * 2) + 1` | `0` — see [trap 3](#3-workers--0-changes-which-port-serves-the-websocket) |
| PostgreSQL dep | `postgresql.service` | `postgresql@18-main.service` — see [trap 5](#5-requirespostgresqlservice-does-not-guarantee-a-database) |
| `ExecReload` | present | **removed** — see [trap 4](#4-execreload-sighup-is-broken-under-python--m-odoo) |

Running as `ubuntu` rather than a dedicated account is the one deliberate weakening: `ubuntu` is a
sudo-capable login, so the service is not isolated from it. It was chosen to avoid an ownership
migration across the venv, filestore and repo. On an internet-facing host a dedicated `odoo` user
is the better posture and is worth revisiting.

## Known gaps

- **No firewall.** `ufw` is inactive and the iptables `INPUT` policy is `ACCEPT`, on a host with a
  directly-attached public IP. Ports are open by default.
- **Self-signed certificate**, so browsers warn and there is no protection against an active
  man-in-the-middle.
- **Secrets live only in `./odoo.conf`** (untracked, mode 0640). It holds the only copy of the
  generated database and `admin_passwd` values. If this box is lost, they are lost.
