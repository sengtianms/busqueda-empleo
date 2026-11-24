"""D83: diagnóstico de solo lectura del catálogo de ubicaciones."""

from typing import Any

from scripts.modelo_catalogo import (
    DEPARTAMENTO,
    MUNICIPIO,
    NO_APLICA,
    PAIS,
    canonico_municipio,
    clave_normalizada,
    diagnosticar,
    es_estructural,
    tipo_de_fila,
)


def _fila(
    id_valor: str,
    municipio: str,
    departamento: str,
    pais: str = "colombia",
    origen: str = "operador",
) -> dict[str, Any]:
    return {
        "id": id_valor,
        "municipio": municipio,
        "departamento": departamento,
        "pais": pais,
        "origen": origen,
    }


def test_clasificacion_de_filas() -> None:
    assert tipo_de_fila(_fila("1", "bogota", "cundinamarca")) == MUNICIPIO
    assert tipo_de_fila(_fila("2", "N/A", "caldas")) == DEPARTAMENTO
    assert tipo_de_fila(_fila("3", "N/A", "N/A", "colombia")) == PAIS
    sin_aplica = _fila("4", "N/A", "N/A", "N/A", "sistema")
    assert tipo_de_fila(sin_aplica) == NO_APLICA
    assert es_estructural(sin_aplica)
    assert es_estructural(_fila("3", "N/A", "N/A", "colombia"))
    assert not es_estructural(_fila("1", "bogota", "cundinamarca"))


def test_diagnostico_cuenta_tipos_y_origenes() -> None:
    filas = [
        _fila("1", "bogota", "cundinamarca"),
        _fila("2", "milan", "caqueta", origen="sistema"),
        _fila("3", "N/A", "caldas"),
        _fila("4", "N/A", "N/A", "colombia"),
        _fila("5", "N/A", "N/A", "N/A", "sistema"),
    ]
    diag = diagnosticar(filas)
    assert diag.total == 5
    assert diag.por_tipo[MUNICIPIO] == 2
    assert diag.por_tipo[DEPARTAMENTO] == 1
    assert diag.filas_pais == 1
    assert diag.no_aplica == 1
    assert diag.por_origen["operador"] == 3
    assert diag.por_origen["sistema"] == 2
    assert diag.variantes == ()


def test_diagnostico_detecta_variantes_y_no_confunde_homonimos() -> None:
    filas = [
        _fila("1", "Bogotá", "cundinamarca"),
        _fila("2", "bogota", "Cundinamarca"),
        _fila("3", "granada", "meta"),
        _fila("4", "granada", "antioquia"),
    ]
    diag = diagnosticar(filas)
    assert len(diag.variantes) == 1
    assert set(diag.variantes[0].ids) == {"1", "2"}


def test_diagnostico_detecta_variantes_por_alias_y_sufijo_dc() -> None:
    filas = [
        _fila("1", "San José de Cúcuta", "norte de santander"),
        _fila("2", "cucuta", "Norte de Santander"),
        _fila("3", "Bogotá D.C.", "cundinamarca"),
        _fila("4", "bogota", "Cundinamarca"),
    ]
    diag = diagnosticar(filas)
    grupos = {frozenset(variante.ids) for variante in diag.variantes}
    assert grupos == {frozenset({"1", "2"}), frozenset({"3", "4"})}
    assert clave_normalizada(filas[0]) == clave_normalizada(filas[1])
    assert clave_normalizada(filas[2]) == clave_normalizada(filas[3])


def test_clave_normalizada_unifica_formas_de_pais() -> None:
    colombia = _fila("1", "cota", "cundinamarca", "colombia")
    abreviatura = _fila("2", "cota", "cundinamarca", "CO")
    assert clave_normalizada(colombia) == clave_normalizada(abreviatura)
    otro_pais = _fila("3", "cota", "cundinamarca", "ecuador")
    assert clave_normalizada(colombia) != clave_normalizada(otro_pais)


def test_canonico_municipio_aplica_alias_y_equivalencias() -> None:
    assert canonico_municipio("San José de Cúcuta") == "cucuta"
    assert canonico_municipio("Bogotá D.C.") == "bogota"
    assert canonico_municipio("Puerto Nuevo") == "puerto nuevo"
