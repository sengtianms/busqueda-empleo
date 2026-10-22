from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from modules.discovery.adapters import linkedin as linkedin_mod
from modules.discovery.adapters.linkedin import (
    _URL_FEED,
    _URL_LOGIN,
    FlowError,
    LinkedInAdapter,
)
from modules.discovery.adapters.tarjetas import (
    _extraer_tarjeta_sdui,
    _fecha_relativa_a_datetime,
)
from shared.models import FichaFuente, PoliticasCaptura, SetFiltros

FIXTURES = Path(__file__).resolve().parent / "fixtures"

URL_BUSQUEDA = "https://www.linkedin.com/jobs/search"

URL_CON_FILTROS = (
    "https://www.linkedin.com/jobs/search?keywords=Data+Engineer"
    "&f_SAL=f_SA_id_225001%3A272001"
)

URL_RESULTADOS = URL_CON_FILTROS.replace(
    "https://www.linkedin.com/jobs/search",
    "https://www.linkedin.com/jobs/search-results/",
)

URL_SIN_MODALIDAD = (
    "https://www.linkedin.com/jobs/search-results/?keywords=Data+Engineer"
)


def _leer(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _sin_memoria() -> Any:
    """Los tests históricos usan el modo automático sin memoria."""
    with patch(
        "modules.discovery.adapters.linkedin._hay_memoria_sesion", return_value=False
    ):
        yield


class FakePage:
    """Playwright-like page served from a dict of URL -> HTML."""

    def __init__(self, por_url: dict[str, str]) -> None:
        self.por_url = por_url
        self._actual = ""
        self.url = ""
        self.gotos: list[str] = []
        self.wait_untils: list[str | None] = []
        self.cerrada = False
        self.keyboard = FakeKeyboard()
        self.esperas: list[tuple[str, str | None, int | None]] = []
        self.clics: list[str] = []

    def goto(self, enlace: str, wait_until: str | None = None) -> None:
        self.gotos.append(enlace)
        self.wait_untils.append(wait_until)
        self.url = enlace
        self._actual = self.por_url.get(enlace, "")

    def content(self) -> str:
        return self._actual

    def fill(self, selector: str, valor: str) -> None:
        pass

    def click(self, selector: str, timeout: int | None = None) -> None:
        self.clics.append(selector)

    def wait_for_selector(
        self,
        selector: str,
        timeout: int | None = None,
        state: str | None = None,
    ) -> None:
        self.esperas.append((selector, state, timeout))

    def wait_for_timeout(self, ms: int) -> None:
        pass

    def close(self) -> None:
        self.cerrada = True


class FakeKeyboard:
    """Playwright-like keyboard stub with no-op press."""

    def press(self, tecla: str) -> None:
        pass


@pytest.fixture
def ficha_publica() -> FichaFuente:
    return FichaFuente(
        fuente_id="linkedin",
        nombre="LinkedIn",
        enlace="https://www.linkedin.com/jobs/search",
        tipo_acceso="publico",
        criterio_exito="global-nav",
        timeout_segundos=5,
    )


@pytest.fixture
def ficha_autenticada() -> FichaFuente:
    return FichaFuente(
        fuente_id="linkedin",
        nombre="LinkedIn",
        enlace="https://www.linkedin.com/jobs/search",
        tipo_acceso="con_autenticacion",
        credenciales_referencia=["LINKEDIN_EMAIL", "LINKEDIN_PASSWORD"],
        criterio_exito="global-nav",
        timeout_segundos=5,
    )


@pytest.fixture
def set_filtros() -> SetFiltros:
    return SetFiltros(
        fuente_id="linkedin",
        indice=0,
        filtros=[
            {"tipo": "keywords", "valor": ["Data Engineer"]},
            {"tipo": "modalidad", "valor": "remoto"},
        ],
    )


@pytest.fixture
def set_filtros_sin_modalidad() -> SetFiltros:
    return SetFiltros(
        fuente_id="linkedin",
        indice=0,
        filtros=[{"tipo": "keywords", "valor": ["Data Engineer"]}],
    )


@pytest.fixture
def politicas() -> PoliticasCaptura:
    return PoliticasCaptura(
        max_paginas=2,
        max_ofertas_por_corrida=2,
        pausa_entre_lotes_segundos=0,
        estrategia_anti_bloqueo="none",
    )


def test_enter_source_exito(ficha_publica: FichaFuente) -> None:
    pagina = FakePage({ficha_publica.enlace: _leer("lista_linkedin.html")})
    resultado = LinkedInAdapter().enter_source(pagina, ficha_publica)
    assert resultado.estado == "exito"


def test_enter_source_autenticada_sin_credenciales(
    ficha_autenticada: FichaFuente,
) -> None:
    pagina = FakePage({ficha_autenticada.enlace: _leer("lista_linkedin.html")})
    with pytest.raises(FlowError) as exc:
        LinkedInAdapter().enter_source(pagina, ficha_autenticada)
    assert exc.value.codigo_motivo == "credenciales_no_disponibles"


def test_enter_source_autenticada_con_credenciales(
    ficha_autenticada: FichaFuente,
) -> None:
    pagina = FakePage(
        {
            URL_BUSQUEDA: _leer("lista_linkedin.html"),
            _URL_LOGIN: "<html><body>global-nav login</body></html>",
        }
    )
    resultado = LinkedInAdapter().enter_source(
        pagina,
        ficha_autenticada,
        {"username": "usuario", "password": "clave"},
    )
    assert resultado.estado == "exito"
    assert pagina.gotos == [_URL_LOGIN]


def test_enter_source_detach_lento_fallback_no_falla(
    ficha_autenticada: FichaFuente,
) -> None:
    class FakePageDetachLento(FakePage):
        """FakePage where the username field never detaches within 15s and the
        submit-button fallback click always fails (button already gone)."""

        def __init__(self, por_url: dict[str, str]) -> None:
            super().__init__(por_url)
            self.clickes = 0

        def wait_for_selector(
            self,
            selector: str,
            timeout: int | None = None,
            state: str | None = None,
        ) -> None:
            if state == "detached":
                raise TimeoutError("detach lento")
            self.esperas.append((selector, state, timeout))

        def click(self, selector: str, timeout: int | None = None) -> None:
            self.clickes += 1
            raise TimeoutError("boton ausente")

    pagina = FakePageDetachLento({_URL_LOGIN: "<html><body>global-nav login</body></html>"})
    resultado = LinkedInAdapter().enter_source(
        pagina,
        ficha_autenticada,
        {"username": "usuario", "password": "clave"},
    )
    assert resultado.estado == "exito"
    assert pagina.clickes == 1


def test_enter_source_con_memoria_sesion_valida_no_toca_formulario(
    ficha_autenticada: FichaFuente,
) -> None:
    """Con sesión guardada va directo sin escribir credenciales."""
    pagina = FakePage({_URL_FEED: "<html><body>global-nav feed</body></html>"})
    with patch(
        "modules.discovery.adapters.linkedin._hay_memoria_sesion", return_value=True
    ):
        resultado = LinkedInAdapter().enter_source(pagina, ficha_autenticada)

    assert resultado.estado == "exito"
    assert "persistente" in resultado.evidencia_acotada
    assert pagina.gotos == [_URL_FEED]


def test_enter_source_con_memoria_espera_ingreso_manual(
    ficha_autenticada: FichaFuente,
) -> None:
    """Sin sesión muestra el ingreso y sigue cuando el usuario entra."""
    class PaginaManual(FakePage):
        def __init__(self) -> None:
            super().__init__({_URL_FEED: "<html><body>login</body></html>"})
            self.lecturas = 0

        def content(self) -> str:
            self.lecturas += 1
            if self.url == _URL_LOGIN and self.lecturas > 3:
                return "<html><body>global-nav feed</body></html>"
            return super().content()

    pagina = PaginaManual()
    with patch.object(linkedin_mod, "_hay_memoria_sesion", return_value=True):
        resultado = LinkedInAdapter(sleep_fn=lambda _: None).enter_source(
            pagina, ficha_autenticada
        )

    assert resultado.estado == "exito"
    assert "manual" in resultado.evidencia_acotada
    assert pagina.gotos[0] == _URL_FEED
    assert _URL_LOGIN in pagina.gotos


def test_enter_source_con_memoria_tiempo_agotado(
    ficha_autenticada: FichaFuente,
) -> None:
    """Si el usuario no ingresa a tiempo falla sin escribir nada."""
    pagina = FakePage({_URL_FEED: "<html><body>login</body></html>"})
    with (
        patch.object(linkedin_mod, "_hay_memoria_sesion", return_value=True),
        patch.object(linkedin_mod, "_espera_manual", return_value=0),
    ):
        with pytest.raises(FlowError) as exc:
            LinkedInAdapter(sleep_fn=lambda _: None).enter_source(
                pagina, ficha_autenticada
            )
    assert exc.value.codigo_motivo == "criterio_no_cumplido"


def test_enter_source_con_memoria_no_acepta_marca_en_pagina_de_ingreso(
    ficha_autenticada: FichaFuente,
) -> None:
    """D9: la marca dentro del código del formulario no vale como sesión."""
    pagina = FakePage(
        {
            _URL_FEED: (
                "<html><body>MainFeed bundles "
                '<input autocomplete="username"></body></html>'
            )
        }
    )
    with (
        patch.object(linkedin_mod, "_hay_memoria_sesion", return_value=True),
        patch.object(linkedin_mod, "_espera_manual", return_value=0),
    ):
        with pytest.raises(FlowError) as exc:
            LinkedInAdapter(sleep_fn=lambda _: None).enter_source(
                pagina, ficha_autenticada
            )
    assert exc.value.codigo_motivo == "criterio_no_cumplido"


def test_enter_source_criterio_no_cumplido() -> None:
    pagina = FakePage({"https://x.com": "<html><body>sin nav</body></html>"})
    ficha = FichaFuente(
        fuente_id="x",
        nombre="X",
        enlace="https://x.com",
        tipo_acceso="publico",
        criterio_exito="global-nav",
    )
    with pytest.raises(FlowError) as exc:
        LinkedInAdapter().enter_source(pagina, ficha)
    assert exc.value.codigo_motivo == "criterio_no_cumplido"


def test_enter_source_bloqueo_captcha() -> None:
    pagina = FakePage({"https://www.linkedin.com/jobs/search": _leer("challenge_linkedin.html")})
    ficha_fuente = FichaFuente(
        fuente_id="linkedin",
        nombre="LinkedIn",
        enlace="https://www.linkedin.com/jobs/search",
        tipo_acceso="publico",
        criterio_exito="global-nav",
    )
    with pytest.raises(FlowError) as exc:
        LinkedInAdapter().enter_source(pagina, ficha_fuente)
    assert exc.value.codigo_motivo == "bloqueo_plataforma"


def test_apply_filters_parsea_resultados(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    pagina = FakePage({URL_RESULTADOS: _leer("lista_linkedin.html")})
    resultado = LinkedInAdapter().apply_filters(pagina, ficha_publica, set_filtros, politicas)
    assert resultado.estado == "exito"
    assert len(resultado.ofertas_primera_pagina) == 2
    oferta = resultado.ofertas_primera_pagina[0]
    assert oferta.titulo == "Data Engineer"
    assert oferta.id_externo == "12345"
    assert oferta.enlace == "https://www.linkedin.com/jobs/view/12345"
    assert resultado.total_declarado == 2
    assert pagina.gotos[-1] == URL_RESULTADOS
    assert pagina.wait_untils[-1] == "commit"


def test_apply_filters_bloqueo(
    ficha_publica: FichaFuente, set_filtros: SetFiltros, politicas: PoliticasCaptura
) -> None:
    pagina = FakePage({URL_RESULTADOS: _leer("challenge_linkedin.html")})
    with pytest.raises(FlowError) as exc:
        LinkedInAdapter().apply_filters(pagina, ficha_publica, set_filtros, politicas)
    assert exc.value.codigo_motivo == "bloqueo_plataforma"


def test_apply_filters_parsea_resultados_ssr_2026(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    pagina = FakePage({URL_RESULTADOS: _leer("lista_linkedin_sesion.html")})
    resultado = LinkedInAdapter().apply_filters(pagina, ficha_publica, set_filtros, politicas)
    assert resultado.estado == "exito"
    assert len(resultado.ofertas_primera_pagina) == 2
    oferta = resultado.ofertas_primera_pagina[0]
    assert oferta.titulo == "Oferta Uno"
    assert oferta.id_externo == "77701"
    assert oferta.enlace == "https://www.linkedin.com/jobs/view/77701/?refId=abc"
    assert resultado.total_declarado is None


def test_apply_filters_fallback_enlace_generico(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    html = (
        "<html><body>"
        "<div role='radio' aria-label='Filtrar por En remoto' "
        "aria-checked='true'>En remoto</div>"
        "<a href='/jobs/view/99901'>Titulo Generico</a>"
        "</body></html>"
    )
    pagina = FakePage({URL_RESULTADOS: html})
    resultado = LinkedInAdapter().apply_filters(pagina, ficha_publica, set_filtros, politicas)
    assert len(resultado.ofertas_primera_pagina) == 1
    assert resultado.ofertas_primera_pagina[0].titulo == "Titulo Generico"


def test_capture_batch_lista_ssr_2026(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    pagina = FakePage({URL_RESULTADOS: _leer("lista_linkedin_sesion.html")})
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert estado.estado == "ok"
    assert len(lote.ofertas) == 2
    assert lote.ofertas[0].titulo == "Oferta Uno"
    assert lote.ofertas[0].id_externo == "77701"
    assert lote.ofertas[0].descripcion_original == ""
    assert not any("/jobs/view/" in enlace for enlace in pagina.gotos)


def test_apply_filters_filtro_tipo_no_soportado(
    ficha_publica: FichaFuente, politicas: PoliticasCaptura
) -> None:
    set_no_soportado = SetFiltros(
        fuente_id=ficha_publica.fuente_id,
        indice=0,
        filtros=[{"tipo": "salario", "valor": "50000"}],
    )
    pagina = FakePage({})
    with pytest.raises(FlowError) as exc:
        LinkedInAdapter().apply_filters(pagina, ficha_publica, set_no_soportado, politicas)
    assert exc.value.codigo_motivo == "filtros_no_aplicables"


def test_apply_filters_fecha_malformada_falla_set(
    ficha_publica: FichaFuente, politicas: PoliticasCaptura
) -> None:
    set_fecha_malformada = SetFiltros(
        fuente_id=ficha_publica.fuente_id,
        indice=0,
        filtros=[
            {"tipo": "keywords", "valor": ["Data Engineer"]},
            {"tipo": "fecha_publicacion", "valor": "24h"},
        ],
    )
    pagina = FakePage({})
    with pytest.raises(FlowError) as exc:
        LinkedInAdapter().apply_filters(
            pagina, ficha_publica, set_fecha_malformada, politicas
        )
    assert exc.value.codigo_motivo == "filtros_no_aplicables"


def test_apply_filters_fecha_formato_rn_aceptado(
    ficha_publica: FichaFuente, politicas: PoliticasCaptura
) -> None:
    set_fecha = SetFiltros(
        fuente_id=ficha_publica.fuente_id,
        indice=0,
        filtros=[
            {"tipo": "keywords", "valor": ["Data Engineer"]},
            {"tipo": "fecha_publicacion", "valor": "r86400"},
        ],
    )
    url_con_fecha = URL_RESULTADOS.replace(
        "&f_SAL=f_SA_id_225001%3A272001", "&f_TPR=r86400"
    )
    pagina = FakePage({url_con_fecha: _leer("lista_linkedin.html")})
    resultado = LinkedInAdapter().apply_filters(
        pagina, ficha_publica, set_fecha, politicas
    )
    assert resultado.estado == "exito"
    assert pagina.gotos[-1] == url_con_fecha


def test_apply_filters_fecha_r_no_canonico_falla_set(
    ficha_publica: FichaFuente, politicas: PoliticasCaptura
) -> None:
    set_fecha = SetFiltros(
        fuente_id=ficha_publica.fuente_id,
        indice=0,
        filtros=[
            {"tipo": "keywords", "valor": ["Data Engineer"]},
            {"tipo": "fecha_publicacion", "valor": "r18000"},
        ],
    )
    with pytest.raises(FlowError) as exc:
        LinkedInAdapter().apply_filters(
            FakePage({}), ficha_publica, set_fecha, politicas
        )
    assert exc.value.codigo_motivo == "filtros_no_aplicables"


def test_apply_filters_evidencia_incluye_url_y_total(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    pagina = FakePage({URL_RESULTADOS: _leer("lista_linkedin.html")})
    resultado = LinkedInAdapter().apply_filters(pagina, ficha_publica, set_filtros, politicas)
    assert resultado.evidencia_acotada == f"url: {URL_RESULTADOS} | total: 2"


def test_apply_filters_filtro_valor_vacio_se_ignora(
    ficha_publica: FichaFuente, politicas: PoliticasCaptura
) -> None:
    set_valor_vacio = SetFiltros(
        fuente_id=ficha_publica.fuente_id,
        indice=0,
        filtros=[
            {"tipo": "keywords", "valor": ""},
            {"tipo": "modalidad", "valor": "remoto"},
        ],
    )
    url_solo_modalidad = (
        "https://www.linkedin.com/jobs/search-results/?f_SAL=f_SA_id_225001%3A272001"
    )
    pagina = FakePage({url_solo_modalidad: _leer("lista_linkedin.html")})
    resultado = LinkedInAdapter().apply_filters(pagina, ficha_publica, set_valor_vacio, politicas)
    assert resultado.estado == "exito"
    assert pagina.gotos[-1] == url_solo_modalidad


def test_capture_batch_captura_dos_ofertas(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    pagina = FakePage({URL_RESULTADOS: _leer("lista_linkedin.html")})
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert estado.estado == "ok"
    assert estado.limite_alcanzado
    assert len(lote.ofertas) == 2
    assert lote.ofertas[0].titulo == "Data Engineer"
    assert lote.ofertas[0].descripcion_original == ""
    assert lote.ofertas[0].id_externo == "12345"
    assert lote.paginas_consumidas == 1


def test_capture_batch_tarjeta_sin_titulo_se_excluye(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    html = (
        "<html><body>"
        "<div componentkey='job-card-component-ref-99901'>"
        "<div componentkey='job-card-component-ref-99901'><p>sin titulo</p></div>"
        "</div>"
        "</body></html>"
    )
    pagina = FakePage({URL_RESULTADOS: html})
    adaptador = LinkedInAdapter()
    lote, estado = adaptador.capture_batch(pagina, ficha_publica, set_filtros, politicas)
    assert estado.estado == "ok"
    assert len(lote.ofertas) == 0


def test_capture_batch_recorre_paginas_hasta_ultima(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    politicas = PoliticasCaptura(
        max_paginas=10,
        max_ofertas_por_corrida=10,
        pausa_entre_lotes_segundos=0,
        estrategia_anti_bloqueo="none",
    )
    pagina = FakePage(
        {
            URL_RESULTADOS: _leer("lista_linkedin_sdui_2026.html"),
            f"{URL_RESULTADOS}&start=3": _leer("lista_linkedin_sdui_2026_pag2.html"),
            f"{URL_RESULTADOS}&start=5": "<html><body><div>sin resultados</div></body></html>",
        }
    )
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert estado.estado == "ok"
    assert len(lote.ofertas) == 5
    assert lote.paginas_consumidas == 2
    assert f"{URL_RESULTADOS}&start=3" in pagina.gotos
    assert f"{URL_RESULTADOS}&start=5" not in pagina.gotos
    assert pagina.esperas[0][2] == 5000
    assert pagina.esperas[1][2] == 5000


def test_capture_batch_no_entra_al_detalle(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    politicas = PoliticasCaptura(
        max_paginas=10,
        max_ofertas_por_corrida=10,
        pausa_entre_lotes_segundos=0,
        estrategia_anti_bloqueo="none",
    )
    pagina = FakePage(
        {
            URL_RESULTADOS: _leer("lista_linkedin_sdui_2026.html"),
            f"{URL_RESULTADOS}&start=3": _leer("lista_linkedin_sdui_2026_pag2.html"),
            f"{URL_RESULTADOS}&start=5": "<html><body><div>sin resultados</div></body></html>",
        }
    )
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert estado.estado == "ok"
    assert not any("/jobs/view/" in enlace for enlace in pagina.gotos)
    assert len(lote.ofertas) == 5


def test_capture_batch_pagina_parcial_no_corta_recorrido(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    politicas = PoliticasCaptura(
        max_paginas=10,
        max_ofertas_por_corrida=10,
        pausa_entre_lotes_segundos=0,
        estrategia_anti_bloqueo="none",
    )
    pagina = FakePage(
        {
            URL_RESULTADOS: _leer("lista_linkedin_sdui_2026.html"),
            f"{URL_RESULTADOS}&start=3": (
                "<html><body>"
                "<div componentkey='job-card-component-ref-99901'>"
                "<div componentkey='job-card-component-ref-99901'>"
                "<span aria-hidden='true'>Oferta Unica</span>"
                "</div></div>"
                "<button aria-label='Siguiente'>Siguiente</button>"
                "</body></html>"
            ),
            f"{URL_RESULTADOS}&start=4": "<html><body><div>sin resultados</div></body></html>",
        }
    )
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert len(lote.ofertas) == 4
    assert lote.paginas_consumidas == 2


def test_capture_batch_respeta_max_paginas(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    politicas = PoliticasCaptura(
        max_paginas=1,
        max_ofertas_por_corrida=10,
        pausa_entre_lotes_segundos=0,
        estrategia_anti_bloqueo="none",
    )
    pagina = FakePage({URL_RESULTADOS: _leer("lista_linkedin_sdui_2026.html")})
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert estado.estado == "ok"
    assert len(lote.ofertas) == 3
    assert lote.paginas_consumidas == 1


def test_capture_batch_respeta_max_ofertas(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    politica = politicas.model_copy(update={"max_ofertas_por_corrida": 4})
    pagina = FakePage(
        {
            URL_RESULTADOS: _leer("lista_linkedin_sdui_2026.html"),
            f"{URL_RESULTADOS}&start=3": _leer("lista_linkedin_sdui_2026_pag2.html"),
        }
    )
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politica
    )
    assert len(lote.ofertas) == 4
    assert lote.paginas_consumidas == 2


def test_capture_batch_dedup_entre_paginas(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    politicas = PoliticasCaptura(
        max_paginas=10,
        max_ofertas_por_corrida=10,
        pausa_entre_lotes_segundos=0,
        estrategia_anti_bloqueo="none",
    )
    pagina = FakePage(
        {
            URL_RESULTADOS: _leer("lista_linkedin_sdui_2026.html"),
            f"{URL_RESULTADOS}&start=3": (
                "<html><body>"
                "<div componentkey='job-card-component-ref-4377518497'>"
                "<div componentkey='job-card-component-ref-4377518497'>"
                "<span aria-hidden='true'>Programador Staff duplicada</span>"
                "</div></div>"
                "</body></html>"
            ),
        }
    )
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert len(lote.ofertas) == 3
    assert estado.estado == "ok"


def test_capture_batch_aplica_pausa_entre_paginas(
    ficha_publica: FichaFuente, set_filtros: SetFiltros
) -> None:
    llamadas: list[float] = []

    def dormir(segundos: float) -> None:
        llamadas.append(segundos)

    politicas = PoliticasCaptura(
        max_paginas=3,
        max_ofertas_por_corrida=10,
        pausa_entre_lotes_segundos=2,
        estrategia_anti_bloqueo="retraso_fijo",
    )
    pagina = FakePage(
        {
            URL_RESULTADOS: _leer("lista_linkedin_sdui_2026.html"),
            f"{URL_RESULTADOS}&start=3": _leer("lista_linkedin_sdui_2026_pag2.html"),
        }
    )
    adaptador = LinkedInAdapter(sleep_fn=dormir)
    adaptador.capture_batch(pagina, ficha_publica, set_filtros, politicas)
    assert llamadas and llamadas[0] == 2.0


def test_capture_batch_reutiliza_pagina_1(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    politicas = PoliticasCaptura(
        max_paginas=10,
        max_ofertas_por_corrida=10,
        pausa_entre_lotes_segundos=0,
        estrategia_anti_bloqueo="none",
    )
    pagina = FakePage(
        {f"{URL_RESULTADOS}&start=3": "<html><body><div>sin resultados</div></body></html>"}
    )
    pagina.url = URL_RESULTADOS
    pagina._actual = _leer("lista_linkedin_sdui_2026.html")
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert estado.estado == "ok"
    assert len(lote.ofertas) == 3
    assert lote.paginas_consumidas == 1
    assert pagina.gotos == [f"{URL_RESULTADOS}&start=3"]


def test_capture_batch_pagina_vacia_con_boton_corta_recorrido(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    politicas = PoliticasCaptura(
        max_paginas=10,
        max_ofertas_por_corrida=10,
        pausa_entre_lotes_segundos=0,
        estrategia_anti_bloqueo="none",
    )
    pagina = FakePage(
        {
            URL_RESULTADOS: _leer("lista_linkedin_sdui_2026.html"),
            f"{URL_RESULTADOS}&start=3": "<html><body><div>sin resultados</div></body></html>",
        }
    )
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert len(lote.ofertas) == 3
    assert lote.paginas_consumidas == 1
    assert f"{URL_RESULTADOS}&start=3" in pagina.gotos


def test_capture_batch_aplica_tope_espera_paginas_sucesivas(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    politicas = PoliticasCaptura(
        max_paginas=10,
        max_ofertas_por_corrida=10,
        pausa_entre_lotes_segundos=0,
        estrategia_anti_bloqueo="none",
    )
    ficha = ficha_publica.model_copy(update={"timeout_segundos": 30})
    pagina = FakePage(
        {
            URL_RESULTADOS: _leer("lista_linkedin_sdui_2026.html"),
            f"{URL_RESULTADOS}&start=3": _leer("lista_linkedin_sdui_2026_pag2.html"),
        }
    )
    LinkedInAdapter().capture_batch(pagina, ficha, set_filtros, politicas)
    assert pagina.esperas[0][2] == 30000
    assert pagina.esperas[1][2] == 10000


def test_close_session_cierra_pagina() -> None:
    pagina = FakePage({})
    LinkedInAdapter().close_session(pagina)
    assert pagina.cerrada


def test_capture_batch_bloqueo_detiene_batch(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    pagina = FakePage({URL_RESULTADOS: _leer("challenge_linkedin.html")})
    with pytest.raises(FlowError) as exc:
        LinkedInAdapter().capture_batch(pagina, ficha_publica, set_filtros, politicas)
    assert exc.value.codigo_motivo == "bloqueo_plataforma"


def test_revisar_bloqueo_ignora_challenge_en_scripts() -> None:
    html = (
        "<html><head><script>var mod = 'challenge-response';</script>"
        "<style>.challenge{color:red}</style></head>"
        "<body><nav id='global-nav'>ok</nav></body></html>"
    )
    LinkedInAdapter()._revisar_bloqueo_html(html)


def test_revisar_bloqueo_detecta_captcha_visible() -> None:
    html = "<html><body><p>Complete the captcha to continue.</p></body></html>"
    with pytest.raises(FlowError) as exc:
        LinkedInAdapter()._revisar_bloqueo_html(html)
    assert exc.value.codigo_motivo == "bloqueo_plataforma"


def test_revisar_bloqueo_ignora_authwall_en_scripts() -> None:
    html = "<html><head><script>const authwall = true;</script></head><body>ok</body></html>"
    LinkedInAdapter()._revisar_bloqueo_html(html)


def test_revisar_bloqueo_detecta_authwall_visible() -> None:
    html = "<html><body><div class='authwall-content'>unete</div></body></html>"
    with pytest.raises(FlowError) as exc:
        LinkedInAdapter()._revisar_bloqueo_html(html)
    assert exc.value.codigo_motivo == "sesion_expirada"


class FakePageRenderizadoTardio(FakePage):
    """Simula el SERP 2026: las tarjetas aparecen al esperar el selector."""

    def __init__(self, cascaron: str, renderizado: str) -> None:
        super().__init__({})
        self._cascaron = cascaron
        self._renderizado = renderizado
        self._actual = cascaron
        self.esperas: list[tuple[str, str | None, int | None]] = []

    def goto(self, enlace: str, wait_until: str | None = None) -> None:
        self.gotos.append(enlace)
        self.url = enlace
        self._actual = self.por_url.get(enlace, self._cascaron)

    def wait_for_selector(
        self,
        selector: str,
        timeout: int | None = None,
        state: str | None = None,
    ) -> None:
        self.esperas.append((selector, state, timeout))
        self._actual = self._renderizado


def test_apply_filters_espera_renderizado_tardio(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    cascaron = "<html><body><p>cargando resultados...</p></body></html>"
    pagina = FakePageRenderizadoTardio(cascaron, _leer("lista_linkedin.html"))
    resultado = LinkedInAdapter().apply_filters(pagina, ficha_publica, set_filtros, politicas)
    assert resultado.estado == "exito"
    assert len(resultado.ofertas_primera_pagina) == 2
    assert pagina.esperas and pagina.esperas[0][0].startswith("div[componentkey^='job-card")


def test_apply_filters_espera_renderizado_tardio_ssr_2026(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    cascaron = "<html><body><div id='root'></div></body></html>"
    pagina = FakePageRenderizadoTardio(cascaron, _leer("lista_linkedin_sesion.html"))
    resultado = LinkedInAdapter().apply_filters(pagina, ficha_publica, set_filtros, politicas)
    assert resultado.estado == "exito"
    assert len(resultado.ofertas_primera_pagina) == 2


def test_apply_filters_parsea_resultados_sdui_2026(
    ficha_publica: FichaFuente,
    set_filtros_sin_modalidad: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    pagina = FakePage({URL_SIN_MODALIDAD: _leer("lista_linkedin_sdui_2026.html")})
    resultado = LinkedInAdapter().apply_filters(
        pagina, ficha_publica, set_filtros_sin_modalidad, politicas
    )
    assert resultado.estado == "exito"
    ofertas = resultado.ofertas_primera_pagina
    assert len(ofertas) == 3
    assert ofertas[0].titulo == "Programador Staff - Data Engineering"
    assert ofertas[0].id_externo == "4377518497"
    assert ofertas[0].enlace == "https://www.linkedin.com/jobs/view/4377518497"
    assert ofertas[0].observaciones == "Publicado hace 9 horas"
    assert ofertas[0].fecha_publicacion is not None
    # Traspaso 2026-08-25: la tarjeta provee ubicación y modalidad.
    assert ofertas[0].ubicacion == "Bogotá"
    assert ofertas[0].modalidad == "N/R"
    assert ofertas[1].titulo == "Solutions Data and Analytics Specialist"
    assert ofertas[1].id_externo == "4454411536"
    assert ofertas[1].ubicacion == "Bogotá"
    assert ofertas[1].modalidad == "hibrido"
    assert ofertas[2].id_externo == "4455353156"
    assert ofertas[2].ubicacion == "Colombia"
    assert ofertas[2].modalidad == "remoto"
    # D41: la tarjeta provee también la empresa cruda (caracteres intactos).
    assert ofertas[0].empresa == "Inetum"
    assert ofertas[1].empresa == "Emergent Cold LatAm"
    assert ofertas[2].empresa == "CI&T"
    assert resultado.total_declarado == 89


def test_apply_filters_sdui_ignora_apply_y_anchors_duplicados(
    ficha_publica: FichaFuente,
    set_filtros_sin_modalidad: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    pagina = FakePage({URL_SIN_MODALIDAD: _leer("lista_linkedin_sdui_2026.html")})
    resultado = LinkedInAdapter().apply_filters(
        pagina, ficha_publica, set_filtros_sin_modalidad, politicas
    )
    assert len(resultado.ofertas_primera_pagina) == 3


def test_apply_filters_y_capture_reutilizan_la_misma_carga(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    pagina = FakePage({URL_RESULTADOS: _leer("lista_linkedin.html")})
    adaptador = LinkedInAdapter()
    adaptador.apply_filters(pagina, ficha_publica, set_filtros, politicas)
    lote, estado = adaptador.capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert estado.estado == "ok"
    assert len(lote.ofertas) == 2
    assert pagina.gotos == [URL_RESULTADOS]


def test_capture_batch_espera_renderizado_tardio(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    cascaron = "<html><body><p>cargando...</p></body></html>"
    pagina = FakePageRenderizadoTardio(cascaron, _leer("lista_linkedin.html"))
    pagina.por_url = {
        "https://www.linkedin.com/jobs/view/12345": _leer("detalle_linkedin.html"),
        "https://www.linkedin.com/jobs/view/12346": _leer("detalle_linkedin.html"),
    }
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert estado.estado == "ok"
    assert len(lote.ofertas) == 2
    assert pagina.esperas


def test_capture_batch_espera_por_cada_pagina(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    pagina = FakePageRenderizadoTardio(
        "<html><body><p>cargando...</p></body></html>", _leer("lista_linkedin.html")
    )
    pagina.por_url = {
        "https://www.linkedin.com/jobs/view/12345": _leer("detalle_linkedin.html"),
        "https://www.linkedin.com/jobs/view/12346": _leer("detalle_linkedin.html"),
    }
    LinkedInAdapter().capture_batch(pagina, ficha_publica, set_filtros, politicas)
    assert len(pagina.esperas) >= 1


def test_esperar_resultados_usa_timeout_de_ficha() -> None:
    pagina = FakePage({})
    adaptador = LinkedInAdapter()
    ficha = FichaFuente(
        fuente_id="linkedin",
        nombre="LinkedIn",
        enlace="https://www.linkedin.com/jobs/search",
        tipo_acceso="publico",
        criterio_exito="global-nav",
        timeout_segundos=5,
    )
    adaptador._esperar_resultados(pagina, ficha.timeout_segundos)
    assert pagina.esperas == [(
        "div[componentkey^='job-card-component-ref-']",
        "attached",
        5000,
    )]


def test_esperar_resultados_tolerante_a_timeout() -> None:
    class PageSinTarjetas(FakePage):
        def wait_for_selector(
            self,
            selector: str,
            timeout: int | None = None,
            state: str | None = None,
        ) -> None:
            raise TimeoutError("no cards")

    pagina = PageSinTarjetas({})
    LinkedInAdapter()._esperar_resultados(pagina, 5)
    assert not pagina.cerrada


CHIPS_ACTIVOS = (
    "<div role='radio' aria-label='Filtrar por En remoto' aria-checked='true'>"
    "En remoto</div>"
    "<div role='button' aria-expanded='false' "
    "componentkey='SearchResults_filter_pill_"
    "JobSearchFacetSuggestionType_TIME_POSTED'>"
    "<input id='r1' type='checkbox' checked='checked' />"
    "<label for='r1'>Últimas 24 horas</label>"
    "</div>"
)

HTML_SIN_CHIPS = (
    "<html><body>"
    "<div componentkey='job-card-component-ref-99901'>"
    "<div componentkey='job-card-component-ref-99901'>"
    "<span aria-hidden='true'>Oferta Sin Filtros</span>"
    "</div></div>"
    "</body></html>"
)


class FakePageFallbackUI(FakePage):
    """Simula el clic de fallback: tras el primer clic el DOM aplica chips."""

    def __init__(self, por_url: dict[str, str]) -> None:
        super().__init__(por_url)
        self._html_tras_clic = (
            "<html><body>"
            f"{CHIPS_ACTIVOS}"
            "<div componentkey='job-card-component-ref-99901'>"
            "<div componentkey='job-card-component-ref-99901'>"
            "<span aria-hidden='true'>Oferta Con Filtros</span>"
            "</div></div>"
            "</body></html>"
        )

    def click(self, selector: str, timeout: int | None = None) -> None:
        self.clics.append(selector)
        self._actual = self._html_tras_clic
        self.url = (
            "https://www.linkedin.com/jobs/search-results/?currentJobId=1"
            "&keywords=Data+Engineer&origin=JOB_SEARCH_PAGE_JOB_FILTER"
            "&referralSearchId=x&f_TPR=r86400&f_SAL=f_SA_id_225001%3A272001"
        )


def test_apply_filters_verifica_chips_sin_clics(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    pagina = FakePage({URL_RESULTADOS: _leer("lista_linkedin.html")})
    resultado = LinkedInAdapter().apply_filters(pagina, ficha_publica, set_filtros, politicas)
    assert resultado.estado == "exito"
    assert pagina.clics == []


def test_apply_filters_fallback_clic_aplica_filtros(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    pagina = FakePageFallbackUI({URL_RESULTADOS: HTML_SIN_CHIPS})
    resultado = LinkedInAdapter().apply_filters(pagina, ficha_publica, set_filtros, politicas)
    assert resultado.estado == "exito"
    assert len(resultado.ofertas_primera_pagina) == 1
    assert resultado.evidencia_acotada.startswith(
        "url: https://www.linkedin.com/jobs/search-results/?currentJobId=1"
    )
    assert "div[role='radio'][aria-label='Filtrar por En remoto']" in pagina.clics


def test_apply_filters_fallback_clic_fecha_aplica_filtros(
    ficha_publica: FichaFuente,
    politicas: PoliticasCaptura,
) -> None:
    set_fecha = SetFiltros(
        fuente_id=ficha_publica.fuente_id,
        indice=0,
        filtros=[{"tipo": "fecha_publicacion", "valor": "r86400"}],
    )
    url_fecha = "https://www.linkedin.com/jobs/search-results/?f_TPR=r86400"
    pagina = FakePageFallbackUI({url_fecha: HTML_SIN_CHIPS})
    resultado = LinkedInAdapter().apply_filters(
        pagina, ficha_publica, set_fecha, politicas
    )
    assert resultado.estado == "exito"
    assert pagina.clics == [
        "div[role='button'][aria-expanded='false'][componentkey^="
        "'SearchResults_filter_pill_JobSearchFacetSuggestionType_"
        "TIME_POSTED']",
        "div[role='radio'][aria-label='Últimas 24 horas']",
        "button:text-is('Mostrar resultados'), a:text-is('Mostrar resultados')",
    ]


def test_apply_filters_fallback_fecha_no_aplica_falla_set(
    ficha_publica: FichaFuente,
    politicas: PoliticasCaptura,
) -> None:
    set_fecha = SetFiltros(
        fuente_id=ficha_publica.fuente_id,
        indice=0,
        filtros=[{"tipo": "fecha_publicacion", "valor": "r86400"}],
    )
    url_fecha = "https://www.linkedin.com/jobs/search-results/?f_TPR=r86400"
    pagina = FakePage({url_fecha: HTML_SIN_CHIPS})
    with pytest.raises(FlowError) as exc:
        LinkedInAdapter().apply_filters(pagina, ficha_publica, set_fecha, politicas)
    assert exc.value.codigo_motivo == "filtros_no_aplicables"
    assert pagina.clics == [
        "div[role='button'][aria-expanded='false'][componentkey^="
        "'SearchResults_filter_pill_JobSearchFacetSuggestionType_"
        "TIME_POSTED']",
        "div[role='radio'][aria-label='Últimas 24 horas']",
        "button:text-is('Mostrar resultados'), a:text-is('Mostrar resultados')",
    ]


def test_apply_filters_verifica_chips_fecha_sin_clics(
    ficha_publica: FichaFuente,
    politicas: PoliticasCaptura,
) -> None:
    set_fecha = SetFiltros(
        fuente_id=ficha_publica.fuente_id,
        indice=0,
        filtros=[{"tipo": "fecha_publicacion", "valor": "r86400"}],
    )
    url_fecha = "https://www.linkedin.com/jobs/search-results/?f_TPR=r86400"
    pagina = FakePage({url_fecha: _leer("lista_linkedin.html")})
    resultado = LinkedInAdapter().apply_filters(
        pagina, ficha_publica, set_fecha, politicas
    )
    assert resultado.estado == "exito"
    assert pagina.clics == []


def test_apply_filters_fallback_no_aplica_falla_set(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
    politicas: PoliticasCaptura,
) -> None:
    pagina = FakePage({URL_RESULTADOS: HTML_SIN_CHIPS})
    with pytest.raises(FlowError) as exc:
        LinkedInAdapter().apply_filters(pagina, ficha_publica, set_filtros, politicas)
    assert exc.value.codigo_motivo == "filtros_no_aplicables"
    assert pagina.clics == ["div[role='radio'][aria-label='Filtrar por En remoto']"]


def test_apply_filters_modalidad_no_remota_falla_set(
    ficha_publica: FichaFuente, politicas: PoliticasCaptura
) -> None:
    set_presencial = SetFiltros(
        fuente_id=ficha_publica.fuente_id,
        indice=0,
        filtros=[{"tipo": "modalidad", "valor": "presencial"}],
    )
    pagina = FakePage({})
    with pytest.raises(FlowError) as exc:
        LinkedInAdapter().apply_filters(pagina, ficha_publica, set_presencial, politicas)
    assert exc.value.codigo_motivo == "filtros_no_aplicables"


def test_apply_filters_total_nuevo_markup_par(
    ficha_publica: FichaFuente, politicas: PoliticasCaptura
) -> None:
    set_solo_keywords = SetFiltros(
        fuente_id=ficha_publica.fuente_id,
        indice=0,
        filtros=[{"tipo": "keywords", "valor": ["Data Engineer"]}],
    )
    url = "https://www.linkedin.com/jobs/search-results/?keywords=Data+Engineer"
    html = (
        "<html><body>"
        "<div componentkey='job-card-component-ref-99901'>"
        "<div componentkey='job-card-component-ref-99901'>"
        "<span aria-hidden='true'>Oferta</span>"
        "</div></div>"
        "<p>67 resultados</p>"
        "</body></html>"
    )
    pagina = FakePage({url: html})
    resultado = LinkedInAdapter().apply_filters(pagina, ficha_publica, set_solo_keywords, politicas)
    assert resultado.total_declarado == 67
    assert resultado.evidencia_acotada == f"url: {url} | total: 67"


def test_capture_batch_pagina_partir_de_url_canonica(
    ficha_publica: FichaFuente, set_filtros: SetFiltros
) -> None:
    politicas = PoliticasCaptura(
        max_paginas=10,
        max_ofertas_por_corrida=10,
        pausa_entre_lotes_segundos=0,
        estrategia_anti_bloqueo="none",
    )
    url_canonica = (
        "https://www.linkedin.com/jobs/search-results/?currentJobId=123"
        "&keywords=Data+Engineer&f_TPR=r86400&f_SAL=f_SA_id_225001%3A272001"
    )
    pagina = FakePage(
        {f"{url_canonica}&start=3": "<html><body><div>sin resultados</div></body></html>"}
    )
    pagina.url = url_canonica
    pagina._actual = _leer("lista_linkedin_sdui_2026.html")
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert estado.estado == "ok"
    assert len(lote.ofertas) == 3
    assert pagina.gotos == [f"{url_canonica}&start=3"]


def test_fecha_relativa_a_datetime_por_unidad() -> None:
    from datetime import datetime, timedelta

    ahora = datetime.now()
    casos = {
        "Publicado hace 5 minutos": timedelta(minutes=5),
        "Publicado hace 1 minuto": timedelta(minutes=1),
        "Publicado hace 9 horas": timedelta(hours=9),
        "Publicado hace 1 hora": timedelta(hours=1),
        "Publicado hace 2 días": timedelta(days=2),
        "Publicado hace 1 día": timedelta(days=1),
        "Publicado hace 3 semanas": timedelta(weeks=3),
        "Publicado hace 2 meses": timedelta(days=60),
    }
    for texto, delta in casos.items():
        resultado = _fecha_relativa_a_datetime(texto)
        assert resultado is not None
        assert abs((ahora - resultado) - delta) < timedelta(seconds=5), texto
    assert _fecha_relativa_a_datetime("") is None
    assert _fecha_relativa_a_datetime("Publicado hace ayer") is None
    assert _fecha_relativa_a_datetime("Publicado hace 999999999 horas") is None


def test_capture_batch_sdui_extrae_fecha_y_observaciones(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    politicas = PoliticasCaptura(
        max_paginas=10,
        max_ofertas_por_corrida=10,
        pausa_entre_lotes_segundos=0,
        estrategia_anti_bloqueo="none",
    )
    pagina = FakePage(
        {
            URL_RESULTADOS: _leer("lista_linkedin_sdui_2026.html"),
            f"{URL_RESULTADOS}&start=3": _leer("lista_linkedin_sdui_2026_pag2.html"),
        }
    )
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert estado.estado == "ok"
    assert len(lote.ofertas) == 5
    ofertas = {o.id_externo: o for o in lote.ofertas}
    assert ofertas["4377518497"].observaciones == "Publicado hace 9 horas"
    assert ofertas["4377518497"].fecha_publicacion is not None
    assert ofertas["4454426405"].fecha_publicacion is not None


def test_total_declarado_ignora_scripts_y_styles(
    ficha_publica: FichaFuente,
    politicas: PoliticasCaptura,
) -> None:
    set_solo_keywords = SetFiltros(
        fuente_id="linkedin",
        indice=0,
        filtros=[{"tipo": "keywords", "valor": ["Data Engineer"]}],
    )
    url = "https://www.linkedin.com/jobs/search-results/?keywords=Data+Engineer"
    html = (
        "<html><body>"
        "<script>window.__initialData__ = 999999;</script>"
        "<style>div { content: '500 resultados'; }</style>"
        "<!-- 700 resultados -->"
        "<p>67 resultados</p>"
        "<div componentkey='job-card-component-ref-99901'>"
        "<div componentkey='job-card-component-ref-99901'>"
        "<span aria-hidden='true'>Oferta</span>"
        "</div></div>"
        "</body></html>"
    )
    pagina = FakePage({url: html})
    resultado = LinkedInAdapter().apply_filters(
        pagina, ficha_publica, set_solo_keywords, politicas
    )
    assert resultado.total_declarado == 67


def test_capture_batch_tarjeta_sin_campos_no_falla(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    politicas = PoliticasCaptura(
        max_paginas=1,
        max_ofertas_por_corrida=10,
        pausa_entre_lotes_segundos=0,
        estrategia_anti_bloqueo="none",
    )
    html = (
        "<html><body>"
        "<div componentkey='job-card-component-ref-99901'>"
        "<div componentkey='job-card-component-ref-99901'>"
        "<span aria-hidden='true'>Oferta</span>"
        "</div></div>"
        "</body></html>"
    )
    pagina = FakePage({URL_RESULTADOS: html})
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert estado.estado == "ok"
    assert len(lote.ofertas) == 1
    oferta = lote.ofertas[0]
    assert oferta.fecha_publicacion is None
    assert oferta.observaciones == ""


def test_capture_batch_variante_clasica_solo_titulos(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    politicas = PoliticasCaptura(
        max_paginas=1,
        max_ofertas_por_corrida=10,
        pausa_entre_lotes_segundos=0,
        estrategia_anti_bloqueo="none",
    )
    pagina = FakePage({URL_RESULTADOS: _leer("lista_linkedin.html")})
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, politicas
    )
    assert estado.estado == "ok"
    assert len(lote.ofertas) == 2
    oferta = lote.ofertas[0]
    assert oferta.titulo == "Data Engineer"
    assert oferta.fecha_publicacion is None
    assert oferta.observaciones == ""
    # Variante clásica: ubicación por selector propio (best-effort).
    assert oferta.ubicacion == "Madrid"
    assert oferta.modalidad == "N/R"
    # "Remoto" como texto completo: sin ubicación útil ('N/R'), sí modalidad.
    assert lote.ofertas[1].ubicacion == "N/R"
    assert lote.ofertas[1].modalidad == "remoto"


# ---------------------------------------------- tarjeta SDUi: ubicación/modality


def _tarjeta_div(
    p_segmentos: list[str], titulo: str = "Ingeniero de Datos"
) -> Any:
    """Construye un div SDUi con el markup mínimo real (componentkey +
    span[aria-hidden] + <p> en el orden observado, Exp 9).

    `titulo` debe coincidir con el primer segmento para simular el bloque
    de título que la clasificación descarta."""
    parrafos = "".join(f"<p>{s}</p>" for s in p_segmentos)
    html = (
        '<div componentkey="job-card-component-ref-123">'
        f"<span aria-hidden='true'>{titulo}</span>{parrafos}</div>"
    )
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "lxml").select_one(
        "div[componentkey^='job-card-component-ref-']"
    )


def test_tarjeta_sdui_ubicacion_con_sufijo_remoto() -> None:
    div = _tarjeta_div(
        [
            "Ingeniero de Datos|Ingeniero de Datos",
            "Acme Corp",
            "Colombia (En remoto)",
            "·",
            "Publicado hace 2 horas|hace 2 horas",
        ]
    )
    tarjeta = _extraer_tarjeta_sdui(div)
    assert tarjeta is not None
    assert tarjeta.ubicacion == "Colombia"
    assert tarjeta.modalidad == "remoto"


def test_tarjeta_sdui_ubicacion_con_sufijo_hibrido_y_ruido() -> None:
    div = _tarjeta_div(
        [
            "Analista|Analista (Empleo verificado)|Analista",
            "Beta Ltda",
            "Bogotá (Híbrido)",
            "Visto",
            "Adelántate a solicitar el empleo",
            "Solicitar",
            "Evaluando solicitudes de forma activa",
            "Publicado hace 30 minutos|hace 30 minutos",
        ],
        titulo="Analista",
    )
    tarjeta = _extraer_tarjeta_sdui(div)
    assert tarjeta is not None
    assert tarjeta.ubicacion == "Bogotá"
    assert tarjeta.modalidad == "hibrido"


def test_tarjeta_sdui_ubicacion_sin_modalidad_da_nr() -> None:
    div = _tarjeta_div(
        ["Ingeniero de Datos", "Gamma SA", "Medellín, Antioquia", "Visto",
         "·", "Publicado hace 1 hora|hace 1 hora"]
    )
    tarjeta = _extraer_tarjeta_sdui(div)
    assert tarjeta is not None
    assert tarjeta.ubicacion == "Medellín, Antioquia"
    assert tarjeta.modalidad == "N/R"


def test_tarjeta_sdui_sin_segundo_candidato_devuelve_vacio_nr() -> None:
    div = _tarjeta_div(["Ingeniero de Datos", "Delta Corp", "Publicado hace 3 días"])
    tarjeta = _extraer_tarjeta_sdui(div)
    assert tarjeta is not None
    assert tarjeta.empresa == "Delta Corp"
    assert tarjeta.ubicacion == ""
    assert tarjeta.modalidad == "N/R"


def test_tarjeta_sdui_empresa_conserva_caracteres_d41() -> None:
    div = _tarjeta_div(
        ["Ingeniero de Datos", "CI&T S.A. (Grupo)", "Bogotá", "·",
         "Publicado hace 5 horas|hace 5 horas"]
    )
    tarjeta = _extraer_tarjeta_sdui(div)
    assert tarjeta is not None
    assert tarjeta.empresa == "CI&T S.A. (Grupo)"
    assert tarjeta.ubicacion == "Bogotá"


def test_tarjeta_sdui_sin_candidatos_no_da_empresa() -> None:
    div = _tarjeta_div(["Ingeniero de Datos", "Visto", "·",
                        "Publicado hace 1 hora|hace 1 hora"])
    tarjeta = _extraer_tarjeta_sdui(div)
    assert tarjeta is not None
    assert tarjeta.empresa == ""
    assert tarjeta.ubicacion == ""
    assert tarjeta.modalidad == "N/R"


def test_tarjeta_sdui_segmento_solo_modalidad_no_es_ubicacion() -> None:
    div = _tarjeta_div(
        ["Ingeniero de Datos", "Epsilon", "Remoto", "·",
         "Publicado hace 4 horas|hace 4 horas"]
    )
    tarjeta = _extraer_tarjeta_sdui(div)
    assert tarjeta is not None
    assert tarjeta.ubicacion == ""
    assert tarjeta.modalidad == "remoto"


@pytest.mark.parametrize(
    "titulo",
    [
        "Backend Engineer, AI | Growth",
        "Senior | Platform Engineer",
        "Data | Ops | Lead",
    ],
)
def test_tarjeta_sdui_titulo_con_pipe_embebido(titulo: str) -> None:
    """COR-0003 (oferta 4455899476): un '|' dentro del título truncaba el
    primer segmento del bloque de título y este no se descartaba — la
    empresa terminaba leída como ubicación."""
    div = _tarjeta_div(
        [titulo, "Acme Corp", "Medellín (Híbrido)", "Visto", "Publicado hace 2 horas|hace 2 horas"],
        titulo=titulo,
    )
    tarjeta = _extraer_tarjeta_sdui(div)
    assert tarjeta is not None
    assert tarjeta.ubicacion == "Medellín"
    assert tarjeta.modalidad == "hibrido"


def test_tarjeta_sdui_empresa_segmento_de_titulo_no_se_descarta() -> None:
    """Una empresa de una sola parte cuyo nombre coincide con un segmento
    del título NO se descarta por la vía multipartidista del filtro."""
    div = _tarjeta_div(
        ["Marketing | Growth", "Growth", "Bogotá"],
        titulo="Marketing | Growth",
    )
    tarjeta = _extraer_tarjeta_sdui(div)
    assert tarjeta is not None
    assert tarjeta.ubicacion == "Bogotá"
    assert tarjeta.modalidad == "N/R"


def test_tarjeta_sdui_real_deel_2026_titulo_con_pipe() -> None:
    """Tarjeta REAL capturada (búsqueda focalizada, oferta Deel): markup
    completo con el título 'Backend Engineer, AI | Growth' embebido."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_leer("lista_linkedin_sdui_deel_2026.html"), "lxml")
    div = soup.select_one("div[componentkey*='4455899476']")
    assert div is not None
    tarjeta = _extraer_tarjeta_sdui(div)
    assert tarjeta is not None
    assert tarjeta.titulo == "Backend Engineer, AI | Growth"
    assert tarjeta.enlace.endswith("/4455899476")
    assert tarjeta.ubicacion == "Colombia"
    assert tarjeta.modalidad == "remoto"


# --- D60 (2026-10-22): geografia por codigo oficial de region ---------- #


def test_construir_url_geoid_parametro_oficial() -> None:
    """El codigo de region viaja como `geoId` en la URL construida."""
    set_geo = SetFiltros(
        fuente_id="linkedin",
        indice=0,
        filtros=[
            {"tipo": "keywords", "valor": ["Data Engineer"]},
            {"tipo": "geoid", "valor": "100876405"},
        ],
    )
    enlace = LinkedInAdapter()._construir_url_busqueda(
        "https://www.linkedin.com/jobs/search", set_geo
    )
    assert enlace == (
        "https://www.linkedin.com/jobs/search"
        "?keywords=Data+Engineer&geoId=100876405"
    )


def test_apply_filters_geoid_captura_con_codigo_en_url(
    ficha_publica: FichaFuente, politicas: PoliticasCaptura
) -> None:
    """Set con geoid navega al listado con el codigo y no exige chips."""
    set_geo = SetFiltros(
        fuente_id="linkedin",
        indice=0,
        filtros=[
            {"tipo": "keywords", "valor": ["Data Engineer"]},
            {"tipo": "geoid", "valor": "100876405"},
        ],
    )
    url = (
        "https://www.linkedin.com/jobs/search-results/"
        "?keywords=Data+Engineer&geoId=100876405"
    )
    html = (
        "<html><body>"
        "<p>67 resultados</p>"
        "<div componentkey='job-card-component-ref-99901'>"
        "<div componentkey='job-card-component-ref-99901'>"
        "<span aria-hidden='true'>Oferta</span>"
        "</div></div>"
        "</body></html>"
    )
    pagina = FakePage({url: html})
    resultado = LinkedInAdapter().apply_filters(
        pagina, ficha_publica, set_geo, politicas
    )
    assert pagina.gotos == [url]
    assert resultado.total_declarado == 67
    assert len(resultado.ofertas_primera_pagina) == 1


def test_apply_filters_geoid_formato_invalido_falla_set(
    ficha_publica: FichaFuente,
    politicas: PoliticasCaptura,
) -> None:
    """Un codigo mal escrito aborta avisando; jamas captura silenciosa."""
    for valor in ("Colombia", "12345", "100876405x", "12 045"):
        set_geo = SetFiltros(
            fuente_id="linkedin",
            indice=0,
            filtros=[{"tipo": "geoid", "valor": valor}],
        )
        with pytest.raises(FlowError) as exc:
            LinkedInAdapter().apply_filters(
                FakePage({}), ficha_publica, set_geo, politicas
            )
        assert exc.value.codigo_motivo == "filtros_no_aplicables"


def test_apply_filters_geoid_y_texto_ubicacion_no_se_combinan(
    ficha_publica: FichaFuente,
    politicas: PoliticasCaptura,
) -> None:
    """geoid + texto de ubicacion = error explicito de configuracion."""
    set_mixto = SetFiltros(
        fuente_id="linkedin",
        indice=0,
        filtros=[
            {"tipo": "geoid", "valor": "100876405"},
            {"tipo": "ubicacion", "valor": "Colombia"},
        ],
    )
    with pytest.raises(FlowError) as exc:
        LinkedInAdapter().apply_filters(
            FakePage({}), ficha_publica, set_mixto, politicas
        )
    assert exc.value.codigo_motivo == "filtros_no_aplicables"


def test_apply_filters_geoid_con_texto_ubicacion_vacio_se_permite(
    ficha_publica: FichaFuente, politicas: PoliticasCaptura
) -> None:
    """Un valor vacio de ubicacion se ignora y el set con geoid es valido."""
    set_geo = SetFiltros(
        fuente_id="linkedin",
        indice=0,
        filtros=[
            {"tipo": "geoid", "valor": "91000011"},
            {"tipo": "ubicacion", "valor": ""},
        ],
    )
    url = "https://www.linkedin.com/jobs/search-results/?geoId=91000011"
    html = "<html><body><p>12 resultados</p></body></html>"
    pagina = FakePage({url: html})
    resultado = LinkedInAdapter().apply_filters(
        pagina, ficha_publica, set_geo, politicas
    )
    assert pagina.gotos == [url]
    assert resultado.total_declarado == 12


def test_apply_filters_geoid_con_remoto_y_fecha_componen_url(
    ficha_publica: FichaFuente, politicas: PoliticasCaptura
) -> None:
    """Barrida 4: codigo de region + modalidad remoto + ventana de fecha."""
    set_mundo = SetFiltros(
        fuente_id="linkedin",
        indice=0,
        filtros=[
            {"tipo": "keywords", "valor": ["Data Engineer"]},
            {"tipo": "geoid", "valor": "100876405"},
            {"tipo": "modalidad", "valor": "remoto"},
            {"tipo": "fecha_publicacion", "valor": "r86400"},
        ],
    )
    url = (
        "https://www.linkedin.com/jobs/search-results/"
        "?keywords=Data+Engineer&geoId=100876405"
        "&f_SAL=f_SA_id_225001%3A272001&f_TPR=r86400"
    )
    html = (
        "<html><body>" f"{CHIPS_ACTIVOS}" "<p>31 resultados</p>" "</body></html>"
    )
    pagina = FakePage({url: html})
    resultado = LinkedInAdapter().apply_filters(
        pagina, ficha_publica, set_mundo, politicas
    )
    assert pagina.gotos == [url]
    assert resultado.total_declarado == 31


# --- 2026-10-22: nuevo enunciado del total declarado -------------------- #


def test_apply_filters_total_mas_de_marco_real(
    ficha_publica: FichaFuente, politicas: PoliticasCaptura
) -> None:
    """Encabezado real 2026: frase completa 'Más de 99 resultados' (nbsp).

    La cifra es una COTA de LinkedIn; la etiqueta original viaja entera en
    la evidencia de la busqueda.
    """
    set_solo_keywords = SetFiltros(
        fuente_id="linkedin",
        indice=0,
        filtros=[{"tipo": "keywords", "valor": ["Data Engineer"]}],
    )
    url = "https://www.linkedin.com/jobs/search-results/?keywords=Data+Engineer"
    pagina = FakePage({url: _leer("lista_linkedin_total_mas_de.html")})
    resultado = LinkedInAdapter().apply_filters(
        pagina, ficha_publica, set_solo_keywords, politicas
    )
    assert resultado.total_declarado == 99
    assert resultado.evidencia_acotada == (
        f"url: {url} | total: 99 (Más de 99 resultados)"
    )


def test_apply_filters_total_forma_exacta_sigue_viva(
    ficha_publica: FichaFuente, politicas: PoliticasCaptura
) -> None:
    """Totales de dos cifras o menos se declaran a secas: 'N resultados'."""
    set_solo_keywords = SetFiltros(
        fuente_id="linkedin",
        indice=0,
        filtros=[{"tipo": "keywords", "valor": ["Data Engineer"]}],
    )
    url = "https://www.linkedin.com/jobs/search-results/?keywords=Data+Engineer"
    html = (
        "<html><body>"
        "<p>9 resultados</p>"
        "<div componentkey='job-card-component-ref-99901'>"
        "<div componentkey='job-card-component-ref-99901'>"
        "<span aria-hidden='true'>Oferta</span>"
        "</div></div>"
        "</body></html>"
    )
    pagina = FakePage({url: html})
    resultado = LinkedInAdapter().apply_filters(
        pagina, ficha_publica, set_solo_keywords, politicas
    )
    assert resultado.total_declarado == 9
    assert resultado.evidencia_acotada == f"url: {url} | total: 9"


def test_total_a_entero_sin_separadores() -> None:
    assert linkedin_mod._total_a_entero("99") == 99
    assert linkedin_mod._total_a_entero("1.024") == 1024
    assert linkedin_mod._total_a_entero("7") == 7


# ==== D61: reanudación por paginación y tramos de renovación ============== #

_POLITICAS_TRAMOS = PoliticasCaptura(
    max_paginas=10,
    max_ofertas_por_corrida=10,
    pausa_entre_lotes_segundos=0,
    estrategia_anti_bloqueo="none",
)


def test_capture_batch_reanuda_en_carta_start(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    """D61: reanuda la MISMA búsqueda en su paginación ```?start=N``` exacta.

    El reanudador llega por otra página (la URL de resultados no está en el
    mapa): la paginación se reconstruye determinista desde la búsqueda.
    """
    pagina = FakePage(
        {f"{URL_RESULTADOS}&start=3": _leer("lista_linkedin_sdui_2026_pag2.html")}
    )
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, _POLITICAS_TRAMOS, desde_desplazamiento=3
    )
    assert pagina.gotos == [f"{URL_RESULTADOS}&start=3"]
    assert len(lote.ofertas) == 2
    assert estado.desplazamiento_final == 5
    # La carta del accesorio no tiene botón "Siguiente": fin real de la búsqueda.
    assert estado.hay_mas_ofertas is False


def test_capture_batch_tramo_por_max_paginas(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    """D61: tramo cortado por presupuesto de páginas deja el avance exacto."""
    pagina = FakePage(
        {
            URL_RESULTADOS: _leer("lista_linkedin_sdui_2026.html"),
            f"{URL_RESULTADOS}&start=3": _leer("lista_linkedin_sdui_2026_pag2.html"),
        }
    )
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, _POLITICAS_TRAMOS, max_paginas=1
    )
    assert len(lote.ofertas) == 3
    assert lote.paginas_consumidas == 1
    assert estado.desplazamiento_final == 3
    assert estado.hay_mas_ofertas is True
    # El freno de emergencia por políticas no lo decide el tramo: es del nodo.
    assert estado.limite_alcanzado is False


def test_capture_batch_fin_real_reporta_continuacion(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    """D61: fin real sin botón anuncia ```hay_mas_ofertas=False``` y avance."""
    pagina = FakePage(
        {
            URL_RESULTADOS: _leer("lista_linkedin_sdui_2026.html"),
            f"{URL_RESULTADOS}&start=3": _leer("lista_linkedin_sdui_2026_pag2.html"),
            f"{URL_RESULTADOS}&start=5": "<html><body><div>sin resultados</div></body></html>",
        }
    )
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, _POLITICAS_TRAMOS
    )
    assert len(lote.ofertas) == 5
    assert estado.hay_mas_ofertas is False
    assert estado.desplazamiento_final == 5


def test_capture_batch_freno_ofertas_por_tramo(
    ficha_publica: FichaFuente,
    set_filtros: SetFiltros,
) -> None:
    """D61: ```max_ofertas``` del tramo acota capturas sin marcar límite."""
    pagina = FakePage(
        {
            URL_RESULTADOS: _leer("lista_linkedin_sdui_2026.html"),
            f"{URL_RESULTADOS}&start=3": _leer("lista_linkedin_sdui_2026_pag2.html"),
        }
    )
    lote, estado = LinkedInAdapter().capture_batch(
        pagina, ficha_publica, set_filtros, _POLITICAS_TRAMOS, max_ofertas=2
    )
    assert len(lote.ofertas) == 2
    # El desplazamiento camina TODAS las tarjetas de la página (3), incluso
    # las que el freno del tramo dejó de anexar.
    assert estado.desplazamiento_final == 3
    assert estado.hay_mas_ofertas is True
    assert estado.limite_alcanzado is False
