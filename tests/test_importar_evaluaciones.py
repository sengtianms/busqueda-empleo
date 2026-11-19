"""Pruebas del comando de importación del operador (Fase 4, D76)."""

import json
from pathlib import Path
from typing import Any

import pytest

from modules.evaluation.nodes.finalizar_manual import ResultadoFinalizarManual
from scripts import importar_evaluaciones as comando
from scripts.notificar_veredicto import componer_importacion
from shared.persistence import escribir_fila
from shared.utilidades import ahora


def _informe(motivo: str = "corrida_completada", **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "proceso": "importacion",
        "id_corrida": "COR-0002",
        "aprobadas": 2,
        "descartadas": 1,
        "rechazadas": 0,
        "lotes_cerrados": ["COR-0002_lote_001"],
        "lotes_conservados": [],
        "faltantes": {},
        "archivos_rechazados": [],
        "archivos_no_eliminados": [],
    }
    base.update(extra)
    return base


def _resultado(
    motivo: str = "corrida_completada", informe: dict[str, Any] | None = None
) -> ResultadoFinalizarManual:
    return ResultadoFinalizarManual(
        estado="ok", codigo=motivo, informe=informe or _informe(motivo)
    )


def _simular(
    monkeypatch: pytest.MonkeyPatch, motivo: str, informe: dict[str, Any] | None = None
) -> list[tuple[str, str]]:
    avisos: list[tuple[str, str]] = []
    monkeypatch.setattr(
        comando, "ejecutar_flujo_importacion", lambda: _resultado(motivo, informe)
    )
    monkeypatch.setattr(
        comando, "enviar_aviso", lambda cuerpo, urgencia: avisos.append((cuerpo, urgencia))
    )
    return avisos


# ------------------------------------------------------------ Informe en pantalla


def test_informe_completada() -> None:
    texto = comando.componer_informe("corrida_completada", _informe())
    assert "Corrida: COR-0002" in texto
    assert "Resultado: completada" in texto
    assert "2 aprobadas / 1 descartadas" in texto
    assert "Lotes cerrados: 1 · Conservados: 0" in texto
    assert "Ofertas que siguen pendientes: ninguna" in texto


def test_informe_conservado_nombra_las_ofertas_pendientes() -> None:
    texto = comando.componer_informe(
        "corrida_completada",
        _informe(
            lotes_conservados=["COR-0002_lote_002"],
            faltantes={"COR-0002_lote_002": ["OFE-0009", "OFE-0010"]},
        ),
    )
    assert "COR-0002_lote_002: quedan pendientes OFE-0009, OFE-0010" in texto
    assert "Ofertas que siguen pendientes: 2" in texto


def test_informe_sin_resultados_no_muestra_cifras_falsas() -> None:
    texto = comando.componer_informe("sin_resultados", _informe("sin_resultados"))
    assert "No había respuestas en la carpeta: no se aplicó nada." in texto
    assert "aprobadas" not in texto


def test_informe_enumera_archivos_apartados_y_no_borrados() -> None:
    texto = comando.componer_informe(
        "corrida_completada",
        _informe(
            archivos_rechazados=["respuesta.txt"],
            archivos_no_eliminados=["COR-0002_lote_001.json"],
        ),
    )
    assert "Archivos apartados: respuesta.txt" in texto
    assert "Archivos que no se pudieron borrar: COR-0002_lote_001.json" in texto


# --------------------------------------------------------------- Aviso de escritorio


def test_aviso_completada_con_pendientes() -> None:
    cuerpo, urgencia = componer_importacion(
        "corrida_completada",
        _informe(
            lotes_conservados=["COR-0002_lote_002"],
            faltantes={"COR-0002_lote_002": ["OFE-0009", "OFE-0010"]},
        ),
    )
    assert urgencia == "normal"
    assert "Importación COR-0002: 2 aprobadas · 1 descartadas" in cuerpo
    assert "2 ofertas siguen pendientes en 1 lote" in cuerpo


@pytest.mark.parametrize(
    "motivo,urgencia,fragmento",
    [
        ("sin_resultados", "normal", "no había respuestas"),
        ("error_total", "critical", "nada aplicado"),
        ("aborto", "critical", "interrumpida: aborto"),
        ("concurrencia", "critical", "interrumpida: concurrencia"),
    ],
)
def test_aviso_de_los_demas_motivos(
    motivo: str, urgencia: str, fragmento: str
) -> None:
    cuerpo, nivel = componer_importacion(motivo, _informe(motivo))
    assert nivel == urgencia
    assert fragmento in cuerpo


# -------------------------------------------------------------------- Ejecución


