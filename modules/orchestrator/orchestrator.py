"""Transversal orchestrator: scheduled run across functional modules.

Implements the node "Corrida programada — lanzar y supervisar módulos"
(ficha D34 v1.0). Loads and validates the `orquestador:` configuration
section, registers its own `corridas` row as the traceability container of
the summary, executes each configured module in strict order by calling its
public `ejecutar_flujo()` (modules load their own configuration), derives
each module's result from the database (RN-05: a closed run inside the
execution window — never from a return contract), emits `modulo_ejecutado`
per module (`modulo_fallido` when the module raises, ERR-03) plus the final
`corrida_programada` summary event, and closes its own run. A module failure
never stops the scheduled run (RN-04); only orchestrator-own failures abort
(ERR-01 config, ERR-02 run creation). Spanish identifiers per decision D38.
"""

import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from loguru import logger

from modules.discovery.orchestrator import ejecutar_flujo as flujo_descubrimiento
from modules.evaluation.orchestrator import ejecutar_flujo as flujo_evaluacion
from modules.preparation.orchestrator import ejecutar_flujo as flujo_preparacion
from shared.config import load
from shared.persistence import (
    actualizar_corrida,
    contar_filas,
    escribir_evento,
    generar_id,
    inicializar_si_ausente,
    leer_ultima_corrida_cerrada,
    registrar_corrida,
)
from shared.utilidades import acotar_evidencia, ahora

T = TypeVar("T")


@dataclass(frozen=True)
class ModuloOrquestado:
    """Declarative registry entry (ficha: nombre, estados, public flow)."""

    nombre: str
    estado_entrada: str
    estado_salida: str
    ejecutar_flujo: Callable[[], None]


MODULOS: list[ModuloOrquestado] = [
    ModuloOrquestado(
        "descubrimiento",
        estado_entrada="-",
        estado_salida="descubierta",
        ejecutar_flujo=flujo_descubrimiento,
    ),
    ModuloOrquestado(
        "preparacion",
        estado_entrada="descubierta",
        estado_salida="preparada/duplicada",
        ejecutar_flujo=flujo_preparacion,
    ),
    ModuloOrquestado(
        "evaluacion",
        estado_entrada="preparada",
        estado_salida="aceptada_ei/descartada_ei",
        ejecutar_flujo=flujo_evaluacion,
    ),
]

_MODO_SERIE = "serie"
_MODOS_VALIDOS = frozenset({_MODO_SERIE, "paralelo"})
_MOTIVO_COMPLETADA = "corrida_completada"


def _modulo_por_nombre(nombre: str) -> ModuloOrquestado | None:
    return next((m for m in MODULOS if m.nombre == nombre), None)


def _validar_configuracion(seccion: Any) -> str:
    """Returns "" when valid; otherwise the ERR-01 description (VAL-01..03)."""
    if not isinstance(seccion, dict):
        return "seccion 'orquestador' ausente o corrupta"
    modo = seccion.get("modo_ejecucion")
    if modo not in _MODOS_VALIDOS:
        return f"modo_ejecucion invalido: {modo!r}"
    if modo != _MODO_SERIE:
        # VAL-02/RN-08: parallel execution is documented but not implemented.
        return f"modo_ejecucion no implementado hoy: {modo!r}"
    nombres = seccion.get("modulos")
    if not isinstance(nombres, list) or not nombres:
        return "'modulos' debe ser una lista no vacia"
    for nombre in nombres:
        if not isinstance(nombre, str) or _modulo_por_nombre(nombre) is None:
            return f"modulo no registrado: {nombre!r}"
    pausa = seccion.get("pausa_entre_modulos_segundos")
    if not isinstance(pausa, (int, float)) or isinstance(pausa, bool) or pausa < 0:
        return "pausa_entre_modulos_segundos debe ser un numero >= 0"
    return ""


def _con_reintento_unico(accion: Callable[[], T], descripcion: str) -> T | None:
    """Runs `accion` with exactly ONE retry, whatever the failure carrier.

    Ficha ERR-02/ERR-05 ("Reint. Sí — reintento único"): BD failures carry no
    retryable `codigo_motivo`, so `ejecutar_con_reintento` would never retry
    them (same reason Finalizar Proceso uses a manual single-retry loop);
    here the retry is unconditional. Returns None once both attempts fail.
    """
    for intento in (1, 2):
        try:
            return accion()
        except Exception as exc:
            logger.error(f"{descripcion} fallido | intento={intento} | {exc}")
    return None


def _evento_best_effort(
    id_corrida: str, tipo: str, codigo: str, evidencia: str
) -> None:
    """ERR-04: summary-event writes never abort the scheduled run."""
    try:
        escribir_evento(
            {
                "id_corrida": id_corrida,
                "tipo": tipo,
                "codigo": codigo,
                "evidencia": acotar_evidencia(evidencia),
            }
        )
    except Exception as exc:
        logger.error(
            f"Evento de resumen no persistible | run={id_corrida} | "
            f"codigo={codigo} | {exc}"
        )


