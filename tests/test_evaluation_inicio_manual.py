"""Unit tests for the manual Evaluation INICIO + decisions (Phase 6.1, D76)."""

from pathlib import Path
from typing import Any

import pytest

from modules.evaluation.nodes.inicio_manual import (
    ejecutar_inicio_exportacion,
    ejecutar_inicio_importacion,
    hay_ofertas_preparadas,
    hay_resultados_para_importar,
)
from modules.evaluation.run_context import RunContext
from shared.evaluacion import validar_evaluacion, validar_evaluacion_manual
from shared.persistence import (
    adquirir_bloqueo,
    consultar_bloqueo,
    escribir_fila,
    leer_tabla,
)
from shared.utilidades import ahora

EVALUACION_MANUAL_VALIDA: dict[str, Any] = {
    "carpeta_base": "data/evaluacion_manual",
    "tamano_lote": 30,
    "modelo_evaluador": "chat: operador",
    "retries": {
        "max_attempts": 2,
        "base_wait_seconds": 2,
        "max_wait_seconds": 30,
        "multiplier": 2,
    },
}


def _config(carpeta_base: Path) -> dict[str, Any]:
    return {
        "concurrencia": {"umbral_obsolescencia_minutos": 120},
        "evaluacion_manual": {
            **EVALUACION_MANUAL_VALIDA,
            "carpeta_base": str(carpeta_base),
        },
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


def _eventos_de(id_corrida: str) -> list[dict[str, Any]]:
    return [
        evento
        for evento in leer_tabla("eventos")
        if evento.get("id_corrida") == id_corrida
    ]


# ---------------------------------------------------------------- Validación


def test_validacion_manual_acepta_la_configuracion_oficial() -> None:
    """Regression guard: the node must accept `config/config.yaml` verbatim."""
    from shared.config import load

    config = load()
    assert validar_evaluacion_manual(config.get("evaluacion_manual")) is None
    # El validador del flujo viejo sigue operando con su propia sección.
    assert validar_evaluacion(config.get("evaluacion"), config) is None


def test_validacion_manual_rechaza_seccion_ausente() -> None:
    assert validar_evaluacion_manual(None) is not None
    assert validar_evaluacion_manual([]) is not None


def test_validacion_manual_exige_carpeta_no_vacia() -> None:
    for valor in (None, "", "   ", 7):
        seccion = {**EVALUACION_MANUAL_VALIDA, "carpeta_base": valor}
        assert validar_evaluacion_manual(seccion) is not None


def test_validacion_manual_exige_tamano_de_lote_entero_positivo() -> None:
    for valor in (None, 0, -3, 2.5, True, "30"):
        seccion = {**EVALUACION_MANUAL_VALIDA, "tamano_lote": valor}
        assert validar_evaluacion_manual(seccion) is not None


def test_validacion_manual_exige_modelo_evaluador() -> None:
    for valor in (None, "", "  ", 5):
        seccion = {**EVALUACION_MANUAL_VALIDA, "modelo_evaluador": valor}
        assert validar_evaluacion_manual(seccion) is not None


def test_validacion_manual_exige_reintentos_coherentes() -> None:
    base = {**EVALUACION_MANUAL_VALIDA, "retries": None}
    assert validar_evaluacion_manual(base) is not None
    sin_intentos = {
        **EVALUACION_MANUAL_VALIDA,
        "retries": {"max_attempts": 0, "base_wait_seconds": 2,
                    "max_wait_seconds": 30, "multiplier": 2},
    }
    assert validar_evaluacion_manual(sin_intentos) is not None
    tope_invertido = {
        **EVALUACION_MANUAL_VALIDA,
        "retries": {"max_attempts": 2, "base_wait_seconds": 30,
                    "max_wait_seconds": 2, "multiplier": 2},
    }
    assert validar_evaluacion_manual(tope_invertido) is not None
    multiplicador_invalido = {
        **EVALUACION_MANUAL_VALIDA,
        "retries": {"max_attempts": 2, "base_wait_seconds": 2,
                    "max_wait_seconds": 30, "multiplier": 0.5},
    }
    assert validar_evaluacion_manual(multiplicador_invalido) is not None


# ---------------------------------------------------------------- Contexto


def test_contexto_defaults_manuales() -> None:
    ctx = RunContext()
    assert ctx.config_evaluacion_manual == {}
    assert ctx.archivos_resultados == []
    assert ctx.hubo_resultados is False
    assert ctx.contador_exportadas == 0
    assert ctx.contador_lotes == 0
    assert ctx.contador_rechazadas == 0
    assert ctx.carpeta_base is None
    assert ctx.carpeta_rechazados is None
    assert ctx.carpetas_resueltas is False


def test_contexto_manual_marca_hubo_resultados() -> None:
    ctx = RunContext(archivos_resultados=[Path("resultados/a.txt")])
    assert ctx.hubo_resultados is True


# ---------------------------------------------------------------- Exportación


def test_inicio_exportacion_ok_sin_candidatas(temp_db_file: Path, tmp_path: Path) -> None:
    base = tmp_path / "evaluacion_manual"
    res = ejecutar_inicio_exportacion(_config(base))
    assert res.estado == "ok"
    assert res.id_corrida.startswith("COR-")
    ctx = res.contexto
    assert isinstance(ctx, RunContext)
    assert ctx.id_corrida == res.id_corrida
    assert ctx.bloqueo_adquirido is True
    assert ctx.hubo_candidatas is False
    assert ctx.candidatas == []
    assert ctx.hubo_resultados is False
    assert ctx.archivos_resultados == []
    assert ctx.contador_exportadas == 0
    assert ctx.contador_lotes == 0
    assert ctx.contador_errores == 0
    assert ctx.config_evaluacion_manual["tamano_lote"] == 30
    # Carpetas resueltas y creadas; `rechazados/` solo se crea al usarse.
    assert ctx.carpetas_resueltas is True
    assert ctx.carpeta_base == base
    assert ctx.carpeta_lotes == base / "lotes"
    assert ctx.carpeta_resultados == base / "resultados"
    assert ctx.carpeta_rechazados == base / "resultados" / "rechazados"
    assert (base / "lotes").is_dir()
    assert (base / "resultados").is_dir()
    assert not (base / "resultados" / "rechazados").exists()
    # Corrida registrada antes del bloqueo y bloqueo en manos propias.
    filas = leer_tabla("corridas")
    fila = next(c for c in filas if c["id_corrida"] == res.id_corrida)
    assert fila["estado"] == "en_ejecucion"
    assert fila["fecha_inicio"] == ctx.fecha_inicio
    bloqueo = consultar_bloqueo()
    assert bloqueo is not None
    assert bloqueo["id_corrida"] == res.id_corrida
    # Pulso de arranque con el proceso en la evidencia.
    tics = [
        e for e in _eventos_de(res.id_corrida) if e["codigo"] == "tic_modulo_iniciado"
    ]
    assert len(tics) == 1
    assert "modulo=evaluacion" in tics[0]["evidencia"]
    assert "proceso=exportacion" in tics[0]["evidencia"]


def test_inicio_exportacion_carga_preparadas_en_fifo(
    temp_db_file: Path, tmp_path: Path
) -> None:
    _insertar_oferta("OFE-0003", "2026-08-20 10:00:00")
    _insertar_oferta("OFE-0001", "2026-08-21 09:00:00")
    _insertar_oferta("OFE-0002", "2026-08-21 09:00:00")
    _insertar_oferta("OFE-0009", "2026-08-19 08:00:00", estado="descubierta")
    _insertar_oferta("OFE-0008", "2026-08-19 08:00:00", estado="duplicada")
    base = tmp_path / "eval"
    res = ejecutar_inicio_exportacion(_config(base))
    assert res.estado == "ok"
    assert res.contexto is not None
    assert [c["id"] for c in res.contexto.candidatas] == [
        "OFE-0003",
        "OFE-0001",
        "OFE-0002",
    ]
    assert res.contexto.hubo_candidatas is True
    # RN-05: el arranque no escribe lotes ni cambia estados de ofertas.
    assert list((base / "lotes").iterdir()) == []
    estados = {
        fila["id"]: fila["estado"] for fila in leer_tabla("ofertas_descubiertas")
    }
    assert estados == {
        "OFE-0003": "preparada",
        "OFE-0001": "preparada",
        "OFE-0002": "preparada",
        "OFE-0009": "descubierta",
        "OFE-0008": "duplicada",
    }


def test_inicio_exportacion_config_invalida_aborta_con_id(
    temp_db_file: Path, tmp_path: Path
) -> None:
    config = _config(tmp_path / "eval")
    config["evaluacion_manual"]["carpeta_base"] = "   "
    res = ejecutar_inicio_exportacion(config)
    assert res.estado == "error"
    assert res.codigo == "ERR-04"
    assert res.id_corrida.startswith("COR-")
    # La configuración precede a la BD: no se registró corrida ni bloqueo.
    assert leer_tabla("corridas") == []
    assert consultar_bloqueo() is None


def test_inicio_exportacion_sin_seccion_aborta(temp_db_file: Path) -> None:
    res = ejecutar_inicio_exportacion({"concurrencia": {}})
    assert res.estado == "error"
    assert res.codigo == "ERR-04"


def test_inicio_exportacion_concurrencia_activa(
    temp_db_file: Path, tmp_path: Path
) -> None:
    adquirir_bloqueo("COR-AJENA", ahora())
    res = ejecutar_inicio_exportacion(_config(tmp_path / "eval"))
    assert res.estado == "concurrencia"
    assert res.codigo == "ERR-06"
    assert res.id_corrida.startswith("COR-")
    # La fila propia existe para que Finalizar la cierre; el bloqueo ajeno sigue.
    filas = leer_tabla("corridas")
    assert any(c["id_corrida"] == res.id_corrida for c in filas)
    bloqueo = consultar_bloqueo()
    assert bloqueo is not None
    assert bloqueo["id_corrida"] == "COR-AJENA"


def test_inicio_exportacion_carpeta_no_creable_aborta(
    temp_db_file: Path, tmp_path: Path
) -> None:
    archivo = tmp_path / "no_es_carpeta"
    archivo.write_text("x", encoding="utf-8")
    res = ejecutar_inicio_exportacion(_config(archivo / "sub"))
    assert res.estado == "error"
    assert res.codigo == "ERR-10"
    assert res.id_corrida.startswith("COR-")
    # La carpeta se comprueba después del bloqueo: la silla queda tomada y
    # "Finalizar Proceso" puede liberarla al cerrar.
    bloqueo = consultar_bloqueo()
    assert bloqueo is not None
    assert bloqueo["id_corrida"] == res.id_corrida


def test_inicio_exportacion_bloqueo_obsoleto_se_sobrescribe(
    temp_db_file: Path, tmp_path: Path
) -> None:
    from datetime import datetime, timedelta

    from shared.utilidades import FORMATO_TIMESTAMP

    marca_vieja = (datetime.now() - timedelta(hours=3)).strftime(FORMATO_TIMESTAMP)
    assert adquirir_bloqueo("COR-VIEJA", marca_vieja, forzar=True) is True
    res = ejecutar_inicio_exportacion(_config(tmp_path / "eval"))
    assert res.estado == "ok"
    assert res.contexto is not None
    bloqueo = consultar_bloqueo()
    assert bloqueo is not None
    assert bloqueo["id_corrida"] == res.id_corrida
    codigos = {evento["codigo"] for evento in _eventos_de(res.id_corrida)}
    assert "ERR-07" in codigos


def test_inicio_exportacion_bloqueo_no_decidible_aborta(
    temp_db_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from modules.evaluation.nodes import inicio_manual

    def _falla() -> None:
        raise RuntimeError("bloqueo ilegible")

    monkeypatch.setattr(inicio_manual, "consultar_bloqueo", _falla)
    res = ejecutar_inicio_exportacion(_config(tmp_path / "eval"))
    assert res.estado == "error"
    assert res.codigo == "ERR-08"
    codigos = {evento["codigo"] for evento in _eventos_de(res.id_corrida)}
    assert "ERR-08" in codigos


def test_inicio_exportacion_marca_de_bloqueo_invalida_aborta(
    temp_db_file: Path, tmp_path: Path
) -> None:
    from shared.persistence import _connection

    conn = _connection()
    try:
        conn.execute(
            "INSERT INTO bloqueo (id_corrida, marca_temporal) VALUES (?, ?)",
            ("COR-RARA", "no-es-fecha"),
        )
        conn.commit()
    finally:
        conn.close()
    res = ejecutar_inicio_exportacion(_config(tmp_path / "eval"))
    assert res.estado == "error"
    assert res.codigo == "ERR-08"
    # La silla ajena no se toca cuando su marca no es decidible.
    bloqueo = consultar_bloqueo()
    assert bloqueo is not None
    assert bloqueo["id_corrida"] == "COR-RARA"


def test_inicio_exportacion_contexto_incompleto_es_err_11(
    temp_db_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from modules.evaluation.nodes import inicio_manual

    monkeypatch.setattr(inicio_manual, "_asignar_carpetas", lambda *_: None)
    res = ejecutar_inicio_exportacion(_config(tmp_path / "eval"))
    assert res.estado == "error"
    assert res.codigo == "ERR-11"
    codigos = {evento["codigo"] for evento in _eventos_de(res.id_corrida)}
    assert "ERR-11" in codigos


def test_inicio_exportacion_carpeta_relativa_bajo_la_raiz(
    temp_db_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from modules.evaluation.nodes import inicio_manual

    monkeypatch.setattr(inicio_manual, "_RAIZ_PROYECTO", tmp_path)
    res = ejecutar_inicio_exportacion(
        {
            "concurrencia": {"umbral_obsolescencia_minutos": 120},
            "evaluacion_manual": {
                **EVALUACION_MANUAL_VALIDA,
                "carpeta_base": "eval_relativa",
            },
        }
    )
    assert res.estado == "ok"
    assert res.contexto is not None
    assert res.contexto.carpeta_base == tmp_path / "eval_relativa"
    assert (tmp_path / "eval_relativa" / "lotes").is_dir()
    assert (tmp_path / "eval_relativa" / "resultados").is_dir()


# ---------------------------------------------------------------- Importación


def test_inicio_importacion_ok_sin_archivos(
    temp_db_file: Path, tmp_path: Path
) -> None:
    base = tmp_path / "eval"
    res = ejecutar_inicio_importacion(_config(base))
    assert res.estado == "ok"
    assert res.id_corrida.startswith("COR-")
    ctx = res.contexto
    assert isinstance(ctx, RunContext)
    assert ctx.bloqueo_adquirido is True
    assert ctx.candidatas == []
    assert ctx.hubo_candidatas is False
    assert ctx.archivos_resultados == []
    assert ctx.hubo_resultados is False
    assert ctx.contador_aprobadas == 0
    assert ctx.contador_descartadas == 0
    assert ctx.contador_rechazadas == 0
    assert ctx.contador_errores == 0
    assert ctx.contador_lotes == 0
    assert ctx.carpetas_resueltas is True
    assert (base / "lotes").is_dir()
    assert (base / "resultados").is_dir()
    tics = [
        e for e in _eventos_de(res.id_corrida) if e["codigo"] == "tic_modulo_iniciado"
    ]
    assert len(tics) == 1
    assert "proceso=importacion" in tics[0]["evidencia"]


def test_inicio_importacion_lista_archivos_ordenados(
    temp_db_file: Path, tmp_path: Path
) -> None:
    base = tmp_path / "eval"
    resultados = base / "resultados"
    resultados.mkdir(parents=True)
    (resultados / "COR-0002_lote-001_parte-02.txt").write_text("b", encoding="utf-8")
    (resultados / "COR-0002_lote-001_parte-01.txt").write_text("a", encoding="utf-8")
    (resultados / "COR-0001_lote-001_parte-01.txt").write_text("c", encoding="utf-8")
    (resultados / ".oculto.txt").write_text("x", encoding="utf-8")
    rechazados = resultados / "rechazados"
    rechazados.mkdir()
    (rechazados / "COR-0009_lote-001_parte-01.txt").write_text("z", encoding="utf-8")

    res = ejecutar_inicio_importacion(_config(base))
    assert res.estado == "ok"
    assert res.contexto is not None
    nombres = [ruta.name for ruta in res.contexto.archivos_resultados]
    assert nombres == [
        "COR-0001_lote-001_parte-01.txt",
        "COR-0002_lote-001_parte-01.txt",
        "COR-0002_lote-001_parte-02.txt",
    ]
    assert all(ruta.parent == resultados for ruta in res.contexto.archivos_resultados)
    assert res.contexto.hubo_resultados is True


def test_inicio_importacion_carpeta_no_creable_aborta(
    temp_db_file: Path, tmp_path: Path
) -> None:
    archivo = tmp_path / "no_es_carpeta"
    archivo.write_text("x", encoding="utf-8")
    res = ejecutar_inicio_importacion(_config(archivo / "sub"))
    assert res.estado == "error"
    assert res.codigo == "ERR-10"
    bloqueo = consultar_bloqueo()
    assert bloqueo is not None
    assert bloqueo["id_corrida"] == res.id_corrida


def test_inicio_importacion_listado_ilegible_aborta(
    temp_db_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from modules.evaluation.nodes import inicio_manual

    def _falla(_carpeta: Path) -> list[Path]:
        raise OSError("listado ilegible")

    monkeypatch.setattr(inicio_manual, "_listar_resultados", _falla)
    res = ejecutar_inicio_importacion(_config(tmp_path / "eval"))
    assert res.estado == "error"
    assert res.codigo == "ERR-10"
    codigos = {evento["codigo"] for evento in _eventos_de(res.id_corrida)}
    assert "ERR-10" in codigos


def test_inicio_importacion_concurrencia_activa(
    temp_db_file: Path, tmp_path: Path
) -> None:
    adquirir_bloqueo("COR-AJENA", ahora())
    res = ejecutar_inicio_importacion(_config(tmp_path / "eval"))
    assert res.estado == "concurrencia"
    assert res.codigo == "ERR-06"
    filas = leer_tabla("corridas")
    assert any(c["id_corrida"] == res.id_corrida for c in filas)


# ---------------------------------------------------------------- Decisiones


def test_decision_exportacion_si_con_ofertas() -> None:
    ctx = RunContext(id_corrida="COR-DEC", candidatas=[{"id": "OFE-0001"}])
    res = hay_ofertas_preparadas(ctx)
    assert res.estado == "ok"
    assert res.decision == "si"
    assert res.contexto is ctx
    assert ctx.motivo_cierre is None


def test_decision_exportacion_no_fija_sin_pendientes() -> None:
    ctx = RunContext(id_corrida="COR-DEC", candidatas=[])
    res = hay_ofertas_preparadas(ctx)
    assert res.estado == "ok"
    assert res.decision == "no"
    assert ctx.motivo_cierre == "sin_pendientes"
    assert ctx.motivo_marca_temporal


def test_decision_exportacion_sin_contexto_es_error() -> None:
    res = hay_ofertas_preparadas(None)
    assert res.estado == "error"
    assert res.codigo == "ERR-01"


def test_decision_importacion_si_con_archivos() -> None:
    ctx = RunContext(
        id_corrida="COR-IMP", archivos_resultados=[Path("resultados/a.txt")]
    )
    res = hay_resultados_para_importar(ctx)
    assert res.estado == "ok"
    assert res.decision == "si"
    assert ctx.motivo_cierre is None


def test_decision_importacion_no_fija_sin_resultados() -> None:
    ctx = RunContext(id_corrida="COR-IMP", archivos_resultados=[])
    res = hay_resultados_para_importar(ctx)
    assert res.estado == "ok"
    assert res.decision == "no"
    assert ctx.motivo_cierre == "sin_resultados"
    assert ctx.motivo_marca_temporal


def test_decision_importacion_sin_contexto_es_error() -> None:
    res = hay_resultados_para_importar(None)
    assert res.estado == "error"
    assert res.codigo == "ERR-01"
