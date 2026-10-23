"""Finalizar Proceso node of the Preparation flow (ficha M2, terminal node).

Convergence point of all run terminations. Mirror of the Discovery node with
the differences the sheet declares: metrics computed from `eventos` (the offer
`id_corrida` is never overwritten, so preparation traceability lives only in
events), the official M2 motive/state table (including `sin_pendientes` and
`concurrencia`) and closure of the preparation HTTP session. The decoupled
company-enrichment step 6 (H2 stub) was removed by decision D39: enrichment
runs in the Preparación de ofertas node (step 2) since 2026-08-25.

Best-effort semantics (sheet decision B): every step logs and continues; a
closure failure never aborts the termination. Metrics follow decision D36
(DISTINCT `id_oferta` per success code — lot (b) re-emits the success event)
and D30 (`total_sucesos` counts only events written before the termination
event, which is never counted).
"""

from dataclasses import dataclass
from typing import Any

from loguru import logger

from modules.preparation.run_context import RunContext
from shared.persistence import (
    actualizar_corrida,
    contar_distintos,
    contar_filas,
    contar_narracion,
    escribir_evento_seguro,
    liberar_bloqueo,
)
from shared.utilidades import acotar_evidencia, ahora

# Official motive -> `corridas.estado` (sheet states/motives table).
_ESTADOS_POR_MOTIVO: dict[str, str] = {
    "sin_pendientes": "sin_pendientes",
    "corrida_completada": "completada",
    "error_total": "abortada",
    "error_critico": "abortada",
    "aborto": "abortada",
    "concurrencia": "abortada",
}

# Motives whose termination event is a success event (`tipo='suceso'`).
_MOTIVOS_SUCESO = frozenset({"sin_pendientes", "corrida_completada", "concurrencia"})

_CAMPOS_METRICAS = (
    "total_preparadas",
    "total_duplicadas",
    "total_ofertas",
    "total_errores",
    "total_sucesos",
)


@dataclass
class ResultadoFinalizar:
    """Outcome of the Finalizar Proceso node handed to the orchestrator."""

    estado: str
    contexto: RunContext | None = None
    codigo: str = ""
    metricas: dict[str, int] | None = None


def _consultar_metricas(id_corrida: str) -> dict[str, int] | None:
    """Step 1: closure metrics from the run's events (D36/D30); single retry.

    Returns None when both attempts fail: the sheet orders degrading to a
    default `aborto` motive with empty metrics (M2 differs from M1's zeros).
    """
    filtros: dict[str, Any] = {"id_corrida": id_corrida}
    for intento in (1, 2):
        try:
            total_preparadas = contar_distintos(
                "eventos",
                "id_oferta",
                {**filtros, "codigo": "oferta_preparada"},
            )
            total_duplicadas = contar_distintos(
                "eventos",
                "id_oferta",
                {**filtros, "codigo": "oferta_duplicada"},
            )
            # Unión DISTINCT (traspaso 2026-08-25): el total reporta ofertas
            # físicas — una oferta preparada y luego duplicada se cuenta una
            # sola vez, en lugar de la suma literal prep+dup que la contaba
            # dos veces (76 vs 72 reales en la corrida de validación).
            total_ofertas = contar_distintos(
                "eventos",
                "id_oferta",
                {
                    **filtros,
                    "codigo": ["oferta_preparada", "oferta_duplicada"],
                },
            )
            total_errores = contar_filas("eventos", {**filtros, "tipo": "error"})
            # Lote 2: los tics de narración no son sucesos del flujo; se
            # restan para que `total_sucesos` conserve su semántica D30/D36.
            total_sucesos = (
                contar_filas("eventos", filtros)
                - total_errores
                - contar_narracion(id_corrida)
            )
            return {
                "total_preparadas": total_preparadas,
                "total_duplicadas": total_duplicadas,
                "total_ofertas": total_ofertas,
                "total_errores": total_errores,
                "total_sucesos": total_sucesos,
            }
        except Exception as exc:
            logger.error(
                f"Metricas no consultables (intento {intento}/2) | "
                f"run={id_corrida} | {exc}"
            )
    return None


def _resolver_motivo(
    contexto: RunContext | None,
    motivo: str | None,
    metricas: dict[str, int] | None,
) -> str:
    """Motive resolution priority: explicit > pre-fixed on the context >
    derived from metrics (`hubo_candidatas` + counters, sheet step 1).
    """
    if motivo:
        return motivo
    if contexto is not None and contexto.motivo_cierre:
        return contexto.motivo_cierre
    if metricas is not None and contexto is not None:
        exitos = metricas["total_ofertas"]
        if contexto.hubo_candidatas and exitos == 0 and metricas["total_errores"] > 0:
            return "error_total"
        return "corrida_completada"
    # Metrics unavailable and nothing pre-fixed: sheet's default motive.
    return "aborto"


