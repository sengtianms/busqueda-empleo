"""Tests for the preflight CLI (D42): environment checks before launching."""

import sqlite3
from pathlib import Path
from typing import Any

from scripts.preflight import (
    _check_bloqueo,
    _check_catalogo,
    _check_config,
    ejecutar_preflight,
)
from shared.persistence import escribir_fila

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
        "timeout_puerta_segundos": 60,
        "puertas_alternas": [],
    },
    "concurrencia": {"umbral_obsolescencia_minutos": 120},
    "evaluacion_manual": {
        "carpeta_base": "data/evaluacion_manual",
        "tamano_lote": 30,
        "modelo_evaluador": "chat: operador",
        "retries": {
            "max_attempts": 2,
            "base_wait_seconds": 2,
            "max_wait_seconds": 30,
            "multiplier": 2,
        },
    },
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
    # El prevuelo comprueba el catálogo (D83): la fila de país la pone el operador.
    escribir_fila(
        "ubicaciones",
        {"municipio": "N/A", "departamento": "N/A", "pais": "colombia"},
    )
    todo_ok, lineas = ejecutar_preflight()
    assert todo_ok is True
    assert any("base de datos escribible" in linea for linea in lineas)
    assert any("catalogo de ubicaciones: OK" in linea for linea in lineas)
    assert any("bloqueo libre" in linea for linea in lineas)
    assert any("evaluacion manual" in linea for linea in lineas)
    assert any("carpeta de trabajo evaluacion" in linea for linea in lineas)


def test_check_config_evaluacion_manual_invalida() -> None:
    rota = dict(CONFIG_OK)
    rota["evaluacion_manual"] = {**CONFIG_OK["evaluacion_manual"], "tamano_lote": 0}
    fallas = [mensaje for ok, mensaje in _check_config(rota) if not ok]
    assert len(fallas) == 1 and "evaluacion manual" in fallas[0]


def test_check_carpeta_evaluacion_no_disponible(tmp_path: Path) -> None:
    config = {
        **CONFIG_OK,
        "evaluacion_manual": {
            **CONFIG_OK["evaluacion_manual"],
            "carpeta_base": str(tmp_path / "sin_padre" / "manual"),
        },
    }
    fallas = [mensaje for ok, mensaje in _check_config(config) if not ok]
    assert any("carpeta de trabajo evaluacion" in falla for falla in fallas)


def _ahora() -> str:
    from datetime import datetime

    from shared.utilidades import FORMATO_TIMESTAMP

    return datetime.now().strftime(FORMATO_TIMESTAMP)


def _sembrar_catalogo_valido() -> None:
    escribir_fila(
        "ubicaciones",
        {"municipio": "N/A", "departamento": "N/A", "pais": "colombia"},
    )
    escribir_fila(
        "ubicaciones",
        {"municipio": "bogota", "departamento": "cundinamarca", "pais": "colombia"},
    )


def test_check_catalogo_valido(temp_db_file: Path) -> None:
    _sembrar_catalogo_valido()
    ok, mensaje = _check_catalogo(CONFIG_OK)
    assert ok is True
    assert "sin variantes" in mensaje


def test_check_catalogo_falta_fila_de_pais(temp_db_file: Path) -> None:
    ok, mensaje = _check_catalogo(CONFIG_OK)
    assert ok is False
    assert "filas de solo pais=0" in mensaje


def test_check_catalogo_dos_filas_de_pais(temp_db_file: Path) -> None:
    _sembrar_catalogo_valido()
    from shared.persistence._migraciones import INDICE_UBICACIONES_UNICA

    conn = sqlite3.connect(str(temp_db_file))
    try:
        conn.execute(f"DROP INDEX {INDICE_UBICACIONES_UNICA}")
        conn.commit()
    finally:
        conn.close()
    escribir_fila(
        "ubicaciones",
        {"municipio": "N/A", "departamento": "N/A", "pais": "ecuador"},
    )
    ok, mensaje = _check_catalogo(CONFIG_OK)
    assert ok is False
    assert "filas de solo pais=2" in mensaje


def test_check_catalogo_variantes_avisa(temp_db_file: Path) -> None:
    _sembrar_catalogo_valido()
    escribir_fila(
        "ubicaciones",
        {"municipio": "Bogotá", "departamento": "cundinamarca", "pais": "colombia"},
    )
    ok, mensaje = _check_catalogo(CONFIG_OK)
    assert ok is True
    assert "aviso" in mensaje and "variantes" in mensaje


def test_check_catalogo_no_aplica_sin_preparacion(temp_db_file: Path) -> None:
    config = dict(CONFIG_OK)
    config["orquestador"] = {
        **CONFIG_OK["orquestador"],
        "modulos": ["descubrimiento", "evaluacion"],
    }
    ok, mensaje = _check_catalogo(config)
    assert ok is True
    assert "no aplica" in mensaje
