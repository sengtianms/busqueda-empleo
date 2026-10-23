"""Tests del tablero de estado de tanda (Lote 1): lecturas de la traza oficial."""

from datetime import datetime
from pathlib import Path

import pytest

from scripts.estado_corrida import _analizar_evidencia, componer_estado, main

REF = datetime(2026, 10, 22, 17, 57, 0)


def _corrida(id_corrida: str, fecha_inicio: str) -> None:
    from shared.persistence import registrar_corrida

    registrar_corrida(
        {"id_corrida": id_corrida, "fecha_inicio": fecha_inicio, "estado": "en_ejecucion"}
    )


def _cerrar(id_corrida: str, campos: dict[str, object]) -> None:
    from shared.persistence import actualizar_corrida

    actualizar_corrida(id_corrida, campos)


def _evento(
    id_corrida: str,
    codigo: str,
    evidencia: str,
    marca: str,
    *,
    tipo: str = "suceso",
    indice_set: int | None = None,
    id_oferta: str | None = None,
) -> None:
    from shared.persistence import escribir_evento

    datos: dict[str, object] = {
        "id_corrida": id_corrida,
        "tipo": tipo,
        "codigo": codigo,
        "evidencia": evidencia,
        "marca_temporal": marca,
    }
    if indice_set is not None:
        datos["indice_set"] = indice_set
    if id_oferta is not None:
        datos["id_oferta"] = id_oferta
    escribir_evento(datos)


def _silla(id_corrida: str, marca: str) -> None:
    from shared.persistence import adquirir_bloqueo

    adquirirse = adquirir_bloqueo(id_corrida, marca)
    assert adquirirse


def _oferta(id_oferta: str, estado: str, id_corrida: str) -> None:
    from shared.persistence import escribir_fila

    escribir_fila(
        "ofertas_descubiertas",
        {
            "id": id_oferta,
            "enlace": f"https://linkedin.com/ofertas/{id_oferta}",
            "estado": estado,
            "id_corrida": id_corrida,
            "id_externo": f"ext-{id_oferta}",
        },
    )


def _tanda_con_figurado() -> None:
    """Tanda + módulo descubrimiento abiertos con 5 de 18 sets terminados."""
    _corrida("COR-9000", "2026-10-22 17:51:03")
    _corrida("COR-9001", "2026-10-22 17:51:10")
    _silla("COR-9001", "2026-10-22 17:51:10")
    _evento("COR-9001", "ingreso_exitoso", "sesion=LK-1", "2026-10-22 17:52:00")
    marcas_sets = ("17:52:30", "17:54:00", "17:54:30", "17:55:00", "17:55:30")
    for seteado, marca in enumerate(marcas_sets):
        _evento(
            "COR-9001",
            "consulta_exitosa",
            f"set={seteado} | total={40 + seteado}",
            f"2026-10-22 {marca}",
            indice_set=seteado,
        )
    _evento(
        "COR-9001",
        "captura_completada",
        "páginas=12 | ofertas=61 | duracion_s=214",
        "2026-10-22 17:55:40",
    )
    _evento(
        "COR-9001",
        "ofertas_registradas",
        "ofertas registradas: 61 | total: 61",
        "2026-10-22 17:55:45",
    )


def test_analizador_de_evidencia_acepta_ambos_separadores() -> None:
    pares = _analizar_evidencia("set=4 | total=47")
    assert pares == {"set": "4", "total": "47"}
    pares = _analizar_evidencia("modulo=preparacion;estado=completada;id_corrida=COR-1")
    assert pares["modulo"] == "preparacion" and pares["id_corrida"] == "COR-1"


def test_sin_tanda_y_sin_antecedentes() -> None:
    lineas = componer_estado(referencia=REF)
    assert any("Sin tanda en curso y sin corridas previas registradas." in x for x in lineas)


def test_reporta_veredicto_de_ultima_cerrada() -> None:
    _corrida("COR-8000", "2026-10-22 16:11:39")
    _cerrar(
        "COR-8000",
        {
            "estado": "completada",
            "fecha_fin": "2026-10-22 16:14:55",
            "motivo_terminacion": "corrida_completada",
            "total_errores": 0,
        },
    )
    _evento(
        "COR-8000",
        "corrida_programada",
        "descubrimiento=completada;preparacion=completada;evaluacion=completada",
        "2026-10-22 16:14:55",
    )
    lineas = componer_estado(referencia=REF)
    assert any("Sin tanda en curso." in x for x in lineas)
    unica = " ".join(lineas)
    assert "última tanda: COR-8000" in unica
    assert "completada" in unica and "corrida_completada" in unica


