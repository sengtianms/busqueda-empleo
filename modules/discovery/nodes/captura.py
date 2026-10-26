"""Nodos de captura y registro de ofertas (Sub-fase 4.4).

Cubre los nodos "Capturar ofertas", "Registrar ofertas en Ofertas Totales",
"¿Quedan ofertas por capturar?" y "¿Quedan sets de filtros por aplicar?"
(DOC-04 Section 15). El adaptador resuelve toda la paginación internamente
(RN-10), por lo que el bucle interno de captura se ejecuta una sola vez por
set; la deduplicación se hace por `id_externo`.
"""

from dataclasses import dataclass
from time import monotonic
from typing import Any

from loguru import logger

from modules.discovery.adapters.linkedin import FlowError
from modules.discovery.adapters.registry import obtener_adaptador
from modules.discovery.navegacion import (
    es_muerte_navegador,
    latido,
    reabrir_navegador,
    renovar_si_toca,
    techo_por_paginas,
)
from modules.discovery.run_context import RunContext
from shared.models import AuditoriaSesion, CaptureBatch, EstadoCaptura, Offer
from shared.narrador import narrar_captura
from shared.persistence import (
    actualizar_fila,
    escribir_fila,
    leer_tabla,
    registrar_evento,
    upsert_lote_ofertas,
)
from shared.retry import ejecutar_con_reintento
from shared.utilidades import FORMATO_TIMESTAMP, acotar_evidencia, ahora


class _FalloTramo(Exception):
    """Señal interna: el tramo de captura falló de forma definitiva.

    Transporta la excepción original para que el bucle de resiliencia
    distinga muerte de navegador (→ resurección, D61) de fallo de
    plataforma (→ fallo del set; la tanda sigue con el siguiente).
    """

    def __init__(self, error: BaseException, intentos: int) -> None:
        super().__init__(str(error))
        self.error = error
        self.intentos = intentos


@dataclass
class ResultadoCaptura:
    estado: str  # "ok" | "error"
    decision: str = ""  # "si" | "no" (solo nodos de decisión)
    contexto: RunContext | None = None
    codigo: str = ""
    descripcion: str = ""


def _registrar_evento(
    contexto: RunContext,
    tipo: str,
    codigo: str,
    evidencia: str,
) -> None:
    """Escribe un evento en la tabla `eventos` sin abortar el flujo (D42)."""
    registrar_evento(
        id_corrida=contexto.id_corrida,
        tipo=tipo,
        codigo=codigo,
        evidencia=evidencia,
        fuente_id=(
            contexto.fuente_corriente.fuente_id if contexto.fuente_corriente else ""
        ),
        id_sesion=contexto.id_sesion,
        indice_set=(
            contexto.set_corriente.indice if contexto.set_corriente else None
        ),
    )


