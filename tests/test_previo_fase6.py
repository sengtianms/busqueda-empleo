"""Tests del Previo Fase 6 (D48): terreno del Módulo 3 sin activar nada nuevo."""

from pathlib import Path
from typing import Any

import pytest

from shared.evaluacion import validar_evaluacion
from shared.models import Corrida, Offer, OfferState
from shared.state_machine import possible_transitions, transition


def _seccion_ok() -> dict[str, Any]:
    return {
        "pausa_entre_ofertas_segundos": 1.2,
        "pausa_jitter_segundos": 0.4,
        "retries": {
            "max_attempts": 2,
            "base_wait_seconds": 2,
            "max_wait_seconds": 30,
            "multiplier": 2,
        },
        "puertas_alternas": [],
    }


def _config_ok() -> dict[str, Any]:
    return {
        "evaluacion": _seccion_ok(),
        "ai_routing": {"evaluation": "cloud"},
        "ai_cloud": {"model": "gemma4:31b-cloud"},
        "ai_local": {"model": "gpt-oss:120b-cloud"},
    }


def test_estados_nuevos_existen() -> None:
    assert OfferState.ACEPTADA_EI.value == "aceptada_ei"
    assert OfferState.DESCARTADA_EI.value == "descartada_ei"


def test_transicion_evaluada_a_aceptada_ei() -> None:
    assert transition(OfferState.EVALUADA, OfferState.ACEPTADA_EI) == OfferState.ACEPTADA_EI


def test_transicion_evaluada_a_descartada_ei() -> None:
    assert (
        transition(OfferState.EVALUADA, OfferState.DESCARTADA_EI)
        == OfferState.DESCARTADA_EI
    )


def test_transicion_directa_preparada_a_aceptada_ei_invalida() -> None:
    with pytest.raises(Exception):
        transition(OfferState.PREPARADA, OfferState.ACEPTADA_EI)


def test_posibles_desde_evaluada_incluyen_nuevos() -> None:
    posibles = possible_transitions(OfferState.EVALUADA)
    assert OfferState.ACEPTADA_EI in posibles
    assert OfferState.DESCARTADA_EI in posibles
    assert OfferState.ACEPTADA in posibles
    assert OfferState.DESCARTADA in posibles


def test_oferta_trae_resultado_pendiente_por_defecto() -> None:
    oferta = Offer(enlace="https://ejemplo.com/oferta", titulo="T", descripcion_original="D")
    assert oferta.resultado_evaluacion_inicial == "N/A"
    assert oferta.estado == OfferState.DESCUBIERTA


def test_corrida_trae_conteos_nuevos_en_cero() -> None:
    corrida = Corrida(id_corrida="COR-0001")
    assert corrida.total_aprobadas == 0
    assert corrida.total_descartadas == 0
    assert corrida.total_preparadas == 0


def test_migracion_crea_columnas_y_check(temp_db_file: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(str(temp_db_file))
    try:
        ofertas = {r[1] for r in conn.execute("PRAGMA table_info(ofertas_descubiertas)")}
        corridas = {r[1] for r in conn.execute("PRAGMA table_info(corridas)")}
        assert "resultado_evaluacion_inicial" in ofertas
        assert "total_aprobadas" in corridas
        assert "total_descartadas" in corridas
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'ofertas_descubiertas'"
        ).fetchone()[0]
        assert "aceptada_ei" in sql and "descartada_ei" in sql
    finally:
        conn.close()


def test_migracion_idempotente(temp_db_file: Path) -> None:
    from shared.persistence import init_db

    init_db()
    init_db()
    test_migracion_crea_columnas_y_check(temp_db_file)


def test_validador_acepta_configuracion_real() -> None:
    from shared import config as config_module

    config_module.reload_config()
    config = config_module.load()
    assert validar_evaluacion(config.get("evaluacion"), config) is None


def test_validador_acepta_seccion_minima() -> None:
    assert validar_evaluacion(_seccion_ok(), _config_ok()) is None


def test_validador_rechaza_seccion_ausente() -> None:
    assert validar_evaluacion(None, _config_ok()) is not None


def test_validador_rechaza_reintentos_distintos_de_dos() -> None:
    seccion = _seccion_ok()
    seccion["retries"] = dict(seccion["retries"], max_attempts=3)
    assert "max_attempts" in str(validar_evaluacion(seccion, _config_ok()))


def test_validador_rechaza_pausa_negativa() -> None:
    seccion = _seccion_ok()
    seccion["pausa_entre_ofertas_segundos"] = -1
    assert validar_evaluacion(seccion, _config_ok()) is not None


def test_validador_rechaza_puertas_no_lista() -> None:
    seccion = _seccion_ok()
    seccion["puertas_alternas"] = "llave"
    assert validar_evaluacion(seccion, _config_ok()) is not None


def test_validador_rechaza_ruta_ausente() -> None:
    config = _config_ok()
    del config["ai_routing"]
    assert validar_evaluacion(config["evaluacion"], config) is not None


def test_validador_rechaza_modelo_ausente() -> None:
    config = _config_ok()
    config["ai_cloud"] = {}
    assert validar_evaluacion(config["evaluacion"], config) is not None
