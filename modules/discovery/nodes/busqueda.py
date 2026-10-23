"""Nodes for searching opportunities with filters (v1.1).
( RN-10: Set iterator is property of this node; reset on source change)
"""

from dataclasses import dataclass
from typing import cast

from loguru import logger

from modules.discovery.adapters.linkedin import FlowError
from modules.discovery.adapters.registry import obtener_adaptador
from modules.discovery.navegacion import (
    es_muerte_navegador,
    latido,
    reabrir_navegador,
    renovar_si_toca,
    techo_por_aplicacion,
)
from modules.discovery.run_context import RunContext
from shared.models import SearchResult
from shared.narrador import narrar_set
from shared.persistence import registrar_evento
from shared.retry import ejecutar_con_reintento
from shared.utilidades import acotar_evidencia


def _tic_set_iniciado(contexto: RunContext, indice: int) -> None:
    """Lote 2: tic de narración del set en marcha (excluido de métricas)."""
    registrar_evento(
        id_corrida=contexto.id_corrida,
        tipo="suceso",
        codigo="tic_set_iniciado",
        evidencia=f"set={indice}",
        indice_set=indice,
    )


@dataclass
class ResultadoBusqueda:
    estado: str  # "ok" | "error"
    decision: str = ""  # "si" | "no" (for decision nodes)
    contexto: RunContext | None = None
    codigo: str = ""
    descripcion: str = ""


class _MuerteBusqueda(Exception):
    """Señal interna: el canal murió durante la búsqueda (resurección D61)."""

    def __init__(self, error: BaseException) -> None:
        super().__init__(str(error))
        self.error = error


def _resultado_fallo(
    codigo_motivo: str, evidencia: str, intentos: int, indice: int
) -> SearchResult:
    """SearchResult de fallo común (fallo final e error interno)."""
    return SearchResult(
        estado="fallo",
        codigo_motivo=codigo_motivo,
        evidencia_acotada=acotar_evidencia(evidencia),
        numero_de_intentos=intentos,
        ofertas_primera_pagina=[],
        estado_paginacion="fin",
        indice_set=indice,
    )


def aplicar_filtros(contexto: RunContext) -> ResultadoBusqueda:
    """
    Node: Apply basic filters.
    Iterates through filter sets and executes query via adapter.
    """
    # Paso 1: Leer insumos
    handle = contexto.handle_sesion
    fuente = contexto.fuente_corriente

    if handle is None or fuente is None:
        logger.error(f"ERR-01: session handle or source missing in run {contexto.id_corrida}")
        return ResultadoBusqueda(estado="error", codigo="ERR-01", descripcion="Insumos ausentes")

    # Paso 2: Detectar cambio de fuente y seleccionar siguiente set
    fuente_id = fuente.fuente_id
    contexto.marcar_cambio_de_fuente(fuente_id)

    try:
        indice = contexto.seleccionar_siguiente_set(fuente_id)
    except ValueError:
        logger.error(f"ERR-01: Unknown source {fuente_id} in run {contexto.id_corrida}")
        return ResultadoBusqueda(estado="error", codigo="ERR-01", descripcion="Fuente desconocida")
    set_actual = contexto.set_filtros(fuente, indice)

    if set_actual is None:
        logger.error(f"ERR-01: No filter set available for {fuente_id} at index {indice}")
        return ResultadoBusqueda(estado="error", codigo="ERR-01", descripcion="Set ausente")

    contexto.set_corriente = set_actual

    # Lote 2: tic de narración del set en marcha (consola manual + tablero).
    _tic_set_iniciado(contexto, set_actual.indice)
    narrar_set(set_actual.indice)

    # Paso 3: resiliencia del canal (D61) — renovación prevista, tramo con
    # reintento condicional clásico y resurección ante muerte del navegador.
    if not renovar_si_toca(contexto):
        return _resultado_insostenible(contexto)

    politicas = contexto.politicas(fuente)
    adapter = obtener_adaptador(fuente.fuente_id)

    def _fallo_final(fe: BaseException, intentos: int) -> SearchResult:
        if es_muerte_navegador(fe):
            raise _MuerteBusqueda(fe) from fe
        error = cast(FlowError, fe)
        return _resultado_fallo(
            codigo_motivo=error.codigo_motivo,
            evidencia=error.mensaje,
            intentos=intentos,
            indice=set_actual.indice,
        )

    def _fallo_interno(exc: Exception, intentos: int) -> SearchResult:
        if es_muerte_navegador(exc):
            raise _MuerteBusqueda(exc) from exc
        logger.error(f"ERR-07: Internal error in apply_filters: {exc}")
        return _resultado_fallo(
            codigo_motivo="error_interno_consulta",
            evidencia=str(exc),
            intentos=intentos,
            indice=set_actual.indice,
        )

    res: SearchResult | None = None
    intentos = 0
    while True:
        supervisor = latido()
        supervisor.vigilar(
            "busqueda", techo_por_aplicacion(fuente.timeout_segundos)
        )

        def _intentar() -> SearchResult:
            handle_actual = contexto.handle_sesion
            if handle_actual is None:
                raise FlowError(
                    "fuente_inalcanzable",
                    "Canal sin página activa para aplicar los filtros.",
                )
            return adapter.apply_filters(
                page=handle_actual,
                ficha=fuente,
                set_filtros=set_actual,
                politicas=politicas,
            )

        try:
            res, intentos = ejecutar_con_reintento(
                _intentar,
                al_fallo_final=_fallo_final,
                al_error_interno=_fallo_interno,
                contexto_log=contexto.id_corrida,
            )
        except BaseException as exc:
            supervisor.descansar()
            if not isinstance(exc, _MuerteBusqueda):
                raise
            causa = exc.error
            muertes = contexto.muertes_sin_avance + 1
            contexto.muertes_sin_avance = muertes
            logger.error(
                f"Navegador muerto en búsqueda | run={contexto.id_corrida} | "
                f"set={set_actual.indice} | muertes_sin_avance={muertes} | "
                f"{acotar_evidencia(str(causa), 200)}"
            )
            if muertes > contexto.tope_muertes_sin_avance:
                return _resultado_insostenible(contexto)
            if not reabrir_navegador(contexto, motivo="colapso"):
                return _resultado_insostenible(contexto)
            continue  # reintenta el MISMO set con el canal reconstruido
        supervisor.descansar()
        contexto.muertes_sin_avance = 0
        contexto.paginas_desde_renovacion += 1
        break

    assert res is not None
    # Paso 4 & 5: Resultado exitoso (intentos reales del flujo)
    contexto.search_result = res.model_copy(
        update={"numero_de_intentos": intentos}
    )
    if res.indice_set != set_actual.indice:
        logger.warning(
            "Consistency warning: search_result index "
            f"{res.indice_set} != set index {set_actual.indice}"
        )

    if res.estado == "exito" and len(res.ofertas_primera_pagina) > 0:
        _registrar_evento_consulta_exitosa(contexto, res)

    return ResultadoBusqueda(estado="ok", contexto=contexto)


