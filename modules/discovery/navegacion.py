"""Canal de navegación resiliente del Módulo 1 (D61, 2026-10-22).

Dos mecanismos sobre un mismo camino de reconstrucción:

- **Renovación preventiva**: el canal se reconstruye tras N cargas pesadas
  de página (umbral configurable) para que la memoria nunca escale a la
  zona de colapso (autopsia 2026-10-22: 5,5 GB con 46 páginas seguidas).
- **Resurección ante muerte**: si el navegador muere ("Target crashed",
  colapso silencioso), el árbol se fuerza al suelo, se abre un canal nuevo
  con la misma memoria de sesión y la búsqueda retoma su paginación en la
  página donde murió. Las resurecciones no tienen techo (ley de la tanda):
  la única rendición honesta es la ventana de ingreso manual o un entorno
  insostenible (muertes consecutivas sin avance), y ambos cierran la tanda
  con veredicto.

El **latido** es la red contra el silencio: toda operación supervisada del
canal lleva un techo de tiempo absoluto; si no responde ni falla, el
vigilante mata el árbol del navegador y la llamada bloqueada despierta con
"Target closed", activando la resurección. El silencio estructural (la
corrida viva pero muda que colgó la tanda de las 14:51) deja de existir.
"""

import re
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger
from playwright.sync_api import sync_playwright

from modules.discovery.adapters.registry import obtener_adaptador
from modules.discovery.nodes.finalizar import cerrar_recursos
from modules.discovery.run_context import RunContext
from shared.config import load
from shared.models import PoliticasCaptura
from shared.persistence import registrar_evento
from shared.utilidades import (
    acotar_evidencia,
    ruta_perfil_navegador,
    ventana_navegador,
)

# Margen fijo sobre la duración legítima declarada de cada operación.
_TECHO_MARGEN_SEGUNDOS = 60.0
# Frecuencia de revisión del vigilante (segundos).
_TABLA_RESPUESTA = 0.5

# Señales con las que el canal anuncia su muerte (adaptador, SDK y driver).
_SENALES_MUERTE = (
    "target crashed",
    "page crashed",
    "target closed",
    "connection closed",
    "browser has been closed",
    "target page, context or browser has been closed",
    "session closed",
    "playwright connection closed",
    "browser detached",
)


def es_muerte_navegador(exc: BaseException) -> bool:
    """True si la señal corresponde a la muerte del canal del navegador.

    Camina la cadena de causas (``__cause__``): el adaptador envuelve los
    fallos de navegación en FlowError con el mensaje original adentro
    ("Target crashed", "Connection closed"...). El bloqueo de plataforma
    (authwall) es problema de la sesión, no del canal, y no cuenta.
    """
    visto: set[int] = set()
    actual: BaseException | None = exc
    while actual is not None and id(actual) not in visto:
        visto.add(id(actual))
        texto = str(actual).lower()
        if any(senal in texto for senal in _SENALES_MUERTE):
            return True
        actual = actual.__cause__
    return False


def resolver_headless(config: dict[str, Any] | None = None) -> bool:
    """Modo headless: BROWSER_HEADLESS (.env) gana sobre config.yaml.

    ``config`` permite inyectar la carga ya resuelta (el nodo de ingreso
    inyecta la SUYA para respetar sus parches de prueba).
    """
    cfg = config if config is not None else load()
    env_raw = cfg.get("_env", {})
    env: dict[str, Any] = env_raw if isinstance(env_raw, dict) else {}
    override = env.get("BROWSER_HEADLESS")
    if isinstance(override, str):
        return override.strip().lower() != "false"
    cfg_browser = cfg.get("browser", {})
    if not isinstance(cfg_browser, dict):
        return True
    return cfg_browser.get("headless", True) is not False


def resolver_perfil() -> str:
    """Carpeta de sesión persistente (``browser.profile_path``); "" = sin memoria."""
    cfg = load()
    return ruta_perfil_navegador(cfg.get("browser", {}))


def abrir_canal_instancia(
    playwright_instance: Any, headless: bool | None = None
) -> tuple[Any, Any]:
    """Crea la ventana del canal sobre una instancia Playwright ya viva.

    Con perfil persistente (memoria de sesión); ante fallo del persistente,
    canal efímero. Devuelve ``(browser_o_contexto, page)``. ``headless=None``
    resuelve el modo en navegación; un valor explícito manda (compatibilidad
    con el nodo de ingreso). Lógica movida desde ``ingreso._abrir_pagina``
    (D61) para compartirla con la reconstrucción.
    """
    ancho, alto = ventana_navegador(load().get("browser", {}))
    argumentos = [f"--window-size={ancho},{alto}"]
    perfil = resolver_perfil()
    if perfil:
        try:
            Path(perfil).mkdir(parents=True, exist_ok=True)
            canal = playwright_instance.chromium.launch_persistent_context(
                perfil,
                headless=resolver_headless() if headless is None else headless,
                args=argumentos,
                no_viewport=True,
            )
            return canal, canal.new_page()
        except Exception as exc:
            logger.warning(f"Perfil persistente no usable ({exc}); uso modo efímero")
    browser = playwright_instance.chromium.launch(
        headless=resolver_headless() if headless is None else headless,
        args=argumentos,
    )
    return browser, browser.new_page(no_viewport=True)


