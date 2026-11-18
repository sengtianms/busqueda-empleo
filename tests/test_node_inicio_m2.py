"""Unit tests for the Preparation INICIO + candidate decision (sub-phase 5.2)."""

import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from modules.preparation.nodes.inicio import (
    ejecutar_inicio,
    quedan_ofertas_por_preparar,
)
from modules.preparation.run_context import RunContext
from shared.errors import PersistenceError
from shared.persistence import (
    adquirir_bloqueo,
    consultar_bloqueo,
    escribir_fila,
    leer_tabla,
    liberar_bloqueo,
)

PREPARACION_VALIDA: dict[str, Any] = {
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
    "puertas_alternas": [
        {
            "nombre": "openrouter-1",
            "modelo": "openai/gpt-oss-120b",
            "clave_ref": "OPENROUTER_API_KEY_1",
        },
    ],
}

CONFIG_BASE: dict[str, Any] = {
    "concurrencia": {"umbral_obsolescencia_minutos": 120},
    "preparacion": PREPARACION_VALIDA,
}


def _marca(momento: datetime.datetime) -> str:
    return momento.strftime("%Y-%m-%d %H:%M:%S")


def _insertar_oferta(oferta_id: str, fecha: str, estado: str = "descubierta") -> None:
    escribir_fila(
        "ofertas_descubiertas",
        {
            "id": oferta_id,
            "enlace": f"https://www.linkedin.com/jobs/view/{oferta_id}",
            "fecha_descubrimiento": fecha,
            "estado": estado,
        },
    )


def _contexto_con(n: int) -> RunContext:
    return RunContext(
        id_corrida="COR-DECISION",
        candidatas=[{"id": f"OFE-{i:04d}"} for i in range(n)],
    )


# ---------------------------------------------------------------- INICIO ok


def test_validacion_acepta_la_seccion_oficial(temp_db_file: Path) -> None:
    """Regression guard: the node must accept `config/config.yaml` verbatim
    (fixture drift here means every real start aborts with ERR-04)."""
    from modules.preparation.nodes.inicio import _validar_preparacion
    from shared.config import load

    assert _validar_preparacion(load().get("preparacion")) is None


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
    assert ctx.config_preparacion == PREPARACION_VALIDA
    corridas = leer_tabla("corridas")
    fila = next(
        c for c in corridas if c["id_corrida"] == res.id_corrida
    )
    assert fila["estado"] == "en_ejecucion"
    # P2-A: una sola fuente de tiempo — la fila y el contexto comparten marca.
    assert fila["fecha_inicio"] == ctx.fecha_inicio
    bloqueo = consultar_bloqueo()
    assert bloqueo is not None
    assert bloqueo["id_corrida"] == res.id_corrida


def test_inicio_carga_candidatas_orden_fifo(temp_db_file: Path) -> None:
    _insertar_oferta("OFE-0003", "2026-08-20 10:00:00")
    _insertar_oferta("OFE-0001", "2026-08-21 09:00:00")
    _insertar_oferta("OFE-0002", "2026-08-21 09:00:00")
    _insertar_oferta("OFE-9999", "2026-08-19 08:00:00", estado="preparada")
    res = ejecutar_inicio(dict(CONFIG_BASE))
    assert res.estado == "ok"
    ctx = res.contexto
    assert ctx is not None
    assert [c["id"] for c in ctx.candidatas] == ["OFE-0003", "OFE-0001", "OFE-0002"]
    assert ctx.hubo_candidatas is True


# ------------------------------------------------------------- INICIO config


@pytest.mark.parametrize(
    "clave,valor",
    [
        ("umbral_titulo", 101),
        ("umbral_titulo", -1),
        ("umbral_descripcion", "alta"),
        ("max_pasadas", 0),
        ("pausa_entre_ofertas_segundos", -1),
        ("limite_vida_sesion", 0),
        (
            "retries",
            {
                "max_attempts": 0,
                "base_wait_seconds": 2,
                "max_wait_seconds": 30,
                "multiplier": 2,
            },
        ),
        (
            "retries",
            {
                "max_attempts": 3,
                "base_wait_seconds": 30,
                "max_wait_seconds": 2,
                "multiplier": 2,
            },
        ),
        (
            "retries",
            {
                "max_attempts": 3,
                "base_wait_seconds": 2,
                "max_wait_seconds": 30,
                "multiplier": 0.5,
            },
        ),
    ],
)
def test_inicio_fuera_de_rango_aborta(
    temp_db_file: Path, clave: str, valor: Any
) -> None:
    config = {**CONFIG_BASE, "preparacion": {**PREPARACION_VALIDA, clave: valor}}
    res = ejecutar_inicio(config)
    assert res.estado == "error"
    assert res.codigo == "ERR-04"
    assert leer_tabla("corridas") == []


