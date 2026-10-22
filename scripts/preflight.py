"""Chequeo prevuelo del pipeline (D42): valida entorno antes de lanzar una corrida.

Uso:
    python scripts/preflight.py [--ia] [--db data/job_search.db]

Verifica: configuracion de modulos/orquestador, base escribible, bloqueo
de concurrencia y (opcional, --ia) disponibilidad del modelo local.
Codigo de salida 0 = todo en orden; 1 = hay bloqueos.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.config import load
from shared.persistence import (
    change_path,
    consultar_bloqueo,
    inicializar_si_ausente,
    reset_path,
    sondear_escritura,
)
from shared.utilidades import FORMATO_TIMESTAMP

Resultados = list[tuple[bool, str]]


def _check_config(config: dict[str, Any]) -> Resultados:
    from modules.orchestrator.orchestrator import _validar_configuracion
    from modules.preparation.nodes.inicio import _validar_preparacion
    from shared.evaluacion import validar_evaluacion

    resultados: Resultados = []
    detalle_orquestador = _validar_configuracion(config.get("orquestador"))
    resultados.append(
        (
            not detalle_orquestador,
            f"configuracion orquestador: {detalle_orquestador or 'ok'}",
        )
    )
    detalle_preparacion = _validar_preparacion(config.get("preparacion"))
    resultados.append(
        (
            not detalle_preparacion,
            f"configuracion preparacion: {detalle_preparacion or 'ok'}",
        )
    )
    detalle_evaluacion = validar_evaluacion(config.get("evaluacion"), config)
    resultados.append(
        (
            not detalle_evaluacion,
            f"configuracion evaluacion: {detalle_evaluacion or 'ok'}",
        )
    )
    return resultados


def _check_base_datos() -> tuple[bool, str]:
    inicializar_si_ausente()
    try:
        sondear_escritura()
    except Exception as exc:  # noqa: BLE001 - diagnostico, no flujo
        return False, f"base de datos no escribible: {exc}"
    return True, "base de datos escribible"


def _check_bloqueo(config: dict[str, Any]) -> tuple[bool, str]:
    fila = consultar_bloqueo()
    if fila is None:
        return True, "bloqueo libre"
    from shared.persistence import umbral_obsolescencia_minutos

    umbral = umbral_obsolescencia_minutos(config)
    marca = datetime.strptime(str(fila["marca_temporal"]), FORMATO_TIMESTAMP)
    minutos = (datetime.now() - marca).total_seconds() / 60
    if minutos >= umbral:
        return (
            True,
            f"bloqueo obsoleto ({int(minutos)} min; se tomara automaticamente)",
        )
    return (
        False,
        f"corrida activa {fila['id_corrida']} ({int(minutos)} min) — espere o libere",
    )


def _check_ia(config: dict[str, Any]) -> tuple[bool, str]:
    import httpx

    routing = config.get("ai_routing") if isinstance(config, dict) else None
    local = routing.get("local", {}) if isinstance(routing, dict) else {}
    host = os.environ.get("OLLAMA_HOST") or (
        str(local.get("host")) if isinstance(local, dict) and local.get("host") else "localhost"
    )
    puerto = int(
        os.environ.get("OLLAMA_PORT")
        or (local.get("port", 11434) if isinstance(local, dict) else 11434)
    )
    try:
        respuesta = httpx.get(f"http://{host}:{puerto}/api/tags", timeout=3.0)
        respuesta.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - diagnostico, no flujo
        return False, f"modelo local inaccesible ({host}:{puerto}): {exc}"
    return True, f"modelo local accesible ({host}:{puerto})"


def ejecutar_preflight(usar_ia: bool = False) -> tuple[bool, list[str]]:
    """Ejecuta todos los chequeos; devuelve (todo_en_orden, lineas)."""
    config = load()
    if not isinstance(config, dict):
        config = {}
    lineas: list[str] = []
    todo_ok = True

    for ok, mensaje in _check_config(config):
        lineas.append(f"[{'OK ' if ok else 'FALLA'}] {mensaje}")
        todo_ok = todo_ok and ok
    ok_bd, mensaje_bd = _check_base_datos()
    lineas.append(f"[{'OK ' if ok_bd else 'FALLA'}] {mensaje_bd}")
    todo_ok = todo_ok and ok_bd
    ok_bloqueo, mensaje_bloqueo = _check_bloqueo(config)
    lineas.append(f"[{'OK ' if ok_bloqueo else 'FALLA'}] {mensaje_bloqueo}")
    todo_ok = todo_ok and ok_bloqueo
    if usar_ia:
        ok_ia, mensaje_ia = _check_ia(config)
        lineas.append(f"[{'OK ' if ok_ia else 'FALLA'}] {mensaje_ia}")
        todo_ok = todo_ok and ok_ia
    return todo_ok, lineas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ia", action="store_true", help="verificar tambien el modelo local")
    parser.add_argument("--db", help="ruta alternativa a la base de datos")
    argumentos = parser.parse_args(argv)
    if argumentos.db:
        change_path(Path(argumentos.db))
    try:
        todo_ok, lineas = ejecutar_preflight(usar_ia=argumentos.ia)
    finally:
        if argumentos.db:
            reset_path()
    print("== PREFLIGHT ==")
    print("\n".join(f"  {linea}" for linea in lineas))
    print("RESULTADO:", "listo para correr" if todo_ok else "hay bloqueos")
    return 0 if todo_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