def test_tanda_en_marcha_con_modulo_descubrimiento() -> None:
    _tanda_con_figurado()
    lineas = componer_estado(referencia=REF, sets_total=18)
    unica = " ".join(lineas)
    assert "Tanda: en marcha" in unica
    assert "iniciada 17:51" in unica and "COR-9000" in unica
    assert "Módulo en curso: descubrimiento · COR-9001 (desde 17:51)" in unica
    assert "búsquedas de filtros terminadas: 5 de 18" in unica
    assert "última búsqueda: set 4 (total declarado: 44)" in unica
    assert "12 páginas | 61 ofertas | duración 214s" in unica
    assert "61 registradas de 61" in unica
    assert "Última señal de vida" in unica
    # 5 sets en 4m 20s -> 52s/set; quedan 13 sets -> ~11m 16s.
    assert "quedan ~11m 16s (ritmo de esta corrida: 52s por unidad)" in unica


def test_tanda_en_modulo_preparacion() -> None:
    _corrida("COR-9002", "2026-10-22 18:01:00")
    _corrida("COR-9003", "2026-10-22 18:01:05")
    _silla("COR-9003", "2026-10-22 18:01:05")
    for id_oferta in ("OFE-A", "OFE-B", "OFE-C"):
        _oferta(id_oferta, "preparada", "COR-9003")
    _oferta("OFE-D", "duplicada", "COR-9003")
    for id_oferta in ("OFE-E", "OFE-F", "OFE-G", "OFE-H"):
        _oferta(id_oferta, "descubierta", "COR-9003")
    _evento(
        "COR-9003", "oferta_preparada", "preparacion ok", "2026-10-22 18:01:20", id_oferta="OFE-A"
    )
    _evento(
        "COR-9003", "oferta_preparada", "preparacion ok", "2026-10-22 18:01:35", id_oferta="OFE-B"
    )
    _evento(
        "COR-9003", "oferta_preparada", "preparacion ok", "2026-10-22 18:01:45", id_oferta="OFE-C"
    )
    _evento(
        "COR-9003", "oferta_duplicada", "original OFE-B", "2026-10-22 18:01:45", id_oferta="OFE-D"
    )
    lineas = componer_estado(referencia=REF, sets_total=18)
    unica = " ".join(lineas)
    assert "Módulo en curso: preparacion" in unica
    assert "preparadas 3 · duplicadas 1 · en cola: 4" in unica
    # 3 unidades en 40s -> 13s/unidad; quedan 4 -> ~53s.
    assert "quedan ~53s (ritmo de esta corrida: 13s por unidad)" in unica


def test_tanda_en_modulo_evaluacion() -> None:
    _corrida("COR-9010", "2026-10-22 19:00:00")
    _corrida("COR-9011", "2026-10-22 19:00:10")
    _silla("COR-9011", "2026-10-22 19:00:10")
    _cerrar(
        "COR-9010",
        {
            "estado": "completada",
            "fecha_fin": "2026-10-22 18:59:30",
            "motivo_terminacion": "corrida_completada",
        },
    )
    _evento(
        "COR-9010",
        "modulo_ejecutado",
        "modulo=preparacion;estado=completada;motivo=corrida_completada;id_corrida=COR-9011",
        "2026-10-22 18:59:20",
    )
    for id_oferta in ("OFE-1", "OFE-2"):
        _oferta(id_oferta, "aceptada_ei", "COR-9011")
    _oferta("OFE-3", "descartada_ei", "COR-9011")
    _oferta("OFE-4", "preparada", "COR-9011")
    _evento(
        "COR-9011",
        "oferta_aprobada",
        "puerta=principal decision=APROBADA",
        "2026-10-22 19:00:40",
        id_oferta="OFE-1",
    )
    _evento(
        "COR-9011",
        "oferta_aprobada",
        "puerta=principal decision=APROBADA",
        "2026-10-22 19:00:50",
        id_oferta="OFE-2",
    )
    _evento(
        "COR-9011",
        "oferta_descartada",
        "puerta=principal decision=DESCARTADA",
        "2026-10-22 19:00:55",
        id_oferta="OFE-3",
    )
    lineas = componer_estado(referencia=datetime(2026, 10, 22, 19, 1, 0), sets_total=18)
    unica = " ".join(lineas)
    assert "Módulo en curso: evaluacion" in unica
    assert "aprobadas 2 · descartadas 1 · en cola: 1" in unica


