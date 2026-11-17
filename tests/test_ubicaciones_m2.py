"""Pruebas del motor determinista de enlace de ubicaciones del Módulo 2."""

from typing import MutableMapping

import pytest

from modules.preparation.ubicaciones import (
    NO_REPORTADO,
    PENDIENTE,
    CatalogoUbicaciones,
)


@pytest.fixture
def catalogo() -> CatalogoUbicaciones:
    """Catálogo de prueba con 24 filas representativas."""
    filas = [
        {"id": "UBI-0109", "municipio": "bogotá", "departamento": "cundinamarca"},
        {"id": "UBI-0249", "municipio": "córdoba", "departamento": "quindío"},
        {"id": "UBI-0114", "municipio": "bolívar", "departamento": "santander"},
        {"id": "UBI-0388", "municipio": "granada", "departamento": "antioquia"},
        {"id": "UBI-0152", "municipio": "cali", "departamento": "valle del cauca"},
        {"id": "UBI-0389", "municipio": "granada", "departamento": "cundinamarca"},
        {"id": "UBI-0176", "municipio": "cartagena de indias", "departamento": "bolívar"},
        {"id": "UBI-0390", "municipio": "granada", "departamento": "meta"},
        {"id": "UBI-0247", "municipio": "córdoba", "departamento": "bolívar"},
        {"id": "UBI-0557", "municipio": "medellín", "departamento": "antioquia"},
        {"id": "UBI-0248", "municipio": "córdoba", "departamento": "nariño"},
        {"id": "UBI-0598", "municipio": "nariño", "departamento": "cundinamarca"},
        {"id": "UBI-0599", "municipio": "nariño", "departamento": "nariño"},
        {"id": "UBI-0669", "municipio": "pereira", "departamento": "risaralda"},
        {"id": "UBI-0951", "municipio": "sucre", "departamento": "santander"},
        {"id": "UBI-0952", "municipio": "sucre", "departamento": "sucre"},
        {"id": "UBI-1105", "municipio": "N/A", "departamento": "antioquia"},
        {"id": "UBI-1108", "municipio": "N/A", "departamento": "bolívar"},
        {"id": "UBI-1116", "municipio": "N/A", "departamento": "cundinamarca"},
        {"id": "UBI-1117", "municipio": "N/A", "departamento": "córdoba"},
        {"id": "UBI-1124", "municipio": "N/A", "departamento": "nariño"},
        {"id": "UBI-1127", "municipio": "N/A", "departamento": "quindío"},
        {"id": "UBI-1130", "municipio": "N/A", "departamento": "santander"},
        {"id": "UBI-1131", "municipio": "N/A", "departamento": "sucre"},
        {"id": "UBI-1133", "municipio": "N/A", "departamento": "valle del cauca"},
        {"id": "UBI-1136", "municipio": "N/A", "departamento": "N/A"},
    ]
    return CatalogoUbicaciones(filas)


