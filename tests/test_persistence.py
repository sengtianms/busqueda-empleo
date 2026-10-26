from pathlib import Path
from typing import Any

import pytest

from shared.persistence import (
    actualizar_fila,
    buscar_por_id,
    escribir_fila,
    generar_id,
    leer_candidatas_descubiertas,
    leer_tabla,
)


def test_generate_id_sequence(temp_db_file: Path) -> None:
    id_1 = generar_id("empresas")
    id_2 = generar_id("empresas")
    id_3 = generar_id("empresas")
    assert id_1 == "EMP-0001"
    assert id_2 == "EMP-0002"
    assert id_3 == "EMP-0003"


def test_generate_id_per_table(temp_db_file: Path) -> None:
    company_id = generar_id("empresas")
    id_oferta = generar_id("ofertas_descubiertas")
    ubicacion_id = generar_id("ubicaciones")
    assert company_id.startswith("EMP-")
    assert id_oferta.startswith("OFE-")
    assert ubicacion_id.startswith("UBI-")


def test_write_and_read(temp_db_file: Path) -> None:
    data = {"nombre": "Test", "perfil_linkedin": "https://www.linkedin.com/company/test"}
    generated_id = escribir_fila("empresas", data)
    assert generated_id.startswith("EMP-")
    rows = leer_tabla("empresas")
    assert len(rows) == 1
    assert rows[0]["nombre"] == "Test"
    assert rows[0]["id"] == generated_id


def test_migracion_d41_renormaliza_nombres_empresas(temp_db_file: Path) -> None:
    from shared.persistence import init_db

    escribir_fila(
        "empresas",
        {
            "nombre": "Clínica & Salud S.A. (Norte)",
            # clave calculada con la regla antigua (sin puntuación ni tildes)
            "nombre_normalizado": "clinica salud s a norte",
        },
    )
    init_db()

    filas = leer_tabla(
        "empresas", {"nombre": "Clínica & Salud S.A. (Norte)"}
    )
    assert len(filas) == 1
    assert (
        filas[0]["nombre_normalizado"] == "clínica & salud s.a. (norte)"
    )


def test_find_by_id_existing(temp_db_file: Path) -> None:
    id_1 = escribir_fila("empresas", {"nombre": "Uno", "perfil_linkedin": "li.com/uno"})
    escribir_fila("empresas", {"nombre": "Dos", "perfil_linkedin": "li.com/dos"})
    result = buscar_por_id("empresas", id_1)
    assert result is not None
    assert result["nombre"] == "Uno"


def test_find_by_id_missing(temp_db_file: Path) -> None:
    result = buscar_por_id("empresas", "EMP-9999")
    assert result is None


def test_update(temp_db_file: Path) -> None:
    id_1 = escribir_fila("empresas", {"nombre": "Viejo", "perfil_linkedin": "li.com/viejo"})
    ok = actualizar_fila("empresas", id_1, {"nombre": "Nuevo"})
    assert ok is True
    rows = leer_tabla("empresas")
    assert rows[0]["nombre"] == "Nuevo"


def test_update_missing(temp_db_file: Path) -> None:
    ok = actualizar_fila("empresas", "EMP-9999", {"nombre": "Nuevo"})
    assert ok is False


def test_write_with_explicit_id(temp_db_file: Path) -> None:
    returned_id = escribir_fila("empresas", {"id": "EMP-0100", "nombre": "Custom"})
    assert returned_id == "EMP-0100"
    result = buscar_por_id("empresas", "EMP-0100")
    assert result is not None
    assert result["nombre"] == "Custom"


def test_json_lists(temp_db_file: Path) -> None:
    id_oferta = escribir_fila("ofertas_descubiertas", {
        "enlace": "https://example.com/job",
        "titulo": "Data Engineer",
        "descripcion_original": "Test",
    })
    result = buscar_por_id("ofertas_descubiertas", id_oferta)
    assert result is not None
    assert result["enlace"] == "https://example.com/job"
    assert result["titulo"] == "Data Engineer"