def capturar_ofertas(contexto: RunContext) -> ResultadoCaptura:
    """Nodo: Capturar ofertas (v1.3, resiliencia D61).

    Camina la búsqueda por TRAMOS paginados: cada tramo captura a lo sumo
    el presupuesto de páginas desde la última renovación y el nodo decide
    después de cada tramo si toca reconstruir el navegador, si la búsqueda
    terminó o si se alcanzó el freno de emergencia de las políticas.

    Resiliencia (D61): una muerte del navegador durante el tramo fuerza el
    árbol, reabre el canal con la misma memoria de sesión (ventana manual
    de 5 minutos si la plataforma la pide) y reanuda el tramo siguiente en
    la paginación exacta donde murió; las resurecciones no tienen techo
    (ley de la tanda). Muertes consecutivas sin avance ni reconstrucción
    posible cierran la tanda honesto (ERR-09 insostenible). El reintento
    condicional clásico (códigos reintentables) se conserva dentro de cada
    tramo; un fallo definitivo descarta solo el set, como siempre.
    """
    if contexto.navegador_insostenible:
        return _resultado_insostenible(contexto)
    # Paso 1: verificar insumos
    if contexto.handle_sesion is None:
        logger.error(f"ERR-01: handle_sesion ausente en corrida {contexto.id_corrida}")
        return ResultadoCaptura(
            estado="error", codigo="ERR-01", descripcion="Insumos ausentes"
        )
    fuente = contexto.fuente_corriente
    if fuente is None:
        logger.error(f"ERR-01: fuente_corriente ausente en corrida {contexto.id_corrida}")
        return ResultadoCaptura(
            estado="error", codigo="ERR-01", descripcion="Fuente ausente"
        )
    set_actual = contexto.set_corriente
    if set_actual is None:
        logger.error(f"ERR-01: set_corriente ausente en corrida {contexto.id_corrida}")
        return ResultadoCaptura(
            estado="error", codigo="ERR-01", descripcion="Set ausente"
        )

    # Paso 2: obtener políticas
    politicas = contexto.politicas(fuente)

    # Paso 3: bucle resiliencia D61 — tramos con reanudación por página
    adapter = obtener_adaptador(fuente.fuente_id)
    inicio_captura = monotonic()
    acumuladas: list[Offer] = []
    paginas_totales = 0
    desplazamiento = 0
    hay_mas = False
    estado_fallo: EstadoCaptura | None = None
    tramos = 0
    lote_unico: CaptureBatch | None = None
    estado_unico: EstadoCaptura | None = None

    while True:
        if contexto.navegador_insostenible or (
            contexto.muertes_sin_avance > contexto.tope_muertes_sin_avance
        ):
            return _resultado_insostenible(contexto)
        if paginas_totales >= politicas.max_paginas:
            break  # freno de emergencia por set (páginas, políticas)
        presupuesto_renovacion: int = (
            contexto.renovar_navegador_tras_paginas
            - contexto.paginas_desde_renovacion
        )
        if presupuesto_renovacion <= 0:
            if not renovar_si_toca(contexto):
                return _resultado_insostenible(contexto)
            presupuesto_renovacion = contexto.renovar_navegador_tras_paginas
        presupuesto = min(
            presupuesto_renovacion, politicas.max_paginas - paginas_totales
        )
        presupuesto_ofertas = politicas.max_ofertas_por_corrida - len(acumuladas)
        if presupuesto_ofertas <= 0:
            break  # freno de emergencia por set (ofertas, políticas)

        supervisor = latido()
        supervisor.vigilar(
            "captura", techo_por_paginas(fuente.timeout_segundos, politicas, presupuesto)
        )

        def _intentar() -> tuple[CaptureBatch, EstadoCaptura]:
            if contexto.handle_sesion is None:
                raise FlowError(
                    "fuente_inalcanzable",
                    "Canal sin página activa para la captura del tramo.",
                )
            return adapter.capture_batch(
                page=contexto.handle_sesion,
                ficha=fuente,
                set_filtros=set_actual,
                politicas=politicas,
                desde_desplazamiento=desplazamiento,
                max_paginas=presupuesto,
                max_ofertas=presupuesto_ofertas,
            )

        def _fallo_final(fe: BaseException, intentos: int) -> tuple[CaptureBatch, EstadoCaptura]:
            raise _FalloTramo(fe, intentos) from fe

        def _error_interno(exc: Exception, intentos: int) -> tuple[CaptureBatch, EstadoCaptura]:
            raise _FalloTramo(exc, intentos) from exc

        try:
            res_tramo, _ = ejecutar_con_reintento(
                _intentar,
                al_fallo_final=_fallo_final,
                al_error_interno=_error_interno,
                contexto_log=contexto.id_corrida,
            )
            lote_tramo, estado_tramo = res_tramo
        except BaseException as exc:
            supervisor.descansar()
            if not isinstance(exc, _FalloTramo):
                raise
            causa = exc.error
            if es_muerte_navegador(causa):
                # Muerte del navegador (D61): resurección sin techo.
                contexto.muertes_sin_avance += 1
                logger.error(
                    f"Navegador muerto en captura | run={contexto.id_corrida} | "
                    f"set={set_actual.indice} | "
                    f"muertes_sin_avance={contexto.muertes_sin_avance} | "
                    f"{acotar_evidencia(str(causa), 200)}"
                )
                if contexto.muertes_sin_avance > contexto.tope_muertes_sin_avance:
                    return _resultado_insostenible(contexto)
                if not reabrir_navegador(contexto, motivo="colapso"):
                    return _resultado_insostenible(contexto)
                continue  # reanuda el MISMO desplazamiento
            codigo = getattr(causa, "codigo_motivo", None)
            if isinstance(codigo, str):
                evidencia = acotar_evidencia(str(causa))
            else:
                codigo = "error_interno_captura"
                evidencia = str(causa)
            estado_fallo = EstadoCaptura(estado="fallo", codigo_motivo=codigo)
            _registrar_evento(
                contexto, tipo="error", codigo=codigo, evidencia=evidencia
            )
            break
        supervisor.descansar()

        # Éxito del tramo: contadores y acumulación.
        contexto.muertes_sin_avance = 0
        tramos += 1
        lote_unico = lote_tramo
        estado_unico = estado_tramo
        paginas_totales += estado_tramo.paginas_consumidas
        desplazamiento = estado_tramo.desplazamiento_final
        hay_mas = estado_tramo.hay_mas_ofertas
        acumuladas.extend(lote_tramo.ofertas)
        contexto.paginas_desde_renovacion += estado_tramo.paginas_consumidas

        # Lote 2: tic de narración de la captura (consola manual + tablero;
        # cuenta el avance en páginas absolutas del set).
        _registrar_evento(
            contexto,
            tipo="suceso",
            codigo="tic_captura_pagina",
            evidencia=(
                f"set={set_actual.indice};pagina={paginas_totales};"
                f"acumuladas={len(acumuladas)}"
            ),
        )
        narrar_captura(paginas_totales, len(acumuladas))

        if not hay_mas:
            break

    if estado_fallo is not None:
        # Paso 6: fallo definitivo del set (semántica v1.2 sin cambios).
        contexto.capture_batch = None
        contexto.estado_captura = estado_fallo
        return ResultadoCaptura(estado="ok", contexto=contexto)

    # Paso 4: éxito de captura. Un solo tramo conserva los objetos tal cual
    # (compatibilidad v1.2); varios tramos se agregan en un lote único.
    assert lote_unico is not None and estado_unico is not None
    if tramos == 1:
        lote = lote_unico
        estado = estado_unico
    else:
        lote = CaptureBatch(
            ofertas=acumuladas,
            id_corrida=lote_unico.id_corrida,
            fuente_id=fuente.fuente_id,
            id_sesion=lote_unico.id_sesion,
            indice_set=set_actual.indice,
            paginas_consumidas=paginas_totales,
        )
        estado = EstadoCaptura(
            estado="ok",
            paginas_consumidas=paginas_totales,
            capturadas_acumuladas_fuente=len(acumuladas),
            limite_alcanzado=len(acumuladas) >= politicas.max_ofertas_por_corrida,
            desplazamiento_final=desplazamiento,
            hay_mas_ofertas=hay_mas,
        )
    contexto.capture_batch = lote
    contexto.estado_captura = estado
    _registrar_evento(
        contexto,
        tipo="suceso",
        codigo="captura_completada",
        evidencia=(
            f"páginas={paginas_totales} | "
            f"ofertas={len(acumuladas)} | "
            f"duracion_s={int(monotonic() - inicio_captura)}"
        ),
    )

    # Paso 5: auditoría de sesión (no aborta si falla la escritura)
    _escribir_auditoria_sesion(contexto, lote)

    return ResultadoCaptura(estado="ok", contexto=contexto)


