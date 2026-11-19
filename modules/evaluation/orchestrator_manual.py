"""Orquestador de los dos flujos del Módulo 3 (Fase 3, D76).

Dos entradas públicas: la exportación (la usará la tanda programada) y la
importación (el comando manual de la Fase 4). Cada una conecta su INICIO, su
decisión, su nodo de proceso y el cierre compartido. Toda corrida registrada se
cierra y devuelve su cierre —incluso en concurrencia o aborto— para que el
comando del operador informe el motivo real; solo se devuelve `None` cuando el
fallo ocurre antes del registro y no hay corrida que cerrar. La ruta de
concurrencia cierra sin tocar el bloqueo ajeno.

Enrutado de motivos (tablas oficiales): fallo de infraestructura/configuración
-> `error_critico`; fallo estructurado de un nodo -> `aborto`; excepción
inesperada -> `aborto`; decisión sin trabajo -> el motivo fijado en el contexto
(`sin_pendientes` / `sin_resultados`); terminación normal -> el cierre deriva
`evaluacion_pendiente` / `corrida_completada` / `error_total` desde los eventos.

Los identificadores son españoles conforme a la excepción de los módulos
funcionales (D49 y D76).
"""

from __future__ import annotations

from typing import Any, Callable, Protocol

from loguru import logger

from modules.evaluation.nodes.exportacion import ejecutar_exportacion
from modules.evaluation.nodes.finalizar_manual import (
    ResultadoFinalizarManual,
)
from modules.evaluation.nodes.finalizar_manual import (
    finalizar_proceso as finalizar_proceso_manual,
)
from modules.evaluation.nodes.importacion import ejecutar_importacion
from modules.evaluation.nodes.inicio_manual import (
    ResultadoDecisionManual,
    ResultadoInicioManual,
    ejecutar_inicio_exportacion,
    ejecutar_inicio_importacion,
    hay_ofertas_preparadas,
    hay_resultados_para_importar,
)
from modules.evaluation.run_context import RunContext
from shared.persistence import inicializar_si_ausente

_PROCESOS = frozenset({"exportacion", "importacion"})
_MOTIVO_ABORTO = "aborto"
_MOTIVO_CRITICO = "error_critico"

# Códigos que significan BD/configuración/carpeta no disponibles (ficha).
_CODIGOS_CRITICOS = frozenset(
    {
        "ERR-01",
        "ERR-02",
        "ERR-03",
        "ERR-04",
        "ERR-05",
        "ERR-08",
        "ERR-09",
        "ERR-10",
        "ERR-11",
    }
)


class _ResultadoNodo(Protocol):
    """Contrato estructural de los resultados de los nodos de proceso."""

    estado: str
    codigo: str
    descripcion: str


_Iniciar = Callable[[dict[str, Any] | None], ResultadoInicioManual]
_Decidir = Callable[[RunContext], ResultadoDecisionManual]
_Procesar = Callable[[RunContext], _ResultadoNodo]


def _motivo_de(resultado: _ResultadoNodo) -> str:
    return (
        _MOTIVO_CRITICO
        if resultado.codigo in _CODIGOS_CRITICOS
        else _MOTIVO_ABORTO
    )


def _terminar(
    contexto: RunContext, proceso: str, motivo: str | None = None
) -> ResultadoFinalizarManual:
    return finalizar_proceso_manual(contexto, proceso, motivo)


def _cerrar_fallo_inicio(
    inicio: ResultadoInicioManual, proceso: str
) -> ResultadoFinalizarManual | None:
    """Cierra toda corrida registrada y devuelve su cierre para informar."""
    if inicio.estado == "concurrencia":
        logger.warning(
            f"Corrida {inicio.id_corrida} no iniciada: otra corrida activa"
        )
        return finalizar_proceso_manual(
            None, proceso, "concurrencia", inicio.id_corrida
        )
    if inicio.estado == "error":
        if not inicio.id_corrida:
            logger.error(
                f"INICIO no entrego corrida | codigo={inicio.codigo} | "
                f"{inicio.descripcion}"
            )
            return None
        logger.error(
            f"INICIO fallo | run={inicio.id_corrida} | codigo={inicio.codigo} | "
            f"{inicio.descripcion}"
        )
        motivo = (
            _MOTIVO_CRITICO
            if inicio.codigo in _CODIGOS_CRITICOS
            else _MOTIVO_ABORTO
        )
        return finalizar_proceso_manual(None, proceso, motivo, inicio.id_corrida)
    return None


def _ejecutar_nodo(
    contexto: RunContext,
    proceso: str,
    nombre: str,
    llamada: Callable[[], _ResultadoNodo],
) -> tuple[_ResultadoNodo | None, ResultadoFinalizarManual | None]:
    """Ejecuta un nodo; en un aborto devuelve también su cierre para informar."""
    try:
        resultado = llamada()
    except Exception as error:
        logger.error(f"{nombre} excepcion | run={contexto.id_corrida} | {error}")
        return None, _terminar(contexto, proceso, _MOTIVO_ABORTO)
    if resultado.estado == "error":
        logger.error(
            f"{nombre} abortado | run={contexto.id_corrida} | "
            f"codigo={resultado.codigo} | {resultado.descripcion}"
        )
        return None, _terminar(contexto, proceso, _motivo_de(resultado))
    return resultado, None


def _flujo(
    proceso: str,
    iniciar: _Iniciar,
    decidir: _Decidir,
    procesar: _Procesar,
    config: dict[str, Any] | None,
) -> ResultadoFinalizarManual | None:
    if proceso not in _PROCESOS:
        raise ValueError(f"proceso desconocido: {proceso}")
    if inicializar_si_ausente():
        logger.info("Esquema de base de datos creado automaticamente")

    inicio = iniciar(config)
    if inicio.estado != "ok":
        return _cerrar_fallo_inicio(inicio, proceso)

    contexto = inicio.contexto
    assert contexto is not None
    logger.info(f"Corrida {contexto.id_corrida} iniciada | proceso={proceso}")

    decision, cierre = _ejecutar_nodo(
        contexto,
        proceso,
        "decision",
        lambda: decidir(contexto),
    )
    if decision is None:
        return cierre
    if getattr(decision, "decision", "") == "no":
        return _terminar(contexto, proceso)

    nodo, cierre = _ejecutar_nodo(
        contexto,
        proceso,
        "proceso",
        lambda: procesar(contexto),
    )
    if nodo is None:
        return cierre
    return _terminar(contexto, proceso)


def ejecutar_flujo_exportacion(
    config: dict[str, Any] | None = None,
) -> ResultadoFinalizarManual | None:
    """Flujo A: exportar lotes y cerrar con `evaluacion_pendiente`."""
    return _flujo(
        "exportacion",
        ejecutar_inicio_exportacion,
        hay_ofertas_preparadas,
        ejecutar_exportacion,
        config,
    )


def ejecutar_flujo_importacion(
    config: dict[str, Any] | None = None,
) -> ResultadoFinalizarManual | None:
    """Flujo B: importar respuestas del chat y cerrar la corrida."""
    return _flujo(
        "importacion",
        ejecutar_inicio_importacion,
        hay_resultados_para_importar,
        ejecutar_importacion,
        config,
    )
