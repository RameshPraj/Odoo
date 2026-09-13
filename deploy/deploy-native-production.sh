#!/usr/bin/env sh
# Promote one immutable main commit into the native Ubuntu systemd Odoo service.
# This is deliberately separate from the Podman staging deployment path.

set -eu

target_sha=${1:?usage: deploy-native-production.sh <commit-sha>}
repo=$(git rev-parse --show-toplevel)
cd "$repo"

test -x venv/bin/python3
test -f odoo.conf
git diff --quiet
git diff --cached --quiet
git cat-file -e "${target_sha}^{commit}"

previous_sha=$(git rev-parse HEAD)

rollback() {
    echo "Deployment failed; restoring ${previous_sha}." >&2
    git checkout --detach "$previous_sha"
    sudo -n /usr/bin/systemctl restart odoo
}

git checkout --detach "$target_sha"

# Requirements are pinned. Install before restarting so a failed dependency
# resolution leaves the running service untouched.
if ! venv/bin/python3 -m pip install --requirement requirements.txt; then
    git checkout --detach "$previous_sha"
    exit 1
fi

if ! sudo -n /usr/bin/systemctl restart odoo; then
    rollback
    exit 1
fi

attempt=0
while [ "$attempt" -lt 30 ]; do
    if curl --fail --silent --show-error --max-time 5 \
        'http://127.0.0.1:8069/web/health?db_server_status=1' >/dev/null; then
        echo "Native production deployment succeeded: ${target_sha}"
        exit 0
    fi
    attempt=$((attempt + 1))
    sleep 2
done

rollback
exit 1
