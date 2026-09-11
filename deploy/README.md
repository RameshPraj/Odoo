# Deploying to a Linux server

`run-odoo.ps1` (Windows) and `run-odoo.sh` (Linux) are **development/operator** launchers. They now
offer `start`/`stop`/`restart`/`status`/`health`/`doctor` and can run Odoo in the background, but they
are still not a service: no supervision, no restart-on-crash, no boot integration. On Linux the service
is systemd, and `odoo.service` here is the unit.

`run-odoo.sh` knows about that unit and **refuses to start when it is active**, rather than racing it
for the port. It never calls `systemctl` for you, because the unit runs as another user from a
different config against a different `data_dir`. Full command reference:
[`docs/operations/ODOO_SERVICE_MANAGEMENT.md`](../docs/operations/ODOO_SERVICE_MANAGEMENT.md).

Nothing in the application code needs changing — the custom modules contain no
platform-specific calls. What changes is the configuration and the process manager.

## 1. Packages

Odoo 19 declares its own supported range in `odoo/release.py`: `MIN_PY_VERSION = (3, 10)` and
`MAX_PY_VERSION = (3, 14)`, and it only warns above the maximum (`odoo/cli/server.py:69-73`).
`requirements.txt` also carries `python_version >= '3.13'` markers, `gevent` among them. So
**3.10 to 3.14** is the supported range; check with `python3 -V`.

> An earlier version of this file said "3.10-3.12 (Odoo 19 does not support 3.13 yet)", which
> contradicted the tree it ships with. `run-odoo.sh doctor` reads the constants rather than
> hard-coding a range, so it cannot go stale the same way.

**Ubuntu 24.04 / 22.04**

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-dev build-essential \
    libxml2-dev libxslt1-dev libldap2-dev libsasl2-dev libjpeg-dev \
    libpq-dev postgresql nodejs npm git
```

**RHEL 9 / Rocky / Alma**

```bash
sudo dnf install -y python3 python3-devel gcc gcc-c++ make \
    libxml2-devel libxslt-devel openldap-devel cyrus-sasl-devel libjpeg-devel \
    libpq-devel postgresql-server nodejs git
sudo postgresql-setup --initdb        # RHEL does not initialise the cluster for you
sudo systemctl enable --now postgresql
```

### wkhtmltopdf

`wkhtmltopdf` is **not** in either distribution's repositories in the patched build Odoo
needs. Without it every PDF report degrades to HTML with the notification "Unable to find
Wkhtmltopdf on this system".

The requirement is not merely "a wkhtmltopdf". An **unpatched-Qt** build passes every check
Odoo makes — `is_patched_qt` is read at `ir_actions_report.py:106` but never changes the
reported state — and then silently drops `--header-html` and `--footer-html`, so reports
render without their headers and footers and nothing says why.

**Linux.** Install **0.12.6.1-3** from the
[packaging releases](https://github.com/wkhtmltopdf/packaging/releases/tag/0.12.6.1-3).
Check the asset list against your target before planning on it — that release is not
comprehensive:

| Target above | Asset in 0.12.6.1-3 |
|---|---|
| RHEL 9 / Rocky 9 / Alma 9 | `wkhtmltox-0.12.6.1-3.almalinux9.x86_64.rpm` |
| Ubuntu 22.04 (jammy) | `wkhtmltox_0.12.6.1-3.jammy_amd64.deb` |
| **Ubuntu 24.04 (noble)** | **none — no noble build exists in any release** |

For 24.04 the jammy `.deb` is what people use in practice, but it is not an official
noble build; confirm `--version` reports patched Qt on the actual host rather than
assuming. Note also that the focal and bionic assets in this release are **ppc64el only** —
there is no amd64 package for either.

**Windows.** 0.12.6.1-3 is **not obtainable**: it publishes Linux packages only. The last
release with any Windows asset is
[**0.12.6-1**](https://github.com/wkhtmltopdf/packaging/releases/tag/0.12.6-1) (2020-06-10),
which offers an MSVC installer and a portable `.7z`. Use the portable archive and point
Odoo at it with `bin_path`, which needs no administrator rights:

```powershell
# Windows' bundled tar is bsdtar/libarchive, which reads 7-Zip -- no 7z install needed.
# Verify with `tar --version` first; PowerShell has no native 7z support, and the `tar`
# inside Git Bash is GNU tar, which cannot read this format.
tar -xf wkhtmltox-0.12.6-1.mxe-cross-win64.7z -C <dest>
```

then in `odoo.conf` — a **directory**, not the executable:

```ini
bin_path = C:\path\to\odoo-19.0\.runtime\bin\wkhtmltopdf\bin
```

`bin_path` is appended to `$PATH` when Odoo resolves a binary (`find_in_path`,
`odoo/tools/misc.py:142-146`), so anything already on `PATH` takes precedence. It can only
be set in the config file: it is a `FileOnlyOption` (`config.py:208`), so there is no
`--bin-path` flag.

**Verify, on either platform:**

```bash
wkhtmltopdf --version     # must print >= 0.12.6 AND "(with patched qt)"
```

`run-odoo.ps1 doctor` / `run-odoo.sh doctor` checks exactly that, looking in `PATH` and then
`bin_path` the way Odoo does, and **fails** rather than warns on an unpatched build.

Two caches make a correct install look like it did nothing. `_wkhtml()` is
`@functools.lru_cache(1)` (`ir_actions_report.py:88`), so **restart the server**; and the web
client memoises the answer on `downloadReport.wkhtmltopdfStatusProm`
(`web/static/src/webclient/actions/reports/utils.js:70`), so **reload the browser tab**.

> **Supply chain.** The wkhtmltopdf packaging repository was archived read-only on
> 2023-08-28 and receives no further releases or security fixes. The 0.12.6-1 release notes
> state explicitly that **no checksums or signatures are provided** for its assets, so the
> Windows binary cannot be verified against anything but TLS to github.com and the signed
> git tag. Odoo 19 has no alternative PDF engine. Tracked as **DEP-6** in
> [`BACKLOG.md`](../docs/project-review/BACKLOG.md).

## 2. User, directories, code

```bash
sudo useradd -r -m -d /var/lib/odoo -s /bin/bash odoo
sudo mkdir -p /opt/odoo /etc/odoo /var/log/odoo
sudo chown -R odoo:odoo /opt/odoo /var/lib/odoo /var/log/odoo

