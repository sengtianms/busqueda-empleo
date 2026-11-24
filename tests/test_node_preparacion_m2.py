"""Unit tests for the Preparación de ofertas node (sub-phase 5.3, D77).

HTTP is mocked via `httpx.MockTransport` (replacing `_construir_cliente`),
location linking uses the deterministic catalogue engine (no AI), SQLite via
the `temp_db_file` fixture, and zero pauses so the suite stays fast.
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
    "puerta_principal_activa": False,
    "puertas_alternas": [
        {
            "nombre": "openrouter-1",
            "modelo": "google/gemma-4-31b-it",
            "clave_ref": "OPENROUTER_API_KEY_1",
        },
    ],
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

HTML_SIN_UBICACION = HTML_COMPLETO.replace(
    '  <span class="topcard__flavor topcard__flavor--bullet">\n'
    '    Bogotá, Distrito Capital, Colombia</span>\n',
    "",
)


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


def _sembrar_catalogo() -> dict[str, str]:
    """Inserta cuatro filas en `ubicaciones` y devuelve sus ids.

    The triple-N/A "no aplica" row is created by init_db(), so we only
    seed the country row (N/A, N/A, Colombia) and the department sentinel.
    """
    ids: dict[str, str] = {}
    ids["bogotá/cundinamarca"] = escribir_fila(
        "ubicaciones",
        {"municipio": "Bogotá", "departamento": "Cundinamarca", "pais": "Colombia"},
    )
    ids["medellín/antioquia"] = escribir_fila(
        "ubicaciones",
        {"municipio": "Medellín", "departamento": "Antioquia", "pais": "Colombia"},
    )
    ids["N/A/antioquia"] = escribir_fila(
        "ubicaciones",
        {"municipio": "N/A", "departamento": "Antioquia", "pais": "Colombia"},
    )
    ids["N/A/N/A"] = escribir_fila(
        "ubicaciones",
        {"municipio": "N/A", "departamento": "N/A", "pais": "Colombia"},
    )
    # The triple-N/A row is already created by init_db()
    na_rows = leer_tabla("ubicaciones", {
        "municipio": "N/A", "departamento": "N/A", "pais": "N/A"
    })
    ids["N/A/N/A/N/A"] = na_rows[0]["id"] if na_rows else "N/A"
    return ids


# ----------------------------------------------------------------- Captura ok


def test_extraccion_completa_actualiza_oferta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _sembrar_catalogo()
    _insertar_oferta(
        "OFE-0001",
        ubicacion="Bogotá, Cundinamarca, Colombia",
        modalidad="remoto",
    )
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["estado"] == "preparada"
    assert fila["titulo"] == "Ingeniero de Datos Senior"
    assert "vacante" in str(fila["descripcion_original"])
    assert fila["modalidad"] == "remoto"
    # La página trae la ubicación en el span topcard__flavor
    assert fila["ubicacion"] == "Bogotá, Distrito Capital, Colombia"
    empresa = leer_tabla("empresas", {"nombre_normalizado": "acme corp"})
    assert len(empresa) == 1
    assert empresa[0]["perfil_linkedin"] == (
        "https://www.linkedin.com/company/acme-corp/"
    )
    assert fila["empresa_id"] == empresa[0]["id"]
    # Deduplicación: "bogota" aparece dos veces (bogota + distrito capital→bogota),
    # queda un solo segmento → enlaza a Bogotá/Cundinamarca
    assert fila["ubicacion_id"] == ids["bogotá/cundinamarca"]
    # Catálogo no cambia: 4 sembradas + 1 de init_db = 5
    assert len(leer_tabla("ubicaciones", {})) == 5
    eventos = leer_tabla("eventos", {"codigo": "oferta_preparada"})
    assert len(eventos) == 1
    assert eventos[0]["id_oferta"] == "OFE-0001"
    assert eventos[0]["tipo"] == "suceso"


def test_descripcion_estructurada_d41(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_ESTRUCTURADO)]])

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
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    html = HTML_COMPLETO.replace(">Acme Corp<", ">Clínica & Salud S.A.<")
    _instalar_servidor(monkeypatch, [[(200, html)]])

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    fila = leer_tabla("empresas", {"nombre_normalizado": "clínica & salud s.a."})
    assert len(fila) == 1


def test_h1_ausente_conserva_titulo_tarjeta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_H1)]])

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["titulo"] == "Titulo tarjeta"  # RN-10


def test_pagina_sin_empresa_continua_con_na(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_EMPRESA)]])

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["empresa_id"] == "N/A"  # ERR-07
    assert fila["estado"] == "preparada"


def test_descripcion_vacia_guarda_nr_con_evidencia(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_DESCRIPCION)]])

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
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    clientes, peticiones = _instalar_servidor(
        monkeypatch, [[(200, HTML_AUTHWALL)], [(200, HTML_COMPLETO)]]
    )

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    assert len(peticiones) == 2
    assert len(clientes) == 2  # ERR-04: sesión renovada entre intentos
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["estado"] == "preparada"


def test_authwall_persistente_agota_en_fallo(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    muro = [(200, HTML_AUTHWALL)]
    _instalar_servidor(monkeypatch, [list(muro), list(muro)])

    contexto = _contexto()
    resultado = ejecutar_preparacion(contexto)

    assert resultado.estado == "completada"  # el fallo es de la oferta, no aborto
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["estado"] == "descubierta"  # RN-04
    assert contexto.contador_errores == 1
    eventos = leer_tabla("eventos", {"codigo": "preparacion_fallida"})
    assert len(eventos) == 1
    assert eventos[0]["id_oferta"] == "OFE-0001"
    assert eventos[0]["tipo"] == "error"
    assert "authwall_detectado" in str(eventos[0]["evidencia"])


def test_404_agota_reintentos_pagina_inalcanzable(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _instalar_servidor(monkeypatch, [[(404, "")], [(404, "")]])

    ejecutar_preparacion(_contexto())

    eventos = leer_tabla("eventos", {"codigo": "preparacion_fallida"})
    assert len(eventos) == 1
    assert "pagina_inalcanzable" in str(eventos[0]["evidencia"])


def test_timeout_mapea_tiempo_agotado_captura(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    agotado = [(httpx.ReadTimeout("read exceeded")), (httpx.ReadTimeout("again"))]
    _instalar_servidor(monkeypatch, [list(agotado)])

    ejecutar_preparacion(_contexto())

    eventos = leer_tabla("eventos", {"codigo": "preparacion_fallida"})
    assert len(eventos) == 1
    assert "tiempo_agotado_captura" in str(eventos[0]["evidencia"])


def test_html_invalido_sin_reintento(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _, peticiones = _instalar_servidor(monkeypatch, [[(200, HTML_VACIO)]])

    ejecutar_preparacion(_contexto())

    assert len(peticiones) == 1  # ERR-05 no reintenta
    eventos = leer_tabla("eventos", {"codigo": "preparacion_fallida"})
    assert "respuesta_invalida" in str(eventos[0]["evidencia"])


def test_error_interno_captura_sin_reintento(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")

    def estalla(html: str) -> preparacion.DatosCaptura:
        raise RuntimeError("x" * 500)

    monkeypatch.setattr(preparacion, "_extraer_datos", estalla)
    _, peticiones = _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])

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
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _insertar_oferta("OFE-0002", ubicacion="Medellín, Antioquia, Colombia")
    clientes, _peticiones = _instalar_servidor(
        monkeypatch, [[(200, HTML_COMPLETO)], [(200, HTML_COMPLETO)]]
    )
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
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _insertar_oferta("OFE-0002", ubicacion="Medellín, Antioquia, Colombia")
    clientes, _peticiones = _instalar_servidor(
        monkeypatch, [[(200, HTML_COMPLETO)], [(200, HTML_COMPLETO)]]
    )

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
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _insertar_oferta("OFE-0002", ubicacion="Medellín, Antioquia, Colombia")
    _instalar_servidor(
        monkeypatch, [[(200, HTML_COMPLETO)], [(200, HTML_COMPLETO)]]
    )
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
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])

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
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])

    ejecutar_preparacion(_contexto())

    assert len(leer_tabla("empresas", {})) == 1  # upsert idempotente
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["empresa_id"] == "EMP-0001"


def test_cache_evita_segunda_consulta_de_catalogos(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _insertar_oferta("OFE-0002", ubicacion="Bogotá, Cundinamarca, Colombia")
    _instalar_servidor(
        monkeypatch, [[(200, HTML_COMPLETO)], [(200, HTML_COMPLETO)]]
    )
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
    assert len(leer_tabla("empresas", {})) == 1


# ----------------------------------------------------- Ubicación (D77)


def test_ubicacion_enlaza_fila_existente(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)]])

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["ubicacion_id"] == ids["bogotá/cundinamarca"]
    assert len(leer_tabla("ubicaciones", {})) == 5  # catálogo no cambia


def test_ubicacion_sin_coincidencia_ia_crea_fila_sistema(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When deterministic engine fails, AI resolves and creates a new row."""
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Puerto Bogotá")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)]])

    def falso_ia(
        prompt_id: str,
        datos: dict[str, str],
        modelo: str,
        clave: str,
        *,
        timeout: float | None = None,
    ) -> dict[str, str]:
        return {"municipio": "Puerto Bogotá", "departamento": "Cundinamarca", "pais": "Colombia"}

    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_ia)

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["estado"] == "preparada"
    # Nueva fila creada con origen sistema (municipio normalizado sin tilde)
    nuevas = leer_tabla("ubicaciones", {
        "municipio": "puerto bogota", "origen": "sistema"
    })
    assert len(nuevas) == 1
    assert fila["ubicacion_id"] == nuevas[0]["id"]
    assert nuevas[0]["departamento"] == "cundinamarca"
    assert nuevas[0]["fecha_creacion"] != ""
    assert nuevas[0]["fecha_ultima_edicion"] != ""
    # Catálogo creció: 4 sembradas + 1 de init_db + 1 creada = 6
    assert len(leer_tabla("ubicaciones", {})) == 6
    eventos = leer_tabla("eventos", {"codigo": "oferta_preparada"})
    assert len(eventos) == 1


