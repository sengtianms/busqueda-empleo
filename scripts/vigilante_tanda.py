"""Sentinela de la tanda (Lote 3): vigila la vida y cierra corridas fantasma.

Se ejecuta cada minuto desde el programador del sistema (una pasada por
activación). Con la traza oficial hace tres cosas, en este orden:

1. **Cierre de fantasmas con prueba de muerte** (autorizado por el usuario,
   2026-10-22). Clasifica las filas abiertas con los mismos anclajes del
   tablero (tanda + módulo en curso vs. sobrantes históricos) y cierra solo
   lo que ya no puede estar vivo:
   - silla **vencida** (su marca excede el horizonte de obsolescencia, el
     mismo que el arranque usa para relevar sillas, ERR-07): la cadena
     completa está muerta → se cierran todas las abiertas;
   - silla **fresca** de otro módulo: los sobrantes de tandas anteriores con
     silencio propio mayor al umbral son zombis; la tanda y el módulo en
     curso NO se tocan (su silla puede pertenecer a un proceso vivo);
   - silla **libre**: ningún módulo puede estar corriendo → toda abierta con
     silencio propio mayor al umbral es zombi (tanda y módulo incluidos).
   - silla de un dueño con fila ya cerrada: se suelta al pasar (limpieza que
     le falló a su Finalizar); un id que ni siquiera existe en `corridas` se
     deja en paz (toque nada).
   El cierre escribe la forma oficial de Finalizar (estado `abortada`,
   fecha_fin, motivo `proceso_desaparecido`, evento de terminación oficial)
   y suelta solo la silla de esa corrida (liberación por identificador).
2. **Aviso de tanda detenida**: si la tanda lleva más del umbral de
   'congelada' sin ninguna señal con silla fresca, notificación de
   escritorio, una sola vez por tramo de silencio (marcador en logs/).
3. **Tanda viva**: no toca nada.

Avisos y cierres son best-effort: una pasada nunca se interrumpe a mitad.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.estado_corrida import (
    _VENTANA_TANDA_DEFECTO,
    _agrupar_por_corrida,
    _base_pendiente,
    _ordenar_eventos,
    _parsear,
    _separar_abiertas,
    _texto,
)
from scripts.notificar_veredicto import enviar_aviso
from shared.persistence import (
    actualizar_corrida,
    consultar_bloqueo,
    escribir_evento_seguro,
    leer_corrida,
    leer_corridas_abiertas,
    leer_eventos_de_corridas,
    liberar_bloqueo,
    umbral_obsolescencia_minutos,
)
from shared.utilidades import FORMATO_TIMESTAMP

MOTIVO_FANTASMA = "proceso_desaparecido"
_UMBRAL_CONGELADA_DEFECTO = 600
_MARCADOR_DEFECTO = Path("logs") / "vigilante_tanda.json"


def _captura() -> dict[str, Any] | None:
    """Lectura acotada de la traza; None si la base no está lista.

    Solo lo que una pasada necesita: las corridas abiertas, la silla y, si
    el dueño de la silla ya cerró su fila (silla heredada), esa única fila.
    Los eventos se leen solo de las corridas abiertas: la historia cerrada
    no interviene, salvo la fila del dueño de una silla heredada (para
    liberarla).
    """
    if _base_pendiente() is not None:
        return None
    try:
        silla = consultar_bloqueo()
        abiertas = leer_corridas_abiertas()
        id_silla = _texto(silla, "id_corrida") if silla else ""
        ids_abiertas = [_texto(f, "id_corrida") for f in abiertas]
        corridas = list(abiertas)
        if id_silla and id_silla not in set(ids_abiertas):
            dueno = leer_corrida(id_silla)
            if dueno is not None:
                corridas.append(dueno)
        eventos = _ordenar_eventos(leer_eventos_de_corridas(ids_abiertas))
    except Exception:
        return None
    return {
        "corridas": corridas,
        "eventos": eventos,
        "grupos": _agrupar_por_corrida(eventos),
        "abiertas": abiertas,
        "silla": silla,
        "id_silla": id_silla,
    }


def _soltar_sillas_heredadas(captura: dict[str, Any]) -> str | None:
    """Suelta la silla cuyo dueño ya no tiene fila abierta o está cerrada.

    El caso: Finalizar cerró la fila pero no logró soltar la silla (paso
    best-effort con reintento único). El dueño no puede estar vivo (su fila
    ya no está 'en_ejecucion'): la silla es limpia herencia. Un dueño cuyo id
    ni siquiera existe en `corridas` se deja en paz (id anónimo: toque nada).
    """
    id_silla = str(captura["id_silla"])
    if not id_silla:
        return None
    abiertos = {_texto(f, "id_corrida") for f in captura["abiertas"]}
    if id_silla in abiertos:
        return None
    dueno = next(
        (
            fila
            for fila in captura["corridas"]
            if _texto(fila, "id_corrida") == id_silla
        ),
        None,
    )
    if dueno is None or _texto(dueno, "estado") == "en_ejecucion":
        return None
    try:
        liberar_bloqueo(id_silla)
    except Exception:
        return None
    captura["silla"] = None
    captura["id_silla"] = ""
    return id_silla


def _silencio_de(
    fila: dict[str, Any], eventos: list[dict[str, Any]], instante: datetime
) -> float:
    """Segundos de silencio PROPIOS de una corrida (sus eventos o su origen).

    Base: el último evento de esa corrida; si no emitió nada, su fecha de
    inicio. Nunca negativa (una marca en el futuro se ve como 0 segundos).
    """
    id_corrida = _texto(fila, "id_corrida")
    base: datetime | None = None
    for evento in eventos:
        if _texto(evento, "id_corrida") == id_corrida:
            marca = _parsear(_texto(evento, "marca_temporal"))
            if marca is not None and (base is None or marca > base):
                base = marca
    if base is None:
        base = _parsear(_texto(fila, "fecha_inicio"))
    if base is None:
        return float("inf")
    return max((instante - base).total_seconds(), 0.0)


def _clave_ofensa(
    id_tanda: str, silencio: float, umbral: int = _UMBRAL_CONGELADA_DEFECTO
) -> str:
    """Una notificación por (tanda, tramo de silencio); crecer vuelve a avisar."""
    tramos = int(silencio) // umbral
    return f"{id_tanda}|detenida|{tramos}"


def _avisar(cuerpo: str, clave: str, marcador: Path, instante: datetime) -> None:
    """Notifica salvo que la misma ofensa ya se haya avisado antes."""
    try:
        previo = json.loads(marcador.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previo = {}
    if str(previo.get("clave")) == clave:
        return  # misma ofensa y misma tanda: silencio, ya se avisó
    try:
        enviar_aviso(cuerpo, "critical")
    finally:
        try:
            marcador.parent.mkdir(parents=True, exist_ok=True)
            marcador.write_text(
                json.dumps(
                    {"clave": clave, "cuando": instante.strftime(FORMATO_TIMESTAMP)}
                ),
                encoding="utf-8",
            )
        except OSError:
            pass  # el marcador es best-effort; avisar nunca altera datos


def _cerrar_fantasma(id_corrida: str, causa: str, autor: str = "guardian") -> bool:
    """Cierra una corrida fantasma con la forma oficial; nunca aborta.

    Devuelve True solo si la fila quedó cerrada: si la actualización falla
    NO se escribe evento y NO se suelta su silla (la pasada siguiente lo
    repasa con el orden honesto: fila primero, luego evento y liberación).

    `autor` nombra en la evidencia quién ordenó el cierre: el vigía por
    defecto ("guardian"); los mandos del operador (detener/limpiar) pasan
    "orden_operador" para que la traza diga quién la cerró.
    """
    try:
        actualizar_corrida(
            id_corrida,
            {
                "estado": "abortada",
                "fecha_fin": datetime.now().strftime(FORMATO_TIMESTAMP),
                "motivo_terminacion": MOTIVO_FANTASMA,
            },
        )
    except Exception:
        return False
    escribir_evento_seguro(
        {
            "id_corrida": id_corrida,
            "tipo": "error",
            "codigo": MOTIVO_FANTASMA,
            "evidencia": f"proceso=desaparecido | cierre={autor} ({causa})",
            "marca_temporal": datetime.now().strftime(FORMATO_TIMESTAMP),
        },
        contexto_log=id_corrida,
    )
    return True


def _cerrar_fantasmas(
    captura: dict[str, Any], causa: str, autor: str = "guardian"
) -> list[str]:
    """Cierra las corridas ya seleccionadas con prueba de muerte.

    Solo cuenta las que quedaron cerradas de verdad: una fila no cerrada
    conserva su silla y no entra en ni avisos ni en el resumen.
    """
    cerradas: list[str] = []
    for fila in captura["abiertas"]:
        id_corrida = _texto(fila, "id_corrida")
        if not _cerrar_fantasma(id_corrida, causa, autor=autor):
            continue  # fila viva para efectos prácticas: toque nada más
        try:
            liberar_bloqueo(id_corrida)
        except Exception:
            pass  # la silla de un fantasma también da otra oportunidad
        cerradas.append(id_corrida)
    return cerradas


def _cierre_con_prueba(
    captura: dict[str, Any], instante: datetime, umbral_congelada: int, horizonte: int
) -> tuple[list[str], str]:
    """(ids a cerrar, causa) según el estado de la silla y el silencio propio.

    Reglas estrictas de propiedad: la tanda y el módulo en curso (mismas
    anclas del tablero) no se tocan mientras su silla esté fresca; lo demás
    cae con silencio propio mayor al umbral. Silla vencida: cae todo.
    """
    silla = captura["silla"]
    eventos = captura["eventos"]
    if silla is None:
        cerrar = [
            _texto(f, "id_corrida")
            for f in captura["abiertas"]
            if _silencio_de(f, eventos, instante) > umbral_congelada
        ]
        return cerrar, "silla libre"
    marca_silla = _parsear(_texto(silla, "marca_temporal"))
    if marca_silla is None or (instante - marca_silla).total_seconds() > horizonte:
        return [_texto(f, "id_corrida") for f in captura["abiertas"]], "silla vencida"
    tanda, filas_modulo, sobrantes = _separar_abiertas(
        captura["abiertas"],
        captura["grupos"],
        _texto(silla, "id_corrida"),
        _VENTANA_TANDA_DEFECTO,
    )
    intocables = {_texto(silla, "id_corrida")}
    intocables |= {_texto(m, "id_corrida") for m in filas_modulo}
    if tanda is not None:
        intocables.add(_texto(tanda, "id_corrida"))
    cerrar = [
        _texto(f, "id_corrida")
        for f in sobrantes
        if _texto(f, "id_corrida") not in intocables
        and _silencio_de(f, eventos, instante) > umbral_congelada
    ]
    return cerrar, "residuos de tandas viejas"


def pasada(
    *,
    umbral_congelada: int = _UMBRAL_CONGELADA_DEFECTO,
    horizonte_minutos: int | None = None,
    marcador: Path = _MARCADOR_DEFECTO,
    referencia: datetime | None = None,
) -> str:
    """Una pasada del vigía; devuelve un resumen legible de lo que hizo."""
    instante = referencia or datetime.now()
    horizonte = (
        horizonte_minutos if horizonte_minutos is not None
        else umbral_obsolescencia_minutos()
    ) * 60
    captura = _captura()
    if captura is None:
        return "Base de datos no disponible: la pasada no toca nada."
    notas: list[str] = []
    heredada = _soltar_sillas_heredadas(captura)
    if heredada is not None:
        notas.append(f"silla heredada de {heredada} liberada")
    abiertas = captura["abiertas"]
    if not abiertas:
        return "; ".join(notas) if notas else "Sin corridas abiertas: nada que vigilar."

    id_tanda = _texto(_ordenamiento_rapido(captura)[0], "id_corrida")
    cerrar, causa = _cierre_con_prueba(
        captura, instante, umbral_congelada, horizonte
    )
    if cerrar:
        cerrables = [f for f in abiertas if _texto(f, "id_corrida") in cerrar]
        cerradas = _cerrar_fantasmas({**captura, "abiertas": cerrables}, causa)
        if cerradas:
            cuenta = (
                "1 fantasma cerrado"
                if len(cerradas) == 1
                else f"{len(cerradas)} fantasmas cerrados"
            )
            notas.append(f"{causa.capitalize()}: {cuenta} ({', '.join(cerradas)})")
            cuerpo = (
                f"Corridas fantasma cerradas ({', '.join(cerradas)}): "
                f"proceso desaparecido ({causa})."
            )
            clave = f"{id_tanda}|fantasmas|{causa}|{'-'.join(cerradas)}"
            _avisar(cuerpo, clave, marcador, instante)
        cerrados = set(cerradas)
        abiertas = [f for f in abiertas if _texto(f, "id_corrida") not in cerrados]

    if not abiertas:
        return "; ".join(notas) if notas else "Sin corridas abiertas: nada que vigilar."

    silencio_tanda = min(_silencio_de(f, captura["eventos"], instante) for f in abiertas)
    destinatario = (f" [{'; '.join(notas)}]" if notas else "")
    if silencio_tanda <= umbral_congelada:
        mensaje = (
            f"Tanda {id_tanda} viva (silencio {int(silencio_tanda)}s): nada que hacer."
        )
        return f"{mensaje}{destinatario}"
    if captura["silla"] is not None:
        cuerpo = (
            f"La tanda {id_tanda} lleva {int(silencio_tanda / 60)} min sin señales "
            "— examínela."
        )
        _avisar(
            cuerpo,
            _clave_ofensa(id_tanda, silencio_tanda, umbral_congelada),
            marcador,
            instante,
        )
        return f"Tanda {id_tanda} detenida con silla fresca: solo aviso.{destinatario}"
    return (
        f"Tanda {id_tanda} en espera temprana (silencio {int(silencio_tanda)}s "
        f"y silla libre): se observa.{destinatario}"
    )


def _ordenamiento_rapido(captura: dict[str, Any]) -> list[dict[str, Any]]:
    """Corridas abiertas de la más nueva a la más vieja."""
    return sorted(
        captura["abiertas"], key=lambda f: _texto(f, "fecha_inicio"), reverse=True
    )


def main(argv: list[str] | None = None) -> int:
    """Entrada del programador: una pasada con --db opcional."""
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else ""
    )
    parser.add_argument(
        "--umbral-congelada",
        type=int,
        default=_UMBRAL_CONGELADA_DEFECTO,
        help="segundos sin señales para considerar la tanda detenida",
    )
    parser.add_argument(
        "--horizonte-minutos",
        type=int,
        default=None,
        help="minutos de silla vencida para cerrar fantasmas (config por defecto)",
    )
    parser.add_argument(
        "--marcador",
        default=str(_MARCADOR_DEFECTO),
        help="ruta del marcador de avisos (una notificación por ofensa)",
    )
    parser.add_argument("--db", help="ruta alternativa a la base de datos")
    args = parser.parse_args(argv)
    if args.umbral_congelada <= 0:
        parser.error("--umbral-congelada debe ser mayor que 0 (segundos)")
    opcion_db = Path(args.db) if args.db else None
    if opcion_db is not None:
        from shared.persistence import change_path, reset_path

        change_path(opcion_db)
    try:
        resumen = pasada(
            umbral_congelada=args.umbral_congelada,
            horizonte_minutos=args.horizonte_minutos,
            marcador=Path(args.marcador),
        )
    finally:
        if opcion_db is not None:
            from shared.persistence import reset_path

            reset_path()
    print(resumen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
