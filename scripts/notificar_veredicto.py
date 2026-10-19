"""Notificador del veredicto de una tanda automatica (D57; solo lectura).

Uso:
    python scripts/notificar_veredicto.py --desde "YYYY-MM-DD HH:MM:SS"
    python scripts/notificar_veredicto.py --fallo "texto"
    python scripts/notificar_veredicto.py --omitida "texto"

Con `--desde` lee la traza oficial de la base de datos para la tanda que
inicio en esa marca: identifica la corrida programada cerrada al final de
la cadena, cuenta sus fallos de modulo (conocidos por sus eventos de
resumen) y toma las metricas finales de cada modulo desde su propia fila.
Con `--fallo`/`--omitida` el motivo ya viene del guion de la tanda
(chequeo previo o salida inesperada); un chequeo previo perdido por
"corrida activa" cuenta como omision benigna, no como error.

Todo veredicto se imprime en stdout (queda en la bitacora de la tanda) y
se intenta enviarlo como aviso de escritorio; el aviso nunca altera el
resultado de la corrida ni su codigo de salida.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.persistence import leer_tabla
from shared.utilidades import numero_secuencial_id

TITULO_AVISO = "Búsqueda de empleo"
TEXTO_TANDA_ACTIVA = "corrida activa"
PISTA_REVISION = "revisa el informe de corrida y la bitácora del sistema"
_TOPE_DETALLE = 160
_TOPE_CAUSA = 140
_TOPE_ESPERA_SEGUNDOS = 10


def _analizar_evidencia(evidencia: str) -> dict[str, str]:
    """Key=value pairs of an official summary event (`modulo=x;estado=y;..`)."""
    pares: dict[str, str] = {}
    for fragmento in evidencia.split(";"):
        if "=" in fragmento:
            clave, valor = fragmento.split("=", 1)
            pares[clave.strip()] = valor.strip()
    return pares


def _corrida_programada(desde: str) -> dict[str, Any] | None:
    """The scheduled run of this batch, identified by its summary event.

    Its `corrida_programada` event is the official marker (written on both
    the normal and the abort path, RN-06): the run is not "the last closed
    row", because a module can close on the very same second (same-second
    timestamps) and would steal the identity — observed live on COR-0009.
    """
    eventos = [
        fila
        for fila in leer_tabla("eventos", {"codigo": "corrida_programada"})
        if fila.get("marca_temporal") and str(fila["marca_temporal"]) >= desde
    ]
    if not eventos:
        return None
    eventos.sort(
        key=lambda fila: (
            str(fila["marca_temporal"]),
            numero_secuencial_id(str(fila["id_corrida"])),
        )
    )
    id_programada = str(eventos[-1]["id_corrida"])
    filas = [
        fila
        for fila in leer_tabla("corridas")
        if str(fila["id_corrida"]) == id_programada
    ]
    return filas[0] if filas else None


def _eventos_programada(id_programada: str) -> list[dict[str, Any]]:
    eventos = leer_tabla("eventos", {"id_corrida": id_programada})
    return sorted(eventos, key=lambda fila: str(fila.get("marca_temporal", "")))


def _fallos_de_modulos(id_programada: str) -> list[str]:
    fallos: list[str] = []
    for fila in _eventos_programada(id_programada):
        if fila.get("codigo") != "modulo_fallido":
            continue
        detalle = _analizar_evidencia(str(fila.get("evidencia", "")))
        modulo = detalle.get("modulo") or "N/R"
        motivo = detalle.get("motivo") or "N/R"
        fallos.append(f"{modulo}: {motivo}")
    return fallos


def _filas_de_modulos(
    id_programada: str, corridas: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Module run rows, keyed by module name (`modulo=x;..;id_corrida=C`)."""
    por_id = {str(fila["id_corrida"]): fila for fila in corridas}
    modulos: dict[str, dict[str, Any]] = {}
    for fila in _eventos_programada(id_programada):
        if fila.get("codigo") not in {"modulo_ejecutado", "modulo_fallido"}:
            continue
        detalle = _analizar_evidencia(str(fila.get("evidencia", "")))
        nombre = detalle.get("modulo")
        id_modulo = detalle.get("id_corrida")
        if nombre and id_modulo and id_modulo in por_id:
            modulos[nombre] = por_id[id_modulo]
    return modulos


def _entero(fila: dict[str, Any] | None, clave: str) -> int:
    if fila is None or not isinstance(fila.get(clave), int):
        return 0
    return int(fila[clave])


