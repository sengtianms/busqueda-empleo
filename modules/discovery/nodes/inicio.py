"""INICIO node of the Discovery flow (technical sheet v1.3, Section 1).

Instantiates the run (id_corrida with a single retry), loads and validates the
global configuration (VAL-02), verifies the database with a rolled-back write
probe (VAL-03), resolves the concurrency lock (VAL-04), filters structurally
valid sources discarding incomplete sheets with an ERR-12 event (VAL-06),
initializes the run state and registers the run row, then delivers a complete
RunContext (VAL-05). This node never touches job sources, filters, offers,
the credential store or runtime validations (RN-05, RN-09).

Definitions (section 1.11): abort = immediate termination on unrecoverable
failure; controlled termination = finishing without processing (concurrency);
discard = excluding a source from the iteration without stopping the run.
Errors ERR-01..ERR-04 and ERR-11 are logged only with Loguru (DB not
connected yet); events that can reach the `eventos` table fall back to Loguru
when the database is unavailable.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import yaml
from loguru import logger

from modules.discovery.run_context import RunContext
from shared.config import load
from shared.persistence import (
    adquirir_bloqueo,
    consultar_bloqueo,
    generar_id,
    init_db,
    registrar_corrida,
    registrar_evento,
    sondear_escritura,
    umbral_obsolescencia_minutos,
)
from shared.utilidades import FORMATO_TIMESTAMP, TIPOS_ACCESO, ahora

_ESTRATEGIAS_ANTI_BLOQUEO = ("pausa_aleatoria", "retraso_fijo", "none")
_RANGOS_POLITICAS: dict[str, int] = {
    "max_paginas": 1,
    "max_ofertas_por_corrida": 1,
    "pausa_entre_lotes_segundos": 0,
}


@dataclass
class ResultadoInicio:
    """Outcome of the INICIO node handed to the orchestrator."""

    estado: str
    id_corrida: str = ""
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


def _registrar_evento(
    id_corrida: str,
    tipo: str,
    codigo: str,
    evidencia: str,
    fuente_id: str = "",
) -> None:
    registrar_evento(
        id_corrida=id_corrida,
        tipo=tipo,
        codigo=codigo,
        evidencia=evidencia,
        fuente_id=fuente_id,
    )


def _validar_fuente(conf: Any) -> str | None:
    """RN-08 sheet validation; returns an explanation or None when valid."""
    if not isinstance(conf, dict):
        return "la fuente no es un objeto"
    fuente_id = conf.get("fuente_id")
    if not isinstance(fuente_id, str) or not fuente_id.strip():
        return "fuente_id ausente o invalido"
    nombre = conf.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        return "nombre ausente o invalido"
    ficha = conf.get("ficha_acceso")
    if not isinstance(ficha, dict):
        return "ficha_acceso ausente o invalida"
    enlace = ficha.get("enlace")
    if not isinstance(enlace, str) or not enlace.strip():
        return "enlace ausente"
    tipo = ficha.get("tipo_acceso")
    if tipo not in TIPOS_ACCESO:
        return "tipo_acceso invalido"
    credenciales = ficha.get("credenciales_referencia")
    if tipo == "con_autenticacion" and (
        not isinstance(credenciales, list) or not credenciales
    ):
        return "credenciales_referencia ausente"
    criterio = ficha.get("criterio_exito")
    if not isinstance(criterio, str) or not criterio:
        return "criterio_exito ausente"
    timeout = ficha.get("timeout_segundos")
    if not isinstance(timeout, int) or timeout < 1:
        return "timeout_segundos invalido"
    sets = conf.get("sets_de_filtros")
    if not isinstance(sets, list) or not sets:
        return "sets_de_filtros vacio o ausente"
    for s in sets:
        if not isinstance(s, dict):
            return "set de filtros invalido"
        if not isinstance(s.get("indice_set"), int):
            return "set sin indice_set valido"
        if not isinstance(s.get("filtros"), list):
            return "filtros del set invalidos"
    politicas = conf.get("politicas_de_captura")
    if politicas is not None:
        if not isinstance(politicas, dict):
            return "politicas_de_captura invalida"
        for clave, minimo in _RANGOS_POLITICAS.items():
            if clave not in politicas:
                continue
            valor = politicas[clave]
            if not isinstance(valor, int) or valor < minimo:
                return f"politica {clave} fuera de rango (minimo {minimo})"
        estrategia = politicas.get("estrategia_anti_bloqueo")
        if estrategia is not None and estrategia not in _ESTRATEGIAS_ANTI_BLOQUEO:
            return "estrategia_anti_bloqueo fuera del conjunto definido"
    return None


def _validar_descubrimiento(config: dict[str, Any]) -> str | None:
    """VAL-02 sección `descubrimiento` (D61): umbrales enteros >= 1."""
    seccion = config.get("descubrimiento")
    if seccion is None:
        return None
    if not isinstance(seccion, dict):
        return "seccion descubrimiento invalida"
    for clave in ("renovar_navegador_tras_paginas", "tope_muertes_sin_avance"):
        valor = seccion.get(clave)
        if valor is None:
            continue
        if not isinstance(valor, int) or valor < 1:
            return f"{clave} debe ser entero >= 1"
    return None


def ejecutar_inicio(config: dict[str, Any] | None = None) -> ResultadoInicio:
    """Run the INICIO node steps in order (section 2 of the sheet)."""
    try:
        id_corrida = _generar_id_corrida()
    except Exception as exc:
        logger.error(f"ERR-01 | id_corrida generado dos veces con fallo | {exc}")
        return ResultadoInicio(
            estado="error",
            codigo="ERR-01",
            descripcion="id_corrida generation failed after a single retry",
        )

    try:
        if config is None:
            config = load()
        if not isinstance(config, dict):
            raise ValueError("configuration root is not a mapping")
        if "fuentes" not in config or not isinstance(config["fuentes"], list):
            raise ValueError("'fuentes' key missing or not a list")
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
            descripcion="configuration corrupt or inconsistent structure",
        )

    fuentes = config["fuentes"]
    ids = [str(c.get("fuente_id", "")) for c in fuentes if isinstance(c, dict)]
    duplicados = sorted({i for i in ids if ids.count(i) > 1}) if ids else []
    if duplicados:
        logger.error(f"ERR-11 | run={id_corrida} | duplicate fuente_ids: {duplicados}")
        return ResultadoInicio(
            estado="error",
            id_corrida=id_corrida,
            codigo="ERR-11",
            descripcion=f"duplicate fuente_id(s) {duplicados}",
        )

    problema_descubrimiento = _validar_descubrimiento(config)
    if problema_descubrimiento is not None:
        logger.error(
            f"ERR-04 | run={id_corrida} | {problema_descubrimiento}"
        )
        return ResultadoInicio(
            estado="error",
            id_corrida=id_corrida,
            codigo="ERR-04",
            descripcion=problema_descubrimiento,
        )

    try:
        init_db()
        sondear_escritura()
    except Exception as error:
        _registrar_evento(id_corrida, "error", "ERR-05", f"base de datos no disponible: {error}")
        logger.error(f"ERR-05 | run={id_corrida} | database unavailable | {error}")
        return ResultadoInicio(
            estado="error",
            id_corrida=id_corrida,
            codigo="ERR-05",
            descripcion="database unavailable or not writable",
        )

    try:
        bloqueo_actual = consultar_bloqueo()
    except Exception as error:
        _registrar_evento(id_corrida, "error", "ERR-08", f"estado de bloqueo no decidible: {error}")
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
            _registrar_evento(id_corrida, "error", "ERR-08", "marca_temporal del bloqueo no valido")
            return ResultadoInicio(
                estado="error",
                id_corrida=id_corrida,
                codigo="ERR-08",
                descripcion="lock marca_temporal undecidable",
            )
        if not _es_obsoleto(fecha_bloqueo, umbral_obsolescencia_minutos(config)):
            _registrar_evento(
                id_corrida,
                "suceso",
                "ERR-06",
                f"corrida {bloqueo_actual.get('id_corrida', '')} activa; "
                "terminacion por concurrencia",
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
            _registrar_evento(id_corrida, "error", "ERR-08", f"fallo al sobrescribir: {error}")
            return ResultadoInicio(
                estado="error",
                id_corrida=id_corrida,
                codigo="ERR-08",
                descripcion="lock overwrite failed (undecidable state)",
            )
        if not adquirido:
            _registrar_evento(
                id_corrida,
                "suceso",
                "ERR-06",
                "contienda de adquisicion al sobrescribir: otro proceso gano el bloqueo",
            )
            return ResultadoInicio(
                estado="concurrencia",
                id_corrida=id_corrida,
                codigo="ERR-06",
                descripcion="lock contention at stale overwrite",
            )
        _registrar_evento(
            id_corrida,
            "suceso",
            "ERR-07",
            f"bloqueo obsoleto de {bloqueo_actual.get('id_corrida', '')} sobrescrito",
        )
    else:
        try:
            adquirido = adquirir_bloqueo(id_corrida, marca_temporal)
        except Exception as error:
            _registrar_evento(id_corrida, "error", "ERR-08", f"fallo al adquirir: {error}")
            return ResultadoInicio(
                estado="error",
                id_corrida=id_corrida,
                codigo="ERR-08",
                descripcion="lock acquisition failed (undecidable state)",
            )
        if not adquirido:
            _registrar_evento(
                id_corrida,
                "suceso",
                "ERR-06",
                "contienda de adquisicion: otro proceso gano el bloqueo",
            )
            return ResultadoInicio(
                estado="concurrencia",
                id_corrida=id_corrida,
                codigo="ERR-06",
                descripcion="lock contention race at acquisition",
            )

    validas: list[dict[str, Any]] = []
    for raw in fuentes:
        problema = _validar_fuente(raw)
        if problema is not None:
            fuente_id = str(raw.get("fuente_id", "")) if isinstance(raw, dict) else ""
            _registrar_evento(
                id_corrida,
                "error",
                "ERR-12",
                f"ficha incompleta: {problema}",
                fuente_id=fuente_id,
            )
            logger.warning(
                f"ERR-12 | run={id_corrida} | source={fuente_id} descartada | {problema}"
            )
            continue
        validas.append(raw)

    try:
        contexto = RunContext(
            config_fuentes=validas,
            config_captura=config.get("captura") or {},
            id_corrida=id_corrida,
            permitir_vacio=True,
            config_descubrimiento=config.get("descubrimiento") or {},
        )
        contexto.bloqueo_adquirido = True
        registrar_corrida(
            {
                "id_corrida": id_corrida,
                "fecha_inicio": contexto.fecha_inicio,
                "estado": "en_ejecucion",
            }
        )
    except Exception as error:
        _registrar_evento(
            id_corrida,
            "error",
            "ERR-10",
            f"Fallo interno de inicializacion de estado: {error}",
        )
        logger.error(f"ERR-10 | run={id_corrida} | internal initialization failure | {error}")
        return ResultadoInicio(
            estado="error",
            id_corrida=id_corrida,
            codigo="ERR-10",
            descripcion="internal run state initialization failure",
        )

    if not (contexto.id_corrida == id_corrida and contexto.bloqueo_adquirido):
        _registrar_evento(id_corrida, "error", "ERR-10", "contexto incompleto al entregar control")
        return ResultadoInicio(
            estado="error",
            id_corrida=id_corrida,
            codigo="ERR-10",
            descripcion="incomplete context before handover (VAL-05)",
        )

    return ResultadoInicio(estado="ok", id_corrida=id_corrida, contexto=contexto)
