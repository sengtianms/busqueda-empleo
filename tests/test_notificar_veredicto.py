"""Tests for the batch-verdict notifier (D57): verdicts from the official trace."""

from pathlib import Path

import pytest

from scripts.notificar_veredicto import componer_de_texto, componer_veredicto, enviar_aviso

DESDE = "2026-10-19 16:11:00"


def _registrar_corridas(estados: dict[str, dict[str, object]]) -> None:
    from shared.persistence import actualizar_corrida, registrar_corrida

    inicios = {
        "COR-8001": "2026-10-19 16:11:39",
        "COR-8002": "2026-10-19 16:11:45",
        "COR-8003": "2026-10-19 16:12:10",
        "COR-8004": "2026-10-19 16:13:40",
    }
    for id_corrida, fecha_inicio in inicios.items():
        registrar_corrida(
            {"id_corrida": id_corrida, "fecha_inicio": fecha_inicio, "estado": "en_ejecucion"}
        )
    for id_corrida, campos in estados.items():
        actualizar_corrida(id_corrida, campos)


def _sembrar_exito() -> None:
    from shared.persistence import escribir_evento

    _registrar_corridas(
        {
            "COR-8002": {
                "estado": "completada",
                "fecha_fin": "2026-10-19 16:12:05",
                "motivo_terminacion": "corrida_completada",
                "total_ofertas": 48,
                "fuentes_procesadas": 1,
            },
            "COR-8003": {
                "estado": "completada",
                "fecha_fin": "2026-10-19 16:13:20",
                "motivo_terminacion": "corrida_completada",
                "total_preparadas": 47,
                "total_duplicadas": 1,
            },
            "COR-8004": {
                "estado": "completada",
                "fecha_fin": "2026-10-19 16:14:55",
                "motivo_terminacion": "corrida_completada",
                "total_aprobadas": 7,
                "total_descartadas": 39,
            },
            "COR-8001": {
                "estado": "completada",
                "fecha_fin": "2026-10-19 16:14:55",
                "motivo_terminacion": "corrida_completada",
                "total_sucesos": 3,
                "total_errores": 0,
                "total_ofertas": 0,
                "fuentes_procesadas": 0,
            },
        }
    )
    for indice, (modulo, id_modulo) in enumerate(
        (("descubrimiento", "COR-8002"), ("preparacion", "COR-8003"), ("evaluacion", "COR-8004"))
    ):
        marca = f"2026-10-19 16:{12 + indice}:11"
        escribir_evento(
            {
                "id_corrida": "COR-8001",
                "tipo": "suceso",
                "codigo": "modulo_ejecutado",
                "evidencia": (
                    f"modulo={modulo};estado=completada;"
                    f"motivo=corrida_completada;id_corrida={id_modulo}"
                ),
                "marca_temporal": marca,
            }
        )
    escribir_evento(
        {
            "id_corrida": "COR-8001",
            "tipo": "suceso",
            "codigo": "corrida_programada",
            "evidencia": "descubrimiento=completada;preparacion=completada;evaluacion=completada",
            "marca_temporal": "2026-10-19 16:14:55",
        }
    )


def _sembrar_fallo_modulo() -> None:
    from shared.persistence import escribir_evento

    _registrar_corridas(
        {
            "COR-8003": {
                "estado": "abortada",
                "fecha_fin": "2026-10-19 16:13:20",
                "motivo_terminacion": "error_critico",
                "total_preparadas": 5,
                "total_duplicadas": 0,
            },
            "COR-8004": {"estado": "en_ejecucion"},
            "COR-8001": {
                "estado": "completada",
                "fecha_fin": "2026-10-19 16:14:55",
                "motivo_terminacion": "corrida_completada",
                "total_sucesos": 1,
                "total_errores": 1,
                "total_ofertas": 0,
                "fuentes_procesadas": 0,
            },
        }
    )
    escribir_evento(
        {
            "id_corrida": "COR-8001",
            "tipo": "error",
            "codigo": "modulo_fallido",
            "evidencia": (
                "modulo=preparacion;estado=abortada;motivo=error_critico;"
                "id_corrida=COR-8003"
            ),
            "marca_temporal": "2026-10-19 16:13:26",
        }
    )
    escribir_evento(
        {
            "id_corrida": "COR-8001",
            "tipo": "suceso",
            "codigo": "corrida_programada",
            "evidencia": "descubrimiento=completada;preparacion=abortada",
            "marca_temporal": "2026-10-19 16:14:55",
        }
    )


def test_veredicto_exito_con_metricas(temp_db_file: Path) -> None:
    _sembrar_exito()
    nivel, mensaje = componer_veredicto(DESDE)
    assert nivel == "exito"
    assert "Tanda 16:11 completada ✓" in mensaje
    assert "48 nuevas" in mensaje
    assert "47 preparadas / 1 duplicadas" in mensaje
    assert "7 aprobadas / 39 descartadas" in mensaje
    assert "0 errores" in mensaje