def _resumen_de_fila(fila: dict[str, Any] | None) -> tuple[str, str, str]:
    """(estado, motivo, id_corrida) for the evidence; `no_iniciada` when none."""
    if fila is None:
        return ("no_iniciada", "N/A", "N/A")
    motivo = fila.get("motivo_terminacion") or "N/A"
    return (str(fila["estado"]), str(motivo), str(fila["id_corrida"]))


def _cerrar_programada_best_effort(id_corrida: str, campos: dict[str, Any]) -> None:
    """ERR-05: closes the scheduled run with a single retry; logs on failure."""
    cerrada = _con_reintento_unico(
        lambda: actualizar_corrida(id_corrida, campos),
        f"Cierre de corrida programada {id_corrida}",
    )
    if cerrada is None:
        logger.error(
            f"Cierre de corrida programada agotado | run={id_corrida} | "
            "la traza queda en eventos"
        )
    else:
        logger.info(f"Corrida programada {id_corrida} cerrada")


def ejecutar_corrida_programada(config: dict[str, Any] | None = None) -> None:
    """Run every configured module in order and record the scheduled-run summary."""
    if inicializar_si_ausente():
        logger.info("Esquema de base de datos creado automaticamente")
    cfg = config if config is not None else load()
    seccion = cfg.get("orquestador") if isinstance(cfg, dict) else None
    detalle = _validar_configuracion(seccion)
    if detalle:
        # ERR-01: nothing launched and nothing registered -> nothing closable.
        logger.error(f"Configuracion orquestador invalida | {detalle}")
        print(f"[ERROR] Configuracion orquestador invalida | {detalle}")
        return
    assert isinstance(seccion, dict)
    nombres: list[str] = list(seccion["modulos"])
    pausa = float(seccion["pausa_entre_modulos_segundos"])

    marca_inicio = ahora()

    def _crear() -> str:
        id_nuevo = str(generar_id("corridas"))
        registrar_corrida(
            {
                "id_corrida": id_nuevo,
                "fecha_inicio": marca_inicio,
                "estado": "en_ejecucion",
            }
        )
        return id_nuevo

    resultado = _con_reintento_unico(_crear, "Creacion de corrida programada")
    # ERR-02: persistent creation failure leaves nothing closable.
    if not isinstance(resultado, str):
        logger.error("Corrida programada no creada: modulos no lanzados (ERR-02)")
        return
    id_programada = resultado

    atribuidos = [id_programada]
    resultados: list[str] = []
    try:
        for indice, nombre in enumerate(nombres):
            modulo = _modulo_por_nombre(nombre)
            assert modulo is not None  # VAL-03 already validated
            logger.info(f"Modulo {nombre} iniciado")
            codigo_evento = "modulo_ejecutado"
            tipo_evento = "suceso"
            try:
                modulo.ejecutar_flujo()
            except Exception as exc:
                # ERR-03/RN-04: capture, record the real state, continue.
                logger.error(f"Modulo {nombre} lanzo una excepcion | {exc}")
                codigo_evento = "modulo_fallido"
                tipo_evento = "error"
            fila = leer_ultima_corrida_cerrada(marca_inicio, atribuidos)
            estado, motivo, id_modulo = _resumen_de_fila(fila)
            if id_modulo != "N/A":
                atribuidos.append(id_modulo)
            _evento_best_effort(
                id_programada,
                tipo_evento,
                codigo_evento,
                (
                    f"modulo={nombre};estado={estado};motivo={motivo};"
                    f"id_corrida={id_modulo}"
                ),
            )
            resultados.append(f"{nombre}={estado}")
            if indice < len(nombres) - 1 and pausa > 0:
                time.sleep(pausa)

        _evento_best_effort(
            id_programada,
            "suceso",
            "corrida_programada",
            ";".join(resultados),
        )
        sucesos = contar_filas(
            "eventos", {"id_corrida": id_programada, "codigo": "modulo_ejecutado"}
        )
        errores = contar_filas(
            "eventos", {"id_corrida": id_programada, "codigo": "modulo_fallido"}
        )
        _cerrar_programada_best_effort(
            id_programada,
            {
                "estado": "completada",
                "fecha_fin": ahora(),
                "motivo_terminacion": _MOTIVO_COMPLETADA,
                "total_sucesos": sucesos,
                "total_errores": errores,
                "total_ofertas": 0,
                "fuentes_procesadas": 0,
            },
        )
        logger.info(
            "Corrida programada finalizada | "
            + " | ".join(resultados)
            + f" | sucesos={sucesos} errores={errores}"
        )
    except Exception as exc:
        # Orchestrator-own unexpected failure after registration (RN-06):
        # the partial summary is still recorded before the abort closure.
        logger.error(
            f"Orquestador fallo de forma inesperada | run={id_programada} | {exc}"
        )
        resumen_parcial = ";".join(resultados) if resultados else "sin_modulos"
        _evento_best_effort(
            id_programada, "suceso", "corrida_programada", resumen_parcial
        )
        _cerrar_programada_best_effort(
            id_programada,
            {
                "estado": "abortada",
                "fecha_fin": ahora(),
                "motivo_terminacion": "error_critico",
            },
        )
