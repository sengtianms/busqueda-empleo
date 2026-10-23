"""Mandos operativos del ciclo de tandas: pausar, reanudar, detener y limpiar.

Cuatro órdenes del operador sobre el ciclo automático (decisión D64), cada
una una sola activación y todas idempotentes (repetirlas es seguro):

- **pausar**: apaga el reloj del programador (ninguna tanda automática
  vuelve a dispararse, ni siquiera tras un reinicio) hasta que se reanude.
  La tanda en curso termina con normalidad.
- **reanudar**: vuelve a armar el reloj y verifica la salud del sistema de
  tandas (si el vigía quedó suelto, lo reinstala con el instalador oficial).
- **detener**: corta la tanda en marcha ahora mismo — si es programada, por
  la vía ordenada del programador; si fue lanzada a mano, junto con su
  navegador — y deja ya mismo el cierre honesto de esa corrida usando la
  maquinaria del vigía, con la orden del operador anotada en la evidencia.
- **limpiar**: barrido a cero: detiene todo residuo en marcha, cierra toda
  corrida abierta, suelta la silla que quede y verifica "nada corriendo".
  Nunca borra datos históricos y nunca desactiva el reloj (eso es pausar).

Cierres y avisos son best-effort: una orden nunca se interrumpe a mitad.
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.estado_corrida import _VENTANA_TANDA_DEFECTO, _separar_abiertas, _texto
from scripts.notificar_veredicto import enviar_aviso
from scripts.vigilante_tanda import _captura, _cerrar_fantasmas
from shared.persistence import change_path, liberar_bloqueo, reset_path

_UNIT_TANDA = "busqueda-empleo.service"
_RELOJ = "busqueda-empleo.timer"
_RELOJ_VIGIA = "busqueda-empleo-vigilante.timer"

# Rastros de proceso propios de una tanda: el flujo oficial (manual o en la
# jaula del programador) y el navegador que la captura puede dejar suelto.
_PATRONES_PROCESOS = ("modules.orchestrator", "corrida_programada.sh")
_PATRON_NAVEGADOR = "ms-playwright"
_GRACIA_SEGUNDOS = 3.0


def _ctl(*argumentos: str) -> subprocess.CompletedProcess[str]:
    """Ejecuta una orden del programador del sistema; nunca interrumpe."""
    try:
        return subprocess.run(
            ["systemctl", "--user", *argumentos],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return subprocess.CompletedProcess(
            args=list(argumentos), returncode=255, stdout="", stderr=""
        )


def _estado_unidad(unidad: str, consulta: str) -> str:
    """Primera línea de 'is-enabled'/'is-active' ('enabled', 'active', ...)."""
    resultado = _ctl(consulta, unidad)
    salida = (resultado.stdout or resultado.stderr or "").strip()
    return salida.splitlines()[0].strip() if salida else ""


def _habilitado(unidad: str) -> bool:
    return _estado_unidad(unidad, "is-enabled") == "enabled"


def _en_marcha(unidad: str) -> bool:
    return _estado_unidad(unidad, "is-active") == "active"


def _instalar_salud() -> str:
    """Repara el sistema de tandas con el instalador oficial (idempotente)."""
    instalador = Path(__file__).resolve().parent / "instalar_programador.sh"
    try:
        resultado = subprocess.run(
            ["bash", str(instalador)],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return "la salud del sistema de tandas no se pudo restaurar (instalador inalcanzable)"
    if resultado.returncode == 0:
        return "salud del sistema de tandas restaurada con el instalador oficial"
    linea = (resultado.stderr or "").strip().splitlines()
    detalle = linea[0][:80] if linea else "sin detalle"
    return f"la salud no se pudo restaurar ({detalle})"


def _procesos(patron: str) -> set[int]:
    """PIDs vivos cuyo texto de ejecución contiene el patrón (pgrep)."""
    try:
        resultado = subprocess.run(
            ["pgrep", "-f", patron],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    return {int(pid) for pid in resultado.stdout.split() if pid.isdigit()}


def _pistas_de_procesos() -> tuple[set[int], set[int]]:
    """(procesos propios de la tanda, procesos del navegador de captura)."""
    propios = {pid for patron in _PATRONES_PROCESOS for pid in _procesos(patron)}
    navegador = _procesos(_PATRON_NAVEGADOR)
    return propios, navegador


def _cortar(pids: set[int], senal: int = signal.SIGTERM) -> None:
    """Manda una señal a cada proceso; uno ya muerto se ignora en paz."""
    for pid in pids:
        try:
            os.kill(pid, senal)
        except OSError:
            pass


def _pausa(segundos: float) -> None:
    time.sleep(max(segundos, 0.0))


def _ancestros() -> set[int]:
    """La cadena de antepasados del propio proceso: la mano que manda.

    Un mando de control puede estar corriendo dentro de una terminal cuyo
    propio texto de ejecución menciona los patrones de proceso (un operador
    que consulta procesos con esos rastros): cortar semejante Match sería
    asesinar la propia orden. Los antepasados jamás son objetivo.
    """
    mano: set[int] = set()
    pid = os.getpid()
    while pid > 1:
        mano.add(pid)
        try:
            texto = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
        except OSError:
            break
        linea = next(
            (linea for linea in texto.splitlines() if linea.startswith("PPid:")),
            None,
        )
        if linea is None:
            break
        try:
            pid = int(linea.split()[1])
        except (IndexError, ValueError):
            break
    return mano


def _matar_derivados(gracia: float = _GRACIA_SEGUNDOS) -> int:
    """Corta los procesos en marcha de la tanda; devuelve cuántos cayeron.

    Primero la señal suave y, si tras la gracia alguien se negó a morir,
    la fuerza para los sobrevivientes. Los antepasados del propio mando
    (la terminal que escribirá los patrones) jamás son objetivo.
    """
    propios, navegador = _pistas_de_procesos()
    objetivos = (propios | navegador) - _ancestros()
    if not objetivos:
        return 0
    _cortar(objetivos)
    _pausa(gracia)
    restos, restos_navegador = _pistas_de_procesos()
    sobrevivientes = ((restos | restos_navegador) & objetivos) - _ancestros()
    if sobrevivientes:
        _cortar(sobrevivientes, senal=signal.SIGKILL)
    _pausa(0.2)
    return len(objetivos)


def _formatear(mensajes: list[str]) -> str:
    return "\n".join(f"· {mensaje}" for mensaje in mensajes)


def pausar() -> str:
    """Apaga el reloj del programador; idempotente y sin tocar la traza."""
    mensajes: list[str] = []
    actuo = False
    if _habilitado(_RELOJ):
        _ctl("stop", _RELOJ)
        _ctl("disable", _RELOJ)
        actuo = True
        mensajes.append(
            "Pausa activa: no se disparará ninguna tanda automática "
            "(sobrevive a apagones y reinicios) hasta que la reanudes."
        )
    else:
        mensajes.append("El reloj ya estaba apagado: la pausa sigue vigente.")
    if _en_marcha(_UNIT_TANDA):
        mensajes.append("La tanda en curso termina con normalidad.")
    if actuo:
        enviar_aviso("; ".join(mensajes), "normal")
    return _formatear(mensajes)


def reanudar() -> str:
    """Arma de nuevo el reloj y restaura la salud del sistema de tandas."""
    mensajes: list[str] = []
    actuo = False
    armado = _habilitado(_RELOJ)
    encendido = _en_marcha(_RELOJ)
    if armado and encendido:
        mensajes.append("El reloj ya está armado: nada que cambiar.")
    else:
        if not armado:
            _ctl("enable", _RELOJ)
        if not encendido:
            _ctl("start", _RELOJ)
        actuo = True
        mensajes.append("Tandas automáticas reanudadas: el reloj quedó armado.")
    if not _habilitado(_RELOJ_VIGIA):
        actuo = True  # una reparación (lograda o no) es una acción real
        mensajes.append(_instalar_salud())
    siguiente = _ctl("list-timers", _RELOJ, "--no-pager")
    lineas = siguiente.stdout.strip().splitlines()
    datos = next((linea for linea in lineas[1:] if linea.strip()), None)
    if datos:
        proximo = " ".join(datos.split()[:5])
        mensajes.append(f"Próximo disparo del reloj: {proximo}.")
    if actuo:
        enviar_aviso("; ".join(mensajes), "normal")
    return _formatear(mensajes)


def detener(*, gracia: float = _GRACIA_SEGUNDOS) -> str:
    """Corta la tanda en marcha y la cierra al instante (forma del vigía).

    Objetivo de cierre: el núcleo vivo identificado con las mismas anclas
    del tablero (tanda + módulo en curso). Si las anclas no delatan nada y
    hay filas abiertas, cayeron ya con el proceso: son todas de esta tanda
    y el operador ordenó detenerla.
    """
    mensajes: list[str] = []
    actuo = False
    estado_servicio = _estado_unidad(_UNIT_TANDA, "is-active")
    if estado_servicio == "active":
        _ctl("stop", _UNIT_TANDA)
        actuo = True
        mensajes.append("Tanda programada detenida por el programador.")
    elif estado_servicio == "failed":
        _ctl("stop", _UNIT_TANDA)
        _ctl("reset-failed", _UNIT_TANDA)
        mensajes.append("La unidad de la tanda quedó marcada como fallida: despejada.")
    cortados = _matar_derivados(gracia=gracia)
    if cortados:
        actuo = True
        mensajes.append(f"{cortados} proceso(s) de tanda manual cortado(s).")
    captura = _captura()
    if captura is None:
        mensajes.append(
            "No se pudo abrir la base de datos: la corrida queda por cerrar "
            "y el vigía la repasará al pasar."
        )
        if actuo:
            enviar_aviso("; ".join(mensajes), "normal")
        return _formatear(mensajes)
    abiertas = captura["abiertas"]
    if not abiertas:
        if not actuo:
            return "No hay tanda en marcha: nada que detener."
        mensajes.append("La traza no tiene corridas abiertas: nada que cerrar.")
        enviar_aviso("; ".join(mensajes), "normal")
        return _formatear(mensajes)
    tanda, filas_modulo, sobrantes = _separar_abiertas(
        abiertas,
        captura["grupos"],
        str(captura["id_silla"]),
        _VENTANA_TANDA_DEFECTO,
    )
    objetivos: list[dict[str, Any]] = [
        fila for fila in (tanda, *filas_modulo) if fila is not None
    ]
    ciegos = not objetivos
    if ciegos:
        objetivos = list(abiertas)
    cerradas = _cerrar_fantasmas(
        {**captura, "abiertas": objetivos},
        "tanda detenida por el operador",
        autor="orden_operador",
    )
    abiertos = {_texto(fila, "id_corrida") for fila in objetivos}
    no_cerradas = sorted(abiertos - set(cerradas))
    if cerradas:
        actuo = True
        mensajes.append(
            f"Corrida(s) cerrada(s) al instante: {', '.join(cerradas)} "
            "(abortada · proceso desaparecido · orden del operador)."
        )
    if no_cerradas:
        mensajes.append(
            f"No se pudo cerrar: {', '.join(no_cerradas)} — "
            "el vigía lo repetirá al pasar."
        )
    if sobrantes and not ciegos:
        mensajes.append(
            f"{len(sobrantes)} fila(s) sobrante(s) de tandas viejas quedan "
            "para el vigía (o usa limpiar)."
        )
    if actuo:
        enviar_aviso("; ".join(mensajes), "normal")
    return _formatear(mensajes)


def limpiar(*, gracia: float = _GRACIA_SEGUNDOS) -> str:
    """Barrido a cero: nada corriendo, sin silla y sin corridas abiertas."""
    mensajes: list[str] = []
    actuo = False
    if _en_marcha(_UNIT_TANDA):
        _ctl("stop", _UNIT_TANDA)
        actuo = True
        mensajes.append("Tanda programada detenida por el programador.")
    elif _estado_unidad(_UNIT_TANDA, "is-active") == "failed":
        _ctl("stop", _UNIT_TANDA)
        _ctl("reset-failed", _UNIT_TANDA)
        mensajes.append("La unidad de la tanda quedó marcada como fallida: despejada.")
    cortados = _matar_derivados(gracia=gracia)
    if cortados:
        actuo = True
        mensajes.append(f"{cortados} proceso(s) suelto(s) de tandas cortado(s).")
    captura = _captura()
    if captura is None:
        mensajes.append(
            "No se pudo abrir la base de datos: las corridas abiertas quedan "
            "para el vigía."
        )
        if actuo:
            enviar_aviso("; ".join(mensajes), "normal")
        return _formatear(mensajes)
    abiertas = list(captura["abiertas"])
    if abiertas:
        cerradas = _cerrar_fantasmas(
            {**captura, "abiertas": abiertas},
            "limpieza ordenada por el operador",
            autor="orden_operador",
        )
        actuo = True
        faltantes = sorted(
            {_texto(fila, "id_corrida") for fila in abiertas} - set(cerradas)
        )
        notas = f"Corridas cerradas: {', '.join(cerradas)}." if cerradas else ""
        if faltantes:
            notas = f"{notas} No se pudo cerrar {', '.join(faltantes)} (el vigía repasará)."
        mensajes.append(notas.strip() or "Nada abierto que cerrar.")
    restante = _captura()
    if restante is None:
        mensajes.append(
            "No se pudo leer la traza para verificar el cierre: revisa con el "
            "tablero; el vigía repasará al pasar."
        )
        quedan = True
    else:
        silla_restante = restante["silla"]
        if silla_restante is not None:
            id_silla = str(_texto(silla_restante, "id_corrida"))
            try:
                liberar_bloqueo(id_silla)
                actuo = True
                mensajes.append(f"Silla restante de {id_silla} liberada.")
            except Exception:
                mensajes.append(f"La silla de {id_silla} no se pudo liberar.")
        quedan = bool(restante["abiertas"])
    propios, navegador = _pistas_de_procesos()
    if quedan or propios or navegador:
        mensajes.append(
            "Aún no hay cero total: quedan corridas abiertas o procesos "
            "(el vigía las repasará); vuelve a pasar limpiar si te hace falta."
        )
    else:
        mensajes.append(
            "Todo en cero: nada queda en marcha."
            if actuo
            else "Ya estaba todo en cero: nada que limpiar."
        )
    if not _habilitado(_RELOJ):
        mensajes.append("El reloj de tandas está en pausa.")
    else:
        mensajes.append("El reloj sigue armado: la próxima tanda llegará en su turno.")
    if actuo:
        enviar_aviso("; ".join(mensajes), "normal")
    return _formatear(mensajes)


_ORDENES: dict[str, Callable[..., str]] = {
    "pausar": pausar,
    "reanudar": reanudar,
    "detener": detener,
    "limpiar": limpiar,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="orden", required=True)
    for nombre in _ORDENES:
        hijo = sub.add_parser(nombre, help=f"orden {nombre}")
        hijo.add_argument("--db", help="ruta alternativa a la base de datos")
        if nombre in ("detener", "limpiar"):
            hijo.add_argument(
                "--gracia",
                type=float,
                default=_GRACIA_SEGUNDOS,
                help="segundos entre la señal suave y la forzosa",
            )
    argumentos = parser.parse_args(argv)
    if argumentos.db:
        change_path(Path(argumentos.db))
    try:
        if argumentos.orden == "detener":
            texto = detener(gracia=argumentos.gracia)
        elif argumentos.orden == "limpiar":
            texto = limpiar(gracia=argumentos.gracia)
        else:
            texto = _ORDENES[argumentos.orden]()
    except Exception as exc:  # una orden nunca deja al operador sin respuesta
        print(f"· La orden {argumentos.orden} se interrumpió: {exc}")
        return 1
    finally:
        if argumentos.db:
            reset_path()
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
