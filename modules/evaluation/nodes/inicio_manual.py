"""INICIO and decision nodes of the two manual Evaluation processes (M3 v2.0).

The Module 3 redesign (D76) replaces the AI evaluation with two independent
processes that never wait inside a run: the scheduled run exports chat-readable
lots and a manual command imports the answers. This module builds the two
entry points and their decisions; lot writing, file matching and result
application belong to the following sub-phases.

1. Export INICIO (`ejecutar_inicio_exportacion`): instantiates its own run
   (single retry, ERR-01), validates the whole `evaluacion_manual:` section
   (VAL-02; ERR-02/03/04), verifies the database with a rolled-back write
   probe (VAL-03, ERR-05), REGISTERS THE RUN ROW before the lock attempt
   (RN-09: every registered run is closable), resolves the shared global
   concurrency lock kept with Modules 1 and 2 (RN-02; ERR-06/07/08/09),
   prepares the work folders (VAL-05, ERR-10), loads the FIFO candidates from
   `ofertas_descubiertas` in state `preparada` (VAL-07, ERR-05), initializes
   the run state (ERR-11) and hands over a complete context (VAL-06).
2. Decision "¿Hay ofertas preparadas?" (`hay_ofertas_preparadas`): pure
   in-memory check of the candidate list (RN-01 forbids re-reading the
   database). An empty list fixes `sin_pendientes` on the context (RN-04);
   this node never registers (RN-05) — "Finalizar Proceso" consumes it.
3. Import INICIO (`ejecutar_inicio_importacion`): same shared startup, then
   creates the missing folders and verifies read and write access (ERR-10),
   lists `resultados/` sorted by name without reading its content (VAL-07)
   and fixes `hubo_resultados` in the context (ERR-11).
4. Decision "¿Hay resultados para importar?" (`hay_resultados_para_importar`):
   pure in-memory check of the listed files; zero files fix `sin_resultados`
   —a success, not an error— for "Finalizar Proceso".

Mandatory sheet order: configuration before database; folders after the lock;
candidates and file listing after database and lock. Neither INICIO touches
the AI service, the network or credentials (RN-08/RN-07).
"""

import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from modules.evaluation.run_context import RunContext
from shared.config import load
from shared.evaluacion import validar_evaluacion_manual
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

_RAIZ_PROYECTO = Path(__file__).resolve().parents[3]
_CARPETAS_OBLIGATORIAS = ("base", "lotes", "resultados")


@dataclass
class ResultadoInicioManual:
    """Outcome of either manual INICIO node handed to the orchestrator."""

    estado: str  # "ok" | "error" | "concurrencia"
    id_corrida: str = ""
    contexto: RunContext | None = None
    codigo: str = ""
    descripcion: str = ""


@dataclass
class ResultadoDecisionManual:
    """Outcome of the two manual decision nodes ("si" / "no" branches)."""

    estado: str  # "ok" | "error"
    decision: str = ""  # "si" | "no"
    contexto: RunContext | None = None
    codigo: str = ""
    descripcion: str = ""


@dataclass
class _Arranque:
    """Carrier of the startup steps shared by both processes (1-4)."""

    id_corrida: str = ""
    configuracion: dict[str, Any] = field(default_factory=dict)
    marca_inicio: str = ""
    terminacion: ResultadoInicioManual | None = None


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


def _error(id_corrida: str, codigo: str, descripcion: str) -> ResultadoInicioManual:
    return ResultadoInicioManual(
        estado="error",
        id_corrida=id_corrida,
        codigo=codigo,
        descripcion=descripcion,
    )


def _cargar_configuracion(
    id_corrida: str, config: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, ResultadoInicioManual | None]:
    """Paso 2: loads and validates the whole `evaluacion_manual:` section."""
    try:
        if config is None:
            config = load()
        if not isinstance(config, dict):
            raise ValueError("configuration root is not a mapping")
        problema = validar_evaluacion_manual(config.get("evaluacion_manual"))
        if problema is not None:
            raise ValueError(f"seccion evaluacion_manual invalida: {problema}")
    except FileNotFoundError:
        logger.error(f"ERR-02 | run={id_corrida} | configuration file missing")
        return None, _error(id_corrida, "ERR-02", "configuration file missing")
    except OSError:
        logger.error(f"ERR-03 | run={id_corrida} | configuration file unreadable")
        return None, _error(id_corrida, "ERR-03", "configuration file unreadable")
    except (ValueError, yaml.YAMLError):
        logger.error(
            f"ERR-04 | run={id_corrida} | configuration corrupt or inconsistent"
        )
        return None, _error(
            id_corrida,
            "ERR-04",
            "configuration missing, corrupt or out of range (VAL-02)",
        )
    return config, None