def _mensaje_exito(fecha_inicio: str, modulos: dict[str, dict[str, Any]]) -> str:
    partes = [f"Tanda {fecha_inicio[11:16]} completada ✓"]
    nuevas = _entero(modulos.get("descubrimiento"), "total_ofertas")
    if nuevas:
        partes.append(f"{nuevas} nuevas")
    preparadas = _entero(modulos.get("preparacion"), "total_preparadas")
    duplicadas = _entero(modulos.get("preparacion"), "total_duplicadas")
    if preparadas or duplicadas:
        partes.append(f"{preparadas} preparadas / {duplicadas} duplicadas")
    aprobadas = _entero(modulos.get("evaluacion"), "total_aprobadas")
    descartadas = _entero(modulos.get("evaluacion"), "total_descartadas")
    if aprobadas or descartadas:
        partes.append(f"{aprobadas} aprobadas / {descartadas} descartadas")
    if len(partes) == 1:
        partes.append("sin ofertas nuevas")
    partes.append("0 errores")
    return " · ".join(partes)


def componer_veredicto(desde: str) -> tuple[str, str]:
    """(nivel, mensaje) con `nivel` en {'exito', 'fallo'} según la traza."""
    programa = _corrida_programada(desde)
    if programa is None:
        return (
            "fallo",
            f"Tanda sin corrida cerrada desde {desde} · {PISTA_REVISION}",
        )
    id_programada = str(programa["id_corrida"])
    estado = str(programa.get("estado") or "N/A")
    motivo = str(programa.get("motivo_terminacion") or "N/R")
    fallos = _fallos_de_modulos(id_programada)
    if estado != "completada" or motivo != "corrida_completada":
        detalle = ", ".join(fallos) if fallos else f"cierre '{motivo}'"
        return "fallo", f"Tanda {id_programada} interrumpida: {detalle} · {PISTA_REVISION}"
    if programa.get("total_errores", 0) or fallos:
        detalle = ", ".join(fallos) or "módulos con fallo"
        return "fallo", f"Tanda {id_programada} con fallos: {detalle} · {PISTA_REVISION}"
    modulos = _filas_de_modulos(id_programada, leer_tabla("corridas"))
    return "exito", _mensaje_exito(str(programa["fecha_inicio"]), modulos)


def _primer_detalle(texto: str) -> str:
    """First failing preflight line when present, else the tempered text."""
    for linea in texto.splitlines():
        if "[FALLA]" in linea:
            detalle = linea.strip()
            break
    else:
        detalle = " ".join(texto.split())
    return detalle[:_TOPE_DETALLE]


def componer_de_texto(fallo: str | None, omitida: str | None) -> tuple[str, str]:
    """Verdict for texts supplied by the wrapper (preflight/hard exit)."""
    if omitida is not None:
        return "omitida", f"Tanda omitida: {omitida}"
    texto = fallo or ""
    if TEXTO_TANDA_ACTIVA in texto:
        linea = next(
            (fragmento for fragmento in texto.splitlines() if TEXTO_TANDA_ACTIVA in fragmento),
            texto,
        )
        razon = linea.strip().removeprefix("[FALLA] ").split(" — ", 1)[0].strip()
        return (
            "omitida",
            f"Tanda omitida: había otra tanda en curso ({razon}) — no es un error",
        )
    return "fallo", f"La tanda no pudo arrancar: {_primer_detalle(texto)} · {PISTA_REVISION}"


def enviar_aviso(cuerpo: str, urgencia: str) -> None:
    """Journal the verdict, then best-effort desktop popup (D57, ERR-04 style)."""
    print(f"AVISO [{urgencia}] {TITULO_AVISO}: {cuerpo}")
    emisor = shutil.which("notify-send")
    if emisor is None:
        print("AVISO no entregado: no hay emisor de avisos de escritorio")
        return
    try:
        resultado = subprocess.run(
            [emisor, "-u", urgencia, TITULO_AVISO, cuerpo],
            check=False,
            capture_output=True,
            timeout=_TOPE_ESPERA_SEGUNDOS,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"AVISO no entregado ({exc})")
        return
    if resultado.returncode != 0:
        causa = (resultado.stderr or "").strip()[:_TOPE_CAUSA] or "sin detalle"
        print(f"AVISO no entregado (sin receptor de avisos en esta sesión): {causa}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Notifica el veredicto de una tanda automatica (D57)."
    )
    parser.add_argument(
        "--desde",
        help="marca de inicio de la tanda (auto veredicto; prioridad sobre --fallo/--omitida)",
    )
    parser.add_argument("--fallo", help="motivo dado por el guion de la tanda")
    parser.add_argument("--omitida", help="motivo de omision dado por el guion")
    args = parser.parse_args()
    if args.desde:
        nivel, cuerpo = componer_veredicto(args.desde)
    elif args.fallo or args.omitida is not None:
        nivel, cuerpo = componer_de_texto(args.fallo, args.omitida)
    else:
        parser.error("se requiere --desde, --fallo o --omitida")
        return
    enviar_aviso(cuerpo, "critical" if nivel == "fallo" else "normal")


if __name__ == "__main__":
    main()
