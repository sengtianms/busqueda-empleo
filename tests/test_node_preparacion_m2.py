"""Unit tests for the Preparación de ofertas node (sub-phase 5.3).

Everything is mocked per the testing strategy: HTTP via `httpx.MockTransport`
(replacing `_construir_cliente`), AI via a patched `analyze`, SQLite via the
`temp_db_file` fixture, and zero pauses so the suite stays fast.
"""

import time
from pathlib import Path
from typing import Any

import httpx
import pytest

import modules.preparation.nodes.preparacion as preparacion
from modules.preparation.nodes.preparacion import (
    ejecutar_preparacion,
)
from modules.preparation.run_context import RunContext
from shared.errors import LLMError
from shared.models import Offer
from shared.persistence import (
    actualizar_fila,
    buscar_por_id,
    escribir_fila,
    leer_tabla,
)
from shared.retry import should_retry

CONFIG_RAPIDO: dict[str, Any] = {
    "umbral_titulo": 90,
    "umbral_descripcion": 85,
    "max_pasadas": 2,
    "pausa_entre_ofertas_segundos": 0,
    "limite_vida_sesion": 50,
    "retries": {
        "max_attempts": 2,
        "base_wait_seconds": 0,
        "max_wait_seconds": 0,
        "multiplier": 1,
    },
    "timeout_puerta_segundos": 60,
    "puertas_alternas": [],
}

HTML_COMPLETO = """
<html><body>
<div class="top-card-layout__card">
  <h1 class="top-card-layout__title">Ingeniero de Datos Senior</h1>
  <span class="topcard__flavor topcard__flavor--bullet">
    Bogotá, Distrito Capital, Colombia</span>
  <span class="workplace-type">Remote</span>
  <a class="topcard__org-name-link" href="/company/acme-corp/">Acme Corp</a>
</div>
<div class="show-more-less-html__markup"><p>Descripción larga de la vacante.</p></div>
</body></html>
"""

HTML_SIN_H1 = HTML_COMPLETO.replace(
    '<h1 class="top-card-layout__title">Ingeniero de Datos Senior</h1>', ""
)
HTML_SIN_EMPRESA = HTML_COMPLETO.replace(
    '<a class="topcard__org-name-link" href="/company/acme-corp/">Acme Corp</a>',
    "",
)
HTML_SIN_DESCRIPCION = HTML_COMPLETO.replace(
    '<div class="show-more-less-html__markup"><p>Descripción larga de la'
    " vacante.</p></div>",
    "",
)
HTML_ESTRUCTURADO = """
<html><body>
<div class="top-card-layout__card">
  <h1 class="top-card-layout__title">Ingeniero de Datos Senior</h1>
</div>
<div class="show-more-less-html__markup">
  <p>Primer párrafo de la vacante.</p>
  <p>Requisitos:</p>
  <ul>
    <li>Python avanzado</li>
    <li>SQL y modelado de datos</li>
  </ul>
  Enviar hoja de vida a<br>vacantes@acme.com
  <p>Acerca de <b>Acme Corp</b> y su equipo.</p>
</div>
<a class="topcard__org-name-link" href="/company/acme-corp/">Acme Corp</a>
</body></html>
"""
HTML_AUTHWALL = (
    "<html><head><title>Sign Up | LinkedIn</title></head>"
    "<body>Please sign in to continue (authwall)</body></html>"
)
HTML_VACIO = "<html><body></body></html>"


def _contexto(config: dict[str, Any] | None = None) -> RunContext:
    return RunContext(
        config_preparacion=config if config is not None else dict(CONFIG_RAPIDO),
        candidatas=[],
        id_corrida="COR-PREP",
    )


def _insertar_oferta(
    oferta_id: str,
    estado: str = "descubierta",
    titulo: str = "Titulo tarjeta",
    ubicacion: str | None = None,
    modalidad: str | None = None,
) -> None:
    """Inserta una fila; `ubicacion`/`modalidad` simulan lo escrito por el
    Módulo 1 en la captura (traspaso aprobado 2026-08-25)."""
    datos: dict[str, Any] = {
        "id": oferta_id,
        "enlace": f"https://www.linkedin.com/jobs/view/{oferta_id}",
        "fecha_descubrimiento": "2026-08-20 10:00:00",
        "estado": estado,
        "titulo": titulo,
    }
    if ubicacion is not None:
        datos["ubicacion"] = ubicacion
    if modalidad is not None:
        datos["modalidad"] = modalidad
    escribir_fila("ofertas_descubiertas", datos)


