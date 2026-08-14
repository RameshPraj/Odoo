# Deploying to a Linux server

`run-odoo.ps1` (Windows) and `run-odoo.sh` (Linux) are **development** launchers: they run in
the foreground and stop on Ctrl-C. Neither is a service. On Linux the service is systemd, and
`odoo.service` here is the unit.

Nothing in the application code needs changing — the custom modules contain no
platform-specific calls. What changes is the configuration and the process manager.

## 1. Packages

The system Python must be 3.10–3.12 (Odoo 19 does not support 3.13 yet — check with
`python3 -V`).

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

`wkhtmltopdf` is **not** in either distribution's repositories in the patched build Odoo
needs. Without it every PDF report fails. Install the Odoo-recommended 0.12.6 build from
<https://github.com/wkhtmltopdf/packaging/releases>, then verify:

```bash
wkhtmltopdf --version     # must mention "with patched qt"
```

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
| `list_db` | `True` | `False` | `/web/database/manager` can drop databases |
| `proxy_mode` | unset | `True` | TLS is terminated by nginx in front |
| `data_dir` | `.odoo_data` | `/var/lib/odoo` | Must be writable and in the unit's `ReadWritePaths` |

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
