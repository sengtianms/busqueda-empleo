"""D82: exact-tuple uniqueness guard for the locations catalogue.

The guard is preventive: no row is merged, deleted or rewritten. These tests
cover the idempotent migration, the refusal to create the index over an
already-duplicated catalogue, and the create-or-reuse writer used by the
Preparation AI exception.
"""

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from shared.persistence import (
    _generar_id_en as generar_id_real,
)
from shared.persistence import (
    buscar_por_id,
    crear_o_reutilizar_ubicacion,
    init_db,
    leer_tabla,
)
from shared.persistence._migraciones import INDICE_UBICACIONES_UNICA

FILA_NUEVA: dict[str, Any] = {
    "municipio": "puerto bogota",
    "departamento": "cundinamarca",
    "pais": "colombia",
    "origen": "sistema",
}


def _indice_presente(path: Path) -> bool:
    conn = sqlite3.connect(str(path))
    try:
        fila = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
            (INDICE_UBICACIONES_UNICA,),
        ).fetchone()
        return fila is not None
    finally:
        conn.close()


def _ultimo_numero(path: Path) -> int:
    conn = sqlite3.connect(str(path))
    try:
        fila = conn.execute(
            "SELECT ultimo_numero FROM secuencia_ids WHERE tabla_nombre = 'ubicaciones'"
        ).fetchone()
        assert fila is not None
        return int(fila[0])
    finally:
        conn.close()


def _insertar_duplicado(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(f"DROP INDEX {INDICE_UBICACIONES_UNICA}")
        for id_valor in ("UBI-9001", "UBI-9002"):
            conn.execute(
                "INSERT INTO ubicaciones "
                "(id, municipio, departamento, pais, origen) "
                "VALUES (?, 'puerto bogota', 'cundinamarca', 'colombia', 'sistema')",
                (id_valor,),
            )
        conn.commit()
    finally:
        conn.close()


def test_migracion_crea_indice_unico(temp_db_file: Path) -> None:
    assert _indice_presente(temp_db_file)


def test_migracion_doble_arranque_es_idempotente(temp_db_file: Path) -> None:
    init_db()
    init_db()

    assert _indice_presente(temp_db_file)
    assert len(leer_tabla("ubicaciones", {})) == 1


def test_duplicado_exacto_omite_indice_y_avisa(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insertar_duplicado(temp_db_file)
    avisos: list[str] = []
    monkeypatch.setattr(
        "shared.persistence._migraciones.logger.warning",
        lambda mensaje, *args, **kwargs: avisos.append(str(mensaje)),
    )

    init_db()

    assert not _indice_presente(temp_db_file)
    assert any("ubicaciones_indice_unico_omitido" in aviso for aviso in avisos)
    assert len(leer_tabla("ubicaciones", {})) == 3


def test_crear_o_reutilizar_ubicacion_crea_fila_nueva(temp_db_file: Path) -> None:
    id_creado = crear_o_reutilizar_ubicacion(dict(FILA_NUEVA))

    fila = buscar_por_id("ubicaciones", id_creado)
    assert fila is not None
    assert fila["municipio"] == "puerto bogota"
    assert fila["origen"] == "sistema"
    assert fila["fecha_creacion"] != ""
    assert fila["fecha_ultima_edicion"] != ""


def test_crear_o_reutilizar_ubicacion_reutiliza_fila_existente(
    temp_db_file: Path,
) -> None:
    primero = crear_o_reutilizar_ubicacion(dict(FILA_NUEVA))
    contador_tras_crear = _ultimo_numero(temp_db_file)
    segundo = crear_o_reutilizar_ubicacion(dict(FILA_NUEVA))

    assert segundo == primero
    assert len(leer_tabla("ubicaciones", {"municipio": "puerto bogota"})) == 1
    # Reusing an existing tuple never consumes an identifier (D82).
    assert _ultimo_numero(temp_db_file) == contador_tras_crear


def test_conflicto_entre_busqueda_e_insercion_reutiliza_fila(
    temp_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The IntegrityError branch covers a rival writer between SELECT and INSERT."""

    def generar_con_rival(conn: Any, tabla: str) -> str:
        rival = sqlite3.connect(str(temp_db_file))
        try:
            rival.execute(
                "INSERT INTO ubicaciones "
                "(id, municipio, departamento, pais, origen) "
                "VALUES ('UBI-9002', 'puerto bogota', 'cundinamarca', "
                "'colombia', 'sistema')"
            )
            rival.commit()
        finally:
            rival.close()
        return generar_id_real(conn, tabla)

    monkeypatch.setattr(
        "shared.persistence._escrituras._generar_id_en", generar_con_rival
    )

    id_devuelto = crear_o_reutilizar_ubicacion(dict(FILA_NUEVA))

    assert id_devuelto == "UBI-9002"
    assert len(leer_tabla("ubicaciones", {"municipio": "puerto bogota"})) == 1


def test_indice_rechaza_duplicado_exacto_por_escritura_directa(
    temp_db_file: Path,
) -> None:
    crear_o_reutilizar_ubicacion(dict(FILA_NUEVA))
    conn = sqlite3.connect(str(temp_db_file))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ubicaciones (id, municipio, departamento, pais) "
                "VALUES ('UBI-9002', 'puerto bogota', 'cundinamarca', 'colombia')"
            )
    finally:
        conn.close()
