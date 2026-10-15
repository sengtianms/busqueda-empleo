"""Internal: schema initialization and idempotent migrations."""

import sqlite3

from ._conexion import _connection
from ._esquemas import (
    _ADICIONES_EVALUACION,
    _ADICIONES_PREPARACION,
    _COLUMNAS_ENRIQUECIMIENTO_RETIRADAS_D40,
    _COLUMNAS_FINALIZACION_CORRIDAS,
    _INDICES,
    _TABLAS_ESQUEMA,
    ESQUEMAS,
    MAPA_COLUMNAS_ESPANOL,
)


def inicializar_si_ausente() -> bool:
    """D42: crea el esquema solo cuando la base no tiene tablas aún.

    Chequeo barato por catálogo: las corridas normales (esquema presente)
    NO ejecutan migraciones en cada arranque; `init_db()` se invoca únicamente
    ante ausencia de `secuencia_ids`. Devuelve True si inicializó.
    """
    conn = _connection()
    try:
        presente = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name = 'secuencia_ids'"
        ).fetchone()
    finally:
        conn.close()
    if presente is not None:
        return False
    init_db()
    return True



def init_db() -> None:
    conn = _connection()
    try:
        _migrate_ofertas_descubiertas(conn)
        tablas = ("secuencia_ids", "empresas", "ubicaciones",
                  "ofertas_descubiertas", "corridas", "eventos",
                  "sesiones", "bloqueo")
        for nombre_tabla in tablas:
            conn.execute(ESQUEMAS[nombre_tabla])
        _migrate_ubicacion_rename(conn)
        _migrar_espanol_total(conn)
        _migrate_ofertas(conn)
        _migrate_ofertas_timestamp_ultima_verificacion(conn)
        _migrate_ofertas_empresa_nombre(conn)
        _migrate_corridas_finalizacion(conn)
        _migrate_sesiones_id(conn)
        _migrate_limpieza_d31(conn)
        _migrate_preparacion_d33(conn)
        _migrate_revertir_enriquecimiento_d40(conn)
        _migrate_normalizacion_nombres_d41(conn)
        _migrate_evaluacion_d48(conn)
        for sentencia in _INDICES:
            conn.execute(sentencia)
        conn.commit()
    finally:
        conn.close()



