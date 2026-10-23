#!/usr/bin/env bash
# Barrido a cero: detiene todo residuo en marcha, cierra toda corrida
# abierta, suelta la silla que quede y verifica "nada corriendo".
# Nunca borra datos históricos y nunca desactiva el reloj (eso es pausar).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

exec "$REPO/.venv/bin/python" scripts/control_tandas.py limpiar "$@"
