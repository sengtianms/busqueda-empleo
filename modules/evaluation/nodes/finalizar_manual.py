"""Nodo terminal compartido de los dos procesos del Módulo 3 (Fase 3).

Convergencia de todas las terminaciones de la exportación y de la importación.
Espejo de los cierres de los Módulos 1 y 2 con las diferencias que declara la
ficha v2.0: motivos propios por proceso, métricas calculadas desde los eventos
de la corrida (el `id_corrida` de la oferta nunca se sobrescribe), eventos de
narración excluidos de `total_sucesos` y liberación del bloqueo solo si la
corrida lo posee.

Semántica best-effort: ningún paso del cierre aborta; un fallo se anota en la
bitácora y se continúa. El evento de terminación se escribe después de consultar
las métricas, de modo que nunca se cuenta a sí mismo (D30). El informe del
operador se devuelve listo, pero mostrarlo y notificarlo son piezas de la capa
de operación de la Fase 4.

Los identificadores son españoles conforme a la excepción registrada para los
nodos de `modules/evaluation/` (D49 y D76).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from modules.evaluation.run_context import RunContext
from shared.persistence import (
    actualizar_corrida,
    contar_narracion,
    escribir_evento_seguro,
    leer_eventos_de_corridas,
    liberar_bloqueo,
)
from shared.utilidades import acotar_evidencia, ahora

_PROCESOS = frozenset({"exportacion", "importacion"})

# Motivo oficial -> estado de `corridas` (tablas de los dos cierres).
_ESTADOS_POR_MOTIVO: dict[str, str] = {
    "evaluacion_pendiente": "completada",
    "sin_pendientes": "sin_pendientes",
    "sin_resultados": "sin_pendientes",
    "corrida_completada": "completada",
    "error_total": "abortada",
    "error_critico": "abortada",
    "aborto": "abortada",
    "concurrencia": "abortada",
}

# Motivos cuyo evento de terminación es un suceso (ambas tablas).
_MOTIVOS_SUCESO = frozenset(
    {
        "evaluacion_pendiente",
        "sin_pendientes",
        "sin_resultados",
        "corrida_completada",
        "concurrencia",
    }
)

_MOTIVOS_POR_PROCESO: dict[str, frozenset[str]] = {
    "exportacion": frozenset(
        {
            "evaluacion_pendiente",
            "sin_pendientes",
            "error_total",
            "error_critico",
            "aborto",
            "concurrencia",
        }
    ),
    "importacion": frozenset(
        {
            "corrida_completada",
            "sin_resultados",
            "error_total",
            "error_critico",
            "aborto",
            "concurrencia",
        }
    ),
}

# Columnas propias de `corridas` que se persisten en cada proceso.
_COLUMNAS_POR_PROCESO: dict[str, tuple[str, ...]] = {
    "exportacion": ("total_ofertas", "total_errores", "total_sucesos"),
    "importacion": (
        "total_aprobadas",
        "total_descartadas",
        "total_ofertas",
        "total_errores",
        "total_sucesos",
    ),
}

_RE_CANTIDAD = re.compile(r"cantidad=(\d+)")


@dataclass
class ResultadoFinalizarManual:
    """Salida del cierre, entregada al orquestador y a la Fase 4."""

    estado: str  # "ok"
    contexto: RunContext | None = None
    codigo: str = ""  # motivo oficial resuelto
    metricas: dict[str, int] | None = None
    informe: dict[str, Any] = field(default_factory=dict)


def _distintos(eventos: list[dict[str, Any]], codigo: str) -> int:
    """Ofertas únicas de un código de suceso (D31: 'N/A' cuenta como vacío)."""
    ids = {
        str(evento.get("id_oferta"))
        for evento in eventos
        if evento.get("codigo") == codigo
        and str(evento.get("id_oferta", "")) not in ("", "N/A", "None")
    }
    return len(ids)


def _consultar_metricas(proceso: str, id_corrida: str) -> dict[str, int] | None:
    """Paso 1: métricas desde los eventos de la corrida; un solo reintento."""
    for intento in (1, 2):
        try:
            eventos = leer_eventos_de_corridas([id_corrida])
            total_errores = sum(1 for e in eventos if e.get("tipo") == "error")
            total_sucesos = sum(1 for e in eventos if e.get("tipo") == "suceso") - contar_narracion(
                id_corrida
            )
            if proceso == "exportacion":
                exportados = [e for e in eventos if e.get("codigo") == "ofertas_exportadas"]
                total_ofertas = 0
                for evento in exportados:
                    hallazgo = _RE_CANTIDAD.search(str(evento.get("evidencia", "")))
                    total_ofertas += int(hallazgo.group(1)) if hallazgo else 1
                return {
                    "lotes": len(exportados),
                    "total_ofertas": total_ofertas,
                    "pendientes": sum(
                        1 for e in eventos if e.get("codigo") == "exportacion_omitida"
                    ),
                    "total_errores": total_errores,
                    "total_sucesos": total_sucesos,
                }
            aprobadas = _distintos(eventos, "oferta_aprobada")
            descartadas = _distintos(eventos, "oferta_descartada")
            todas = {
                str(e.get("id_oferta"))
                for e in eventos
                if e.get("codigo") in ("oferta_aprobada", "oferta_descartada")
                and str(e.get("id_oferta", "")) not in ("", "N/A", "None")
            }
            return {
                "total_aprobadas": aprobadas,
                "total_descartadas": descartadas,
                "total_ofertas": len(todas),
                "rechazadas": sum(1 for e in eventos if e.get("codigo") == "evaluacion_rechazada"),
                "total_errores": total_errores,
                "total_sucesos": total_sucesos,
            }
        except Exception as exc:
            logger.error(
                f"Metricas no consultables (intento {intento}/2) | "
                f"run={id_corrida} | proceso={proceso} | {exc}"
            )
    return None


def _resolver_motivo(
    proceso: str,
    contexto: RunContext | None,
    motivo: str | None,
    metricas: dict[str, int] | None,
) -> str:
    """Prioridad: motivo explícito > fijado en el contexto > derivado."""
    if motivo:
        return motivo
    if contexto is not None and contexto.motivo_cierre:
        return contexto.motivo_cierre
    if metricas is None:
        return "aborto"
    if proceso == "exportacion":
        if (
            contexto is not None
            and contexto.hubo_candidatas
            and metricas["total_ofertas"] == 0
            and metricas["total_errores"] > 0
        ):
            return "error_total"
        if metricas["total_ofertas"] > 0 or metricas["pendientes"] > 0:
            return "evaluacion_pendiente"
        return "sin_pendientes"
    if (
        contexto is not None
        and contexto.hubo_resultados
        and metricas["total_ofertas"] == 0
        and (metricas["rechazadas"] > 0 or metricas["total_errores"] > 0)
    ):
        return "error_total"
    if metricas["total_ofertas"] > 0:
        return "corrida_completada"
    return "sin_resultados"


def _evidencia(proceso: str, metricas: dict[str, int] | None, contexto: RunContext | None) -> str:
    if metricas is None:
        return "metricas=no_disponibles"
    if proceso == "exportacion":
        campos: tuple[str, ...] = (
            f"lotes={metricas['lotes']}",
            f"pendientes={metricas['pendientes']}",
            f"ofertas={metricas['total_ofertas']}",
            f"errores={metricas['total_errores']}",
            f"sucesos={metricas['total_sucesos']}",
        )
    else:
        cerrados = len(contexto.lotes_cerrados) if contexto is not None else 0
        conservados = len(contexto.lotes_conservados) if contexto is not None else 0
        no_eliminados = len(contexto.archivos_no_eliminados) if contexto is not None else 0
        campos = (
            f"aprobadas={metricas['total_aprobadas']}",
            f"descartadas={metricas['total_descartadas']}",
            f"ofertas={metricas['total_ofertas']}",
            f"rechazadas={metricas['rechazadas']}",
            f"lotes_cerrados={cerrados}",
            f"lotes_conservados={conservados}",
            f"no_eliminados={no_eliminados}",
            f"errores={metricas['total_errores']}",
            f"sucesos={metricas['total_sucesos']}",
        )
    return acotar_evidencia(" | ".join(campos))


def _construir_informe(
    proceso: str,
    contexto: RunContext | None,
    metricas: dict[str, int] | None,
    id_corrida: str = "",
) -> dict[str, Any]:
    """Informe del operador: se calcula aquí; mostrarlo es labor de la Fase 4."""
    if contexto is None:
        # Concurrencia y fallo de INICIO con id cierran sin contexto: la corrida
        # existe y su identificador debe llegar al informe y al aviso.
        return {"proceso": proceso, "id_corrida": id_corrida}
    base: dict[str, Any] = {"proceso": proceso, "id_corrida": contexto.id_corrida}
    if proceso == "exportacion":
        base.update(
            {
                "lotes": contexto.contador_lotes,
                "exportadas": contexto.contador_exportadas,
                "errores": contexto.contador_errores,
                "pendientes": metricas.get("pendientes", 0) if metricas else 0,
            }
        )
    else:
        base.update(
            {
                "aprobadas": contexto.contador_aprobadas,
                "descartadas": contexto.contador_descartadas,
                "rechazadas": contexto.contador_rechazadas,
                "lotes_cerrados": list(contexto.lotes_cerrados),
                "lotes_conservados": list(contexto.lotes_conservados),
                "faltantes": dict(contexto.faltantes_por_lote),
                "archivos_rechazados": list(contexto.archivos_rechazados),
                "archivos_no_eliminados": list(contexto.archivos_no_eliminados),
            }
        )
    return base


def _escribir_evento_terminacion(
    id_corrida: str,
    proceso: str,
    motivo: str,
    metricas: dict[str, int] | None,
    contexto: RunContext | None,
) -> None:
    """Paso 2: evento de terminación; nunca aborta."""
    escribir_evento_seguro(
        {
            "id_corrida": id_corrida,
            "tipo": "suceso" if motivo in _MOTIVOS_SUCESO else "error",
            "codigo": motivo,
            "evidencia": _evidencia(proceso, metricas, contexto),
            "marca_temporal": ahora(),
        },
        contexto_log=id_corrida,
    )


def _persistir_cierre_corrida(
    id_corrida: str,
    proceso: str,
    estado: str,
    motivo: str,
    metricas: dict[str, int] | None,
) -> None:
    """Paso 3: cierre de la corrida con un reintento; nunca aborta."""
    campos: dict[str, Any] = {
        "estado": estado,
        "fecha_fin": ahora(),
        "motivo_terminacion": motivo,
        "fuentes_procesadas": 0,
    }
    if metricas is not None:
        for columna in _COLUMNAS_POR_PROCESO[proceso]:
            campos[columna] = metricas[columna]
    for intento in (1, 2):
        try:
            actualizar_corrida(id_corrida, campos)
            return
        except Exception as exc:
            logger.error(
                f"actualizar_corrida fallo (intento {intento}/2) | run={id_corrida} | {exc}"
            )
    logger.error(f"Corrida no persistida | run={id_corrida} | estado={estado} | {motivo}")


def cerrar_recursos(contexto: RunContext | None) -> None:
    """Paso 4: los procesos manuales no dejan recursos HTTP abiertos."""
    if contexto is None:
        return
    # El contexto se conserva intacto para el informe; no hay sesión que cerrar.
    return


def _liberar_bloqueo(id_corrida: str) -> None:
    """Paso 5: libera el bloqueo solo si esta corrida es su dueña."""
    try:
        liberar_bloqueo(id_corrida)
    except Exception as exc:
        logger.error(f"liberar_bloqueo fallo | run={id_corrida} | {exc}")


def finalizar_proceso(
    contexto: RunContext | None = None,
    proceso: str = "exportacion",
    motivo: str | None = None,
    id_corrida: str = "",
) -> ResultadoFinalizarManual:
    """Ejecuta los pasos del cierre en orden obligatorio (ficha v2.0)."""
    if proceso not in _PROCESOS:
        raise ValueError(f"proceso desconocido: {proceso}")
    id_corrida = (contexto.id_corrida if contexto is not None else "") or id_corrida

    metricas = _consultar_metricas(proceso, id_corrida) if id_corrida else None
    motivo_resuelto = _resolver_motivo(proceso, contexto, motivo, metricas)
    if motivo_resuelto not in _MOTIVOS_POR_PROCESO[proceso]:
        logger.warning(
            f"Motivo fuera del catalogo de {proceso} | run={id_corrida} | "
            f"motivo={motivo_resuelto}: se conserva por trazabilidad"
        )
    estado = _ESTADOS_POR_MOTIVO.get(motivo_resuelto, "abortada")

    if id_corrida:
        try:
            _escribir_evento_terminacion(id_corrida, proceso, motivo_resuelto, metricas, contexto)
        except Exception as exc:
            logger.error(
                f"Evento de terminacion no persistible | run={id_corrida} | "
                f"motivo={motivo_resuelto} | {exc}"
            )
        _persistir_cierre_corrida(id_corrida, proceso, estado, motivo_resuelto, metricas)

    cerrar_recursos(contexto)
    if id_corrida:
        _liberar_bloqueo(id_corrida)

    informe = _construir_informe(proceso, contexto, metricas, id_corrida)
    if contexto is not None:
        contexto.informe = informe
    resumen = (
        " | ".join(f"{clave}={valor}" for clave, valor in (metricas or {}).items())
        or "metricas=no_disponibles"
    )
    logger.info(
        f"Corrida finalizada | run={id_corrida} | proceso={proceso} | "
        f"motivo={motivo_resuelto} | {resumen}"
    )
    return ResultadoFinalizarManual(
        estado="ok",
        contexto=contexto,
        codigo=motivo_resuelto,
        metricas=metricas,
        informe=informe,
    )
