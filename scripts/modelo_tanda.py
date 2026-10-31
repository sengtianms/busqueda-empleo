"""Núcleo de la traza en marcha (punto 5): biblioteca de la sala de observación.

Todo lo que el tablero de la terminal mira y el centinela de la tanda aplica
para saber QUÉ está pasando —sin pintar nada— vive aquí: vocabulario oficial
de códigos, cómo se ordenan y agrupan eventos, cómo se separan las corridas
abiertas en tanda / módulo en curso / sobrantes, cuánto silencio llena cada
una y los dos umbrales de decisión, que se leen de la configuración oficial
(sección `visibilidad:`) con respaldo si la configuración no los trae.

Consumidores: `scripts/estado_corrida.py` (el dibujante: lectura + texto de
pantalla), `scripts/vigilante_tanda.py` (el centinela) y
`scripts/control_tandas.py` (mandos del operador). Ninguno escribe aquí rastro
del usuario: sólo lectura de la traza oficial y de la configuración.

Decisión de reestructura (punto 5, 2026-10-31): el núcleo sale del archivo del
tablero, que era antes la biblioteca y el dibujante a la vez; centinela y
mandos tomaban sus piezas prestadas de forma interna. Con esta separación,
retocar la pantalla no puede romper al centinela, y los umbrales compartidos
viven en un solo sitio.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from shared.config import load
from shared.persistence import _db_path
from shared.utilidades import FORMATO_TIMESTAMP, numero_secuencial_id

DEFAULT_UMBRAL_CONGELADA = 600
DEFAULT_VENTANA_TANDA = 900

CODIGOS_TANDA = frozenset({"modulo_ejecutado", "modulo_fallido", "corrida_programada"})

# Un set de busqueda esta completo cuando dejo su captura o su registro; la
# union de ambos codigos, por indice de set, es la unidad de ritmo.
CODIGOS_SET_COMPLETO = ("captura_completada", "ofertas_registradas")

# Codigos propios de cada modulo: nombran una corrida abierta de un modulo
# cuando su fila todavia no fue anunciada por el resumen de la tanda.
FAMILIAS_CODIGOS: dict[str, frozenset[str]] = {
    "descubrimiento": frozenset(
        {
            "ingreso_exitoso",
            "consulta_exitosa",
            "captura_completada",
            "ofertas_registradas",
            "navegador_renovado",
            "lote_degradado",
        }
    ),
    "preparacion": frozenset(
        {
            "oferta_preparada",
            "preparacion_fallida",
            "oferta_duplicada",
            "revision_pendientes",
        }
    ),
    "evaluacion": frozenset(
        {"oferta_aprobada", "oferta_descartada", "evaluacion_fallida"}
    ),
}

# Señales que identifican una corrida de módulo para la regla de identidad
# tanda/tramo: el tic de arranque más los códigos propios de cada familia.
CODIGOS_MODULO = frozenset({"tic_modulo_iniciado"}).union(*FAMILIAS_CODIGOS.values())

MODULOS_UNIVERSO = frozenset({"preparacion", "evaluacion"})


def _valor_visibilidad(clave: str, defecto: int) -> int:
    """Valor de `visibilidad:` (config oficial); respaldo si falta o es inválido."""
    try:
        cfg = load()
        seccion = cfg.get("visibilidad") if isinstance(cfg, dict) else None
        valor = seccion.get(clave) if isinstance(seccion, dict) else None
        if isinstance(valor, int) and not isinstance(valor, bool) and valor > 0:
            return valor
    except Exception:  # lector defensivo: la configuración puede no estar lista
        pass
    return defecto


def umbral_congelada_segundos() -> int:
    """Segundos sin señales para considerar detenida la tanda (config, 600)."""
    return _valor_visibilidad("umbral_congelada_segundos", DEFAULT_UMBRAL_CONGELADA)


def ventana_tanda_segundos() -> int:
    """Ventana para reconocer que una fila arrancó junto a su tanda (config, 900)."""
    return _valor_visibilidad("ventana_tanda_segundos", DEFAULT_VENTANA_TANDA)


def _analizar_evidencia(texto: str) -> dict[str, str]:
    """Pares clave=valor (o clave: valor) de una evidencia oficial ('|' o ';')."""
    pares: dict[str, str] = {}
    for fragmento in str(texto or "").replace("|", ";").split(";"):
        if "=" in fragmento:
            clave, valor = fragmento.split("=", 1)
        elif ":" in fragmento:
            clave, valor = fragmento.split(":", 1)
        else:
            continue
        pares[clave.strip()] = valor.strip()
    return pares


def _parsear(marca: str) -> datetime | None:
    try:
        return datetime.strptime(str(marca), FORMATO_TIMESTAMP)
    except (TypeError, ValueError):
        return None


def _texto(fila: dict[str, Any], clave: str) -> str:
    valor = fila.get(clave)
    return "" if valor is None else str(valor)


def _abiertas(corridas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filas de corrida sin cierre: fecha_fin ausente, vacia o 'N/A'."""
    return [c for c in corridas if _texto(c, "fecha_fin") in ("", "N/A")]


