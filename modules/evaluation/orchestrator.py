"""Orchestrator of the full Evaluation flow (ficha M3).

Connects the four nodes in flow order: INICIO, candidate decision,
Evaluación inicial, always terminating in Finalizar Proceso. Mirror of the
Preparation orchestrator: every node failure routes to a controlled
termination; the run only skips closure when INICIO failed before registering
the run row (no id, nothing closable). Informative milestones use Loguru.

Motive routing (sheet states/motives table):
- INICIO `concurrencia` (ERR-06) -> Finalizar with motive `concurrencia`.
- INICIO error WITH an id (row already registered) -> Finalizar with motive
  `aborto`.
- INICIO error WITHOUT an id (nothing registered) -> report and return.
- Candidate decision "no" -> Finalizar consumes the context's pre-fixed
  `sin_pendientes`.
- Structured node aborts (BD/config codes) -> `error_critico`; unexpected
  exceptions -> `aborto`.
- Normal exit (including the quota-ordered stop, pre-fixed as
  `cupo_agotado` on the context) -> Finalizar derives or consumes the motive.
"""

from typing import Any, Callable, Protocol

from loguru import logger

from modules.evaluation.nodes.evaluacion import ejecutar_evaluacion
from modules.evaluation.nodes.finalizar import (
    ResultadoFinalizar,
    finalizar_proceso,
)
from modules.evaluation.nodes.inicio import (
    ResultadoInicio,
    ejecutar_inicio,
    hay_ofertas_por_procesar,
)
from modules.evaluation.run_context import RunContext
from shared.persistence import inicializar_si_ausente

_MOTIVO_ABORTO = "aborto"
_MOTIVO_CONCURRENCIA = "concurrencia"

# Node abort codes that mean a critical BD/config failure (ficha: `error_critico`).
_CODIGOS_CRITICOS = frozenset({"ERR-01", "ERR-03", "ERR-04", "ERR-09"})


class _ResultadoNodo(Protocol):
    """Structural contract of every node result consumed by the flow."""

    estado: str
    codigo: str
    descripcion: str


def _decision_de(res: _ResultadoNodo) -> str:
    """Reads the `decision` field only decision nodes carry."""
    return str(getattr(res, "decision", ""))


def _terminar(contexto: RunContext, motivo: str | None) -> ResultadoFinalizar:
    """Controlled termination: close the run and log the outcome."""
    resultado = finalizar_proceso(contexto, motivo)
    logger.info(
        f"Corrida {contexto.id_corrida} terminada | motivo={resultado.codigo}"
    )
    return resultado


def _fallo_nodo(contexto: RunContext, nodo: str, resultado: _ResultadoNodo) -> None:
    """Routes a structured node abort to the controlled critical termination."""
    logger.error(
        f"{nodo} abortado | run={contexto.id_corrida} | "
        f"codigo={resultado.codigo} | {resultado.descripcion}"
    )
    _terminar(contexto, "error_critico")


def _ejecutar_nodo(
    contexto: RunContext,
    nombre: str,
    llamada: Callable[[], _ResultadoNodo],
) -> _ResultadoNodo | None:
    """Runs a node; structured aborts -> `error_critico`, exceptions -> `aborto`.

    Returns the node result when it is not an abort, or None after the
    controlled termination.
    """
    try:
        res = llamada()
    except Exception as exc:  # unexpected node crash: aborto
        logger.error(f"{nombre} excepcion | run={contexto.id_corrida} | {exc}")
        _terminar(contexto, _MOTIVO_ABORTO)
        return None
    if res.estado in ("error", "abortada"):
        if res.codigo not in _CODIGOS_CRITICOS:
            # Non-critical structured failure (none today): aborto.
            logger.error(
                f"{nombre} abortado | run={contexto.id_corrida} | "
                f"codigo={res.codigo} | {res.descripcion}"
            )
            _terminar(contexto, _MOTIVO_ABORTO)
            return None
        _fallo_nodo(contexto, nombre, res)
        return None
    return res


def ejecutar_flujo(config: dict[str, Any] | None = None) -> None:
    """Run the complete Evaluation flow; terminates in Finalizar Proceso."""
    if inicializar_si_ausente():
        logger.info("Esquema de base de datos creado automaticamente")
    resultado_inicio: ResultadoInicio = ejecutar_inicio(config)
    if resultado_inicio.estado == "error":
        if resultado_inicio.id_corrida:
            # Row already registered: close it as a controlled abort.
            logger.error(
                f"INICIO fallo | run={resultado_inicio.id_corrida} | "
                f"codigo={resultado_inicio.codigo} | {resultado_inicio.descripcion}"
            )
            finalizar_proceso(
                None, _MOTIVO_ABORTO, resultado_inicio.id_corrida
            )
        else:
            print(
                f"[ERROR] INICIO no entrego corrida | "
                f"codigo={resultado_inicio.codigo} | "
                f"{resultado_inicio.descripcion}"
            )
        return
    if resultado_inicio.estado == "concurrencia":
        logger.warning(
            f"Corrida {resultado_inicio.id_corrida} no iniciada: "
            "otra corrida activa (ERR-06)"
        )
        finalizar_proceso(None, _MOTIVO_CONCURRENCIA, resultado_inicio.id_corrida)
        return

    contexto = resultado_inicio.contexto
    assert contexto is not None
    logger.info(
        f"Corrida {contexto.id_corrida} iniciada | "
        f"{len(contexto.candidatas)} candidatas en cola"
    )

    res_candidatas = _ejecutar_nodo(
        contexto,
        "hay_ofertas_por_procesar",
        lambda: hay_ofertas_por_procesar(contexto),
    )
    if res_candidatas is None:
        return
    if _decision_de(res_candidatas) == "no":
        # The node pre-fixed `sin_pendientes` on the context (VAL-04).
        _terminar(contexto, None)
        return

    res_evaluacion = _ejecutar_nodo(
        contexto, "evaluacion", lambda: ejecutar_evaluacion(contexto)
    )
    if res_evaluacion is None:
        return

    # Normal exit: Finalizar consumes a pre-fixed motive (`cupo_agotado`,
    # set by the evaluation node on quota exhaustion) or derives
    # `corrida_completada`/`error_total` from metrics.
    _terminar(contexto, None)
