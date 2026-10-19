#!/usr/bin/env bash
# Install (or remove) the user-level systemd timer for the scheduled pipeline
# (decision D54). No fixed wall-clock schedule: first run 10 min after boot,
# repeats every 3 h counted from each run, stops when the machine powers off.
#
# Usage:
#   bash scripts/instalar_programador.sh                install + activate now
#   bash scripts/instalar_programador.sh --desinstalar  remove units (stop timer)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIDAD_DIR="$REPO/scripts/systemd"
DESTINO="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICIO="busqueda-empleo.service"
TEMPORIZADOR="busqueda-empleo.timer"

do_install() {
  mkdir -p "$DESTINO"
  install -m 644 "$UNIDAD_DIR/$SERVICIO" "$UNIDAD_DIR/$TEMPORIZADOR" "$DESTINO/"
  systemctl --user daemon-reload
  systemctl --user enable "$TEMPORIZADOR"
  systemctl --user start "$TEMPORIZADOR"
  systemctl --user status "$TEMPORIZADOR" --no-pager -l | head -12 || true
}

do_uninstall() {
  systemctl --user stop "$TEMPORIZADOR" 2>/dev/null || true
  systemctl --user disable "$TEMPORIZADOR" 2>/dev/null || true
  rm -f "$DESTINO/$SERVICIO" "$DESTINO/$TEMPORIZADOR"
  systemctl --user daemon-reload
  echo "Programador retirado (las corridas manuales siguen disponibles)."
}

case "${1:-instalar}" in
  instalar) do_install ;;
  --desinstalar) do_uninstall ;;
  *) echo "Usage: $0 [instalar|--desinstalar]" >&2; exit 2 ;;
esac
