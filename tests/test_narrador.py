"""Tests del Lote 2 (narración en vivo): tics, narrador y métricas intactas."""

from typing import Any

import pytest

import shared.narrador as narrador
from scripts.estado_corrida import _analizar_evidencia


def _evento(
    id_corrida: str,
    tipo: str,
    codigo: str,
    evidencia: str,
    marca: str = "2026-10-22 17:00:00",
    *,
    indice_set: int | None = None,
    id_oferta: str = "N/A",
) -> None:
    from shared.persistence import escribir_evento

    datos: dict[str, Any] = {
        "id_corrida": id_corrida,
        "tipo": tipo,
        "codigo": codigo,
        "evidencia": evidencia,
        "marca_temporal": marca,
        "id_oferta": id_oferta,
    }
    if indice_set is not None:
        datos["indice_set"] = indice_set
    escribir_evento(datos)


# ---------------------------------------------------------------- narrador


def test_narracion_activa_para_manual_y_callada_en_tanda(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(narrador.MARCA_TANDA_PROGRAMADA, raising=False)
    assert narrador.narracion_activa() is True
    monkeypatch.setenv(narrador.MARCA_TANDA_PROGRAMADA, "1")
    assert narrador.narracion_activa() is False


def test_narrar_imprime_solo_en_manual(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(narrador.MARCA_TANDA_PROGRAMADA, raising=False)
    narrador.narrar("hola mundo")
    assert "hola mundo" in capsys.readouterr().out

    monkeypatch.setenv(narrador.MARCA_TANDA_PROGRAMADA, "1")
    narrador.narrar("esto no se imprime")
    captura = capsys.readouterr()
    assert "esto no se imprime" not in captura.out


def test_lineas_de_narracion_amables(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(narrador.MARCA_TANDA_PROGRAMADA, raising=False)
    narrador.narrar_modulo("preparacion")
    narrador.narrar_set(3)
    narrador.narrar_captura(2, 41)
    salido = capsys.readouterr().out
    assert "Módulo preparacion — preparación de ofertas" in salido
    assert "Búsqueda de filtros #3" in salido
    assert "página 2 — 41 ofertas" in salido


# ------------------------------------------------------ contador y métricas


def test_contar_narracion_solo_cuenta_tics_del_propio_corrida() -> None:
    _evento("COR-NAR", "suceso", "tic_modulo_iniciado", "modulo=preparacion")
    _evento("COR-NAR", "suceso", "tic_set_iniciado", "set=0", indice_set=0)
    _evento("COR-NAR", "suceso", "tic_captura_pagina", "set=0;pagina=1;acumuladas=7")
    _evento("COR-NAR", "suceso", "oferta_preparada", "ok", id_oferta="OFE-1")
    _evento("COR-NAR", "suceso", "ingreso_exitoso", "sesion=S")
    _evento("COR-NAR", "error", "ERR-13", "fallo")
    _evento("COR-NAR", "suceso", "tic_modulo_iniciado", "modulo=evaluacion")
    _evento("COR-NAR", "error", "tic_set_iniciado", "set=9", indice_set=9)
    _evento("COR-OTRO", "suceso", "tic_modulo_iniciado", "modulo=descubrimiento")

    from shared.persistence import CODIGOS_NARRACION, contar_narracion

    assert contar_narracion("COR-NAR") == 4  # el tic con tipo='error' no descuenta
    assert len(CODIGOS_NARRACION) == 3
    assert contar_narracion("COR-OTRO") == 1
    assert contar_narracion("COR-SECA") == 0


def _tanda_discovery_metricas() -> None:
    _evento("COR-MET1", "suceso", "ingreso_exitoso", "sesion=S")
    _evento("COR-MET1", "suceso", "consulta_exitosa", "set=0 | total=5", indice_set=0)
    _evento("COR-MET1", "error", "ERR-13", "fallo de red")
    _evento("COR-MET1", "suceso", "tic_modulo_iniciado", "modulo=descubrimiento")
    _evento("COR-MET1", "suceso", "tic_set_iniciado", "set=0", indice_set=0)
    _evento("COR-MET1", "suceso", "tic_captura_pagina", "set=0;pagina=2;acumuladas=9")


def test_metricas_del_descubrimiento_no_cuentan_narracion() -> None:
    from modules.discovery.nodes.finalizar import consultar_metricas
    from modules.discovery.run_context import RunContext

    _tanda_discovery_metricas()
    contexto = RunContext(
        config_fuentes=[],
        config_captura={},
        id_corrida="COR-MET1",
        permitir_vacio=True,
        config_descubrimiento={},
    )
    metricas = consultar_metricas(contexto)
    assert metricas == {
        "total_ofertas": 0,
        "total_errores": 1,
        "total_sucesos": 2,  # ingreso_exitoso + consulta_exitosa; tics fuera
        "fuentes_procesadas": 0,
    }


def test_metricas_de_preparacion_no_cuentan_narracion() -> None:
    from modules.preparation.nodes.finalizar import _consultar_metricas

    _evento("COR-MET2", "suceso", "oferta_preparada", "ok", id_oferta="OFE-1")
    _evento("COR-MET2", "error", "ERR-15", "fallo captura", id_oferta="OFE-2")
    _evento("COR-MET2", "suceso", "tic_modulo_iniciado", "modulo=preparacion")
    _evento("COR-MET2", "suceso", "revision_pendientes", "pendientes=2")

    metricas = _consultar_metricas("COR-MET2")
    assert metricas is not None
    assert metricas["total_preparadas"] == 1
    assert metricas["total_duplicadas"] == 0
    assert metricas["total_ofertas"] == 1
    assert metricas["total_errores"] == 1
    assert metricas["total_sucesos"] == 2  # oferta_preparada + revision_pendientes


def test_metricas_de_evaluacion_no_cuentan_narracion() -> None:
    from modules.evaluation.nodes.finalizar import _consultar_metricas

    _evento("COR-MET3", "suceso", "oferta_aprobada", "APROBADA", id_oferta="OFE-1")
    _evento("COR-MET3", "suceso", "oferta_descartada", "DESCARTADA", id_oferta="OFE-2")
    _evento("COR-MET3", "error", "ERR-04", "anotación fallida", id_oferta="OFE-3")
    _evento("COR-MET3", "suceso", "tic_modulo_iniciado", "modulo=evaluacion")

    metricas = _consultar_metricas("COR-MET3")
    assert metricas is not None
    assert metricas["total_aprobadas"] == 1
    assert metricas["total_descartadas"] == 1
    assert metricas["total_ofertas"] == 2
    assert metricas["total_errores"] == 1
    assert metricas["total_sucesos"] == 2  # aprobada + descartada; tic fuera


def test_tic_de_set_del_busqueda_nodo_queda_avisado() -> None:
    from modules.discovery.nodes.busqueda import _tic_set_iniciado
    from modules.discovery.run_context import RunContext
    from shared.persistence import leer_tabla

    contexto = RunContext(
        config_fuentes=[],
        config_captura={},
        id_corrida="COR-TIC",
        permitir_vacio=True,
        config_descubrimiento={},
    )
    _tic_set_iniciado(contexto, 2)
    filas = leer_tabla("eventos", {"id_corrida": "COR-TIC"})
    assert len(filas) == 1
    assert filas[0]["codigo"] == "tic_set_iniciado"
    assert filas[0]["tipo"] == "suceso"
    assert filas[0]["indice_set"] == 2
    assert _analizar_evidencia(str(filas[0]["evidencia"]))["set"] == "2"