def test_tanda_congelada_con_silla() -> None:
    _corrida("COR-9000", "2026-10-22 17:00:00")
    _corrida("COR-9001", "2026-10-22 17:00:10")
    _silla("COR-9001", "2026-10-22 17:00:10")
    _evento("COR-9001", "consulta_exitosa", "set=0 | total=30", "2026-10-22 17:20:30", indice_set=0)
    lineas = componer_estado(
        referencia=datetime(2026, 10, 22, 17, 40, 0), sets_total=18, umbral_congelada=600
    )
    unica = " ".join(lineas)
    assert "congelada" in unica and "muerta" not in unica


def test_tanda_muerta_sin_silla() -> None:
    _corrida("COR-9000", "2026-10-22 17:00:00")
    _corrida("COR-9001", "2026-10-22 17:00:10")
    _evento("COR-9001", "consulta_exitosa", "set=0 | total=30", "2026-10-22 17:20:30", indice_set=0)
    lineas = componer_estado(
        referencia=datetime(2026, 10, 22, 17, 40, 0), sets_total=18, umbral_congelada=600
    )
    unica = " ".join(lineas)
    assert "muerta o abandonada" in unica and "silla libre" in unica


def test_corrida_arrancando_sin_senales() -> None:
    _corrida("COR-9020", "2026-10-22 17:56:30")
    lineas = componer_estado(referencia=REF)
    mensaje = "Corrida(s) arrancando (todavía sin señales): COR-9020 (desde 17:56)"
    assert any(mensaje in x for x in lineas)


def test_sobrantes_abiertas_sin_dueno() -> None:
    _corrida("COR-7000", "2026-10-21 09:00:00")
    _corrida("COR-9000", "2026-10-22 17:51:03")
    _corrida("COR-9001", "2026-10-22 17:51:10")
    _silla("COR-9001", "2026-10-22 17:51:10")
    _evento("COR-9001", "consulta_exitosa", "set=0 | total=30", "2026-10-22 17:52:30", indice_set=0)
    lineas = componer_estado(referencia=REF, sets_total=18)
    unica = " ".join(lineas)
    assert "⚠ Corridas abiertas sin dueño: COR-7000 (posible muerte anterior)" in unica
    assert "Tanda: en marcha" in unica and "COR-9000" in unica


def test_errores_asomados_por_la_tanda() -> None:
    _corrida("COR-9000", "2026-10-22 17:51:03")
    _corrida("COR-9001", "2026-10-22 17:51:10")
    _silla("COR-9001", "2026-10-22 17:51:10")
    _evento("COR-9001", "consulta_exitosa", "set=0 | total=30", "2026-10-22 17:52:30", indice_set=0)
    _evento(
        "COR-9001",
        "preparacion_fallida",
        "fallo de captura | id=OFE-9",
        "2026-10-22 17:52:35",
    )
    _evento(
        "COR-9001",
        "ERR-08",
        "clasificación de ubicación pendiente",
        "2026-10-22 17:52:36",
        tipo="error",
    )
    lineas = componer_estado(referencia=REF, sets_total=18)
    unica = " ".join(lineas)
    assert "Avisos de error en la tanda: 1 (últimos)" in unica
    assert "[17:52:36] ERR-08: clasificación de ubicación pendiente" in unica


def test_corrida_individual_de_modulo() -> None:
    _corrida("COR-9001", "2026-10-22 17:51:10")
    _silla("COR-9001", "2026-10-22 17:51:10")
    _evento("COR-9001", "consulta_exitosa", "set=0 | total=30", "2026-10-22 17:52:30", indice_set=0)
    lineas = componer_estado(referencia=REF, sets_total=18)
    unica = " ".join(lineas)
    assert "Corrida individual de módulo (sin tanda programada)." in unica
    assert "Módulo en curso: descubrimiento" in unica
    assert "Tanda:" not in unica


