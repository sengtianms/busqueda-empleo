"""Unit tests for the location-classifier reserve doors (decision D75).

Mirror of the evaluation's door-rotation tests (D59): a failed door is
marked down for the run and the next one answers at once; a malformed
ANSWER never silences a door; with every door down the location stays
pending with one aggregated ERR-08. AI is mocked by patching
`analyze`/`analyze_openrouter`; SQLite via the `temp_db_file` fixture.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

import modules.preparation.nodes.preparacion as preparacion
from modules.preparation.nodes.inicio import _validar_preparacion
from modules.preparation.nodes.preparacion import (
    _clasificar_con_puertas,
    _diligenciar_ubicacion,
)
from modules.preparation.run_context import RunContext
from shared.errors import LLMError
from shared.persistence import buscar_por_id

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


# ------------------------------------------------------------ Flujo completo


def test_diligenciar_ubicacion_usa_reserva_y_cachea_el_exito(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contexto = _contexto()

    def falso_analyze(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise LLMError("003", "local Ollama responded with code 402")

    def falso_reserva(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return dict(RESPUESTA_BOGOTA)

    monkeypatch.setattr(preparacion, "analyze", falso_analyze)
    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_reserva)

    resultado = _diligenciar_ubicacion(contexto, "Bogotá")

    assert resultado == "UBI-0001"  # primera fila del catálogo
    fila = buscar_por_id("ubicaciones", "UBI-0001")
    assert fila is not None
    # VAL-04: la fila guarda los componentes normalizados.
    assert fila["municipio"] == "bogota"
    # RN-07: solo los éxitos se cachean; aquí hubo éxito por la reserva.
    assert contexto.cache_ia["Bogotá"] == ("Bogotá", "Distrito Capital", "Colombia")


def test_diligenciar_ubicacion_pendiente_no_se_cachea(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contexto = _contexto()

    def falso_analyze(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise LLMError("003", "local Ollama responded with code 402")

    def falso_reserva(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise LLMError("003", "openrouter-1 rejected the key (401)")

    monkeypatch.setattr(preparacion, "analyze", falso_analyze)
    monkeypatch.setattr(preparacion, "analyze_openrouter", falso_reserva)

    assert _diligenciar_ubicacion(contexto, "Bogotá") == "N/A"
    # RN-07: los fallos no se cachean; el lote (b)/la tanda siguiente reintenta.
    assert "Bogotá" not in contexto.cache_ia
    assert set(contexto.puertas_caidas) == {
        "principal",
        "openrouter-1",
        "openrouter-2",
    }


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
