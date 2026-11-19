#!/usr/bin/env bash
# Importa lo que devolvió el chat (Fase 4, D76): una orden, sin argumentos.
# Muestra el informe, avisa en el escritorio y devuelve el resultado real.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# El aviso vive en la sesión gráfica; el bus de la sesión está siempre en
# $XDG_RUNTIME_DIR/bus, también al lanzar el comando desde un terminal.
export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/bus"

exec "$REPO/.venv/bin/python" scripts/importar_evaluaciones.py "$@"
