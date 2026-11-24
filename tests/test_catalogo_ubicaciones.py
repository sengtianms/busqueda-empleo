"""D83: mantenimiento del catálogo de ubicaciones por el operador."""

from pathlib import Path
from typing import Any

import pytest

import scripts.catalogo_ubicaciones as herramienta
from shared.persistence import (
    adquirir_bloqueo,
    buscar_por_id,
    change_path,
    escribir_fila,
    init_db,
    leer_tabla,
)
from shared.utilidades import ahora


@pytest.fixture(autouse=True)
def diario_en_memoria(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    lineas: list[str] = []
    monkeypatch.setattr(herramienta, "_diario", lineas.append)
    return lineas


def _args(argv: list[str]) -> Any:
    return herramienta._parser().parse_args(argv)


def _sembrar() -> dict[str, str]:
    ids: dict[str, str] = {}
    datos = {
        "pais": ("N/A", "N/A", "colombia", "operador"),
        "bogota": ("bogota", "cundinamarca", "colombia", "operador"),
        "granada": ("granada", "antioquia", "colombia", "operador"),
        "caldas": ("N/A", "caldas", "colombia", "operador"),
    }
    for clave, (municipio, departamento, pais, origen) in datos.items():
        ids[clave] = escribir_fila(
            "ubicaciones",
            {
                "municipio": municipio,
                "departamento": departamento,
                "pais": pais,
                "origen": origen,
            },
        )
    return ids


def _oferta(id_oferta: str, id_ubicacion: str, estado: str = "preparada") -> None:
    escribir_fila(
        "ofertas_descubiertas",
        {
            "id": id_oferta,
            "enlace": f"https://www.linkedin.com/jobs/view/{id_oferta}",
            "estado": estado,
            "titulo": "Título de prueba",
            "ubicacion": "texto original capturado",
            "ubicacion_id": id_ubicacion,
        },
    )


def test_listar_resumen_y_filtros(temp_db_file: Path) -> None:
    ids = _sembrar()
    lineas = herramienta.listar(_args(["listar", "bogota"]))
    assert any("Catálogo: 5 filas" in linea for linea in lineas)
    assert any(ids["bogota"] in linea for linea in lineas)
    assert any("Filas que cumplen el filtro: 1" in linea for linea in lineas)

    por_origen = herramienta.listar(_args(["listar", "--origen", "sistema"]))
    assert any("Filas que cumplen el filtro: 1" in linea for linea in por_origen)
    assert any("UBI-0001" in linea for linea in por_origen)
    todo = herramienta.listar(_args(["listar", "--todo"]))
    assert any("Filas que cumplen el filtro: 5" in linea for linea in todo)


def test_agregar_municipio_y_solo_departamento(
    temp_db_file: Path, diario_en_memoria: list[str]
) -> None:
    _sembrar()
    lineas = herramienta.agregar(
        _args(["agregar", "--municipio", "Puerto Nuevo", "--departamento", "Cundinamarca"])
    )
    assert any("Fila agregada:" in linea for linea in lineas)
    filas = leer_tabla("ubicaciones", {"municipio": "puerto nuevo"})
    assert len(filas) == 1
    assert filas[0]["departamento"] == "cundinamarca"
    assert filas[0]["pais"] == "colombia"
    assert filas[0]["origen"] == "operador"
    assert filas[0]["fecha_creacion"] != ""

    herramienta.agregar(_args(["agregar", "--departamento", "Chocó"]))
    filas_dept = leer_tabla("ubicaciones", {"departamento": "choco"})
    assert len(filas_dept) == 1
    assert filas_dept[0]["municipio"] == "N/A"
    assert len(diario_en_memoria) == 2
    assert all("AGREGAR" in linea for linea in diario_en_memoria)


def test_agregar_rechaza_duplicado_variante_y_alias(temp_db_file: Path) -> None:
    _sembrar()
    with pytest.raises(ValueError, match="ya existe"):
        herramienta.agregar(
            _args(["agregar", "--municipio", "bogota", "--departamento", "cundinamarca"])
        )
    escribir_fila(
        "ubicaciones",
        {"municipio": "Puerto Milán", "departamento": "caquetá", "pais": "colombia"},
    )
    with pytest.raises(ValueError, match="variante"):
        herramienta.agregar(
            _args(["agregar", "--municipio", "Puerto Milan", "--departamento", "Caqueta"])
        )
    with pytest.raises(ValueError, match="se resuelve como"):
        herramienta.agregar(
            _args(
                ["agregar", "--municipio", "San José de Cúcuta",
                 "--departamento", "Norte de Santander"]
            )
        )
    escribir_fila(
        "ubicaciones",
        {"municipio": "N/A", "departamento": "Chocó", "pais": "colombia"},
    )
    with pytest.raises(ValueError, match="variante"):
        herramienta.agregar(_args(["agregar", "--departamento", "Choco"]))


def test_agregar_y_corregir_rechazan_fila_canonica_cuando_existe_alias(
    temp_db_file: Path,
) -> None:
    ids = _sembrar()
    escribir_fila(
        "ubicaciones",
        {
            "municipio": "San José de Cúcuta",
            "departamento": "norte de santander",
            "pais": "colombia",
        },
    )
    with pytest.raises(ValueError, match="variante"):
        herramienta.agregar(
            _args(["agregar", "--municipio", "Cúcuta", "--departamento", "Norte de Santander"])
        )
    with pytest.raises(ValueError, match="variante"):
        herramienta.corregir(
            _args(
                ["corregir", ids["granada"],
                 "--municipio", "Cúcuta", "--departamento", "Norte de Santander"]
            )
        )


def test_agregar_rechaza_datos_incompletos(temp_db_file: Path) -> None:
    with pytest.raises(ValueError):
        herramienta.agregar(_args(["agregar"]))
    with pytest.raises(ValueError):
        herramienta.agregar(_args(["agregar", "--municipio", "Solo municipio"]))


def test_corregir_conserva_identificador_y_enlace(temp_db_file: Path) -> None:
    ids = _sembrar()
    _oferta("OFE-0001", ids["bogota"])
    lineas = herramienta.corregir(
        _args(["corregir", ids["bogota"], "--municipio", "Bogotá Oeste"])
    )
    assert any("Fila corregida:" in linea for linea in lineas)
    fila = buscar_por_id("ubicaciones", ids["bogota"])
    assert fila is not None and fila["municipio"] == "bogota oeste"
    oferta = buscar_por_id("ofertas_descubiertas", "OFE-0001")
    assert oferta is not None
    assert oferta["ubicacion_id"] == ids["bogota"]
    assert oferta["ubicacion"] == "texto original capturado"


def test_corregir_rechaza_colisiones_y_filas_estructurales(temp_db_file: Path) -> None:
    ids = _sembrar()
    with pytest.raises(ValueError, match="ya existe"):
        herramienta.corregir(
            _args(["corregir", ids["granada"], "--municipio", "bogota",
                   "--departamento", "cundinamarca"])
        )
    with pytest.raises(ValueError, match="solo lectura"):
        herramienta.corregir(_args(["corregir", "UBI-0001", "--departamento", "Meta"]))
    with pytest.raises(ValueError, match="solo lectura"):
        herramienta.corregir(_args(["corregir", ids["pais"], "--departamento", "Meta"]))


def test_corregir_rechaza_cambio_de_tipo(temp_db_file: Path) -> None:
    ids = _sembrar()
    with pytest.raises(ValueError, match="no puede cambiar de tipo"):
        herramienta.corregir(
            _args(["corregir", ids["caldas"], "--municipio", "Manizales"])
        )


def test_fusionar_mueve_ofertas_y_elimina_origen(temp_db_file: Path) -> None:
    ids = _sembrar()
    _oferta("OFE-0001", ids["bogota"], "aceptada_ei")
    _oferta("OFE-0002", ids["granada"], "descartada_ei")
    lineas = herramienta.fusionar(_args(["fusionar", ids["bogota"], ids["granada"]]))
    assert any("Ofertas movidas: 1" in linea for linea in lineas)
    assert buscar_por_id("ubicaciones", ids["bogota"]) is None
    ofertas = leer_tabla("ofertas_descubiertas")
    assert all(oferta["ubicacion_id"] == ids["granada"] for oferta in ofertas)
    assert all(oferta["ubicacion"] == "texto original capturado" for oferta in ofertas)


def test_fusionar_rechaza_reglas_de_integridad(temp_db_file: Path) -> None:
    ids = _sembrar()
    with pytest.raises(ValueError, match="no se fusionan"):
        herramienta.fusionar(_args(["fusionar", "UBI-0001", ids["bogota"]]))
    with pytest.raises(ValueError, match="mismo tipo"):
        herramienta.fusionar(_args(["fusionar", ids["caldas"], ids["bogota"]]))
    with pytest.raises(ValueError, match="misma fila"):
        herramienta.fusionar(_args(["fusionar", ids["bogota"], ids["bogota"]]))
    with pytest.raises(ValueError, match="deben existir"):
        herramienta.fusionar(_args(["fusionar", ids["bogota"], "UBI-9999"]))
    extranjera = escribir_fila(
        "ubicaciones",
        {"municipio": "quito", "departamento": "pichincha", "pais": "ecuador"},
    )
    with pytest.raises(ValueError, match="mismo país"):
        herramienta.fusionar(_args(["fusionar", extranjera, ids["bogota"]]))


def test_silla_vigente_bloquea_escrituras_pero_no_listado(temp_db_file: Path) -> None:
    ids = _sembrar()
    adquirir_bloqueo("COR-PRUEBA", ahora())
    assert herramienta.listar(_args(["listar"]))
    with pytest.raises(RuntimeError, match="tanda activa"):
        herramienta.agregar(
            _args(["agregar", "--municipio", "Nuevo", "--departamento", "Meta"])
        )
    with pytest.raises(RuntimeError, match="tanda activa"):
        herramienta.corregir(_args(["corregir", ids["bogota"], "--municipio", "Otro"]))
    with pytest.raises(RuntimeError, match="tanda activa"):
        herramienta.fusionar(_args(["fusionar", ids["bogota"], ids["granada"]]))


def test_silla_obsoleta_no_bloquea(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sembrar()
    monkeypatch.setattr(herramienta, "umbral_obsolescencia_minutos", lambda config: 0)
    adquirir_bloqueo("COR-VIEJA", ahora())
    herramienta.agregar(_args(["agregar", "--municipio", "Nuevo", "--departamento", "Meta"]))
    assert leer_tabla("ubicaciones", {"municipio": "nuevo"})


def test_main_con_base_ausente_no_crea_nada(
    temp_db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ruta = temp_db_file.parent / "no_existe.db"
    codigo = herramienta.main(["listar", "--db", str(ruta)])
    change_path(temp_db_file)
    assert codigo == 1
    assert "no existe la base de datos" in capsys.readouterr().out
    assert not ruta.exists()


def test_main_con_db_alternativo_no_toca_la_viva(temp_db_file: Path) -> None:
    copia = temp_db_file.parent / "copia.db"
    change_path(copia)
    init_db()
    change_path(temp_db_file)
    try:
        codigo = herramienta.main(
            ["agregar", "--municipio", "Solo copia", "--departamento", "Meta",
             "--db", str(copia)]
        )
        assert codigo == 0
    finally:
        change_path(temp_db_file)
    change_path(copia)
    assert leer_tabla("ubicaciones", {"municipio": "solo copia"})
    change_path(temp_db_file)
    assert not leer_tabla("ubicaciones", {"municipio": "solo copia"})
