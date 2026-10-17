"""Unit tests for the Evaluation Finalizar Proceso (Phase 6.3).

Metrics come from events (DISTINCT `id_oferta` per success code); the
official M3 motive/state table includes `cupo_agotado` and `concurrencia`.
"""

from pathlib import Path
from typing import Any

from modules.evaluation.nodes.finalizar import finalizar_proceso
from modules.evaluation.run_context import RunContext
from shared.persistence import (
    adquirir_bloqueo,
    consultar_bloqueo,
    escribir_evento,
    leer_tabla,
    registrar_corrida,
)


def _corrida(corrida_id: str) -> None:
    registrar_corrida(
        {"id_corrida": corrida_id, "fecha_inicio": "2026-10-15 10:00:00", "estado": "en_ejecucion"}
    )


def _evento(corrida_id: str, tipo: str, codigo: str, oferta: str = "N/A") -> None:
    escribir_evento(
        {
            "id_corrida": corrida_id,
            "tipo": tipo,
            "codigo": codigo,
            "evidencia": "prueba",
            "id_oferta": oferta,
        }
    )


def _fila(corrida_id: str) -> dict[str, Any]:
    filas = leer_tabla("corridas")
    return next(c for c in filas if c["id_corrida"] == corrida_id)


def test_metricas_por_eventos_sin_repetir(temp_db_file: Path) -> None:
    _corrida("COR-0001")
    _evento("COR-0001", "suceso", "oferta_aprobada", "OFE-0001")
    _evento("COR-0001", "suceso", "oferta_aprobada", "OFE-0001")  # doble emision
    _evento("COR-0001", "suceso", "oferta_descartada", "OFE-0002")
    _evento("COR-0001", "error", "evaluacion_fallida", "OFE-0003")
    ctx = RunContext(id_corrida="COR-0001", candidatas=[{"id": "x"}])
    res = finalizar_proceso(ctx)
    assert res.codigo == "corrida_completada"
    assert res.metricas is not None
    assert res.metricas["total_aprobadas"] == 1
    assert res.metricas["total_descartadas"] == 1
    assert res.metricas["total_ofertas"] == 2
    assert res.metricas["total_errores"] == 1
    # El evento de cierre no se cuenta en sucesos (D30).
    assert res.metricas["total_sucesos"] == 3
    fila = _fila("COR-0001")
    assert fila["estado"] == "completada"
    assert fila["motivo_terminacion"] == "corrida_completada"
    assert fila["total_aprobadas"] == 1
    assert fila["total_descartadas"] == 1


def test_sin_pendientes_prefijado(temp_db_file: Path) -> None:
    _corrida("COR-0001")
    ctx = RunContext(id_corrida="COR-0001", candidatas=[])
    ctx.motivo_cierre = "sin_pendientes"
    res = finalizar_proceso(ctx)
    assert res.codigo == "sin_pendientes"
    assert _fila("COR-0001")["estado"] == "sin_pendientes"


def test_cupo_agotado_cierra_completada_como_suceso(temp_db_file: Path) -> None:
    _corrida("COR-0001")
    _evento("COR-0001", "suceso", "oferta_aprobada", "OFE-0001")
    _evento("COR-0001", "error", "evaluacion_fallida", "OFE-0002")
    ctx = RunContext(id_corrida="COR-0001", candidatas=[{"id": "x"}])
    ctx.motivo_cierre = "cupo_agotado"
    res = finalizar_proceso(ctx)
    assert res.codigo == "cupo_agotado"
    assert _fila("COR-0001")["estado"] == "completada"
    cierres = [e for e in leer_tabla("eventos") if e["codigo"] == "cupo_agotado"]
    assert len(cierres) == 1
    assert cierres[0]["tipo"] == "suceso"


def test_error_total_sin_exitos(temp_db_file: Path) -> None:
    _corrida("COR-0001")
    _evento("COR-0001", "error", "evaluacion_fallida", "OFE-0001")
    ctx = RunContext(id_corrida="COR-0001", candidatas=[{"id": "OFE-0001"}])
    res = finalizar_proceso(ctx)
    assert res.codigo == "error_total"
    fila = _fila("COR-0001")
    assert fila["estado"] == "abortada"
    cierres = [e for e in leer_tabla("eventos") if e["codigo"] == "error_total"]
    assert cierres[0]["tipo"] == "error"


def test_concurrencia_no_toca_bloqueo_ajeno(temp_db_file: Path) -> None:
    adquirir_bloqueo("COR-AJENA", "2026-10-15 10:00:00")
    _corrida("COR-0001")
    res = finalizar_proceso(None, "concurrencia", "COR-0001")
    assert res.codigo == "concurrencia"
    assert _fila("COR-0001")["estado"] == "abortada"
    bloqueo = consultar_bloqueo()
    assert bloqueo is not None
    assert bloqueo["id_corrida"] == "COR-AJENA"


def test_motivo_explicito_gana_a_metricas(temp_db_file: Path) -> None:
    _corrida("COR-0001")
    _evento("COR-0001", "suceso", "oferta_aprobada", "OFE-0001")
    ctx = RunContext(id_corrida="COR-0001", candidatas=[{"id": "OFE-0001"}])
    res = finalizar_proceso(ctx, "aborto")
    assert res.codigo == "aborto"
    assert _fila("COR-0001")["estado"] == "abortada"
