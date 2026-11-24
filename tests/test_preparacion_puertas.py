"""Unit tests for the location-classifier doors (decision D75).

Mirror of the evaluation's door-rotation tests (D59): a failed door is
marked down for the run and the next one answers at once; a malformed
ANSWER never silences a door; with every door down the cascade falls back
to department or country row. The `puerta_principal_activa` switch controls
whether the local door is included. AI is mocked by patching
`analyze`/`analyze_openrouter`; SQLite via the `temp_db_file` fixture.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

import modules.preparation.nodes.preparacion as preparacion
from modules.preparation.nodes.inicio import _validar_preparacion
from modules.preparation.nodes.preparacion import _clasificar_con_puertas
from modules.preparation.run_context import RunContext
from shared.errors import LLMError

CONFIG_PUERTAS: dict[str, Any] = {
    "umbral_titulo": 90,
    "umbral_descripcion": 85,
    "max_pasadas": 2,
    "pausa_entre_ofertas_segundos": 0,
    "limite_vida_sesion": 50,
    "retries": {
        "max_attempts": 3,
        "base_wait_seconds": 0,
        "max_wait_seconds": 0,
        "multiplier": 1,
    },
    "timeout_puerta_segundos": 60,
    "puerta_principal_activa": True,
    "puertas_alternas": [
        {
            "nombre": "openrouter-1",
            "modelo": "openai/gpt-oss-120b",
            "clave_ref": "OPENROUTER_API_KEY_1",
        },
        {
            "nombre": "openrouter-2",
            "modelo": "openai/gpt-oss-120b",
            "clave_ref": "OPENROUTER_API_KEY_2",
        },
    ],
}

RESPUESTA_BOGOTA = {
    "municipio": "Bogotá",
    "departamento": "Distrito Capital",
    "pais": "Colombia",
}


def _contexto() -> RunContext:
    return RunContext(
        config_preparacion=dict(CONFIG_PUERTAS),
        candidatas=[],
        id_corrida="COR-P75",
    )


@pytest.fixture
def mensajes_loguru() -> Generator[list[str], None, None]:
    """Captures Loguru messages (caplog only sees stdlib logging)."""
    from loguru import logger

    mensajes: list[str] = []
    handler_id = logger.add(mensajes.append, format="{message}", level="INFO")
    yield mensajes
    logger.remove(handler_id)


# ------------------------------------------------------- Rotación de puertas


def test_fallo_de_principal_rota_a_reserva_y_clasifica(
    monkeypatch: pytest.MonkeyPatch, mensajes_loguru: list[str]
) -> None:
    contexto = _contexto()
    llamadas: dict[str, Any] = {}

    def falso_analyze(
        prompt_id: str, datos: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        llamadas["principal"] = dict(kwargs)
        raise LLMError(
            "003", "local Ollama responded with code 402 | module: ia_service"
        )

    def falso_reserva(
        prompt_id: str,
        datos: dict[str, Any],
        modelo: str,
        clave: str,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        llamadas["reservas"] = [(modelo, clave, timeout)]
        return dict(RESPUESTA_BOGOTA)

    monkeypatch.setattr(preparacion, "analyze", falso_analyze)
    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_reserva)

    resultado = _clasificar_con_puertas(contexto, "Bogotá")

    assert resultado is not None
    assert (resultado.municipio, resultado.departamento, resultado.pais) == (
        "Bogotá",
        "Distrito Capital",
        "Colombia",
    )
    # La principal quedó marcada caída con su motivo; la reserva respondió.
    assert set(contexto.puertas_caidas) == {"principal"}
    assert llamadas["principal"]["purpose"] == "preparacion"
    # Fallo rápido (D59): el nodo pide la principal sin reintento propio.
    assert llamadas["principal"]["reintentar"] is False
    assert llamadas["principal"]["timeout"] == 60
    assert llamadas["reservas"][0][0] == "openai/gpt-oss-120b"
    assert llamadas["reservas"][0][1] == "OPENROUTER_API_KEY_1"
    assert llamadas["reservas"][0][2] == 60
    assert any(
        "puerta_descartada" in mensaje and "principal" in mensaje
        for mensaje in mensajes_loguru
    )


def test_puerta_caida_se_recuerda_en_las_siguientes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contexto = _contexto()
    conteo = {"principal": 0, "reservas": 0}

    def falso_analyze(*args: Any, **kwargs: Any) -> dict[str, Any]:
        conteo["principal"] += 1
        raise LLMError("003", "local Ollama responded with code 402")

    def falso_reserva(*args: Any, **kwargs: Any) -> dict[str, Any]:
        conteo["reservas"] += 1
        return dict(RESPUESTA_BOGOTA)

    monkeypatch.setattr(preparacion, "analyze", falso_analyze)
    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_reserva)

    assert _clasificar_con_puertas(contexto, "Bogotá") is not None
    assert _clasificar_con_puertas(contexto, "Medellín") is not None

    assert conteo["principal"] == 1  # la caída no se reintenta (D59)
    assert conteo["reservas"] == 2


def test_todas_las_puertas_caidas_devuelve_pendiente_sin_llamar(
    monkeypatch: pytest.MonkeyPatch, mensajes_loguru: list[str]
) -> None:
    contexto = _contexto()
    contexto.puertas_caidas.update(
        {"principal": "cupo", "openrouter-1": "cupo", "openrouter-2": "cupo"}
    )
    conteo = {"llamadas": 0}

    def falso(*args: Any, **kwargs: Any) -> dict[str, Any]:
        conteo["llamadas"] += 1
        return dict(RESPUESTA_BOGOTA)

    monkeypatch.setattr(preparacion, "analyze", falso)
    monkeypatch.setattr(preparacion, "analyze_openrouter", falso)

    assert _clasificar_con_puertas(contexto, "Bogotá") is None
    assert conteo["llamadas"] == 0  # deja de llamar: pendiente honesto
    assert any(
        "todas las puertas caidas" in mensaje for mensaje in mensajes_loguru
    )


# --------------------------------------- Respuesta mal formada: sin silenciar


def test_respuesta_no_json_queda_pendiente_sin_marcar_puerta(
    monkeypatch: pytest.MonkeyPatch, mensajes_loguru: list[str]
) -> None:
    contexto = _contexto()
    conteo = {"reservas": 0}

    def falso_analyze(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise LLMError("003", "Response is not valid JSON | module: ia_service")

    def falso_reserva(*args: Any, **kwargs: Any) -> dict[str, Any]:
        conteo["reservas"] += 1
        return dict(RESPUESTA_BOGOTA)

    monkeypatch.setattr(preparacion, "analyze", falso_analyze)
    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_reserva)

    assert _clasificar_con_puertas(contexto, "Home Office") is None
    # D75: una respuesta mal formada es contenido — no silencia la puerta ni
    # rota; la ubicación queda pendiente para el reintento propio.
    assert contexto.puertas_caidas == {}
    assert conteo["reservas"] == 0
    assert any("respuesta no JSON" in mensaje for mensaje in mensajes_loguru)


def test_respuesta_json_no_objeto_no_marca_puerta(
    monkeypatch: pytest.MonkeyPatch, mensajes_loguru: list[str]
) -> None:
    """JSON válido que no es objeto: el servicio lo rechaza con su mensaje
    004 — es contenido (D75), no infraestructura: la puerta queda viva."""
    contexto = _contexto()

    def falso_analyze(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise LLMError(
            "004", "Unexpected response format: expected a dictionary"
        )

    def falso_reserva(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("no debe rotar a la reserva")

    monkeypatch.setattr(preparacion, "analyze", falso_analyze)
    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_reserva)

    assert _clasificar_con_puertas(contexto, "Home Office") is None
    assert contexto.puertas_caidas == {}
    assert any("respuesta no JSON" in mensaje for mensaje in mensajes_loguru)


def test_respuesta_invalida_de_esquema_no_rota_ni_marca_puerta(
    monkeypatch: pytest.MonkeyPatch, mensajes_loguru: list[str]
) -> None:
    contexto = _contexto()
    conteo = {"reservas": 0}

    def falso_analyze(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"municipio": 123, "departamento": "Distrito", "pais": "Colombia"}

    def falso_reserva(*args: Any, **kwargs: Any) -> dict[str, Any]:
        conteo["reservas"] += 1
        return dict(RESPUESTA_BOGOTA)

    monkeypatch.setattr(preparacion, "analyze", falso_analyze)
    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_reserva)

    assert _clasificar_con_puertas(contexto, "Bogotá") is None
    assert contexto.puertas_caidas == {}
    assert conteo["reservas"] == 0
    assert any(
        "respuesta invalida de principal" in mensaje for mensaje in mensajes_loguru
    )


# --------------------------------------------------------- Validación (VAL-02)


def test_validacion_rechaza_seccion_sin_puertas() -> None:
    seccion = dict(CONFIG_PUERTAS)
    seccion.pop("puertas_alternas")
    assert _validar_preparacion(seccion) == (
        "puertas_alternas ausente (lista, vacia hasta la construccion)"
    )


def test_validacion_rechaza_puerta_sin_modelo() -> None:
    seccion = dict(CONFIG_PUERTAS)
    seccion["puertas_alternas"] = [{"nombre": "x", "clave_ref": "K"}]
    assert _validar_preparacion(seccion) == (
        "puertas_alternas invalida (cada puerta requiere 'modelo')"
    )


def test_validacion_rechaza_timeout_no_positivo() -> None:
    seccion = dict(CONFIG_PUERTAS)
    seccion["timeout_puerta_segundos"] = 0
    assert _validar_preparacion(seccion) == (
        "timeout_puerta_segundos invalido (numerico > 0)"
    )


def test_validacion_acepta_lista_vacia_solo_principal() -> None:
    seccion = dict(CONFIG_PUERTAS)
    seccion["puertas_alternas"] = []
    assert _validar_preparacion(seccion) is None


# ------------------------------------------------ Interruptor puerta principal


def test_puertas_con_interruptor_apagado_solo_alternas() -> None:
    """When puerta_principal_activa is False, only alternate doors are returned."""
    from modules.preparation.nodes.preparacion import _puertas_clasificacion

    seccion = dict(CONFIG_PUERTAS)
    seccion["puerta_principal_activa"] = False
    puertas = _puertas_clasificacion(seccion)
    nombres = [p["nombre"] for p in puertas]
    assert "principal" not in nombres
    assert "openrouter-1" in nombres


def test_validacion_rechaza_puerta_principal_no_booleana() -> None:
    """puerta_principal_activa must be boolean if present."""
    seccion = dict(CONFIG_PUERTAS)
    seccion["puerta_principal_activa"] = "false"
    assert _validar_preparacion(seccion) == (
        "puerta_principal_activa debe ser booleano (true/false)"
    )


def test_validacion_rechaza_principal_apagada_con_alternas_vacias() -> None:
    """puerta_principal_activa false requires at least one alternate door."""
    seccion = dict(CONFIG_PUERTAS)
    seccion["puerta_principal_activa"] = False
    seccion["puertas_alternas"] = []
    assert _validar_preparacion(seccion) == (
        "puerta_principal_activa false requiere al menos una puerta alterna"
    )


def test_validacion_acepta_principal_apagada_con_una_alternas() -> None:
    """puerta_principal_activa false with one alternate door is valid."""
    seccion = dict(CONFIG_PUERTAS)
    seccion["puerta_principal_activa"] = False
    seccion["puertas_alternas"] = [
        {
            "nombre": "openrouter-1",
            "modelo": "google/gemma-4-31b-it",
            "clave_ref": "OPENROUTER_API_KEY_1",
        }
    ]
    assert _validar_preparacion(seccion) is None


def test_reserva_crea_fila_con_componentes_normalizados(
    monkeypatch: pytest.MonkeyPatch, temp_db_file: Path
) -> None:
    """Reserve door creates a row with normalized components; second call caches."""
    from modules.preparation.nodes.preparacion import _diligenciar_ubicacion
    from modules.preparation.run_context import RunContext
    from modules.preparation.ubicaciones import CatalogoUbicaciones
    from shared.persistence import (
        change_path,
        escribir_fila,
        init_db,
        leer_tabla,
    )

    change_path(temp_db_file)
    init_db()
    escribir_fila(
        "ubicaciones",
        {"municipio": "N/A", "departamento": "N/A", "pais": "Colombia"},
    )
    # The triple-N/A "no aplica" row is already seeded by init_db(); the D82
    # unique guard rejects a second identical row.

    filas = leer_tabla("ubicaciones")
    catalogo = CatalogoUbicaciones(filas)

    seccion = dict(CONFIG_PUERTAS)
    seccion["puerta_principal_activa"] = False
    contexto = RunContext(
        config_preparacion=seccion, candidatas=[], id_corrida="COR-NORM"
    )
    contexto.catalogo_ubicaciones = catalogo

    llamadas_ia = {"count": 0}

    def falso_analyze(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise LLMError("003", "local Ollama responded with code 402")

    def falso_reserva(*args: Any, **kwargs: Any) -> dict[str, Any]:
        llamadas_ia["count"] += 1
        return {
            "municipio": "Cota",
            "departamento": "Cundinamarca",
            "pais": "Colombia",
        }

    monkeypatch.setattr(preparacion, "analyze", falso_analyze)
    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_reserva)

    texto = "Cota, Cundinamarca, Colombia"
    id_primero = _diligenciar_ubicacion(contexto, texto)
    id_segundo = _diligenciar_ubicacion(contexto, texto)

    assert id_primero == id_segundo
    assert llamadas_ia["count"] == 1
    assert contexto.cache_ia[texto] == ("Cota", "Cundinamarca", "Colombia")

    fila = leer_tabla("ubicaciones", {"id": id_primero})
    assert len(fila) == 1
    assert fila[0]["municipio"] == "cota"
    assert fila[0]["departamento"] == "cundinamarca"
    assert fila[0]["pais"] == "colombia"
    assert fila[0]["origen"] == "sistema"