sudo -u odoo git clone <this-repo> /opt/odoo
cd /opt/odoo
sudo -u odoo python3 -m venv venv
sudo -u odoo ./venv/bin/pip install --upgrade pip wheel
sudo -u odoo ./venv/bin/pip install -r requirements.txt
```

`requirements.txt` now covers everything, including `nepali-datetime`. The separate
`pip install nepali_datetime` step that used to be here is gone: it was unpinned,
and it named `l10n_np_bs`, which is now only a compatibility shim.

The package is pinned exactly (`nepali-datetime==1.0.8.5`) in the project-additions
block at the end of `requirements.txt`. It is also declared in
`nepali_calendar_core`'s `external_dependencies`, so if it is ever missing the
module refuses to install rather than failing mid-request — but note that Odoo,
not pip, reads that declaration, which is why the pin is what actually installs it.

`nepali_calendar_core/tests/test_requirements.py` fails if the pin goes missing or
drifts from the installed version, so re-vendoring `requirements.txt` from a newer
Odoo release cannot silently drop it.

## 3. Database role

```bash
sudo -u postgres createuser --createdb odoo
sudo -u postgres createdb --owner=odoo odoo19
```

No password is set: the config uses the local socket and peer authentication, so the `odoo` OS
user maps to the `odoo` role and no credential travels anywhere. The role deliberately is not
a superuser — Odoo refuses to start as `postgres` (`check_postgres_user()` in
`odoo/cli/server.py`).

## 4. Configuration

```bash
sudo cp /opt/odoo/deploy/odoo.conf.linux.example /etc/odoo/odoo.conf
sudo chown odoo:odoo /etc/odoo/odoo.conf
sudo chmod 640 /etc/odoo/odoo.conf          # it holds admin_passwd
sudo -e /etc/odoo/odoo.conf                 # set admin_passwd, workers, dbfilter
```

Differences from the Windows development config that matter:

| Setting | Windows dev | Linux server | Why |
|---|---|---|---|
| `workers` | `0` | `(cores * 2) + 1` | gevent is unavailable on Windows, so multiprocessing is not |
| `limit_time_real` | `0` | `120` | On Windows the watchdog's `reload()` is a hard self-kill; on Linux SIGHUP is real and reloads gracefully |
| `list_db` | `True` | `False` | Stops unauthenticated clients enumerating every database on the cluster. It does **not** close the manager: `/web/database/manager` is `auth="none"` with no `list_db` guard (`web/controllers/database.py:65-69`) and still serves create/drop/backup forms. Block it at the proxy, below |
| `admin_passwd` | default, plaintext | strong, **hashed** | This is the only thing actually guarding the manager. While it verifies as `admin`, any POST to a manager route silently reassigns it to the attacker's value and proceeds (`database.py:73-75`) — finding SAAS-2 |
| `proxy_mode` | unset | `True` | TLS is terminated by nginx in front |
| `data_dir` | `C:\Users\i81129\odoo-data` (**outside** the project tree since DAT-1) | `/var/lib/odoo` | Must be writable and in the unit's `ReadWritePaths`. Moved out of the tree on the dev host because the tree is OneDrive-synced and `data_dir` holds the filestore, session files and any dumps -- see DAT-1 |

## 5. Install the service

```bash
sudo cp /opt/odoo/deploy/odoo.service /etc/systemd/system/odoo.service
sudo -e /etc/systemd/system/odoo.service    # check the paths and the postgresql unit name
sudo systemctl daemon-reload
sudo systemctl enable --now odoo
```

On RHEL with the PGDG packages the PostgreSQL unit is versioned
(`postgresql-17.service`), so update `After=` and `Requires=` to match or the dependency
silently does nothing.

### Commands

```bash
sudo systemctl start odoo
sudo systemctl stop odoo
sudo systemctl restart odoo          # stop, then start
sudo systemctl reload odoo           # SIGHUP: Odoo shuts down cleanly and re-execs
                                     # itself, re-reading config and code. Graceful,
                                     # but a few seconds of downtime, not zero.
