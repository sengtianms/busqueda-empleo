"""Adapter registry per platform source (D13).

Nodes resolve the platform adapter by ``fuente_id`` instead of importing a
concrete class: a new source only adds its adapter plus one registry entry,
keeping the flow (ingreso/busqueda/captura) unchanged.
"""

from typing import Any, Protocol

from modules.discovery.adapters.linkedin import FlowError, LinkedInAdapter
from shared.models import (
    CaptureBatch,
    EntryResult,
    EstadoCaptura,
    FichaFuente,
    PoliticasCaptura,
    SearchResult,
    SetFiltros,
)


class AdaptadorPlataforma(Protocol):
    """Contract every platform adapter must satisfy (enter/query/capture).

    Verified structurally by mypy strict: a new adapter is rejected at
    type-check time if it misses any method or returns a different model.
    """

    def enter_source(
        self,
        page: Any,
        ficha: FichaFuente,
        credenciales: dict[str, str] | None = None,
    ) -> EntryResult: ...

    def apply_filters(
        self,
        page: Any,
        ficha: FichaFuente,
        set_filtros: SetFiltros,
        politicas: PoliticasCaptura,
    ) -> SearchResult: ...

    def capture_batch(
        self,
        page: Any,
        ficha: FichaFuente,
        set_filtros: SetFiltros,
        politicas: PoliticasCaptura,
        desde_desplazamiento: int = 0,
        max_paginas: int | None = None,
        max_ofertas: int | None = None,
    ) -> tuple[CaptureBatch, EstadoCaptura]: ...

    def close_session(self, page: Any) -> None: ...


REGISTRO_ADAPTADORES: dict[str, type[AdaptadorPlataforma]] = {
    "linkedin": LinkedInAdapter,
}


def obtener_adaptador(fuente_id: str) -> AdaptadorPlataforma:
    """Return a fresh adapter instance for ``fuente_id``.

    Unknown sources fail with the official DOC-06 code
    ``fuente_no_soportada`` (no adapter registered, never retried)
    instead of crashing the run with an unexpected error.
    """
    clase = REGISTRO_ADAPTADORES.get(fuente_id)
    if clase is None:
        raise FlowError(
            "fuente_no_soportada",
            f"No adapter registered for source '{fuente_id}'.",
        )
    return clase()
