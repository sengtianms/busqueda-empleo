#!/usr/bin/env bash
# Mantenedor del catálogo de ubicaciones (D83): una línea, sin consultas.
# Ejemplos:
#   ./scripts/catalogo_ubicaciones.sh listar bogota
#   ./scripts/catalogo_ubicaciones.sh agregar --municipio "Puerto Nuevo" --departamento "Cundinamarca"
#   ./scripts/catalogo_ubicaciones.sh corregir UBI-XXXX --municipio "Nombre correcto"
#   ./scripts/catalogo_ubicaciones.sh fusionar UBI-XXXX UBI-YYYY
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

exec "$REPO/.venv/bin/python" scripts/catalogo_ubicaciones.py "$@"