def test_ia_con_fila_ya_registrada_reutiliza_sin_error(temp_db_file: Path) -> None:
    """D82: a row unknown to the in-memory catalogue is reused, not duplicated."""
    import sqlite3

    from modules.preparation.ubicaciones import CatalogoUbicaciones

    _sembrar_catalogo()
    conn = sqlite3.connect(str(temp_db_file))
    try:
        conn.execute(
            "INSERT INTO ubicaciones (id, municipio, departamento, pais, origen) "
            "VALUES ('UBI-9001', 'puerto bogota', 'cundinamarca', 'colombia', 'sistema')"
        )
        conn.commit()
    finally:
        conn.close()

    contexto = _contexto()
    filas = [f for f in leer_tabla("ubicaciones", {}) if f["id"] != "UBI-9001"]
    contexto.catalogo_ubicaciones = CatalogoUbicaciones(filas)
    contexto.cache_ia["Puerto Bogotá"] = (
        "Puerto Bogotá", "Cundinamarca", "Colombia"
    )

    resultado = preparacion._diligenciar_ubicacion(contexto, "Puerto Bogotá")

    assert resultado == "UBI-9001"
    assert len(leer_tabla("ubicaciones", {"municipio": "puerto bogota"})) == 1


def test_ubicacion_solo_departamento_enlaza_fila_na(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Antioquia")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)]])

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["ubicacion_id"] == ids["N/A/antioquia"]


def test_ubicacion_solo_pais_enlaza_fila_pais(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)]])

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["ubicacion_id"] == ids["N/A/N/A"]


