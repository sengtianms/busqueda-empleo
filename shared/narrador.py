"""Narración en vivo de las corridas manuales (Lote 2; nunca altera datos).

Las corridas automáticas arrancan desde el guion de la tanda programada,
que marca el proceso con `TANDA_PROGRAMADA=1`: ahí la narración queda
callada (la pantalla viva es el tablero `scripts/estado_corrida.py`).

En una corrida manual el proceso no lleva la marca y `narrar` imprime
líneas de avance amables en el propio terminal del usuario.

Es solo una bocina: no escribe en la base, no emite eventos y nunca lanza
excepciones que puedan detener un módulo.
"""

import os

MARCA_TANDA_PROGRAMADA = "TANDA_PROGRAMADA"


def narracion_activa() -> bool:
    """Verdadero si la corrida es manual (sin la marca de la tanda programada)."""
    return os.environ.get(MARCA_TANDA_PROGRAMADA) != "1"


def narrar(texto: str) -> None:
    """Imprime una línea de narración si la corrida es manual; nunca falla."""
    try:
        if narracion_activa():
            print(texto, flush=True)
    except Exception:  # la narración nunca detiene el flujo
        pass


def narrar_modulo(nombre: str) -> None:
    """Anuncia el arranque de un módulo en el terminal manual."""
    etiquetas = {
        "descubrimiento": "descubrimiento de ofertas",
        "preparacion": "preparación de ofertas",
        "evaluacion": "evaluación inicial",
    }
    etiqueta = etiquetas.get(nombre, nombre)
    narrar(f"▶ Módulo {nombre} — {etiqueta}")


def narrar_set(indice: int) -> None:
    """Anuncia el arranque de una búsqueda de filtros (Módulo 1)."""
    narrar(f"   ▶ Búsqueda de filtros #{indice}: lanzando…")


def narrar_captura(pagina: int, acumuladas: int) -> None:
    """Reporta el avance de la captura en el set (Módulo 1)."""
    narrar(f"   · captura: página {pagina} — {acumuladas} ofertas acumuladas")
