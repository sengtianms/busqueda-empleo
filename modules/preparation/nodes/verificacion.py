"""Verificación de duplicidad node of the Preparation flow (ficha M2 v1.0).

Process node, 100 % local (RN-01): no AI, no HTTP, no catalogs. It compares
offers already prepared with RapidFuzz in two stages — stage 1 exact match on
`(titulo_normalizado, empresa_id)` via an in-memory O(1) index, stage 2 fuzzy
title AND description thresholds restricted to the same company — and marks
re-publications as `duplicada` pointing at the original (`id_duplicidad`).

Universes (RN-05/06): pendientes = `preparada` with `fecha_ultima_verificacion
= ''`; comparison universe = `preparada` with `id_duplicidad = 'N/A'`
(excludes `duplicada` so chains never form, excludes `descubierta`). The
universe INCLUDES the current lot's other pendings so same-pass duplicates
are detected; an offer simply never matches against itself. This node is the
only writer of `fecha_ultima_verificacion` (marker "already checked for
duplicates", RN-09) and never touches `id_corrida` (RN-12).

Approved interpretation notes (sub-phase 5.4):
- P1: offers whose company could not be extracted (`empresa_id = 'N/A'`,
  capture ERR-07) are excluded from matching on BOTH sides: `'N/A' == 'N/A'`
  would falsely equate different companies, breaking RN-02's same-company
  requirement. They only receive the verification marker.
- T4: when several candidates tie, the original is the OLDEST offer
  (smallest sequential `id`, FIFO guarantee of RN-07) compared numerically
  via `numero_secuencial_id` (D53 — the raw-text order flips past 9.999
  offers per prefix).
- T6: a pending may only match candidates with a SMALLER sequential id
  (numeric via `numero_secuencial_id`, D53). Within a same pass the ids are
  sequential (RN-07: oldest prepared first is the original), so this makes
  the older offer the original and prevents two intra-lot duplicates from
  marking each other mutually.
"""

from dataclasses import dataclass
from typing import Any

from loguru import logger
from rapidfuzz import fuzz

from modules.preparation.nodes.preparacion import FalloPreparacion
from modules.preparation.run_context import RunContext
from shared.persistence import (
    actualizar_fila,
    leer_tabla,
    registrar_evento,
)
from shared.retry import ejecutar_con_reintento
from shared.utilidades import ahora, normalizar_texto, numero_secuencial_id

# Values meaning "no usable data" for the fuzzy stage (RN-08) and for the
# same-company requirement (P1).
_SIN_DATO = {"", "N/A", "N/R"}


@dataclass
class ResultadoVerificacion:
    """Outcome handed to the flow: `completada` or `abortada` (ERR-01/03)."""

    estado: str
    contexto: RunContext | None = None
    codigo: str = ""
    descripcion: str = ""
    duplicadas: int = 0
    verificadas: int = 0
    errores: int = 0


def _registrar_evento(
    id_corrida: str, tipo: str, codigo: str, evidencia: str, id_oferta: str
) -> None:
    """VAL-05: every offer event carries `id_oferta`; evidence bounded.

    Public so the sibling decision node reuses it (single implementation of
    the M2 offer-event contract). D42: delega en el emisor unico compartido."""
    registrar_evento(
        id_corrida=id_corrida,
        tipo=tipo,
        codigo=codigo,
        evidencia=evidencia,
        id_oferta=id_oferta,
    )


def _abortar(
    contexto: RunContext, codigo: str, descripcion: str
) -> ResultadoVerificacion:
    _registrar_evento(contexto.id_corrida, "error", codigo, descripcion, "N/A")
    logger.error(f"{codigo} | {contexto.id_corrida} | {descripcion}")
    return ResultadoVerificacion(
        estado="abortada", contexto=contexto, codigo=codigo, descripcion=descripcion
    )


def _politica_reintentos(contexto: RunContext) -> dict[str, float]:
    reintentos = contexto.config_preparacion["retries"]
    return {
        "max_attempts": int(reintentos["max_attempts"]),
        "base_wait": float(reintentos["base_wait_seconds"]),
        "multiplier": float(reintentos["multiplier"]),
        "max_wait": float(reintentos["max_wait_seconds"]),
    }


def _consultar_con_reintento(
    contexto: RunContext, filtros: dict[str, Any]
) -> list[dict[str, Any]]:
    """ERR-01: DB reads retry via the shared helper; exhaustion raises."""
    politica = _politica_reintentos(contexto)

    def _leer() -> list[dict[str, Any]]:
        try:
            return leer_tabla("ofertas_descubiertas", filtros)
        except Exception as exc:
            # Generic SQLite failures become flow-code failures so the shared
            # helper actually retries them (ERR-01).
            raise FalloPreparacion("error_bd", str(exc)) from exc

    def _fallo(exc: BaseException, intentos: int) -> list[dict[str, Any]]:
        raise FalloPreparacion("error_bd", f"{exc} tras {intentos} intentos") from exc

    resultado, _ = ejecutar_con_reintento(
        _leer,
        al_fallo_final=_fallo,
        max_attempts=int(politica["max_attempts"]),
        base_wait=politica["base_wait"],
        multiplier=politica["multiplier"],
        max_wait=politica["max_wait"],
        contexto_log=contexto.id_corrida,
    )
    return resultado