def test_inicio_sin_seccion_preparacion_aborta(temp_db_file: Path) -> None:
    res = ejecutar_inicio({"concurrencia": {"umbral_obsolescencia_minutos": 120}})
    assert res.estado == "error"
    assert res.codigo == "ERR-04"


def test_inicio_config_ausente_aborta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _sin_archivo() -> dict[str, Any]:
        raise FileNotFoundError("config.yaml missing")

    monkeypatch.setattr("modules.preparation.nodes.inicio.load", _sin_archivo)
    res = ejecutar_inicio()
    assert res.estado == "error"
    assert res.codigo == "ERR-02"


def test_inicio_config_ilegible_aborta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _ilegible() -> dict[str, Any]:
        raise OSError("config.yaml unreadable")

    monkeypatch.setattr("modules.preparation.nodes.inicio.load", _ilegible)
    res = ejecutar_inicio()
    assert res.estado == "error"
    assert res.codigo == "ERR-03"


def test_inicio_config_corrupta_aborta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _corrupta() -> dict[str, Any]:
        raise yaml.YAMLError("bad yaml")

    monkeypatch.setattr("modules.preparation.nodes.inicio.load", _corrupta)
    res = ejecutar_inicio()
    assert res.estado == "error"
    assert res.codigo == "ERR-04"


# ------------------------------------------------------------------ INICIO BD


def test_inicio_bd_indisponible_aborta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom() -> None:
        raise PersistenceError("05", "database down")

    monkeypatch.setattr("modules.preparation.nodes.inicio.init_db", _boom)
    res = ejecutar_inicio(dict(CONFIG_BASE))
    assert res.estado == "error"
    assert res.codigo == "ERR-05"


def test_inicio_carga_candidatas_falla_aborta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom() -> list[dict[str, Any]]:
        raise PersistenceError("05", "candidate query down")

    monkeypatch.setattr(
        "modules.preparation.nodes.inicio.leer_candidatas_descubiertas", _boom
    )
    res = ejecutar_inicio(dict(CONFIG_BASE))
    assert res.estado == "error"
    assert res.codigo == "ERR-05"
    assert any(e["codigo"] == "ERR-05" for e in leer_tabla("eventos"))


# --------------------------------------------------------- INICIO concurrencia


def test_inicio_concurrencia_activa_terminacion_controlada(
    temp_db_file: Path,
) -> None:
    adquirir_bloqueo("COR-OTRA", _marca(datetime.datetime.now()))
    try:
        res = ejecutar_inicio(dict(CONFIG_BASE))
    finally:
        liberar_bloqueo("COR-OTRA")
    assert res.estado == "concurrencia"
    assert res.codigo == "ERR-06"
    # P2-A (sub-fase 5.5): la fila se registra antes del bloqueo, así que
    # la ruta concurrencia deja una corrida cerrable por Finalizar.
    corridas = leer_tabla("corridas")
    assert any(
        c["id_corrida"] == res.id_corrida and c["estado"] == "en_ejecucion"
        for c in corridas
    )
    eventos = leer_tabla("eventos")
    assert any(e["codigo"] == "ERR-06" and e["tipo"] == "suceso" for e in eventos)


def test_inicio_bloqueo_obsoleto_se_sobrescribe(temp_db_file: Path) -> None:
    viejo = datetime.datetime.now() - datetime.timedelta(minutes=300)
    adquirir_bloqueo("COR-VIEJA", _marca(viejo))
    try:
        res = ejecutar_inicio(dict(CONFIG_BASE))
        assert res.estado == "ok"
        bloqueo = consultar_bloqueo()
        assert bloqueo is not None
        assert bloqueo["id_corrida"] == res.id_corrida
        eventos = leer_tabla("eventos")
        assert any(e["codigo"] == "ERR-07" for e in eventos)
    finally:
        liberar_bloqueo(res.id_corrida)


