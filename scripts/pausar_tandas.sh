#!/usr/bin/env bash
# Pausa las próximas tandas automáticas: apaga el reloj del programador y
# sobrevive a apagones/reinicios. La tanda en curso termina con normalidad.
# Reactivar: scripts/reanudar_tandas.sh
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

exec "$REPO/.venv/bin/python" scripts/control_tandas.py pausar "$@"
