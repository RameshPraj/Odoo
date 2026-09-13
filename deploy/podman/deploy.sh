#!/usr/bin/env bash
# Deploy one immutable OCI image to the rootless Podman/Quadlet installation.
# This script runs on the Ubuntu host as the dedicated `odoo` account. GitHub
# Actions reaches it over SSH only after CI succeeds and the target environment
# has released its secrets.
set -euo pipefail

: "${ODOO_IMAGE:?Set ODOO_IMAGE to an immutable ghcr.io image reference}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
quadlet_dir="${XDG_CONFIG_HOME:-$HOME/.config}/containers/systemd"
config_dir="$HOME/.config/odoo"
health_url="${ODOO_HEALTH_URL:-http://127.0.0.1:8069/web/health?db_server_status=1}"

install -d -m 0700 "$quadlet_dir" "$config_dir"

# These files contain no credentials. Credentials stay outside the checkout in
# /etc/odoo and are mounted read-only by the Odoo Quadlet.
install -m 0644 "$repo_root/deploy/podman/odoo.network" "$quadlet_dir/odoo.network"
install -m 0644 "$repo_root/deploy/podman/odoo-db-data.volume" "$quadlet_dir/odoo-db-data.volume"
install -m 0644 "$repo_root/deploy/podman/odoo-filestore.volume" "$quadlet_dir/odoo-filestore.volume"
install -m 0644 "$repo_root/deploy/podman/odoo-db.container" "$quadlet_dir/odoo-db.container"

# The image is passed as data, never evaluated as shell code. Only the exact
# commit-SHA image produced by CI should be supplied by the deployment workflow.
escaped_image="${ODOO_IMAGE//|/\\|}"
sed "s|__ODOO_IMAGE__|$escaped_image|g" \
    "$repo_root/deploy/podman/odoo.container.in" > "$quadlet_dir/odoo.container"
chmod 0644 "$quadlet_dir/odoo.container"

systemctl --user daemon-reload
systemctl --user start odoo-db.service

# Do not start Odoo until PostgreSQL is genuinely accepting connections. A
# systemd dependency orders processes; it does not prove database readiness.
for attempt in $(seq 1 30); do
    if podman healthcheck run odoo-db >/dev/null 2>&1; then
        break
    fi
    if [ "$attempt" -eq 30 ]; then
        echo "PostgreSQL did not become healthy" >&2
        exit 1
    fi
    sleep 2
done

# Pull before stopping the current service: a registry failure must leave the
# known-good release serving traffic. The host authenticates to GHCR once during
# provisioning using a read-only package token; no registry credential crosses
# GitHub Actions on each deploy.
podman pull "$ODOO_IMAGE"
systemctl --user restart odoo.service

for attempt in $(seq 1 30); do
    if curl --fail --silent --show-error "$health_url" >/dev/null; then
        printf 'Deployed and healthy: %s\n' "$ODOO_IMAGE"
        exit 0
    fi
    sleep 2
done

echo "Odoo did not become healthy; inspect: journalctl --user -u odoo.service" >&2
exit 1