def test_comando_de_consulta_sin_seguir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _tanda_con_figurado()
    codigo = main([])
    captura = capsys.readouterr()
    assert codigo == 0
    assert "== ESTADO DE LA TANDA" in captura.out
    assert "Módulo en curso: descubrimiento" in captura.out


def test_set_en_marcha_y_captura_actual_del_descubrimiento() -> None:
    """Lote 2: el tablero muestra el set en marcha y la página de captura."""
    _corrida("COR-9100", "2026-10-22 17:51:03")
    _corrida("COR-9101", "2026-10-22 17:51:10")
    _silla("COR-9101", "2026-10-22 17:51:10")
    _evento("COR-9101", "tic_modulo_iniciado", "modulo=descubrimiento", "2026-10-22 17:51:12")
    _evento("COR-9101", "tic_set_iniciado", "set=2", "2026-10-22 17:53:00", indice_set=2)
    _evento(
        "COR-9101",
        "tic_captura_pagina",
        "set=2;pagina=3;acumuladas=44",
        "2026-10-22 17:53:30",
        indice_set=2,
    )
    _evento("COR-9101", "consulta_exitosa", "set=1 | total=18", "2026-10-22 17:51:40", indice_set=1)
    lineas = componer_estado(referencia=REF, sets_total=18)
    unica = "\n".join(lineas)
    assert "Módulo en curso: descubrimiento" in unica
    assert "búsquedas de filtros terminadas: 1 de 18" in unica
    assert "set en marcha: #2 (empezado 17:53:00)" in unica
    assert "captura en marcha: página 3 (acumuladas 44)" in unica


def test_nombre_de_modulo_por_su_tic_de_arranque() -> None:
    """Lote 2: el tic `tic_modulo_iniciado` nombra al módulo en curso."""
    _corrida("COR-9200", "2026-10-22 17:55:00")
    _corrida("COR-9201", "2026-10-22 17:55:05")
    _silla("COR-9201", "2026-10-22 17:55:05")
    _evento("COR-9201", "tic_modulo_iniciado", "modulo=preparacion", "2026-10-22 17:55:08")
    lineas = componer_estado(referencia=REF, sets_total=18)
    unica = "\n".join(lineas)
    assert "Módulo en curso: preparacion · COR-9201 (desde 17:55)" in unica


def test_umbral_negativo_rechazado(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--umbral-congelada", "-5"])
    assert "no puede ser negativo" in capsys.readouterr().err


def test_base_ausente_muestra_panel_y_no_crea_nada(tmp_path: Path) -> None:
    from shared.persistence import change_path, reset_path

    destino = tmp_path / "aun" / "no" / "existe.db"
    change_path(destino)
    try:
        lineas = componer_estado(referencia=REF)
    finally:
        reset_path()
    unica = " ".join(lineas)
    assert "La base de datos no está lista" in unica
    assert "no existe todavía" in unica
    assert not destino.exists()  # solo lectura: ningún archivo creado


def test_refugio_de_configuracion(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.estado_corrida as visor

    def rota() -> dict[str, object]:
        raise RuntimeError("config inservible")

    monkeypatch.setattr(visor, "load", rota)
    assert visor._nombres_config() == ["descubrimiento", "preparacion", "evaluacion"]
    assert visor._total_sets_config() is None


def test_modulo_ciego_de_lote_con_nombre_previsto() -> None:
    """Tanda abierta + módulo previo cerrado + módulo nuevo sin señales: previsto."""
    _corrida("COR-9300", "2026-10-22 20:00:00")
    _corrida("COR-9301", "2026-10-22 20:00:05")
    _cerrar(
        "COR-9301",
        {
            "estado": "completada",
            "fecha_fin": "2026-10-22 20:34:00",
            "motivo_terminacion": "corrida_completada",
        },
    )
    _evento(
        "COR-9300",
        "modulo_ejecutado",
        "modulo=descubrimiento;estado=completada;motivo=corrida_completada;id_corrida=COR-9301",
        "2026-10-22 20:34:00",
    )
    _corrida("COR-9302", "2026-10-22 20:35:00")
    _silla("COR-9302", "2026-10-22 20:35:00")
    lineas = componer_estado(referencia=datetime(2026, 10, 22, 20, 40, 0), sets_total=18)
    unica = " ".join(lineas)
    assert "Módulo en curso: preparacion · COR-9302 (desde 20:35)" in unica
    assert "Tanda: en marcha" in unica
    assert "Corrida individual" not in unica