def _migrate_ofertas_descubiertas(conn: sqlite3.Connection) -> None:
    """D32 migration: rename the `ofertas` table to `ofertas_descubiertas`.

    Renames the physical table when a DB created before decision D32 still
    holds `ofertas`; SQLite keeps the indexes under their same names and the
    `secuencia_ids` row is updated so the next generated id continues the
    `OFE` sequence without collisions. Runs before the schema creation loop
    so the new `CREATE TABLE IF NOT EXISTS` never creates an empty duplicate.
    Idempotent: no-op when the rename is already applied.
    """
    tablas = {
        fila["name"]
        for fila in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "ofertas" in tablas and "ofertas_descubiertas" not in tablas:
        conn.execute("ALTER TABLE ofertas RENAME TO ofertas_descubiertas")
    if "secuencia_ids" in tablas:
        conn.execute(
            "UPDATE secuencia_ids SET tabla_nombre = 'ofertas_descubiertas' "
            "WHERE tabla_nombre = 'ofertas'"
        )



def _migrar_espanol_total(conn: sqlite3.Connection) -> None:
    """D7/D8 migration: full Spanish schema (columns + `ofertas_descubiertas.estado` CHECK).

    Rebuilds each tracked table from the Spanish ESQUEMAS when its current
    schema still uses English column names, mapping old columns to their
    Spanish equivalents (MAPA_COLUMNAS_ESPANOL) so no data is lost and the
    `estado` CHECK constraint is recreated with Spanish values. Runs before
    the legacy migrations so they operate on the Spanish schema. Idempotent:
    a table is rebuilt only when it lacks some expected Spanish column.
    """
    for nombre_tabla in _TABLAS_ESQUEMA:
        filas = conn.execute(
            f"PRAGMA table_info({nombre_tabla})"
        ).fetchall()
        columnas_actuales = {fila["name"] for fila in filas}
        if not columnas_actuales:
            conn.execute(ESQUEMAS[nombre_tabla])
            continue
        conn.execute(
            ESQUEMAS[nombre_tabla].replace(
                f"TABLE IF NOT EXISTS {nombre_tabla}",
                f"TABLE {nombre_tabla}_nueva",
            )
        )
        esperadas = {
            fila["name"]
            for fila in conn.execute(
                f"PRAGMA table_info({nombre_tabla}_nueva)"
            ).fetchall()
        }
        if esperadas.issubset(columnas_actuales):
            conn.execute(f"DROP TABLE {nombre_tabla}_nueva")
            continue
        seleccion = []
        destinos = []
        for columna in columnas_actuales:
            if columna in MAPA_COLUMNAS_ESPANOL[nombre_tabla]:
                nuevo = MAPA_COLUMNAS_ESPANOL[nombre_tabla][columna]
                if nuevo in esperadas:
                    seleccion.append(f"{columna} AS {nuevo}")
                    destinos.append(nuevo)
            elif columna in esperadas:
                if nombre_tabla == "ofertas_descubiertas" and columna == "estado":
                    seleccion.append(
                        "CASE estado WHEN 'discovered' THEN 'descubierta' "
                        "WHEN 'prepared' THEN 'preparada' "
                        "WHEN 'evaluated' THEN 'evaluada' "
                        "WHEN 'accepted' THEN 'aceptada' "
                        "WHEN 'discarded' THEN 'descartada' "
                        "WHEN 'processed' THEN 'procesada' "
                        "WHEN 'finalized' THEN 'finalizada' "
                        "ELSE estado END AS estado"
                    )
                    destinos.append("estado")
                else:
                    seleccion.append(columna)
                    destinos.append(columna)
        conn.execute(
            f"INSERT INTO {nombre_tabla}_nueva ({', '.join(destinos)}) "
            f"SELECT {', '.join(seleccion)} FROM {nombre_tabla}"
        )
        conn.execute(f"DROP TABLE {nombre_tabla}")
        conn.execute(
            f"ALTER TABLE {nombre_tabla}_nueva RENAME TO {nombre_tabla}"
        )
    conn.execute(
        "UPDATE sesiones SET id = id_sesion WHERE id IS NULL OR id = ''"
    )



def _migrate_sesiones_id(conn: sqlite3.Connection) -> None:
    """Sesiones migration: align the table with `escribir_fila` generic inserts.

    `escribir_fila` inserts an `id` (and `fecha_creacion`/`fecha_ultima_edicion`) column
    by default, but the legacy `sesiones` table was declared with
    `id_sesion TEXT PRIMARY KEY` and no `id` column, so every session audit
    insert failed with "table sesiones has no column named id". The table is
    rebuilt with `id TEXT PRIMARY KEY` carrying the id_sesion value.
    Migration is idempotent: it only runs when the `id` column is missing.
    """
    columnas = {
        fila["name"]
        for fila in conn.execute("PRAGMA table_info(sesiones)").fetchall()
    }
    if "id" in columnas:
        return
    conn.execute("ALTER TABLE sesiones RENAME TO sesiones_legacy")
    conn.execute(ESQUEMAS["sesiones"])
    comunes = [
        nombre
        for nombre in columnas
        if nombre in {
            fila["name"]
            for fila in conn.execute("PRAGMA table_info(sesiones)").fetchall()
        }
    ]
    lista = ", ".join(comunes)
    conn.execute(
        f"INSERT INTO sesiones ({lista}) SELECT {lista} FROM sesiones_legacy"
    )
    conn.execute(
        "UPDATE sesiones SET id = id_sesion WHERE id IS NULL OR id = ''"
    )
    conn.execute("DROP TABLE sesiones_legacy")



def _migrate_ofertas(conn: sqlite3.Connection) -> None:
    """C2 migration: "lo crudo se conserva crudo".

    SQLite cannot drop a NOT NULL constraint in place, so the
    `ofertas_descubiertas` table is rebuilt without NOT NULL on `titulo` and
    `descripcion_original`, allowing capturing raw listings that lack those
    fields. The columns of traceability (`id_corrida`, `id_sesion`,
    `indice_set`, `id_externo`) are included in the new schema. Migration is
    idempotent: it only runs when the current schema still declares
    `titulo NOT NULL`.
    """
    columnas = {
        fila["name"]: fila["notnull"]
        for fila in conn.execute(
            "PRAGMA table_info(ofertas_descubiertas)"
        ).fetchall()
    }
    if "titulo" in columnas and columnas["titulo"] == 0:
        return
    conn.execute(
        ESQUEMAS["ofertas_descubiertas"].replace(
            "TABLE IF NOT EXISTS ofertas_descubiertas",
            "TABLE ofertas_descubiertas_nueva",
        )
    )
    nuevas = {
        fila["name"]
        for fila in conn.execute(
            "PRAGMA table_info(ofertas_descubiertas_nueva)"
        ).fetchall()
    }
    comunes = [
        fila["name"]
        for fila in conn.execute(
            "PRAGMA table_info(ofertas_descubiertas)"
        ).fetchall()
        if fila["name"] in nuevas
    ]
    lista = ", ".join(comunes)
    conn.execute(
        f"INSERT INTO ofertas_descubiertas_nueva ({lista}) SELECT {lista} "
        "FROM ofertas_descubiertas"
    )
    conn.execute("DROP TABLE ofertas_descubiertas")
    conn.execute(
        "ALTER TABLE ofertas_descubiertas_nueva "
        "RENAME TO ofertas_descubiertas"
    )



def _migrate_ofertas_empresa_nombre(conn: sqlite3.Connection) -> None:
    """D29 migration: drop `empresa_nombre` from `ofertas_descubiertas`.

    D4 (2026-08-09) added raw-string company/location columns; D29
    (2026-08-17) removes them from the model: the adapter no longer
    extracts company/location from the cards (only the publication date),
    so raw strings are not persisted. SQLite >= 3.35 supports in-place
    `ALTER TABLE ... DROP COLUMN`; each column is dropped only if present
    (idempotent). `ubicacion_nombre` is NOT dropped here: decision D33
    re-added it for Module 2 and `_migrate_ubicacion_rename` later renames
    it to `ubicacion`, so dropping it first would silently destroy data.
    """
    columnas = {
        fila["name"]
        for fila in conn.execute(
            "PRAGMA table_info(ofertas_descubiertas)"
        ).fetchall()
    }
    if "empresa_nombre" in columnas:
        conn.execute(
            "ALTER TABLE ofertas_descubiertas DROP COLUMN empresa_nombre"
        )



def _migrate_ofertas_timestamp_ultima_verificacion(conn: sqlite3.Connection) -> None:
    """4.4 migration: ensure `ofertas_descubiertas.fecha_ultima_verificacion` exists.

    The capture upsert refreshes this column for re-seen listings. The column
    is added on first init if absent; subsequent inits are no-ops.
    """
    columnas = {
        fila["name"]
        for fila in conn.execute(
            "PRAGMA table_info(ofertas_descubiertas)"
        ).fetchall()
    }
    if "fecha_ultima_verificacion" not in columnas:
        conn.execute(
            "ALTER TABLE ofertas_descubiertas ADD COLUMN "
            "fecha_ultima_verificacion TEXT DEFAULT ''"
        )



def _migrate_limpieza_d31(conn: sqlite3.Connection) -> None:
    """D31 migration: schema cleanup + no-empty-field rule (N/A).

    (1) Drops the `fuentes` table and its `secuencia_ids` row (sources are
    config-driven; the catalog was never populated).
    (2) Drops `ofertas_descubiertas.identificador_origen` (dead duplicate of
    `id_externo`). `eventos.id_oferta` is NO LONGER dropped here: decision
    D33 re-adds it for Module 2 per-offer traceability, superseding D31 D-1
    on that column.
    (3) Backfills the no-empty-field rule (decision D31): empty/NULL values
    in the non-nullable-by-semantics columns become 'N/A' so no field stays
    empty (the backfill updates are per-column and safe no-ops when no row
    matches; the DROP COLUMN steps are guarded by a column-presence check).
    `ofertas_descubiertas.fecha_ultima_verificacion` is exempted (only
    refreshed on re-visits; D31 point 4 keeps its current behavior).
    Idempotent: every destructive step only runs when its target is present.
    """
    conn.execute("DROP TABLE IF EXISTS fuentes")
    conn.execute("DELETE FROM secuencia_ids WHERE tabla_nombre = 'fuentes'")
    actuales_ofertas = {
        fila["name"]
        for fila in conn.execute(
            "PRAGMA table_info(ofertas_descubiertas)"
        ).fetchall()
    }
    if "identificador_origen" in actuales_ofertas:
        conn.execute(
            "ALTER TABLE ofertas_descubiertas DROP COLUMN identificador_origen"
        )
    for columna in (
        "descripcion_original",
        "fecha_publicacion",
        "observaciones",
        "empresa_id",
        "ubicacion_id",
    ):
        conn.execute(
            f"UPDATE ofertas_descubiertas SET {columna} = 'N/A' "
            f"WHERE {columna} IS NULL OR {columna} = ''"
        )
    for columna in ("fuente_id", "id_sesion", "indice_set", "evidencia"):
        conn.execute(
            f"UPDATE eventos SET {columna} = 'N/A' "
            f"WHERE {columna} IS NULL OR {columna} = ''"
        )



def _migrate_preparacion_d33(conn: sqlite3.Connection) -> None:
    """D33 migration: Module 2 (Preparation) consolidated schema dependencies.

    (1) Adds the preparation columns when absent (on legacy DBs the
    `_migrar_espanol_total` rebuild usually applies them from ESQUEMAS; this
    guarded pass is the explicit safety net): `ofertas_descubiertas`.
    `id_duplicidad`/`modalidad` ('N/A'), `corridas`.
    `total_preparadas`/`total_duplicadas` (0) and `eventos`.`id_oferta`
    ('N/A'; re-added, superseding D31 D-1). The raw-location column is NOT
    added here under its historical name: `_migrate_ubicacion_rename`
    already renamed it to `ubicacion` earlier in the chain.
    (2) Drops `ubicaciones.modalidad`: `ubicaciones` is restructured to the
    `(ciudad, region, pais)` tuple (components default 'N/A'); the extra
    column does not trigger the rebuild path, so the drop must be explicit.
    The `estado` CHECK with 'duplicada' comes from the updated ESQUEMAS via
    the same rebuild. Idempotent: every step only runs when its target is
    present.
    """
    columnas_por_tabla = {
        tabla: {
            fila["name"]
            for fila in conn.execute(f"PRAGMA table_info({tabla})").fetchall()
        }
        for tabla in ("ofertas_descubiertas", "corridas", "eventos")
    }
    for tabla, definicion in _ADICIONES_PREPARACION:
        nombre_columna = definicion.split(" ")[0]
        if nombre_columna not in columnas_por_tabla[tabla]:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {definicion}")
    columnas_ubicaciones = {
        fila["name"]
        for fila in conn.execute("PRAGMA table_info(ubicaciones)").fetchall()
    }
    if "modalidad" in columnas_ubicaciones:
        conn.execute("ALTER TABLE ubicaciones DROP COLUMN modalidad")



def _migrate_revertir_enriquecimiento_d40(conn: sqlite3.Connection) -> None:
    """D40 migration: drop the enrichment columns from `empresas`.

    Decision D40 supersedes D39: bulk guest-profile enrichment proved to be
    a run bottleneck (~96% of a full run) for informational-only value, so
    the catalog returns to its identity shape (id/nombre/nombre_normalizado/
    perfil_linkedin plus the audit dates). Requires SQLite >= 3.35
    (`ALTER TABLE ... DROP COLUMN`); each drop only runs while the column
    exists. Idempotent: fresh DBs already create the minimal shape from
    ESQUEMAS and skip every step.
    """
    columnas = {
        fila["name"]
        for fila in conn.execute("PRAGMA table_info(empresas)").fetchall()
    }
    if not columnas:
        return
    for columna in _COLUMNAS_ENRIQUECIMIENTO_RETIRADAS_D40:
        if columna in columnas:
            conn.execute(f"ALTER TABLE empresas DROP COLUMN {columna}")



def _migrate_normalizacion_nombres_d41(conn: sqlite3.Connection) -> None:
    """D41 migration: recompute `empresas.nombre_normalizado`.

    Decision D41 changes the company-name key rule to
    `normalizar_nombre_empresa` (lowercase + single spaces, keeping every
    character) — rows normalized under the strict D33 rule (accents and
    punctuation stripped) would never match the new keys computed by the
    Preparation upsert, silently splitting companies. Recomputes every row
    from `nombre`. Idempotent: recomputation is stable under the new rule.
    """
    from shared.utilidades import normalizar_nombre_empresa

    filas = conn.execute(
        "SELECT id, nombre, nombre_normalizado FROM empresas"
    ).fetchall()
    for id_oferta, nombre, clave_actual in filas:
        nueva = normalizar_nombre_empresa(nombre)
        if nueva != clave_actual:
            conn.execute(
                "UPDATE empresas SET nombre_normalizado = ? WHERE id = ?",
                (nueva, id_oferta),
            )



def _migrate_evaluacion_d48(conn: sqlite3.Connection) -> None:
    """D48 migration (Previo Fase 6): Module 3 evaluation groundwork.

    (1) Adds the evaluation columns when absent: `ofertas_descubiertas`.
    `resultado_evaluacion_inicial` ('N/A' = pending) and `corridas`.
    `total_aprobadas`/`total_descartadas` (0).
    (2) Extends the `ofertas_descubiertas.estado` CHECK with
    'aceptada_ei'/'descartada_ei': when the live CHECK predates them, the
    table is rebuilt from ESQUEMAS preserving every common column (same
    copy pattern as `_migrate_ofertas`; the new states are a superset so
    existing rows stay valid). Idempotent: every step only runs when its
    target is absent.
    """
    columnas_por_tabla = {
        tabla: {
            fila["name"]
            for fila in conn.execute(f"PRAGMA table_info({tabla})").fetchall()
        }
        for tabla in ("ofertas_descubiertas", "corridas")
    }
    for tabla, definicion in _ADICIONES_EVALUACION:
        nombre_columna = definicion.split(" ")[0]
        if nombre_columna not in columnas_por_tabla[tabla]:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {definicion}")
    fila = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type = 'table' AND name = 'ofertas_descubiertas'"
    ).fetchone()
    if fila is None or "aceptada_ei" in str(fila["sql"]):
        return
    conn.execute(
        ESQUEMAS["ofertas_descubiertas"].replace(
            "TABLE IF NOT EXISTS ofertas_descubiertas",
            "TABLE ofertas_descubiertas_nueva",
        )
    )
    nuevas = {
        fila["name"]
        for fila in conn.execute(
            "PRAGMA table_info(ofertas_descubiertas_nueva)"
        ).fetchall()
    }
    comunes = [
        fila["name"]
        for fila in conn.execute(
            "PRAGMA table_info(ofertas_descubiertas)"
        ).fetchall()
        if fila["name"] in nuevas
    ]
    lista = ", ".join(comunes)
    conn.execute(
        f"INSERT INTO ofertas_descubiertas_nueva ({lista}) SELECT {lista} "
        "FROM ofertas_descubiertas"
    )
    conn.execute("DROP TABLE ofertas_descubiertas")
    conn.execute(
        "ALTER TABLE ofertas_descubiertas_nueva RENAME TO ofertas_descubiertas"
    )


