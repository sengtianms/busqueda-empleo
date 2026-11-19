"""Pruebas de las dos entradas del Módulo 3 (Fase 3, D76)."""

import json
from pathlib import Path
from typing import Any

import pytest

from modules.evaluation import orchestrator_manual
from modules.evaluation.nodes.exportacion import ResultadoExportacion
from modules.evaluation.nodes.inicio_manual import (
    ResultadoDecisionManual,
    ResultadoInicioManual,
)
from modules.evaluation.orchestrator_manual import (
    ejecutar_flujo_exportacion,
    ejecutar_flujo_importacion,
)
from shared.persistence import (
    adquirir_bloqueo,
    escribir_fila,
    leer_tabla,
    registrar_corrida,
)
from shared.utilidades import ahora


def _config(base: Path) -> dict[str, Any]:
    return {
        "evaluacion_manual": {
            "carpeta_base": str(base),
            "tamano_lote": 2,
            "modelo_evaluador": "chat: gemini",
            "retries": {
                "max_attempts": 2,
                "base_wait_seconds": 0,
                "max_wait_seconds": 0,
                "multiplier": 1,
            },
        }
    }


def _insertar(identificador: str) -> None:
    escribir_fila(
        "ofertas_descubiertas",
        {
            "id": identificador,
            "enlace": f"https://example.com/{identificador}",
            "titulo": f"Oferta {identificador}",
            "descripcion_original": "Responsabilidades: dirigir la operación.",
            "fecha_descubrimiento": ahora(),
            "estado": "preparada",
        },
    )


def _oferta(identificador: str) -> dict[str, Any]:
    return next(f for f in leer_tabla("ofertas_descubiertas") if f["id"] == identificador)


def _corridas() -> list[dict[str, Any]]:
    return sorted(leer_tabla("corridas"), key=lambda fila: fila["id_corrida"])


def _eventos(identificador: str) -> list[dict[str, Any]]:
    return [e for e in leer_tabla("eventos") if e["id_corrida"] == identificador]


def _linea(identificador: str) -> str:
    return json.dumps(
        {
            "id": identificador,
            "entregable_principal": "Plan de operaciones",
            "v1": "PASS",
            "v2": "PASS",
            "v3": "PASS",
            "v4": "PASS",
            "v5": "PASS",
            "decision": "APROBADA",
            "justificacion": "Solicita dirigir la operación y presentar planes.",
        },
        ensure_ascii=False,
    )


def _exportar(tmp_path: Path, cantidad: int = 3) -> tuple[Path, str]:
    base = tmp_path / "manual"
    for numero in range(1, cantidad + 1):
        _insertar(f"OFE-{numero:04d}")
    resultado = ejecutar_flujo_exportacion(_config(base))
    assert resultado is not None
    corrida = next(
        e["id_corrida"]
        for e in leer_tabla("eventos")
        if e["codigo"] == "ofertas_exportadas"
    )
    return base, corrida


# ------------------------------------------------------------- Exportación


def test_flujo_exportacion_cierra_evaluacion_pendiente(tmp_path: Path) -> None:
    base = tmp_path / "manual"
    for numero in range(1, 4):
        _insertar(f"OFE-{numero:04d}")
    resultado = ejecutar_flujo_exportacion(_config(base))
    assert resultado is not None
    assert resultado.codigo == "evaluacion_pendiente"
    assert resultado.informe["exportadas"] == 3
    fila = _corridas()[0]
    assert fila["estado"] == "completada"
    assert fila["total_ofertas"] == 3
    assert fila["motivo_terminacion"] == "evaluacion_pendiente"
    assert leer_tabla("bloqueo") == []
    assert len(list((base / "lotes").glob("*.md"))) == 2


def test_flujo_exportacion_sin_ofertas_cierra_sin_pendientes(tmp_path: Path) -> None:
    resultado = ejecutar_flujo_exportacion(_config(tmp_path / "manual"))
    assert resultado is not None
    assert resultado.codigo == "sin_pendientes"
    assert _corridas()[0]["estado"] == "sin_pendientes"
    assert leer_tabla("bloqueo") == []


# ------------------------------------------------------------- Importación


def test_flujo_importacion_cierra_completada(tmp_path: Path) -> None:
    base, corrida_export = _exportar(tmp_path)
    ficha = json.loads(
        (base / "lotes" / f"{corrida_export}_lote_001.json").read_text(
            encoding="utf-8"
        )
    )
    (base / "resultados" / f"{corrida_export}_lote_001.jsonl").write_text(
        "\n".join(_linea(i) for i in ficha["ids"]) + "\n", encoding="utf-8"
    )
    resultado = ejecutar_flujo_importacion(_config(base))
    assert resultado is not None
    assert resultado.codigo == "corrida_completada"
    assert resultado.informe["aprobadas"] == 2
    assert resultado.informe["lotes_cerrados"] == [f"{corrida_export}_lote_001"]
    fila = next(f for f in _corridas() if f["motivo_terminacion"] == "corrida_completada")
    assert fila["total_aprobadas"] == 2
    assert fila["total_ofertas"] == 2
    assert _oferta(ficha["ids"][0])["estado"] == "aceptada_ei"
    assert leer_tabla("bloqueo") == []