def test_veredicto_exito_sin_novedades(temp_db_file: Path) -> None:
    from shared.persistence import actualizar_corrida

    _sembrar_exito()
    # Overwrite to a zero-news batch: no counts, no offers to report.
    for id_corrida, campos in {
        "COR-8002": {"total_ofertas": 0, "fuentes_procesadas": 1},
        "COR-8003": {"total_preparadas": 0, "total_duplicadas": 0},
        "COR-8004": {"total_aprobadas": 0, "total_descartadas": 0},
    }.items():
        actualizar_corrida(id_corrida, campos)
    nivel, mensaje = componer_veredicto(DESDE)
    assert nivel == "exito"
    assert "Tanda 16:11 completada ✓ · sin ofertas nuevas · 0 errores" == mensaje


def test_veredicto_fallo_modulo(temp_db_file: Path) -> None:
    _sembrar_fallo_modulo()
    nivel, mensaje = componer_veredicto(DESDE)
    assert nivel == "fallo"
    assert "con fallos" in mensaje
    assert "preparacion: error_critico" in mensaje


def test_veredicto_tanda_interrumpida(temp_db_file: Path) -> None:
    from shared.persistence import actualizar_corrida

    _sembrar_fallo_modulo()
    actualizar_corrida(
        "COR-8001",
        {"estado": "abortada", "motivo_terminacion": "error_critico"},
    )
    nivel, mensaje = componer_veredicto(DESDE)
    assert nivel == "fallo"
    assert "interrumpida" in mensaje
    assert "preparacion: error_critico" in mensaje


def test_veredicto_sin_corridas(temp_db_file: Path) -> None:
    nivel, mensaje = componer_veredicto(DESDE)
    assert nivel == "fallo"
    assert "sin corrida cerrada" in mensaje


def test_texto_tanda_activa_es_omision(temp_db_file: Path) -> None:
    nivel, mensaje = componer_de_texto(
        "== PREFLIGHT ==\n  [FALLA] corrida activa COR-0008 (3 min) — espere o libere\n"
        "RESULTADO: hay bloqueos\n",
        None,
    )
    assert nivel == "omitida"
    assert "otra tanda en curso" in mensaje
    assert "COR-0008" in mensaje
    assert "no es un error" in mensaje


def test_texto_fallo_chequeo_previo(temp_db_file: Path) -> None:
    nivel, mensaje = componer_de_texto(
        "== PREFLIGHT ==\n  [OK ] bloqueo libre\n  [FALLA] motor de IA sin respuesta\n",
        None,
    )
    assert nivel == "fallo"
    assert "[FALLA] motor de IA sin respuesta" in mensaje
    assert "no pudo arrancar" in mensaje


def test_texto_omision_explicita(temp_db_file: Path) -> None:
    nivel, mensaje = componer_de_texto(None, "prueba de guion")
    assert nivel == "omitida"
    assert "Tanda omitida: prueba de guion" in mensaje


def test_texto_sin_linea_falla_usa_texto_integral(temp_db_file: Path) -> None:
    texto = "la corrida terminó de forma inesperada (código 2)"
    nivel, mensaje = componer_de_texto(texto, None)
    assert nivel == "fallo"
    assert texto in mensaje


def test_detalle_largo_se_acota(temp_db_file: Path) -> None:
    motivo = "F" * 220
    _, mensaje = componer_de_texto(f"  [FALLA] {motivo}\n", None)
    # The 160-char cap covers the whole failing line: '[FALLA] ' prefix
    # (8 chars) + 220 F's leaves 152 F's, never the full 220.
    assert "F" * 152 in mensaje
    assert "F" * 153 not in mensaje


def test_enviar_aviso_emisor_rechaza(temp_db_file: Path, capsys: pytest.CaptureFixture[str],
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess as sp

    from scripts.notificar_veredicto import _TOPE_CAUSA

    resultado = sp.CompletedProcess([], 1, stderr="sin receptor\n")
    monkeypatch.setattr("shutil.which", lambda nombre: "/usr/bin/notify-send")
    monkeypatch.setattr(sp, "run", lambda *a, **kw: resultado)
    enviar_aviso("mensaje rechazado", "critical")
    salida = capsys.readouterr().out
    assert "AVISO [critical] Búsqueda de empleo: mensaje rechazado" in salida
    assert "no entregado" in salida
    assert _TOPE_CAUSA == 140


def test_enviar_aviso_sin_emisor(
    temp_db_file: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda nombre: None)
    enviar_aviso("mensaje de prueba", "normal")
    salida = capsys.readouterr().out
    assert "AVISO [normal] Búsqueda de empleo: mensaje de prueba" in salida
    assert "no hay emisor" in salida
