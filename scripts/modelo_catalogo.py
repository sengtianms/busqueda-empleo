"""Núcleo de diagnóstico del catálogo de ubicaciones (D83; solo lectura).

Clasifica las filas, comprueba las condiciones estructurales que exige el
Módulo 2 y detecta variantes de escritura con las mismas reglas del motor de
enlace. Lo usan la orden de mantenimiento y el prevuelo, sin duplicar reglas.
Identificadores en español según la excepción de la capa de operación (D74).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from modules.preparation.ubicaciones import CatalogoUbicaciones, normalizar_pais
from shared.utilidades import normalizar_texto

MUNICIPIO = "municipio"
DEPARTAMENTO = "departamento"
PAIS = "pais"
NO_APLICA = "no_aplica"
TIPOS = (MUNICIPIO, DEPARTAMENTO, PAIS, NO_APLICA)


def _vacio(valor: Any) -> bool:
    return valor is None or str(valor).strip() in ("", "N/A", "N/R")


def tipo_de_fila(fila: Mapping[str, Any]) -> str:
    """Clase de fila según el criterio que usa el motor al leer el catálogo."""
    if _vacio(fila.get("municipio")):
        if _vacio(fila.get("departamento")):
            return NO_APLICA if _vacio(fila.get("pais")) else PAIS
        return DEPARTAMENTO
    return MUNICIPIO


def es_estructural(fila: Mapping[str, Any]) -> bool:
    """Las filas 'no aplica' y 'solo país' son fijas: no se editan ni se fusionan."""
    return tipo_de_fila(fila) in (NO_APLICA, PAIS)


def clave_normalizada(fila: Mapping[str, Any]) -> tuple[str, str, str]:
    """Tupla que el motor considera la misma ubicación, con cualquier escritura.

    El municipio se limpia igual que el motor limpia el texto de la oferta: sin
    esto, «San José de Cúcuta» y «Cúcuta» parecerían dos filas distintas aunque
    el motor resuelve ambos textos a la segunda, dejando la primera inalcanzable.
    """
    municipio = normalizar_texto(str(fila.get("municipio") or ""))
    return (
        CatalogoUbicaciones.limpiar_municipio(municipio),
        normalizar_texto(str(fila.get("departamento") or "")),
        normalizar_pais(str(fila.get("pais") or "")),
    )


@dataclass(frozen=True)
class Variante:
    clave: tuple[str, str, str]
    ids: tuple[str, ...]
    descripciones: tuple[str, ...]


@dataclass(frozen=True)
class Diagnostico:
    total: int
    por_tipo: dict[str, int]
    por_origen: dict[str, int]
    no_aplica: int
    filas_pais: int
    variantes: tuple[Variante, ...]


def diagnosticar(filas: Iterable[Mapping[str, Any]]) -> Diagnostico:
    """Resume el catálogo y agrupa las filas que el motor vería como ambiguas."""
    lista = list(filas)
    por_tipo = Counter(tipo_de_fila(fila) for fila in lista)
    por_origen = Counter(str(fila.get("origen") or "N/A") for fila in lista)
    agrupadas: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for fila in lista:
        agrupadas[clave_normalizada(fila)].append(fila)
    variantes = tuple(
        Variante(
            clave=clave,
            ids=tuple(str(fila.get("id")) for fila in grupo),
            descripciones=tuple(
                f"{fila.get('municipio')}/{fila.get('departamento')}/"
                f"{fila.get('pais')}"
                for fila in grupo
            ),
        )
        for clave, grupo in agrupadas.items()
        if len(grupo) > 1
    )
    return Diagnostico(
        total=len(lista),
        por_tipo={tipo: por_tipo.get(tipo, 0) for tipo in TIPOS},
        por_origen=dict(por_origen),
        no_aplica=por_tipo.get(NO_APLICA, 0),
        filas_pais=por_tipo.get(PAIS, 0),
        variantes=variantes,
    )


def canonico_municipio(nombre: str) -> str:
    """Nombre que el motor usará finalmente para un municipio escrito por el operador."""
    normalizado = normalizar_texto(nombre)
    return CatalogoUbicaciones.limpiar_municipio(normalizado)
