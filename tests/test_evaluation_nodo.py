"""Unit tests for the Evaluación inicial node (Phase 6.2).

The AI boundary (`analyze`) is mocked; persistence and counters run against
a temporary database. Covers approved/rejected persistence, the V3-FAIL
fast path, per-offer failure tolerance, quota-ordered stop and answer
validation (VAL-04).
"""

import json
from pathlib import Path
from typing import Any

import pytest

import modules.evaluation.nodes.evaluacion as evaluacion_mod
from modules.evaluation.nodes.evaluacion import (
    _limpiar_descripcion_para_ia,
    _validar_respuesta,
    ejecutar_evaluacion,
)
from modules.evaluation.run_context import RunContext
from shared.persistence import buscar_por_id, leer_tabla

EVALUACION_VALIDA: dict[str, Any] = {
    "pausa_entre_ofertas_segundos": 0,
    "pausa_jitter_segundos": 0,
    "timeout_puerta_segundos": 60,
    "retries": {
        "max_attempts": 2,
        "base_wait_seconds": 0,
        "max_wait_seconds": 0,
        "multiplier": 1,
    },
    "puertas_alternas": [],
}


def _respuesta(decision: str = "APROBADA", veto: str = "v1") -> dict[str, str]:
    base = {
        "entregable_principal": "  Proceso de planeación y criterios de priorización  ",
        "v1": "PASS",
        "v2": "PASS",
        "v3": "PASS",
        "v4": "PASS",
        "v5": "PASS",
    }
    if decision == "DESCARTADA":
        base[veto] = "FAIL"
    return {**base, "decision": decision, "justificacion": "Rol compatible con el perfil buscado"}


def _sembrar(oferta_id: str, descripcion: str = "Descripcion valida de la oferta.") -> None:
    from shared.persistence import escribir_fila

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


def _contexto(ids: list[str]) -> RunContext:
    from shared.persistence import leer_candidatas_preparadas

    candidatas = [c for c in leer_candidatas_preparadas() if c["id"] in ids]
    return RunContext(
        config_evaluacion=dict(EVALUACION_VALIDA),
        candidatas=candidatas,
        id_corrida="COR-TEST",
    )


def _eventos(codigo: str) -> list[dict[str, Any]]:
    return [e for e in leer_tabla("eventos") if e["codigo"] == codigo]


# ---------------------------------------------------------------- VAL-04


def test_validar_respuesta_aprobada_ok() -> None:
    validada = _validar_respuesta(_respuesta("APROBADA"))
    assert validada.decision == "APROBADA"


def test_validar_respuesta_sin_entregable_principal() -> None:
    mala = _respuesta("APROBADA")
    del mala["entregable_principal"]
    with pytest.raises(ValueError):
        _validar_respuesta(mala)


def test_validar_respuesta_entregable_vacio() -> None:
    mala = _respuesta("APROBADA")
    mala["entregable_principal"] = "   "
    with pytest.raises(ValueError):
        _validar_respuesta(mala)


def test_validar_respuesta_entregable_centinela() -> None:
    mala = _respuesta("APROBADA")
    mala["entregable_principal"] = "N/A"
    with pytest.raises(ValueError):
        _validar_respuesta(mala)


def test_validar_respuesta_entregable_mas_de_20_palabras() -> None:
    mala = _respuesta("APROBADA")
    mala["entregable_principal"] = " ".join(f"palabra{i}" for i in range(21))
    with pytest.raises(ValueError):
        _validar_respuesta(mala)


def test_validar_respuesta_entregable_exacto_20_palabras_ok() -> None:
    buena = _respuesta("APROBADA")
    buena["entregable_principal"] = " ".join(f"palabra{i}" for i in range(20))
    assert _validar_respuesta(buena).decision == "APROBADA"


def test_validar_respuesta_entregable_multilinea() -> None:
    mala = _respuesta("APROBADA")
    mala["entregable_principal"] = "Proceso de planeación\r\ncon criterios"
    with pytest.raises(ValueError):
        _validar_respuesta(mala)


def test_validar_respuesta_entregable_con_comillas_dobles() -> None:
    mala = _respuesta("APROBADA")
    mala["entregable_principal"] = 'Proceso "S&OP"'
    with pytest.raises(ValueError):
        _validar_respuesta(mala)


