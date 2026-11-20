"""Pruebas del nodo Importar evaluaciones (M3 v2.0, Fase 3, D76)."""

import json
from pathlib import Path
from typing import Any

import pytest

from modules.evaluation.nodes import importacion
from modules.evaluation.nodes.importacion import ejecutar_importacion
from modules.evaluation.run_context import RunContext
from shared.persistence import actualizar_fila, escribir_fila, leer_tabla
from shared.utilidades import ahora

_CORRIDA = "COR-0001"


def _config(base: Path, tamano: int = 2) -> dict[str, Any]:
    return {
        "carpeta_base": str(base),
        "tamano_lote": tamano,
        "modelo_evaluador": "chat: gemini",
        "retries": {
            "max_attempts": 2,
            "base_wait_seconds": 0,
            "max_wait_seconds": 0,
            "multiplier": 1,
        },
    }


def _insertar(
    identificador: str, estado: str = "preparada", descripcion: str = "Dirigir operaciones"
) -> None:
    escribir_fila(
        "ofertas_descubiertas",
        {
            "id": identificador,
            "enlace": f"https://example.com/{identificador}",
            "titulo": f"Oferta {identificador}",
            "descripcion_original": descripcion,
            "fecha_descubrimiento": ahora(),
            "estado": estado,
        },
    )


def _contexto(
    ofertas: list[str], base: Path, *, id_corrida: str = _CORRIDA
) -> RunContext:
    for identificador in ofertas:
        _insertar(identificador)
    contexto = RunContext(
        config_evaluacion_manual=_config(base),
        id_corrida=id_corrida,
    )
    contexto.bloqueo_adquirido = True
    contexto.carpeta_base = base
    contexto.carpeta_lotes = base / "lotes"
    contexto.carpeta_resultados = base / "resultados"
    contexto.carpeta_rechazados = base / "resultados" / "rechazados"
    for carpeta in (
        base,
        contexto.carpeta_lotes,
        contexto.carpeta_resultados,
        contexto.carpeta_rechazados,
    ):
        carpeta.mkdir(parents=True, exist_ok=True)
    return contexto


def _lotes(contexto: RunContext) -> Path:
    assert contexto.carpeta_lotes is not None
    return contexto.carpeta_lotes


def _rechazados(contexto: RunContext) -> Path:
    assert contexto.carpeta_rechazados is not None
    return contexto.carpeta_rechazados


