from dataclasses import dataclass
from typing import Any, cast

from loguru import logger
from playwright.sync_api import sync_playwright

from modules.discovery.adapters.linkedin import FlowError
from modules.discovery.adapters.registry import AdaptadorPlataforma, obtener_adaptador
from modules.discovery.navegacion import (
    abrir_canal_instancia,
    resolver_headless,
    resolver_perfil,
)
from modules.discovery.run_context import RunContext
from shared.config import load
from shared.models import EntryResult, FichaFuente
from shared.persistence import generar_id, registrar_evento
from shared.retry import ejecutar_con_reintento
from shared.utilidades import acotar_evidencia


@dataclass
class ResultadoIngreso:
    estado: str  # "ok" | "error"
    contexto: RunContext | None = None
    codigo: str = ""
    descripcion: str = ""
    decision: str = ""  # "si" | "no"


def ejecutar_ingreso(contexto: RunContext) -> ResultadoIngreso:
    """
    Nodo: Entrar a la fuente seleccionada (v1.1).
    Abre el canal de comunicación y verifica el criterio de ingreso.
    """
    ficha = contexto.fuente_corriente
    if ficha is None:
        logger.error(f"ERR-01: fuente_corriente ausente en corrida {contexto.id_corrida}")
        return ResultadoIngreso(
            estado="error", codigo="ERR-01", descripcion="Fuente corriente ausente"
        )

    # Paso 2: Resolver credenciales (una sola vez; el loop las recibe).
    # Con memoria de sesión no se exigen: la primera vez ingresa el usuario
    # a mano y las siguientes reutilizan la sesión guardada.
    credenciales = _resolver_credenciales(ficha)
    if (
        ficha.tipo_acceso == "con_autenticacion"
        and credenciales is None
        and not _resolver_perfil()
    ):
        # ERR-02: Credenciales no disponibles
        contexto.entry_result = EntryResult(
            estado="fallo",
            codigo_motivo="credenciales_no_disponibles",
            evidencia_acotada="Credenciales ausentes en .env",
            numero_de_intentos=0,
        )
        return ResultadoIngreso(estado="ok", contexto=contexto)

    # Paso 3, 4, 5: Abrir canal y acceder con reintentos (config-driven)
    adapter = obtener_adaptador(ficha.fuente_id)

    return _ejecutar_ingreso_loop(contexto, adapter, ficha, credenciales)

def _resolver_headless() -> bool:
    """Modo headless del canal (lógica en navegación; usa SU carga)."""
    return resolver_headless(load())


def _resolver_perfil() -> str:
    """Carpeta de sesión persistente (delegado en navegación, D61)."""
    return resolver_perfil()


def _abrir_pagina(
    playwright_instance: Any, headless: bool
) -> tuple[Any, Any]:
    """Crea la ventana del canal sobre una instancia Playwright viva (D61).

    Delegado en `navegacion.abrir_canal_instancia`; `headless` se entrega
    explícito para respetar la resolución del propio nodo (parcheable).
    """
    canal, pagina = abrir_canal_instancia(playwright_instance, headless)
    return canal, pagina


