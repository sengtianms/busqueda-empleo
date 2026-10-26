"""Tablero del estado de una tanda en vivo (Lote 1; solo lectura).

Uso:
    python scripts/estado_corrida.py [--seguir] [--intervalo SEG]
                                      [--umbral-congelada SEG] [--db RUTA]

Sin `--seguir` imprime una foto del instante; con `--seguir` el tablero se
refresca cada pocos segundos (sirve para una tanda automatica desde otra
terminal o para una manual desde una segunda). Nunca escribe: solo lee la
traza oficial (corridas, eventos, silla y conteos de ofertas).

Muestra: tanda en curso y su modulo; en que parte va el modulo (sets de
busqueda del descubrimiento con su captura y registro, universos de
candidatas de preparacion y evaluacion); errores de la tanda; senal de
vida; estado vital (en marcha / congelada / muerta o abandonada) y
estimacion de lo que falta con el ritmo real de esta misma tanda; si no
hay tanda, el veredicto de la ultima cerrada.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.config import load
from shared.persistence import (
    _db_path,
    change_path,
    consultar_bloqueo,
    ids_de_corrida_con_codigos,
    leer_eventos_de_corridas,
    leer_tabla,
    reset_path,
    resumen_ofertas_por_estado,
)
from shared.utilidades import FORMATO_TIMESTAMP, numero_secuencial_id

CODIGOS_TANDA = frozenset({"modulo_ejecutado", "modulo_fallido", "corrida_programada"})

# Un set de busqueda esta completo cuando dejo su captura o su registro; la
# union de ambos codigos, por indice de set, es la unidad de ritmo.
_CODIGOS_SET_COMPLETO = ("captura_completada", "ofertas_registradas")

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

_TOPE_ERRORES = 8
_TOPE_EVIDENCIA = 180
_UMBRAL_CONGELADA_DEFECTO = 600
_VENTANA_TANDA_DEFECTO = 900
# La estimacion avanza con el reloj, pero una corrida sin senales no la hace
# crecer sin limite: la ventana se detiene en el umbral de congelacion.
_TOPE_VENTANA_SEGUNDOS = _UMBRAL_CONGELADA_DEFECTO


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


def _campo(detalle: dict[str, str], clave: str) -> str:
    return detalle.get(clave, "N/R")


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


def _nombres_config() -> list[str]:
    """Orden oficial de modulos: config 'orquestador' con respaldo del registro."""
    try:
        cfg = load()
        seccion = cfg.get("orquestador") if isinstance(cfg, dict) else None
        nombres = seccion.get("modulos") if isinstance(seccion, dict) else None
        if isinstance(nombres, list) and nombres:
            return [str(n) for n in nombres]
    except Exception:  # visor defensivo: la configuración puede no estar lista
        pass
    return ["descubrimiento", "preparacion", "evaluacion"]


def _total_sets_config() -> int | None:
    """Numero de sets de filtros de la primera fuente; None si no se sabe."""
    try:
        cfg = load()
        fuentes = cfg.get("fuentes") if isinstance(cfg, dict) else None
        primera = fuentes[0] if isinstance(fuentes, list) and fuentes else {}
        sets = primera.get("sets_de_filtros") if isinstance(primera, dict) else None
        return len(sets) if isinstance(sets, list) and sets else None
    except Exception:  # visor defensivo: la configuración puede no estar lista
        return None


def _duracion_compacta(segundos: float) -> str:
    if segundos < 0:
        return "0s"
    if segundos < 60:
        return f"{int(segundos)}s"
    horas = int(segundos // 3600)
    minutos = int((segundos % 3600) // 60)
    restos = int(segundos % 60)
    if horas:
        return f"{horas}h {minutos:02d}m"
    return f"{minutos}m {restos:02d}s"


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


def _modulo_anunciado(
    tanda: dict[str, Any] | None, grupos: dict[str, list[dict[str, Any]]], nombres: list[str]
) -> str | None:
    """Ultimo modulo terminado y anunciado por la tanda (modulo=<nombre>;...)."""
    if tanda is None:
        return None
    ultimo: str | None = None
    for evento in grupos.get(str(tanda["id_corrida"]), []):
        if str(evento.get("codigo")) in {"modulo_ejecutado", "modulo_fallido"}:
            ultimo = _analizar_evidencia(str(evento.get("evidencia", ""))).get("modulo")
    return ultimo if ultimo in nombres else None


def _siguiente_en_lista(nombre: str, nombres: list[str]) -> str:
    try:
        indice = nombres.index(nombre)
    except ValueError:
        return nombre
    return nombres[indice + 1] if indice + 1 < len(nombres) else nombre


def _modulo_en_curso(
    anunciado: str | None,
    filas_modulo: list[dict[str, Any]],
    grupos: dict[str, list[dict[str, Any]]],
    nombres: list[str],
) -> tuple[dict[str, Any] | None, str]:
    """(fila del modulo en curso, nombre) a partir de anuncios y filas abiertas.

    Prioridad: una fila de modulo abierta que delata su familia de codigos
    es el modulo en curso; si ninguna delata, el nombre previsto viene del
    ultimo anuncio de la tanda (siguiente en la lista de la configuracion).
    """
    nombre_previsto = _siguiente_en_lista(anunciado, nombres) if anunciado else None
    fila_ciega: dict[str, Any] | None = None
    for fila in filas_modulo:
        delatado = _nombre_por_familia(grupos.get(str(fila["id_corrida"]), []))
        if delatado is not None:
            return fila, delatado
        if fila_ciega is None:
            fila_ciega = fila
    if nombre_previsto is not None and anunciado:
        return fila_ciega, nombre_previsto
    return fila_ciega, (nombre_previsto or "módulo en marcha")


def _distintos(eventos: list[dict[str, Any]], codigos: tuple[str, ...]) -> set[str]:
    return {
        str(e.get("id_oferta"))
        for e in eventos
        if str(e.get("codigo")) in codigos and str(e.get("id_oferta")) not in ("", "N/A")
    }


def _ultimo_evento(eventos: list[dict[str, Any]], codigo: str) -> dict[str, Any] | None:
    candidatos = [e for e in eventos if str(e.get("codigo")) == codigo]
    return candidatos[-1] if candidatos else None


def _conteo_estados(conteos: dict[str, int], estado: str) -> int:
    """Cantidad de ofertas en un estado (resumen pedido a la base)."""
    return int(conteos.get(estado, 0))


def _bloque_descubrimiento(
    fila: dict[str, Any] | None,
    eventos: list[dict[str, Any]],
    sets_total: int | None,
    instante: datetime | None = None,
) -> list[str]:
    """Progreso del modulo de descubrimiento a partir de sus eventos."""
    lineas: list[str] = []
    consultas = [e for e in eventos if str(e.get("codigo")) == "consulta_exitosa"]
    sets_hechos = {
        str(e.get("indice_set"))
        for e in consultas
        if str(e.get("indice_set", "")).isdigit()
    }
    hechos = len(sets_hechos)
    panorama = f" de {sets_total}" if sets_total else ""
    hecho = f"   · búsquedas de filtros terminadas: {hechos}{panorama}"
    lineas.append(hecho)
    tic_set = _ultimo_evento(eventos, "tic_set_iniciado")
    if tic_set:
        lineas.append(
            f"   · set en marcha: #{_texto(tic_set, 'indice_set')}"
            f" (empezado {_texto(tic_set, 'marca_temporal')[11:19]})"
        )
    tic_pagina = _ultimo_evento(eventos, "tic_captura_pagina")
    if tic_pagina:
        detalle = _analizar_evidencia(str(tic_pagina.get("evidencia", "")))
        lineas.append(
            f"   · captura en marcha: página {_campo(detalle, 'pagina')}"
            f" (acumuladas {_campo(detalle, 'acumuladas')})"
        )
    ultimo = _ultimo_evento(eventos, "consulta_exitosa")
    if ultimo:
        detalle = _analizar_evidencia(str(ultimo.get("evidencia", "")))
        lineas.append(
            f"   · última búsqueda: set {_texto(ultimo, 'indice_set') or _campo(detalle, 'set')}"
            f" (total declarado: {_campo(detalle, 'total')})"
        )
    captura = _ultimo_evento(eventos, "captura_completada")
    if captura:
        detalle = _analizar_evidencia(str(captura.get("evidencia", "")))
        lineas.append(
            f"   · última captura: {_campo(detalle, 'páginas')} páginas"
            f" | {_campo(detalle, 'ofertas')} ofertas"
            f" | duración {_campo(detalle, 'duracion_s')}s"
        )
    registro = _ultimo_evento(eventos, "ofertas_registradas")
    if registro:
        detalle = _analizar_evidencia(str(registro.get("evidencia", "")))
        lineas.append(
            f"   · último registro: {_campo(detalle, 'ofertas registradas')}"
            f" registradas de {_campo(detalle, 'total')}"
        )
    renovaciones = sum(1 for e in eventos if str(e.get("codigo")) == "navegador_renovado")
    if renovaciones:
        lineas.append(f"   · renovaciones preventivas del canal: {renovaciones}")
    # El ritmo se mide con sets COMPLETADOS (con captura o registro hechos), no
    # con busquedas cargadas: la captura es el grueso del tiempo y la busqueda
    # en curso aun no termino. Sin ningun set completo no hay estimacion honesta.
    completados = {
        str(e.get("indice_set"))
        for e in eventos
        if str(e.get("codigo")) in _CODIGOS_SET_COMPLETO
        and str(e.get("indice_set", "")).isdigit()
    }
    resto_de_sets = (sets_total - len(completados)) if sets_total else 0
    linea_estimacion = _estimacion_linea(
        fila,
        eventos,
        resto_de_sets,
        _CODIGOS_SET_COMPLETO,
        "indice_set",
        instante,
    )
    if linea_estimacion:
        lineas.append(linea_estimacion)
    return lineas


def _estimacion_linea(
    fila: dict[str, Any] | None,
    eventos: list[dict[str, Any]],
    restantes: int,
    codigos_unidad: tuple[str, ...],
    clave_unidad: str = "id_oferta",
    instante: datetime | None = None,
) -> str | None:
    """Estimacion con el ritmo real de esta misma corrida (unidades hechas).

    La ventana de medicion termina en el instante de la consulta (no en la
    ultima marca escrita): si una unidad tarda 80 s, su captura cuenta. La
    ventana nunca retrocede por detras de la ultima marca, para que un reloj
    de referencia anterior a la traza (pruebas) no produzca cifras absurdas,
    y se detiene en el umbral de congelacion: una corrida parada no hace
    crecer la estimacion.
    """
    if fila is None or restantes <= 0:
        return None
    inicio = _parsear(_texto(fila, "fecha_inicio"))
    if inicio is None:
        return None
    unidades = [e for e in eventos if str(e.get("codigo")) in codigos_unidad]
    ids = {
        str(e[clave_unidad])
        for e in unidades
        if e.get(clave_unidad) is not None
        and str(e.get(clave_unidad)).strip() not in ("", "N/A")
    }
    if not ids:
        return None
    ultima = _parsear(_texto(unidades[-1], "marca_temporal"))
    if ultima is None or ultima < inicio:
        return None
    fin = ultima
    if instante is not None and instante > ultima:
        # La ventana avanza con el reloj, pero se detiene en el umbral de
        # congelacion: una corrida parada no hace crecer la estimacion.
        fin = min(instante, ultima + timedelta(seconds=_TOPE_VENTANA_SEGUNDOS))
    ritmo = (fin - inicio).total_seconds() / len(ids)
    return (
        f"   · quedan ~{_duracion_compacta(restantes * ritmo)}"
        f" (ritmo de esta corrida: {_duracion_compacta(ritmo)} por unidad)"
    )


def _bloque_universo(
    nombre: str,
    fila: dict[str, Any] | None,
    eventos: list[dict[str, Any]],
    conteos: dict[str, int],
    instante: datetime | None = None,
) -> list[str]:
    """Progreso por universos de candidatas de preparacion o evaluacion."""
    if nombre == "preparacion":
        preparadas = len(_distintos(eventos, ("oferta_preparada",)))
        duplicadas = len(_distintos(eventos, ("oferta_duplicada",)))
        caidas = len(_distintos(eventos, ("preparacion_fallida",)))
        en_cola = _conteo_estados(conteos, "descubierta")
        unidades = f"   · preparadas {preparadas} · duplicadas {duplicadas}"
        if caidas:
            unidades += f" · con reintento pendiente {caidas}"
        unidades += f" · en cola: {en_cola}"
        lineas = [unidades]
        estimacion = _estimacion_linea(
            fila, eventos, en_cola, ("oferta_preparada",), instante=instante
        )
        if estimacion:
            lineas.append(estimacion)
        return lineas
    aprobadas = len(_distintos(eventos, ("oferta_aprobada",)))
    descartadas = len(_distintos(eventos, ("oferta_descartada",)))
    caidas = len(_distintos(eventos, ("evaluacion_fallida",)))
    en_cola = _conteo_estados(conteos, "preparada")
    unidades = f"   · aprobadas {aprobadas} · descartadas {descartadas}"
    if caidas:
        unidades += f" · con reintento pendiente {caidas}"
    unidades += f" · en cola: {en_cola}"
    lineas = [unidades]
    estimacion = _estimacion_linea(
        fila,
        eventos,
        en_cola,
        ("oferta_aprobada", "oferta_descartada"),
        instante=instante,
    )
    if estimacion:
        lineas.append(estimacion)
    return lineas


def _vida_de_tanda(
    tanda: dict[str, Any],
    latidos: list[dict[str, Any]],
    umbral: int,
    referencia: datetime,
    silla_tomada: bool,
) -> str:
    """Clasificacion vital: en marcha / congelada / muerta o abandonada."""
    marca_latido = _texto(latidos[-1], "marca_temporal") if latidos else ""
    marca = _parsear(marca_latido) or _parsear(_texto(tanda, "fecha_inicio"))
    base = marca or referencia
    silencio = max((referencia - base).total_seconds(), 0.0)
    if silencio > umbral:
        if silla_tomada:
            return f"congelada: {_duracion_compacta(silencio)} sin avances"
        return f"muerta o abandonada: {_duracion_compacta(silencio)} sin avances y silla libre"
    if not silla_tomada:
        return "en marcha (pausa entre módulos)"
    return "en marcha"


def _errores(
    ids: list[str], grupos: dict[str, list[dict[str, Any]]], tope: int = _TOPE_ERRORES
) -> list[dict[str, Any]]:
    errores = [
        e
        for id_corrida in ids
        for e in grupos.get(id_corrida, [])
        if str(e.get("tipo")) == "error"
    ]
    ordenados = sorted(errores, key=lambda e: _texto(e, "marca_temporal"), reverse=True)
    return ordenados[:tope]


def _linea_cierre(etiqueta: str, fila: dict[str, Any]) -> str:
    """Linea de veredicto de una corrida cerrada (tanda o tramo)."""
    return (
        f"  {etiqueta}: {_texto(fila, 'id_corrida')}"
        f" · cerró '{_texto(fila, 'estado')}'"
        f" ({_texto(fila, 'motivo_terminacion') or 'sin motivo'})"
        f" a las {_texto(fila, 'fecha_fin')[11:16]}"
        f" · errores: {fila.get('total_errores', 0)}"
    )


def _orden_cierre(fila: dict[str, Any]) -> tuple[str, int]:
    """Orden de cierre: marca temporal y, en empate, numero oficial (D53)."""
    return (
        _texto(fila, "fecha_fin"),
        numero_secuencial_id(str(fila.get("id_corrida"))),
    )


def _ultima_cerrada(corridas: list[dict[str, Any]]) -> dict[str, Any] | None:
    """La corrida cerrada mas reciente; None si no hay ninguna."""
    cerradas = [c for c in corridas if _texto(c, "fecha_fin") not in ("", "N/A")]
    return max(cerradas, key=_orden_cierre) if cerradas else None


def _traza_final(
    corridas: list[dict[str, Any]],
    grupos: dict[str, list[dict[str, Any]]],
    tramos: set[str],
    ultima_cerrada: dict[str, Any] | None,
) -> list[str]:
    """Bloque sin tanda: veredicto de la ultima tanda cerrada y su ultimo tramo.

    Regla de identidad: una corrida cerrada CON senales de modulo es un tramo;
    sin ellas es la tanda (lleve o no su resumen del orquestador, porque una
    tanda cortada a la fuerza se queda sin el), y a igual cierre gana el id
    menor (la tanda se registra antes que sus modulos). `tramos` llega de la
    consulta acotada de senales (mismo catalogo que `_nombre_por_familia`), de
    modo que el tablero no necesita cargar el historial de eventos cerrado.
    `ultima_cerrada` ya viene calculada por el llamador (`_ultima_cerrada`).
    """
    cerradas = [c for c in corridas if _texto(c, "fecha_fin") not in ("", "N/A")]
    if not cerradas or ultima_cerrada is None:
        return ["Sin tanda en curso y sin corridas previas registradas."]

    def _orden_tanda(fila: dict[str, Any]) -> tuple[str, int]:
        # A igual marca de cierre gana el id MENOR: la tanda registra su fila
        # antes de lanzar cada modulo, asi que una etapa que aborto en INICIO
        # (sin senales de modulo) no puede desplazarla.
        return (
            _texto(fila, "fecha_fin"),
            -numero_secuencial_id(str(fila.get("id_corrida"))),
        )

    def _es_tramo(fila: dict[str, Any]) -> bool:
        return _texto(fila, "id_corrida") in tramos

    tandas = [c for c in cerradas if not _es_tramo(c)]
    if not tandas:
        return ["Sin tanda en curso.", _linea_cierre("última corrida", ultima_cerrada)]
    tanda = max(tandas, key=_orden_tanda)
    lineas = ["Sin tanda en curso.", _linea_cierre("última tanda", tanda)]
    if _texto(tanda, "id_corrida") != _texto(ultima_cerrada, "id_corrida"):
        nombre = _nombre_por_familia(grupos.get(_texto(ultima_cerrada, "id_corrida"), []))
        lineas.append(
            f"  último tramo: {_texto(ultima_cerrada, 'id_corrida')}"
            f" ({nombre or 'módulo sin identificar'})"
        )
    return lineas


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


def componer_estado(
    referencia: datetime | None = None,
    *,
    sets_total: int | None = None,
    umbral_congelada: int = _UMBRAL_CONGELADA_DEFECTO,
    ventana_tanda: int = _VENTANA_TANDA_DEFECTO,
) -> list[str]:
    """Lineas del tablero para el instante de `referencia` (ahora por defecto)."""
    instante = referencia or datetime.now()
    sets_total = sets_total if sets_total is not None else _total_sets_config()
    bordes: list[str] = [f"== ESTADO DE LA TANDA — {instante.strftime('%H:%M:%S')} =="]
    retraso = _base_pendiente()
    if retraso is not None:
        return bordes + [f"⚠ La base de datos no está lista ({retraso}); no hay nada que mirar."]
    try:
        corridas = leer_tabla("corridas")
        abiertas = _abiertas(corridas)
        ultima_cerrada = _ultima_cerrada(corridas)
        ids_eventos = [_texto(c, "id_corrida") for c in abiertas]
        if ultima_cerrada is not None:
            ids_eventos.append(_texto(ultima_cerrada, "id_corrida"))
        eventos = _ordenar_eventos(leer_eventos_de_corridas(ids_eventos))
        grupos = _agrupar_por_corrida(eventos)
        silla = consultar_bloqueo()
    except Exception as exc:  # base vacía o sin tablas: panel legible, nunca crash
        return bordes + [f"⚠ La base de datos no está lista: {exc}"]

    id_silla = _texto(silla, "id_corrida") if silla else ""
    tanda, filas_modulo, ignoradas = _separar_abiertas(
        abiertas, grupos, id_silla, ventana_tanda
    )

    if tanda is None and not filas_modulo:
        ciegas = [c for c in ignoradas if not grupos.get(_texto(c, "id_corrida"), [])]
        if ciegas:
            detalladas = ", ".join(
                f"{_texto(c, 'id_corrida')} (desde {_texto(c, 'fecha_inicio')[11:16]})"
                for c in ciegas
            )
            return bordes + [f"Corrida(s) arrancando (todavía sin señales): {detalladas}"]
        try:
            tramos = ids_de_corrida_con_codigos(CODIGOS_MODULO)
        except Exception as exc:  # base sin tablas: panel legible, nunca crash
            return bordes + [f"⚠ La base de datos no está lista: {exc}"]
        return bordes + _traza_final(corridas, grupos, tramos, ultima_cerrada)

    ids_vivos: list[str] = []
    if tanda is not None:
        ids_vivos.append(_texto(tanda, "id_corrida"))
    if filas_modulo:
        ids_vivos.append(_texto(filas_modulo[0], "id_corrida"))

    nombres = _nombres_config()
    anunciado = _modulo_anunciado(tanda, grupos, nombres)
    fila_modulo, nombre_modulo = _modulo_en_curso(anunciado, filas_modulo, grupos, nombres)
    eventos_modulo = (
        grupos.get(_texto(fila_modulo, "id_corrida"), []) if fila_modulo is not None else []
    )
    ids_vivos = [i for i in ids_vivos if i]

    latidos = [e for id_corrida in ids_vivos for e in grupos.get(id_corrida, [])]
    latidos = _ordenar_eventos(latidos)

    if tanda is not None:
        inicio = _parsear(_texto(tanda, "fecha_inicio")) or instante
        vida = _vida_de_tanda(tanda, latidos, umbral_congelada, instante, silla is not None)
        bordes.append(
            f"Tanda: {vida}"
            f" · iniciada {_texto(tanda, 'fecha_inicio')[11:16]}"
            f" · lleva {_duracion_compacta((instante - inicio).total_seconds())}"
            f" · {_texto(tanda, 'id_corrida')}"
        )

    etiqueta = (
        f"{_texto(fila_modulo, 'id_corrida')} (desde {_texto(fila_modulo, 'fecha_inicio')[11:16]})"
        if fila_modulo is not None
        else "en pausa o a punto de arrancar"
    )
    bordes.append(f"Módulo en curso: {nombre_modulo} · {etiqueta}")
    if tanda is None:
        bordes.append("Corrida individual de módulo (sin tanda programada).")

    if nombre_modulo == "descubrimiento":
        bordes.append("Progreso del módulo:")
        bordes.extend(
            _bloque_descubrimiento(fila_modulo, eventos_modulo, sets_total, instante=instante)
        )
    elif nombre_modulo in MODULOS_UNIVERSO:
        try:
            conteos = resumen_ofertas_por_estado()
        except Exception as exc:  # base sin tablas: panel legible, nunca crash
            return bordes + [f"⚠ La base de datos no está lista: {exc}"]
        bordes.append("Progreso del módulo:")
        bordes.extend(
            _bloque_universo(nombre_modulo, fila_modulo, eventos_modulo, conteos, instante=instante)
        )

    marca_latido = _texto(latidos[-1], "marca_temporal") if latidos else ""
    ultima = _parsear(marca_latido)
    if ultima is not None:
        silencio = _duracion_compacta(max((instante - ultima).total_seconds(), 0.0))
        bordes.append(f"Última señal de vida: {silencio} ({marca_latido[11:19]})")

    avisos = _errores(ids_vivos, grupos)
    if avisos:
        bordes.append(f"Avisos de error en la tanda: {len(avisos)} (últimos)")
        for error in avisos:
            linea = (
                f"   · [{_texto(error, 'marca_temporal')[11:19]}] {_texto(error, 'codigo')}:"
                f" {_texto(error, 'evidencia')}"
            )
            bordes.append(linea[: _TOPE_EVIDENCIA])

    if ignoradas:
        nombres_ignoradas = ", ".join(_texto(c, "id_corrida") for c in ignoradas)
        bordes.append(
            f"⚠ Corridas abiertas sin dueño: {nombres_ignoradas} (posible muerte anterior)"
        )
    return bordes


def _vivir(intervalo: int, umbral: int) -> None:
    """Modo en vivo: refresca el tablero hasta Ctrl+C."""
    tty = sys.stdout.isatty()
    while True:
        lineas = componer_estado(umbral_congelada=umbral)
        if tty:
            print("\x1b[2J\x1b[H", end="")
        else:
            print()
        print("\n".join(lineas))
        time.sleep(max(intervalo, 1))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seguir", action="store_true", help="refrescar el tablero en vivo")
    parser.add_argument(
        "--intervalo", type=int, default=5, help="segundos entre refrescos (--seguir)"
    )
    parser.add_argument(
        "--umbral-congelada",
        type=int,
        default=_UMBRAL_CONGELADA_DEFECTO,
        help="segundos sin avances para avisar 'congelada'",
    )
    parser.add_argument("--db", help="ruta alternativa a la base de datos")
    argumentos = parser.parse_args(argv)
    if argumentos.umbral_congelada < 0:
        parser.error("el umbral de 'congelada' no puede ser negativo")
    if argumentos.db:
        change_path(Path(argumentos.db))
    try:
        if argumentos.seguir:
            try:
                _vivir(argumentos.intervalo, argumentos.umbral_congelada)
            except KeyboardInterrupt:
                print("\nTablero cerrado.")
        else:
            print(
                "\n".join(
                    componer_estado(umbral_congelada=argumentos.umbral_congelada)
                )
            )
    finally:
        if argumentos.db:
            reset_path()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
