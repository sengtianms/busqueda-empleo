"""Unit tests for the Evaluation INICIO + candidate decision (Phase 6.1)."""

from pathlib import Path
from typing import Any

from modules.evaluation.nodes.inicio import (
    ejecutar_inicio,
    hay_ofertas_por_procesar,
)
from modules.evaluation.run_context import RunContext
from shared.evaluacion import validar_evaluacion
from shared.persistence import (
    adquirir_bloqueo,
    consultar_bloqueo,
    escribir_fila,
    leer_tabla,
)
from shared.utilidades import ahora

EVALUACION_VALIDA: dict[str, Any] = {
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
}

CONFIG_BASE: dict[str, Any] = {
    "concurrencia": {"umbral_obsolescencia_minutos": 120},
    "evaluacion": EVALUACION_VALIDA,
    "ai_routing": {"evaluation": "cloud"},
    "ai_cloud": {"model": "gemma4:31b-cloud"},
}


def _insertar_oferta(oferta_id: str, fecha: str, estado: str = "preparada") -> None:
    escribir_fila(
        "ofertas_descubiertas",
        {
            "id": oferta_id,
            "enlace": f"https://www.linkedin.com/jobs/view/{oferta_id}",
            "titulo": f"Oferta {oferta_id}",
            "descripcion_original": "Descripcion de prueba.",
            "fecha_descubrimiento": fecha,
            "estado": estado,
        },
    )


# ---------------------------------------------------------------- Contexto


def test_contexto_defaults() -> None:
    ctx = RunContext()
    assert ctx.id_corrida.startswith("COR-")
    assert ctx.fecha_inicio
    assert ctx.config_evaluacion == {}
    assert ctx.candidatas == []
    assert ctx.hubo_candidatas is False
    assert ctx.contador_aprobadas == 0
    assert ctx.contador_descartadas == 0
    assert ctx.contador_errores == 0
    assert ctx.bloqueo_adquirido is False
    assert ctx.motivo_cierre is None
    assert ctx.motivo_marca_temporal is None


def test_contexto_con_candidatas_marca_hubo() -> None:
    ctx = RunContext(candidatas=[{"id": "OFE-0001"}])
    assert ctx.hubo_candidatas is True


# ---------------------------------------------------------------- INICIO ok


def test_validacion_acepta_la_configuracion_oficial() -> None:
    """Regression guard: the node must accept `config/config.yaml` verbatim
    (drift here means every real start aborts with ERR-04)."""
    from shared.config import load

    config = load()
    assert validar_evaluacion(config.get("evaluacion"), config) is None


def test_inicio_ok_sin_candidatas(temp_db_file: Path) -> None:
    res = ejecutar_inicio(dict(CONFIG_BASE))
    assert res.estado == "ok"
    assert res.id_corrida.startswith("COR-")
    ctx = res.contexto
    assert isinstance(ctx, RunContext)
    assert ctx.id_corrida == res.id_corrida
    assert ctx.bloqueo_adquirido is True
    assert ctx.hubo_candidatas is False
    assert ctx.candidatas == []
    assert ctx.config_evaluacion == EVALUACION_VALIDA
    filas = leer_tabla("corridas")
    fila = next(c for c in filas if c["id_corrida"] == res.id_corrida)
    assert fila["estado"] == "en_ejecucion"
    assert fila["fecha_inicio"] == ctx.fecha_inicio
    bloqueo = consultar_bloqueo()
    assert bloqueo is not None
    assert bloqueo["id_corrida"] == res.id_corrida


def test_inicio_carga_solo_preparadas_en_fifo(temp_db_file: Path) -> None:
    _insertar_oferta("OFE-0003", "2026-08-20 10:00:00")
    _insertar_oferta("OFE-0001", "2026-08-21 09:00:00")
    _insertar_oferta("OFE-0002", "2026-08-21 09:00:00")
    _insertar_oferta("OFE-0009", "2026-08-19 08:00:00", estado="descubierta")
    _insertar_oferta("OFE-0008", "2026-08-19 08:00:00", estado="duplicada")
    res = ejecutar_inicio(dict(CONFIG_BASE))
    assert res.estado == "ok"
    assert res.contexto is not None
    assert [c["id"] for c in res.contexto.candidatas] == [
        "OFE-0003",
        "OFE-0001",
        "OFE-0002",
    ]
    assert res.contexto.hubo_candidatas is True


# ---------------------------------------------------------------- INICIO errores


def test_inicio_config_invalida_aborta_con_id(temp_db_file: Path) -> None:
    config = {**CONFIG_BASE, "evaluacion": {**EVALUACION_VALIDA, "retries": {"max_attempts": 3}}}
    res = ejecutar_inicio(config)
    assert res.estado == "error"
    assert res.codigo == "ERR-04"
    assert res.id_corrida.startswith("COR-")


def test_inicio_sin_seccion_aborta(temp_db_file: Path) -> None:
    config = {k: v for k, v in CONFIG_BASE.items() if k != "evaluacion"}
    res = ejecutar_inicio(config)
    assert res.estado == "error"
    assert res.codigo == "ERR-04"


def test_inicio_concurrencia_activa(temp_db_file: Path) -> None:
    adquirir_bloqueo("COR-AJENA", ahora())
    res = ejecutar_inicio(dict(CONFIG_BASE))
    assert res.estado == "concurrencia"
    assert res.codigo == "ERR-06"
    assert res.id_corrida.startswith("COR-")
    # La fila propia existe para que Finalizar la cierre; el bloqueo ajeno sigue.
    filas = leer_tabla("corridas")
    assert any(c["id_corrida"] == res.id_corrida for c in filas)
    bloqueo = consultar_bloqueo()
    assert bloqueo is not None
    assert bloqueo["id_corrida"] == "COR-AJENA"


# ---------------------------------------------------------------- Decisión


def test_decision_si_con_candidatas() -> None:
    ctx = RunContext(id_corrida="COR-DECISION", candidatas=[{"id": "OFE-0001"}])
    res = hay_ofertas_por_procesar(ctx)
    assert res.estado == "ok"
    assert res.decision == "si"
    assert ctx.motivo_cierre is None


def test_decision_no_fija_sin_pendientes() -> None:
    ctx = RunContext(id_corrida="COR-DECISION", candidatas=[])
    res = hay_ofertas_por_procesar(ctx)
    assert res.estado == "ok"
    assert res.decision == "no"
    assert ctx.motivo_cierre == "sin_pendientes"
    assert ctx.motivo_marca_temporal


def test_decision_sin_contexto_es_error() -> None:
    res = hay_ofertas_por_procesar(None)
    assert res.estado == "error"
    assert res.codigo == "ERR-01"