def _resultado_insostenible(contexto: RunContext) -> ResultadoCaptura:
    """ERR-09 honesto: el canal no se puede sostener; la tanda cierra."""
    logger.error(
        f"ERR-09: Navegador insostenible, cierre honesto de la tanda | "
        f"run={contexto.id_corrida}"
    )
    return ResultadoCaptura(
        estado="error",
        codigo="ERR-09",
        descripcion="Navegador insostenible: cierre honesto de la tanda",
        contexto=contexto,
    )


def _escribir_auditoria_sesion(contexto: RunContext, lote: CaptureBatch) -> None:
    """Escribe una auditoría por (id_sesion, indice_set); reintenta una vez."""
    id_sesion = contexto.id_sesion or ""
    total_declarado = (
        contexto.search_result.total_declarado
        if contexto.search_result is not None
        else None
    )
    indice_set = lote.indice_set
    # El id de la fila lo genera el escritor: usar el id de la sesión hacía
    # que el segundo set chocara con la clave primaria (UNIQUE, D67).
    datos = {
        "id_sesion": id_sesion,
        "id_corrida": contexto.id_corrida,
        "fuente_id": (
            contexto.fuente_corriente.fuente_id
            if contexto.fuente_corriente
            else ""
        ),
        "indice_set": indice_set if indice_set is not None else None,
        "marca_temporal": ahora(),
        "total_declarado": total_declarado,
        "conteo": len(lote.ofertas),
        "estado": "completa",
    }
    intentos = 2
    for intento in range(1, intentos + 1):
        try:
            AuditoriaSesion.model_validate(datos)
            filtros: dict[str, Any] = {
                "id_sesion": id_sesion,
                "fuente_id": datos["fuente_id"],
            }
            if indice_set is not None:
                filtros["indice_set"] = indice_set
            existentes = leer_tabla("sesiones", filtros)
            if indice_set is None:
                existentes = [
                    fila for fila in existentes if fila["indice_set"] is None
                ]
            if existentes:
                if not actualizar_fila("sesiones", existentes[0]["id"], datos):
                    raise RuntimeError("La fila de auditoría ya no existe")
            else:
                escribir_fila("sesiones", datos)
            return
        except Exception as exc:
            logger.error(
                f"[{contexto.id_corrida}] Auditoría de sesión fallida "
                f"(intento {intento}/{intentos}): {exc}"
            )
    logger.error(f"[{contexto.id_corrida}] Auditoría de sesión no persistida.")


