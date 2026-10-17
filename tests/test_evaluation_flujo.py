"""Integration tests for the Module 3 flow orchestrator (Phase 6.3).

Real nodes over a temporary SQLite database; only the AI is replaced
(module boundary). Covers the happy path, the zero-candidates
short-circuit, the `concurrencia` route with a foreign lock intact and the
all-failures `error_total` close.
"""

from pathlib import Path
from typing import Any

import pytest

import modules.evaluation.nodes.evaluacion as evaluacion_mod
from modules.evaluation.orchestrator import ejecutar_flujo
from shared.persistence import (
    adquirir_bloqueo,
    buscar_por_id,
    consultar_bloqueo,
    escribir_fila,
    leer_tabla,
)
from shared.utilidades import ahora

EVALUACION: dict[str, Any] = {
    "pausa_entre_ofertas_segundos": 0,
    "pausa_jitter_segundos": 0,
    "retries": {
        "max_attempts": 2,
        "base_wait_seconds": 0,
        "max_wait_seconds": 0,
        "multiplier": 1,
    },
    "puertas_alternas": [],
}

CONFIG: dict[str, Any] = {
    "concurrencia": {"umbral_obsolescencia_minutos": 120},
    "evaluacion": EVALUACION,
    "ai_routing": {"evaluation": "cloud"},
    "ai_cloud": {"model": "gemma4:31b-cloud"},
}


def _sembrar(oferta_id: str, descripcion: str = "Descripcion valida de la oferta.") -> None:
    escribir_fila(
        "ofertas_descubiertas",
        {
            "id": oferta_id,
            "enlace": f"https://www.linkedin.com/jobs/view/{oferta_id}",
            "titulo": f"Oferta {oferta_id}",
            "descripcion_original": descripcion,
            "modalidad": "remoto",
            "ubicacion": "Colombia",
            "fecha_descubrimiento": "2026-10-15 10:00:00",
            "estado": "preparada",
        },
    )


def _respuesta(decision: str = "APROBADA") -> dict[str, str]:
    base = {"v1": "PASS", "v2": "PASS", "v3": "PASS", "v4": "PASS", "v5": "PASS"}
    if decision == "DESCARTADA":
        base["v2"] = "FAIL"
    return {**base, "decision": decision, "justificacion": "Rol compatible con el perfil"}


def _ultima_corrida() -> dict[str, Any]:
    filas = [c for c in leer_tabla("corridas") if c.get("fecha_fin")]
    assert filas
    return sorted(filas, key=lambda c: str(c["fecha_fin"]))[-1]


def test_flujo_completo_aprueba_y_descarta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar("OFE-0001")
    _sembrar("OFE-0002", descripcion="")
    llamadas = {"n": 0}

    def _ia(*a: Any, **k: Any) -> dict[str, str]:
        llamadas["n"] += 1
        return _respuesta("APROBADA")

    monkeypatch.setattr(evaluacion_mod, "analyze", _ia)
    ejecutar_flujo(dict(CONFIG))
    # OFE-0001 aprobada por la IA (1 llamada); OFE-0002 descartada por V3 sin IA.
    assert llamadas["n"] == 1
    fila1 = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila1 is not None and fila1["estado"] == "aceptada_ei"
    fila2 = buscar_por_id("ofertas_descubiertas", "OFE-0002")
    assert fila2 is not None and fila2["estado"] == "descartada_ei"
    corrida = _ultima_corrida()
    assert corrida["estado"] == "completada"
    assert corrida["motivo_terminacion"] == "corrida_completada"
    assert corrida["total_aprobadas"] == 1
    assert corrida["total_descartadas"] == 1
    assert consultar_bloqueo() is None


def test_flujo_sin_candidatas_cierra_sin_pendientes(temp_db_file: Path) -> None:
    ejecutar_flujo(dict(CONFIG))
    corrida = _ultima_corrida()
    assert corrida["estado"] == "sin_pendientes"
    assert corrida["motivo_terminacion"] == "sin_pendientes"
    assert consultar_bloqueo() is None


def test_flujo_concurrencia_con_bloqueo_ajeno(temp_db_file: Path) -> None:
    adquirir_bloqueo("COR-AJENA", ahora())
    ejecutar_flujo(dict(CONFIG))
    corrida = _ultima_corrida()
    assert corrida["motivo_terminacion"] == "concurrencia"
    bloqueo = consultar_bloqueo()
    assert bloqueo is not None
    assert bloqueo["id_corrida"] == "COR-AJENA"


def test_flujo_todo_falla_cierra_error_total(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shared.errors import LLMError

    _sembrar("OFE-0001")

    def _caida(*a: Any, **k: Any) -> dict[str, str]:
        raise LLMError("001", "puerta caida", source_module="ia_service")

    monkeypatch.setattr(evaluacion_mod, "analyze", _caida)
    ejecutar_flujo(dict(CONFIG))
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None and fila["estado"] == "preparada"
    corrida = _ultima_corrida()
    assert corrida["estado"] == "abortada"
    assert corrida["motivo_terminacion"] == "error_total"
    assert consultar_bloqueo() is None
