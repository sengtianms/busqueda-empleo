#!/usr/bin/env bash
# Detiene la tanda que corre ahora mismo (programada o manual) y la cierra
# al instante con la forma oficial: abortada · proceso desaparecido ·
# orden del operador.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

exec "$REPO/.venv/bin/python" scripts/control_tandas.py detener "$@"