def _ordenar_eventos(eventos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Orden determinista: marca temporal y, en empate, numero oficial."""
    return sorted(
        eventos,
        key=lambda e: (
            _texto(e, "marca_temporal"),
            numero_secuencial_id(str(e.get("evento_id", ""))),
        ),
    )


def _agrupar_por_corrida(eventos: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grupos: dict[str, list[dict[str, Any]]] = {}
    for evento in _ordenar_eventos(eventos):
        grupos.setdefault(str(evento.get("id_corrida")), []).append(evento)
    return grupos


def _es_tanda(fila: dict[str, Any], grupos: dict[str, list[dict[str, Any]]]) -> bool:
    return any(
        str(e.get("codigo")) in CODIGOS_TANDA
        for e in grupos.get(str(fila.get("id_corrida")), [])
    )


def _nombre_por_familia(eventos: list[dict[str, Any]]) -> str | None:
    """Nombre del módulo: por su tic de arranque o por sus códigos propios."""
    for evento in eventos:
        if str(evento.get("codigo")) == "tic_modulo_iniciado":
            nombre = _analizar_evidencia(str(evento.get("evidencia", ""))).get("modulo")
            if nombre:
                return nombre
    for nombre, codigos in FAMILIAS_CODIGOS.items():
        if any(str(e.get("codigo")) in codigos for e in eventos):
            return nombre
    return None


def _separar_abiertas(
    abiertas: list[dict[str, Any]],
    grupos: dict[str, list[dict[str, Any]]],
    id_silla: str,
    ventana_segundos: int,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """(tanda, fila del módulo en curso, sobrantes) entre las filas abiertas.

    Anclas oficiales: el módulo en curso es la abierta dueña de la silla
    (la garantía de concurrencia la marca mientras corre) o, si la silla no
    delata fila, la más nueva con códigos propios de módulo. La tanda es la
    abierta con eventos de resumen del orquestador y, a falta de ellos, la
    más nueva que arrancó dentro de la ventana de las pruebas (registra su
    fila segundos antes de lanzar cada módulo). Todo lo demás son
    sobrantes (corridas que quedaron abiertas, probablemente muertas).

    `ventana_segundos` llega del clasificador (config `visibilidad:`).
    """
    if not abiertas:
        return None, [], []
    reciente = sorted(abiertas, key=lambda c: _texto(c, "fecha_inicio"), reverse=True)
    modulo = next(
        (
            c
            for c in reciente
            if _texto(c, "id_corrida") == id_silla
            or _nombre_por_familia(grupos.get(_texto(c, "id_corrida"), [])) is not None
        ),
        None,
    )
    resto = [c for c in reciente if c is not modulo]
    tanda = next((c for c in resto if _es_tanda(c, grupos)), None)
    if tanda is None:
        if modulo is None:
            return None, [], resto
        _nexo_modulo_inicio = _parsear(_texto(modulo, "fecha_inicio"))
        previos = [
            c for c in resto if _arranco_junto(c, _nexo_modulo_inicio, ventana_segundos)
        ]
        tanda = previos[0] if previos else None
    sobrantes = [c for c in resto if c is not tanda]
    return tanda, ([] if modulo is None else [modulo]), sobrantes


def _arranco_junto(fila: dict[str, Any], inicio_modulo: datetime | None, ventana: int) -> bool:
    """Verdadero si la fila arrancó dentro de `ventana` antes del módulo."""
    if inicio_modulo is None:
        return False
    inicio_fila = _parsear(_texto(fila, "fecha_inicio"))
    if inicio_fila is None:
        return False
    separacion = (inicio_modulo - inicio_fila).total_seconds()
    return 0 <= separacion <= ventana


def _silencio_de(
    fila: dict[str, Any], eventos: list[dict[str, Any]], instante: datetime
) -> float:
    """Segundos de silencio PROPIOS de una corrida (sus eventos o su origen).

    Base: el último evento de esa corrida; si no emitió nada, su fecha de
    inicio. Nunca negativa (una marca en el futuro se ve como 0 segundos).
    """
    id_corrida = _texto(fila, "id_corrida")
    base: datetime | None = None
    for evento in eventos:
        if _texto(evento, "id_corrida") == id_corrida:
            marca = _parsear(_texto(evento, "marca_temporal"))
            if marca is not None and (base is None or marca > base):
                base = marca
    if base is None:
        base = _parsear(_texto(fila, "fecha_inicio"))
    if base is None:
        return float("inf")
    return max((instante - base).total_seconds(), 0.0)


def _base_pendiente() -> str | None:
    """Motivo por el que la base no está lista para leerse; None si está bien.

    Verificación previa a toda lectura: con la base ausente el lector
    genérico crearía el archivo vacío (efecto colateral de escritura que
    un visor de solo lectura no debe provocar).
    """
    try:
        ruta = _db_path()
    except Exception:  # configuración rota: dejar que las lecturas expliquen
        return None
    if not Path(ruta).exists():
        return f"el archivo de datos no existe todavía: {ruta}"
    return None
