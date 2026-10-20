"""Tests for the preflight CLI (D42): environment checks before launching."""

from pathlib import Path
from typing import Any

from scripts.preflight import _check_bloqueo, _check_config, ejecutar_preflight

CONFIG_OK: dict[str, Any] = {
    "orquestador": {
        "modo_ejecucion": "serie",
        "modulos": ["descubrimiento", "preparacion"],
        "pausa_entre_modulos_segundos": 5,
    },
    "preparacion": {
        "umbral_titulo": 90,
        "umbral_descripcion": 85,
        "max_pasadas": 2,
        "pausa_entre_ofertas_segundos": 2,
        "limite_vida_sesion": 50,
        "retries": {
            "max_attempts": 3,
            "base_wait_seconds": 2,
            "max_wait_seconds": 30,
            "multiplier": 2,
        },
    },
    "concurrencia": {"umbral_obsolescencia_minutos": 120},
    "evaluacion": {
        "pausa_entre_ofertas_segundos": 1.2,
        "pausa_jitter_segundos": 0.4,
        "timeout_puerta_segundos": 60,
        "retries": {
            "max_attempts": 2,
            "base_wait_seconds": 2,
            "max_wait_seconds": 30,
            "multiplier": 2,
        },
        "puertas_alternas": [],
    },
    "ai_routing": {"evaluation": "cloud"},
    "ai_cloud": {"model": "gemma4:31b-cloud"},
}


def test_check_config_ok() -> None:
    resultados = _check_config(CONFIG_OK)
    assert all(ok for ok, _ in resultados), resultados


def test_check_config_invalida() -> None:
    rota = dict(CONFIG_OK)
    rota["preparacion"] = {"umbral_titulo": "alta"}
    resultados = _check_config(rota)
    fallas = [m for ok, m in resultados if not ok]
    assert len(fallas) == 1 and "preparacion" in fallas[0]


def test_check_bloqueo_libre(temp_db_file: Path) -> None:
    ok, mensaje = _check_bloqueo(CONFIG_OK)
    assert ok and "libre" in mensaje


def test_check_bloqueo_activo_reciente(temp_db_file: Path) -> None:
    from shared.persistence import _connection, adquirir_bloqueo

    assert adquirir_bloqueo("COR-0009", _ahora()) is True
    ok, mensaje = _check_bloqueo(CONFIG_OK)
    assert not ok and "COR-0009" in mensaje
    con = _connection()
    try:
        con.execute("DELETE FROM bloqueo")
        con.commit()
    finally:
        con.close()


def test_check_bloqueo_obsoleto(temp_db_file: Path) -> None:
    from shared.persistence import _connection, adquirir_bloqueo

    assert adquirir_bloqueo("COR-0008", _ahora()) is True
    con = _connection()
    try:
        con.execute(
            "UPDATE bloqueo SET marca_temporal = '2020-01-01 00:00:00'"
        )
        con.commit()
    finally:
        con.close()
    ok, mensaje = _check_bloqueo(CONFIG_OK)
    assert ok and "obsoleto" in mensaje


def test_ejecutar_preflight_camino_feliz(temp_db_file: Path) -> None:
    todo_ok, lineas = ejecutar_preflight(usar_ia=False)
    assert todo_ok is True
    assert any("base de datos escribible" in linea for linea in lineas)
    assert any("bloqueo libre" in linea for linea in lineas)


def _ahora() -> str:
    from datetime import datetime

    from shared.utilidades import FORMATO_TIMESTAMP

    return datetime.now().strftime(FORMATO_TIMESTAMP)