def _migrate_ubicacion_rename(conn: sqlite3.Connection) -> None:
    """Renames `ofertas_descubiertas.ubicacion_nombre` to `ubicacion`.

    User-requested naming simplification: the raw location text captured by
    Module 1 lives in a column named simply `ubicacion` (D7/D8 catalog style,
    no accents). Runs right after the schema loop and BEFORE
    `_migrar_espanol_total`, so a legacy table carrying populated location
    text gets its column renamed first and the Spanish rebuild then copies
    it as `ubicacion` instead of dropping it as an unknown column. Fresh
    DBs already create `ubicacion` from ESQUEMAS and skip the rename.
    Idempotent: only runs when the old column exists and the new doesn't.
    """
    columnas = {
        fila["name"]
        for fila in conn.execute(
            "PRAGMA table_info(ofertas_descubiertas)"
        ).fetchall()
    }
    if (
        columnas
        and "ubicacion" not in columnas
        and "ubicacion_nombre" in columnas
    ):
        conn.execute(
            "ALTER TABLE ofertas_descubiertas "
            "RENAME COLUMN ubicacion_nombre TO ubicacion"
        )



def _migrate_corridas_finalizacion(conn: sqlite3.Connection) -> None:
    """4.5 migration: add closure metrics columns to `corridas`.

    The Finalizar Proceso node persists closure metrics (fecha_fin,
    motivo_terminacion, total_ofertas, total_errores, total_sucesos,
    fuentes_procesadas) via `actualizar_corrida`. Columns are added one by
    one on first init if absent; subsequent inits are no-ops (idempotent,
    tolerates partially migrated legacy DBs).
    """
    columnas = {
        fila["name"]
        for fila in conn.execute("PRAGMA table_info(corridas)").fetchall()
    }
    for definicion in _COLUMNAS_FINALIZACION_CORRIDAS:
        nombre_columna = definicion.split(" ")[0]
        if nombre_columna not in columnas:
            conn.execute(f"ALTER TABLE corridas ADD COLUMN {definicion}")
