#!/usr/bin/env bash
# Install (or remove) the user-level systemd units of the scheduled pipeline
# (decisions D54 + Lote 3): the hourly/bi-daily run timer plus the sentinel
# timer (one watchdog pass every 2 minutes, Punto 3/D68) and the OnFailure
# desktop alert. No
# fixed wall-clock schedule for runs: first run 10 min after boot, repeats
# every 3 h counted from each run, stops when the machine powers off.
#
# Usage:
#   bash scripts/instalar_programador.sh                install + activate now
#   bash scripts/instalar_programador.sh --desinstalar  remove units (timers)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIDAD_DIR="$REPO/scripts/systemd"
DESTINO="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICIO="busqueda-empleo.service"
TEMPORIZADOR="busqueda-empleo.timer"
UNIDADES=("$SERVICIO" "$TEMPORIZADOR")

# Lote 3: sentinel watchdog (every 2 minutes, Punto 3/D68) + OnFailure alert.
UNIDADES+=(
  "busqueda-empleo-vigilante.service"
  "busqueda-empleo-vigilante.timer"
  "busqueda-empleo-aviso-fallo.service"
)
VIGIA="busqueda-empleo-vigilante.timer"

do_install() {
  mkdir -p "$DESTINO"
  for unidad in "${UNIDADES[@]}"; do
    install -m 644 "$UNIDAD_DIR/$unidad" "$DESTINO/$unidad"
  done
  systemctl --user daemon-reload
  systemctl --user enable "$TEMPORIZADOR" "$VIGIA"
  systemctl --user start "$TEMPORIZADOR" "$VIGIA"
  echo "Programador y sentinel instalados:"
  systemctl --user list-timers --no-pager -l | head -8 || true
}

do_uninstall() {
  systemctl --user stop "$TEMPORIZADOR" "$VIGIA" 2>/dev/null || true
  systemctl --user disable "$TEMPORIZADOR" "$VIGIA" 2>/dev/null || true
  for unidad in "${UNIDADES[@]}"; do
    rm -f "$DESTINO/$unidad"
  done
  systemctl --user daemon-reload
  echo "Programador y sentinel retirados (las corridas manuales siguen disponibles)."
}

case "${1:-instalar}" in
  instalar) do_install ;;
  --desinstalar) do_uninstall ;;
  *) echo "Usage: $0 [instalar|--desinstalar]" >&2; exit 2 ;;
esac
