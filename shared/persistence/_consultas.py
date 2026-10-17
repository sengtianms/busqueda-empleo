"""Internal: read-only query helpers."""

from typing import Any

from ._conexion import _connection, _deserialize


def leer_tabla(
    tabla: str, filtros: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    conn = _connection()
    try:
        if filtros:
            condiciones = " AND ".join(f"{k} = :{k}" for k in filtros.keys())
            sql = f"SELECT * FROM {tabla} WHERE {condiciones}"
            cursor = conn.execute(sql, dict(filtros))
        else:
            cursor = conn.execute(f"SELECT * FROM {tabla}")
        results: list[dict[str, Any]] = []
        for f in cursor.fetchall():
            r = _deserialize(f)
            if r is not None:
                results.append(r)
        return results
    finally:
        conn.close()



def leer_candidatas_descubiertas() -> list[dict[str, Any]]:
    """Reads offers in `descubierta` in FIFO order (Módulo 2 INICIO, VAL-06).

    FIFO selection per ficha M2 RN-07: oldest discovery date first, `id ASC`
    as tiebreaker. Lives in the persistence layer so functional modules never
    write SQL directly (architecture rule).
    """
    conn = _connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM ofertas_descubiertas WHERE estado = 'descubierta' "
            "ORDER BY fecha_descubrimiento ASC, id ASC"
        )
        results: list[dict[str, Any]] = []
        for f in cursor.fetchall():
            r = _deserialize(f)
            if r is not None:
                results.append(r)
        return results
    finally:
        conn.close()



def leer_candidatas_preparadas() -> list[dict[str, Any]]:
    """Reads offers in `preparada` in FIFO order (Módulo 3 INICIO, VAL-06).

    FIFO selection per ficha M3 RN-07: oldest discovery date first, `id ASC`
    as tiebreaker. Lives in the persistence layer so functional modules never
    write SQL directly (architecture rule).
    """
    conn = _connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM ofertas_descubiertas WHERE estado = 'preparada' "
            "ORDER BY fecha_descubrimiento ASC, id ASC"
        )
        results: list[dict[str, Any]] = []
        for f in cursor.fetchall():
            r = _deserialize(f)
            if r is not None:
                results.append(r)
        return results
    finally:
        conn.close()



def contar_filas(tabla: str, filtros: dict[str, Any] | None = None) -> int:
    """Counts rows of a table; optional equality filters."""
    conn = _connection()
    try:
        if filtros:
            condiciones = " AND ".join(f"{k} = :{k}" for k in filtros.keys())
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM {tabla} WHERE {condiciones}", dict(filtros)
            )
        else:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {tabla}")
        fila = cursor.fetchone()
        return int(fila[0]) if fila is not None else 0
    finally:
        conn.close()



def contar_distintos(
    tabla: str, columna: str, filtros: dict[str, Any] | None = None
) -> int:
    """Counts distinct non-empty values of a column (equality filters).

    Empty values are NULL, '' and 'N/A' (no-empty-field rule, decision D31:
    'N/A' is the placeholder for not-applicable fields). A filter whose
    value is a list/tuple matches any of its members (`IN`) — used by the
    M2 closure to count the UNION of success codes as distinct offers.
    """
    conn = _connection()
    try:
        condiciones = (
            f"{columna} IS NOT NULL AND {columna} != '' "
            f"AND {columna} != 'N/A'"
        )
        params: dict[str, Any] = {}
        if filtros:
            clausulas: list[str] = []
            for i, (clave, valor) in enumerate(filtros.items()):
                if isinstance(valor, (list, tuple)):
                    marcadores = ", ".join(f":{clave}_{j}" for j in range(len(valor)))
                    clausulas.append(f"{clave} IN ({marcadores})")
                    for j, elemento in enumerate(valor):
                        params[f"{clave}_{j}"] = elemento
                else:
                    clausulas.append(f"{clave} = :{clave}")
                    params[clave] = valor
            condiciones += " AND " + " AND ".join(clausulas)
        cursor = conn.execute(
            f"SELECT COUNT(DISTINCT {columna}) FROM {tabla} WHERE {condiciones}",
            params,
        )
        fila = cursor.fetchone()
        return int(fila[0]) if fila is not None else 0
    finally:
        conn.close()



def buscar_por_id(tabla: str, id_valor: str) -> dict[str, Any] | None:
    conn = _connection()
    try:
        cursor = conn.execute(f"SELECT * FROM {tabla} WHERE id = ?", (id_valor,))
        return _deserialize(cursor.fetchone())
    finally:
        conn.close()



def consultar_bloqueo() -> dict[str, Any] | None:
    conn = _connection()
    try:
        fila = conn.execute(
            "SELECT * FROM bloqueo ORDER BY marca_temporal DESC LIMIT 1"
        ).fetchone()
        return dict(fila) if fila is not None else None
    finally:
        conn.close()



def leer_ultima_corrida_cerrada(
    desde: str, excluir_ids: list[str] | None = None
) -> dict[str, Any] | None:
    """Returns the most recently closed run started at or after `desde`.

    Transversal orchestrator helper (ficha D34): derives each module's result
    from the database instead of a return contract — the global lock
    guarantees only the just-executed module can close a run inside the
    window. "Closed" means `fecha_fin` populated (never ''/NULL/'N/A' per the
    D31 no-empty-field rule). `excluir_ids` removes already-attributed runs
    (the scheduled run itself and previously derived modules) so attribution
    stays one-to-one; ordering is by `fecha_fin DESC LIMIT 1`.
    """
    exclusiones = list(excluir_ids or [])
    placeholders = ", ".join(f":excl_{i}" for i in range(len(exclusiones))) or ":ninguno"
    parametros: dict[str, Any] = {"desde": desde, "ninguno": ""}
    for i, valor in enumerate(exclusiones):
        parametros[f"excl_{i}"] = valor
    sql = (
        "SELECT * FROM corridas "
        "WHERE fecha_fin NOT IN ('', 'N/A') AND fecha_inicio >= :desde "
        f"AND id_corrida NOT IN ({placeholders}) "
        "ORDER BY fecha_fin DESC, id_corrida DESC LIMIT 1"
    )
    conn = _connection()
    try:
        fila = conn.execute(sql, parametros).fetchone()
        return dict(fila) if fila is not None else None
    finally:
        conn.close()