def _validar_umbrales(config: dict[str, Any]) -> str | None:
    """VAL-01: both thresholds present and within [0, 100]. None → valid."""
    for clave in ("umbral_titulo", "umbral_descripcion"):
        if clave not in config:
            return f"falta {clave}"
        valor = config[clave]
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            return f"{clave} no numerico"
        if not 0 <= float(valor) <= 100:
            return f"{clave} fuera de rango"
    return None


def _anexar_observaciones(anteriores: str, evidencia: str) -> str:
    """T3: append evidence preserving previous observations; a leading
    placeholder collapses so it never reads `N/A; DUP ...`."""
    if anteriores.strip() in _SIN_DATO:
        return evidencia
    return f"{anteriores}; {evidencia}"


def _construir_indice(universo: list[dict[str, Any]]) -> tuple[
    dict[tuple[str, str], str],
    dict[str, list[tuple[str, str, str]]],
]:
    """Sheet paso 3 (VAL-03): exact index by `(titulo_normalizado, empresa_id)`
    plus the per-company candidate pool for the fuzzy stage. P1: entries
    without a real company or title never enter either structure."""
    indice_exacto: dict[tuple[str, str], str] = {}
    candidatos_difusos: dict[str, list[tuple[str, str, str]]] = {}
    for fila in universo:
        empresa_id = str(fila.get("empresa_id", "N/A"))
        if empresa_id in _SIN_DATO:
            continue
        titulo_norm = normalizar_texto(str(fila.get("titulo", "")))
        if titulo_norm == "":
            continue
        descripcion_norm = normalizar_texto(str(fila.get("descripcion_original", "")))
        oferta_id = str(fila["id"])
        clave = (titulo_norm, empresa_id)
        # Keep the oldest id on collision (T4, numeric per D53).
        if clave not in indice_exacto or numero_secuencial_id(oferta_id) < numero_secuencial_id(
            indice_exacto[clave]
        ):
            indice_exacto[clave] = oferta_id
        candidatos_difusos.setdefault(empresa_id, []).append(
            (oferta_id, titulo_norm, descripcion_norm)
        )
    return indice_exacto, candidatos_difusos


def _buscar_etapa_2(
    pendiente: dict[str, Any],
    candidatos: list[tuple[str, str, str]],
    umbral_titulo: float,
    umbral_descripcion: float,
    marcadas_en_pasada: set[str],
) -> tuple[str, float, float] | None:
    """Stage 2 (RN-04/08): fuzzy title >= umbral_titulo AND description >=
    umbral_descripcion among same-company candidates. Returns the matched
    original id with its percentages (oldest wins ties, T4), or None.
    Descriptions without usable data never match (no false positives)."""
    titulo_norm = normalizar_texto(str(pendiente.get("titulo", "")))
    descripcion_pendiente = normalizar_texto(
        str(pendiente.get("descripcion_original", ""))
    )
    if titulo_norm == "" or descripcion_pendiente in _SIN_DATO:
        return None
    id_propio = str(pendiente.get("id"))
    mejor: tuple[str, float, float] | None = None
    for candidato_id, titulo_candidato, descripcion_candidato in candidatos:
        # Only an OLDER offer can be the original (T6, numeric per D53);
        # offers marked this pass are no longer candidates (no chains).
        candidato_no_antiguo = numero_secuencial_id(candidato_id) >= numero_secuencial_id(
            id_propio
        )
        if candidato_no_antiguo or candidato_id in marcadas_en_pasada:
            continue
        if descripcion_candidato in _SIN_DATO:
            continue
        pct_titulo = fuzz.token_sort_ratio(titulo_norm, titulo_candidato)
        if pct_titulo < umbral_titulo:
            continue
        pct_descripcion = fuzz.partial_ratio(
            descripcion_pendiente, descripcion_candidato
        )
        if pct_descripcion < umbral_descripcion:
            continue
        if mejor is None or numero_secuencial_id(candidato_id) < numero_secuencial_id(
            mejor[0]
        ):
            mejor = (candidato_id, pct_titulo, pct_descripcion)
    return mejor


