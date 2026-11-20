"""Pruebas del nodo Exportar ofertas (M3 v2.0, Fase 2, D76)."""

from pathlib import Path
from typing import Any

import pytest

from modules.evaluation.nodes import exportacion
from modules.evaluation.nodes.exportacion import (
    ResultadoExportacion,
    ejecutar_exportacion,
)
from modules.evaluation.run_context import RunContext
from shared.evaluacion import limpiar_descripcion_para_evaluacion
from shared.persistence import (
    escribir_fila,
    leer_candidatas_preparadas,
    leer_tabla,
)
from shared.utilidades import ahora


def _config(base: Path, tamano: int = 30) -> dict[str, Any]:
    return {
        "carpeta_base": str(base),
        "tamano_lote": tamano,
        "modelo_evaluador": "chat: operador",
        "retries": {
            "max_attempts": 2,
            "base_wait_seconds": 0,
            "max_wait_seconds": 0,
            "multiplier": 1,
        },
    }


def _oferta(identificador: str, **extra: Any) -> dict[str, Any]:
    datos: dict[str, Any] = {
        "id": identificador,
        "titulo": f"Oferta {identificador}",
        "empresa": f"Empresa {identificador}",
        "ubicacion": "Bogotá",
        "modalidad": "Remoto",
        "descripcion_original": "Responsabilidades: dirigir la operación.",
    }
    datos.update(extra)
    return datos


def _contexto(
    ofertas: list[dict[str, Any]],
    base: Path,
    *,
    id_corrida: str = "COR-0001",
    tamano: int = 30,
) -> RunContext:
    contexto = RunContext(
        config_evaluacion_manual=_config(base, tamano),
        candidatas=ofertas,
        id_corrida=id_corrida,
    )
    contexto.bloqueo_adquirido = True
    contexto.carpeta_base = base
    contexto.carpeta_lotes = base / "lotes"
    contexto.carpeta_resultados = base / "resultados"
    contexto.carpeta_rechazados = base / "resultados" / "rechazados"
    for carpeta in (base, contexto.carpeta_lotes, contexto.carpeta_resultados):
        carpeta.mkdir(parents=True, exist_ok=True)
    return contexto


def _lotes(contexto: RunContext) -> Path:
    assert contexto.carpeta_lotes is not None
    return contexto.carpeta_lotes


def _base(contexto: RunContext) -> Path:
    assert contexto.carpeta_base is not None
    return contexto.carpeta_base


def _eventos_de(id_corrida: str) -> list[dict[str, Any]]:
    return [
        evento
        for evento in leer_tabla("eventos")
        if evento.get("id_corrida") == id_corrida
    ]


def _insertar_oferta(identificador: str, estado: str = "preparada", **extra: Any) -> None:
    datos = _oferta(identificador, **extra)
    escribir_fila(
        "ofertas_descubiertas",
        {
            "id": identificador,
            "enlace": f"https://example.com/{identificador}",
            "titulo": datos["titulo"],
            "descripcion_original": datos["descripcion_original"],
            "fecha_descubrimiento": ahora(),
            "estado": estado,
        },
    )


def _escribir_ficha(
    carpeta: Path, base: str, ids: list[str], estado: str = "preparada"
) -> None:
    import json

    for identificador in ids:
        _insertar_oferta(identificador, estado)
    (carpeta / f"{base}.json").write_text(
        json.dumps(
            {
                "id_corrida": base.split("_lote_")[0],
                "lote": base.split("_lote_")[1],
                "fecha": ahora(),
                "ids": ids,
            }
        ),
        encoding="utf-8",
    )
    (carpeta / f"{base}.md").write_text(f"lote previo {base}\n", encoding="utf-8")


# ------------------------------------------------------------------ Insumos


def test_exportacion_sin_contexto_aborta() -> None:
    resultado = ejecutar_exportacion(None)
    assert isinstance(resultado, ResultadoExportacion)
    assert resultado.estado == "error"
    assert resultado.codigo == "ERR-01"


