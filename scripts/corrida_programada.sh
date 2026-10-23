#!/usr/bin/env bash
# Scheduled-run wrapper (decision D54): preflight gate, then the official
# transversal entry point chaining the three active modules (discovery →
# preparation → initial evaluation). A preflight failure aborts the run.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

PY="$REPO/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: virtual environment not found at '$PY' (create it first — see README Prerequisites)." >&2
  exit 127
fi

# Verdict notifications (decision D57): skip, preflight failure, unexpected
# exit, or the run's own verdict read from the official trace are journalled
# and offered as a desktop popup; notifications never alter the result.
# The notification daemon lives in the graphical session, while this service
# has no display environment — but the session bus socket is always at
# $XDG_RUNTIME_DIR/bus, so popups land whenever the user is logged in.
export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/bus"

# Narration: this batch IS the scheduled one; without this mark the run
# would print its friendly narration lines to its journal like a manual
# run (Lote 2). Manual runs don't set it → they narrate in their terminal.
export TANDA_PROGRAMADA="1"

if ! SALIDA_PREVIA=$("$PY" scripts/preflight.py --ia 2>&1); then
  "$PY" scripts/notificar_veredicto.py --fallo "$SALIDA_PREVIA" || true
  exit 1
fi

DESDE="$(date '+%Y-%m-%d %H:%M:%S')"
CODIGO=0
"$PY" -m modules.orchestrator || CODIGO=$?
if (( CODIGO != 0 )); then
  "$PY" scripts/notificar_veredicto.py --fallo "la corrida terminó de forma inesperada (código $CODIGO)" || true
  exit "$CODIGO"
fi
# Best-effort: a notifier failure must never turn a successful run into a
# failed service activation.
"$PY" scripts/notificar_veredicto.py --desde "$DESDE" || true