def ejecutar_verificacion(contexto: RunContext | None) -> ResultadoVerificacion:
    """Run the Verificación de duplicidad node (sheet pasos funcionales 1-6)."""
    if contexto is None or not isinstance(contexto, RunContext):
        logger.error(
            "ERR-01 | sin id_corrida | contexto ausente o corrupto: "
            "no se puede ejecutar la verificación"
        )
        return ResultadoVerificacion(
            estado="abortada",
            codigo="ERR-01",
            descripcion="contexto ausente o corrupto",
        )
    id_corrida = contexto.id_corrida

    # Paso 1 — VAL-01: umbrales presentes y en rango (T5 → ERR-03).
    problema = _validar_umbrales(contexto.config_preparacion)
    if problema is not None:
        return _abortar(contexto, "ERR-03", f"insumos invalidos: {problema}")

    umbral_titulo = float(contexto.config_preparacion["umbral_titulo"])
    umbral_descripcion = float(contexto.config_preparacion["umbral_descripcion"])
    politica = _politica_reintentos(contexto)

    # Paso 2 — consult pendings + universe (ERR-01 retries; abort on exhaust).
    try:
        pendientes = _consultar_con_reintento(
            contexto, {"estado": "preparada", "fecha_ultima_verificacion": ""}
        )
        universo = _consultar_con_reintento(
            contexto, {"estado": "preparada", "id_duplicidad": "N/A"}
        )
    except FalloPreparacion as error:
        return _abortar(contexto, "ERR-01", f"fallo de bd en consulta: {error.detalle}")

    # Paso 3 — build the stage-1 index and the fuzzy candidate pool. The
    # universe includes the current lot's other pendings (RN-05); an offer
    # never matches against itself (self-id filtered at lookup time).
    indice_exacto, candidatos_difusos = _construir_indice(universo)

    duplicadas = 0
    verificadas = 0
    errores = 0
    # Offers marked as duplicates DURING this pass stop being candidates for
    # the remaining pendings: with non-transitive similarity (U~V, V~W, but
    # U≁W) a later pending could otherwise chain W→V instead of pointing at
    # the original U (RN-05 "sin cadenas").
    marcadas_en_pasada: set[str] = set()

    # Pasos 4-5 — evaluate each pending and persist its outcome.
    for pendiente in pendientes:
        oferta_id = str(pendiente["id"])
        empresa_id = str(pendiente.get("empresa_id", "N/A"))
        marcador = ahora()

        id_original = ""
        pct_titulo = 100.0
        pct_descripcion = 100.0
        etapa = 1
        if empresa_id not in _SIN_DATO:
            titulo_norm = normalizar_texto(str(pendiente.get("titulo", "")))
            hallado = indice_exacto.get((titulo_norm, empresa_id), "")
            # Only an OLDER offer can be the original (self excluded, T6);
            # offers marked this pass are no longer candidates (no chains).
            if hallado >= oferta_id or hallado in marcadas_en_pasada:
                hallado = ""
            if not hallado:
                hallazgo = _buscar_etapa_2(
                    pendiente,
                    candidatos_difusos.get(empresa_id, []),
                    umbral_titulo,
                    umbral_descripcion,
                    marcadas_en_pasada,
                )
                if hallazgo is not None:
                    etapa = 2
                    hallado, pct_titulo, pct_descripcion = hallazgo
            id_original = hallado
        es_duplicada = bool(id_original)
        evidencia = (
            f"DUP etapa{etapa} | {pct_titulo:.0f}% titulo | "
            f"{pct_descripcion:.0f}% desc | original={id_original}"
        )

        def _escribir(origen: str = id_original) -> bool:
            datos: dict[str, Any] = {
                "fecha_ultima_verificacion": marcador,
                "fecha_ultima_edicion": ahora(),
            }
            if origen:
                datos["estado"] = "duplicada"
                datos["id_duplicidad"] = origen
                datos["observaciones"] = _anexar_observaciones(
                    str(pendiente.get("observaciones", "N/A")), evidencia
                )
            try:
                return actualizar_fila("ofertas_descubiertas", oferta_id, datos)
            except Exception as exc:
                # Generic SQLite failures become flow-code failures so the
                # shared helper actually retries them (ERR-02).
                raise FalloPreparacion("error_bd", str(exc)) from exc

        def _fallo_escritura(exc: BaseException, intentos: int) -> bool:
            raise FalloPreparacion(
                "error_bd", f"{exc} tras {intentos} intentos"
            ) from exc

        try:
            _, _ = ejecutar_con_reintento(
                _escribir,
                al_fallo_final=_fallo_escritura,
                max_attempts=int(politica["max_attempts"]),
                base_wait=politica["base_wait"],
                multiplier=politica["multiplier"],
                max_wait=politica["max_wait"],
                contexto_log=id_corrida,
            )
        except FalloPreparacion as error:
            # ERR-02: the offer stays pending (unverified) and the flow continues.
            errores += 1
            logger.warning(
                f"ERR-02 | run={id_corrida} | oferta={oferta_id} | "
                f"{error.detalle}: queda pendiente para la próxima corrida"
            )
            continue

        verificadas += 1
        if es_duplicada:
            duplicadas += 1
            # Persisted: this id stops being a candidate for later pendings.
            marcadas_en_pasada.add(oferta_id)
            _registrar_evento(
                id_corrida,
                "suceso",
                "oferta_duplicada",
                evidencia,
                oferta_id,
            )

    # Keep the context counters coherent with the preparation node's usage
    # (Finalizar Proceso computes its metrics from events via SQL, D36).
    contexto.contador_duplicadas += duplicadas
    contexto.contador_errores += errores
    logger.info(
        f"VERIFICACION COMPLETADA | run={id_corrida} | evaluadas={verificadas} "
        f"duplicadas={duplicadas} errores={errores}"
    )
    return ResultadoVerificacion(
        estado="completada",
        contexto=contexto,
        duplicadas=duplicadas,
        verificadas=verificadas,
        errores=errores,
    )