def _instalar_servidor(
    monkeypatch: pytest.MonkeyPatch,
    guion: list[list[Any]],
) -> tuple[list[httpx.Client], list[str]]:
    """Sequential response script flattened across all requests (the guest
    session is reused, so scripts must be request-ordered, not client-ordered).
    Items are `(status, html)` tuples or Exception instances."""
    clientes: list[httpx.Client] = []
    peticiones: list[str] = []
    plan = iter(item for sub in guion for item in sub)

    def fabrica() -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            peticiones.append(str(request.url))
            item = next(plan)
            if isinstance(item, Exception):
                raise item
            estado, html = item
            return httpx.Response(estado, text=html, request=request)

        cliente = httpx.Client(
            transport=httpx.MockTransport(handler), follow_redirects=True
        )
        clientes.append(cliente)
        return cliente

    monkeypatch.setattr(preparacion, "_construir_cliente", fabrica)
    return clientes, peticiones


def _instalar_ia(
    monkeypatch: pytest.MonkeyPatch,
    resultado: Any,
) -> list[str]:
    llamadas: list[str] = []

    def falso_analyze(
        prompt_id: str,
        context: dict[str, Any],
        purpose: str = "preparacion",
        **kwargs: Any,
    ) -> dict[str, Any]:
        llamadas.append(context["texto_ubicacion"])
        assert prompt_id == preparacion.PROMPT_UBICACION
        assert purpose == "preparacion"
        if isinstance(resultado, Exception):
            raise resultado
        return dict(resultado)

    monkeypatch.setattr(preparacion, "analyze", falso_analyze)
    return llamadas


TUPLA_BOGOTA = {"municipio": "Bogotá", "departamento": "Distrito Capital", "pais": "Colombia"}


# ----------------------------------------------------------------- Captura ok


def test_extraccion_completa_actualiza_oferta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta(
        "OFE-0001",
        ubicacion="Bogotá, Distrito Capital, Colombia",
        modalidad="remoto",
    )
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["estado"] == "preparada"
    assert fila["titulo"] == "Ingeniero de Datos Senior"
    assert "vacante" in str(fila["descripcion_original"])
    # Propiedad del Módulo 1: M2 las conserva intactas.
    assert fila["modalidad"] == "remoto"
    assert fila["ubicacion"] == "Bogotá, Distrito Capital, Colombia"
    empresa = leer_tabla("empresas", {"nombre_normalizado": "acme corp"})
    assert len(empresa) == 1
    assert empresa[0]["perfil_linkedin"] == (
        "https://www.linkedin.com/company/acme-corp/"
    )
    assert fila["empresa_id"] == empresa[0]["id"]
    ubicaciones = leer_tabla("ubicaciones", {})
    assert len(ubicaciones) == 1
    assert fila["ubicacion_id"] == ubicaciones[0]["id"]
    eventos = leer_tabla("eventos", {"codigo": "oferta_preparada"})
    assert len(eventos) == 1
    assert eventos[0]["id_oferta"] == "OFE-0001"
    assert eventos[0]["tipo"] == "suceso"


def test_descripcion_estructurada_d41(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    _instalar_servidor(monkeypatch, [[(200, HTML_ESTRUCTURADO)]])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert str(fila["descripcion_original"]) == (
        "Primer párrafo de la vacante.\n"
        "Requisitos:\n"
        "- Python avanzado\n"
        "- SQL y modelado de datos\n"
        "Enviar hoja de vida a\nvacantes@acme.com\n"
        "Acerca de Acme Corp y su equipo."
    )


def test_clave_empresa_conserva_caracteres_d41(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    html = HTML_COMPLETO.replace(">Acme Corp<", ">Clínica & Salud S.A.<")
    _instalar_servidor(monkeypatch, [[(200, html)]])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    fila = leer_tabla("empresas", {"nombre_normalizado": "clínica & salud s.a."})
    assert len(fila) == 1


def test_h1_ausente_conserva_titulo_tarjeta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_H1)]])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["titulo"] == "Titulo tarjeta"  # RN-10


def test_pagina_sin_empresa_continua_con_na(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_EMPRESA)]])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["empresa_id"] == "N/A"  # ERR-07
    assert fila["estado"] == "preparada"


def test_descripcion_vacia_guarda_nr_con_evidencia(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_DESCRIPCION)]])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["descripcion_original"] == "N/R"
    assert "descripcion no extraible" in str(fila["observaciones"])


# ------------------------------------------------------- Fallos de captura