def _escribir_evento_terminacion(
    id_corrida: str, motivo: str, metricas: dict[str, int] | None
) -> None:
    """Step 2: termination event (success or error per motive); never aborts."""
    if metricas is not None:
        evidencia = acotar_evidencia(
            " | ".join(f"{c}={metricas.get(c, 0)}" for c in _CAMPOS_METRICAS)
        )
    else:
        evidencia = "metricas=no_disponibles"
    escribir_evento_seguro(
        {
            "id_corrida": id_corrida,
            "tipo": "suceso" if motivo in _MOTIVOS_SUCESO else "error",
            "codigo": motivo,
            "evidencia": evidencia,
            "marca_temporal": ahora(),
        },
        contexto_log=id_corrida,
    )


def _persistir_cierre_corrida(
    id_corrida: str, estado: str, motivo: str, metricas: dict[str, int] | None
) -> None:
    """Step 3: close the run row with a single retry; never aborts."""
    campos: dict[str, Any] = {
        "estado": estado,
        "fecha_fin": ahora(),
        "motivo_terminacion": motivo,
    }
    if metricas is not None:
        campos.update(metricas)
    for intento in (1, 2):
        try:
            actualizar_corrida(id_corrida, campos)
            return
        except Exception as exc:
            logger.error(
                f"actualizar_corrida fallo (intento {intento}/2) | "
                f"run={id_corrida} | {exc}"
            )
    logger.error(
        f"Corrida no persistida | run={id_corrida} | estado={estado} | {motivo}"
    )


def cerrar_recursos(contexto: RunContext | None) -> None:
    """Step 4: close the preparation HTTP session; errors never abort.

    Public and reusable (mirror of the M1 node): closes `sesion_http`
    (httpx client) best-effort and resets the slot so a second call is a
    no-op.
    """
    if contexto is None:
        return
    if contexto.sesion_http is not None:
        try:
            contexto.sesion_http.close()
        except Exception as exc:
            logger.error(
                f"sesion_http.close() fallo | run={contexto.id_corrida} | {exc}"
            )
        contexto.sesion_http = None
        contexto.ofertas_en_sesion = 0


def _liberar_bloqueo(id_corrida: str) -> None:
    """Step 5: release the concurrency lock; never aborts.

    `liberar_bloqueo` deletes only the rows owned by this run
    (`DELETE WHERE id_corrida = ?`), which satisfies the sheet's
    ownership condition by construction: on the `concurrencia` route this
    run never owns the lock and the delete is a harmless no-op.
    """
    try:
        liberar_bloqueo(id_corrida)
    except Exception as exc:
        logger.error(f"liberar_bloqueo fallo | run={id_corrida} | {exc}")


def finalizar_proceso(
    contexto: RunContext | None,
    motivo: str | None = None,
    id_corrida: str = "",
) -> ResultadoFinalizar:
    """Run the Finalizar Proceso steps in order (sheet functional spec 1-7).

    Args:
        contexto: best-effort run context (may be None or partially corrupt;
            the INICIO error/concurrencia routes close without a context).
        motivo: explicit termination reason routed by the orchestrator; when
            omitted the node consumes `contexto.motivo_cierre` or derives the
            motive from metrics.
        id_corrida: run id used only when no context is available.
    """
    id_corrida = (contexto.id_corrida if contexto is not None else "") or id_corrida

    # Metrics BEFORE the termination event (D30: the closure event is never
    # counted in `total_sucesos`).
    metricas = _consultar_metricas(id_corrida) if id_corrida else None
    motivo_resuelto = _resolver_motivo(contexto, motivo, metricas)
    estado = _ESTADOS_POR_MOTIVO.get(motivo_resuelto, "abortada")

    if id_corrida:
        try:
            _escribir_evento_terminacion(id_corrida, motivo_resuelto, metricas)
        except Exception as exc:
            # Registro crítico local: la terminación nunca aborta.
            logger.error(
                f"Evento de terminacion no persistible | run={id_corrida} | "
                f"motivo={motivo_resuelto} | {exc}"
            )
        _persistir_cierre_corrida(id_corrida, estado, motivo_resuelto, metricas)

    # Sheet's mandatory order: (4) resources -> (5) lock. Step 6 (H2
    # enrichment stub) was removed by D39 — enrichment lives in the
    # Preparación de ofertas node now.
    cerrar_recursos(contexto)
    if id_corrida:
        _liberar_bloqueo(id_corrida)

    if metricas is not None:
        resumen = " | ".join(f"{c}={metricas[c]}" for c in _CAMPOS_METRICAS)
        logger.info(f"Corrida finalizada | run={id_corrida} | motivo={motivo_resuelto} | {resumen}")
    else:
        logger.info(f"Corrida finalizada | run={id_corrida} | motivo={motivo_resuelto}")

    return ResultadoFinalizar(
        estado="ok", contexto=contexto, codigo=motivo_resuelto, metricas=metricas
    )