def _resultado_insostenible(contexto: RunContext) -> ResultadoBusqueda:
    """ERR-09 honesto: el canal no se puede sostener; la tanda cierra."""
    logger.error(
        f"ERR-09: Navegador insostenible, cierre honesto de la tanda | "
        f"run={contexto.id_corrida}"
    )
    return ResultadoBusqueda(
        estado="error",
        codigo="ERR-09",
        descripcion="Navegador insostenible: cierre honesto de la tanda",
        contexto=contexto,
    )


def _registrar_evento_consulta_exitosa(
    contexto: RunContext, res: SearchResult
) -> None:
    """Writes the `consulta_exitosa` success event (ficha contract, D30).

    Non-aborting. Emitted only on success *with offers*: success with zero
    offers and failures keep being typed by the register node
    (registro.py), so every search result ends with exactly one event.
    """
    registrar_evento(
        id_corrida=contexto.id_corrida,
        tipo="suceso",
        codigo="consulta_exitosa",
        evidencia=(
            f"set={res.indice_set} | "
            f"total={res.total_declarado if res.total_declarado is not None else 'desconocido'}"
        ),
        fuente_id=(
            contexto.fuente_corriente.fuente_id if contexto.fuente_corriente else ""
        ),
        id_sesion=contexto.id_sesion,
        indice_set=res.indice_set,
    )


def se_encontraron_ofertas(contexto: RunContext) -> ResultadoBusqueda:
    """
    Node: Were offers found?
    Pure decision based on the search result.
    """
    res = contexto.search_result
    if res is None:
        logger.error(f"ERR-01: search_result missing in run {contexto.id_corrida}")
        return ResultadoBusqueda(
            estado="error", codigo="ERR-01", descripcion="search_result ausente"
        )

    # Paso 2: Validar consistencia (valores reales, no estructura:
    # SearchResult es un modelo Pydantic cuyos atributos siempre existen)
    if res.estado not in ("exito", "fallo"):
        logger.error(f"ERR-02: Invalid search_result structure in run {contexto.id_corrida}")
        return ResultadoBusqueda(estado="error", codigo="ERR-02", descripcion="Estructura inválida")

    if res.estado == "exito" and not isinstance(res.ofertas_primera_pagina, list):
        logger.error(
            f"ERR-02: search_result success without offer list in run {contexto.id_corrida}"
        )
        return ResultadoBusqueda(estado="error", codigo="ERR-02", descripcion="Éxito sin lista")

    # Paso 3 & 4: Evaluar y Bifurcar
    condicion = (res.estado == "exito" and len(res.ofertas_primera_pagina) > 0)
    decision = "si" if condicion else "no"

    return ResultadoBusqueda(estado="ok", decision=decision, contexto=contexto)
