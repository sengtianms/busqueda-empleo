#!/usr/bin/env bash
# Sentinel wrapper (Lote 3): watchdog pass over the official trace.
# One invocation = one pass (invoked by the systemd minute timer).
#
# Desktop notifications need the graphical session's bus; the service has
# no display environment, but the session bus socket is always at
# $XDG_RUNTIME_DIR/bus, so popups land whenever the user is logged in
# (same pattern as the scheduled-run wrapper, decision D57).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/bus"

exec "$REPO/.venv/bin/python" scripts/vigilante_tanda.py "$@"