sudo systemctl status odoo
sudo journalctl -u odoo -f           # follow the log
sudo journalctl -u odoo --since "10 min ago"
```

Upgrading a module still needs the server stopped, because `-u` takes an exclusive lock:

```bash
sudo systemctl stop odoo
sudo -u odoo /opt/odoo/venv/bin/python3 -m odoo -c /etc/odoo/odoo.conf \
    -u l10n_np_accounting --stop-after-init
sudo systemctl start odoo
```

## 6. Reverse proxy and TLS

Odoo speaks plain HTTP only. Put nginx in front, and give `/websocket` a long read timeout or
live chat and the activity bus will drop:

```nginx
server {
    listen 443 ssl http2;
    server_name accounting.example.com;
    ssl_certificate     /etc/letsencrypt/live/accounting.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/accounting.example.com/privkey.pem;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    client_max_body_size 100m;      # attachments

    location /websocket {
        proxy_pass http://127.0.0.1:8072;   # gevent_port, not http_port
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 720s;
    }
    # The database manager is auth="none" and cannot be switched off in odoo.conf:
    # list_db only hides the database list. A strong hashed admin_passwd is the real
    # guard, but there is no reason to expose create/drop/backup/restore to the
    # internet at all. Deny it here, and reach it over an SSH tunnel if ever needed.
    location ~ ^/web/database/(create|drop|backup|restore|duplicate|change_password) {
        return 404;
    }

    location / {
        proxy_pass http://127.0.0.1:8069;
        proxy_read_timeout 720s;
    }
}
server {
    listen 80;
    server_name accounting.example.com;
    return 301 https://$host$request_uri;
}
```

`proxy_mode = True` in the config is what makes Odoo trust `X-Forwarded-*`. Setting it while
Odoo is directly reachable would let a client spoof its own address, so bind
`http_interface = 127.0.0.1` as the example config does.

## Distribution-specific traps

**RHEL: SELinux.** Enforcing mode blocks nginx from connecting to Odoo, and blocks Odoo from
writing outside the expected contexts. Symptom is a 502 with nothing in Odoo's log:

```bash
sudo setsebool -P httpd_can_network_connect on
sudo semanage fcontext -a -t var_lib_t "/var/lib/odoo(/.*)?"
sudo restorecon -Rv /var/lib/odoo
sudo ausearch -m avc -ts recent          # what actually got denied
```

**RHEL: firewalld.** `sudo firewall-cmd --permanent --add-service=https && sudo firewall-cmd --reload`

**Ubuntu: ufw.** `sudo ufw allow 'Nginx Full'`

**Both: locale.** The Nepali translations and `NPR` formatting need a UTF-8 locale. If
`locale` reports `POSIX`, generate `en_US.UTF-8` (`sudo locale-gen en_US.UTF-8` on Ubuntu,
`sudo localectl set-locale LANG=en_US.UTF-8` on RHEL) or dates and currency render wrongly.

## Before going live

The suite ships **empty rate and form tables** by design, so a chartered accountant must sign
off the chart of accounts, TDS rates, the IRD VAT return layout and depreciation classes
first. Until then: post test transactions freely, **file nothing**. See
`custom_addons/l10n_np_accounting/README.md`.

Also note this is an Odoo **source distribution, not a git checkout of upstream** — there is
no upstream remote, so `git pull` will not bring security patches. Track
<https://github.com/odoo/odoo> releases and apply updates deliberately.
