"""Unit tests for the INICIO node (sub-phase 4.1, Discovery module)."""

import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml

from modules.discovery.nodes.inicio import ejecutar_inicio
from modules.discovery.run_context import RunContext
from shared.errors import PersistenceError
from shared.persistence import (
    adquirir_bloqueo,
    consultar_bloqueo,
    leer_tabla,
    liberar_bloqueo,
)

CONFIG_BASE = {
    "captura": {
        "max_paginas": 5,
        "max_ofertas_por_corrida": 25,
        "pausa_entre_lotes_segundos": 10,
    },
    "concurrencia": {"umbral_obsolescencia_minutos": 120},
}

FUENTE_VALIDA: dict[str, Any] = {
    "fuente_id": "linkedin",
    "nombre": "LinkedIn",
    "ficha_acceso": {
        "enlace": "https://www.linkedin.com/jobs/search",
        "tipo_acceso": "con_autenticacion",
        "credenciales_referencia": ["LINKEDIN_EMAIL", "LINKEDIN_PASSWORD"],
        "criterio_exito": "global-nav",
        "timeout_segundos": 30,
    },
    "sets_de_filtros": [
        {"indice_set": 0, "filtros": [{"tipo": "keywords", "valor": ["Data Engineer"]}]},
        {"indice_set": 1, "filtros": []},
    ],
    "politicas_de_captura": {
        "max_paginas": 2,
        "max_ofertas_por_corrida": 10,
        "pausa_entre_lotes_segundos": 1,
    },
}

CONFIG_UNA_FUENTE: dict[str, Any] = {
    **CONFIG_BASE,
    "fuentes": [FUENTE_VALIDA],
}


def _marca(momento: datetime.datetime) -> str:
    return momento.strftime("%Y-%m-%d %H:%M:%S")


def test_inicio_ok_corrida_registrada_y_bloqueo(temp_db_file: Path) -> None:
    res = ejecutar_inicio(dict(CONFIG_UNA_FUENTE))
    assert res.estado == "ok"
    assert res.id_corrida.startswith("COR-")
    assert isinstance(res.contexto, RunContext)
    assert res.contexto.id_corrida == res.id_corrida
    assert res.contexto.bloqueo_adquirido is True
    corridas = leer_tabla("corridas")
    assert any(
        c["id_corrida"] == res.id_corrida and c["estado"] == "en_ejecucion"
        for c in corridas
    )
    bloqueo = consultar_bloqueo()
    assert bloqueo is not None
    assert bloqueo["id_corrida"] == res.id_corrida


def test_inicio_config_sin_fuentes_no_es_error(temp_db_file: Path) -> None:
    res = ejecutar_inicio({**CONFIG_BASE, "fuentes": []})
    assert res.estado == "ok"
    assert res.contexto is not None
    assert res.contexto.fuentes_filtradas == []


def test_inicio_descarta_fuente_incompleta_con_evento(temp_db_file: Path) -> None:
    incompleta: dict[str, Any] = {
        "fuente_id": "rotosource",
        "nombre": "Roto",
        "ficha_acceso": {"tipo_acceso": "publico"},
    }
    config = {
        **CONFIG_BASE,
        "fuentes": [dict(FUENTE_VALIDA), incompleta],
    }
    res = ejecutar_inicio(config)
    assert res.estado == "ok"
    assert res.contexto is not None
    assert [f.fuente_id for f in res.contexto.fuentes_filtradas] == ["linkedin"]
    eventos = leer_tabla("eventos")
    assert any(
        e["codigo"] == "ERR-12" and e["fuente_id"] == "rotosource"
        for e in eventos
    )


def test_inicio_aborta_source_id_duplicados(temp_db_file: Path) -> None:
    duplicada = {**FUENTE_VALIDA, "nombre": "LinkedIn Clon"}
    res = ejecutar_inicio({**CONFIG_BASE, "fuentes": [FUENTE_VALIDA, duplicada]})
    assert res.estado == "error"
    assert res.codigo == "ERR-11"
    assert leer_tabla("corridas") == []


def test_inicio_concurrencia_activa_terminacion_controlada(
    temp_db_file: Path,
) -> None:
    adquirir_bloqueo("COR-OTRO", _marca(datetime.datetime.now()))
    try:
        res = ejecutar_inicio(dict(CONFIG_UNA_FUENTE))
    finally:
        liberar_bloqueo("COR-OTRO")
    assert res.estado == "concurrencia"
    assert res.codigo == "ERR-06"
    assert leer_tabla("corridas") == []
    eventos = leer_tabla("eventos")
    assert any(e["codigo"] == "ERR-06" for e in eventos)