def abrir_canal() -> tuple[Any, Any, Any]:
    """Abre un canal completo: ``(instancia, browser_o_contexto, page)``."""
    instancia = sync_playwright().start()
    try:
        canal, pagina = abrir_canal_instancia(instancia)
    except Exception:
        try:
            instancia.stop()
        except Exception:
            pass
        raise
    return instancia, canal, pagina


def matar_arbol_navegador() -> None:
    """Fuerza el árbol del navegador de automatización al suelo (D61).

    Solo procesos de la automatización: el patrón exige `--user-data-dir=`
    (los procesos hijos del navegador no lo llevan y los navegadores
    personales no usan este perfil); sin perfil se apunta al chromium de
    Playwright. SIGKILL al navegador principal: sus hijos mueren al caer el
    padre. Mejor esfuerzo, sin excepciones.
    """
    perfil = resolver_perfil()
    if perfil:
        patron = f"--user-data-dir=.*{re.escape(perfil)}"
    else:
        patron = "ms-playwright"
    try:
        subprocess.run(
            ["pkill", "-9", "-f", "--", patron],
            check=False,
            timeout=15,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        logger.warning(f"pkill del navegador fallo (mejor esfuerzo): {exc}")


def matar_navegador(contexto: RunContext) -> None:
    """Cierra el canal con cortesía y fuerza el árbol al suelo (D61)."""
    cerrar_recursos(contexto)
    matar_arbol_navegador()


def _declarar_insostenible(contexto: RunContext, razon: str) -> None:
    """Marca la tanda insostenible: el cierre honesto es lo que sigue."""
    contexto.navegador_insostenible = True
    logger.error(
        f"Navegador insostenible | run={contexto.id_corrida} | {razon}"
    )


def _descartar_canal(instancia: Any, canal: Any, pagina: Any) -> None:
    """Cierra un canal de reconstrucción fallida; mejor esfuerzo."""
    for recurso, cerrar in ((pagina, "close"), (canal, "close")):
        try:
            getattr(recurso, cerrar)()
        except Exception:
            pass
    try:
        instancia.stop()
    except Exception:
        pass


def reabrir_navegador(contexto: RunContext, motivo: str) -> bool:
    """Reconstruye el canal con la misma memoria de sesión y re-ingresa (D61).

    Mata el árbol herido, abre un canal nuevo, verifica la entrada con la
    sesión persistente (la ventana manual de 5 minutos del nodo de ingreso
    vive dentro de ``enter_source``) y actualiza el contexto. Devuelve True
    con el canal vivo; False deja ``navegador_insostenible`` activo para que
    los llamadores cierren la tanda honesto. El ``id_sesion`` se conserva:
    la sesión lógica de la tanda no cambia con la reconstrucción.
    """
    ficha = contexto.fuente_corriente
    logger.warning(
        f"Reconstruyendo navegador | run={contexto.id_corrida} | motivo={motivo} | "
        f"fuente={ficha.fuente_id if ficha else 'desconocida'} | "
        f"paginas_renovadas={contexto.paginas_desde_renovacion}"
    )
    matar_navegador(contexto)
    if ficha is None:
        _declarar_insostenible(contexto, "fuente_corriente ausente en la reconstrucción")
        return False
    try:
        instancia, canal, pagina = abrir_canal()
    except Exception as exc:
        evidencia = acotar_evidencia(str(exc))
        logger.error(f"Reapertura del navegador fallo | run={contexto.id_corrida} | {evidencia}")
        _declarar_insostenible(contexto, f"reapertura falló: {evidencia}")
        return False
    try:
        resultado = obtener_adaptador(ficha.fuente_id).enter_source(pagina, ficha, None)
    except Exception as exc:
        evidencia = acotar_evidencia(str(exc))
        logger.error(
            f"Reingreso tras reconstrucción falló | run={contexto.id_corrida} | {evidencia}"
        )
        _descartar_canal(instancia, canal, pagina)
        _declarar_insostenible(contexto, f"reingreso falló: {evidencia}")
        return False
    contexto.playwright_instance = instancia
    contexto.browser = canal
    contexto.handle_sesion = pagina
    if resultado.estado != "exito":
        logger.error(
            f"Reingreso sin criterio cumplido | run={contexto.id_corrida} | "
            f"estado={resultado.estado} | motivo={resultado.codigo_motivo}"
        )
        _declarar_insostenible(
            contexto, f"reingreso sin criterio ({resultado.codigo_motivo})"
        )
        return False
    registrar_evento(
        id_corrida=contexto.id_corrida,
        tipo="suceso",
        codigo="navegador_renovado",
        evidencia=(
            f"motivo={motivo} | paginas_renovadas={contexto.paginas_desde_renovacion} | "
            f"criterio={ficha.criterio_exito}"
        ),
        fuente_id=ficha.fuente_id,
        id_sesion=contexto.id_sesion,
    )
    return True


def renovar_si_toca(contexto: RunContext) -> bool:
    """Reconstruye el canal cuando el tramo vivido alcanza el umbral (D61).

    True con el canal vivo (nada que renovar o renovación exitosa); False
    si la renovación falló (contexto insostenible, cierre honesto arriba).
    """
    if contexto.paginas_desde_renovacion < contexto.renovar_navegador_tras_paginas:
        return True
    logger.info(
        f"Renovación prevista del navegador | run={contexto.id_corrida} | "
        f"paginas={contexto.paginas_desde_renovacion}"
    )
    if not reabrir_navegador(contexto, motivo="renovacion_programada"):
        return False
    contexto.paginas_desde_renovacion = 0
    return True


def techo_por_paginas(
    ficha_timeout_segundos: int,
    politicas: PoliticasCaptura,
    paginas: int,
) -> float:
    """Techo de latido para un tramo de captura de ``paginas`` páginas.

    Deriva del tiempo legítimo declarado por página (navegación + espera +
    pausa anti-bloqueo) más un margen fijo: nunca debe dispararse con
    trabajo real en marcha, solo con el canal colgado.
    """
    por_pagina = float(
        max(1, ficha_timeout_segundos)
        + max(1, politicas.tope_espera_paginas_sucesivas_segundos)
        + politicas.pausa_entre_lotes_segundos * 1.5
    )
    return max(1.0, float(paginas)) * por_pagina + _TECHO_MARGEN_SEGUNDOS


def techo_por_aplicacion(ficha_timeout_segundos: int) -> float:
    """Techo de latido para la aplicación de filtros (incluye fallback UI)."""
    return max(1, ficha_timeout_segundos) * 4 + _TECHO_MARGEN_SEGUNDOS


class LatidoNavegador:
    """Vigilante con techo absoluto por operación del canal (D61).

    Una llamada silenciosa (canal colgado sin excepción) no puede detener
    la tanda: vencido el techo, el vigilante mata el árbol del navegador y
    la llamada bloqueada despierta con un error de canal muerto, que el
    camino de resurección ya sabe tratar.
    """

    def __init__(self) -> None:
        self._candado = threading.Lock()
        self._limite: float = 0.0
        self._matador: Callable[[], None] | None = None
        self._hilo: threading.Thread | None = None
        self._detener = threading.Event()

    def vigilar(
        self,
        etiqueta: str,
        techo_segundos: float,
        matador: Callable[[], None] | None = None,
    ) -> None:
        """Arma el techo de la operación vigente (una sola a la vez)."""
        with self._candado:
            self._limite = time.monotonic() + max(1.0, techo_segundos)
            self._matador = matador if matador is not None else matar_arbol_navegador
        self._asegurar_hilo()
        logger.debug(
            f"Latido armado | operacion={etiqueta} | techo_s={techo_segundos:.0f}"
        )

    def descansar(self) -> None:
        """Paga el techo: la operación terminó (bien, mal o con muerte)."""
        with self._candado:
            self._limite = 0.0
            self._matador = None

    def cerrar(self) -> None:
        """Apaga el vigilante (higiene entre tandas; el hilo es daemon igual)."""
        self._detener.set()

    def _asegurar_hilo(self) -> None:
        if self._hilo is not None and self._hilo.is_alive():
            return
        self._detener.clear()
        self._hilo = threading.Thread(
            target=self._ciclo_vigilante, name="latido-navegador", daemon=True
        )
        self._hilo.start()

    def _ciclo_vigilante(self) -> None:
        while not self._detener.wait(_TABLA_RESPUESTA):
            self._revisar()

    def _revisar(self) -> None:
        with self._candado:
            limite = self._limite
            matador = self._matador
        if not limite or time.monotonic() <= limite:
            return
        self.descansar()
        logger.error(
            "Latido: operación del navegador sin respuesta; "
            "árbol del navegador forzado al suelo"
        )
        if matador is not None:
            try:
                matador()
            except Exception as exc:
                logger.error(f"Latido: el matador falló (mejor esfuerzo): {exc}")


_LATIDO: LatidoNavegador | None = None


def latido() -> LatidoNavegador:
    """Vigilante único por proceso (diferido; las pruebas pueden sustituirlo)."""
    global _LATIDO
    if _LATIDO is None:
        _LATIDO = LatidoNavegador()
    return _LATIDO