def test_init_db_crea_ocho_tablas(temp_db_file: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(str(temp_db_file))
    try:
        tablas = {
            fila[0] for fila in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()
    expected = {"secuencia_ids", "empresas", "ubicaciones",
                "ofertas_descubiertas", "corridas", "eventos",
                "sesiones", "bloqueo"}
    assert expected.issubset(tablas)
    assert "fuentes" not in tablas


def test_acquire_and_release_lock(temp_db_file: Path) -> None:
    from shared.persistence import adquirir_bloqueo, consultar_bloqueo, liberar_bloqueo

    assert adquirir_bloqueo("COR-0001", "2026-08-07 10:00:00") is True
    assert consultar_bloqueo() == {
        "id_corrida": "COR-0001",
        "marca_temporal": "2026-08-07 10:00:00",
    }
    liberar_bloqueo("COR-0001")
    assert consultar_bloqueo() is None


def test_lock_obsoleto_se_sobrescribe(temp_db_file: Path) -> None:
    import datetime

    from shared.persistence import adquirir_bloqueo, consultar_bloqueo

    viejo = datetime.datetime.now() - datetime.timedelta(minutes=300)
    assert adquirir_bloqueo("COR-0001", viejo.strftime("%Y-%m-%d %H:%M:%S")) is True
    assert adquirir_bloqueo("COR-0002", datetime.datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S")) is True
    lock = consultar_bloqueo()
    assert lock is not None
    assert lock["id_corrida"] == "COR-0002"


def test_lock_vigente_rechaza(temp_db_file: Path) -> None:
    import datetime

    from shared.persistence import adquirir_bloqueo

    ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    assert adquirir_bloqueo("COR-0001", ahora) is True
    assert adquirir_bloqueo("COR-0002", ahora) is False


def test_generate_id_prefijos_nuevos(temp_db_file: Path) -> None:
    from shared.persistence import generar_id

    assert generar_id("corridas").startswith("COR-")
    assert generar_id("sesiones").startswith("SES-")
    assert generar_id("eventos").startswith("EVT-")
    assert generar_id("bloqueo").startswith("BLO-")


def test_esquema_ofertas_sin_not_null(temp_db_file: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(str(temp_db_file))
    try:
        columnas = {
            fila[1]: fila[3] for fila in conn.execute(
                "PRAGMA table_info(ofertas_descubiertas)"
            ).fetchall()
        }
    finally:
        conn.close()
    assert columnas["titulo"] == 0
    assert columnas["descripcion_original"] == 0


def test_migracion_c2_desde_esquema_antiguo(tmp_path: Path) -> None:
    import sqlite3

    from shared.persistence import change_path, init_db, leer_tabla, reset_path

    path = tmp_path / "vieja.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE ofertas ("
        "id TEXT PRIMARY KEY,"
        "enlace TEXT NOT NULL,"
        "titulo TEXT NOT NULL,"
        "descripcion_original TEXT NOT NULL"
        ")"
    )
    conn.execute(
        "INSERT INTO ofertas (id, enlace, titulo, descripcion_original) "
        "VALUES ('OFE-0001', 'https://x.com/1', 'Titulo Antiguo', 'Desc')"
    )
    conn.commit()
    conn.close()

    change_path(path)
    try:
        init_db()
        columnas = {
            fila[1]: fila[3] for fila in sqlite3.connect(str(path)).execute(
                "PRAGMA table_info(ofertas_descubiertas)"
            ).fetchall()
        }
        assert columnas["titulo"] == 0
        assert columnas["descripcion_original"] == 0
        rows = leer_tabla("ofertas_descubiertas")
        assert len(rows) == 1
        assert rows[0]["id"] == "OFE-0001"
        assert rows[0]["titulo"] == "Titulo Antiguo"
    finally:
        reset_path()


def test_migracion_c2_idempotente(tmp_path: Path) -> None:
    import sqlite3

    from shared.persistence import change_path, init_db, reset_path

    path = tmp_path / "nueva.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE ofertas ("
        "id TEXT PRIMARY KEY,"
        "enlace TEXT NOT NULL,"
        "titulo TEXT NOT NULL,"
        "descripcion_original TEXT NOT NULL"
        ")"
    )
    conn.commit()
    conn.close()

    change_path(path)
    try:
        init_db()
        init_db()
        columnas = {
            fila[1]: fila[3] for fila in sqlite3.connect(str(path)).execute(
                "PRAGMA table_info(ofertas_descubiertas)"
            ).fetchall()
        }
        assert columnas["titulo"] == 0
        assert columnas["descripcion_original"] == 0
    finally:
        reset_path()


def test_migracion_d32_renombra_ofertas_a_ofertas_descubiertas(
    tmp_path: Path,
) -> None:
    import sqlite3

    from shared.persistence import change_path, init_db, leer_tabla, reset_path

    path = tmp_path / "d32.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE ofertas ("
        "id TEXT PRIMARY KEY,"
        "enlace TEXT NOT NULL,"
        "titulo TEXT NOT NULL,"
        "descripcion_original TEXT NOT NULL"
        ")"
    )
    conn.execute(
        "INSERT INTO ofertas (id, enlace, titulo, descripcion_original) "
        "VALUES ('OFE-0001', 'https://x.com/1', 'Titulo Antiguo', 'Desc')"
    )
    conn.execute(
        "CREATE TABLE secuencia_ids ("
        "tabla_nombre TEXT PRIMARY KEY,"
        "prefijo TEXT NOT NULL,"
        "ultimo_numero INTEGER NOT NULL DEFAULT 0"
        ")"
    )
    conn.execute(
        "INSERT INTO secuencia_ids (tabla_nombre, prefijo, ultimo_numero) "
        "VALUES ('ofertas', 'OFE', 62)"
    )
    conn.commit()
    conn.close()

    change_path(path)
    try:
        init_db()
        conn = sqlite3.connect(str(path))
        try:
            tablas = {
                fila[0]
                for fila in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            secuencia = conn.execute(
                "SELECT tabla_nombre, prefijo, ultimo_numero FROM secuencia_ids"
            ).fetchone()
        finally:
            conn.close()
        assert "ofertas" not in tablas
        assert "ofertas_descubiertas" in tablas
        assert secuencia == ("ofertas_descubiertas", "OFE", 62)
        rows = leer_tabla("ofertas_descubiertas")
        assert len(rows) == 1
        assert rows[0]["id"] == "OFE-0001"
        assert rows[0]["titulo"] == "Titulo Antiguo"
    finally:
        reset_path()


def test_migracion_d32_idempotente(tmp_path: Path) -> None:
    import sqlite3

    from shared.persistence import change_path, init_db, leer_tabla, reset_path

    path = tmp_path / "d32_nueva.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE ofertas ("
        "id TEXT PRIMARY KEY,"
        "enlace TEXT NOT NULL,"
        "titulo TEXT NOT NULL,"
        "descripcion_original TEXT NOT NULL"
        ")"
    )
    conn.commit()
    conn.close()

    change_path(path)
    try:
        init_db()
        init_db()
        conn = sqlite3.connect(str(path))
        try:
            tablas = {
                fila[0]
                for fila in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()
        assert "ofertas" not in tablas
        assert "ofertas_descubiertas" in tablas
        assert len(leer_tabla("ofertas_descubiertas")) == 0
    finally:
        reset_path()


def test_probe_write_no_deja_filas(temp_db_file: Path) -> None:
    from shared.persistence import leer_tabla, sondear_escritura

    sondear_escritura()
    assert leer_tabla("bloqueo") == []


def test_write_corrida_idempotente(temp_db_file: Path) -> None:
    from shared.persistence import leer_tabla, registrar_corrida

    datos = {
        "id_corrida": "COR-0009",
        "fecha_inicio": "2026-08-07 10:00:00",
        "estado": "en_ejecucion",
    }
    registrar_corrida(datos)
    registrar_corrida(datos)
    filas = leer_tabla("corridas")
    assert len(filas) == 1
    assert filas[0]["id_corrida"] == "COR-0009"
    assert filas[0]["estado"] == "en_ejecucion"


def test_write_evento_genera_evento_id(temp_db_file: Path) -> None:
    from shared.persistence import escribir_evento, leer_tabla

    evt_id = escribir_evento(
        {
            "id_corrida": "RUN-0001",
            "fuente_id": "linkedin",
            "tipo": "suceso",
            "codigo": "ERR-07",
            "evidencia": "lock sobrescrito",
            "marca_temporal": "2026-08-07 10:00:00",
        }
    )
    assert evt_id.startswith("EVT-")
    filas = leer_tabla("eventos")
    assert len(filas) == 1
    assert filas[0]["evento_id"] == evt_id


def test_escribir_evento_rechaza_datos_invalidos(temp_db_file: Path) -> None:
    from pydantic import ValidationError

    from shared.persistence import escribir_evento, leer_tabla

    try:
        escribir_evento({"tipo": "suceso"})
    except ValidationError:
        pass
    else:
        raise AssertionError("deberia rechazar evento sin id_corrida ni codigo")
    assert leer_tabla("eventos") == []


def test_escribir_evento_seguro_no_aborta_y_persiste(temp_db_file: Path) -> None:

    from shared.persistence import escribir_evento_seguro, leer_tabla

    escribir_evento_seguro(
        {
            "id_corrida": "RUN-0001",
            "tipo": "suceso",
            "codigo": "captura_completada",
            "evidencia": "ok",
        },
        contexto_log="RUN-0001",
    )
    filas = leer_tabla("eventos")
    assert len(filas) == 1
    assert filas[0]["codigo"] == "captura_completada"


def test_escribir_evento_seguro_no_aborta_ante_fallo_de_escritura(
    temp_db_file: Path,
) -> None:
    from unittest.mock import patch

    from shared.persistence import escribir_evento_seguro

    with patch("shared.persistence.escribir_evento", side_effect=Exception("DB Error")):
        escribir_evento_seguro(
            {"id_corrida": "RUN-0001", "tipo": "error", "codigo": "ERR-05", "evidencia": "x"}
        )


def test_registrar_corrida_rechaza_estado_invalido(temp_db_file: Path) -> None:
    from pydantic import ValidationError

    from shared.persistence import leer_tabla, registrar_corrida

    try:
        registrar_corrida(
            {"id_corrida": "COR-0099", "estado": "estado_inventado"}
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("deberia rechazar estado fuera del catalogo")
    assert leer_tabla("corridas") == []


def test_actualizar_corrida_rechaza_estado_invalido(temp_db_file: Path) -> None:
    from pydantic import ValidationError

    from shared.persistence import actualizar_corrida

    try:
        actualizar_corrida("COR-0099", {"estado": "estado_inventado"})
    except ValidationError:
        pass
    else:
        raise AssertionError("deberia rechazar estado fuera del catalogo")


def test_actualizar_corrida_rechaza_metricas_con_tipo_incorrecto(
    temp_db_file: Path,
) -> None:
    from pydantic import ValidationError

    from shared.persistence import actualizar_corrida

    try:
        actualizar_corrida("COR-0099", {"total_ofertas": "tres"})
    except ValidationError:
        pass
    else:
        raise AssertionError("deberia rechazar metrica con tipo incorrecto")


def test_actualizar_corrida_rechaza_campo_desconocido(temp_db_file: Path) -> None:
    from pydantic import ValidationError

    from shared.persistence import actualizar_corrida

    try:
        actualizar_corrida("COR-0099", {"campo_inventado": "x"})
    except ValidationError:
        pass
    else:
        raise AssertionError("deberia rechazar campo fuera del modelo Corrida")


def test_lock_forzar_sobrescribe_y_contienda_mantiene(temp_db_file: Path) -> None:
    import datetime

    from shared.persistence import adquirir_bloqueo, consultar_bloqueo

    ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    assert adquirir_bloqueo("COR-0001", ahora) is True
    assert adquirir_bloqueo("COR-0002", ahora, forzar=True) is True
    lock = consultar_bloqueo()
    assert lock is not None
    assert lock["id_corrida"] == "COR-0002"


def test_upsert_oferta_inserta_nueva(temp_db_file: Path) -> None:
    from shared.persistence import leer_tabla, upsert_oferta

    oferta = {
        "titulo": "Desarrollador Python",
        "descripcion_original": "Descripcion.",
        "empresa_id": None,
        "ubicacion_id": None,
        "enlace": "https://www.linkedin.com/jobs/view/123",
        "fuente_id": "LI-01",
        "indice_set": 0,
        "id_externo": "123",
        "id_corrida": "RUN-0001",
        "id_sesion": "SES-0001",
        "fecha_descubrimiento": "2026-08-09 10:00:00",
    }

    id_oferta = upsert_oferta(oferta)
    assert id_oferta.startswith("OFE-")

    filas = leer_tabla("ofertas_descubiertas", {"id": id_oferta})
    assert len(filas) == 1
    assert filas[0]["titulo"] == "Desarrollador Python"
    assert filas[0]["fuente_id"] == "LI-01"
    assert filas[0]["empresa_id"] == "N/A"
    assert filas[0]["ubicacion_id"] == "N/A"


def test_upsert_oferta_ids_nulos_sin_fk_error(temp_db_file: Path) -> None:
    from shared.persistence import leer_tabla, upsert_oferta

    id_oferta = upsert_oferta(
        {
            "titulo": "Data Analyst",
            "descripcion_original": "Sin empresa registrada.",
            "empresa_id": None,
            "ubicacion_id": None,
            "enlace": "https://www.linkedin.com/jobs/view/456",
            "fuente_id": "LI-01",
            "indice_set": 1,
            "id_externo": "456",
            "id_corrida": "RUN-0002",
            "id_sesion": "SES-0002",
            "fecha_descubrimiento": "2026-08-09 10:05:00",
        }
    )
    assert id_oferta.startswith("OFE-")
    filas = leer_tabla("ofertas_descubiertas", {"id_externo": "456"})
    assert len(filas) == 1
    assert filas[0]["empresa_id"] == "N/A"
    assert filas[0]["ubicacion_id"] == "N/A"


def test_init_db_crea_indices_esperados(temp_db_file: Path) -> None:
    import sqlite3

    from shared.persistence import init_db

    init_db()
    conn = sqlite3.connect(temp_db_file)
    try:
        indices = {
            fila[1]
            for tabla in ("ofertas_descubiertas", "eventos")
            for fila in conn.execute(f"PRAGMA index_list('{tabla}')")
        }
    finally:
        conn.close()
    assert {
        "idx_ofertas_id_externo",
        "idx_ofertas_id_corrida",
        "idx_eventos_id_corrida",
    } <= indices


def test_upsert_oferta_mismo_id_externo_no_duplica_y_actualiza_timestamp(
    temp_db_file: Path,
) -> None:
    from shared.persistence import leer_tabla, upsert_oferta

    base = {
        "titulo": "Ingeniero DevOps",
        "descripcion_original": "Descripcion.",
        "empresa_id": None,
        "ubicacion_id": None,
        "enlace": "https://www.linkedin.com/jobs/view/789",
        "fuente_id": "LI-01",
        "indice_set": 0,
        "id_externo": "789",
        "id_corrida": "RUN-0003",
        "id_sesion": "SES-0003",
        "fecha_descubrimiento": "2026-08-09 10:00:00",
    }
    primero = upsert_oferta(dict(base))
    segundo = upsert_oferta(dict(base))

    assert primero == segundo
    filas = leer_tabla("ofertas_descubiertas", {"id_externo": "789"})
    assert len(filas) == 1
    assert filas[0]["fecha_ultima_verificacion"] != ""
    assert filas[0]["id"] == primero


def _oferta_base(
    id_externo: str, enlace: str | None, id_corrida: str = "RUN-0005"
) -> dict[str, Any]:
    return {
        "titulo": "Oferta " + id_externo,
        "descripcion_original": "Descripcion.",
        "empresa_id": None,
        "ubicacion_id": None,
        "enlace": enlace,
        "fuente_id": "LI-01",
        "indice_set": 0,
        "id_externo": id_externo,
        "id_corrida": id_corrida,
        "id_sesion": "SES-0005",
        "fecha_descubrimiento": "2026-08-09 10:00:00",
    }


def test_upsert_lote_ofertas_inserta_nuevas(temp_db_file: Path) -> None:
    from shared.persistence import leer_tabla, upsert_lote_ofertas

    filas = [
        _oferta_base("1", "https://www.linkedin.com/jobs/view/1"),
        _oferta_base("2", "https://www.linkedin.com/jobs/view/2"),
    ]
    registradas, fallidas = upsert_lote_ofertas(filas)

    assert registradas == 2
    assert fallidas == 0
    assert len(leer_tabla("ofertas_descubiertas", {"id_corrida": "RUN-0005"})) == 2


def test_upsert_lote_ofertas_mismo_id_externo_no_duplica(
    temp_db_file: Path,
) -> None:
    from shared.persistence import leer_tabla, upsert_lote_ofertas

    base = _oferta_base("789", "https://www.linkedin.com/jobs/view/789")
    registradas, fallidas = upsert_lote_ofertas([dict(base), dict(base)])

    assert registradas == 2
    assert fallidas == 0
    filas = leer_tabla("ofertas_descubiertas", {"id_externo": "789"})
    assert len(filas) == 1
    assert filas[0]["fecha_ultima_verificacion"] != ""


def test_upsert_lote_ofertas_fila_invalida_no_pierde_lote(temp_db_file: Path) -> None:
    from shared.persistence import leer_tabla, upsert_lote_ofertas

    invalida = _oferta_base("bad", None)
    valida = _oferta_base("ok", "https://www.linkedin.com/jobs/view/ok")
    registradas, fallidas = upsert_lote_ofertas([invalida, valida])

    assert registradas == 1
    assert fallidas == 1
    filas = leer_tabla("ofertas_descubiertas", {"id_corrida": "RUN-0005"})
    assert len(filas) == 1
    assert filas[0]["id_externo"] == "ok"


def test_upsert_lote_ofertas_vacio_no_op(temp_db_file: Path) -> None:
    from shared.persistence import upsert_lote_ofertas

    assert upsert_lote_ofertas([]) == (0, 0)


def test_upsert_oferta_fila_invalida_error_descriptivo(temp_db_file: Path) -> None:
    from shared.errors import PersistenceError
    from shared.persistence import upsert_oferta

    invalida = _oferta_base("bad", None)
    with pytest.raises(PersistenceError) as exc:
        upsert_oferta(invalida)
    assert "id_externo=bad" in str(exc.value)


def test_contar_filas_con_y_sin_filtros(temp_db_file: Path) -> None:
    from shared.persistence import contar_filas, escribir_evento

    escribir_evento(
        {"id_corrida": "COR-0001", "tipo": "suceso", "codigo": "a", "fuente_id": "LI-01"}
    )
    escribir_evento(
        {"id_corrida": "COR-0001", "tipo": "error", "codigo": "b", "fuente_id": "LI-01"}
    )
    escribir_evento(
        {"id_corrida": "COR-0002", "tipo": "suceso", "codigo": "c", "fuente_id": ""}
    )

    assert contar_filas("eventos") == 3
    assert contar_filas("eventos", {"id_corrida": "COR-0001"}) == 2
    assert contar_filas("eventos", {"id_corrida": "COR-0001", "tipo": "error"}) == 1
    assert contar_filas("eventos", {}) == 3


def test_contar_distintos_excluye_vacios(temp_db_file: Path) -> None:
    from shared.persistence import contar_distintos, escribir_evento

    escribir_evento(
        {"id_corrida": "COR-0001", "tipo": "suceso", "codigo": "a", "fuente_id": "LI-01"}
    )
    escribir_evento(
        {"id_corrida": "COR-0001", "tipo": "error", "codigo": "b", "fuente_id": "LI-01"}
    )
    escribir_evento(
        {"id_corrida": "COR-0002", "tipo": "suceso", "codigo": "c", "fuente_id": ""}
    )
    escribir_evento(
        {"id_corrida": "COR-0003", "tipo": "suceso", "codigo": "corrida_completada"}
    )

    assert contar_distintos("eventos", "fuente_id", {"id_corrida": "COR-0001"}) == 1
    assert contar_distintos("eventos", "fuente_id", {}) == 1
    assert contar_distintos("eventos", "fuente_id") == 1


def test_contar_distintos_acepta_filtro_con_lista(temp_db_file: Path) -> None:
    """Un filtro cuyo valor es lista coincide por IN (unión de códigos del
    cierre M2: total_ofertas cuenta el DISTINCT físico)."""
    from shared.persistence import contar_distintos, escribir_evento

    for codigo, id_oferta in (
        ("oferta_preparada", "OFE-0001"),
        ("oferta_preparada", "OFE-0002"),
        ("oferta_duplicada", "OFE-0002"),
        ("revision_pendientes", "N/A"),
    ):
        escribir_evento(
            {
                "id_corrida": "COR-0001",
                "tipo": "suceso",
                "codigo": codigo,
                "id_oferta": id_oferta,
            }
        )
    filtros = {
        "id_corrida": "COR-0001",
        "codigo": ["oferta_preparada", "oferta_duplicada"],
    }
    assert contar_distintos("eventos", "id_oferta", filtros) == 2


def test_eventos_sin_vacios_se_guardan_como_n_a(temp_db_file: Path) -> None:
    from shared.persistence import escribir_evento, leer_tabla

    escribir_evento(
        {
            "id_corrida": "COR-0001",
            "tipo": "suceso",
            "codigo": "corrida_completada",
            "evidencia": "ok",
        }
    )
    escribir_evento(
        {
            "id_corrida": "COR-0002",
            "tipo": "error",
            "codigo": "fuente_inalcanzable",
            "fuente_id": "",
        }
    )

    filas = leer_tabla("eventos", {"id_corrida": "COR-0001"})
    assert len(filas) == 1
    assert filas[0]["fuente_id"] == "N/A"
    assert filas[0]["id_sesion"] == "N/A"
    assert filas[0]["indice_set"] == "N/A"
    filas = leer_tabla("eventos", {"id_corrida": "COR-0002"})
    assert len(filas) == 1
    assert filas[0]["fuente_id"] == "N/A"


def test_ofertas_sin_vacios_se_guardan_como_n_a(temp_db_file: Path) -> None:
    from shared.persistence import leer_tabla, upsert_oferta

    id_oferta = upsert_oferta(
        {
            "titulo": "Data Analyst",
            "descripcion_original": "",
            "empresa_id": None,
            "ubicacion_id": None,
            "enlace": "https://www.linkedin.com/jobs/view/789",
            "fuente_id": "LI-01",
            "indice_set": 1,
            "id_externo": "789",
            "id_corrida": "COR-0002",
            "id_sesion": "SES-0002",
            "fecha_descubrimiento": "2026-08-09 10:05:00",
        }
    )
    filas = leer_tabla("ofertas_descubiertas", {"id": id_oferta})
    assert len(filas) == 1
    assert filas[0]["descripcion_original"] == "N/A"
    assert filas[0]["empresa_id"] == "N/A"
    assert filas[0]["ubicacion_id"] == "N/A"
    assert filas[0]["observaciones"] == "N/A"
    assert filas[0]["fecha_publicacion"] == "N/A"


def test_migracion_4_4_fks_anulables_idempotente(tmp_path: Path) -> None:
    import sqlite3

    from shared.persistence import change_path, init_db, leer_tabla, reset_path

    path = tmp_path / "fk.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE ofertas ("
        "id TEXT PRIMARY KEY,"
        "enlace TEXT NOT NULL,"
        "titulo TEXT NOT NULL,"
        "descripcion_original TEXT NOT NULL,"
        "fuente_id TEXT REFERENCES fuentes(id),"
        "empresa_id TEXT REFERENCES empresas(id),"
        "ubicacion_id TEXT REFERENCES ubicaciones(id)"
        ")"
    )
    conn.execute(
        "INSERT INTO ofertas (id, enlace, titulo, descripcion_original) "
        "VALUES ('OFE-0001', 'https://x.com/1', 'Vieja', 'Desc')"
    )
    conn.commit()
    conn.close()

    change_path(path)
    try:
        init_db()
        init_db()
        columnas = {
            fila[1]
            for fila in sqlite3.connect(str(path)).execute(
                "PRAGMA table_info(ofertas_descubiertas)"
            ).fetchall()
        }
        assert "empresa_nombre" not in columnas
        # Traspaso 2026-08-25: la columna D33 se renombra a `ubicacion`.
        assert "ubicacion" in columnas
        assert "ubicacion_nombre" not in columnas
        fks = sqlite3.connect(str(path)).execute(
            "PRAGMA foreign_key_list(ofertas_descubiertas)"
        ).fetchall()
        assert fks == []
        rows = leer_tabla("ofertas_descubiertas")
        assert len(rows) == 1
        assert rows[0]["id"] == "OFE-0001"
        assert rows[0]["titulo"] == "Vieja"
    finally:
        reset_path()


def test_migracion_sesiones_desde_esquema_antiguo(tmp_path: Path) -> None:
    import sqlite3

    from shared.persistence import change_path, init_db, reset_path

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE sesiones ("
        "id_sesion TEXT PRIMARY KEY,"
        "id_corrida TEXT NOT NULL,"
        "fuente_id TEXT NOT NULL,"
        "indice_set INTEGER DEFAULT '',"
        "marca_temporal TEXT NOT NULL,"
        "total_declarado INTEGER DEFAULT '',"
        "conteo INTEGER DEFAULT '',"
        "estado TEXT NOT NULL"
        ")"
    )
    conn.execute(
        "INSERT INTO sesiones (id_sesion, id_corrida, fuente_id, marca_temporal, "
        "conteo, estado) VALUES "
        "('SES-0100', 'COR-1000', 'linkedin', '2026-08-10 10:00:00', 5, "
        "'completa')"
    )
    conn.commit()
    conn.close()

    change_path(path)
    try:
        init_db()
        columnas = {
            fila[1]
            for fila in sqlite3.connect(str(path)).execute(
                "PRAGMA table_info(sesiones)"
            ).fetchall()
        }
        assert "id" in columnas
        assert "fecha_creacion" in columnas
        assert "fecha_ultima_edicion" in columnas
        rows = leer_tabla("sesiones")
        assert len(rows) == 1
        assert rows[0]["id"] == "SES-0100"
        assert rows[0]["id_sesion"] == "SES-0100"
        assert rows[0]["conteo"] == 5
    finally:
        reset_path()


def test_migracion_sesiones_idempotente(tmp_path: Path) -> None:
    import sqlite3

    from shared.persistence import change_path, init_db, reset_path

    path = tmp_path / "nueva.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE sesiones ("
        "id_sesion TEXT PRIMARY KEY,"
        "id_corrida TEXT NOT NULL,"
        "fuente_id TEXT NOT NULL,"
        "indice_set INTEGER DEFAULT '',"
        "marca_temporal TEXT NOT NULL,"
        "total_declarado INTEGER DEFAULT '',"
        "conteo INTEGER DEFAULT '',"
        "estado TEXT NOT NULL"
        ")"
    )
    conn.commit()
    conn.close()

    change_path(path)
    try:
        init_db()
        init_db()
        columnas = {
            fila[1]
            for fila in sqlite3.connect(str(path)).execute(
                "PRAGMA table_info(sesiones)"
            ).fetchall()
        }
        assert "id" in columnas
        assert len(leer_tabla("sesiones")) == 0
    finally:
        reset_path()


def test_write_row_sesiones_auditoria(temp_db_file: Path) -> None:
    import sqlite3

    from shared.persistence import escribir_fila

    fila = {
        "id": "SES-0201",
        "id_sesion": "SES-0201",
        "id_corrida": "COR-1839",
        "fuente_id": "linkedin",
        "indice_set": 0,
        "marca_temporal": "2026-08-10 16:37:08",
        "total_declarado": 7,
        "conteo": 7,
        "estado": "completa",
    }
    returned_id = escribir_fila("sesiones", fila)
    assert returned_id == "SES-0201"

    conn = sqlite3.connect(str(temp_db_file))
    try:
        rows = conn.execute(
            "SELECT id, id_sesion, id_corrida, conteo, estado, fecha_creacion, "
            "fecha_ultima_edicion FROM sesiones"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "SES-0201"
    assert rows[0][1] == "SES-0201"
    assert rows[0][2] == "COR-1839"
    assert rows[0][3] == 7
    assert rows[0][4] == "completa"
    assert rows[0][5] != ""
    assert rows[0][6] == rows[0][5]


def _crear_esquema_ingles(path: Path) -> None:
    """Crea una BD con el esquema legacy (inglés) de la era pre-español."""
    import sqlite3

    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE fuentes (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            tipo TEXT DEFAULT '',
            url_base TEXT DEFAULT '',
            activa INTEGER DEFAULT 1,
            creation_date TEXT DEFAULT '',
            last_edit_date TEXT DEFAULT ''
        );
        CREATE TABLE empresas (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            normalized_name TEXT DEFAULT '',
            sitio_web TEXT DEFAULT '',
            linkedin TEXT DEFAULT '',
            sector TEXT DEFAULT '',
            size TEXT DEFAULT '',
            descripcion TEXT DEFAULT '',
            creation_date TEXT DEFAULT '',
            last_edit_date TEXT DEFAULT ''
        );
        CREATE TABLE ubicaciones (
            id TEXT PRIMARY KEY,
            ciudad TEXT DEFAULT '',
            region TEXT DEFAULT '',
            pais TEXT DEFAULT '',
            modalidad TEXT DEFAULT '',
            creation_date TEXT DEFAULT '',
            last_edit_date TEXT DEFAULT ''
        );
        CREATE TABLE ofertas (
            id TEXT PRIMARY KEY,
            source_identifier TEXT DEFAULT '',
            url TEXT NOT NULL,
            titulo TEXT DEFAULT '',
            descripcion_original TEXT DEFAULT '',
            fecha_publicacion TEXT DEFAULT '',
            discovery_date TEXT DEFAULT '',
            estado TEXT DEFAULT 'discovered'
                CHECK(estado IN ('discovered','prepared','evaluated',
                'accepted','discarded','processed','finalized')),
            observaciones TEXT DEFAULT '',
            creation_date TEXT DEFAULT '',
            last_edit_date TEXT DEFAULT '',
            fuente_id TEXT DEFAULT '',
            empresa_id TEXT DEFAULT '',
            ubicacion_id TEXT DEFAULT '',
            empresa_nombre TEXT DEFAULT '',
            ubicacion_nombre TEXT DEFAULT '',
            run_id TEXT DEFAULT '',
            session_id TEXT DEFAULT '',
            set_indice INTEGER DEFAULT '',
            id_externo_url TEXT DEFAULT '',
            timestamp_ultima_verificacion TEXT DEFAULT ''
        );
        CREATE TABLE corridas (
            run_id TEXT PRIMARY KEY,
            timestamp_inicio TEXT NOT NULL,
            estado TEXT NOT NULL
        );
        CREATE TABLE eventos (
            evento_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            source_id TEXT DEFAULT '',
            session_id TEXT DEFAULT '',
            set_indice INTEGER DEFAULT '',
            timestamp TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK(tipo IN ('error','suceso')),
            codigo TEXT NOT NULL,
            evidencia TEXT DEFAULT '',
            offer_id TEXT DEFAULT ''
        );
        CREATE TABLE sesiones (
            session_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            set_indice INTEGER DEFAULT '',
            timestamp TEXT NOT NULL,
            total_declarado INTEGER DEFAULT '',
            conteo INTEGER DEFAULT '',
            estado TEXT NOT NULL
        );
        CREATE TABLE bloqueo (
            run_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL
        );
        CREATE TABLE secuencia_ids (
            tabla_nombre TEXT PRIMARY KEY,
            prefijo TEXT NOT NULL,
            ultimo_numero INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.execute(
        "INSERT INTO fuentes (id, nombre, tipo, url_base, activa, creation_date, "
        "last_edit_date) VALUES ('FNT-0001', 'LinkedIn', 'red_social', "
        "'https://www.linkedin.com/jobs', 1, '2026-01-01 10:00:00', "
        "'2026-01-01 10:00:00')"
    )
    conn.execute(
        "INSERT INTO empresas (id, nombre, normalized_name, sitio_web, linkedin, "
        "sector, size, creation_date, last_edit_date) VALUES "
        "('EMP-0001', 'TechCorp', 'techcorp', 'https://techcorp.com', "
        "'https://www.linkedin.com/company/techcorp', 'tecnologia', '500-1000', "
        "'2026-01-01 10:00:00', '2026-01-01 10:00:00')"
    )
    conn.execute(
        "INSERT INTO ofertas (id, source_identifier, url, titulo, "
        "descripcion_original, discovery_date, estado, run_id, session_id, "
        "set_indice, id_externo_url, timestamp_ultima_verificacion) VALUES "
        "('OFE-0001', 'LI-1', 'https://www.linkedin.com/jobs/view/4439280106', "
        "'Data Engineer', 'Desc.', '2026-08-10 16:38:02', 'discovered', "
        "'COR-1839', 'SES-0218', 0, '4439280106', '2026-08-10 16:38:02')"
    )
    conn.execute(
        "INSERT INTO corridas (run_id, timestamp_inicio, estado) VALUES "
        "('COR-1839', '2026-08-10 16:37:00', 'en_ejecucion')"
    )
    conn.execute(
        "INSERT INTO eventos (evento_id, run_id, source_id, session_id, "
        "set_indice, timestamp, tipo, codigo, evidencia, offer_id) VALUES "
        "('EVT-0001', 'COR-1839', 'linkedin', 'SES-0218', 0, "
        "'2026-08-10 16:38:00', 'suceso', 'ofertas_registradas', '7', 'OFE-0001')"
    )
    conn.execute(
        "INSERT INTO sesiones (session_id, run_id, source_id, set_indice, "
        "timestamp, total_declarado, conteo, estado) VALUES "
        "('SES-0218', 'COR-1839', 'linkedin', 0, '2026-08-10 16:38:00', 7, 7, "
        "'completa')"
    )
    conn.execute(
        "INSERT INTO bloqueo (run_id, timestamp) VALUES "
        "('COR-1839', '2026-08-10 16:37:00')"
    )
    conn.commit()
    conn.close()


def test_migracion_espanol_total_desde_esquema_ingles(tmp_path: Path) -> None:
    import sqlite3

    from shared.persistence import change_path, init_db, leer_tabla, reset_path

    path = tmp_path / "ingles.db"
    _crear_esquema_ingles(path)

    change_path(path)
    try:
        init_db()
        conn = sqlite3.connect(str(path))
        try:
            columnas_ofertas = {
                fila[1] for fila in conn.execute(
                    "PRAGMA table_info(ofertas_descubiertas)"
                ).fetchall()
            }
            esperadas_ofertas = {
                "enlace", "fecha_descubrimiento",
                "id_corrida", "id_sesion", "indice_set", "id_externo",
                "fecha_ultima_verificacion", "fecha_creacion",
                "fecha_ultima_edicion",
            }
            assert esperadas_ofertas.issubset(columnas_ofertas)
            assert "identificador_origen" not in columnas_ofertas
            assert "empresa_nombre" not in columnas_ofertas
            assert "ubicacion" in columnas_ofertas
            sql_ofertas = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name='ofertas_descubiertas'"
            ).fetchone()[0]
            assert "descubierta" in sql_ofertas
            assert "discovered" not in sql_ofertas
            tablas = {
                fila[0] for fila in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "fuentes" not in tablas
            for tabla, esperadas in {
                "empresas": {"nombre_normalizado", "perfil_linkedin"},
                "corridas": {"id_corrida", "fecha_inicio"},
                "eventos": {"id_corrida", "fuente_id", "marca_temporal"},
                "sesiones": {"id", "id_sesion", "id_corrida", "fuente_id"},
                "bloqueo": {"id_corrida", "marca_temporal"},
            }.items():
                columnas = {
                    fila[1] for fila in conn.execute(
                        f"PRAGMA table_info({tabla})"
                    ).fetchall()
                }
                assert esperadas.issubset(columnas), f"{tabla}: {esperadas - columnas}"
            columnas_eventos = {
                fila[1] for fila in conn.execute(
                    "PRAGMA table_info(eventos)"
                ).fetchall()
            }
            # D33 re-adds `eventos.id_oferta` (supersedes D31 D-1).
            assert "id_oferta" in columnas_eventos
        finally:
            conn.close()

        ofertas = leer_tabla("ofertas_descubiertas")
        assert len(ofertas) == 1
        oferta = ofertas[0]
        assert oferta["id"] == "OFE-0001"
        assert oferta["enlace"] == "https://www.linkedin.com/jobs/view/4439280106"
        assert oferta["id_externo"] == "4439280106"
        assert oferta["id_corrida"] == "COR-1839"
        assert oferta["id_sesion"] == "SES-0218"
        assert oferta["indice_set"] == 0
        assert oferta["fecha_descubrimiento"] == "2026-08-10 16:38:02"
        assert oferta["fecha_ultima_verificacion"] == "2026-08-10 16:38:02"
        assert oferta["estado"] == "descubierta"

        empresas = leer_tabla("empresas")
        assert empresas[0]["nombre_normalizado"] == "techcorp"
        assert empresas[0]["perfil_linkedin"] == "https://www.linkedin.com/company/techcorp"
        eventos = leer_tabla("eventos")
        assert eventos[0]["id_corrida"] == "COR-1839"
        assert eventos[0]["fuente_id"] == "linkedin"
        assert eventos[0]["id_oferta"] == "N/A"
        sesiones = leer_tabla("sesiones")
        assert len(sesiones) == 1
        assert sesiones[0]["id"] == "SES-0218"
        assert sesiones[0]["id_sesion"] == "SES-0218"
        bloqueo = leer_tabla("bloqueo")
        assert bloqueo[0]["id_corrida"] == "COR-1839"
    finally:
        reset_path()


def test_migracion_espanol_total_idempotente(tmp_path: Path) -> None:
    import sqlite3

    from shared.persistence import change_path, init_db, leer_tabla, reset_path

    path = tmp_path / "ingles2.db"
    _crear_esquema_ingles(path)

    change_path(path)
    try:
        init_db()
        init_db()
        conn = sqlite3.connect(str(path))
        try:
            columnas = {
                fila[1] for fila in conn.execute(
                    "PRAGMA table_info(ofertas_descubiertas)"
                ).fetchall()
            }
        finally:
            conn.close()
        assert "identificador_origen" not in columnas
        rows = leer_tabla("ofertas_descubiertas")
        assert len(rows) == 1
        assert rows[0]["id"] == "OFE-0001"
        assert rows[0]["enlace"] == "https://www.linkedin.com/jobs/view/4439280106"
    finally:
        reset_path()


def test_migracion_espanol_total_base_nueva_no_reconstruye(tmp_path: Path) -> None:
    import sqlite3

    from shared.persistence import change_path, init_db, reset_path

    path = tmp_path / "nueva_espanol.db"
    change_path(path)
    try:
        init_db()
        init_db()
        conn = sqlite3.connect(str(path))
        try:
            columnas = {
                fila[1] for fila in conn.execute(
                    "PRAGMA table_info(ofertas_descubiertas)"
                ).fetchall()
            }
        finally:
            conn.close()
        assert "identificador_origen" not in columnas
        assert "enlace" in columnas
        assert "fecha_descubrimiento" in columnas
    finally:
        reset_path()


def _crear_bd_legado_pre_d33(path: Path) -> None:
    """Builds a post-D31 / pre-D33 legacy DB (7-state CHECK, no preparation
    columns, `ubicaciones` with `modalidad`, `eventos` without `id_oferta`)."""
    import sqlite3

    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE ofertas_descubiertas ("
        "id TEXT PRIMARY KEY,"
        "enlace TEXT NOT NULL,"
        "titulo TEXT DEFAULT '',"
        "descripcion_original TEXT DEFAULT 'N/A',"
        "fecha_publicacion TEXT DEFAULT 'N/A',"
        "fecha_descubrimiento TEXT DEFAULT '',"
        "estado TEXT DEFAULT 'descubierta' "
        "CHECK(estado IN ('descubierta','preparada','evaluada',"
        "'aceptada','descartada','procesada','finalizada')),"
        "observaciones TEXT DEFAULT 'N/A',"
        "fecha_creacion TEXT DEFAULT '',"
        "fecha_ultima_edicion TEXT DEFAULT '',"
        "fuente_id TEXT DEFAULT '',"
        "empresa_id TEXT DEFAULT 'N/A',"
        "ubicacion_id TEXT DEFAULT 'N/A',"
        "id_corrida TEXT DEFAULT '',"
        "id_sesion TEXT DEFAULT '',"
        "indice_set INTEGER DEFAULT '',"
        "id_externo TEXT DEFAULT '',"
        "fecha_ultima_verificacion TEXT DEFAULT ''"
        ")"
    )
    conn.execute(
        "INSERT INTO ofertas_descubiertas (id, enlace, titulo, estado, id_externo) "
        "VALUES ('OFE-0001', 'https://x.com/1', 'Titulo Legado', 'descubierta', 'li-1')"
    )
    conn.execute(
        "CREATE TABLE ubicaciones ("
        "id TEXT PRIMARY KEY,"
        "ciudad TEXT DEFAULT '',"
        "region TEXT DEFAULT '',"
        "pais TEXT DEFAULT '',"
        "modalidad TEXT DEFAULT '',"
        "fecha_creacion TEXT DEFAULT '',"
        "fecha_ultima_edicion TEXT DEFAULT ''"
        ")"
    )
    conn.execute(
        "INSERT INTO ubicaciones (id, ciudad, pais, modalidad) "
        "VALUES ('UBI-0001', 'Madrid', 'Espana', 'remoto')"
    )
    conn.execute(
        "CREATE TABLE eventos ("
        "evento_id TEXT PRIMARY KEY,"
        "id_corrida TEXT NOT NULL,"
        "fuente_id TEXT DEFAULT 'N/A',"
        "id_sesion TEXT DEFAULT 'N/A',"
        "indice_set INTEGER DEFAULT 'N/A',"
        "marca_temporal TEXT NOT NULL,"
        "tipo TEXT NOT NULL CHECK(tipo IN ('error','suceso')),"
        "codigo TEXT NOT NULL,"
        "evidencia TEXT DEFAULT 'N/A'"
        ")"
    )
    conn.execute(
        "INSERT INTO eventos (evento_id, id_corrida, marca_temporal, tipo, codigo) "
        "VALUES ('EVT-0001', 'COR-0001', '2026-08-20 10:00:00', 'suceso', "
        "'captura_completada')"
    )
    conn.execute(
        "CREATE TABLE corridas ("
        "id_corrida TEXT PRIMARY KEY,"
        "fecha_inicio TEXT NOT NULL,"
        "estado TEXT NOT NULL"
        ")"
    )
    conn.execute(
        "INSERT INTO corridas (id_corrida, fecha_inicio, estado) "
        "VALUES ('COR-0001', '2026-08-20 10:00:00', 'en_ejecucion')"
    )
    conn.execute(
        "CREATE TABLE secuencia_ids ("
        "tabla_nombre TEXT PRIMARY KEY,"
        "prefijo TEXT NOT NULL,"
        "ultimo_numero INTEGER NOT NULL DEFAULT 0"
        ")"
    )
    conn.execute(
        "INSERT INTO secuencia_ids (tabla_nombre, prefijo, ultimo_numero) "
        "VALUES ('ofertas_descubiertas', 'OFE', 1)"
    )
    conn.execute(
        "INSERT INTO secuencia_ids (tabla_nombre, prefijo, ultimo_numero) "
        "VALUES ('eventos', 'EVT', 5)"
    )
    conn.commit()
    conn.close()


def test_esquema_fresco_d33_columnas_check_y_ubicaciones(temp_db_file: Path) -> None:
    from shared.persistence import _connection

    conn = _connection()
    try:
        columnas_ofertas = {
            fila["name"]
            for fila in conn.execute(
                "PRAGMA table_info(ofertas_descubiertas)"
            ).fetchall()
        }
        assert {"id_duplicidad", "ubicacion", "modalidad"} <= columnas_ofertas
        columnas_corridas = {
            fila["name"]
            for fila in conn.execute("PRAGMA table_info(corridas)").fetchall()
        }
        assert {"total_preparadas", "total_duplicadas"} <= columnas_corridas
        columnas_eventos = {
            fila["name"]
            for fila in conn.execute("PRAGMA table_info(eventos)").fetchall()
        }
        assert "id_oferta" in columnas_eventos
        columnas_ubicaciones = {
            fila["name"]
            for fila in conn.execute("PRAGMA table_info(ubicaciones)").fetchall()
        }
        assert "modalidad" not in columnas_ubicaciones
        conn.execute(
            "INSERT INTO ofertas_descubiertas (id, enlace, estado) "
            "VALUES ('OFE-9001', 'https://x.com/9001', 'duplicada')"
        )
        conn.commit()
    finally:
        conn.close()


def test_migracion_d33_desde_esquema_legado(tmp_path: Path) -> None:
    import sqlite3

    from shared.persistence import change_path, init_db, leer_tabla, reset_path

    path = tmp_path / "legado_d33.db"
    _crear_bd_legado_pre_d33(path)

    change_path(path)
    try:
        init_db()
        filas = leer_tabla("ofertas_descubiertas")
        assert len(filas) == 1
        assert filas[0]["id"] == "OFE-0001"
        assert filas[0]["titulo"] == "Titulo Legado"
        assert filas[0]["id_duplicidad"] == "N/A"
        assert filas[0]["ubicacion"] == "N/A"
        assert filas[0]["modalidad"] == "N/A"

        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                "UPDATE ofertas_descubiertas SET estado = 'duplicada' "
                "WHERE id = 'OFE-0001'"
            )
            conn.commit()
            columnas_ubicaciones = {
                fila[1]
                for fila in conn.execute(
                    "PRAGMA table_info(ubicaciones)"
                ).fetchall()
            }
            columnas_corridas = {
                fila[1]
                for fila in conn.execute("PRAGMA table_info(corridas)").fetchall()
            }
        finally:
            conn.close()
        assert "modalidad" not in columnas_ubicaciones
        assert {"total_preparadas", "total_duplicadas"} <= columnas_corridas

        corrida = leer_tabla("corridas", {"id_corrida": "COR-0001"})[0]
        assert corrida["total_preparadas"] == 0
        assert corrida["total_duplicadas"] == 0

        ubis = leer_tabla("ubicaciones")
        assert len(ubis) == 1
        assert ubis[0]["ciudad"] == "Madrid"

        evs = leer_tabla("eventos")
        assert len(evs) == 1
        assert evs[0]["codigo"] == "captura_completada"
        assert evs[0]["id_oferta"] == "N/A"

        assert leer_tabla("ofertas_descubiertas")[0]["estado"] == "duplicada"
    finally:
        reset_path()


def test_ubicacion_nombre_legada_se_renombra_y_sobrevive(tmp_path: Path) -> None:
    """Regression guard: `_migrate_ubicacion_rename` renames the D33-era
    `ubicacion_nombre` to `ubicacion` preserving populated values, so no
    raw location text is silently lost by `init_db()`."""
    import sqlite3

    from shared.persistence import change_path, init_db, leer_tabla, reset_path

    path = tmp_path / "pre_d29.db"
    _crear_bd_legado_pre_d33(path)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "ALTER TABLE ofertas_descubiertas "
            "ADD COLUMN ubicacion_nombre TEXT DEFAULT ''"
        )
        conn.execute(
            "UPDATE ofertas_descubiertas SET ubicacion_nombre = 'Bogotá, Colombia' "
            "WHERE id = 'OFE-0001'"
        )
        conn.commit()
    finally:
        conn.close()

    change_path(path)
    try:
        init_db()
        columnas = {
            fila[1]
            for fila in sqlite3.connect(str(path)).execute(
                "PRAGMA table_info(ofertas_descubiertas)"
            ).fetchall()
        }
        assert "ubicacion" in columnas
        assert "ubicacion_nombre" not in columnas
        filas = leer_tabla("ofertas_descubiertas")
        assert len(filas) == 1
        assert filas[0]["ubicacion"] == "Bogotá, Colombia"
    finally:
        reset_path()


def test_migracion_d33_idempotente(tmp_path: Path) -> None:
    import sqlite3

    from shared.persistence import change_path, init_db, leer_tabla, reset_path

    path = tmp_path / "legado_d33_idem.db"
    _crear_bd_legado_pre_d33(path)

    change_path(path)
    try:
        init_db()
        init_db()
        assert len(leer_tabla("ofertas_descubiertas")) == 1
        assert len(leer_tabla("ubicaciones")) == 1
        assert len(leer_tabla("eventos")) == 1
        conn = sqlite3.connect(str(path))
        try:
            columnas_ubicaciones = {
                fila[1]
                for fila in conn.execute(
                    "PRAGMA table_info(ubicaciones)"
                ).fetchall()
            }
        finally:
            conn.close()
        assert "modalidad" not in columnas_ubicaciones
    finally:
        reset_path()


def test_eventos_id_oferta_sobrevive_doble_init_db(tmp_path: Path) -> None:
    """Regression guard: `_migrate_limpieza_d31` no longer drops
    `eventos.id_oferta` (D33 supersedes D31 D-1 on that column), so a value
    written after the first init survives subsequent inits."""
    from shared.persistence import (
        change_path,
        escribir_evento,
        init_db,
        leer_tabla,
        reset_path,
    )

    path = tmp_path / "legado_d33_evento.db"
    _crear_bd_legado_pre_d33(path)

    change_path(path)
    try:
        init_db()
        escribir_evento(
            {
                "id_corrida": "COR-0002",
                "tipo": "suceso",
                "codigo": "oferta_preparada",
                "id_oferta": "OFE-0009",
            }
        )
        init_db()
        evs = leer_tabla("eventos", {"codigo": "oferta_preparada"})
        assert len(evs) == 1
        assert evs[0]["id_oferta"] == "OFE-0009"
    finally:
        reset_path()


def test_escribir_evento_normaliza_id_oferta_vacio(temp_db_file: Path) -> None:
    from shared.persistence import escribir_evento, leer_tabla

    evento_id = escribir_evento(
        {
            "id_corrida": "COR-0003",
            "tipo": "suceso",
            "codigo": "oferta_preparada",
            "id_oferta": "",
        }
    )
    filas = leer_tabla("eventos", {"evento_id": evento_id})
    assert len(filas) == 1
    assert filas[0]["id_oferta"] == "N/A"


def test_actualizar_corrida_acepta_sin_pendientes(temp_db_file: Path) -> None:
    from shared.models import EstadoCorrida
    from shared.persistence import actualizar_corrida, registrar_corrida

    registrar_corrida(
        {
            "id_corrida": "COR-0004",
            "fecha_inicio": "2026-08-21 08:00:00",
            "estado": "en_ejecucion",
        }
    )
    assert actualizar_corrida(
        "COR-0004",
        {
            "estado": EstadoCorrida.SIN_PENDIENTES,
            "motivo_terminacion": "sin_pendientes",
        },
    )
    from shared.persistence import leer_tabla

    corridas = leer_tabla("corridas", {"id_corrida": "COR-0004"})
    assert corridas[0]["estado"] == EstadoCorrida.SIN_PENDIENTES.value


def test_leer_candidatas_descubiertas_orden_fifo(temp_db_file: Path) -> None:
    escribir_fila(
        "ofertas_descubiertas",
        {"id": "OFE-0002", "enlace": "e2", "fecha_descubrimiento": "2026-08-21 09:00:00"},
    )
    escribir_fila(
        "ofertas_descubiertas",
        {"id": "OFE-0001", "enlace": "e1", "fecha_descubrimiento": "2026-08-21 09:00:00"},
    )
    escribir_fila(
        "ofertas_descubiertas",
        {"id": "OFE-0003", "enlace": "e3", "fecha_descubrimiento": "2026-08-20 10:00:00"},
    )
    filas = leer_candidatas_descubiertas()
    # Empate de fecha entre OFE-0001 y OFE-0002: el número secuencial rompe
    # el empate (D53, orden numérico del identificador).
    assert [f["id"] for f in filas] == ["OFE-0003", "OFE-0001", "OFE-0002"]


def test_leer_candidatas_descubiertas_orden_fifo_miles_d53(temp_db_file: Path) -> None:
    # La comparación lexicográfica invierte el orden a partir de 10.000
    # ('OFE-9999' > 'OFE-10000' como texto): la clave numérica (D53) mantiene
    # el ciclo de vida real con la misma fecha de descubrimiento.
    for id_oferta in ("OFE-10001", "OFE-0002", "OFE-9998", "OFE-10000"):
        escribir_fila(
            "ofertas_descubiertas",
            {
                "id": id_oferta,
                "enlace": f"https://example.com/{id_oferta}",
                "fecha_descubrimiento": "2026-08-21 09:00:00",
            },
        )
    filas = leer_candidatas_descubiertas()
    assert [f["id"] for f in filas] == [
        "OFE-0002",
        "OFE-9998",
        "OFE-10000",
        "OFE-10001",
    ]


def test_leer_ultima_corrida_cerrada_desempate_numerico_d53(temp_db_file: Path) -> None:
    # Con la misma fecha_fin, la corrida con número MAYOR es la más reciente
    # (se lanzó después): el desempate numérico (D53) la elige, el texto
    # ('COR-9998' > 'COR-10000') habría elegido la antigua.
    from shared.persistence import (
        actualizar_corrida,
        leer_ultima_corrida_cerrada,
        registrar_corrida,
    )

    for corrida_id, fecha_inicio in (
        ("COR-9998", "2026-08-21 08:00:00"),
        ("COR-10000", "2026-08-21 08:10:00"),
    ):
        registrar_corrida(
            {
                "id_corrida": corrida_id,
                "fecha_inicio": fecha_inicio,
                "estado": "en_ejecucion",
            }
        )
        actualizar_corrida(
            corrida_id,
            {
                "estado": "completada",
                "fecha_fin": "2026-08-21 08:30:00",
                "motivo_terminacion": "corrida_completada",
            },
        )
    fila = leer_ultima_corrida_cerrada("2026-08-21 00:00:00")
    assert fila is not None
    assert fila["id_corrida"] == "COR-10000"


def test_leer_candidatas_descubiertas_excluye_otros_estados(
    temp_db_file: Path,
) -> None:
    for oferta_id, estado in (
        ("OFE-A", "descubierta"),
        ("OFE-B", "preparada"),
        ("OFE-C", "duplicada"),
    ):
        escribir_fila(
            "ofertas_descubiertas",
            {
                "id": oferta_id,
                "enlace": f"e-{oferta_id}",
                "fecha_descubrimiento": "2026-08-21 09:00:00",
                "estado": estado,
            },
        )
    filas = leer_candidatas_descubiertas()
    assert [f["id"] for f in filas] == ["OFE-A"]


def test_leer_corridas_abiertas_ignora_cerradas(temp_db_file: Path) -> None:
    import sqlite3

    from shared.persistence import (
        actualizar_corrida,
        leer_corridas_abiertas,
        registrar_corrida,
    )

    for id_corrida, inicio in (
        ("COR-AB1", "2026-10-24 10:00:00"),
        ("COR-AB2", "2026-10-24 10:05:00"),
        ("COR-CE1", "2026-10-24 09:00:00"),
        ("COR-NU1", "2026-10-24 10:10:00"),
        ("COR-NA1", "2026-10-24 10:15:00"),
    ):
        registrar_corrida(
            {"id_corrida": id_corrida, "fecha_inicio": inicio, "estado": "en_ejecucion"}
        )
    actualizar_corrida(
        "COR-CE1",
        {"estado": "completada", "fecha_fin": "2026-10-24 09:30:00"},
    )
    # Las otras dos ramas del predicado (D31) no se pueden escribir con la API
    # validada: se fijan con SQL directo sobre la base temporal.
    con = sqlite3.connect(str(temp_db_file))
    con.execute("UPDATE corridas SET fecha_fin = NULL WHERE id_corrida = 'COR-NU1'")
    con.execute("UPDATE corridas SET fecha_fin = 'N/A' WHERE id_corrida = 'COR-NA1'")
    con.commit()
    con.close()

    abiertas = leer_corridas_abiertas()

    assert [c["id_corrida"] for c in abiertas] == [
        "COR-AB1",
        "COR-AB2",
        "COR-NU1",
        "COR-NA1",
    ]


def test_leer_corrida_puntual(temp_db_file: Path) -> None:
    from shared.persistence import leer_corrida, registrar_corrida

    registrar_corrida(
        {
            "id_corrida": "COR-P1",
            "fecha_inicio": "2026-10-24 10:00:00",
            "estado": "en_ejecucion",
        }
    )

    fila = leer_corrida("COR-P1")
    assert fila is not None and fila["estado"] == "en_ejecucion"
    assert leer_corrida("COR-NO-EXISTE") is None


def test_leer_eventos_de_corridas_acota_por_ids(temp_db_file: Path) -> None:
    from shared.persistence import escribir_evento, leer_eventos_de_corridas

    for id_corrida in ("COR-E1", "COR-E2"):
        escribir_evento(
            {
                "id_corrida": id_corrida,
                "tipo": "suceso",
                "codigo": "ingreso_exitoso",
                "evidencia": "sesion=LK-1",
                "marca_temporal": "2026-10-24 10:00:00",
            }
        )

    solo_e1 = leer_eventos_de_corridas(["COR-E1"])
    assert [e["id_corrida"] for e in solo_e1] == ["COR-E1"]
    assert leer_eventos_de_corridas([]) == []
    assert len(leer_eventos_de_corridas(["COR-E1", "COR-E1"])) == 1


def test_resumen_ofertas_por_estado(temp_db_file: Path) -> None:
    from shared.persistence import escribir_fila, resumen_ofertas_por_estado

    for numero, estado in enumerate(("descubierta", "descubierta", "preparada"), 1):
        escribir_fila(
            "ofertas_descubiertas",
            {
                "id": f"OFE-{numero:04d}",
                "enlace": f"https://example.test/{numero}",
                "estado": estado,
                "id_externo": f"ext-{numero}",
            },
        )

    assert resumen_ofertas_por_estado() == {"descubierta": 2, "preparada": 1}


def test_ids_de_corrida_con_codigos(temp_db_file: Path) -> None:
    from shared.persistence import (
        escribir_evento,
        ids_de_corrida_con_codigos,
        registrar_corrida,
    )

    for id_corrida in ("COR-S1", "COR-S2"):
        registrar_corrida(
            {
                "id_corrida": id_corrida,
                "fecha_inicio": "2026-10-24 10:00:00",
                "estado": "en_ejecucion",
            }
        )
    escribir_evento(
        {
            "id_corrida": "COR-S1",
            "tipo": "suceso",
            "codigo": "tic_modulo_iniciado",
            "evidencia": "modulo=descubrimiento",
            "marca_temporal": "2026-10-24 10:00:00",
        }
    )
    escribir_evento(
        {
            "id_corrida": "COR-S2",
            "tipo": "suceso",
            "codigo": "modulo_ejecutado",
            "evidencia": "modulo=descubrimiento",
            "marca_temporal": "2026-10-24 10:00:00",
        }
    )

    assert ids_de_corrida_con_codigos(["tic_modulo_iniciado"]) == {"COR-S1"}
    assert ids_de_corrida_con_codigos([]) == set()


def test_inicializar_si_ausente_d42(temp_db_file: Path) -> None:
    from shared.persistence import inicializar_si_ausente

    assert inicializar_si_ausente() is False  # esquema ya presente: no-op
    import sqlite3

    from shared.persistence import reset_path

    con = sqlite3.connect(str(temp_db_file))
    con.execute("DROP TABLE secuencia_ids")
    for t in ("empresas", "ubicaciones", "ofertas_descubiertas", "corridas",
              "eventos", "sesiones", "bloqueo"):
        con.execute(f"DROP TABLE IF EXISTS {t}")
    con.commit()
    con.close()
    # sin tablas -> inicializa; segunda vez -> no-op
    assert inicializar_si_ausente() is True
    assert inicializar_si_ausente() is False
    reset_path()