def test_texto_vacio_o_centinela_queda_no_reportado(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("") == NO_REPORTADO
    assert catalogo.resolver("   ") == NO_REPORTADO
    assert catalogo.resolver("N/A") == NO_REPORTADO
    assert catalogo.resolver("N/R") == NO_REPORTADO


def test_texto_remoto_queda_no_reportado(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Remoto") == NO_REPORTADO
    assert catalogo.resolver("Trabajo remoto") == NO_REPORTADO
    assert catalogo.resolver("Remote") == NO_REPORTADO
    assert catalogo.resolver("REMOTO") == NO_REPORTADO


def test_municipio_unico_enlaza_su_fila(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Pereira") == "UBI-0669"


def test_tildes_y_mayusculas_no_impiden_el_enlace(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Medellin") == "UBI-0557"
    assert catalogo.resolver("MEDELLÍN") == "UBI-0557"
    assert catalogo.resolver("medellín") == "UBI-0557"


def test_municipio_con_departamento_y_pais_enlaza(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Cali, Valle del Cauca, Colombia") == "UBI-0152"


def test_municipio_repetido_con_departamento_enlaza(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Granada, Antioquia") == "UBI-0388"


def test_municipio_repetido_sin_departamento_queda_pendiente(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Granada") == PENDIENTE


def test_homonimo_solo_usa_la_fila_de_departamento(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Córdoba") == "UBI-1117"


def test_homonimo_con_su_departamento_usa_el_municipio(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Córdoba, Quindío") == "UBI-0249"


def test_solo_departamento_enlaza_su_fila(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Antioquia, Colombia") == "UBI-1105"


def test_solo_pais_enlaza_la_fila_de_pais(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Colombia") == "UBI-1136"


def test_sufijo_dc_enlaza_bogota(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Bogotá D.C.") == "UBI-0109"
    assert catalogo.resolver("Bogotá DC") == "UBI-0109"
    assert catalogo.resolver("Bogotá D. C.") == "UBI-0109"


def test_distrito_capital_enlaza_bogota(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Distrito Capital, Colombia") == "UBI-0109"


def test_area_metropolitana_queda_pendiente(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Área metropolitana de Bogotá D.C.") == PENDIENTE
    assert catalogo.resolver("Área metropolitana de Medellín") == PENDIENTE


def test_texto_fuera_del_catalogo_queda_pendiente(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Ciudad Bolivar") == PENDIENTE
    assert catalogo.resolver("Puerto Bogotá") == PENDIENTE


def test_departamento_que_no_contiene_el_municipio_queda_pendiente(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Cali, Antioquia") == PENDIENTE
    assert catalogo.resolver("Pereira, Risaralda, Antioquia") == PENDIENTE
    assert catalogo.resolver("Granada, Antioquia, Cundinamarca") == PENDIENTE


def test_dos_municipios_distintos_quedan_pendientes(
    catalogo: CatalogoUbicaciones,
) -> None:
    assert catalogo.resolver("Bogotá, Medellín") == PENDIENTE


def test_catalogo_vacio_queda_pendiente_y_avisa_una_vez() -> None:
    from loguru import logger

    mensajes: list[str] = []
    handler_id = logger.add(mensajes.append, format="{message}", level="WARNING")
    try:
        vacio = CatalogoUbicaciones([])
        assert vacio.esta_vacio is True
        assert vacio.resolver("Pereira") == PENDIENTE

        # Dos filas de país: no es vacío, Colombia queda PENDIENTE, sin aviso
        doble_pais = CatalogoUbicaciones([
            {"id": "UBI-1136", "municipio": "N/A", "departamento": "N/A"},
            {"id": "UBI-9999", "municipio": "N/A", "departamento": "N/A"},
        ])
        assert doble_pais.esta_vacio is False
        assert doble_pais.resolver("Colombia") == PENDIENTE

        encontrados = [
            m for m in mensajes
            if "catalogo_ubicaciones_vacio | todas las ofertas quedaran pendientes" in m
        ]
        assert len(encontrados) == 1
    finally:
        logger.remove(handler_id)


def test_memoria_evita_repetir_la_busqueda(
    catalogo: CatalogoUbicaciones,
) -> None:
    memoria: MutableMapping[str, str] = {}
    assert catalogo.resolver("Granada", memoria) == PENDIENTE
    assert len(memoria) == 1
    clave = list(memoria.keys())[0]
    memoria[clave] = "UBI-9999"
    assert catalogo.resolver("Granada", memoria) == "UBI-9999"


def test_textos_equivalentes_comparten_entrada_de_memoria(
    catalogo: CatalogoUbicaciones,
) -> None:
    memoria: MutableMapping[str, str] = {}
    assert catalogo.resolver("Medellín", memoria) == "UBI-0557"
    assert catalogo.resolver("medellin", memoria) == "UBI-0557"
    assert len(memoria) == 1


def test_filas_duplicadas_en_el_catalogo_quedan_pendientes() -> None:
    filas = [
        {"id": "UBI-0388", "municipio": "granada", "departamento": "antioquia"},
        {"id": "UBI-0388-b", "municipio": "granada", "departamento": "antioquia"},
        {"id": "UBI-1105", "municipio": "N/A", "departamento": "antioquia"},
        {"id": "UBI-1105-b", "municipio": "N/A", "departamento": "antioquia"},
    ]
    cat = CatalogoUbicaciones(filas)
    assert cat.resolver("Granada, Antioquia") == PENDIENTE
    assert cat.resolver("Antioquia") == PENDIENTE
