"""Internal: write operations (ids, offers, runs, events, lock)."""

import sqlite3
import uuid
from datetime import datetime
from typing import Any, cast

from loguru import logger

from shared.config import load
from shared.errors import PersistenceError
from shared.models import Corrida, EventoAlmacen
from shared.utilidades import acotar_evidencia, ahora

from ._conexion import _connection, _serialize
from ._esquemas import PREFIXES


def _generar_id_en(conn: sqlite3.Connection, tabla: str) -> str:
    """Generates the next sequential id for `tabla` on an existing connection.

    Reads the `RETURNING` value of the single upsert statement, so no extra
    SELECT is needed. The caller decides when to commit.
    """
    prefijo = PREFIXES.get(tabla)
    if prefijo is None:
        disponibles = list(PREFIXES.keys())
        raise ValueError(f"Unknown table: {tabla}. Available prefixes: {disponibles}")
    fila = conn.execute(
        "INSERT INTO secuencia_ids (tabla_nombre, prefijo, ultimo_numero) VALUES (?, ?, 1) "
        "ON CONFLICT(tabla_nombre) DO UPDATE SET ultimo_numero = ultimo_numero + 1 "
        "RETURNING ultimo_numero",
        (tabla, prefijo),
    ).fetchone()
    assert fila is not None
    return f"{prefijo}-{int(fila[0]):04d}"



def generar_id(tabla: str) -> str:
    conn = _connection()
    try:
        resultado = _generar_id_en(conn, tabla)
        conn.commit()
        return resultado
    finally:
        conn.close()



def escribir_fila(tabla: str, datos: dict[str, Any]) -> str:
    d = _serialize(datos)
    if "id" not in d or not d["id"]:
        d["id"] = generar_id(tabla)
    marca = ahora()
    if not d.get("fecha_creacion"):
        d["fecha_creacion"] = marca
    d["fecha_ultima_edicion"] = marca

    columnas = [k for k in d.keys()]
    placeholders = [":" + k for k in d.keys()]
    sql = f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({', '.join(placeholders)})"
    conn = _connection()
    try:
        conn.execute(sql, d)
        conn.commit()
        return cast(str, d["id"])
    finally:
        conn.close()



def actualizar_fila(tabla: str, id_valor: str, datos: dict[str, Any]) -> bool:
    d = _serialize(datos)
    d["fecha_ultima_edicion"] = ahora()
    if "id" in d:
        del d["id"]
    asignaciones = ", ".join(f"{k} = :{k}" for k in d.keys())
    d["_id_valor"] = id_valor
    sql = f"UPDATE {tabla} SET {asignaciones} WHERE id = :_id_valor"
    conn = _connection()
    try:
        cursor = conn.execute(sql, d)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()



def umbral_obsolescencia_minutos(config: dict[str, Any] | None = None) -> int:
    cfg = config if config is not None else load()
    valor = (cfg.get("concurrencia") or {}).get(
        "umbral_obsolescencia_minutos", 120
    )
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 120