def test_exportacion_sin_candidatas_aborta(tmp_path: Path) -> None:
    contexto = _contexto([], tmp_path / "manual")
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "error"
    assert resultado.codigo == "ERR-01"
    assert list((contexto.carpeta_lotes or tmp_path).iterdir()) == []


def test_exportacion_configuracion_incompleta_aborta(tmp_path: Path) -> None:
    base = tmp_path / "manual"
    contexto = _contexto([_oferta("OFE-0001")], base)
    del contexto.config_evaluacion_manual["tamano_lote"]
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "error"
    assert resultado.codigo == "ERR-01"


@pytest.mark.parametrize(
    "clave,valor",
    [
        ("retries", None),
        ("retries", {"max_attempts": 2}),
        ("tamano_lote", 0),
        ("tamano_lote", "treinta"),
    ],
)
def test_configuracion_corrupta_aborta_sin_excepcion(
    tmp_path: Path, clave: str, valor: Any
) -> None:
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    contexto.config_evaluacion_manual[clave] = valor
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "error"
    assert resultado.codigo == "ERR-01"


def test_carpeta_de_lotes_no_escribible_aborta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def sin_permisos(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("solo lectura")

    monkeypatch.setattr(exportacion, "_verificar_escritura", sin_permisos)
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "error"
    assert resultado.codigo == "ERR-02"


def test_exportacion_carpetas_no_resueltas_aborta(tmp_path: Path) -> None:
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    contexto.carpeta_lotes = None
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "error"
    assert resultado.codigo == "ERR-01"


# -------------------------------------------------------------------- Lotes


def test_exportacion_agrupa_en_lotes_y_cuenta(tmp_path: Path) -> None:
    ofertas = [_oferta(f"OFE-{n:04d}") for n in range(1, 76)]
    contexto = _contexto(ofertas, tmp_path / "manual")
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "ok"
    assert resultado.contexto is contexto
    assert contexto.contador_lotes == 3
    assert contexto.contador_exportadas == 75
    assert contexto.contador_errores == 0
    assert sorted(p.name for p in (contexto.carpeta_lotes or tmp_path).iterdir()) == [
        "COR-0001_lote_001.json",
        "COR-0001_lote_001.md",
        "COR-0001_lote_002.json",
        "COR-0001_lote_002.md",
        "COR-0001_lote_003.json",
        "COR-0001_lote_003.md",
    ]
    eventos = [
        e for e in _eventos_de("COR-0001") if e["codigo"] == "ofertas_exportadas"
    ]
    assert len(eventos) == 3
    assert "cantidad=30" in eventos[0]["evidencia"]
    assert "cantidad=15" in eventos[2]["evidencia"]


def test_ficha_de_control_contiene_la_corrida_y_los_ids_exactos(tmp_path: Path) -> None:
    ofertas = [_oferta("OFE-0002"), _oferta("OFE-0001")]
    contexto = _contexto(ofertas, tmp_path / "manual")
    ejecutar_exportacion(contexto)
    import json

    ficha = json.loads(
        (_lotes(contexto) / "COR-0001_lote_001.json").read_text(encoding="utf-8")
    )
    assert ficha["id_corrida"] == "COR-0001"
    assert ficha["lote"] == "001"
    assert isinstance(ficha["fecha"], str) and ficha["fecha"]
    assert ficha["ids"] == ["OFE-0002", "OFE-0001"]


def test_contenido_del_lote_incluye_seis_campos_en_orden_fifo(tmp_path: Path) -> None:
    ofertas = [_oferta("OFE-0002"), _oferta("OFE-0001")]
    contexto = _contexto(ofertas, tmp_path / "manual")
    ejecutar_exportacion(contexto)
    texto = (_lotes(contexto) / "COR-0001_lote_001.md").read_text(
        encoding="utf-8"
    )
    assert "Corrida: COR-0001" in texto
    assert "Lote: 001" in texto
    assert "Ofertas: 2" in texto
    for campo in ("Título", "Empresa", "Ubicación", "Modalidad", "Descripción"):
        assert f"- {campo}:" in texto
    assert texto.index("OFE-0002") < texto.index("OFE-0001")


def test_descripcion_se_limpia_y_el_original_de_la_base_no_cambia(
    tmp_path: Path,
) -> None:
    descripcion = (
        "About us\nSomos una empresa líder\n\nThe role\nDirigir la operación diaria"
    )
    _insertar_oferta("OFE-0001", descripcion_original=descripcion)
    base = tmp_path / "manual"
    contexto = _contexto(leer_candidatas_preparadas(), base)
    ejecutar_exportacion(contexto)
    texto = (_lotes(contexto) / "COR-0001_lote_001.md").read_text(
        encoding="utf-8"
    )
    assert "Dirigir la operación diaria" in texto
    assert "Somos una empresa líder" not in texto
    fila = next(
        f
        for f in leer_tabla("ofertas_descubiertas")
        if f["id"] == "OFE-0001"
    )
    assert fila["descripcion_original"] == descripcion


def test_descripcion_larga_se_recorta_con_nota_visible(tmp_path: Path) -> None:
    contexto = _contexto(
        [_oferta("OFE-0001", descripcion_original="a" * 7000)],
        tmp_path / "manual",
    )
    ejecutar_exportacion(contexto)
    texto = (_lotes(contexto) / "COR-0001_lote_001.md").read_text(
        encoding="utf-8"
    )
    assert "recortada a 6.000 caracteres" in texto
    assert "a" * 6000 in texto
    assert "a" * 6001 not in texto


def test_campos_vacios_usan_marcador(tmp_path: Path) -> None:
    oferta = _oferta(
        "OFE-0001",
        titulo="",
        empresa="",
        ubicacion="",
        modalidad="",
        descripcion_original="",
    )
    contexto = _contexto([oferta], tmp_path / "manual")
    ejecutar_exportacion(contexto)
    texto = (_lotes(contexto) / "COR-0001_lote_001.md").read_text(
        encoding="utf-8"
    )
    for marcador in ("Título: N/A", "Empresa: N/A", "Ubicación: N/A"):
        assert marcador in texto
    assert "- Descripción:\nN/A" in texto


def test_no_escribe_en_las_ofertas(tmp_path: Path) -> None:
    _insertar_oferta("OFE-0001")
    antes = next(
        f for f in leer_tabla("ofertas_descubiertas") if f["id"] == "OFE-0001"
    )
    contexto = _contexto(leer_candidatas_preparadas(), tmp_path / "manual")
    ejecutar_exportacion(contexto)
    despues = next(
        f for f in leer_tabla("ofertas_descubiertas") if f["id"] == "OFE-0001"
    )
    assert despues["estado"] == "preparada"
    assert despues["resultado_evaluacion_inicial"] == antes[
        "resultado_evaluacion_inicial"
    ]
    assert despues["id_corrida"] == antes["id_corrida"]


def test_candidatas_del_contexto_no_se_releen_de_la_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def prohibido() -> list[dict[str, Any]]:
        raise AssertionError("el nodo no debe releer candidatas")

    monkeypatch.setattr(
        "shared.persistence.leer_candidatas_preparadas", prohibido
    )
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "ok"


# -------------------------------------------------------------- Instrucción


def test_instruccion_se_genera_desde_el_prompt_oficial(tmp_path: Path) -> None:
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    ejecutar_exportacion(contexto)
    texto = (_base(contexto) / "instruccion_evaluacion.md").read_text(
        encoding="utf-8"
    )
    assert "instruccion_evaluacion | huella:" in texto
    assert "REGLA DE ORO" in texto
    assert "FORMATO DE RESPUESTA PARA EL LOTE" in texto
    assert "una línea JSON por oferta" in texto
    assert "eje_organizacional" in texto
    assert "SISTEMAS_OPERACIONALES" in texto
    assert "NO_APLICA" in texto
    assert "entregable_principal" not in texto
    for prohibido in ("api_key", "ollama", "openrouter", "gemma"):
        assert prohibido not in texto.lower()


def test_instruccion_no_se_reescribe_si_esta_vigente(tmp_path: Path) -> None:
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    ejecutar_exportacion(contexto)
    ruta = _base(contexto) / "instruccion_evaluacion.md"
    ruta.write_text(ruta.read_text(encoding="utf-8") + "\nMARCA-MANUAL\n", encoding="utf-8")
    ejecutar_exportacion(contexto)
    assert "MARCA-MANUAL" in ruta.read_text(encoding="utf-8")


def test_instruccion_se_reescribe_si_cambia_el_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("## Objetivo\nEvalúa con cinco vetos.\n", encoding="utf-8")
    monkeypatch.setattr(exportacion, "RUTA_PROMPT", prompt)
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    ejecutar_exportacion(contexto)
    ruta = _base(contexto) / "instruccion_evaluacion.md"
    ruta.write_text(ruta.read_text(encoding="utf-8") + "\nMARCA-MANUAL\n", encoding="utf-8")
    prompt.write_text("## Objetivo\nEvalúa con siete vetos.\n", encoding="utf-8")
    ejecutar_exportacion(contexto)
    actualizado = ruta.read_text(encoding="utf-8")
    assert "MARCA-MANUAL" not in actualizado
    assert "siete vetos" in actualizado


def test_prompt_ausente_aborta_con_err01(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(exportacion, "RUTA_PROMPT", tmp_path / "no_existe.md")
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "error"
    assert resultado.codigo == "ERR-01"
    assert list((contexto.carpeta_lotes or tmp_path).iterdir()) == []


def test_escritura_de_instruccion_fallida_aborta_con_err02(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fallar(*_args: Any, **_kwargs: Any) -> None:
        raise exportacion.ErrorArchivo("sin permisos")

    monkeypatch.setattr(exportacion, "_escribir_archivo", fallar)
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "error"
    assert resultado.codigo == "ERR-02"


def test_limpieza_de_descripcion_quita_ruido_y_conserva_el_original() -> None:
    casos = {
        "": "",
        "N/A": "N/A",
        "About us\nPropaganda\nThe role\nDirigir operaciones": (
            "The role\nDirigir operaciones"
        ),
        "Benefits\nSeguro médico\nResponsabilidades\nPlanear la demanda": (
            "Responsabilidades\nPlanear la demanda"
        ),
        "Texto sin encabezados": "Texto sin encabezados",
    }
    for caso, esperado in casos.items():
        limpio, recortado = limpiar_descripcion_para_evaluacion(caso)
        assert limpio == esperado
        assert recortado is False


# ------------------------------------------------------------------ Guardián


def test_guardian_no_exporta_si_un_lote_tiene_pendientes(tmp_path: Path) -> None:
    base = tmp_path / "manual"
    contexto = _contexto([_oferta("OFE-0001")], base)
    assert contexto.carpeta_lotes is not None
    _escribir_ficha(contexto.carpeta_lotes, "COR-0009_lote_001", ["OFE-0001"])
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "ok"
    assert sorted(p.name for p in contexto.carpeta_lotes.iterdir()) == [
        "COR-0009_lote_001.json",
        "COR-0009_lote_001.md",
    ]
    assert contexto.contador_lotes == 0
    assert contexto.contador_exportadas == 0
    eventos = [e for e in _eventos_de("COR-0001") if e["codigo"] == "exportacion_omitida"]
    assert len(eventos) == 1
    assert "pendientes=1" in eventos[0]["evidencia"]


def test_guardian_bloquea_con_ficha_ilegible(tmp_path: Path) -> None:
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    assert contexto.carpeta_lotes is not None
    (_lotes(contexto) / "COR-0009_lote_001.json").write_text(
        "{no es json", encoding="utf-8"
    )
    ejecutar_exportacion(contexto)
    assert contexto.contador_lotes == 0
    eventos = [e for e in _eventos_de("COR-0001") if e["codigo"] == "exportacion_omitida"]
    assert "ficha_ilegible" in eventos[0]["evidencia"]


def test_guardian_descarta_texto_sin_ficha_y_no_bloquea(tmp_path: Path) -> None:
    """RN-09: un lote a medias se descarta, no bloquea la exportación."""
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    (_lotes(contexto) / "COR-0009_lote_001.md").write_text(
        "lote a medias", encoding="utf-8"
    )
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "ok"
    assert not (_lotes(contexto) / "COR-0009_lote_001.md").exists()
    assert (_lotes(contexto) / "COR-0001_lote_001.md").exists()
    assert contexto.contador_lotes == 1
    assert contexto.contador_errores == 1
    errores = [e for e in _eventos_de("COR-0001") if e["codigo"] == "ERR-04"]
    assert len(errores) == 1
    assert "texto_sin_ficha" in errores[0]["evidencia"]


def test_guardian_bloquea_texto_sin_ficha_con_respuesta(tmp_path: Path) -> None:
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    (_lotes(contexto) / "COR-0009_lote_001.md").write_text(
        "lote sin ficha", encoding="utf-8"
    )
    (_lotes(contexto) / "COR-0009_lote_001.jsonl").write_text(
        "{}\n", encoding="utf-8"
    )
    ejecutar_exportacion(contexto)
    assert contexto.contador_lotes == 0
    eventos = [
        e for e in _eventos_de("COR-0001") if e["codigo"] == "exportacion_omitida"
    ]
    assert "sin_ficha" in eventos[0]["evidencia"]


def test_respuesta_huerfana_se_retira(tmp_path: Path) -> None:
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    (_lotes(contexto) / "COR-0009_lote_001.jsonl").write_text(
        "{}\n", encoding="utf-8"
    )
    ejecutar_exportacion(contexto)
    assert not (_lotes(contexto) / "COR-0009_lote_001.jsonl").exists()
    assert contexto.contador_lotes == 1


def test_guardian_retira_resueltos_aunque_otro_bloquee(tmp_path: Path) -> None:
    contexto = _contexto([_oferta("OFE-0002")], tmp_path / "manual")
    lotes = _lotes(contexto)
    _escribir_ficha(lotes, "COR-0008_lote_001", ["OFE-0001"], "aceptada_ei")
    _escribir_ficha(lotes, "COR-0009_lote_001", ["OFE-0002"], "preparada")
    ejecutar_exportacion(contexto)
    assert not any(p.name.startswith("COR-0008") for p in lotes.iterdir())
    assert any(p.name.startswith("COR-0009") for p in lotes.iterdir())
    assert contexto.contador_lotes == 0


def test_guardian_retira_lotes_resueltos_y_sus_partes(tmp_path: Path) -> None:
    base = tmp_path / "manual"
    contexto = _contexto([_oferta("OFE-0002")], base)
    assert contexto.carpeta_lotes is not None
    _escribir_ficha(
        contexto.carpeta_lotes, "COR-0009_lote_001", ["OFE-0001"], "aceptada_ei"
    )
    for sufijo in (".jsonl", "_parte2.jsonl"):
        (_lotes(contexto) / f"COR-0009_lote_001{sufijo}").write_text(
            "{}\n", encoding="utf-8"
        )
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "ok"
    assert not any(
        p.name.startswith("COR-0009_lote_001")
        for p in contexto.carpeta_lotes.iterdir()
    )
    assert (_lotes(contexto) / "COR-0001_lote_001.md").exists()
    eventos = [e for e in _eventos_de("COR-0001") if e["codigo"] == "lotes_retirados"]
    assert len(eventos) == 1
    assert "archivos=4" in eventos[0]["evidencia"]


def test_guardian_con_error_de_base_aborta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fallar(*_args: Any, **_kwargs: Any) -> dict[str, str]:
        raise RuntimeError("base no disponible")

    monkeypatch.setattr(exportacion, "leer_estados_ofertas", fallar)
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    assert contexto.carpeta_lotes is not None
    _escribir_ficha(
        contexto.carpeta_lotes, "COR-0009_lote_001", ["OFE-0001"]
    )
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "error"
    assert resultado.codigo == "ERR-01"


# ---------------------------------------------------------- Fallos por lote


def test_fallo_de_escritura_descarta_el_lote_y_continua(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = exportacion._escribir_par

    def fallar_primero(*args: Any, **kwargs: Any) -> None:
        if "_lote_001" in args[0].name:
            raise exportacion.ErrorArchivo("fallo forzado")
        return original(*args, **kwargs)

    monkeypatch.setattr(exportacion, "_escribir_par", fallar_primero)
    ofertas = [_oferta("OFE-0001"), _oferta("OFE-0002")]
    contexto = _contexto(ofertas, tmp_path / "manual", tamano=1)
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "ok"
    assert not (_lotes(contexto) / "COR-0001_lote_001.md").exists()
    assert not (_lotes(contexto) / "COR-0001_lote_001.json").exists()
    assert (_lotes(contexto) / "COR-0001_lote_002.md").exists()
    assert contexto.contador_errores == 1
    assert contexto.contador_lotes == 1
    errores = [e for e in _eventos_de("COR-0001") if e["codigo"] == "ERR-03"]
    assert len(errores) == 1


def test_un_reintento_exitoso_escribe_el_lote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = exportacion._escribir_par
    llamadas = {"n": 0}

    def fallar_una_vez(*args: Any, **kwargs: Any) -> None:
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise exportacion.ErrorArchivo("fallo transitorio")
        return original(*args, **kwargs)

    monkeypatch.setattr(exportacion, "_escribir_par", fallar_una_vez)
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "ok"
    assert llamadas["n"] == 2
    assert (_lotes(contexto) / "COR-0001_lote_001.md").exists()
    assert contexto.contador_errores == 0


def test_ficha_inconsistente_descarta_el_lote_y_continua(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = exportacion._ficha_del_lote
    import json

    def ficha_mal_primer_lote(*args: Any, **kwargs: Any) -> str:
        if args[1] == 1:
            return json.dumps({"ids": ["OFE-9999"]})
        return original(*args, **kwargs)

    monkeypatch.setattr(exportacion, "_ficha_del_lote", ficha_mal_primer_lote)
    contexto = _contexto(
        [_oferta("OFE-0001"), _oferta("OFE-0002")],
        tmp_path / "manual",
        tamano=1,
    )
    ejecutar_exportacion(contexto)
    assert not (_lotes(contexto) / "COR-0001_lote_001.md").exists()
    assert (_lotes(contexto) / "COR-0001_lote_002.md").exists()
    assert contexto.contador_errores == 1
    errores = [e for e in _eventos_de("COR-0001") if e["codigo"] == "ERR-04"]
    assert len(errores) == 1


def test_fallo_al_registrar_el_suceso_no_detiene(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fallar_suceso(*args: Any, **kwargs: Any) -> None:
        if kwargs.get("codigo") == "ofertas_exportadas":
            raise RuntimeError("eventos no disponibles")

    monkeypatch.setattr(exportacion, "registrar_evento", fallar_suceso)
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    resultado = ejecutar_exportacion(contexto)
    assert resultado.estado == "ok"
    assert (_lotes(contexto) / "COR-0001_lote_001.md").exists()
    assert contexto.contador_exportadas == 1
    assert contexto.contador_lotes == 1


def test_eventos_llevan_corrida_y_fuente_na(tmp_path: Path) -> None:
    contexto = _contexto([_oferta("OFE-0001")], tmp_path / "manual")
    ejecutar_exportacion(contexto)
    eventos = _eventos_de("COR-0001")
    assert eventos
    assert all(e["id_corrida"] == "COR-0001" for e in eventos)
    assert all(e["fuente_id"] == "N/A" for e in eventos)
    assert all(e["id_oferta"] == "N/A" for e in eventos)