def test_ubicacion_remota_enlaza_fila_no_aplica(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Remoto")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)]])

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    # La fila "no aplica" se busca por su triple N/A
    na_filas = leer_tabla("ubicaciones", {
        "municipio": "N/A", "departamento": "N/A", "pais": "N/A"
    })
    assert len(na_filas) == 1
    assert fila["ubicacion_id"] == na_filas[0]["id"]
    assert len(leer_tabla("ubicaciones", {})) == 5  # catálogo no cambia


def test_ubicacion_ausente_enlaza_fila_no_aplica(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="N/A")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)]])

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    na_filas = leer_tabla("ubicaciones", {
        "municipio": "N/A", "departamento": "N/A", "pais": "N/A"
    })
    assert len(na_filas) == 1
    assert fila["ubicacion_id"] == na_filas[0]["id"]


def test_catalogo_de_ubicaciones_se_lee_una_sola_vez(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _insertar_oferta("OFE-0002", ubicacion="Medellín, Antioquia, Colombia")
    _instalar_servidor(
        monkeypatch, [[(200, HTML_COMPLETO)], [(200, HTML_COMPLETO)]]
    )
    consultas: list[str] = []

    def espia(tabla: str, filtros: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        consultas.append(tabla)
        return leer_tabla(tabla, filtros)

    monkeypatch.setattr(
        "modules.preparation.nodes.preparacion.leer_tabla", espia
    )

    ejecutar_preparacion(_contexto())

    assert consultas.count("ubicaciones") == 1


def test_catalogo_incompleto_aborta_err09(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing 'no aplica' or country row aborts with ERR-09."""
    import sqlite3

    _insertar_oferta("OFE-0001", ubicacion="Bogotá")
    # Vaciar ubicaciones por completo (incluida la fila "no aplica").
    conn = sqlite3.connect(str(temp_db_file))
    conn.execute("DELETE FROM ubicaciones")
    conn.commit()
    conn.close()

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "abortada"
    assert resultado.codigo == "ERR-09"
    eventos = leer_tabla("eventos", {"codigo": "ERR-09"})
    assert len(eventos) == 1
    assert "catalogo_ubicaciones_incompleto" in eventos[0]["evidencia"]
    # Ninguna oferta se procesó
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["estado"] == "descubierta"


def test_fallo_al_leer_catalogo_aborta_err09(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_oferta("OFE-0001", ubicacion="Bogotá")

    def estalla(tabla: str, filtros: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if tabla == "ubicaciones":
            raise RuntimeError("db corrupta")
        return leer_tabla(tabla, filtros)

    monkeypatch.setattr(
        "modules.preparation.nodes.preparacion.leer_tabla", estalla
    )

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "abortada"
    assert resultado.codigo == "ERR-09"
    eventos = leer_tabla("eventos", {"codigo": "ERR-09"})
    assert len(eventos) == 1
    assert eventos[0]["id_oferta"] == "N/A"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["estado"] == "descubierta"


def test_pendiente_no_se_reintenta_en_la_misma_corrida(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """IA down falls back to country row; offer prepared once, no lot b retry."""
    from shared.errors import LLMError

    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Puerto Bogotá")
    clientes, peticiones = _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)]])

    def falso_analyze(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise LLMError("003", "local Ollama responded with code 402")

    def falso_reserva(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise LLMError("004", "OpenRouter quota exceeded")

    monkeypatch.setattr(
        "modules.preparation.nodes.preparacion.analyze", falso_analyze
    )
    monkeypatch.setattr(
        "modules.preparation.nodes.preparacion.analyze_openrouter", falso_reserva
    )

    ejecutar_preparacion(_contexto())

    assert len(peticiones) == 1  # exactamente una captura HTTP
    eventos = leer_tabla("eventos", {"codigo": "oferta_preparada"})
    assert len(eventos) == 1
    for evento in eventos:
        assert "lote (b)" not in str(evento["evidencia"])

    # Oferta enlazada a la fila de país (sembrada por _sembrar_catalogo)
    ids = {"pais": None}
    pais_rows = leer_tabla("ubicaciones", {
        "municipio": "N/A", "departamento": "N/A", "pais": "Colombia"
    })
    if pais_rows:
        ids["pais"] = pais_rows[0]["id"]
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["ubicacion_id"] == ids["pais"]


# -------------------------------------------------------- Oferta y eventos


def test_actualizacion_respeta_d31_sin_vacios(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_EMPRESA)]])

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
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    actualizar_fila(
        "ofertas_descubiertas",
        "OFE-0001",
        {
            "fecha_ultima_verificacion": "2026-08-19 00:00:00",
            "id_corrida": "COR-VIEJA",
        },
    )
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["fecha_ultima_verificacion"] == "2026-08-19 00:00:00"  # RN-11
    assert fila["id_corrida"] == "COR-VIEJA"


def test_contadores_del_contexto(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá, Cundinamarca, Colombia")
    _insertar_oferta("OFE-0002", ubicacion="Bogotá, Cundinamarca, Colombia")
    _instalar_servidor(
        monkeypatch, [[(404, ""), (404, "")], [(200, HTML_COMPLETO)]]
    )
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


def test_m2_no_sobreescribe_modalidad_de_m1(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La modalidad no se toca; la ubicación se actualiza con el texto de la página."""
    _sembrar_catalogo()
    _insertar_oferta(
        "OFE-0001",
        ubicacion="Medellín, Antioquia, Colombia",
        modalidad="hibrido",
    )
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])

    resultado = ejecutar_preparacion(_contexto())

    assert resultado.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["estado"] == "preparada"
    # La página manda en ubicacion
    assert fila["ubicacion"] == "Bogotá, Distrito Capital, Colombia"
    # Modalidad no se toca
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
            titulo_h1="T", descripcion="", empresa_nombre="", empresa_perfil="",
            ubicacion_pagina="",
        ),
    )
    monkeypatch.setattr(preparacion, "_diligenciar_empresa", lambda ctx, n, p: "EMP-0001")
    monkeypatch.setattr(preparacion, "_diligenciar_ubicacion", lambda ctx, t: "UBI-0001")

    config = dict(CONFIG_RAPIDO)
    config["pausa_entre_ofertas_segundos"] = 2.0
    config["pausa_jitter_segundos"] = 0.5
    contexto = _contexto(config)
    lote = [{"id": f"OFE-{i:04d}", "enlace": f"https://x/{i}"} for i in range(3)]

    ok = preparacion._procesar_lote(contexto, lote)

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
            titulo_h1="T", descripcion="", empresa_nombre="", empresa_perfil="",
            ubicacion_pagina="",
        ),
    )
    monkeypatch.setattr(preparacion, "_diligenciar_empresa", lambda ctx, n, p: "EMP-0001")
    monkeypatch.setattr(preparacion, "_diligenciar_ubicacion", lambda ctx, t: "UBI-0001")

    config = dict(CONFIG_RAPIDO)
    config["pausa_entre_ofertas_segundos"] = 3.0
    contexto = _contexto(config)
    lote = [{"id": f"OFE-{i:04d}", "enlace": f"https://x/{i}"} for i in range(2)]
    assert preparacion._procesar_lote(contexto, lote) is True
    assert llamadas_uniform == []  # jitter ausente => pausa fija
    assert dormidos == [3.0]