def registrar_ofertas(contexto: RunContext) -> ResultadoCaptura:
    """Nodo: Registrar ofertas en Ofertas Totales (v1.0).

    Deduplica por `id_externo` vía `upsert_lote_ofertas` (una conexión y un
    reintento único para el lote completo). Si todas fallan, registra un
    evento crítico de lote degradado; el flujo siempre continúa.
    """
    lote = contexto.capture_batch
    if lote is None or not lote.ofertas:
        return ResultadoCaptura(estado="ok", contexto=contexto)

    filas = [_oferta_a_dict(oferta, contexto) for oferta in lote.ofertas]
    registradas, fallidas = _registrar_lote_con_reintento(filas)

    if registradas > 0:
        _registrar_evento(
            contexto,
            tipo="suceso",
            codigo="ofertas_registradas",
            evidencia=(
                f"ofertas registradas: {registradas} | "
                f"total: {len(lote.ofertas)}"
            ),
        )

    if fallidas > 0 and registradas == 0:
        _registrar_evento(
            contexto,
            tipo="error",
            codigo="lote_degradado",
            evidencia=(
                f"Lote degradado: {fallidas} ofertas fallidas de "
                f"{len(lote.ofertas)} en el set."
            ),
        )
    elif fallidas > 0:
        _registrar_evento(
            contexto,
            tipo="error",
            codigo="registro_parcial",
            evidencia=(
                f"Registro parcial: {registradas} registradas, "
                f"{fallidas} fallidas de {len(lote.ofertas)}."
            ),
        )

    return ResultadoCaptura(estado="ok", contexto=contexto)


def _oferta_a_dict(oferta: Offer, contexto: RunContext) -> dict[str, Any]:
    """Construye el dict de la fila `ofertas_descubiertas` desde una oferta capturada.

    `empresa_id`/`ubicacion_id` se guardan como NULL (catálogos no poblados
    en el MVP, D29), `fuente_id` conserva su fuente_id y la empresa cruda +
    ubicación cruda + modalidad provienen de la tarjeta (traspaso aprobado
    2026-08-25; `empresa` añadida por D41).
    """
    return {
        "titulo": oferta.titulo,
        "descripcion_original": oferta.descripcion_original,
        "empresa_id": None,
        "ubicacion_id": None,
        "enlace": oferta.enlace,
        "fuente_id": oferta.fuente_id,
        "indice_set": oferta.indice_set,
        "id_externo": oferta.id_externo,
        "fecha_publicacion": (
            oferta.fecha_publicacion.strftime(FORMATO_TIMESTAMP)
            if oferta.fecha_publicacion
            else None
        ),
        "observaciones": oferta.observaciones or "",
        "empresa": oferta.empresa or None,
        "ubicacion": oferta.ubicacion or None,
        "modalidad": oferta.modalidad or None,
        "id_corrida": contexto.id_corrida,
        "id_sesion": contexto.id_sesion,
        "fecha_descubrimiento": ahora(),
    }


def _registrar_lote_con_reintento(
    filas: list[dict[str, Any]],
) -> tuple[int, int]:
    """Registra el lote completo en una conexión; reintenta una vez si falla.

    Returns (registradas, fallidas).
    """
    for intento in range(1, 3):
        try:
            return upsert_lote_ofertas(filas)
        except Exception as exc:
            logger.error(
                f"Fallo registrando lote de ofertas (intento {intento}/2): {exc}"
            )
    return 0, len(filas)


def quedan_sets_por_aplicar(contexto: RunContext) -> ResultadoCaptura:
    """Decisión: ¿Quedan sets de filtros por aplicar? (v1.0).

    Calcula los sets pendientes SIN avanzar el iterador.
    """
    fuente = contexto.fuente_corriente
    if fuente is None:
        logger.error(f"ERR-01: fuente_corriente ausente en corrida {contexto.id_corrida}")
        return ResultadoCaptura(
            estado="error", codigo="ERR-01", descripcion="Fuente ausente"
        )
    total_sets = len(contexto.sets_validos(fuente))
    iterador_actual = contexto.iterador_sets.get(fuente.fuente_id, -1)
    sets_pendientes = total_sets - (iterador_actual + 1)
    decision = "si" if sets_pendientes > 0 else "no"
    return ResultadoCaptura(estado="ok", decision=decision, contexto=contexto)