def test_inicio_bloqueo_obsoleto_se_sobrescribe(temp_db_file: Path) -> None:
    viejo = datetime.datetime.now() - datetime.timedelta(minutes=300)
    adquirir_bloqueo("COR-VIEJA", _marca(viejo))
    try:
        res = ejecutar_inicio(dict(CONFIG_UNA_FUENTE))
        assert res.estado == "ok"
        bloqueo = consultar_bloqueo()
        assert bloqueo is not None
        assert bloqueo["id_corrida"] == res.id_corrida
        eventos = leer_tabla("eventos")
        assert any(e["codigo"] == "ERR-07" for e in eventos)
    finally:
        liberar_bloqueo(res.id_corrida)


def test_inicio_bd_indisponible_aborta(temp_db_file: Path, monkeypatch: Any) -> None:
    def _boom() -> None:
        raise PersistenceError("05", "database down")

    monkeypatch.setattr("modules.discovery.nodes.inicio.init_db", _boom)
    res = ejecutar_inicio(dict(CONFIG_UNA_FUENTE))
    assert res.estado == "error"
    assert res.codigo == "ERR-05"


def test_inicio_config_ausente_aborta(temp_db_file: Path, monkeypatch: Any) -> None:
    def _sin_archivo() -> dict[str, Any]:
        raise FileNotFoundError("config.yaml missing")

    monkeypatch.setattr("modules.discovery.nodes.inicio.load", _sin_archivo)
    res = ejecutar_inicio()
    assert res.estado == "error"
    assert res.codigo == "ERR-02"


def test_inicio_config_ilegible_aborta(temp_db_file: Path, monkeypatch: Any) -> None:
    def _ilegible() -> dict[str, Any]:
        raise OSError("config.yaml unreadable")

    monkeypatch.setattr("modules.discovery.nodes.inicio.load", _ilegible)
    res = ejecutar_inicio()
    assert res.estado == "error"
    assert res.codigo == "ERR-03"


def test_inicio_run_id_falla_dos_veces_aborta(
    temp_db_file: Path, monkeypatch: Any
) -> None:
    def _falla() -> str:
        raise PersistenceError("01", "id generation down")

    monkeypatch.setattr("modules.discovery.nodes.inicio.generar_id", _falla)
    res = ejecutar_inicio(dict(CONFIG_UNA_FUENTE))
    assert res.estado == "error"
    assert res.codigo == "ERR-01"


def test_inicio_timestamp_bloqueo_invalido_aborta(
    temp_db_file: Path, monkeypatch: Any
) -> None:
    def _bloqueo_invalido() -> dict[str, Any] | None:
        return {"id_corrida": "COR-ROTA", "marca_temporal": "no-es-fecha"}

    monkeypatch.setattr("modules.discovery.nodes.inicio.consultar_bloqueo", _bloqueo_invalido)
    res = ejecutar_inicio(dict(CONFIG_UNA_FUENTE))
    assert res.estado == "error"
    assert res.codigo == "ERR-08"
    assert leer_tabla("corridas") == []


def test_inicio_descarta_estrategia_anti_bloqueo_invalida(
    temp_db_file: Path,
) -> None:
    con_estrategia_mala = {**FUENTE_VALIDA, "fuente_id": "fuente_maliciosa"}
    con_estrategia_mala["politicas_de_captura"] = {
        "max_paginas": 2,
        "max_ofertas_por_corrida": 10,
        "pausa_entre_lotes_segundos": 1,
        "estrategia_anti_bloqueo": "inventada",
    }
    res = ejecutar_inicio(
        {**CONFIG_BASE, "fuentes": [FUENTE_VALIDA, con_estrategia_mala]}
    )
    assert res.estado == "ok"
    assert res.contexto is not None
    assert [f.fuente_id for f in res.contexto.fuentes_filtradas] == ["linkedin"]
    eventos = leer_tabla("eventos")
    assert any(e["codigo"] == "ERR-12" for e in eventos)