# -------------------------------------------------- Cascada IA en ubicación


def test_ia_resuelve_municipio_existente_con_dept_distinto(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AI resolves an existing municipality with different dept — no new row."""
    ids = _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Algo desconocido")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)]])

    def falso_ia(
        prompt_id: str, datos: dict[str, str], modelo: str, clave: str,
        *, timeout: float | None = None,
    ) -> dict[str, str]:
        return {"municipio": "Medellín", "departamento": "Santander", "pais": "Colombia"}

    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_ia)

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["ubicacion_id"] == ids["medellín/antioquia"]
    # No se creó fila nueva
    assert len(leer_tabla("ubicaciones", {})) == 5


def test_segunda_oferta_mismo_municipio_desconocido_reutiliza_fila(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second offer with same unknown municipality reuses the created row."""
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Cota")
    _insertar_oferta("OFE-0002", ubicacion="Cota")
    _instalar_servidor(
        monkeypatch, [[(200, HTML_SIN_UBICACION)], [(200, HTML_SIN_UBICACION)]]
    )

    def falso_ia(
        prompt_id: str, datos: dict[str, str], modelo: str, clave: str,
        *, timeout: float | None = None,
    ) -> dict[str, str]:
        return {"municipio": "Cota", "departamento": "Cundinamarca", "pais": "Colombia"}

    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_ia)

    ejecutar_preparacion(_contexto())

    fila1 = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    fila2 = buscar_por_id("ofertas_descubiertas", "OFE-0002")
    assert fila1 is not None and fila2 is not None
    assert fila1["ubicacion_id"] == fila2["ubicacion_id"]
    # Solo una fila creada (la de init_db ya existe con origen sistema)
    creadas = leer_tabla("ubicaciones", {"origen": "sistema"})
    assert len(creadas) == 2


