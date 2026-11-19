"""Previo Fase 6 y cierre del rediseño (D48, D76): terreno del Módulo 3.

Se conserva lo que sigue vigente —estados, transiciones, columnas y llaves
compartidas—. Las comprobaciones de la ruta de inteligencia artificial se
retiraron al cerrar la Fase 4, cuando el flujo antiguo dejó de existir.
"""

from pathlib import Path

import pytest

from shared.models import Corrida, Offer, OfferState
from shared.state_machine import possible_transitions, transition


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


def test_template_privado_reserva_las_tres_llaves() -> None:
    plantilla = Path("config/.env.template").read_text(encoding="utf-8")
    for i in (1, 2, 3):
        assert f"OPENROUTER_API_KEY_{i}=" in plantilla


def test_config_ya_no_declara_la_ruta_de_evaluacion_con_ia() -> None:
    from shared.config import load

    config = load()
    assert "evaluacion" not in config
    assert "evaluation" not in config["ai_routing"]


def test_herramienta_de_prompts_no_usa_la_ruta_retirada() -> None:
    from scripts.prompt_tester import PURPOSE
    from shared.config import load

    rutas = load()["ai_routing"]
    assert "evaluation" not in PURPOSE.values()
    assert all(proposito in rutas for proposito in PURPOSE.values())
