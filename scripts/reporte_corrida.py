"""Reporte funcional de una corrida programada (D42; solo lectura).

Uso:
    python scripts/reporte_corrida.py [--corrida COR-XXXX] [--db data/job_search.db]

Sin `--corrida` toma la ultima corrida programada registrada. Imprime:
etapas y duraciones, ofertas por estado, errores con evidencia,
duplicadas con su original, catálogos nuevos, cobertura de enlaces,
modalidad y verificacion de la regla de no vacios.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.persistence import change_path, leer_tabla, reset_path
from shared.utilidades import FORMATO_TIMESTAMP

EXENTAS_NO_VACIOS = frozenset(
    {
        "id_externo",
        "fecha_ultima_verificacion",
        # D71: `id_lista` puede quedar sin valor SOLO en las ofertas previas
        # al cambio (instruccion expresa del usuario: no atribuirlas; sus
        # apuntes de duplicado llevan origen desconocido). Las nuevas
        # siempre la traen, asi que cualquier NULL futuro "nuevo" sigue
        # siendo anomalia detectable por el contador de legado del informe.
        "id_lista",
    }
)


def _duracion(inicio: str, fin: str) -> str:
    if not inicio or not fin:
        return "—"
    delta = (
        datetime.strptime(fin, FORMATO_TIMESTAMP)
        - datetime.strptime(inicio, FORMATO_TIMESTAMP)
    ).total_seconds()
    return f"{int(delta // 60)}m {int(delta % 60)}s"


def _id_programada() -> str | None:
    eventos = sorted(
        leer_tabla("eventos", {"codigo": "corrida_programada"}),
        key=lambda e: str(e.get("marca_temporal") or ""),
    )
    if eventos:
        return str(eventos[-1]["id_corrida"])
    corridas = sorted(
        leer_tabla("corridas"), key=lambda c: str(c.get("fecha_inicio") or "")
    )
    return str(corridas[-1]["id_corrida"]) if corridas else None


def generar_reporte(id_corrida: str | None = None) -> list[str]:
    """Construye las lineas del reporte para la corrida indicada o la ultima."""
    lineas: list[str] = []
    corridas = leer_tabla("corridas")
    objetivo = id_corrida or _id_programada()
    if objetivo is None:
        return ["No hay corridas registradas en la base de datos."]

    programada = next((c for c in corridas if str(c["id_corrida"]) == objetivo), None)
    if programada is None:
        return [f"No existe la corrida {objetivo}."]
    inicio = str(programada.get("fecha_inicio") or "")
    fin = str(programada.get("fecha_fin") or "")
    relacionadas = {
        str(c["id_corrida"])
        for c in corridas
        if c is not programada
        and inicio <= str(c.get("fecha_inicio") or "") <= (fin or "9999")
    }
    relacionadas.add(objetivo)

    lineas.append(f"== CORRIDA {objetivo} ==")
    lineas.append(
        f"  estado={programada.get('estado')} | motivo={programada.get('motivo_terminacion')}"
        f" | duracion={_duracion(inicio, fin)}"
        f" | sucesos={programada.get('total_sucesos')} | errores={programada.get('total_errores')}"
    )
    for c in sorted(
        (c for c in corridas if str(c["id_corrida"]) in relacionadas - {objetivo}),
        key=lambda c: str(c.get("fecha_inicio") or ""),
    ):
        lineas.append(
            f"   · {c['id_corrida']} | {c.get('motivo_terminacion')}"
            f" | {_duracion(str(c.get('fecha_inicio') or ''), str(c.get('fecha_fin') or ''))}"
            f" | prep={c.get('total_preparadas')} dup={c.get('total_duplicadas')}"
        )

    ofertas = [
        o
        for o in leer_tabla("ofertas_descubiertas")
        if str(o.get("id_corrida")) in relacionadas
    ]
    por_estado: dict[str, int] = {}
    for oferta in ofertas:
        clave = str(oferta.get("estado"))
        por_estado[clave] = por_estado.get(clave, 0) + 1
    lineas.append(f"== OFERTAS == {por_estado} | total={len(ofertas)}")

    errores = [
        e
        for e in leer_tabla("eventos")
        if str(e.get("tipo")) == "error" and str(e.get("id_corrida")) in relacionadas
    ]
    lineas.append(f"== ERRORES ({len(errores)}) ==")
    for error in errores:
        lineas.append(f"   · [{error['codigo']}] {error.get('evidencia')}")

    duplicadas = [o for o in ofertas if str(o.get("estado")) == "duplicada"]
    lineas.append(f"== DUPLICADAS ({len(duplicadas)}) ==")
    for dup in duplicadas:
        original = next(
            (o for o in ofertas if str(o["id"]) == str(dup.get("id_duplicidad"))),
            None,
        )
        titulo = str(original.get("titulo"))[:60] if original else "(original fuera del conjunto)"
        lineas.append(f"   · {dup['id']} -> {dup.get('id_duplicidad')} | {titulo}")

    empresas = leer_tabla("empresas")
    ubicaciones = leer_tabla("ubicaciones")
    sin_empresa = sum(1 for o in ofertas if str(o.get("empresa_id")) in ("N/A", ""))
    sin_ubicacion = sum(1 for o in ofertas if str(o.get("ubicacion_id")) in ("N/A", ""))
    empresa_sin_dato = sum(1 for o in ofertas if str(o.get("empresa")) == "N/R")
    modalidad: dict[str, int] = {}
    for oferta in ofertas:
        clave = str(oferta.get("modalidad"))
        modalidad[clave] = modalidad.get(clave, 0) + 1
    lineas.append("== CATALOGOS Y CALIDAD ==")
    lineas.append(
        f"  empresas (catalogo)={len(empresas)} | ubicaciones (catalogo)={len(ubicaciones)}"
        f" | ofertas sin link empresa={sin_empresa} / ubicacion={sin_ubicacion}"
        f" | columna empresa 'N/R'={empresa_sin_dato}"
    )
    lineas.append(f"  modalidad: {modalidad}")

    violaciones: list[str] = []
    for tabla in ("ofertas_descubiertas", "eventos"):  # alcance D31
        columnas = [fila["name"] for fila in _columnas(tabla)]
        for columna in columnas:
            if columna in EXENTAS_NO_VACIOS:
                continue
            vacias = _vacias(tabla, columna)
            if vacias:
                violaciones.append(f"{tabla}.{columna}={vacias}")
    lineas.append(
        "== REGLA NO VACIOS == cumple"
        if not violaciones
        else f"== REGLA NO VACIOS == VIOLACIONES: {violaciones}"
    )
    return lineas


def _columnas(tabla: str) -> list[Any]:
    from shared.persistence import _connection

    conn = _connection()
    try:
        return conn.execute(f"PRAGMA table_info({tabla})").fetchall()
    finally:
        conn.close()


def _vacias(tabla: str, columna: str) -> int:
    from shared.persistence import _connection

    conn = _connection()
    try:
        return int(
            conn.execute(
                f'SELECT COUNT(*) FROM "{tabla}" '
                f'WHERE "{columna}" IS NULL OR "{columna}" = \'\''
            ).fetchone()[0]
        )
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corrida", help="ID de la corrida programada (ej. COR-0001)")
    parser.add_argument("--db", help="Ruta alternativa a la base de datos")
    argumentos = parser.parse_args(argv)
    if argumentos.db:
        change_path(argumentos.db)
    try:
        lineas = generar_reporte(argumentos.corrida)
    finally:
        if argumentos.db:
            reset_path()
    print("\n".join(lineas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