def _lote(contexto: RunContext, ids: list[str], base: str = "COR-0009_lote_001") -> None:
    assert contexto.carpeta_lotes is not None
    (contexto.carpeta_lotes / f"{base}.json").write_text(
        json.dumps(
            {
                "id_corrida": base.split("_lote_")[0],
                "lote": base.split("_lote_")[1],
                "fecha": ahora(),
                "ids": ids,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (contexto.carpeta_lotes / f"{base}.md").write_text(
        f"# Lote {base}\n\n" + "\n".join(f"- {i}" for i in ids) + "\n",
        encoding="utf-8",
    )


def _linea(identificador: str, **extra: Any) -> str:
    datos: dict[str, Any] = {
        "id": identificador,
        "eje_organizacional": "SISTEMAS_OPERACIONALES",
        "v1": "PASS",
        "v2": "PASS",
        "v3": "PASS",
        "v4": "PASS",
        "v5": "PASS",
        "decision": "APROBADA",
        "justificacion": "Solicita liderar la operación y diseñar planes.",
    }
    datos.update(extra)
    return json.dumps(datos, ensure_ascii=False)


def _respuesta(
    contexto: RunContext,
    nombre: str,
    lineas: list[str],
    *,
    registrar: bool = True,
) -> Path:
    assert contexto.carpeta_resultados is not None
    ruta = contexto.carpeta_resultados / nombre
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    if registrar:
        contexto.archivos_resultados = [ruta]
    return ruta


def _oferta(identificador: str) -> dict[str, Any]:
    return next(f for f in leer_tabla("ofertas_descubiertas") if f["id"] == identificador)


def _eventos(
    codigo: str | None = None, id_corrida: str = _CORRIDA
) -> list[dict[str, Any]]:
    return [
        evento
        for evento in leer_tabla("eventos")
        if evento["id_corrida"] == id_corrida
        and (codigo is None or evento["codigo"] == codigo)
    ]


def _preparar(
    tmp_path: Path, ids: list[str] | None = None
) -> tuple[RunContext, str]:
    identificadores = ids or ["OFE-0001"]
    contexto = _contexto(identificadores, tmp_path / "manual")
    base = "COR-0009_lote_001"
    _lote(contexto, identificadores, base)
    return contexto, base


def _rechazo() -> dict[str, Any]:
    eventos = _eventos("evaluacion_rechazada")
    assert len(eventos) == 1
    return eventos[0]


# ------------------------------------------------------------------ Insumos


def test_importacion_sin_contexto_aborta() -> None:
    resultado = ejecutar_importacion(None)
    assert resultado.estado == "error"
    assert resultado.codigo == "ERR-01"


def test_importacion_configuracion_corrupta_aborta(tmp_path: Path) -> None:
    contexto = _contexto(["OFE-0001"], tmp_path / "manual")
    contexto.config_evaluacion_manual["tamano_lote"] = 0
    resultado = ejecutar_importacion(contexto)
    assert resultado.estado == "error"
    assert resultado.codigo == "ERR-01"


def test_importacion_carpetas_no_resueltas_aborta(tmp_path: Path) -> None:
    contexto = _contexto(["OFE-0001"], tmp_path / "manual")
    contexto.carpeta_lotes = None
    resultado = ejecutar_importacion(contexto)
    assert resultado.estado == "error"
    assert resultado.codigo == "ERR-01"


# -------------------------------------------------------------- Emparejamiento


def test_respuesta_sin_lote_se_aparta_y_no_toca_la_oferta(tmp_path: Path) -> None:
    contexto, _ = _preparar(tmp_path)
    ruta = _respuesta(contexto, "COR-0009_lote_099.jsonl", [_linea("OFE-0001")])
    resultado = ejecutar_importacion(contexto)
    assert resultado.estado == "ok"
    assert _oferta("OFE-0001")["estado"] == "preparada"
    assert not ruta.exists()
    assert (_rechazados(contexto) / ruta.name).exists()
    evento = _eventos("ERR-02")
    assert len(evento) == 1
    assert "lote_ausente" in evento[0]["evidencia"]
    assert contexto.archivos_rechazados == [ruta.name]


def test_respuesta_con_nombre_no_reconocido_se_aparta(tmp_path: Path) -> None:
    contexto, _ = _preparar(tmp_path)
    ruta = _respuesta(contexto, "respuesta.txt", [_linea("OFE-0001")])
    ejecutar_importacion(contexto)
    assert not ruta.exists()
    assert (_rechazados(contexto) / ruta.name).exists()
    assert "nombre_no_reconocido" in _eventos("ERR-02")[0]["evidencia"]


def test_respuesta_con_ficha_ilegible_se_aparta(tmp_path: Path) -> None:
    contexto, base = _preparar(tmp_path, ["OFE-0001", "OFE-0002"])
    assert contexto.carpeta_lotes is not None
    (contexto.carpeta_lotes / f"{base}.json").write_text(
        "{no es json", encoding="utf-8"
    )
    ruta = _respuesta(contexto, f"{base}.jsonl", [_linea("OFE-0001")])
    ejecutar_importacion(contexto)
    assert not ruta.exists()
    assert "ficha_ilegible" in _eventos("ERR-02")[0]["evidencia"]
    assert _oferta("OFE-0001")["estado"] == "preparada"


def test_archivo_solo_adornos_se_aparta_y_no_aplica(tmp_path: Path) -> None:
    contexto, base = _preparar(tmp_path)
    ruta = _respuesta(
        contexto, f"{base}.jsonl", ["```json", "texto sin llaves", "```"]
    )
    ejecutar_importacion(contexto)
    assert not ruta.exists()
    assert _oferta("OFE-0001")["estado"] == "preparada"
    assert "archivo_sin_lineas" in _eventos("ERR-03")[0]["evidencia"]


def test_adornos_del_chat_se_ignoran(tmp_path: Path) -> None:
    contexto, base = _preparar(tmp_path)
    _respuesta(
        contexto,
        f"{base}.jsonl",
        [
            "```json",
            _linea("OFE-0001", justificacion="DENTRO DEL BLOQUE"),
            "```",
            "texto suelto del chat",
            "",
            _linea("OFE-0001", justificacion="FUERA DEL BLOQUE"),
        ],
    )
    ejecutar_importacion(contexto)
    assert _oferta("OFE-0001")["estado"] == "aceptada_ei"
    resultado = json.loads(_oferta("OFE-0001")["resultado_evaluacion_inicial"])
    assert resultado["justificacion"] == "FUERA DEL BLOQUE"


# ------------------------------------------------------------- Validación


@pytest.mark.parametrize(
    "extra,motivo,codigo",
    [
        ({"v2": None}, "veto_ausente", "ERR-03"),
        ({"v2": "MAYBE"}, "veto_invalido", "ERR-03"),
        ({"v3": "FAIL"}, "decision_incoherente", "ERR-05"),
        ({"decision": "DESCARTADA"}, "decision_incoherente", "ERR-05"),
        ({"justificacion": "N/A"}, "justificacion_vacia", "ERR-05"),
        ({"eje_organizacional": ""}, "eje_invalido", "ERR-05"),
        ({"eje_organizacional": "OPERACIONAL"}, "eje_invalido", "ERR-05"),
        ({"eje_organizacional": "NO_APLICA"}, "eje_incoherente", "ERR-05"),
        (
            {
                "eje_organizacional": "SISTEMAS_OPERACIONALES",
                "v1": "FAIL",
                "decision": "DESCARTADA",
            },
            "eje_incoherente",
            "ERR-05",
        ),
        ({"decision": "INDETERMINADA"}, "decision_invalida", "ERR-05"),
    ],
)
def test_lineas_invalidas_se_rechazan(
    tmp_path: Path, extra: dict[str, Any], motivo: str, codigo: str
) -> None:
    contexto, base = _preparar(tmp_path)
    if "v2" in extra and extra["v2"] is None:
        datos = json.loads(_linea("OFE-0001"))
        del datos["v2"]
        linea = json.dumps(datos)
    else:
        linea = _linea("OFE-0001", **extra)
    _respuesta(contexto, f"{base}.jsonl", [linea])
    ejecutar_importacion(contexto)
    evento = _rechazo()
    assert f"codigo={codigo}" in evento["evidencia"]
    assert f"motivo={motivo}" in evento["evidencia"]
    assert evento["id_oferta"] == "OFE-0001"
    assert _oferta("OFE-0001")["estado"] == "preparada"
    assert contexto.contador_rechazadas == 1


def test_linea_ilegible_se_rechaza_como_err03(tmp_path: Path) -> None:
    contexto, base = _preparar(tmp_path)
    _respuesta(contexto, f"{base}.jsonl", ["{esto no es json}"])
    ejecutar_importacion(contexto)
    assert "codigo=ERR-03" in _rechazo()["evidencia"]


def test_id_ausente_se_rechaza_como_err03(tmp_path: Path) -> None:
    contexto, base = _preparar(tmp_path)
    datos = json.loads(_linea("OFE-0001"))
    del datos["id"]
    _respuesta(contexto, f"{base}.jsonl", [json.dumps(datos)])
    ejecutar_importacion(contexto)
    assert "codigo=ERR-03" in _rechazo()["evidencia"]


def test_eje_ausente_se_rechaza_como_err05(tmp_path: Path) -> None:
    contexto, base = _preparar(tmp_path)
    datos = json.loads(_linea("OFE-0001"))
    del datos["eje_organizacional"]
    _respuesta(contexto, f"{base}.jsonl", [json.dumps(datos)])
    ejecutar_importacion(contexto)
    rechazo = _rechazo()
    assert "codigo=ERR-05" in rechazo["evidencia"]
    assert "motivo=falta_eje_organizacional" in rechazo["evidencia"]
    assert _oferta("OFE-0001")["estado"] == "preparada"


def test_eje_no_aplica_se_admite_en_descarte_sin_descripcion(tmp_path: Path) -> None:
    contexto = _contexto([], tmp_path / "manual")
    _insertar("OFE-0001", descripcion="N/A")
    assert contexto.carpeta_lotes is not None
    for carpeta in (contexto.carpeta_lotes,):
        assert carpeta.exists()
    (contexto.carpeta_lotes / "COR-0009_lote_001.json").write_text(
        json.dumps({"ids": ["OFE-0001"]}), encoding="utf-8"
    )
    (contexto.carpeta_lotes / "COR-0009_lote_001.md").write_text("lote", encoding="utf-8")
    _respuesta(
        contexto,
        "COR-0009_lote_001.jsonl",
        [
            _linea(
                "OFE-0001",
                eje_organizacional="NO_APLICA",
                v1="FAIL",
                v3="FAIL",
                decision="DESCARTADA",
            )
        ],
    )
    resultado = ejecutar_importacion(contexto)
    assert resultado.estado == "ok"
    assert _oferta("OFE-0001")["estado"] == "descartada_ei"
    assert json.loads(_oferta("OFE-0001")["resultado_evaluacion_inicial"])[
        "eje_organizacional"
    ] == "NO_APLICA"


@pytest.mark.parametrize(
    "id_linea,motivo",
    [
        ("OFE-9999", "oferta_inexistente"),
        ("OFE-9998", "fuera_de_lote"),
    ],
)
def test_oferta_inexistente_o_fuera_de_lote(
    tmp_path: Path, id_linea: str, motivo: str
) -> None:
    contexto = _contexto([], tmp_path / "manual")
    base = "COR-0009_lote_001"
    if motivo == "fuera_de_lote":
        _insertar("OFE-0001")
        _insertar(id_linea)
        _lote(contexto, ["OFE-0001"], base)
    else:
        # La oferta figura en la ficha pero no existe en la base.
        _lote(contexto, [id_linea], base)
    _respuesta(contexto, f"{base}.jsonl", [_linea(id_linea)])
    ejecutar_importacion(contexto)
    assert f"motivo={motivo}" in _rechazo()["evidencia"]
    if motivo == "fuera_de_lote":
        assert _oferta("OFE-0001")["estado"] == "preparada"


def test_oferta_ya_evaluada_se_rechaza(tmp_path: Path) -> None:
    contexto, base = _preparar(tmp_path)
    actualizar_fila(
        "ofertas_descubiertas", "OFE-0001", {"estado": "aceptada_ei"}
    )
    _respuesta(contexto, f"{base}.jsonl", [_linea("OFE-0001")])
    ejecutar_importacion(contexto)
    assert "motivo=no_pendiente" in _rechazo()["evidencia"]


def test_linea_repetida_se_rechaza(tmp_path: Path) -> None:
    contexto, base = _preparar(tmp_path, ["OFE-0001", "OFE-0002"])
    _respuesta(
        contexto,
        f"{base}.jsonl",
        [_linea("OFE-0001"), _linea("OFE-0001", justificacion="REPETIDA")],
    )
    ejecutar_importacion(contexto)
    assert _oferta("OFE-0001")["estado"] == "aceptada_ei"
    assert "motivo=repetida" in _rechazo()["evidencia"]


# -------------------------------------------------------------- Aplicación


def test_aplicacion_guarda_estado_resultado_evento_y_contador(tmp_path: Path) -> None:
    contexto, base = _preparar(tmp_path)
    _respuesta(contexto, f"{base}.jsonl", [_linea("OFE-0001")])
    resultado = ejecutar_importacion(contexto)
    assert resultado.estado == "ok"
    assert _oferta("OFE-0001")["estado"] == "aceptada_ei"
    almacenado = json.loads(_oferta("OFE-0001")["resultado_evaluacion_inicial"])
    assert almacenado == {
        "eje_organizacional": "SISTEMAS_OPERACIONALES",
        "v1": "PASS",
        "v2": "PASS",
        "v3": "PASS",
        "v4": "PASS",
        "v5": "PASS",
        "decision": "APROBADA",
        "justificacion": "Solicita liderar la operación y diseñar planes.",
        "evaluador": "chat: gemini",
    }
    evento = _eventos("oferta_aprobada")
    assert len(evento) == 1
    assert evento[0]["id_oferta"] == "OFE-0001"
    assert "chat: gemini" in evento[0]["evidencia"]
    assert contexto.contador_aprobadas == 1
    assert contexto.contador_descartadas == 0


def test_descarte_guarda_primer_veto_y_evento(tmp_path: Path) -> None:
    contexto, base = _preparar(tmp_path)
    _respuesta(
        contexto,
        f"{base}.jsonl",
        [
            _linea(
                "OFE-0001",
                v2="FAIL",
                v5="FAIL",
                decision="DESCARTADA",
                justificacion="Falla dos vetos concretos.",
            )
        ],
    )
    ejecutar_importacion(contexto)
    assert _oferta("OFE-0001")["estado"] == "descartada_ei"
    almacenado = json.loads(_oferta("OFE-0001")["resultado_evaluacion_inicial"])
    assert almacenado["evaluador"] == "chat: gemini"
    evento = _eventos("oferta_descartada")
    assert len(evento) == 1
    assert "veto=v2" in evento[0]["evidencia"]
    assert contexto.contador_descartadas == 1


def test_no_sobrescribe_la_corrida_de_descubrimiento(tmp_path: Path) -> None:
    contexto, base = _preparar(tmp_path)
    antes = _oferta("OFE-0001")["id_corrida"]
    _respuesta(contexto, f"{base}.jsonl", [_linea("OFE-0001")])
    ejecutar_importacion(contexto)
    assert _oferta("OFE-0001")["id_corrida"] == antes


def test_fallo_de_base_en_aplicacion_aborta_con_err06(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fallar(*_args: Any, **_kwargs: Any) -> bool:
        raise RuntimeError("base no disponible")

    monkeypatch.setattr(importacion, "actualizar_fila", fallar)
    contexto, base = _preparar(tmp_path)
    _respuesta(contexto, f"{base}.jsonl", [_linea("OFE-0001")])
    resultado = ejecutar_importacion(contexto)
    assert resultado.estado == "error"
    assert resultado.codigo == "ERR-06"
    assert len(_eventos("ERR-06")) == 1
    assert _oferta("OFE-0001")["estado"] == "preparada"


def test_reintento_exitoso_aplica_la_oferta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = actualizar_fila
    llamadas = {"n": 0}

    def fallar_una_vez(*args: Any, **kwargs: Any) -> bool:
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise RuntimeError("fallo transitorio")
        return original(*args, **kwargs)

    monkeypatch.setattr(importacion, "actualizar_fila", fallar_una_vez)
    contexto, base = _preparar(tmp_path)
    _respuesta(contexto, f"{base}.jsonl", [_linea("OFE-0001")])
    resultado = ejecutar_importacion(contexto)
    assert resultado.estado == "ok"
    assert llamadas["n"] == 2
    assert _oferta("OFE-0001")["estado"] == "aceptada_ei"


# ----------------------------------------------------------- Cierre de lote


def test_lote_completo_se_borra_y_deja_suceso(tmp_path: Path) -> None:
    contexto, base = _preparar(tmp_path)
    contexto.archivos_resultados = [
        _respuesta(contexto, f"{base}.jsonl", [_linea("OFE-0001")], registrar=False)
    ]
    ejecutar_importacion(contexto)
    assert contexto.lotes_cerrados == ["COR-0009_lote_001"]
    assert contexto.lotes_conservados == []
    assert contexto.contador_lotes == 1
    assert not any(
        p.name.startswith("COR-0009_lote_001")
        for p in (contexto.carpeta_lotes or tmp_path).iterdir()
    )
    evento = _eventos("evaluaciones_importadas")
    assert len(evento) == 1
    assert "aplicadas=1" in evento[0]["evidencia"]
    assert "eliminados=3" in evento[0]["evidencia"]


def test_lote_con_faltantes_se_conserva_y_se_informa(tmp_path: Path) -> None:
    contexto, base = _preparar(tmp_path, ["OFE-0001", "OFE-0002"])
    respuesta = _respuesta(contexto, f"{base}.jsonl", [_linea("OFE-0001")])
    ejecutar_importacion(contexto)
    assert respuesta.exists()
    assert (_lotes(contexto) / f"{base}.json").exists()
    assert (_lotes(contexto) / f"{base}.md").exists()
    assert contexto.lotes_conservados == [base]
    assert contexto.faltantes_por_lote[base] == ["OFE-0002"]
    assert _oferta("OFE-0002")["estado"] == "preparada"
    conservado = _eventos("lote_conservado")
    assert len(conservado) == 1
    assert "ids=OFE-0002" in conservado[0]["evidencia"]
    assert "faltantes=1" in _eventos("evaluaciones_importadas")[0]["evidencia"]


def test_partes_se_unen_en_orden_numerico(tmp_path: Path) -> None:
    contexto, base = _preparar(tmp_path)
    _respuesta(contexto, f"{base}.jsonl", [], registrar=False)
    parte2 = _respuesta(
        contexto,
        f"{base}_parte2.jsonl",
        [_linea("OFE-0001", justificacion="DE LA PARTE DOS")],
        registrar=False,
    )
    parte10 = _respuesta(
        contexto,
        f"{base}_parte10.jsonl",
        [_linea("OFE-0001", justificacion="DE LA PARTE DIEZ")],
        registrar=False,
    )
    contexto.archivos_resultados = [parte10, parte2]
    ejecutar_importacion(contexto)
    assert _oferta("OFE-0001")["estado"] == "aceptada_ei"
    assert json.loads(_oferta("OFE-0001")["resultado_evaluacion_inicial"])[
        "justificacion"
    ] == "DE LA PARTE DOS"


def test_multiples_lotes_se_procesan_en_orden(tmp_path: Path) -> None:
    contexto = _contexto(["OFE-0001", "OFE-0002"], tmp_path / "manual")
    for numero in (1, 2):
        base = f"COR-0009_lote_{numero:03d}"
        _lote(contexto, [f"OFE-000{numero}"], base)
    primero = _respuesta(
        contexto, "COR-0009_lote_001.jsonl", [_linea("OFE-0001")], registrar=False
    )
    segundo = _respuesta(
        contexto, "COR-0009_lote_002.jsonl", [_linea("OFE-0002")], registrar=False
    )
    contexto.archivos_resultados = [segundo, primero]
    ejecutar_importacion(contexto)
    assert contexto.lotes_cerrados == [
        "COR-0009_lote_001",
        "COR-0009_lote_002",
    ]
    assert len(_eventos("evaluaciones_importadas")) == 2
    assert _oferta("OFE-0002")["estado"] == "aceptada_ei"


def test_misma_oferta_en_dos_lotes_no_se_aplica_dos_veces(tmp_path: Path) -> None:
    contexto = _contexto(["OFE-0001"], tmp_path / "manual")
    for numero in (1, 2):
        _lote(contexto, ["OFE-0001"], f"COR-0009_lote_{numero:03d}")
    primero = _respuesta(
        contexto, "COR-0009_lote_001.jsonl", [_linea("OFE-0001")], registrar=False
    )
    segundo = _respuesta(
        contexto,
        "COR-0009_lote_002.jsonl",
        [_linea("OFE-0001", justificacion="SEGUNDA APLICACION")],
        registrar=False,
    )
    contexto.archivos_resultados = [primero, segundo]
    ejecutar_importacion(contexto)
    assert _oferta("OFE-0001")["estado"] == "aceptada_ei"
    assert len(_eventos("oferta_aprobada")) == 1
    rechazos = _eventos("evaluacion_rechazada")
    assert len(rechazos) == 1
    assert "motivo=no_pendiente" in rechazos[0]["evidencia"]


def test_fallo_al_borrar_no_desaplica_la_oferta_y_se_informa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_borrar(*_args: Any, **_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(importacion, "_borrar", no_borrar)
    contexto, base = _preparar(tmp_path)
    contexto.archivos_resultados = [
        _respuesta(contexto, f"{base}.jsonl", [_linea("OFE-0001")], registrar=False)
    ]
    ejecutar_importacion(contexto)
    assert _oferta("OFE-0001")["estado"] == "aceptada_ei"
    assert contexto.lotes_cerrados == [base]
    assert len(contexto.archivos_no_eliminados) == 3
    assert "no_eliminados=3" in _eventos("evaluaciones_importadas")[0]["evidencia"]


def test_cadena_exportacion_e_importacion(tmp_path: Path) -> None:
    from modules.evaluation.nodes.exportacion import ejecutar_exportacion

    contexto = _contexto(["OFE-0001", "OFE-0002"], tmp_path / "manual")
    contexto.candidatas = [{"id": "OFE-0001"}, {"id": "OFE-0002"}]
    contexto.hubo_candidatas = True
    assert ejecutar_exportacion(contexto).estado == "ok"
    base = "COR-0001_lote_001"
    ficha = json.loads(
        (_lotes(contexto) / f"{base}.json").read_text(encoding="utf-8")
    )
    assert ficha["ids"] == ["OFE-0001", "OFE-0002"]
    _respuesta(contexto, f"{base}.jsonl", [_linea(i) for i in ficha["ids"]])
    resultado = ejecutar_importacion(contexto)
    assert resultado.estado == "ok"
    assert _oferta("OFE-0001")["estado"] == "aceptada_ei"
    assert _oferta("OFE-0002")["estado"] == "aceptada_ei"
    assert not (_lotes(contexto) / f"{base}.md").exists()
