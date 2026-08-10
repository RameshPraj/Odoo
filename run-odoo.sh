#!/usr/bin/env bash
# Start the local Odoo 19 server (Linux/macOS). POSIX counterpart of run-odoo.ps1.
#
#   ./run-odoo.sh                     # start the server
#   ./run-odoo.sh --install account   # install/reinstall a module, then exit
#   ./run-odoo.sh --update account    # upgrade a module after editing it, then exit
#   ./run-odoo.sh --shell             # interactive Python shell with `env` bound
#   ./run-odoo.sh --dev               # start with auto-reload + no asset cache
#
# This is the *development* launcher: it runs in the foreground and stops on
# Ctrl-C. To run Odoo as a managed service, install deploy/odoo.service instead
# and use systemctl -- see deploy/README.md.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python="$root/venv/bin/python3"
conf="$root/odoo.conf"

install_module=""
update_module=""
shell=0
dev=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--install) install_module="${2:?--install needs a module name}"; shift 2 ;;
        -u|--update)  update_module="${2:?--update needs a module name}";  shift 2 ;;
        -s|--shell)   shell=1; shift ;;
        -d|--dev)     dev=1;   shift ;;
        -h|--help)    sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
    esac
done

if [[ ! -x "$python" ]]; then
    echo "venv not found at $python" >&2
    echo "  python3 -m venv venv && ./venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi
if [[ ! -f "$conf" ]]; then
    echo "$conf not found -- copy odoo.conf.example and edit it for this host" >&2
    exit 1
fi

cmd=(-m odoo)
[[ $shell -eq 1 ]] && cmd+=(shell)
cmd+=(-c "$conf")
[[ -n "$install_module" ]] && cmd+=(-i "$install_module" --stop-after-init)
[[ -n "$update_module"  ]] && cmd+=(-u "$update_module"  --stop-after-init)
[[ $dev -eq 1 ]] && cmd+=(--dev reload,qweb,xml)

printf '> python %s\n' "${cmd[*]}"
if [[ -z "$install_module" && -z "$update_module" && $shell -eq 0 ]]; then
    # Report the address actually configured rather than assuming 8069.
    port="$(sed -nE 's/^[[:space:]]*http_port[[:space:]]*=[[:space:]]*([0-9]+).*/\1/p' "$conf" | tail -1)"
    echo "  http://localhost:${port:-8069}"
fi

exec "$python" "${cmd[@]}"