def test_ia_caida_usa_departamento_del_texto(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When AI is down, departamento_en_texto fallback is used."""
    ids = _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Algo, Antioquia")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)]])

    def falso_ia(
        prompt_id: str, datos: dict[str, str], modelo: str, clave: str,
        *, timeout: float | None = None,
    ) -> dict[str, str]:
        raise Exception("quota exceeded")

    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_ia)

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["ubicacion_id"] == ids["N/A/antioquia"]


def test_ia_caida_sin_departamento_usa_fila_pais(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When AI is down and no department in text, country row is used."""
    ids = _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Algo desconocido")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)]])

    def falso_ia(
        prompt_id: str, datos: dict[str, str], modelo: str, clave: str,
        *, timeout: float | None = None,
    ) -> dict[str, str]:
        raise Exception("quota exceeded")

    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_ia)

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["ubicacion_id"] == ids["N/A/N/A"]


def test_ia_responde_todo_na_usa_fila_pais(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When AI returns all N/A, country row fallback is used."""
    ids = _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Algo desconocido")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)]])

    def falso_ia(
        prompt_id: str, datos: dict[str, str], modelo: str, clave: str,
        *, timeout: float | None = None,
    ) -> dict[str, str]:
        return {"municipio": "N/A", "departamento": "N/A", "pais": "N/A"}

    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_ia)

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["ubicacion_id"] == ids["N/A/N/A"]


def test_ia_municipio_existente_ambiguo_no_crea_fila(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AI with existing but ambiguous municipality doesn't create, uses country."""
    import sqlite3

    from shared.persistence._migraciones import INDICE_UBICACIONES_UNICA

    ids = _sembrar_catalogo()
    # Legacy catalogue without the D82 guard: seed two identical Granada rows
    # so the municipality is ambiguous (a guarded catalogue cannot hold them).
    conn = sqlite3.connect(str(temp_db_file))
    try:
        conn.execute(f"DROP INDEX {INDICE_UBICACIONES_UNICA}")
        conn.commit()
    finally:
        conn.close()
    escribir_fila(
        "ubicaciones",
        {"municipio": "Granada", "departamento": "Antioquia", "pais": "Colombia"},
    )
    escribir_fila(
        "ubicaciones",
        {"municipio": "Granada", "departamento": "Antioquia", "pais": "Colombia"},
    )
    _insertar_oferta("OFE-0001", ubicacion="Algo desconocido")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)]])

    def falso_ia(
        prompt_id: str, datos: dict[str, str], modelo: str, clave: str,
        *, timeout: float | None = None,
    ) -> dict[str, str]:
        return {"municipio": "Granada", "departamento": "Antioquia", "pais": "Colombia"}

    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_ia)

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["ubicacion_id"] == ids["N/A/N/A"]
    # No se creó fila nueva: 4 sembradas + 1 init_db + 2 granada = 7
    assert len(leer_tabla("ubicaciones", {})) == 7


