"""INICIO and candidate-decision nodes of the Evaluation flow (ficha M3 v1.0).

Two nodes implemented here:

1. Process INICIO (v1.0): instantiates the run (id_corrida with a single
   retry, ERR-01), loads and validates the whole `evaluacion:` section plus
   the existing `ai_routing.evaluation` route (VAL-02; ERR-02/03/04),
   verifies the database with a rolled-back write probe (VAL-03, ERR-05),
   REGISTERS THE RUN ROW right after the probe and before the lock attempt
   (mirror of sub-phase 5.5 P2-A: every registered run is closable by
   Finalizar Proceso), resolves the shared global concurrency lock kept with
   Modules 1 and 2 (RN-02; ERR-06/07/08/09), loads the FIFO candidates from
   `ofertas_descubiertas` in state `preparada` (VAL-06, ERR-05), initializes
   the run state, then delivers a complete RunContext (VAL-05).
2. Decision "Hay ofertas por procesar" (v1.0): pure in-memory evaluation of
   the candidate list (RN-01 forbids re-reading the database). An empty list
   fixes the controlled-termination motive `sin_pendientes` on the context
   (VAL-04); this node never registers (RN-05) — "Finalizar Proceso"
   consumes and records it.

Mandatory sheet order: configuration before database; candidates after
database and lock. The node never touches the AI service (VAL-05/RN-05 of
the sheet: INICIO does not probe the AI), platforms or credentials. Errors
ERR-01..ERR-04 are logged only with Loguru (database not connected yet);
events that can reach the `eventos` table fall back to Loguru when the store
rejects them.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import yaml
from loguru import logger

from modules.evaluation.run_context import RunContext
from shared.config import load
from shared.evaluacion import validar_evaluacion
from shared.narrador import narrar_modulo
from shared.persistence import (
    adquirir_bloqueo,
    consultar_bloqueo,
    generar_id,
    init_db,
    leer_candidatas_preparadas,
    registrar_corrida,
    registrar_evento,
    sondear_escritura,
    umbral_obsolescencia_minutos,
)
from shared.utilidades import FORMATO_TIMESTAMP, ahora


@dataclass
class ResultadoInicio:
    """Outcome of the INICIO node handed to the orchestrator."""

    estado: str
    id_corrida: str = ""
    contexto: RunContext | None = None
    codigo: str = ""
    descripcion: str = ""


@dataclass
class ResultadoDecisionCandidatas:
    """Outcome of the candidate decision ("si" / "no" branches)."""

    estado: str  # "ok" | "error"
    decision: str = ""  # "si" | "no"
    contexto: RunContext | None = None
    codigo: str = ""
    descripcion: str = ""


def _generar_id_corrida() -> str:
    for intento in (1, 2):
        try:
            return generar_id("corridas")
        except Exception:
            if intento == 2:
                raise
    raise RuntimeError("unreachable")  # pragma: no cover


def _es_obsoleto(marca_temporal: datetime, umbral_minutos: int) -> bool:
    """Mirrors `shared.persistence.adquirir_bloqueo` staleness semantics."""
    if umbral_minutos <= 0:
        return False
    antiguedad = (datetime.now() - marca_temporal).total_seconds() / 60
    return antiguedad >= umbral_minutos


def _tic_modulo_iniciado(id_corrida: str) -> None:
    """Lote 2: tic de arranque del módulo (excluido de métricas por narración)."""
    registrar_evento(
        id_corrida=id_corrida,
        tipo="suceso",
        codigo="tic_modulo_iniciado",
        evidencia="modulo=evaluacion",
    )


def ejecutar_inicio(config: dict[str, Any] | None = None) -> ResultadoInicio:
    """Run the INICIO node steps in order (sheet pasos funcionales 1-7)."""
    # Paso 1 — instancia de corrida con reintento unico.
    try:
        id_corrida = _generar_id_corrida()
    except Exception as exc:
        logger.error(f"ERR-01 | id_corrida generado dos veces con fallo | {exc}")
        return ResultadoInicio(
            estado="error",
            codigo="ERR-01",
            descripcion="id_corrida generation failed after a single retry",
        )

    # Paso 2 — configuración global (orden obligatorio: antes que BD).
    try:
        if config is None:
            config = load()
        if not isinstance(config, dict):
            raise ValueError("configuration root is not a mapping")
        problema = validar_evaluacion(config.get("evaluacion"), config)
        if problema is not None:
            raise ValueError(f"seccion evaluacion invalida: {problema}")
    except FileNotFoundError:
        logger.error(f"ERR-02 | run={id_corrida} | configuration file missing")
        return ResultadoInicio(
            estado="error",
            id_corrida=id_corrida,
            codigo="ERR-02",
            descripcion="configuration file missing",
        )
    except OSError:
        logger.error(f"ERR-03 | run={id_corrida} | configuration file unreadable")
        return ResultadoInicio(
            estado="error",
            id_corrida=id_corrida,
            codigo="ERR-03",
            descripcion="configuration file unreadable",
        )
    except (ValueError, yaml.YAMLError):
        logger.error(f"ERR-04 | run={id_corrida} | configuration corrupt or inconsistent")
        return ResultadoInicio(
            estado="error",
            id_corrida=id_corrida,
            codigo="ERR-04",
            descripcion="configuration missing, corrupt or out of range (VAL-02)",
        )

    # Paso 3 — verificación de BD (prueba de escritura con rollback).
    try:
        init_db()
        sondear_escritura()
    except Exception as error:
        registrar_evento(
            id_corrida=id_corrida,
            tipo="error",
            codigo="ERR-05",
            evidencia=f"base de datos no disponible: {error}",
        )
        logger.error(f"ERR-05 | run={id_corrida} | database unavailable | {error}")
        return ResultadoInicio(
            estado="error",
            id_corrida=id_corrida,
            codigo="ERR-05",
            descripcion="database unavailable or not writable",
        )

    # Paso 3b — registro de la corrida tras el sondeo de BD y ANTES del
    # intento de bloqueo, de modo que toda terminación posterior (incluida
    # la ruta concurrencia) deja una fila en `corridas` que "Finalizar
    # Proceso" puede cerrar.
    marca_inicio = ahora()
    try:
        registrar_corrida(
            {
                "id_corrida": id_corrida,
                "fecha_inicio": marca_inicio,
                "estado": "en_ejecucion",
            }
        )
    except Exception as error:
        registrar_evento(
            id_corrida=id_corrida,
            tipo="error",
            codigo="ERR-05",
            evidencia=f"fallo al registrar la corrida: {error}",
        )
        logger.error(f"ERR-05 | run={id_corrida} | run registration failed | {error}")
        return ResultadoInicio(
            estado="error",
            id_corrida=id_corrida,
            codigo="ERR-05",
            descripcion="run registration failed",
        )

    # Paso 4 — bloqueo global compartido con los Módulos 1 y 2 (RN-02).
    try:
        bloqueo_actual = consultar_bloqueo()
    except Exception as error:
        registrar_evento(
            id_corrida=id_corrida,
            tipo="error",
            codigo="ERR-08",
            evidencia=f"estado de bloqueo no decidible: {error}",
        )
        logger.error(f"ERR-08 | run={id_corrida} | lock state undecidable | {error}")
        return ResultadoInicio(
            estado="error",
            id_corrida=id_corrida,
            codigo="ERR-08",
            descripcion="lock state undecidable",
        )

    marca_temporal = ahora()
    if bloqueo_actual is not None:
        try:
            fecha_bloqueo = datetime.strptime(
                str(bloqueo_actual.get("marca_temporal", "")), FORMATO_TIMESTAMP
            )
        except (TypeError, ValueError):
            registrar_evento(
                id_corrida=id_corrida,
                tipo="error",
                codigo="ERR-08",
                evidencia="marca_temporal del bloqueo no valido",
            )
            return ResultadoInicio(
                estado="error",
                id_corrida=id_corrida,
                codigo="ERR-08",
                descripcion="lock marca_temporal undecidable",
            )
        if not _es_obsoleto(fecha_bloqueo, umbral_obsolescencia_minutos(config)):
            registrar_evento(
                id_corrida=id_corrida,
                tipo="suceso",
                codigo="ERR-06",
                evidencia=(
                    f"corrida {bloqueo_actual.get('id_corrida', '')} activa; "
                    "terminacion por concurrencia"
                ),
            )
            return ResultadoInicio(
                estado="concurrencia",
                id_corrida=id_corrida,
                codigo="ERR-06",
                descripcion="another run is active (lock not stale)",
            )
        try:
            adquirido = adquirir_bloqueo(id_corrida, marca_temporal, forzar=True)
        except Exception as error:
            registrar_evento(
                id_corrida=id_corrida,
                tipo="error",
                codigo="ERR-08",
                evidencia=f"fallo al sobrescribir: {error}",
            )
            return ResultadoInicio(
                estado="error",
                id_corrida=id_corrida,
                codigo="ERR-08",
                descripcion="lock overwrite failed (undecidable state)",
            )
        if not adquirido:
            registrar_evento(
                id_corrida=id_corrida,
                tipo="suceso",
                codigo="ERR-06",
                evidencia=(
                    "contienda de adquisicion al sobrescribir: "
                    "otro proceso gano el bloqueo"
                ),
            )
            return ResultadoInicio(
                estado="concurrencia",
                id_corrida=id_corrida,
                codigo="ERR-06",
                descripcion="lock contention at stale overwrite",
            )
        registrar_evento(
            id_corrida=id_corrida,
            tipo="suceso",
            codigo="ERR-07",
            evidencia=(
                f"bloqueo obsoleto de {bloqueo_actual.get('id_corrida', '')} "
                "sobrescrito"
            ),
        )
    else:
        try:
            adquirido = adquirir_bloqueo(id_corrida, marca_temporal)
        except Exception as error:
            registrar_evento(
                id_corrida=id_corrida,
                tipo="error",
                codigo="ERR-08",
                evidencia=f"fallo al adquirir: {error}",
            )
            return ResultadoInicio(
                estado="error",
                id_corrida=id_corrida,
                codigo="ERR-08",
                descripcion="lock acquisition failed (undecidable state)",
            )
        if not adquirido:
            registrar_evento(
                id_corrida=id_corrida,
                tipo="suceso",
                codigo="ERR-06",
                evidencia="contienda de adquisicion: otro proceso gano el bloqueo",
            )
            return ResultadoInicio(
                estado="concurrencia",
                id_corrida=id_corrida,
                codigo="ERR-06",
                descripcion="lock contention race at acquisition",
            )

    # Paso 5 — carga FIFO de candidatas (después de BD y bloqueo).
    try:
        candidatas = leer_candidatas_preparadas()
    except Exception as error:
        registrar_evento(
            id_corrida=id_corrida,
            tipo="error",
            codigo="ERR-05",
            evidencia=f"fallo al cargar candidatas: {error}",
        )
        logger.error(f"ERR-05 | run={id_corrida} | candidate load failed | {error}")
        return ResultadoInicio(
            estado="error",
            id_corrida=id_corrida,
            codigo="ERR-05",
            descripcion="candidate load failed",
        )

    # Paso 6 — inicialización de estado (la fila de la corrida ya existe:
    # se registró en el paso 3b antes del bloqueo).
    try:
        contexto = RunContext(
            config_evaluacion=config["evaluacion"],
            candidatas=candidatas,
            id_corrida=id_corrida,
            fecha_inicio=marca_inicio,
        )
        contexto.bloqueo_adquirido = True
    except Exception as error:
        registrar_evento(
            id_corrida=id_corrida,
            tipo="error",
            codigo="ERR-10",
            evidencia=f"Fallo interno de inicializacion de estado: {error}",
        )
        logger.error(
            f"ERR-10 | run={id_corrida} | internal initialization failure | {error}"
        )
        return ResultadoInicio(
            estado="error",
            id_corrida=id_corrida,
            codigo="ERR-10",
            descripcion="internal run state initialization failure",
        )

    # Paso 7 — VAL-05: contexto completo antes de entregar control.
    if not (
        contexto.id_corrida == id_corrida
        and contexto.bloqueo_adquirido
        and isinstance(contexto.hubo_candidatas, bool)
    ):
        registrar_evento(
            id_corrida=id_corrida,
            tipo="error",
            codigo="ERR-10",
            evidencia="contexto incompleto al entregar control",
        )
        return ResultadoInicio(
            estado="error",
            id_corrida=id_corrida,
            codigo="ERR-10",
            descripcion="incomplete context before handover (VAL-05)",
        )

    _tic_modulo_iniciado(id_corrida)
    narrar_modulo("evaluacion")
    return ResultadoInicio(estado="ok", id_corrida=id_corrida, contexto=contexto)


def hay_ofertas_por_procesar(
    contexto: RunContext | None,
) -> ResultadoDecisionCandidatas:
    """Decision node: "Hay ofertas por procesar" (v1.0)."""
    if contexto is None:
        logger.error(
            "ERR-01 | sin id_corrida | contexto ausente: "
            "no se puede evaluar la existencia de candidatas"
        )
        return ResultadoDecisionCandidatas(
            estado="error",
            codigo="ERR-01",
            descripcion="contexto ausente: no hay candidatas que evaluar",
        )

    lista = contexto.candidatas
    if not isinstance(lista, list):
        registrar_evento(
            id_corrida=contexto.id_corrida,
            tipo="error",
            codigo="ERR-01",
            evidencia="contexto incompleto: la lista de candidatas no es accesible",
        )
        logger.error(
            f"ERR-01 | run={contexto.id_corrida} | candidate list inaccessible"
        )
        return ResultadoDecisionCandidatas(
            estado="error",
            contexto=contexto,
            codigo="ERR-01",
            descripcion="lista de candidatas no accesible en el contexto",
        )

    # Evaluación pura sobre la lista leída por INICIO (RN-01: sin releer BD).
    if len(lista) > 0:
        return ResultadoDecisionCandidatas(
            estado="ok", decision="si", contexto=contexto
        )

    # Rama No (VAL-04): fijar motivo en el propio contexto; "Finalizar
    # Proceso" lo consume y registra (RN-05: este nodo no registra).
    contexto.motivo_cierre = "sin_pendientes"
    contexto.motivo_marca_temporal = ahora()
    return ResultadoDecisionCandidatas(estado="ok", decision="no", contexto=contexto)
