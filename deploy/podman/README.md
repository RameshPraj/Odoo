# Ubuntu production deployment with rootless Podman

This is the production runtime path. GitHub-hosted Actions build an OCI image;
Ubuntu runs that same immutable image with rootless Podman and systemd Quadlet.
No GitHub Actions runner is installed on the production host.

## One-time server preparation

Create an unprivileged service account and permit its user services to continue
after logout:

```bash
sudo adduser --disabled-password --gecos '' odoo
sudo loginctl enable-linger odoo
sudo apt update
sudo apt install -y podman curl git
sudo -u odoo mkdir -p /home/odoo/.config/containers/systemd /opt/odoo
```

Clone this repository to `/opt/odoo` as `odoo`, using a read-only deploy key or a
GitHub App token. The host must be able to fetch `origin/main`, but must never
hold GitHub write credentials.

Create `/etc/odoo/odoo.conf` from `deploy/odoo.conf.container.example` and
`/etc/odoo/podman.env` from `production.env.example`. Give both files ownership
`root:odoo` and mode `0640`. Their database passwords must match. Configure a
strong hashed `admin_passwd`, `list_db = False`, and the production `dbfilter`.

Authenticate the `odoo` account to the private GHCR package once using a
read-only package token:

```bash
sudo -u odoo podman login ghcr.io
```

Put nginx/TLS in front of `127.0.0.1:8069`; retain the `/web/database/*` deny
rule in `deploy/README.md`. Do not expose Odoo or PostgreSQL directly.

## Automated deployment contract

The local staging instance is deployed automatically from `main` by a dedicated
Windows self-hosted runner labelled `odoo-staging`. The runner pulls the exact
GHCR image produced by the successful quality run, replaces the local staging
container, verifies its localhost health endpoint, and restores the prior image
if the new one is unhealthy. It must run under the same Windows user that owns
the rootless Podman machine. Authenticate that user to private GHCR once with
`podman login ghcr.io`; the runner deliberately reuses that local Podman
credential rather than copying a long-lived registry token into every workflow.

The GitHub `production` environment supplies SSH host, user, private key,
known-hosts entry, and checkout path. Production is a native Ubuntu systemd
service, not a Podman host: its deploy script checks out the approved commit,
installs its pinned Python requirements, restarts `odoo`, checks the loopback
health endpoint, and restores the prior commit if health fails.

This script intentionally does **not** run module upgrades. An Odoo `-u` can
migrate data and needs a matched PostgreSQL/filestore backup plus a reviewed
migration plan. Make that a separate, approved release step until backup and
restore automation has been proven.

## Required GitHub Environment configuration

For native Ubuntu production, create these in `production`:

| Secret | Meaning |
|---|---|
| `DEPLOY_HOST` | Ubuntu host name or address |
| `DEPLOY_USER` | `ubuntu` |
| `DEPLOY_SSH_PRIVATE_KEY` | Deploy-only SSH key |
| `DEPLOY_SSH_KNOWN_HOSTS` | Pinned server host-key line, not `ssh-keyscan` output at deploy time |
| `DEPLOY_PATH` | Checkout path, `/var/www/hosts/odoo19` on this host |

In GitHub, protect `production` with a required reviewer. `staging` may deploy
automatically after a successful merge to `main`.

Production never deploys from a push or merge. An authorised operator opens
**Actions → Manual environment deployment → Run workflow**, selects
`production` from the **Deployment target** dropdown, and approves the protected
`production` environment. The workflow automatically promotes the latest
successfully staged immutable image; the operator does not enter a SHA.

The same workflow can manually redeploy `staging`. Select `staging` and leave
the optional reference blank to deploy current `main`, or supply a specific
main ref. A separate development target is intentionally not offered: this
installation has one local staging instance and no development server.

## Host checks

```bash
sudo -u odoo podman info --format '{{.Host.CgroupsVersion}}'  # must be v2
sudo -u odoo systemctl --user daemon-reload
sudo -u odoo systemctl --user status odoo-db.service odoo.service
sudo -u odoo journalctl --user -u odoo.service -f
```

Quadlet files live under the service user's
`~/.config/containers/systemd/`; systemd generates and manages the resulting
units. See the official Podman Quadlet documentation before changing their
structure.
