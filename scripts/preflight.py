"""Chequeo prevuelo del pipeline (D42): valida entorno antes de lanzar una corrida.

Uso:
    python scripts/preflight.py [--db data/job_search.db]

Verifica: configuracion de modulos/orquestador y de la evaluacion manual,
carpeta de trabajo, base escribible, bloqueo de concurrencia y catálogo de
ubicaciones (D83, solo si la preparación está habilitada). No consulta ningun
modelo: la inteligencia artificial ya no interviene en la evaluacion y la de
preparacion es opcional (Fase 4, D76).
Codigo de salida 0 = todo en orden; 1 = hay bloqueos.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.evaluation.nodes.inicio_manual import _carpetas_de_trabajo
from scripts.modelo_catalogo import diagnosticar
from shared.config import load
from shared.persistence import (
    change_path,
    consultar_bloqueo,
    inicializar_si_ausente,
    leer_tabla,
    reset_path,
    sondear_escritura,
)
from shared.utilidades import FORMATO_TIMESTAMP

Resultados = list[tuple[bool, str]]


def _check_config(config: dict[str, Any]) -> Resultados:
    from modules.orchestrator.orchestrator import _validar_configuracion
    from modules.preparation.nodes.inicio import _validar_preparacion
    from shared.evaluacion import validar_evaluacion_manual

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
    detalle_evaluacion = validar_evaluacion_manual(config.get("evaluacion_manual"))
    resultados.append(
        (
            not detalle_evaluacion,
            f"configuracion evaluacion manual: {detalle_evaluacion or 'ok'}",
        )
    )
    resultados.append(_check_carpeta_manual(config))
    return resultados


def _check_carpeta_manual(config: dict[str, Any]) -> tuple[bool, str]:
    """La carpeta de la evaluación manual existe o puede crearla el arranque."""
    seccion = config.get("evaluacion_manual")
    valor = seccion.get("carpeta_base") if isinstance(seccion, dict) else None
    if not isinstance(valor, str) or not valor.strip():
        return False, "carpeta de trabajo evaluacion: configuracion ausente"
    # Misma resolución que usa el arranque del módulo: una ruta relativa
    # se interpreta desde la raíz del proyecto, no desde el directorio actual.
    base = _carpetas_de_trabajo(valor)["base"]
    destino = base if base.is_dir() else base.parent
    if not destino.is_dir():
        return False, f"carpeta de trabajo evaluacion no disponible: {base}"
    try:
        with tempfile.NamedTemporaryFile(dir=destino, prefix=".sonda_", suffix=".tmp"):
            pass
    except OSError as exc:
        return False, f"carpeta de trabajo evaluacion no escribible: {exc}"
    mensaje = (
        "carpeta de trabajo evaluacion disponible"
        if base.is_dir()
        else "carpeta de trabajo evaluacion creable por el arranque"
    )
    return True, f"{mensaje}: {base}"


def _check_base_datos() -> tuple[bool, str]:
    inicializar_si_ausente()
    try:
        sondear_escritura()
    except Exception as exc:  # noqa: BLE001 - diagnostico, no flujo
        return False, f"base de datos no escribible: {exc}"
    return True, "base de datos escribible"


def _check_catalogo(config: dict[str, Any]) -> tuple[bool, str]:
    """Condiciones que el Módulo 2 exige al catálogo (D83; solo lectura)."""
    modulos = (config.get("orquestador") or {}).get("modulos") or []
    if "preparacion" not in modulos:
        return True, "catalogo de ubicaciones: no aplica (preparacion no habilitada)"
    try:
        diagnostico = diagnosticar(leer_tabla("ubicaciones"))
    except sqlite3.OperationalError as error:
        return False, f"catalogo de ubicaciones ilegible: {error}"
    if diagnostico.no_aplica != 1:
        return (
            False,
            f"catalogo incompleto: fila 'no aplica'={diagnostico.no_aplica} (debe ser 1)",
        )
    if diagnostico.filas_pais != 1:
        return (
            False,
            f"catalogo incompleto: filas de solo pais={diagnostico.filas_pais} (debe ser 1)",
        )
    avisos: list[str] = []
    if diagnostico.variantes:
        avisos.append(
            f"{len(diagnostico.variantes)} variantes de escritura (dejan ofertas pendientes)"
        )
    if (
        diagnostico.por_tipo["municipio"] == 0
        and diagnostico.por_tipo["departamento"] == 0
    ):
        avisos.append("sin municipios ni departamentos cargados")
    if avisos:
        return True, (
            f"catalogo de ubicaciones: OK {diagnostico.total} filas; "
            f"aviso: {'; '.join(avisos)}"
        )
    return True, f"catalogo de ubicaciones: OK {diagnostico.total} filas, sin variantes"


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


def ejecutar_preflight() -> tuple[bool, list[str]]:
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
    ok_catalogo, mensaje_catalogo = _check_catalogo(config)
    lineas.append(f"[{'OK ' if ok_catalogo else 'FALLA'}] {mensaje_catalogo}")
    todo_ok = todo_ok and ok_catalogo
    ok_bloqueo, mensaje_bloqueo = _check_bloqueo(config)
    lineas.append(f"[{'OK ' if ok_bloqueo else 'FALLA'}] {mensaje_bloqueo}")
    todo_ok = todo_ok and ok_bloqueo
    return todo_ok, lineas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="ruta alternativa a la base de datos")
    argumentos = parser.parse_args(argv)
    if argumentos.db:
        change_path(Path(argumentos.db))
    try:
        todo_ok, lineas = ejecutar_preflight()
    finally:
        if argumentos.db:
            reset_path()
    print("== PREFLIGHT ==")
    print("\n".join(f"  {linea}" for linea in lineas))
    print("RESULTADO:", "listo para correr" if todo_ok else "hay bloqueos")
    return 0 if todo_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