def test_authwall_renovacion_y_logro(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    clientes, peticiones = _instalar_servidor(
        monkeypatch, [[(200, HTML_AUTHWALL)], [(200, HTML_COMPLETO)]]
    )
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    assert len(peticiones) == 2
    assert len(clientes) == 2  # ERR-04: sesión renovada entre intentos
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["estado"] == "preparada"


def test_authwall_persistente_agota_en_fallo(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    muro = [(200, HTML_AUTHWALL)]
    _instalar_servidor(monkeypatch, [list(muro), list(muro)])
    llamadas = _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    contexto = _contexto()
    resultado = ejecutar_preparacion(contexto)

    assert resultado.estado == "completada"  # el fallo es de la oferta, no aborto
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["estado"] == "descubierta"  # RN-04
    assert contexto.contador_errores == 1
    assert llamadas == []  # jamás llegó al paso de ubicación
    eventos = leer_tabla("eventos", {"codigo": "preparacion_fallida"})
    assert len(eventos) == 1
    assert eventos[0]["id_oferta"] == "OFE-0001"
    assert eventos[0]["tipo"] == "error"
    assert "authwall_detectado" in str(eventos[0]["evidencia"])


def test_404_agota_reintentos_pagina_inalcanzable(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    _instalar_servidor(monkeypatch, [[(404, "")], [(404, "")]])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    ejecutar_preparacion(_contexto())

    eventos = leer_tabla("eventos", {"codigo": "preparacion_fallida"})
    assert len(eventos) == 1
    assert "pagina_inalcanzable" in str(eventos[0]["evidencia"])


def test_timeout_mapea_tiempo_agotado_captura(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    agotado = [(httpx.ReadTimeout("read exceeded")), (httpx.ReadTimeout("again"))]
    _instalar_servidor(monkeypatch, [list(agotado)])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    ejecutar_preparacion(_contexto())

    eventos = leer_tabla("eventos", {"codigo": "preparacion_fallida"})
    assert len(eventos) == 1
    assert "tiempo_agotado_captura" in str(eventos[0]["evidencia"])


def test_html_invalido_sin_reintento(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    _, peticiones = _instalar_servidor(monkeypatch, [[(200, HTML_VACIO)]])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    ejecutar_preparacion(_contexto())

    assert len(peticiones) == 1  # ERR-05 no reintenta
    eventos = leer_tabla("eventos", {"codigo": "preparacion_fallida"})
    assert "respuesta_invalida" in str(eventos[0]["evidencia"])


def test_error_interno_captura_sin_reintento(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")

    def estalla(html: str) -> preparacion.DatosCaptura:
        raise RuntimeError("x" * 500)

    monkeypatch.setattr(preparacion, "_extraer_datos", estalla)
    _, peticiones = _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    ejecutar_preparacion(_contexto())

    assert len(peticiones) == 1  # ERR-06 no reintenta
    eventos = leer_tabla("eventos", {"codigo": "preparacion_fallida"})
    assert "error_interno_captura" in str(eventos[0]["evidencia"])
    assert str(eventos[0]["evidencia"]).endswith("...")  # RN-12: acotada
    assert len(str(eventos[0]["evidencia"])) <= 303  # 300 + sufijo


# ------------------------------------------------------------- Sesión/pausa


def test_sesion_reutilizada_entre_ofertas(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    _insertar_oferta("OFE-0002")
    clientes, _peticiones = _instalar_servidor(
        monkeypatch, [[(200, HTML_COMPLETO)], [(200, HTML_COMPLETO)]]
    )
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)
    contexto = _contexto()

    resultado = ejecutar_preparacion(contexto)

    assert resultado.estado == "completada"
    assert len(clientes) == 1  # RN-03: una sola sesión
    assert contexto.ofertas_en_sesion == 2


def test_renovacion_por_limite_vida_sesion(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = dict(CONFIG_RAPIDO)
    config["limite_vida_sesion"] = 1
    _insertar_oferta("OFE-0001")
    _insertar_oferta("OFE-0002")
    clientes, _peticiones = _instalar_servidor(
        monkeypatch, [[(200, HTML_COMPLETO)], [(200, HTML_COMPLETO)]]
    )
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    resultado = ejecutar_preparacion(_contexto(config))

    assert resultado.estado == "completada"
    assert len(clientes) == 2  # renovación cada N=1 ofertas
    assert clientes[0].is_closed  # la sesión vieja se cierra al renovar
    assert not clientes[1].is_closed  # la activa queda para Finalizar (5.5)


def test_pausa_solo_entre_ofertas(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = dict(CONFIG_RAPIDO)
    config["pausa_entre_ofertas_segundos"] = 0.5
    _insertar_oferta("OFE-0001")
    _insertar_oferta("OFE-0002")
    _instalar_servidor(
        monkeypatch, [[(200, HTML_COMPLETO)], [(200, HTML_COMPLETO)]]
    )
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)
    dormidas: list[float] = []
    monkeypatch.setattr(
        "modules.preparation.nodes.preparacion.time.sleep", lambda s: dormidas.append(s)
    )

    ejecutar_preparacion(_contexto(config))

    assert dormidas == [0.5]  # VAL-03: entre ofertas, no tras la última


# ------------------------------------------------------------------ Empresa


def test_empresa_nueva_se_crea_con_perfil(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    ejecutar_preparacion(_contexto())

    empresas = leer_tabla("empresas", {})
    assert len(empresas) == 1
    assert empresas[0]["nombre"] == "Acme Corp"
    assert empresas[0]["nombre_normalizado"] == "acme corp"


def test_empresa_existente_se_reutiliza(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    escribir_fila(
        "empresas",
        {
            "id": "EMP-0001",
            "nombre": "Acme Corp",
            "nombre_normalizado": "acme corp",
            "perfil_linkedin": "N/A",
        },
    )
    _insertar_oferta("OFE-0001")
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    ejecutar_preparacion(_contexto())

    assert len(leer_tabla("empresas", {})) == 1  # upsert idempotente
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["empresa_id"] == "EMP-0001"


def test_cache_evita_segunda_consulta_de_catalogos(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Distrito Capital, Colombia")
    _insertar_oferta("OFE-0002", ubicacion="Bogotá, Distrito Capital, Colombia")
    _instalar_servidor(
        monkeypatch, [[(200, HTML_COMPLETO)], [(200, HTML_COMPLETO)]]
    )
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)
    consultas: list[str] = []

    def espia(tabla: str, filtros: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        consultas.append(tabla)
        return leer_tabla(tabla, filtros)

    monkeypatch.setattr(
        "modules.preparation.nodes.preparacion.leer_tabla", espia
    )

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    assert consultas.count("empresas") == 1  # VAL-06: caché de corrida
    assert consultas.count("ubicaciones") == 1
    assert len(leer_tabla("empresas", {})) == 1


# ---------------------------------------------------------------- Ubicación


def test_remoto_no_crea_fila_ni_invoca_ia(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001", ubicacion="Remoto")
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])
    llamadas = _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["ubicacion_id"] == "N/R"  # RN-06
    assert leer_tabla("ubicaciones", {}) == []
    assert llamadas == []


def test_municipio_completo_crea_tupla_normalizada(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Distrito Capital, Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    ejecutar_preparacion(_contexto())

    ubicaciones = leer_tabla("ubicaciones", {})
    assert len(ubicaciones) == 1  # VAL-04: componentes normalizados
    assert ubicaciones[0]["municipio"] == "bogota"
    assert ubicaciones[0]["departamento"] == "distrito capital"
    assert ubicaciones[0]["pais"] == "colombia"


def test_textos_distintos_misma_tupla_una_sola_fila(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta(
        "OFE-0001", ubicacion="Bogotá, Distrito Capital, Colombia"
    )
    _insertar_oferta("OFE-0002", ubicacion="BOGOTÁ, Distrito Capital, Colombia")
    _instalar_servidor(
        monkeypatch, [[(200, HTML_COMPLETO)], [(200, HTML_COMPLETO)]]
    )
    llamadas = _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    ejecutar_preparacion(_contexto())

    assert len(leer_tabla("ubicaciones", {})) == 1  # RN-06 dedup por tupla
    assert llamadas == [
        "Bogotá, Distrito Capital, Colombia",
        "BOGOTÁ, Distrito Capital, Colombia",
    ]  # RN-07: una invocación por TEXTO distinto; la tupla deduplica en BD


def test_pais_solo_genera_fila_compartida(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001", ubicacion="Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])
    _instalar_ia(
        monkeypatch, {"municipio": "N/A", "departamento": "N/A", "pais": "Colombia"}
    )

    ejecutar_preparacion(_contexto())

    ubicaciones = leer_tabla("ubicaciones", {})
    assert len(ubicaciones) == 1
    assert (
        ubicaciones[0]["municipio"],
        ubicaciones[0]["departamento"],
        ubicaciones[0]["pais"],
    ) == ("N/A", "N/A", "colombia")


def test_chuleta_departamentos_casos_directos() -> None:
    """D43: variantes de texto que la chuleta resuelve sin IA (función pura)."""
    resolver = preparacion._clasificar_departamento
    assert resolver("CAUCA") == ("N/A", "cauca", "colombia")
    assert resolver("Cauca") == ("N/A", "cauca", "colombia")
    assert resolver("Antioquia, Colombia") == ("N/A", "antioquia", "colombia")
    assert resolver("Distrito Capital, Colombia") == (
        "N/A",
        "distrito capital",
        "colombia",
    )
    # D46: alias con tupla COMPLETA (no pierde la ciudad)
    assert resolver("Bogotá D.C.") == ("bogota", "distrito capital", "colombia")
    assert resolver(
        "Área metropolitana de Bogotá D.C."
    ) == ("bogota", "distrito capital", "colombia")
    assert resolver("Bogotá, Distrito Capital, Colombia") is None
    assert resolver("Valle del Cauca, COLOMBIA") == (
        "N/A",
        "valle del cauca",
        "colombia",
    )
    assert resolver("Medellín, Antioquia") is None  # con ciudad: va a la IA
    assert resolver("Lima, Perú") is None
    assert resolver("Colombia") is None  # país solo: camino IA existente


def test_departamento_en_mayusculas_resuelve_sin_ia(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D43: el caso real medido ('CAUCA' ×16 con ERR-08) se resuelve con una
    fila de catálogo determinista y cero invocaciones a la IA."""
    _insertar_oferta("OFE-0001", ubicacion="CAUCA")
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])
    llamadas = _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    assert llamadas == []
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["estado"] == "preparada"
    ubicaciones = leer_tabla("ubicaciones", {})
    assert len(ubicaciones) == 1
    assert (
        ubicaciones[0]["municipio"],
        ubicaciones[0]["departamento"],
        ubicaciones[0]["pais"],
    ) == ("N/A", "cauca", "colombia")
    assert fila["ubicacion_id"] == ubicaciones[0]["id"]


def test_guarda_alias_casos_directos(temp_db_file: Path) -> None:
    """D46: reglas de la resolución exacta+fusión en una sola lectura."""
    escribir_fila(
        "ubicaciones", {"municipio": "bogota", "departamento": "distrito capital",
                        "pais": "colombia"}
    )
    escribir_fila(
        "ubicaciones", {"municipio": "gachala", "departamento": "boyaca",
                        "pais": "colombia"}
    )
    resolver = preparacion._resolver_ubicacion_existente
    contexto = _contexto()
    id_bogota = [r["id"] for r in leer_tabla("ubicaciones", {"municipio": "bogota"})][0]
    id_gachala = [
        r["id"] for r in leer_tabla("ubicaciones", {"municipio": "gachala"})
    ][0]

    # Igualdad exacta gana siempre (aun con umbral 0)
    assert resolver(contexto, ("bogota", "distrito capital", "colombia")) == (
        id_bogota,
        False,
    )
    # Variante de ciudad con región desconocida -> fusiona con bogota
    assert resolver(contexto, ("bogota d c", "N/A", "colombia")) == (
        id_bogota,
        True,
    )
    # Conflicto de región (cundinamarca vs boyaca) bloquea la fusión
    assert resolver(contexto, ("gachala", "cundinamarca", "colombia")) is None
    # Sin ninguna coincidencia real (solo comodines) nunca fusiona
    assert resolver(contexto, ("N/A", "antioquia", "colombia")) is None
    # Solo-país jamás fusiona por esta vía
    assert resolver(contexto, ("N/A", "N/A", "colombia")) is None
    # Umbral 0 desactiva SOLO la vía difusa; la exacta sigue funcionando
    contexto_sin = _contexto({**CONFIG_RAPIDO, "umbral_alias_ubicacion": 0})
    assert resolver(contexto_sin, ("bogota d c", "N/A", "colombia")) is None
    assert resolver(
        contexto_sin, ("gachala", "boyaca", "colombia")
    ) == (id_gachala, False)
    # Otro país no es candidato
    assert resolver(contexto, ("lima", "N/A", "peru"),) is None


def _instalar_ia_por_texto(
    monkeypatch: pytest.MonkeyPatch,
    respuestas: dict[str, dict[str, str]],
) -> list[str]:
    """Variante de `_instalar_ia` con respuesta distinta por texto crudo."""
    llamadas: list[str] = []

    def falso_analyze(
        prompt_id: str,
        context: dict[str, Any],
        purpose: str = "preparacion",
        **kwargs: Any,
    ) -> dict[str, Any]:
        llamadas.append(context["texto_ubicacion"])
        return dict(respuestas[context["texto_ubicacion"]])

    monkeypatch.setattr(preparacion, "analyze", falso_analyze)
    return llamadas


def test_variante_bogota_dc_se_fusiona_con_fila_existente(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D46: el caso real medido — 'Bogotá' crea la fila canónica y una
    variante clasificada distinto reusa esa fila en vez de duplicarla."""
    _insertar_oferta("OFE-0001", ubicacion="Bogotá")
    _insertar_oferta("OFE-0002", ubicacion="Bogota DC")  # no chuleta: va a IA
    _instalar_servidor(
        monkeypatch, [[(200, HTML_COMPLETO)], [(200, HTML_COMPLETO)]]
    )
    llamadas = _instalar_ia_por_texto(
        monkeypatch,
        {
            "Bogotá": TUPLA_BOGOTA,
            "Bogota DC": {
                "municipio": "Bogotá D.C.",
                "departamento": "N/A",
                "pais": "Colombia",
            },
        },
    )

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    assert llamadas == ["Bogotá", "Bogota DC"]
    assert len(leer_tabla("ubicaciones", {})) == 1  # sin duplicado
    fila1 = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    fila2 = buscar_por_id("ofertas_descubiertas", "OFE-0002")
    assert fila1 is not None and fila2 is not None
    assert fila1["ubicacion_id"] == fila2["ubicacion_id"]


def test_alias_desactivado_crea_fila_distinta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D46: umbral 0 desactiva la fusión — comportamiento previo intacto."""
    config = {**CONFIG_RAPIDO, "umbral_alias_ubicacion": 0}
    _insertar_oferta("OFE-0001", ubicacion="Bogotá")
    _insertar_oferta("OFE-0002", ubicacion="Bogota DC")
    _instalar_servidor(
        monkeypatch, [[(200, HTML_COMPLETO)], [(200, HTML_COMPLETO)]]
    )
    _instalar_ia_por_texto(
        monkeypatch,
        {
            "Bogotá": TUPLA_BOGOTA,
            "Bogota DC": {
                "municipio": "Bogotá D.C.",
                "departamento": "N/A",
                "pais": "Colombia",
            },
        },
    )

    ejecutar_preparacion(_contexto(config))

    assert len(leer_tabla("ubicaciones", {})) == 2


def test_json_ia_invalido_queda_pendiente_err08(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Distrito Capital, Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])
    _instalar_ia(monkeypatch, {"foo": "bar"})

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"  # la IA jamás bloquea (RN-07)
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["ubicacion_id"] == "N/A"  # pendiente (RN-08)
    assert fila["estado"] == "preparada"


def test_ia_caida_llmerror_queda_pendiente_err08(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Distrito Capital, Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])
    _instalar_ia(monkeypatch, LLMError("001", "ollama down"))

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["ubicacion_id"] == "N/A"


# -------------------------------------------------------------------- Lote b


def test_lote_b_resuelve_sin_http(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta(
        "OFE-0001",
        estado="preparada",
        ubicacion="Medellín, Antioquia",
    )
    actualizar_fila(
        "ofertas_descubiertas", "OFE-0001", {"ubicacion_id": "N/A"}
    )
    _, peticiones = _instalar_servidor(monkeypatch, [[]])
    _instalar_ia(
        monkeypatch, {"municipio": "Medellín", "departamento": "Antioquia", "pais": "Colombia"}
    )

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    assert peticiones == []  # H1: sin re-capturar la página
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["ubicacion_id"].startswith("UBI-")
    eventos = leer_tabla("eventos", {"codigo": "oferta_preparada"})
    assert len(eventos) == 1
    assert "lote (b)" in str(eventos[0]["evidencia"])


def test_lote_b_ia_caida_deja_pendiente(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta(
        "OFE-0001", estado="preparada", ubicacion="Medellín, Antioquia"
    )
    actualizar_fila(
        "ofertas_descubiertas", "OFE-0001", {"ubicacion_id": "N/A"}
    )
    _instalar_servidor(monkeypatch, [[]])
    _instalar_ia(monkeypatch, LLMError("001", "ollama down"))

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["ubicacion_id"] == "N/A"
    assert leer_tabla("eventos", {"codigo": "oferta_preparada"}) == []


def test_fallo_ia_no_se_cachea_y_lote_b_lo_resuelve(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Distrito Capital, Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])
    # D75: el fallo simulado es una RESPUESTA mal formada (contenido), no un
    # fallo de puerta — así la principal queda viva y el lote (b) de la MISMA
    # corrida puede reintentar la pendiente.
    llamadas = _instalar_ia(
        monkeypatch, LLMError("003", "Response is not valid JSON | module: ia_service")
    )
    contexto = _contexto()

    primero = ejecutar_preparacion(contexto)
    assert primero.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["ubicacion_id"] == "N/A"
    assert not contexto.puertas_caidas  # la puerta no se silencia

    # La IA vuelve: el lote (b) de la MISMA corrida resuelve la pendiente.
    monkeypatch.setattr(
        preparacion,
        "analyze",
        lambda prompt_id, context, purpose="preparacion", **kwargs: dict(
            TUPLA_BOGOTA
        ),
    )

    segundo = ejecutar_preparacion(contexto)
    assert segundo.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["ubicacion_id"].startswith("UBI-")
    assert len(llamadas) == 2  # el fallo no entró en cache_ia (RN-07)


def test_lote_b_con_sentinela_na_termina_en_nr_sin_ia(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fila legada `preparada`+`N/A` sin texto crudo: terminal `N/R`, la IA
    jamás recibe centinelas."""
    _insertar_oferta(
        "OFE-0001", estado="preparada", ubicacion="N/A"
    )
    actualizar_fila(
        "ofertas_descubiertas", "OFE-0001", {"ubicacion_id": "N/A"}
    )
    _instalar_servidor(monkeypatch, [[]])
    llamadas = _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    assert llamadas == []
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["ubicacion_id"] == "N/R"


def test_lote_b_corrupcion_al_persistir_aborta_err09(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta(
        "OFE-0001", estado="preparada", ubicacion="Medellín, Antioquia"
    )
    actualizar_fila(
        "ofertas_descubiertas", "OFE-0001", {"ubicacion_id": "N/A"}
    )
    _instalar_servidor(monkeypatch, [[]])
    _instalar_ia(
        monkeypatch,
        {"municipio": "Medellín", "departamento": "Antioquia", "pais": "Colombia"},
    )

    def estalla(_tabla: str, _id: str, _campos: dict[str, Any]) -> bool:
        raise RuntimeError("db corrupta")

    monkeypatch.setattr(preparacion, "actualizar_fila", estalla)
    contexto = _contexto()

    resultado = ejecutar_preparacion(contexto)

    assert resultado.estado == "abortada"
    assert resultado.codigo == "ERR-09"
    eventos = leer_tabla("eventos", {"codigo": "ERR-09"})
    assert len(eventos) == 1
    assert eventos[0]["id_oferta"] == "OFE-0001"


# -------------------------------------------------------- Oferta y eventos


def test_actualizacion_respeta_d31_sin_vacios(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_EMPRESA)]])
    _instalar_ia(monkeypatch, {"municipio": "N/A", "departamento": "N/A", "pais": "Chile"})

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    for clave in ("empresa_id", "ubicacion_id", "modalidad", "titulo",
                  "descripcion_original", "observaciones"):
        valor = fila.get(clave)
        assert valor not in ("", None), f"{clave} viola D31"


def test_no_toca_verificacion_ni_corrida(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    actualizar_fila(
        "ofertas_descubiertas",
        "OFE-0001",
        {
            "fecha_ultima_verificacion": "2026-08-19 00:00:00",
            "id_corrida": "COR-VIEJA",
        },
    )
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["fecha_ultima_verificacion"] == "2026-08-19 00:00:00"  # RN-11
    assert fila["id_corrida"] == "COR-VIEJA"


def test_contadores_del_contexto(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001")
    _insertar_oferta("OFE-0002")
    _instalar_servidor(
        monkeypatch, [[(404, ""), (404, "")], [(200, HTML_COMPLETO)]]
    )
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)
    contexto = _contexto()

    ejecutar_preparacion(contexto)

    assert contexto.contador_preparadas == 1
    assert contexto.contador_errores == 1
    assert contexto.contador_duplicadas == 0


# ------------------------------------------------------------------- Abortos


def test_contexto_ausente_aborta_sin_bd() -> None:
    resultado = ejecutar_preparacion(None)

    assert resultado.estado == "abortada"
    assert resultado.codigo == "ERR-01"
    assert resultado.contexto is None


def test_config_invalida_aborta_err01(
    temp_db_file: Path,
) -> None:
    contexto = RunContext(
        config_preparacion={}, candidatas=[], id_corrida="COR-MALA"
    )

    resultado = ejecutar_preparacion(contexto)

    assert resultado.estado == "abortada"
    assert resultado.codigo == "ERR-01"
    eventos = leer_tabla("eventos", {"codigo": "ERR-01"})
    assert len(eventos) == 1


def test_fallo_bd_al_determinar_lotes_aborta_err09(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def estalla() -> list[dict[str, Any]]:
        raise RuntimeError("db gone")

    monkeypatch.setattr(preparacion, "leer_candidatas_descubiertas", estalla)
    contexto = _contexto()

    resultado = ejecutar_preparacion(contexto)

    assert resultado.estado == "abortada"
    assert resultado.codigo == "ERR-09"
    eventos = leer_tabla("eventos", {"codigo": "ERR-09"})
    assert len(eventos) == 1


# ------------------------------------------------------------ Shared helpers


def test_codigos_reintentables_incluyen_captura_m2() -> None:
    assert should_retry("pagina_inalcanzable")  # ERR-02
    assert should_retry("tiempo_agotado_captura")  # ERR-03
    assert should_retry("authwall_detectado")  # ERR-04
    assert not should_retry("respuesta_invalida")  # ERR-05
    assert not should_retry("error_interno_captura")  # ERR-06


def test_offer_tiene_campos_nuevos_d33() -> None:
    oferta = Offer(enlace="https://x", titulo="t", descripcion_original="d")
    assert oferta.ubicacion == "N/A"
    assert oferta.modalidad == "N/A"


def test_m2_no_sobreescribe_ubicacion_ni_modalidad_de_m1(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Traspaso 2026-08-25: la actualización de M2 jamás toca las columnas
    propiedad del Módulo 1 (`ubicacion`, `modalidad`)."""
    _insertar_oferta(
        "OFE-0001",
        ubicacion="Medellín, Antioquia",
        modalidad="hibrido",
    )
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])
    _instalar_ia(monkeypatch, TUPLA_BOGOTA)

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["estado"] == "preparada"
    assert fila["ubicacion"] == "Medellín, Antioquia"
    assert fila["modalidad"] == "hibrido"


def test_pausa_con_jitter_d42(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D42: la espera efectiva es uniforme en [base-jitter, base+jitter]."""
    import random as random_mod

    llamadas_uniform: list[tuple[float, float]] = []
    dormidos: list[float] = []
    def _uniforme(a: float, b: float) -> float:
        llamadas_uniform.append((a, b))
        return 1.0

    monkeypatch.setattr(random_mod, "uniform", _uniforme)
    monkeypatch.setattr(time, "sleep", dormidos.append)
    monkeypatch.setattr(
        preparacion,
        "_capturar_pagina",
        lambda ctx, enlace: preparacion.DatosCaptura(
            titulo_h1="T", descripcion="", empresa_nombre="", empresa_perfil=""
        ),
    )
    monkeypatch.setattr(preparacion, "_diligenciar_empresa", lambda ctx, n, p: "EMP-0001")
    monkeypatch.setattr(preparacion, "_diligenciar_ubicacion", lambda ctx, t: "N/R")

    config = dict(CONFIG_RAPIDO)
    config["pausa_entre_ofertas_segundos"] = 2.0
    config["pausa_jitter_segundos"] = 0.5
    contexto = _contexto(config)
    lote = [{"id": f"OFE-{i:04d}", "enlace": f"https://x/{i}"} for i in range(3)]

    ok = preparacion._procesar_lote_a(contexto, lote)

    assert ok is True
    assert len(llamadas_uniform) == 2  # entre ofertas; nunca tras la última
    assert all(par == (1.5, 2.5) for par in llamadas_uniform)
    assert dormidos == [1.0, 1.0]


def test_pausa_sin_jitter_mantiene_fijo_d42(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import random as random_mod

    llamadas_uniform: list[tuple[float, float]] = []
    dormidos: list[float] = []
    def _uniforme(a: float, b: float) -> float:
        llamadas_uniform.append((a, b))
        return 0.0

    monkeypatch.setattr(random_mod, "uniform", _uniforme)
    monkeypatch.setattr(time, "sleep", dormidos.append)
    monkeypatch.setattr(
        preparacion,
        "_capturar_pagina",
        lambda ctx, enlace: preparacion.DatosCaptura(
            titulo_h1="T", descripcion="", empresa_nombre="", empresa_perfil=""
        ),
    )
    monkeypatch.setattr(preparacion, "_diligenciar_empresa", lambda ctx, n, p: "EMP-0001")
    monkeypatch.setattr(preparacion, "_diligenciar_ubicacion", lambda ctx, t: "N/R")

    config = dict(CONFIG_RAPIDO)
    config["pausa_entre_ofertas_segundos"] = 3.0
    contexto = _contexto(config)
    lote = [{"id": f"OFE-{i:04d}", "enlace": f"https://x/{i}"} for i in range(2)]
    assert preparacion._procesar_lote_a(contexto, lote) is True
    assert llamadas_uniform == []  # jitter ausente => pausa fija
    assert dormidos == [3.0]