def adquirir_bloqueo(
    id_corrida: str,
    marca_temporal: str,
    forzar: bool = False,
    umbral_minutos: int | None = None,
) -> bool:
    conn = _connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        fila = conn.execute(
            "SELECT * FROM bloqueo ORDER BY marca_temporal DESC LIMIT 1"
        ).fetchone()
        if fila is None:
            try:
                conn.execute(
                    "INSERT INTO bloqueo (id_corrida, marca_temporal) VALUES (?, ?)",
                    (id_corrida, marca_temporal),
                )
            except sqlite3.IntegrityError:
                conn.rollback()
                return False
            conn.commit()
            return True
        if forzar:
            cursor = conn.execute(
                "UPDATE bloqueo SET id_corrida = ?, marca_temporal = ? WHERE id_corrida = ?",
                (id_corrida, marca_temporal, fila["id_corrida"]),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                return False
            conn.commit()
            return True
        actual = datetime.strptime(fila["marca_temporal"], "%Y-%m-%d %H:%M:%S")
        if umbral_minutos is None:
            umbral_minutos = umbral_obsolescencia_minutos()
        vigente = (
            datetime.now() - actual
        ).total_seconds() / 60 < umbral_minutos if umbral_minutos > 0 else True
        if vigente:
            conn.rollback()
            return False
        cursor = conn.execute(
            "UPDATE bloqueo SET id_corrida = ?, marca_temporal = ? WHERE id_corrida = ?",
            (id_corrida, marca_temporal, fila["id_corrida"]),
        )
        if cursor.rowcount == 0:
            conn.rollback()
            return False
        conn.commit()
        return True
    finally:
        conn.close()



def liberar_bloqueo(id_corrida: str) -> None:
    """Releases the concurrency lock for a run (Finalizar node)."""
    conn = _connection()
    try:
        conn.execute("DELETE FROM bloqueo WHERE id_corrida = ?", (id_corrida,))
        conn.commit()
    finally:
        conn.close()



def sondear_escritura() -> None:
    """VAL-03 probe: INSERT with immediate rollback on the bloqueo table."""
    try:
        conn = _connection()
    except sqlite3.Error as exc:
        raise PersistenceError("01", f"Connection failed: {exc}") from exc
    try:
        conn.execute(
            "INSERT INTO bloqueo (id_corrida, marca_temporal) VALUES (?, ?)",
            (f"PROBE-{uuid.uuid4().hex[:8]}", ahora()),
        )
        conn.rollback()
    except sqlite3.Error as exc:
        raise PersistenceError("01", f"Write probe failed: {exc}") from exc
    finally:
        conn.close()



def registrar_corrida(datos: dict[str, Any]) -> None:
    """Registers a run row in `corridas`, idempotent per id_corrida.

    Validates the row against `Corrida` (Pydantic) before writing so schema
    drift surfaces at runtime instead of producing silently corrupted rows.
    """
    Corrida.model_validate(datos)
    d = _serialize(datos)
    conn = _connection()
    try:
        conn.execute(
            "INSERT INTO corridas (id_corrida, fecha_inicio, estado) "
            "VALUES (:id_corrida, :fecha_inicio, :estado) "
            "ON CONFLICT (id_corrida) DO NOTHING",
            {
                "id_corrida": d["id_corrida"],
                "fecha_inicio": d.get("fecha_inicio") or ahora(),
                "estado": d.get("estado") or "",
            },
        )
        conn.commit()
    finally:
        conn.close()



def actualizar_corrida(id_corrida: str, campos: dict[str, Any]) -> bool:
    """Updates the `corridas` row of a run; returns whether a row matched.

    Closes a run (Finalizar Proceso node): persists the final state and the
    closure metrics (`fecha_fin`, `motivo_terminacion`, `total_ofertas`,
    `total_errores`, `total_sucesos`, `fuentes_procesadas`). Follows the
    `actualizar_fila` pattern; `corridas` is keyed by `id_corrida` instead of `id`.
    Validates the closure fields against `Corrida` (Pydantic) before writing
    so schema drift surfaces at runtime (P4-13; deferred from D23).
    """
    Corrida(id_corrida=id_corrida, **campos)
    d = _serialize(campos)
    asignaciones = ", ".join(f"{k} = :{k}" for k in d.keys())
    d["_run_id"] = id_corrida
    sql = f"UPDATE corridas SET {asignaciones} WHERE id_corrida = :_run_id"
    conn = _connection()
    try:
        cursor = conn.execute(sql, d)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()



def _upsert_ofertas_en(
    conn: sqlite3.Connection, filas: list[dict[str, Any]]
) -> tuple[list[str], int]:
    """Upserts offers on an existing connection, dedup by `id_externo`.

    Existing rows only refresh `fecha_ultima_verificacion`; new rows get a
    generated `id` on the same connection. Row-level failures are logged and
    counted without aborting the remaining rows; the caller commits.
    Returns (ids_registradas, fallidas). No-empty-field rule (D31): empty
    values in `descripcion_original`/`fecha_publicacion`/`observaciones`/
    `empresa_id`/`ubicacion_id`/`ubicacion`/`modalidad`/`empresa`/
    `resultado_evaluacion_inicial` are persisted as 'N/A'.
    """
    registradas: list[str] = []
    fallidas = 0
    if not filas:
        return registradas, fallidas
    preparadas = [_serialize(dict(f)) for f in filas]
    for d in preparadas:
        for campo in (
            "descripcion_original",
            "fecha_publicacion",
            "observaciones",
            "empresa_id",
            "ubicacion_id",
            "ubicacion",
            "modalidad",
            "empresa",
            "resultado_evaluacion_inicial",
        ):
            if not d.get(campo):
                d[campo] = "N/A"
    id_externos = [d.get("id_externo") for d in preparadas if d.get("id_externo")]
    ids_por_id_externo: dict[str, str] = {}
    if id_externos:
        marcas = ",".join("?" for _ in id_externos)
        for fila in conn.execute(
            "SELECT id_externo, id FROM ofertas_descubiertas "
            f"WHERE id_externo IN ({marcas})",
            id_externos,
        ).fetchall():
            ids_por_id_externo[str(fila["id_externo"])] = str(fila["id"])
    marca = ahora()
    for d in preparadas:
        try:
            id_externo = d.get("id_externo")
            if id_externo and id_externo in ids_por_id_externo:
                conn.execute(
                    "UPDATE ofertas_descubiertas "
                    "SET fecha_ultima_verificacion = ? WHERE id = ?",
                    (marca, ids_por_id_externo[id_externo]),
                )
                registradas.append(ids_por_id_externo[id_externo])
                continue
            if not d.get("id"):
                d["id"] = _generar_id_en(conn, "ofertas_descubiertas")
            if not d.get("fecha_creacion"):
                d["fecha_creacion"] = marca
            d["fecha_ultima_edicion"] = marca
            columnas = list(d.keys())
            placeholders = [":" + k for k in d.keys()]
            conn.execute(
                "INSERT INTO ofertas_descubiertas "
                f"({', '.join(columnas)}) VALUES ({', '.join(placeholders)})",
                d,
            )
            registradas.append(cast(str, d["id"]))
            if id_externo:
                ids_por_id_externo[id_externo] = cast(str, d["id"])
        except Exception as exc:
            logger.error(
                f"Oferta no registrada en lote | "
                f"id_externo={d.get('id_externo')} | "
                f"id_corrida={d.get('id_corrida')} | {exc}"
            )
            fallidas += 1
    return registradas, fallidas



def upsert_lote_ofertas(filas: list[dict[str, Any]]) -> tuple[int, int]:
    """Inserts or updates a batch of offers in a single connection.

    Deduplicates by `id_externo` like `upsert_oferta` but in one
    transaction. Returns (registradas, fallidas); row-level failures never
    abort the remaining rows. Connection failures raise.
    """
    if not filas:
        return 0, 0
    conn = _connection()
    try:
        ids, fallidas = _upsert_ofertas_en(conn, filas)
        conn.commit()
        return len(ids), fallidas
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()



def upsert_oferta(oferta: dict[str, Any]) -> str:
    """Inserts or updates a single offer by `id_externo` (public API).

    Thin wrapper over the batch upsert; returns the offer `id` (str).
    A row rejected at row level raises `PersistenceError` instead of the
    misleading `IndexError` of an empty result list.
    """
    conn = _connection()
    try:
        ids, _ = _upsert_ofertas_en(conn, [oferta])
        if not ids:
            raise PersistenceError(
                "09",
                f"Oferta no registrada (fila inválida) | "
                f"id_externo={oferta.get('id_externo')}",
            )
        conn.commit()
        return ids[0]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()



def escribir_evento(datos: dict[str, Any]) -> str:
    """Registers an event/success row in `eventos`; returns its evento_id.

    Validates the row against `EventoAlmacen` (Pydantic) before writing so
    schema drift surfaces at runtime instead of producing corrupted rows.
    """
    EventoAlmacen.model_validate(datos)
    d = _serialize(datos)
    for campo in ("fuente_id", "id_sesion", "evidencia", "id_oferta"):
        if not d.get(campo):
            d[campo] = "N/A"
    if d.get("indice_set") is None:
        d["indice_set"] = "N/A"
    evento_id = str(d.get("evento_id") or generar_id("eventos"))
    d["evento_id"] = evento_id
    if not d.get("marca_temporal"):
        d["marca_temporal"] = ahora()
    columnas = ", ".join(d.keys())
    placeholders = ", ".join(f":{k}" for k in d.keys())
    conn = _connection()
    try:
        conn.execute(f"INSERT INTO eventos ({columnas}) VALUES ({placeholders})", d)
        conn.commit()
        return evento_id
    finally:
        conn.close()



def registrar_evento(
    id_corrida: str,
    tipo: str,
    codigo: str,
    evidencia: str,
    *,
    fuente_id: str = "N/A",
    id_oferta: str = "N/A",
    id_sesion: str | None = None,
    indice_set: int | None = None,
    acotar: bool = True,
) -> None:
    """D42: single event emitter for every node (replaces the 8 wrappers).

    Non-aborting (`escribir_evento_seguro`), evidence bounded by default
    (D42 fixes the M1-inicio sites that skipped `acotar_evidencia`), and
    optional `id_sesion`/`indice_set` for the search-side success events.
    """
    datos: dict[str, Any] = {
        "id_corrida": id_corrida,
        "fuente_id": fuente_id or "N/A",
        "tipo": tipo,
        "codigo": codigo,
        "evidencia": acotar_evidencia(evidencia) if acotar else evidencia,
        "id_oferta": id_oferta,
        "marca_temporal": ahora(),
    }
    if id_sesion is not None:
        datos["id_sesion"] = id_sesion
    if indice_set is not None:
        datos["indice_set"] = indice_set
    escribir_evento_seguro(datos, contexto_log=id_corrida)



def escribir_evento_seguro(datos: dict[str, Any], contexto_log: str = "") -> None:
    """Writes an event best-effort: never aborts, falls back to Loguru.

    Single non-aborting wrapper replacing the per-node try/except copies
    (inicio, captura, control_fuentes, registro, finalizar). The node
    builds the full row dict; validation and persistence stay in
    `escribir_evento`.
    """
    try:
        escribir_evento(datos)
    except Exception as exc:
        run = contexto_log or str(datos.get("id_corrida", ""))
        codigo = str(datos.get("codigo", ""))
        logger.error(f"Evento no persistible | run={run} | codigo={codigo} | {exc}")
