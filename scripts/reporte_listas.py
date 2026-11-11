"""Informe de lectura por lista de busqueda (D71; solo lectura).

Uso:
    python scripts/reporte_listas.py [--db RUTA]

Responde "¿que lista me captura mas ofertas y cual me duplica mas?" con la
traza oficial: por cada lista (`listas_busquedas`, ids LT por posicion de
configuracion) muestra cuantas ofertas nuevas trajo, cuantos encuentros
duplicados provoco al recorrerla y de que listas venian esos duplicados
(`duplicados_descubiertas`, apuntes DUP). Nunca escribe nada.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.persistence import (
    change_path,
    contar_ofertas_sin_lista,
    leer_resumen_listas,
    reset_path,
)

_TOPE_FRASE = 92


def _frase_visible(texto: str) -> str:
    """Recorta la frase para la pantalla (la palabra completa vive en la BD)."""
    texto = " ".join(texto.split())
    if len(texto) <= _TOPE_FRASE:
        return texto
    return texto[: _TOPE_FRASE - 3].rstrip() + "..."


def componer_informe() -> list[str]:
    """Lineas del informe; lanza `OperationalError` si la estructura aun
    no existe (el `main` la convierte en un mensaje legible)."""
    resumen = leer_resumen_listas()
    lineas: list[str] = ["Informe por lista de busqueda (solo lectura)", ""]

    if not resumen:
        lineas.append(
            "La tabla de listas esta vacia: se llenara sola cuando corra la "
            "proxima tanda del descubrimiento."
        )
        return lineas

    total_nuevas = 0
    total_duplicados = 0
    for fila in resumen:
        id_lista = fila["id_lista"]
        ofertas = int(fila["ofertas"])
        duplicados = int(fila["duplicados"])
        total_nuevas += ofertas
        total_duplicados += duplicados
        origenes = fila["origenes"]
        parte_origen = (
            ", ".join(
                f"{origen if origen else 'sin atribucion'}={conteo}"
                for origen, conteo in sorted(
                    origenes.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            )
            if origenes
            else "sin duplicados"
        )
        lineas.append(
            f"{id_lista} | capturadas: {ofertas} | duplicados: {duplicados}"
        )
        lineas.append(f"    duplicados venian de: {parte_origen}")
        lineas.append(f"    frase: {_frase_visible(fila['texto'])}")
    lineas.append("")
    lineas.append(f"Totales | capturadas: {total_nuevas} | duplicados: {total_duplicados}")
    sin_lista = contar_ofertas_sin_lista()
    if sin_lista:
        lineas.append(
            f"Ademas, {sin_lista} ofertas previas al cambio quedan sin lista "
            "(historico; se descartaran al limpiar la base a futuro)."
        )
    return lineas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="ruta alternativa a la base de datos")
    argumentos = parser.parse_args(argv)
    if argumentos.db:
        change_path(Path(argumentos.db))
    try:
        try:
            print("\n".join(componer_informe()))
        except sqlite3.OperationalError:
            print(
                "El informe todavia no esta disponible: la base no tiene aun "
                "la estructura de listas y duplicados (se crea sola con la "
                "proxima tanda del descubrimiento)."
            )
    finally:
        if argumentos.db:
            reset_path()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