def test_inicio_contienda_adquisicion_err06(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "modules.preparation.nodes.inicio.adquirir_bloqueo",
        lambda _run_id, _ts, forzar=False: False,
    )
    res = ejecutar_inicio(dict(CONFIG_BASE))
    assert res.estado == "concurrencia"
    assert res.codigo == "ERR-06"
    eventos = leer_tabla("eventos")
    assert any(e["codigo"] == "ERR-06" for e in eventos)


def test_inicio_timestamp_bloqueo_invalido_aborta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _bloqueo_invalido() -> dict[str, Any] | None:
        return {"id_corrida": "COR-ROTA", "marca_temporal": "no-es-fecha"}

    monkeypatch.setattr(
        "modules.preparation.nodes.inicio.consultar_bloqueo", _bloqueo_invalido
    )
    res = ejecutar_inicio(dict(CONFIG_BASE))
    assert res.estado == "error"
    assert res.codigo == "ERR-08"
    # P2-A: la fila ya existe (el registro precede al bloqueo).
    assert any(
        c["id_corrida"] == res.id_corrida for c in leer_tabla("corridas")
    )


def test_inicio_fallo_adquisicion_bloqueo_err08(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _estalla(_run_id: str, _ts: str, forzar: bool = False) -> bool:
        raise PersistenceError("08", "lock store down")

    monkeypatch.setattr(
        "modules.preparation.nodes.inicio.adquirir_bloqueo", _estalla
    )
    res = ejecutar_inicio(dict(CONFIG_BASE))
    assert res.estado == "error"
    assert res.codigo == "ERR-08"


def test_inicio_contienda_sobrescritura_obsoleta_err06(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    viejo = datetime.datetime.now() - datetime.timedelta(minutes=300)
    adquirir_bloqueo("COR-VIEJA", _marca(viejo))
    try:
        monkeypatch.setattr(
            "modules.preparation.nodes.inicio.adquirir_bloqueo",
            lambda _run_id, _ts, forzar=False: False,
        )
        res = ejecutar_inicio(dict(CONFIG_BASE))
        assert res.estado == "concurrencia"
        assert res.codigo == "ERR-06"
    finally:
        liberar_bloqueo("COR-VIEJA")


# ------------------------------------------------------- INICIO estado interno


def test_inicio_registro_corrida_falla_aborta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _estalla(_: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "modules.preparation.nodes.inicio.registrar_corrida", _estalla
    )
    res = ejecutar_inicio(dict(CONFIG_BASE))
    assert res.estado == "error"
    # El registro ocurre en el paso 3b (antes del bloqueo): su fallo es ERR-05.
    assert res.codigo == "ERR-05"
    assert leer_tabla("corridas") == []


def test_inicio_id_falla_dos_veces_aborta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _falla() -> str:
        raise PersistenceError("01", "id generation down")

    monkeypatch.setattr("modules.preparation.nodes.inicio.generar_id", _falla)
    res = ejecutar_inicio(dict(CONFIG_BASE))
    assert res.estado == "error"
    assert res.codigo == "ERR-01"


# ------------------------------------------------------- Decisión de candidatas


def test_decision_si_entrega_contrato_lista_no_vacia() -> None:
    ctx = _contexto_con(1)
    res = quedan_ofertas_por_preparar(ctx)
    assert res.estado == "ok"
    assert res.decision == "si"
    assert res.contexto is ctx
    assert ctx.motivo_cierre is None


def test_decision_no_fija_sin_pendientes_en_contexto(temp_db_file: Path) -> None:
    ctx = _contexto_con(0)
    res = quedan_ofertas_por_preparar(ctx)
    assert res.estado == "ok"
    assert res.decision == "no"
    assert res.contexto is ctx
    assert ctx.motivo_cierre == "sin_pendientes"
    assert ctx.motivo_marca_temporal
    assert len(ctx.motivo_marca_temporal) == len("YYYY-MM-DD HH:MM:SS")
    assert leer_tabla("eventos") == []


def test_decision_contexto_ausente_aborta() -> None:
    res = quedan_ofertas_por_preparar(None)
    assert res.estado == "error"
    assert res.codigo == "ERR-01"
    assert res.contexto is None


def test_decision_lista_inaccesible_aborta(temp_db_file: Path) -> None:
    ctx = RunContext(id_corrida="COR-ROTA")
    ctx.candidatas = object()  # type: ignore[assignment]
    res = quedan_ofertas_por_preparar(ctx)
    assert res.estado == "error"
    assert res.codigo == "ERR-01"
    eventos = leer_tabla("eventos")
    assert any(e["codigo"] == "ERR-01" for e in eventos)