def _ejecutar_ingreso_loop(
    contexto: RunContext,
    adapter: AdaptadorPlataforma,
    ficha: FichaFuente,
    credenciales: dict[str, str] | None,
) -> ResultadoIngreso:
    playwright_instance: Any = None
    browser: Any = None
    page: Any = None
    playwright_activo = False

    def _cerrar_canal() -> None:
        """Cierra page/browser del intento; el canal vuelve a abrirse al
        reintentar. No detiene la instancia Playwright (se reutiliza)."""
        nonlocal page, browser
        if page:
            page.close()
        if browser:
            browser.close()
        page = None
        browser = None

    def _cerrar_playwright_local() -> None:
        """Detiene la instancia Playwright solo si esta invocación la arrancó."""
        nonlocal playwright_instance, playwright_activo
        if playwright_activo:
            if playwright_instance:
                playwright_instance.stop()
            playwright_activo = False

    def _intento() -> EntryResult:
        nonlocal playwright_instance, browser, page, playwright_activo
        # No usar sync_playwright() con 'with': cierra el navegador al salir
        # del bloque. Se inicia manualmente para mantener la página abierta.
        if playwright_instance is None:
            playwright_instance = sync_playwright().start()
            playwright_activo = True

        headless = _resolver_headless()
        browser, page = _abrir_pagina(playwright_instance, headless)

        # Cast context.fuente_corriente to FichaFuente since we verified it's not
        # None in ejecutar_ingreso
        ficha_actual = contexto.fuente_corriente
        if ficha_actual is None:
            raise RuntimeError("Fuente corriente must be present")

        page.set_default_timeout(ficha_actual.timeout_segundos * 1000)

        # Llamada al adaptador que encapsula navegación + auth + criterio
        # enter_source ya hace page.goto y _autenticar
        return adapter.enter_source(
            page,
            ficha_actual,
            credenciales,
        )

    def _fallo_final(fe: BaseException, intentos: int) -> ResultadoIngreso:
        _cerrar_canal()
        _cerrar_playwright_local()
        error = cast(FlowError, fe)
        contexto.entry_result = EntryResult(
            estado="fallo",
            codigo_motivo=error.codigo_motivo,
            evidencia_acotada=acotar_evidencia(error.mensaje),
            numero_de_intentos=intentos,
        )
        contexto.id_sesion = None
        contexto.handle_sesion = None
        contexto.browser = None
        contexto.playwright_instance = None
        return ResultadoIngreso(estado="ok", contexto=contexto)

    def _error_interno(exc: Exception, intentos: int) -> ResultadoIngreso:
        _cerrar_canal()
        _cerrar_playwright_local()
        contexto.browser = None
        contexto.playwright_instance = None
        logger.error(f"ERR-09: Error interno en nodo ingreso: {exc}")
        return ResultadoIngreso(estado="error", codigo="ERR-09", descripcion=str(exc))

    res, _ = ejecutar_con_reintento(
        _intento,
        al_reintento=_cerrar_canal,
        al_fallo_final=_fallo_final,
        al_error_interno=_error_interno,
        contexto_log=contexto.id_corrida,
    )
    if isinstance(res, ResultadoIngreso):
        return res

    # Éxito: se conserva la sesión para los nodos siguientes
    contexto.id_sesion = generar_id("sesiones")
    contexto.handle_sesion = page
    contexto.browser = browser
    contexto.playwright_instance = playwright_instance
    contexto.entry_result = res
    playwright_activo = False
    _registrar_evento_ingreso_exitoso(contexto)
    return ResultadoIngreso(estado="ok", contexto=contexto)


def _registrar_evento_ingreso_exitoso(contexto: RunContext) -> None:
    """Writes the `ingreso_exitoso` success event (ficha contract, D30).

    Non-aborting; evidence is bounded (source and session id, never
    credentials — RN-08 of the sheet).
    """
    if contexto.id_sesion is None:
        return
    registrar_evento(
        id_corrida=contexto.id_corrida,
        tipo="suceso",
        codigo="ingreso_exitoso",
        evidencia=f"sesion={contexto.id_sesion}",
        fuente_id=(
            contexto.fuente_corriente.fuente_id if contexto.fuente_corriente else ""
        ),
        id_sesion=contexto.id_sesion,
    )



def _resolver_credenciales(ficha: FichaFuente) -> dict[str, str] | None:
    """Resolves the source credentials in a single config read.

    Returns ``None`` for public sources (no credentials needed) or when any
    declared reference is missing (the caller reports
    ``credenciales_no_disponibles``). Maps ``credenciales_referencia[0]`` →
    ``username``, ``[1]`` → ``password`` (MVP contract with the adapter);
    remaining refs are ignored.
    """
    if ficha.tipo_acceso != "con_autenticacion":
        return None
    env_vars = load().get("_env", {})
    valores = [env_vars.get(ref) for ref in ficha.credenciales_referencia]
    if not valores or not all(valores):
        return None
    return {
        "username": valores[0],
        "password": valores[1] if len(valores) > 1 else "",
    }


def ingreso_exitoso(contexto: RunContext) -> ResultadoIngreso:
    """
    Nodo: ¿El ingreso fue exitoso? (v1.0).
    Valida el resultado del ingreso y decide la bifurcación.
    """
    res = contexto.entry_result
    if res is None:
        logger.error(f"ERR-01: entry_result ausente en corrida {contexto.id_corrida}")
        return ResultadoIngreso(estado="error", codigo="ERR-01", descripcion="entry_result ausente")

    # Validación de consistencia (valores reales, no estructura: EntryResult
    # es un modelo Pydantic cuyos atributos siempre existen)
    if res.estado not in ("exito", "fallo"):
        logger.error(
            f"ERR-02: estructura de entry_result inválida en corrida {contexto.id_corrida}"
        )
        return ResultadoIngreso(
            estado="error", codigo="ERR-02", descripcion="Estructura EntryResult inválida"
        )

    if res.estado == "exito":
        if contexto.id_sesion is None or contexto.handle_sesion is None:
            logger.error(
                f"ERR-02: Éxito de ingreso sin sesión activa en corrida {contexto.id_corrida}"
            )
            return ResultadoIngreso(
                estado="error", codigo="ERR-02", descripcion="Éxito sin sesión activa"
            )

    decision = "si" if res.estado == "exito" else "no"
    return ResultadoIngreso(estado="ok", decision=decision, contexto=contexto)

