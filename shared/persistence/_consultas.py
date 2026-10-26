"""Internal: read-only query helpers."""

from collections.abc import Iterable
from typing import Any

from ._conexion import _connection, _deserialize


def _orden_secuencial_sql(columna: str) -> str:
    """SQL numeric key of an official id (`PREFIJO-NNNN`, D53): the number
    after the dash cast to integer. Ordering by the raw text flips once the
    sequence passes 9.999 (`'OFE-9999' > 'OFE-10000'` as text, older first
    is the only correct order) — numbers order by true age with zero data
    migration. Unparsable (defensive) values sort as 0. Valid only for
    single-dash `PREFIJO-NNNN` ids (the current generator), the same
    assumption `numero_secuencial_id` makes."""
    return f"CAST(substr({columna}, instr({columna}, '-') + 1) AS INTEGER)"


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



def leer_corridas_abiertas() -> list[dict[str, Any]]:
    """Corridas sin cierre (`fecha_fin` ausente, vacia o 'N/A', D31).

    Lectura acotada para los visores de operacion: el guardian solo actua
    sobre filas abiertas, asi que no necesita recorrer la historia. Mismo
    predicado que `_abiertas` en `scripts/estado_corrida.py`: si cambia uno,
    cambiar el otro.
    """
    conn = _connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM corridas "
            "WHERE COALESCE(fecha_fin, '') IN ('', 'N/A') "
            "ORDER BY fecha_inicio ASC"
        )
        results: list[dict[str, Any]] = []
        for f in cursor.fetchall():
            r = _deserialize(f)
            if r is not None:
                results.append(r)
        return results
    finally:
        conn.close()



def leer_corrida(id_corrida: str) -> dict[str, Any] | None:
    """Una corrida por su id (lectura puntual, sin recorrer la tabla).

    `buscar_por_id` asume una columna `id`; `corridas` usa `id_corrida`, de
    ahi esta lectura propia.
    """
    conn = _connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM corridas WHERE id_corrida = ?", (id_corrida,)
        )
        return _deserialize(cursor.fetchone())
    finally:
        conn.close()



def leer_eventos_de_corridas(ids_corrida: Iterable[str]) -> list[dict[str, Any]]:
    """Eventos de las corridas indicadas, en una sola consulta acotada.

    Sin ids no consulta (devuelve vacio). Conserva el orden natural de la
    tabla; los llamadores ordenan por marca temporal cuando lo necesitan.
    """
    ids = list(dict.fromkeys(str(i) for i in ids_corrida if str(i)))
    if not ids:
        return []
    marcadores = ", ".join("?" for _ in ids)
    conn = _connection()
    try:
        cursor = conn.execute(
            f"SELECT * FROM eventos WHERE id_corrida IN ({marcadores})", ids
        )
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

    FIFO selection per ficha M2 RN-07: oldest discovery date first, smallest
    sequential id as tiebreaker (numeric per D53, see `_orden_secuencial_sql`).
    Lives in the persistence layer so functional modules never write SQL
    directly (architecture rule).
    """
    conn = _connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM ofertas_descubiertas WHERE estado = 'descubierta' "
            f"ORDER BY fecha_descubrimiento ASC, {_orden_secuencial_sql('id')} ASC"
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

    FIFO selection per ficha M3 RN-07: oldest discovery date first, smallest
    sequential id as tiebreaker (numeric per D53, see `_orden_secuencial_sql`).
    Lives in the persistence layer so functional modules never write SQL
    directly (architecture rule).
    """
    conn = _connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM ofertas_descubiertas WHERE estado = 'preparada' "
            f"ORDER BY fecha_descubrimiento ASC, {_orden_secuencial_sql('id')} ASC"
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
    stays one-to-one; ordering is by `fecha_fin DESC` with the largest
    sequential `id_corrida` breaking equal timestamps (numeric per D53 — the
    highest sequence launched last).
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
        f"ORDER BY fecha_fin DESC, {_orden_secuencial_sql('id_corrida')} DESC LIMIT 1"
    )
    conn = _connection()
    try:
        fila = conn.execute(sql, parametros).fetchone()
        return dict(fila) if fila is not None else None
    finally:
        conn.close()


CODIGOS_NARRACION: tuple[str, ...] = (
    "tic_modulo_iniciado",
    "tic_set_iniciado",
    "tic_captura_pagina",
)
"""Lote 2: códigos de narración en vivo.

Events purely informative (progress tick); they do not alter flow metrics:
`Finalizar` subtracts them from `total_sucesos` via `contar_narracion`.
"""


def contar_narracion(id_corrida: str) -> int:
    """Counts the run's narration events (Lote 2); excluded from metrics.

    Defensive: only `tipo='suceso'` counts — a narration code reused as an
    error would otherwise be subtracted twice (once via `total_errores`,
    once here).
    """
    conn = _connection()
    try:
        marcadores = ", ".join("?" for _ in CODIGOS_NARRACION)
        fila = conn.execute(
            f"SELECT COUNT(*) FROM eventos "
            f"WHERE id_corrida = ? AND tipo = 'suceso' "
            f"AND codigo IN ({marcadores})",
            (id_corrida, *CODIGOS_NARRACION),
        ).fetchone()
        return int(fila[0]) if fila is not None else 0
    finally:
        conn.close()



def resumen_ofertas_por_estado() -> dict[str, int]:
    """Conteo de ofertas por estado (una fila por estado, sin listar ofertas)."""
    conn = _connection()
    try:
        cursor = conn.execute(
            "SELECT estado, COUNT(*) FROM ofertas_descubiertas GROUP BY estado"
        )
        return {
            str(fila[0]) if fila[0] is not None else "": int(fila[1])
            for fila in cursor.fetchall()
        }
    finally:
        conn.close()



def ids_de_corrida_con_codigos(codigos: Iterable[str]) -> set[str]:
    """Ids de corrida con al menos uno de esos codigos de evento.

    Usa el indice por corrida (EXISTS por fila de `corridas`): el costo
    depende del numero de corridas y de sus eventos, no de recorrer la
    tabla de eventos completa. Sin codigos devuelve vacio.
    """
    limpios = tuple(dict.fromkeys(str(c) for c in codigos if str(c)))
    if not limpios:
        return set()
    marcadores = ", ".join("?" for _ in limpios)
    conn = _connection()
    try:
        cursor = conn.execute(
            "SELECT c.id_corrida FROM corridas c "
            "WHERE EXISTS ("
            "SELECT 1 FROM eventos e "
            "WHERE e.id_corrida = c.id_corrida "
            f"AND e.codigo IN ({marcadores})"
            ")",
            limpios,
        )
        return {str(fila[0]) for fila in cursor.fetchall()}
    finally:
        conn.close()