def test_importar_exitoso_muestra_informe_y_aviso(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    avisos = _simular(monkeypatch, "corrida_completada")
    codigo, texto = comando.importar()
    capsys.readouterr()
    assert codigo == 0
    assert "Corrida: COR-0002" in texto
    assert len(avisos) == 1
    assert avisos[0][1] == "normal"


def test_importar_sin_resultados_tambien_es_exito(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _simular(monkeypatch, "sin_resultados")
    codigo, texto = comando.importar()
    assert codigo == 0
    assert "no se aplicó nada" in texto


def test_importar_con_fallo_devuelve_uno(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    avisos = _simular(monkeypatch, "error_total")
    codigo, _ = comando.importar()
    assert codigo == 1
    assert avisos[0][1] == "critical"


@pytest.mark.parametrize(
    "motivo", ["concurrencia", "aborto", "error_critico", "error_total"]
)
def test_importar_informa_el_motivo_real_de_una_corrida_cerrada(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch, motivo: str
) -> None:
    avisos = _simular(monkeypatch, motivo)
    codigo, texto = comando.importar()
    assert codigo == 1
    assert "Corrida: COR-0002" in texto
    assert comando._ETIQUETAS[motivo] in texto
    assert "No se registró ninguna corrida" not in texto
    assert avisos[0][1] == "critical"


def test_informe_real_de_concurrencia_incluye_la_corrida(
    temp_db_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from modules.evaluation.orchestrator_manual import (
        ejecutar_flujo_importacion as flujo_real,
    )
    from shared.config import load as load_config
    from shared.persistence import adquirir_bloqueo
    from shared.utilidades import ahora

    base = tmp_path / "manual"
    (base / "resultados").mkdir(parents=True, exist_ok=True)
    config = load_config()
    seccion = dict(config["evaluacion_manual"])
    seccion["carpeta_base"] = str(base)
    monkeypatch.setattr(
        "modules.evaluation.nodes.inicio_manual.load",
        lambda: {**config, "evaluacion_manual": seccion},
    )
    adquirir_bloqueo("COR-9999", ahora())
    monkeypatch.setattr(comando, "ejecutar_flujo_importacion", lambda: flujo_real())
    avisos: list[tuple[str, str]] = []
    monkeypatch.setattr(
        comando, "enviar_aviso", lambda cuerpo, urgencia: avisos.append((cuerpo, urgencia))
    )

    codigo, texto = comando.importar()
    assert codigo == 1
    assert "sin corrida" not in texto
    assert "Corrida: COR-" in texto
    assert "COR-" in avisos[0][0]
    assert "concurrencia" in avisos[0][0]


def test_importar_sin_corrida_no_finge_un_informe(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(comando, "ejecutar_flujo_importacion", lambda: None)
    avisos: list[tuple[str, str]] = []
    monkeypatch.setattr(
        comando, "enviar_aviso", lambda cuerpo, urgencia: avisos.append((cuerpo, urgencia))
    )
    codigo, texto = comando.importar()
    assert codigo == 1
    assert "No se registró ninguna corrida" in texto
    assert "COR-" not in texto
    assert avisos[0][1] == "critical"


def test_importar_sobre_copia_restaura_la_base(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shared.persistence import _db_path

    copia = temp_db_file.parent / "copia.db"
    _simular(monkeypatch, "corrida_completada")
    comando.importar(copia)
    assert _db_path() != copia


def test_main_con_cadena_real_aplica_la_respuesta(
    temp_db_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3

    from shared.config import load as load_config

    base = tmp_path / "manual"
    for carpeta in (base, base / "lotes", base / "resultados", base / "resultados" / "rechazados"):
        carpeta.mkdir(parents=True, exist_ok=True)

    escribir_fila(
        "ofertas_descubiertas",
        {
            "id": "OFE-0001",
            "enlace": "https://example.com/1",
            "titulo": "Jefe de operaciones",
            "descripcion_original": "Diseñar el plan operativo de la planta.",
            "fecha_descubrimiento": ahora(),
            "estado": "preparada",
        },
    )
    (base / "lotes" / "COR-0100_lote_001.json").write_text(
        json.dumps({"ids": ["OFE-0001"]}), encoding="utf-8"
    )
    (base / "lotes" / "COR-0100_lote_001.md").write_text("# Lote 001", encoding="utf-8")
    (base / "resultados" / "COR-0100_lote_001.jsonl").write_text(
        json.dumps(
            {
                "id": "OFE-0001",
                "entregable_principal": "Plan operativo",
                "v1": "PASS",
                "v2": "PASS",
                "v3": "PASS",
                "v4": "PASS",
                "v5": "PASS",
                "decision": "APROBADA",
                "justificacion": "El cargo entrega un mecanismo organizacional.",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    config = load_config()
    seccion = dict(config["evaluacion_manual"])
    seccion["carpeta_base"] = str(base)
    seccion["retries"] = {
        "max_attempts": 2,
        "base_wait_seconds": 0,
        "max_wait_seconds": 0,
        "multiplier": 1,
    }
    monkeypatch.setattr(
        "modules.evaluation.nodes.inicio_manual.load",
        lambda: {**config, "evaluacion_manual": seccion},
    )
    monkeypatch.setattr(comando, "enviar_aviso", lambda cuerpo, urgencia: None)

    codigo = comando.main(["--db", str(temp_db_file)])
    with sqlite3.connect(temp_db_file) as conexion:
        estado = conexion.execute(
            "SELECT estado FROM ofertas_descubiertas WHERE id = 'OFE-0001'"
        ).fetchone()[0]
    assert codigo == 0
    assert estado == "aceptada_ei"
