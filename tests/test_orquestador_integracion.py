from contextlib import ExitStack
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from modules.discovery.orchestrator import ejecutar_flujo
from shared.models import CaptureBatch, EntryResult, EstadoCaptura, Offer, SearchResult
from shared.persistence import consultar_bloqueo, leer_tabla

_CONFIG: dict[str, Any] = {
    "fuentes": [
        {
            "fuente_id": "linkedin",
            "nombre": "LinkedIn",
            "ficha_acceso": {
                "enlace": "https://www.linkedin.com/jobs/search",
                "tipo_acceso": "publico",
                "criterio_exito": "global-nav",
                "timeout_segundos": 30,
            },
            "sets_de_filtros": [
                {
                    "indice_set": 0,
                    "filtros": [{"tipo": "keywords", "valor": ["Data Engineer"]}],
                }
            ],
            "politicas_de_captura": {
                "max_paginas": 5,
                "max_ofertas_por_corrida": 100,
                "pausa_entre_lotes_segundos": 0,
                "tope_espera_paginas_sucesivas_segundos": 5,
                "estrategia_anti_bloqueo": "none",
            },
        }
    ],
    "captura": {
        "max_paginas": 5,
        "max_ofertas_por_corrida": 100,
        "pausa_entre_lotes_segundos": 0,
        "tope_espera_paginas_sucesivas_segundos": 5,
        "estrategia_anti_bloqueo": "none",
    },
    "concurrencia": {"umbral_obsolescencia_minutos": 120},
    "retries": {
        "max_attempts": 2,
        "base_wait_seconds": 0,
        "max_wait_seconds": 0,
        "multiplier": 1,
    },
    "browser": {"headless": True},
    "_env": {},
}


class AdaptadorFalso:
    """Adaptador simulado: sustituye la red, no la lógica de los nodos."""

    def __init__(self) -> None:
        self.entradas = 0
        self.filtros = 0
        self.capturas = 0
        self.cierres = 0

    def enter_source(
        self,
        page: Any,
        ficha: Any,
        credenciales: dict[str, str] | None = None,
    ) -> EntryResult:
        self.entradas += 1
        return EntryResult(
            estado="exito",
            evidencia_acotada="ingreso simulado",
            numero_de_intentos=1,
        )

    def apply_filters(
        self,
        page: Any,
        ficha: Any,
        set_filtros: Any,
        politicas: Any,
    ) -> SearchResult:
        self.filtros += 1
        ofertas = [
            Offer(
                enlace="https://linkedin.com/jobs/1",
                titulo="Oferta 1",
                descripcion_original="Descripcion 1",
                id_externo="ext-1",
            ),
            Offer(
                enlace="https://linkedin.com/jobs/2",
                titulo="Oferta 2",
                descripcion_original="Descripcion 2",
                id_externo="ext-2",
            ),
        ]
        return SearchResult(
            estado="exito",
            evidencia_acotada="busqueda simulada",
            ofertas_primera_pagina=ofertas,
            estado_paginacion="fin",
            total_declarado=2,
            indice_set=set_filtros.indice,
            numero_de_intentos=1,
        )

    def capture_batch(
        self,
        page: Any,
        ficha: Any,
        set_filtros: Any,
        politicas: Any,
        desde_desplazamiento: int = 0,
        max_paginas: int | None = None,
        max_ofertas: int | None = None,
    ) -> tuple[CaptureBatch, EstadoCaptura]:
        self.capturas += 1
        lote = CaptureBatch(
            ofertas=[
                Offer(
                    enlace="https://linkedin.com/jobs/1",
                    titulo="Oferta 1",
                    descripcion_original="Descripcion 1",
                    id_externo="ext-1",
                ),
                Offer(
                    enlace="https://linkedin.com/jobs/2",
                    titulo="Oferta 2",
                    descripcion_original="Descripcion 2",
                    id_externo="ext-2",
                ),
            ],
            indice_set=set_filtros.indice,
        )
        return (
            lote,
            EstadoCaptura(
                estado="exito",
                paginas_consumidas=1,
                capturadas_acumuladas_fuente=2,
            ),
        )

    def close_session(self, page: Any) -> None:
        self.cierres += 1


class _PlaywrightFalso:
    """Sustituye el arranque de Chromium: el nodo de ingreso sigue real."""

    def start(self) -> "_PlaywrightFalso":
        self.page = MagicMock()
        browser = MagicMock()
        browser.new_page.return_value = self.page
        self.chromium = MagicMock()
        self.chromium.launch.return_value = browser
        self.chromium.launch_persistent_context.return_value = browser
        return self

    def stop(self) -> None:
        return None


@pytest.fixture
def adaptador_falso() -> AdaptadorFalso:
    return AdaptadorFalso()


def _parches(adaptador: AdaptadorFalso) -> list[Any]:
    return [
        patch("modules.discovery.nodes.inicio.load", return_value=_CONFIG),
        patch("modules.discovery.nodes.ingreso.load", return_value=_CONFIG),
        patch("shared.retry.load", return_value=_CONFIG),
        patch(
            "modules.discovery.nodes.ingreso.obtener_adaptador",
            return_value=adaptador,
        ),
        patch(
            "modules.discovery.nodes.busqueda.obtener_adaptador",
            return_value=adaptador,
        ),
        patch(
            "modules.discovery.nodes.captura.obtener_adaptador",
            return_value=adaptador,
        ),
        patch(
            "modules.discovery.nodes.finalizar.obtener_adaptador",
            return_value=adaptador,
        ),
        patch(
            "modules.discovery.nodes.ingreso.sync_playwright",
            return_value=_PlaywrightFalso(),
        ),
    ]


def test_flujo_completo_nodos_reales_persiste_y_cierra(
    temp_db_file: Any, adaptador_falso: Any
) -> None:
    with ExitStack() as stack:
        for parche in _parches(adaptador_falso):
            stack.enter_context(parche)
        ejecutar_flujo()

    corridas = leer_tabla("corridas")
    assert len(corridas) == 1
    assert corridas[0]["estado"] == "completada"

    ofertas = leer_tabla("ofertas_descubiertas")
    assert len(ofertas) == 2
    ids_externos = {o["id_externo"] for o in ofertas}
    assert ids_externos == {"ext-1", "ext-2"}

    sesiones = leer_tabla("sesiones")
    assert len(sesiones) == 1
    assert sesiones[0]["conteo"] == 2
    assert sesiones[0]["estado"] == "completa"

    eventos = leer_tabla("eventos")
    codigos = {e["codigo"] for e in eventos}
    assert "captura_completada" in codigos
    assert "ingreso_exitoso" in codigos
    assert "consulta_exitosa" in codigos
    captura_evidencia = next(
        e["evidencia"] for e in eventos if e["codigo"] == "captura_completada"
    )
    assert "duracion_s=" in captura_evidencia
    assert corridas[0]["total_sucesos"] == 4

    assert consultar_bloqueo() is None
    assert adaptador_falso.entradas == 1
    assert adaptador_falso.filtros == 1
    assert adaptador_falso.capturas == 1
    assert adaptador_falso.cierres == 1


def test_flujo_completo_segunda_corrida_reusa_indices_y_dedup(
    temp_db_file: Any, adaptador_falso: Any
) -> None:
    with ExitStack() as stack:
        for parche in _parches(adaptador_falso):
            stack.enter_context(parche)
        ejecutar_flujo()
        ejecutar_flujo()

    corridas = leer_tabla("corridas")
    assert len(corridas) == 2
    assert {c["estado"] for c in corridas} == {"completada"}

    ofertas = leer_tabla("ofertas_descubiertas")
    assert len(ofertas) == 2