def test_inicio_descarta_fuente_sin_source_id(temp_db_file: Path) -> None:
    sin_id = {**FUENTE_VALIDA, "fuente_id": None}
    res = ejecutar_inicio({**CONFIG_BASE, "fuentes": [FUENTE_VALIDA, sin_id]})
    assert res.estado == "ok"
    assert res.contexto is not None
    assert [f.fuente_id for f in res.contexto.fuentes_filtradas] == ["linkedin"]
    eventos = leer_tabla("eventos")
    assert any(
        e["codigo"] == "ERR-12" and "fuente_id" in e["evidencia"] for e in eventos
    )


def test_inicio_config_corrupta_aborta(temp_db_file: Path, monkeypatch: Any) -> None:
    def _corrupta() -> dict[str, Any]:
        raise yaml.YAMLError("bad yaml")

    monkeypatch.setattr("modules.discovery.nodes.inicio.load", _corrupta)
    res = ejecutar_inicio()
    assert res.estado == "error"
    assert res.codigo == "ERR-04"


def test_inicio_estado_interno_falla_aborta(
    temp_db_file: Path, monkeypatch: Any
) -> None:
    def _estalla(_: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("modules.discovery.nodes.inicio.registrar_corrida", _estalla)
    res = ejecutar_inicio(dict(CONFIG_UNA_FUENTE))
    assert res.estado == "error"
    assert res.codigo == "ERR-10"


def test_inicio_contienda_normal_err06_de_concurrencia(
    temp_db_file: Path, monkeypatch: Any
) -> None:
    def _pierde(_run_id: str, _ts: str) -> bool:
        return False

    monkeypatch.setattr(
        "modules.discovery.nodes.inicio.adquirir_bloqueo",
        lambda _run_id, _ts, forzar=False: False,
    )
    res = ejecutar_inicio(dict(CONFIG_UNA_FUENTE))
    assert res.estado == "concurrencia"
    assert res.codigo == "ERR-06"
    eventos = leer_tabla("eventos")
    assert any(e["codigo"] == "ERR-06" for e in eventos)


def test_inicio_contienda_sobrescritura_err06(
    temp_db_file: Path, monkeypatch: Any
) -> None:
    viejo = datetime.datetime.now() - datetime.timedelta(minutes=300)
    adquirir_bloqueo("COR-VIEJA", _marca(viejo))
    try:
        monkeypatch.setattr(
            "modules.discovery.nodes.inicio.adquirir_bloqueo",
            lambda _run_id, _ts, forzar=False: False,
        )
        res = ejecutar_inicio(dict(CONFIG_UNA_FUENTE))
        assert res.estado == "concurrencia"
        assert res.codigo == "ERR-06"
    finally:
        liberar_bloqueo("COR-VIEJA")


def test_sincronizar_listas_desde_config_alimenta_tabla(temp_db_file: Path) -> None:
    from modules.discovery.nodes.inicio import _sincronizar_listas_desde_config
    from shared.persistence import leer_tabla

    config: dict[str, Any] = {
        "sets_de_filtros": [
            {
                "indice_set": 0,
                "filtros": [{"tipo": "keywords", "valor": ["\"frase alfa\""]}],
            },
            {
                "indice_set": 1,
                "filtros": [
                    {"tipo": "geoid", "valor": "100876405"},
                    {"tipo": "keywords", "valor": ["frase", "beta"]},
                ],
            },
            {"indice_set": 2, "filtros": []},  # sin frase: se salta con aviso
            {"indice_set": 3},  # sin filtros: lo mismo
        ],
    }
    _sincronizar_listas_desde_config(config)

    filas = {fila["id_lista"]: fila["texto"] for fila in leer_tabla(
        "listas_busquedas"
    )}
    assert filas == {
        "LT-0001": "\"frase alfa\"",
        "LT-0002": "frase beta",
    }


def test_inicio_sincronizacion_fallida_no_aborta(temp_db_file: Path) -> None:
    # best-effort (D71): si la sincronizacion falla, el arranque sigue
    with patch(
        "modules.discovery.nodes.inicio.sincronizar_listas_busquedas",
        side_effect=RuntimeError("db"),
    ):
        res = ejecutar_inicio(dict(CONFIG_UNA_FUENTE))
    assert res.estado == "ok"


def test_inicio_ok_deja_tabla_de_listas(temp_db_file: Path) -> None:
    res = ejecutar_inicio(dict(CONFIG_UNA_FUENTE))
    assert res.estado == "ok"
    filas = {fila["id_lista"]: fila["texto"] for fila in leer_tabla("listas_busquedas")}
    assert filas == {"LT-0001": "Data Engineer"}  # set sin filtros: saltado
