#!/usr/bin/env bash
# OnFailure alert for the scheduled unit (Lote 3). Fires via systemd
# OnFailure= when the unit exits non-zero, so only crash-like deaths reach
# it. The wrapper already notifies its own voluntary failures (preflight
# gate, unexpected chain exit — decision D57); to avoid duplicate popups
# this alert first checks the journal for a recent verdict line ("AVISO")
# from the core unit and stays silent when found.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/bus"

if journalctl --user -u busqueda-empleo.service --since "-15 min" -g 'AVISO \[' -q 2>/dev/null |
    grep -q 'AVISO \['; then
  echo "Aviso ya emitido por el guion de la tanda; no se duplica."
  exit 0
fi

PY="$REPO/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: virtual environment not found at '$PY'." >&2
  exit 127
fi
"$PY" scripts/notificar_veredicto.py --fallo \
  "la unidad del programador falló sin aviso propio (proceso muerto o interrumpido)" || true
