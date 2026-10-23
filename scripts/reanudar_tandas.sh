#!/usr/bin/env bash
# Reanuda las tandas automáticas: vuelve a armar el reloj y restaura la
# salud del sistema de tandas (vigía incluido) si quedó suelto.
# Pausar de nuevo: scripts/pausar_tandas.sh
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

exec "$REPO/.venv/bin/python" scripts/control_tandas.py reanudar "$@"