def test_flujo_importacion_sin_resultados(tmp_path: Path) -> None:
    base = tmp_path / "manual"
    (base / "resultados").mkdir(parents=True, exist_ok=True)
    resultado = ejecutar_flujo_importacion(_config(base))
    assert resultado is not None
    assert resultado.codigo == "sin_resultados"
    assert _corridas()[0]["estado"] == "sin_pendientes"


# ------------------------------------------------------------ Enrutado


def test_inicio_error_con_id_cierra_como_critico(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def inicio_error(*_args: Any, **_kwargs: Any) -> ResultadoInicioManual:
        return ResultadoInicioManual(
            estado="error",
            id_corrida="COR-0100",
            codigo="ERR-02",
            descripcion="config ausente",
        )

    monkeypatch.setattr(orchestrator_manual, "ejecutar_inicio_exportacion", inicio_error)
    registrar_corrida(
        {"id_corrida": "COR-0100", "fecha_inicio": ahora(), "estado": "en_ejecucion"}
    )
    cierre = ejecutar_flujo_exportacion(_config(tmp_path / "manual"))
    assert cierre is not None and cierre.codigo == "error_critico"
    fila = next(f for f in _corridas() if f["id_corrida"] == "COR-0100")
    assert fila["estado"] == "abortada"
    assert fila["motivo_terminacion"] == "error_critico"
    assert [e["codigo"] for e in _eventos("COR-0100")] == ["error_critico"]


def test_inicio_error_sin_id_no_cierra_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def inicio_error(*_args: Any, **_kwargs: Any) -> ResultadoInicioManual:
        return ResultadoInicioManual(
            estado="error", codigo="ERR-01", descripcion="sin id"
        )

    monkeypatch.setattr(orchestrator_manual, "ejecutar_inicio_exportacion", inicio_error)
    assert ejecutar_flujo_exportacion(_config(tmp_path / "manual")) is None
    assert leer_tabla("corridas") == []
    assert leer_tabla("eventos") == []


def test_concurrencia_cierra_sin_tocar_el_bloqueo_ajeno(tmp_path: Path) -> None:
    adquirir_bloqueo("COR-9999", ahora())
    cierre = ejecutar_flujo_exportacion(_config(tmp_path / "manual"))
    assert cierre is not None and cierre.codigo == "concurrencia"
    assert [f["id_corrida"] for f in leer_tabla("bloqueo")] == ["COR-9999"]
    fila = next(f for f in _corridas() if f["id_corrida"] != "COR-9999")
    assert fila["estado"] == "abortada"
    assert fila["motivo_terminacion"] == "concurrencia"


@pytest.mark.parametrize(
    "codigo,motivo",
    [("ERR-01", "error_critico"), ("ERR-06", "aborto")],
)
def test_nodo_con_error_cierra_con_el_motivo_correspondiente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, codigo: str, motivo: str
) -> None:
    def nodo_error(*_args: Any, **_kwargs: Any) -> ResultadoExportacion:
        return ResultadoExportacion(estado="error", codigo=codigo, descripcion="fallo")

    monkeypatch.setattr(orchestrator_manual, "ejecutar_exportacion", nodo_error)
    for numero in range(1, 3):
        _insertar(f"OFE-{numero:04d}")
    cierre = ejecutar_flujo_exportacion(_config(tmp_path / "manual"))
    assert cierre is not None and cierre.codigo == motivo
    assert _corridas()[0]["motivo_terminacion"] == motivo
    assert leer_tabla("bloqueo") == []


def test_nodo_con_excepcion_cierra_aborto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def nodo_explota(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("fallo inesperado")

    monkeypatch.setattr(orchestrator_manual, "ejecutar_exportacion", nodo_explota)
    _insertar("OFE-0001")
    cierre = ejecutar_flujo_exportacion(_config(tmp_path / "manual"))
    assert cierre is not None and cierre.codigo == "aborto"
    assert _corridas()[0]["motivo_terminacion"] == "aborto"


def test_decision_con_error_cierra_error_critico(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def decision_error(*_args: Any, **_kwargs: Any) -> ResultadoDecisionManual:
        return ResultadoDecisionManual(
            estado="error", codigo="ERR-01", descripcion="contexto roto"
        )

    monkeypatch.setattr(orchestrator_manual, "hay_ofertas_preparadas", decision_error)
    _insertar("OFE-0001")
    cierre = ejecutar_flujo_exportacion(_config(tmp_path / "manual"))
    assert cierre is not None and cierre.codigo == "error_critico"
    assert _corridas()[0]["motivo_terminacion"] == "error_critico"