def _verificar_bd(id_corrida: str) -> ResultadoInicioManual | None:
    """Paso 3: database availability with a rolled-back write probe."""
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
        return _error(id_corrida, "ERR-05", "database unavailable or not writable")
    return None


def _registrar(
    id_corrida: str,
) -> tuple[str, ResultadoInicioManual | None]:
    """Paso 3b: registers the run row before the lock attempt (RN-09)."""
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
        return "", _error(id_corrida, "ERR-05", "run registration failed")
    return marca_inicio, None


def _adquirir_bloqueo(
    id_corrida: str, configuracion: dict[str, Any]
) -> ResultadoInicioManual | None:
    """Paso 4: shared global lock with Modules 1 and 2 (RN-02)."""
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
        return _error(id_corrida, "ERR-08", "lock state undecidable")

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
            logger.error(
                f"ERR-08 | run={id_corrida} | lock marca_temporal undecidable"
            )
            return _error(id_corrida, "ERR-08", "lock marca_temporal undecidable")
        if not _es_obsoleto(fecha_bloqueo, umbral_obsolescencia_minutos(configuracion)):
            registrar_evento(
                id_corrida=id_corrida,
                tipo="suceso",
                codigo="ERR-06",
                evidencia=(
                    f"corrida {bloqueo_actual.get('id_corrida', '')} activa; "
                    "terminacion por concurrencia"
                ),
            )
            return ResultadoInicioManual(
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
            return _error(
                id_corrida, "ERR-08", "lock overwrite failed (undecidable state)"
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
            return ResultadoInicioManual(
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
        return None

    try:
        adquirido = adquirir_bloqueo(id_corrida, marca_temporal)
    except Exception as error:
        registrar_evento(
            id_corrida=id_corrida,
            tipo="error",
            codigo="ERR-08",
            evidencia=f"fallo al adquirir: {error}",
        )
        return _error(
            id_corrida, "ERR-08", "lock acquisition failed (undecidable state)"
        )
    if not adquirido:
        registrar_evento(
            id_corrida=id_corrida,
            tipo="suceso",
            codigo="ERR-06",
            evidencia="contienda de adquisicion: otro proceso gano el bloqueo",
        )
        return ResultadoInicioManual(
            estado="concurrencia",
            id_corrida=id_corrida,
            codigo="ERR-06",
            descripcion="lock contention race at acquisition",
        )
    return None


def _arrancar(config: dict[str, Any] | None) -> _Arranque:
    """Steps 1-4 shared by both manual entry points."""
    arranque = _Arranque()
    try:
        arranque.id_corrida = _generar_id_corrida()
    except Exception as exc:
        logger.error(f"ERR-01 | id_corrida generado dos veces con fallo | {exc}")
        arranque.terminacion = _error(
            "", "ERR-01", "id_corrida generation failed after a single retry"
        )
        return arranque

    configuracion, fallo = _cargar_configuracion(arranque.id_corrida, config)
    if fallo is not None or configuracion is None:
        arranque.terminacion = fallo
        return arranque
    arranque.configuracion = configuracion

    fallo = _verificar_bd(arranque.id_corrida)
    if fallo is not None:
        arranque.terminacion = fallo
        return arranque

    marca_inicio, fallo = _registrar(arranque.id_corrida)
    if fallo is not None:
        arranque.terminacion = fallo
        return arranque
    arranque.marca_inicio = marca_inicio

    fallo = _adquirir_bloqueo(arranque.id_corrida, arranque.configuracion)
    if fallo is not None:
        arranque.terminacion = fallo
    return arranque


def _carpetas_de_trabajo(carpeta_base: str) -> dict[str, Path]:
    """Resolves the four work-folder paths from the configured base."""
    base = Path(carpeta_base).expanduser()
    if not base.is_absolute():
        base = _RAIZ_PROYECTO / base
    return {
        "base": base,
        "lotes": base / "lotes",
        "resultados": base / "resultados",
        "rechazados": base / "resultados" / "rechazados",
    }


def _verificar_escritura(carpeta: Path) -> None:
    """Probe: creates and removes a temporary file inside the folder."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=carpeta,
        prefix=".sonda_",
        suffix=".tmp",
        delete=True,
        encoding="utf-8",
    ) as sonda:
        sonda.write("ok")


def _preparar_carpetas(
    carpeta_base: str, *, verificar_lectura: bool
) -> tuple[dict[str, Path], str | None]:
    """Paso 5: creates the missing folders and verifies read/write access."""
    carpetas = _carpetas_de_trabajo(carpeta_base)
    try:
        for clave in _CARPETAS_OBLIGATORIAS:
            carpetas[clave].mkdir(parents=True, exist_ok=True)
            _verificar_escritura(carpetas[clave])
            if verificar_lectura:
                list(carpetas[clave].iterdir())
    except OSError as error:
        return carpetas, str(error)
    return carpetas, None


def _listar_resultados(carpeta: Path) -> list[Path]:
    """Paso 6: lists direct files of `resultados/` sorted by name.

    Hidden files are ignored: they are never answers returned by the chat and
    must not turn `hubo_resultados` on. `rechazados/` is a folder and is
    therefore excluded by the file filter; its content is never listed here.
    """
    return sorted(
        (ruta for ruta in carpeta.iterdir() if ruta.is_file() and not ruta.name.startswith(".")),
        key=lambda ruta: ruta.name,
    )


def _asignar_carpetas(contexto: RunContext, carpetas: dict[str, Path]) -> None:
    contexto.carpeta_base = carpetas["base"]
    contexto.carpeta_lotes = carpetas["lotes"]
    contexto.carpeta_resultados = carpetas["resultados"]
    contexto.carpeta_rechazados = carpetas["rechazados"]


def _tic_modulo_iniciado(id_corrida: str, proceso: str) -> None:
    """Narration tick of the module start (excluded from closure metrics)."""
    registrar_evento(
        id_corrida=id_corrida,
        tipo="suceso",
        codigo="tic_modulo_iniciado",
        evidencia=f"modulo=evaluacion;proceso={proceso}",
    )


def _cerrar_arranque(
    arranque: _Arranque, contexto: RunContext, proceso: str
) -> ResultadoInicioManual:
    """Paso 8: VAL-06 contract check, narration and handover."""
    if not (
        contexto.id_corrida == arranque.id_corrida
        and contexto.bloqueo_adquirido
        and isinstance(contexto.hubo_candidatas, bool)
        and isinstance(contexto.hubo_resultados, bool)
        and contexto.carpetas_resueltas
    ):
        registrar_evento(
            id_corrida=arranque.id_corrida,
            tipo="error",
            codigo="ERR-11",
            evidencia="contexto incompleto al entregar control",
        )
        logger.error(
            f"ERR-11 | run={arranque.id_corrida} | incomplete context before handover"
        )
        return _error(
            arranque.id_corrida, "ERR-11", "incomplete context before handover (VAL-06)"
        )
    _tic_modulo_iniciado(arranque.id_corrida, proceso)
    narrar_modulo("evaluacion")
    return ResultadoInicioManual(
        estado="ok", id_corrida=arranque.id_corrida, contexto=contexto
    )


def ejecutar_inicio_exportacion(
    config: dict[str, Any] | None = None,
) -> ResultadoInicioManual:
    """Export INICIO: run the sheet steps 1-8 in order."""
    arranque = _arrancar(config)
    if arranque.terminacion is not None:
        return arranque.terminacion
    id_corrida = arranque.id_corrida
    seccion = arranque.configuracion["evaluacion_manual"]

    # Paso 5 — carpeta de trabajo (después del bloqueo, antes de candidatas).
    carpetas, error_carpeta = _preparar_carpetas(
        str(seccion["carpeta_base"]), verificar_lectura=False
    )
    if error_carpeta is not None:
        registrar_evento(
            id_corrida=id_corrida,
            tipo="error",
            codigo="ERR-10",
            evidencia=f"carpeta de trabajo no disponible: {error_carpeta}",
        )
        logger.error(
            f"ERR-10 | run={id_corrida} | work folder unavailable | {error_carpeta}"
        )
        return _error(id_corrida, "ERR-10", "work folder unavailable or not writable")

    # Paso 6 — carga FIFO de candidatas (sin tope: RN-06).
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
        return _error(id_corrida, "ERR-05", "candidate load failed")

    # Paso 7 — inicialización de estado; la fila de la corrida ya existe.
    try:
        contexto = RunContext(
            config_evaluacion_manual=seccion,
            candidatas=candidatas,
            id_corrida=id_corrida,
            fecha_inicio=arranque.marca_inicio,
        )
        contexto.bloqueo_adquirido = True
        _asignar_carpetas(contexto, carpetas)
    except Exception as error:
        registrar_evento(
            id_corrida=id_corrida,
            tipo="error",
            codigo="ERR-11",
            evidencia=f"Fallo interno de inicializacion de estado: {error}",
        )
        logger.error(
            f"ERR-11 | run={id_corrida} | internal initialization failure | {error}"
        )
        return _error(
            id_corrida, "ERR-11", "internal run state initialization failure"
        )

    return _cerrar_arranque(arranque, contexto, "exportacion")


def ejecutar_inicio_importacion(
    config: dict[str, Any] | None = None,
) -> ResultadoInicioManual:
    """Import INICIO: run the sheet steps 1-8 in order."""
    arranque = _arrancar(config)
    if arranque.terminacion is not None:
        return arranque.terminacion
    id_corrida = arranque.id_corrida
    seccion = arranque.configuracion["evaluacion_manual"]

    # Paso 5 — carpeta de trabajo con lectura y escritura (el listado exige
    # lectura; el import escribirá las ofertas y apartará rechazados).
    carpetas, error_carpeta = _preparar_carpetas(
        str(seccion["carpeta_base"]), verificar_lectura=True
    )
    if error_carpeta is not None:
        registrar_evento(
            id_corrida=id_corrida,
            tipo="error",
            codigo="ERR-10",
            evidencia=f"carpeta de trabajo no disponible: {error_carpeta}",
        )
        logger.error(
            f"ERR-10 | run={id_corrida} | work folder unavailable | {error_carpeta}"
        )
        return _error(
            id_corrida, "ERR-10", "work folder unavailable or not accessible"
        )

    # Paso 6 — listado de resultados ordenado por nombre, sin leer contenido.
    try:
        archivos = _listar_resultados(carpetas["resultados"])
    except OSError as error:
        registrar_evento(
            id_corrida=id_corrida,
            tipo="error",
            codigo="ERR-10",
            evidencia=f"listado de resultados no disponible: {error}",
        )
        logger.error(
            f"ERR-10 | run={id_corrida} | result listing failed | {error}"
        )
        return _error(id_corrida, "ERR-10", "result files not listable")

    # Paso 7 — inicialización de estado; la fila de la corrida ya existe.
    try:
        contexto = RunContext(
            config_evaluacion_manual=seccion,
            archivos_resultados=archivos,
            id_corrida=id_corrida,
            fecha_inicio=arranque.marca_inicio,
        )
        contexto.bloqueo_adquirido = True
        _asignar_carpetas(contexto, carpetas)
    except Exception as error:
        registrar_evento(
            id_corrida=id_corrida,
            tipo="error",
            codigo="ERR-11",
            evidencia=f"Fallo interno de inicializacion de estado: {error}",
        )
        logger.error(
            f"ERR-11 | run={id_corrida} | internal initialization failure | {error}"
        )
        return _error(
            id_corrida, "ERR-11", "internal run state initialization failure"
        )

    return _cerrar_arranque(arranque, contexto, "importacion")


def hay_ofertas_preparadas(
    contexto: RunContext | None,
) -> ResultadoDecisionManual:
    """Decision node: "¿Hay ofertas preparadas?" (export process)."""
    if contexto is None:
        logger.error(
            "ERR-01 | sin id_corrida | contexto ausente: "
            "no se puede evaluar la existencia de ofertas preparadas"
        )
        return ResultadoDecisionManual(
            estado="error",
            codigo="ERR-01",
            descripcion="contexto ausente: no hay ofertas que evaluar",
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
        return ResultadoDecisionManual(
            estado="error",
            contexto=contexto,
            codigo="ERR-01",
            descripcion="lista de candidatas no accesible en el contexto",
        )

    # Evaluación pura sobre la lista leída por INICIO (RN-01: sin releer BD).
    if len(lista) > 0:
        return ResultadoDecisionManual(estado="ok", decision="si", contexto=contexto)

    # Rama No (RN-04): fijar motivo en el propio contexto; "Finalizar
    # Proceso" lo consume y registra (RN-05: este nodo no registra).
    contexto.motivo_cierre = "sin_pendientes"
    contexto.motivo_marca_temporal = ahora()
    return ResultadoDecisionManual(estado="ok", decision="no", contexto=contexto)


def hay_resultados_para_importar(
    contexto: RunContext | None,
) -> ResultadoDecisionManual:
    """Decision node: "¿Hay resultados para importar?" (import process)."""
    if contexto is None:
        logger.error(
            "ERR-01 | sin id_corrida | contexto ausente: "
            "no se puede evaluar la existencia de resultados"
        )
        return ResultadoDecisionManual(
            estado="error",
            codigo="ERR-01",
            descripcion="contexto ausente: no hay resultados que evaluar",
        )

    archivos = contexto.archivos_resultados
    if not isinstance(archivos, list):
        registrar_evento(
            id_corrida=contexto.id_corrida,
            tipo="error",
            codigo="ERR-01",
            evidencia="contexto incompleto: la lista de archivos no es accesible",
        )
        logger.error(
            f"ERR-01 | run={contexto.id_corrida} | result file list inaccessible"
        )
        return ResultadoDecisionManual(
            estado="error",
            contexto=contexto,
            codigo="ERR-01",
            descripcion="lista de archivos no accesible en el contexto",
        )

    # Evaluación pura sobre el listado hecho por INICIO (RN-01/RN-02).
    if len(archivos) > 0:
        return ResultadoDecisionManual(estado="ok", decision="si", contexto=contexto)

    # Rama No: terminación controlada `sin_resultados`, tipo suceso (RN-04).
    contexto.motivo_cierre = "sin_resultados"
    contexto.motivo_marca_temporal = ahora()
    return ResultadoDecisionManual(estado="ok", decision="no", contexto=contexto)