def test_validar_respuesta_incoherente() -> None:
    mala = _respuesta("APROBADA")
    mala["v2"] = "FAIL"
    with pytest.raises(ValueError):
        _validar_respuesta(mala)


def test_validar_respuesta_justificacion_larga() -> None:
    mala = _respuesta("APROBADA")
    mala["justificacion"] = " ".join(f"palabra{i}" for i in range(61))
    with pytest.raises(ValueError):
        _validar_respuesta(mala)


def test_validar_respuesta_justificacion_exacto_60_palabras_ok() -> None:
    buena = _respuesta("APROBADA")
    buena["justificacion"] = " ".join(f"palabra{i}" for i in range(60))
    assert _validar_respuesta(buena).decision == "APROBADA"


def test_validar_respuesta_no_dict() -> None:
    with pytest.raises(ValueError):
        _validar_respuesta("APROBADA")


# ---------------------------------------------------------------- Caminos felices


def test_aprobada_persiste_estado_resultado_y_evento(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar("OFE-0001")
    monkeypatch.setattr(evaluacion_mod, "analyze", lambda *a, **k: _respuesta("APROBADA"))
    res = ejecutar_evaluacion(_contexto(["OFE-0001"]))
    assert res.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["estado"] == "aceptada_ei"
    guardado = json.loads(str(fila["resultado_evaluacion_inicial"]))
    assert next(iter(guardado)) == "entregable_principal"
    assert guardado["entregable_principal"] == "Proceso de planeación y criterios de priorización"
    assert guardado["decision"] == "APROBADA"
    assert guardado["puerta"] == "principal"
    eventos = _eventos("oferta_aprobada")
    assert len(eventos) == 1
    assert eventos[0]["id_oferta"] == "OFE-0001"
    assert res.contexto is not None
    assert res.contexto.contador_aprobadas == 1


def test_descartada_registra_el_veto_que_freno(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar("OFE-0001")
    monkeypatch.setattr(
        evaluacion_mod, "analyze", lambda *a, **k: _respuesta("DESCARTADA", veto="v5")
    )
    res = ejecutar_evaluacion(_contexto(["OFE-0001"]))
    assert res.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["estado"] == "descartada_ei"
    eventos = _eventos("oferta_descartada")
    assert len(eventos) == 1
    assert "veto=v5" in str(eventos[0]["evidencia"])
    assert res.contexto is not None
    assert res.contexto.contador_descartadas == 1


# ---------------------------------------------------------------- V3-FAIL


@pytest.mark.parametrize("descripcion", ["", "N/A", "N/R", "No reportada por la fuente"])
def test_descripcion_vacia_descarta_sin_llamar_a_la_ia(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch, descripcion: str
) -> None:
    _sembrar("OFE-0001", descripcion=descripcion)

    def _boom(*a: Any, **k: Any) -> dict[str, str]:
        raise AssertionError("la IA no debe llamarse sin descripcion")

    monkeypatch.setattr(evaluacion_mod, "analyze", _boom)
    res = ejecutar_evaluacion(_contexto(["OFE-0001"]))
    assert res.estado == "completada"
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["estado"] == "descartada_ei"
    guardado = json.loads(str(fila["resultado_evaluacion_inicial"]))
    assert guardado["entregable_principal"] == "N/A"
    assert guardado["v3"] == "FAIL"
    assert guardado["puerta"] == "sin_llamada"


# ---------------------------------------------------------------- Fallos por oferta


def test_configuracion_sin_timeout_de_puerta_aborta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-01/D59: sin espera por puerta válida no se llama a la IA."""
    _sembrar("OFE-0001")
    ctx = _contexto(["OFE-0001"])
    del ctx.config_evaluacion["timeout_puerta_segundos"]

    def _boom(*a: Any, **k: Any) -> dict[str, str]:
        raise AssertionError("la IA no debe llamarse sin timeout de puerta")

    monkeypatch.setattr(evaluacion_mod, "analyze", _boom)
    res = ejecutar_evaluacion(ctx)
    assert res.estado == "abortada"
    assert res.codigo == "ERR-01"


def test_fallo_de_puerta_sin_alternas_detiene_sin_reintentar(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D59: una puerta caída no se reintenta; sin puertas sanas no se sigue."""
    from shared.errors import LLMError

    _sembrar("OFE-0001")
    _sembrar("OFE-0002")
    llamadas = {"n": 0}

    def _falla(*a: Any, **k: Any) -> dict[str, str]:
        llamadas["n"] += 1
        assert k["timeout"] == 60
        assert k["reintentar"] is False
        raise LLMError("001", "puerta caida", source_module="ia_service")

    monkeypatch.setattr(evaluacion_mod, "analyze", _falla)
    ctx = _contexto(["OFE-0001", "OFE-0002"])
    ctx.candidatas.sort(key=lambda c: str(c["id"]))
    res = ejecutar_evaluacion(ctx)
    assert res.estado == "completada"
    # Un solo intento: la puerta caida no se reintenta en la misma corrida.
    assert llamadas["n"] == 1
    assert res.contexto is not None
    # El motivo no se fija aquí: lo deriva Finalizar (error_total/corrida_completada).
    assert res.contexto.motivo_cierre is None
    assert "principal" in res.contexto.puertas_caidas
    fila1 = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila1 is not None
    assert fila1["estado"] == "preparada"
    assert fila1["resultado_evaluacion_inicial"] == "N/A"
    fila2 = buscar_por_id("ofertas_descubiertas", "OFE-0002")
    assert fila2 is not None
    assert fila2["estado"] == "preparada"
    assert len(_eventos("evaluacion_fallida")) == 1
    assert res.contexto.contador_errores == 1


def test_respuesta_invalida_reintente_en_la_misma_puerta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar("OFE-0001")
    llamadas = {"n": 0}

    def _invalida(*a: Any, **k: Any) -> dict[str, str]:
        llamadas["n"] += 1
        return {"decision": "APROBADA"}

    monkeypatch.setattr(evaluacion_mod, "analyze", _invalida)
    res = ejecutar_evaluacion(_contexto(["OFE-0001"]))
    assert res.estado == "completada"
    # RN-07/D59: la respuesta mal formada reintenta en la misma puerta y no
    # la marca caida (la puerta respondio).
    assert llamadas["n"] == 2
    assert res.contexto is not None
    assert res.contexto.puertas_caidas == {}
    assert res.contexto.contador_errores == 1
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["estado"] == "preparada"
    assert len(_eventos("evaluacion_fallida")) == 1


def test_fallo_de_principal_rota_a_alterna_y_registra_puerta(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shared.errors import LLMError

    _sembrar("OFE-0001")

    def _principal_caida(*a: Any, **k: Any) -> dict[str, str]:
        raise LLMError("001", "puerta caida", source_module="ia_service")

    llamadas = {"n": 0}

    def _alterna_responde(
        prompt: str, contexto: dict[str, str], modelo: str, clave: str, **k: Any
    ) -> dict[str, str]:
        llamadas["n"] += 1
        assert modelo == "google/gemma-4-31b-it"
        assert clave == "OPENROUTER_API_KEY_1"
        assert k["timeout"] == 60
        return _respuesta("APROBADA")

    monkeypatch.setattr(evaluacion_mod, "analyze", _principal_caida)
    monkeypatch.setattr(evaluacion_mod, "analyze_openrouter", _alterna_responde)
    ctx = _contexto(["OFE-0001"])
    ctx.config_evaluacion["puertas_alternas"] = [
        {
            "nombre": "openrouter-1",
            "modelo": "google/gemma-4-31b-it",
            "clave_ref": "OPENROUTER_API_KEY_1",
        }
    ]
    res = ejecutar_evaluacion(ctx)
    assert res.estado == "completada"
    assert llamadas["n"] == 1
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["estado"] == "aceptada_ei"
    guardado = json.loads(str(fila["resultado_evaluacion_inicial"]))
    assert guardado["puerta"] == "openrouter-1"
    eventos = _eventos("oferta_aprobada")
    assert len(eventos) == 1
    assert "puerta=openrouter-1" in str(eventos[0]["evidencia"])


def test_puerta_caida_se_recuerda_en_las_siguientes_ofertas(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D59: una puerta que cae no se vuelve a llamar en la misma corrida."""
    from shared.errors import LLMError

    _sembrar("OFE-0001")
    _sembrar("OFE-0002")
    principal = {"n": 0}

    def _principal_caida(*a: Any, **k: Any) -> dict[str, str]:
        principal["n"] += 1
        raise LLMError("001", "puerta caida", source_module="ia_service")

    alternas = {"n": 0}

    def _alterna_responde(*a: Any, **k: Any) -> dict[str, str]:
        alternas["n"] += 1
        return _respuesta("APROBADA")

    monkeypatch.setattr(evaluacion_mod, "analyze", _principal_caida)
    monkeypatch.setattr(evaluacion_mod, "analyze_openrouter", _alterna_responde)
    ctx = _contexto(["OFE-0001", "OFE-0002"])
    ctx.candidatas.sort(key=lambda c: str(c["id"]))
    ctx.config_evaluacion["puertas_alternas"] = [
        {
            "nombre": "openrouter-1",
            "modelo": "google/gemma-4-31b-it",
            "clave_ref": "OPENROUTER_API_KEY_1",
        }
    ]
    res = ejecutar_evaluacion(ctx)
    assert res.estado == "completada"
    # La principal se intento una sola vez; la alterna respondio las dos.
    assert principal["n"] == 1
    assert alternas["n"] == 2
    assert res.contexto is not None
    assert list(res.contexto.puertas_caidas) == ["principal"]
    for oferta_id in ("OFE-0001", "OFE-0002"):
        fila = buscar_por_id("ofertas_descubiertas", oferta_id)
        assert fila is not None
        assert fila["estado"] == "aceptada_ei"


def test_todas_las_puertas_caidas_cierra_sin_llamar(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D59: al caer todas las puertas se deja de llamar; el resto queda pendiente."""
    from shared.errors import LLMError

    _sembrar("OFE-0001")
    _sembrar("OFE-0002")
    llamadas = {"n": 0}

    def _caida(*a: Any, **k: Any) -> dict[str, str]:
        llamadas["n"] += 1
        raise LLMError(
            "002", "Timeout connecting to AI Cloud (60s)", source_module="ia_service"
        )

    monkeypatch.setattr(evaluacion_mod, "analyze", _caida)
    monkeypatch.setattr(evaluacion_mod, "analyze_openrouter", _caida)
    ctx = _contexto(["OFE-0001", "OFE-0002"])
    ctx.candidatas.sort(key=lambda c: str(c["id"]))
    ctx.config_evaluacion["puertas_alternas"] = [
        {
            "nombre": f"openrouter-{numero}",
            "modelo": "google/gemma-4-31b-it",
            "clave_ref": f"OPENROUTER_API_KEY_{numero}",
        }
        for numero in (1, 2, 3)
    ]
    res = ejecutar_evaluacion(ctx)
    assert res.estado == "completada"
    # 4 puertas intentadas una vez; la segunda oferta ni se toca.
    assert llamadas["n"] == 4
    assert res.contexto is not None
    assert res.contexto.motivo_cierre is None
    assert len(res.contexto.puertas_caidas) == 4
    fila2 = buscar_por_id("ofertas_descubiertas", "OFE-0002")
    assert fila2 is not None
    assert fila2["estado"] == "preparada"
    assert len(_eventos("evaluacion_fallida")) == 1


def test_cupo_agotado_frena_y_fija_cierre_por_cupo(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shared.errors import LLMError

    _sembrar("OFE-0001")
    _sembrar("OFE-0002")

    def _cupo(*a: Any, **k: Any) -> dict[str, str]:
        raise LLMError("003", "AI Cloud responded with code 429", source_module="ia_service")

    monkeypatch.setattr(evaluacion_mod, "analyze", _cupo)
    ctx = _contexto(["OFE-0001", "OFE-0002"])
    ctx.candidatas.sort(key=lambda c: str(c["id"]))
    res = ejecutar_evaluacion(ctx)
    assert res.estado == "completada"
    assert res.contexto is not None
    assert res.contexto.motivo_cierre == "cupo_agotado"
    # Solo la primera se intento; la segunda ni se toco.
    assert len(_eventos("evaluacion_fallida")) == 1
    fila2 = buscar_por_id("ofertas_descubiertas", "OFE-0002")
    assert fila2 is not None
    assert fila2["estado"] == "preparada"


# ---------------------------------------------------------------- Limpieza de entrada


def test_limpieza_deja_intacta_la_descripcion_corta() -> None:
    texto = "Únete al mejor equipo.\nBuscamos Desarrollador Python con PySpark."
    assert _limpiar_descripcion_para_ia(texto) == texto


def test_limpieza_quita_beneficios_y_avisos_del_final() -> None:
    texto = (
        "Responsibilities\nBuild data pipelines.\n"
        "Benefits\nHealth insurance.\n"
        "Equal Opportunity\nWe are an equal opportunity employer."
    )
    limpio = _limpiar_descripcion_para_ia(texto)
    assert "Build data pipelines" in limpio
    assert "Benefits" not in limpio
    assert "Health insurance" not in limpio
    assert "equal opportunity employer" not in limpio


def test_limpieza_salta_propaganda_inicial_hasta_el_rol() -> None:
    texto = (
        "About Us\nWe are the best company in the world.\n"
        "Responsibilities\nDesign the planning process.\n"
        "Benefits\nFree coffee."
    )
    limpio = _limpiar_descripcion_para_ia(texto)
    assert "best company" not in limpio
    assert "Design the planning process" in limpio
    assert "Free coffee" not in limpio


def test_limpieza_no_toca_menciones_dentro_del_rol() -> None:
    texto = "Responsibilities\nWe offer benefits including remote work."
    assert _limpiar_descripcion_para_ia(texto) == texto


def test_limpieza_con_tope_alto_de_seguridad() -> None:
    texto = "Responsibilities\n" + ("linea de rol. " * 2000)
    limpio = _limpiar_descripcion_para_ia(texto)
    assert len(limpio) == 6000
    assert limpio.startswith("Responsibilities")


def test_limpieza_todo_ruido_devuelve_el_original() -> None:
    texto = "Benefits\nFree coffee."
    assert _limpiar_descripcion_para_ia(texto) == texto


def test_la_ia_recibe_limpio_y_la_base_guarda_el_original(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descripcion = (
        "Responsibilities\nBuild data pipelines.\nBenefits\nHealth insurance."
    )
    _sembrar("OFE-0001", descripcion=descripcion)
    recibidas: dict[str, str] = {}

    def _ia(
        prompt: str, contexto: dict[str, str], purpose: str = "", **k: Any
    ) -> dict[str, str]:
        recibidas.update(contexto)
        return _respuesta("DESCARTADA", veto="v1")

    monkeypatch.setattr(evaluacion_mod, "analyze", _ia)
    res = ejecutar_evaluacion(_contexto(["OFE-0001"]))
    assert res.estado == "completada"
    assert "Health insurance" not in recibidas["descripcion_original"]
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert str(fila["descripcion_original"]) == descripcion


def test_mencion_no_reportada_en_texto_real_si_llama_a_la_ia(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar(
        "OFE-0001",
        descripcion="Rol de transformación con datos no reportada antes en otra empresa.",
    )
    llamadas = {"n": 0}

    def _ia(*a: Any, **k: Any) -> dict[str, str]:
        llamadas["n"] += 1
        return _respuesta("APROBADA")

    monkeypatch.setattr(evaluacion_mod, "analyze", _ia)
    res = ejecutar_evaluacion(_contexto(["OFE-0001"]))
    assert res.estado == "completada"
    assert llamadas["n"] == 1
    fila = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert fila is not None
    assert fila["estado"] == "aceptada_ei"


# ---------------------------------------------------------------- Abortos


def test_sin_contexto_aborta() -> None:
    res = ejecutar_evaluacion(None)
    assert res.estado == "abortada"
    assert res.codigo == "ERR-01"


def test_candidata_sin_id_aborta(temp_db_file: Path) -> None:
    ctx = RunContext(
        config_evaluacion=dict(EVALUACION_VALIDA),
        candidatas=[{"titulo": "sin id"}],
        id_corrida="COR-TEST",
    )
    res = ejecutar_evaluacion(ctx)
    assert res.estado == "abortada"
    assert res.codigo == "ERR-01"
