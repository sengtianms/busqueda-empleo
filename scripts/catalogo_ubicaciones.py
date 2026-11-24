"""Mantenimiento del catálogo de ubicaciones por el operador (D83).

Uso:
    python scripts/catalogo_ubicaciones.py listar [texto] [--todo]
    python scripts/catalogo_ubicaciones.py agregar --municipio X --departamento Y
    python scripts/catalogo_ubicaciones.py corregir UBI-XXXX --municipio X
    python scripts/catalogo_ubicaciones.py fusionar UBI-XXXX UBI-YYYY

Cuatro acciones, sin consultas y sin escribir en la base viva salvo una orden
explícita. Todas las acciones de escritura comprueban la silla de concurrencia
y admiten ``--db`` para ensayar sobre una copia. El diario queda en
``logs/catalogo_ubicaciones.log``; no se crean eventos de corrida porque esos
pertenecen a una tanda y alterarían sus métricas. Los ensayos con ``--db``
dejan sus líneas en un diario separado, ``catalogo_ubicaciones_ensayo.log``.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.modelo_catalogo import (  # noqa: E402
    DEPARTAMENTO,
    MUNICIPIO,
    canonico_municipio,
    clave_normalizada,
    diagnosticar,
    es_estructural,
    tipo_de_fila,
)
from shared.config import load  # noqa: E402
from shared.errors import PersistenceError  # noqa: E402
from shared.persistence import (  # noqa: E402
    _db_path,
    actualizar_fila,
    buscar_por_id,
    change_path,
    consultar_bloqueo,
    contar_filas,
    contar_ofertas_por_ubicacion,
    crear_o_reutilizar_ubicacion,
    fusionar_ubicacion,
    leer_tabla,
    reset_path,
    umbral_obsolescencia_minutos,
)
from shared.utilidades import FORMATO_TIMESTAMP, normalizar_texto  # noqa: E402

_TOPE_LISTADO = 50
_SENTINELA = "N/A"


def _diario(linea: str) -> None:
    config = load()
    base = str(config.get("logging", {}).get("logs_path", "logs"))
    por_defecto = Path(str(config.get("persistence", {}).get("db_file", "data/job_search.db")))
    ensayo = _db_path().resolve() != por_defecto.resolve()
    nombre = "catalogo_ubicaciones_ensayo.log" if ensayo else "catalogo_ubicaciones.log"
    ruta = Path(base) / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime(FORMATO_TIMESTAMP)
    prefijo = "ENSAYO | " if ensayo else ""
    with ruta.open("a", encoding="utf-8") as archivo:
        archivo.write(f"{marca} | {prefijo}{linea}\n")


def _silla_vigente(config: dict[str, Any]) -> bool:
    """Espejo del prevuelo: una silla vigente bloquea cualquier escritura."""
    try:
        fila = consultar_bloqueo()
    except Exception:
        return True
    if fila is None:
        return False
    try:
        marca = datetime.strptime(str(fila["marca_temporal"]), FORMATO_TIMESTAMP)
    except (KeyError, TypeError, ValueError):
        return True
    minutos = (datetime.now() - marca).total_seconds() / 60
    return minutos < umbral_obsolescencia_minutos(config)


def _base_disponible() -> tuple[bool, str]:
    ruta = _db_path()
    if not ruta.exists():
        return False, f"no existe la base de datos: {ruta}"
    try:
        contar_filas("ubicaciones")
    except sqlite3.OperationalError as error:
        return False, f"la base no tiene catálogo de ubicaciones: {error}"
    return True, ""


def _resumen(filas: list[dict[str, Any]]) -> list[str]:
    diag = diagnosticar(filas)
    lineas = [
        f"Catálogo: {diag.total} filas | "
        f"municipios={diag.por_tipo[MUNICIPIO]} "
        f"solo departamento={diag.por_tipo[DEPARTAMENTO]} "
        f"solo país={diag.filas_pais} no aplica={diag.no_aplica}",
        f"Origen: operador={diag.por_origen.get('operador', 0)} "
        f"sistema={diag.por_origen.get('sistema', 0)}",
        f"Variantes de escritura detectadas: {len(diag.variantes)}",
    ]
    for variante in diag.variantes:
        lineas.append(f"  variante: {', '.join(variante.ids)} | {variante.descripciones}")
    return lineas


def _descripcion(fila: dict[str, Any]) -> str:
    return (
        f"{fila.get('municipio')}/{fila.get('departamento')}/"
        f"{fila.get('pais')} ({fila.get('origen')})"
    )


def listar(argumentos: argparse.Namespace) -> list[str]:
    filas = leer_tabla("ubicaciones")
    usos = contar_ofertas_por_ubicacion()
    lineas = _resumen(filas)
    texto = (argumentos.texto or "").strip().lower()
    departamento = (argumentos.departamento or "").strip().lower()
    filtradas: list[dict[str, Any]] = []
    for fila in filas:
        if texto and not any(
            texto in str(fila.get(campo) or "").lower()
            for campo in ("id", "municipio", "departamento", "pais")
        ):
            continue
        if departamento and departamento not in str(fila.get("departamento") or "").lower():
            continue
        if argumentos.origen and str(fila.get("origen")) != argumentos.origen:
            continue
        if argumentos.tipo and tipo_de_fila(fila) != argumentos.tipo:
            continue
        filtradas.append(fila)
    filtradas.sort(key=lambda fila: str(fila.get("id", "")))
    total = len(filtradas)
    if not argumentos.todo:
        filtradas = filtradas[:_TOPE_LISTADO]
    lineas.append(f"Filas que cumplen el filtro: {total}")
    lineas.append(
        f"{'ID':<10} {'TIPO':<13} {'MUNICIPIO':<24} {'DEPARTAMENTO':<24} "
        f"{'PAIS':<12} {'ORIGEN':<10} {'OFERTAS':>7}"
    )
    for fila in filtradas:
        lineas.append(
            f"{str(fila.get('id', '')):<10} {tipo_de_fila(fila):<13} "
            f"{str(fila.get('municipio', '')):<24.24} "
            f"{str(fila.get('departamento', '')):<24.24} "
            f"{str(fila.get('pais', '')):<12.12} "
            f"{str(fila.get('origen', '')):<10.10} "
            f"{usos.get(str(fila.get('id', '')), 0):>7}"
        )
    if total > len(filtradas):
        lineas.append(f"(se muestran {len(filtradas)} de {total}; use --todo para ver todas)")
    return lineas


def agregar(argumentos: argparse.Namespace) -> list[str]:
    municipio = normalizar_texto(argumentos.municipio or "") or _SENTINELA
    departamento = normalizar_texto(argumentos.departamento or "") or _SENTINELA
    if municipio == _SENTINELA and departamento == _SENTINELA:
        raise ValueError("no se indicó municipio ni departamento")
    if municipio != _SENTINELA and departamento == _SENTINELA:
        raise ValueError("un municipio necesita departamento; use --departamento")
    if municipio != _SENTINELA and canonico_municipio(municipio) != municipio:
        canonico = canonico_municipio(municipio)
        raise ValueError(f"«{municipio}» se resuelve como «{canonico}»; no se agregó la fila")
    if _silla_vigente(load()):
        raise RuntimeError("hay una tanda activa; espere a que termine")

    filas = leer_tabla("ubicaciones")
    for fila in filas:
        if (
            str(fila.get("municipio")) == municipio
            and str(fila.get("departamento")) == departamento
            and str(fila.get("pais")) == "colombia"
        ):
            raise ValueError(f"la combinación ya existe en {fila.get('id')}; no se agregó")
    nueva = {
        "municipio": municipio,
        "departamento": departamento,
        "pais": "colombia",
    }
    clave = clave_normalizada(nueva)
    existentes = {clave_normalizada(fila): str(fila.get("id")) for fila in filas}
    if clave in existentes:
        raise ValueError(
            f"existe una variante de esta ubicación en {existentes[clave]}; no se agregó"
        )

    id_nuevo = crear_o_reutilizar_ubicacion({**nueva, "origen": "operador"})
    _diario(f"AGREGAR | {id_nuevo} | {_descripcion({**nueva, 'origen': 'operador'})}")
    return [
        f"Fila agregada: {id_nuevo} | {_descripcion({**nueva, 'origen': 'operador'})}",
        "Ofertas enlazadas: 0",
    ]


def corregir(argumentos: argparse.Namespace) -> list[str]:
    fila = buscar_por_id("ubicaciones", argumentos.id)
    if fila is None:
        raise ValueError(f"no existe la fila {argumentos.id}")
    if es_estructural(fila):
        raise ValueError("las filas 'no aplica' y 'solo país' son de solo lectura")
    tipo = tipo_de_fila(fila)
    if tipo == MUNICIPIO:
        permitidos: tuple[str, ...] = ("municipio", "departamento")
    else:
        permitidos = ("departamento",)
        if getattr(argumentos, "municipio", None):
            raise ValueError("una fila de solo departamento no puede cambiar de tipo")
    cambios: dict[str, Any] = {}
    for campo in permitidos:
        valor = getattr(argumentos, campo, None)
        if valor is not None and str(valor).strip():
            cambios[campo] = normalizar_texto(str(valor))
    if not cambios:
        raise ValueError("no se indicó ningún cambio")
    if (
        "municipio" in cambios
        and canonico_municipio(cambios["municipio"]) != cambios["municipio"]
    ):
        raise ValueError(f"«{cambios['municipio']}» se resuelve como otra fila; no se corrigió")
    if _silla_vigente(load()):
        raise RuntimeError("hay una tanda activa; espere a que termine")

    resultante = {**fila, **cambios}
    filas = [otra for otra in leer_tabla("ubicaciones") if str(otra.get("id")) != argumentos.id]
    for otra in filas:
        if (
            str(otra.get("municipio")) == resultante["municipio"]
            and str(otra.get("departamento")) == resultante["departamento"]
            and str(otra.get("pais")) == resultante["pais"]
        ):
            raise ValueError(f"la combinación ya existe en {otra.get('id')}; use fusionar")
        if clave_normalizada(otra) == clave_normalizada(resultante):
            raise ValueError(f"existe una variante en {otra.get('id')}; use fusionar")

    actualizar_fila("ubicaciones", argumentos.id, cambios)
    usos = contar_ofertas_por_ubicacion().get(argumentos.id, 0)
    _diario(
        f"CORREGIR | {argumentos.id} | {_descripcion(fila)} -> "
        f"{_descripcion(resultante)} | ofertas={usos}"
    )
    return [
        f"Fila corregida: {argumentos.id}",
        f"Antes: {_descripcion(fila)}",
        f"Después: {_descripcion(resultante)}",
        f"Ofertas que conservan el enlace: {usos} (texto original intacto)",
    ]


def fusionar(argumentos: argparse.Namespace) -> list[str]:
    id_origen = argumentos.origen
    id_destino = argumentos.destino
    origen = buscar_por_id("ubicaciones", id_origen)
    destino = buscar_por_id("ubicaciones", id_destino)
    if origen is None or destino is None:
        raise ValueError("ambos identificadores deben existir")
    if id_origen == id_destino:
        raise ValueError("origen y destino son la misma fila")
    if es_estructural(origen) or es_estructural(destino):
        raise ValueError("las filas 'no aplica' y 'solo país' no se fusionan")
    if tipo_de_fila(origen) != tipo_de_fila(destino):
        raise ValueError("solo se fusionan filas del mismo tipo")
    if str(origen.get("pais")) != str(destino.get("pais")):
        raise ValueError("solo se fusionan filas del mismo país")
    if _silla_vigente(load()):
        raise RuntimeError("hay una tanda activa; espere a que termine")

    usos = contar_ofertas_por_ubicacion()
    movidas = fusionar_ubicacion(id_origen, id_destino)
    _diario(
        f"FUSIONAR | {id_origen} -> {id_destino} | "
        f"{_descripcion(origen)} -> {_descripcion(destino)} | ofertas={movidas}"
    )
    return [
        f"Fusión realizada: {id_origen} -> {id_destino}",
        f"Antes: {_descripcion(origen)} ({usos.get(id_origen, 0)} ofertas) | "
        f"{_descripcion(destino)} ({usos.get(id_destino, 0)} ofertas)",
        f"Después: {_descripcion(destino)} "
        f"({usos.get(id_origen, 0) + usos.get(id_destino, 0)} ofertas)",
        f"Ofertas movidas: {movidas} (texto original intacto)",
    ]


def _parser() -> argparse.ArgumentParser:
    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument("--db", help="ruta alternativa a la base de datos (ensayo)")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="accion", required=True)

    listado = sub.add_parser("listar", parents=[comun], help="ver el catálogo")
    listado.add_argument("texto", nargs="?", help="buscar por texto o identificador")
    listado.add_argument("--departamento", help="filtrar por departamento")
    listado.add_argument("--origen", choices=("operador", "sistema"))
    listado.add_argument(
        "--tipo",
        choices=("municipio", "departamento", "pais", "no_aplica"),
    )
    listado.add_argument("--todo", action="store_true", help="sin límite de filas")

    alta = sub.add_parser("agregar", parents=[comun], help="registrar una fila")
    alta.add_argument("--municipio", help="nombre del municipio (omitir para solo departamento)")
    alta.add_argument("--departamento", help="nombre del departamento")

    correccion = sub.add_parser("corregir", parents=[comun], help="corregir una fila")
    correccion.add_argument("id", help="identificador de la fila")
    correccion.add_argument("--municipio", help="nuevo nombre del municipio")
    correccion.add_argument("--departamento", help="nuevo nombre del departamento")

    union = sub.add_parser("fusionar", parents=[comun], help="unir dos filas")
    union.add_argument("origen", help="fila equivocada, que se retira")
    union.add_argument("destino", help="fila correcta, que se conserva")
    return parser


def main(argv: list[str] | None = None) -> int:
    argumentos = _parser().parse_args(argv)
    if argumentos.db:
        change_path(Path(argumentos.db))
    try:
        disponible, motivo = _base_disponible()
        if not disponible:
            print(motivo)
            return 1
        try:
            if argumentos.accion == "listar":
                lineas = listar(argumentos)
            elif argumentos.accion == "agregar":
                lineas = agregar(argumentos)
            elif argumentos.accion == "corregir":
                lineas = corregir(argumentos)
            else:
                lineas = fusionar(argumentos)
        except (ValueError, RuntimeError, PersistenceError, sqlite3.Error) as error:
            print(f"No se realizó la acción: {error}")
            return 1
        print("\n".join(lineas))
        return 0
    finally:
        if argumentos.db:
            reset_path()


if __name__ == "__main__":
    raise SystemExit(main())