# -------------------------------------------------- Ubicación de página


def test_extraccion_con_span_ubicacion(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Page location span is extracted and saved to the offer."""
    ids = _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Bogotá")
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["ubicacion"] == "Bogotá, Distrito Capital, Colombia"
    # Enlace a Bogotá por deduplicación de segmentos
    assert fila["ubicacion_id"] == ids["bogotá/cundinamarca"]


def test_extraccion_sin_span_ubicacion_conserva_tarjeta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When page has no location span, the card value is preserved."""
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Medellín, Antioquia, Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)]])

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["ubicacion"] == "Medellín, Antioquia, Colombia"


def test_nodo_usa_texto_pagina_por_encima_guardado(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The node uses page location text for resolution, not the card value."""
    ids = _sembrar_catalogo()
    # Card says Medellín, page says "Bogotá, Distrito Capital, Colombia"
    # The page text is used for resolution → Bogotá by dedup
    _insertar_oferta("OFE-0001", ubicacion="Medellín, Antioquia, Colombia")
    _instalar_servidor(monkeypatch, [[(200, HTML_COMPLETO)]])

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    # Page text is used, not card text — links to Bogotá
    assert fila["ubicacion_id"] == ids["bogotá/cundinamarca"]
    # If card text were used, it would be Medellín
    assert fila["ubicacion_id"] != ids["medellín/antioquia"]


def test_area_metropolitana_enlaza_a_su_ciudad(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metropolitan area text resolves to its city without creating a row."""
    ids = _sembrar_catalogo()
    _insertar_oferta(
        "OFE-0001", ubicacion="Área metropolitana de Medellín"
    )
    # HTML with metropolitan area in the span
    html_am = HTML_COMPLETO.replace(
        "Bogotá, Distrito Capital, Colombia",
        "Área metropolitana de Medellín",
    )
    _instalar_servidor(monkeypatch, [[(200, html_am)]])

    llamar_ia: list[str] = []
    def espia_ia(*a: Any, **k: Any) -> dict[str, str]:
        llamar_ia.append("called")
        return {"municipio": "N/A", "departamento": "N/A", "pais": "N/A"}

    monkeypatch.setattr(preparacion, "analyze_openrouter", espia_ia)

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    # "Área metropolitana de Medellín" → resolves to Medellín
    assert fila["ubicacion_id"] == ids["medellín/antioquia"]
    # Original text preserved in column
    assert "Área metropolitana de Medellín" in fila["ubicacion"]
    # No new catalogue row created
    assert len(leer_tabla("ubicaciones", {})) == 5
    # IA was NOT called (known AM resolves deterministically)
    assert llamar_ia == []


def test_area_metropolitana_desconocida_no_crea_fila(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown metropolitan area does not create a row; falls to country."""
    ids = _sembrar_catalogo()
    _insertar_oferta(
        "OFE-0001", ubicacion="Área metropolitana del Valle de Aburrá"
    )
    html_am = HTML_COMPLETO.replace(
        "Bogotá, Distrito Capital, Colombia",
        "Área metropolitana del Valle de Aburrá",
    )
    _instalar_servidor(monkeypatch, [[(200, html_am)]])

    llamar_ia: list[str] = []
    def espia_ia(*a: Any, **k: Any) -> dict[str, str]:
        llamar_ia.append("called")
        return {"municipio": "N/A", "departamento": "N/A", "pais": "N/A"}

    monkeypatch.setattr(preparacion, "analyze_openrouter", espia_ia)

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    # Falls to country row (paso 4 after AM skips 1-2)
    assert fila["ubicacion_id"] == ids["N/A/N/A"]
    # Original text preserved
    assert "Área metropolitana del Valle de Aburrá" in fila["ubicacion"]
    # No new catalogue row created
    assert len(leer_tabla("ubicaciones", {})) == 5
    # IA was NOT called (AM skips steps 1-2)
    assert llamar_ia == []


def test_lugar_extranjero_ausente_crea_fila_propia(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Foreign place creates its own row, not linked to Italy row."""
    _sembrar_catalogo()
    # Seed a Milan/Italy row
    escribir_fila(
        "ubicaciones",
        {"municipio": "Milán", "departamento": "Lombardía", "pais": "Italia"},
    )
    _insertar_oferta("OFE-0001", ubicacion="Milán, Caquetá, Colombia")
    html_milan = HTML_COMPLETO.replace(
        "Bogotá, Distrito Capital, Colombia",
        "Milán, Caquetá, Colombia",
    )
    _instalar_servidor(monkeypatch, [[(200, html_milan)]])

    def falso_ia(
        prompt_id: str, datos: dict[str, str], modelo: str, clave: str,
        *, timeout: float | None = None,
    ) -> dict[str, str]:
        return {"municipio": "Milán", "departamento": "Caquetá", "pais": "Colombia"}

    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_ia)

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    # New row created: milan/caqueta/colombia (not the Italy row)
    nuevas = leer_tabla("ubicaciones", {
        "municipio": "milan", "departamento": "caqueta", "pais": "colombia"
    })
    assert len(nuevas) == 1
    assert nuevas[0]["origen"] == "sistema"
    assert fila["ubicacion_id"] == nuevas[0]["id"]
    # Catalogue grew: 4 sembradas + 1 init_db + 1 milan/italia + 1 creada = 7
    assert len(leer_tabla("ubicaciones", {})) == 7


def test_ubicacion_nombre_oficial_largo_enlaza_municipio_catalogo(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """San José de Cúcuta (official long name) links to Cúcuta catalogue row."""
    _sembrar_catalogo()
    # Seed Cúcuta / Norte de Santander / Colombia
    cucuta_id = escribir_fila(
        "ubicaciones",
        {"municipio": "Cúcuta", "departamento": "Norte de Santander", "pais": "Colombia"},
    )
    _insertar_oferta("OFE-0001", ubicacion="San Jose de Cucuta, Norte de Santander, Colombia")
    html = HTML_COMPLETO.replace(
        "Bogotá, Distrito Capital, Colombia",
        "San Jose de Cucuta, Norte de Santander, Colombia",
    )
    _instalar_servidor(monkeypatch, [[(200, html)]])

    llamar_ia: list[str] = []
    def espia_ia(*a: Any, **k: Any) -> dict[str, str]:
        llamar_ia.append("called")
        return {"municipio": "N/A", "departamento": "N/A", "pais": "N/A"}

    monkeypatch.setattr(preparacion, "analyze_openrouter", espia_ia)

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["estado"] == "preparada"
    assert fila["ubicacion_id"] == cucuta_id
    assert fila["ubicacion"] == "San Jose de Cucuta, Norte de Santander, Colombia"
    # IA was NOT called (alias resolves deterministically)
    assert llamar_ia == []
    # 4 sembradas + 1 init_db + 1 Cúcuta = 6, no new rows
    assert len(leer_tabla("ubicaciones", {})) == 6


def test_ubicacion_localidad_distrito_capital_enlaza_bogota(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ciudad Bolívar is a Bogotá locality: link to Bogotá, no new row."""
    ids = _sembrar_catalogo()
    _insertar_oferta(
        "OFE-0001", ubicacion="Ciudad Bolivar, Distrito Capital, Colombia"
    )
    html = HTML_COMPLETO.replace(
        "Bogotá, Distrito Capital, Colombia",
        "Ciudad Bolivar, Distrito Capital, Colombia",
    )
    _instalar_servidor(monkeypatch, [[(200, html)]])

    llamar_ia: list[str] = []
    def espia_ia(*a: Any, **k: Any) -> dict[str, str]:
        llamar_ia.append("called")
        return {"municipio": "N/A", "departamento": "N/A", "pais": "N/A"}

    monkeypatch.setattr(preparacion, "analyze_openrouter", espia_ia)

    ejecutar_preparacion(_contexto())

    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["estado"] == "preparada"
    assert fila["ubicacion_id"] == ids["bogotá/cundinamarca"]
    assert fila["ubicacion"] == "Ciudad Bolivar, Distrito Capital, Colombia"
    # IA was NOT called (locality rule resolves deterministically)
    assert llamar_ia == []
    # No new catalogue row created
    assert len(leer_tabla("ubicaciones", {})) == 5


def test_creacion_fila_sistema_distinge_homonimos(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same municipality name in two departments gets two distinct rows."""
    _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Puerto Bogotá Norte")
    _insertar_oferta("OFE-0002", ubicacion="Puerto Bogotá Sur")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)], [(200, HTML_SIN_UBICACION)]])

    respuestas = {
        "Puerto Bogotá Norte": {
            "municipio": "Puerto Bogotá", "departamento": "Caquetá", "pais": "Colombia",
        },
        "Puerto Bogotá Sur": {
            "municipio": "Puerto Bogotá", "departamento": "Cauca", "pais": "Colombia",
        },
    }

    def falso_ia(
        prompt_id: str, datos: dict[str, str], modelo: str, clave: str,
        *, timeout: float | None = None,
    ) -> dict[str, str]:
        return respuestas[datos["texto_ubicacion"]]

    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_ia)
    ejecutar_preparacion(_contexto())

    creadas = leer_tabla("ubicaciones", {
        "origen": "sistema", "municipio": "puerto bogota"
    })
    assert len(creadas) == 2
    assert {fila["departamento"] for fila in creadas} == {"caqueta", "cauca"}
    for oferta_id, departamento in (("OFE-0001", "caqueta"), ("OFE-0002", "cauca")):
        oferta = buscar_por_id("ofertas_descubiertas", oferta_id)
        assert oferta is not None
        enlace = next(f for f in creadas if f["departamento"] == departamento)
        assert oferta["ubicacion_id"] == enlace["id"]


def test_ia_pais_alias_enlaza_fila_existente_sin_duplicar(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """'CO' as the AI country still links the existing Medellín row."""
    ids = _sembrar_catalogo()
    _insertar_oferta("OFE-0001", ubicacion="Puerto Bogotá")
    _instalar_servidor(monkeypatch, [[(200, HTML_SIN_UBICACION)]])

    def falso_ia(
        prompt_id: str, datos: dict[str, str], modelo: str, clave: str,
        *, timeout: float | None = None,
    ) -> dict[str, str]:
        return {"municipio": "Medellín", "departamento": "Antioquia", "pais": "CO"}

    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_ia)
    ejecutar_preparacion(_contexto())

    oferta = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert oferta is not None
    assert oferta["ubicacion_id"] == ids["medellín/antioquia"]
    assert leer_tabla("ubicaciones", {
        "origen": "sistema", "municipio": "medellin"
    }) == []
