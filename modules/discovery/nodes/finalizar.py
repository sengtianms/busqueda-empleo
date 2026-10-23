"""Finalizar Proceso node of the Discovery flow (technical sheet, terminal node).

Convergence point of all run terminations. It closes the run deterministically
with best-effort semantics (ficha técnica decisions B): persists the closure
metrics in `corridas` (single retry), writes the termination event, closes the
open Playwright resources, releases the concurrency lock only if this run holds
it, and ends without successors. Failures never abort the closure: each step
logs with Loguru and continues. `should_retry`/`retry_conditional` are not used
here — retries are limited to one manual retry per persistence step.
"""

from dataclasses import dataclass
from typing import Any

from loguru import logger

from modules.discovery.adapters.registry import obtener_adaptador
from modules.discovery.run_context import RunContext
from shared.persistence import (
    actualizar_corrida,
    contar_distintos,
    contar_filas,
    contar_narracion,
    escribir_evento_seguro,
    liberar_bloqueo,
)
from shared.utilidades import ahora

_ESTADOS_POR_MOTIVO: dict[str, str] = {
    "corrida_completada": "completada",
    "sin_fuentes": "sin_fuentes",
    "error_critico": "abortada",
    "aborto": "abortada",
}

_CAMPOS_METRICAS = (
    "total_ofertas",
    "total_errores",
    "total_sucesos",
    "fuentes_procesadas",
)


@dataclass
class ResultadoFinalizar:
    """Outcome of the Finalizar Proceso node handed to the orchestrator."""

    estado: str
    contexto: RunContext | None = None
    codigo: str = ""
    metricas: dict[str, int] | None = None


def consultar_metricas(contexto: RunContext | None) -> dict[str, int]:
    """Counts closure metrics from the database; zeros on any failure.

    Metrics: offers registered in this run, error/success events, and the
    number of distinct sources present in the run's events. A failing query
    degrades to zeros (best-effort, ES-4.5 closure must never abort).

    Semantics of `total_sucesos` (D30): it counts the flow events written
    *before* closure — the termination event is written after counting
    (in `_escribir_evento_terminacion`) and is never included. So the value
    means "success events of the run prior to closing", not the absolute
    event count.
    """
    if contexto is None:
        return {campo: 0 for campo in _CAMPOS_METRICAS}
    id_corrida = contexto.id_corrida
    try:
        total_ofertas = contar_filas(
            "ofertas_descubiertas", {"id_corrida": id_corrida}
        )
        total_errores = contar_filas(
            "eventos", {"id_corrida": id_corrida, "tipo": "error"}
        )
        # Lote 2: los tics de narración no son sucesos del flujo; se restan
        # para que `total_sucesos` conserve su semántica D30 exacta.
        total_sucesos = (
            contar_filas("eventos", {"id_corrida": id_corrida})
            - total_errores
            - contar_narracion(id_corrida)
        )
        fuentes_procesadas = contar_distintos(
            "eventos", "fuente_id", {"id_corrida": id_corrida}
        )
    except Exception as exc:
        logger.error(
            f"Metricas no consultables | run={id_corrida} | {exc} | "
            "se degrada a ceros"
        )
        return {campo: 0 for campo in _CAMPOS_METRICAS}
    return {
        "total_ofertas": total_ofertas,
        "total_errores": total_errores,
        "total_sucesos": total_sucesos,
        "fuentes_procesadas": fuentes_procesadas,
    }


def _persistir_cierre_corrida(
    id_corrida: str, estado: str, motivo: str, metricas: dict[str, int]
) -> None:
    """Step 3: update the run row with a single retry; never aborts."""
    campos: dict[str, Any] = {
        "estado": estado,
        "fecha_fin": ahora(),
        "motivo_terminacion": motivo,
        **metricas,
    }
    for intento in (1, 2):
        try:
            actualizar_corrida(id_corrida, campos)
            return
        except Exception as exc:
            logger.error(
                f"actualizar_corrida fallo (intento {intento}/2) | "
                f"run={id_corrida} | {exc}"
            )
    logger.error(f"Corrida no persistida | run={id_corrida} | estado={estado} | {motivo}")


def _escribir_evento_terminacion(
    id_corrida: str, estado: str, motivo: str, metricas: dict[str, int]
) -> None:
    """Step 4: write the termination event; never aborts."""
    evidencia = " | ".join(
        f"{campo}={metricas.get(campo, 0)}" for campo in _CAMPOS_METRICAS
    )
    escribir_evento_seguro(
        {
            "id_corrida": id_corrida,
            "tipo": "suceso" if estado == "completada" else "error",
            "codigo": motivo,
            "evidencia": evidencia,
            "marca_temporal": ahora(),
        },
        contexto_log=id_corrida,
    )


def cerrar_recursos(contexto: RunContext | None) -> None:
    """Step 5: close open Playwright resources; errors never abort.

    Closes in order: session page (via adapter, `page.close()` fallback),
    browser and Playwright instance; resets the three context fields so a
    second call is a no-op. Reused by the orchestrator when switching
    sources.
    """
    if contexto is None:
        return
    if contexto.handle_sesion is not None:
        try:
            fuente = contexto.fuente_corriente
            if fuente is not None:
                obtener_adaptador(fuente.fuente_id).close_session(
                    contexto.handle_sesion
                )
            else:
                contexto.handle_sesion.close()
        except Exception as exc:
            logger.error(
                f"page.close() fallo | run={contexto.id_corrida} | {exc}"
            )
    if contexto.browser is not None:
        try:
            contexto.browser.close()
        except Exception as exc:
            logger.error(f"browser.close() fallo | run={contexto.id_corrida} | {exc}")
    if contexto.playwright_instance is not None:
        try:
            contexto.playwright_instance.stop()
        except Exception as exc:
            logger.error(
                f"playwright.stop() fallo | run={contexto.id_corrida} | {exc}"
            )
    contexto.handle_sesion = None
    contexto.browser = None
    contexto.playwright_instance = None


def _liberar_bloqueo(id_corrida: str) -> None:
    """Step 6: release the concurrency lock; never aborts."""
    try:
        liberar_bloqueo(id_corrida)
    except Exception as exc:
        logger.error(f"liberar_bloqueo fallo | run={id_corrida} | {exc}")


def finalizar_proceso(
    contexto: RunContext | None, motivo: str
) -> ResultadoFinalizar:
    """Run the Finalizar Proceso node steps in order (section 2 of the sheet).

    Args:
        contexto: best-effort run context (may be None or partially corrupt).
        motivo: official termination reason (`corrida_completada`, `sin_fuentes`,
            `error_critico`, `aborto`).
    """
    estado = _ESTADOS_POR_MOTIVO.get(motivo, "abortada")
    id_corrida = contexto.id_corrida if contexto is not None else ""

    # Métricas antes del evento de cierre (D30): total_sucesos excluye el
    # evento de terminación — ver semántica en consultar_metricas.
    metricas = consultar_metricas(contexto)

    if id_corrida:
        _escribir_evento_terminacion(id_corrida, estado, motivo, metricas)
        _persistir_cierre_corrida(id_corrida, estado, motivo, metricas)

    cerrar_recursos(contexto)
    if id_corrida:
        _liberar_bloqueo(id_corrida)

    return ResultadoFinalizar(
        estado="ok", contexto=contexto, codigo=motivo, metricas=metricas
    )
