"""Pruebas de la navegación resiliente del Módulo 1 (D61, 2026-10-22).

Cubre el chaleco antibloqueo: detección de muerte del navegador (señales
directas y por cadena de causas), matador del árbol de procesos, reconstrucción
del canal con memoria de sesión, renovación por tramos y el latido (techo
absoluto por operación). Todo sin navegador real: sustitutos y parches.
"""

import time
from typing import Any
from unittest.mock import MagicMock, patch

from modules.discovery import navegacion
from modules.discovery.navegacion import (
    LatidoNavegador,
    es_muerte_navegador,
    matar_arbol_navegador,
    reabrir_navegador,
    renovar_si_toca,
    techo_por_aplicacion,
    techo_por_paginas,
)
from modules.discovery.run_context import RunContext
from shared.models import EntryResult, PoliticasCaptura

_CONFIG_FUENTE = [
    {
        "fuente_id": "LI-01",
        "nombre": "LinkedIn",
        "ficha_acceso": {
            "enlace": "https://www.linkedin.com/jobs",
            "tipo_acceso": "publico",
            "criterio_exito": "global-nav",
            "timeout_segundos": 10,
        },
        "sets_de_filtros": [{"indice_set": 0, "filtros": []}],
    }
]


def _contexto() -> RunContext:
    contexto = RunContext(config_fuentes=_CONFIG_FUENTE)
    contexto.fuente_corriente = contexto.fuentes_filtradas[0]
    contexto.id_sesion = "SES-1"
    return contexto


# ==== detección de muerte ================================================= #

def test_es_muerte_navegador_senales_directas() -> None:
    for mensaje in (
        "Page.goto: Target crashed",
        "Page crashed while executing",
        "Target closed after browser exit",
        "Playwright connection closed",
        "browser has been closed",
        "Target page, context or browser has been closed",
    ):
        assert es_muerte_navegador(Exception(mensaje)), mensaje


def test_es_muerte_navegador_por_cadena_de_causas() -> None:
    """El adaptador envuelve el fallo del navegador en FlowError con causa."""
    base = Exception("Page.goto: Target page crashed")
    envuelto: Any = None
    try:
        raise base
    except Exception as exc:
        try:
            raise RuntimeError("wrapper sin señal") from exc
        except RuntimeError as envoltorio:
            envuelto = envoltorio
    assert es_muerte_navegador(envuelto)


def test_es_muerte_navegador_no_confunde_bloqueos_de_plataforma() -> None:
    """La muralla de la plataforma no es muerte del canal (D61)."""
    assert not es_muerte_navegador(Exception("Authwall detected."))
    assert not es_muerte_navegador(Exception("Captcha/challenge evidence."))
    assert not es_muerte_navegador(Exception("criterio de ingreso no cumplido"))
    assert not es_muerte_navegador(RuntimeError("pagina vacia"))


# ==== matador del árbol ================================================== #

def test_matar_arbol_usa_el_patron_del_perfil() -> None:
    with (
        patch.object(navegacion, "resolver_perfil", return_value="data/browser_profile"),
        patch("modules.discovery.navegacion.subprocess.run") as ejecutar,
    ):
        matar_arbol_navegador()

    args = ejecutar.call_args.args
    assert args[0][:5] == [
        "pkill",
        "-9",
        "-f",
        "--",
        "--user-data-dir=.*data/browser_profile",
    ]
    assert ejecutar.call_args.kwargs["check"] is False


def test_matar_arbol_sin_perfil_apunta_a_playwright() -> None:
    with (
        patch.object(navegacion, "resolver_perfil", return_value=""),
        patch("modules.discovery.navegacion.subprocess.run") as ejecutar,
    ):
        matar_arbol_navegador()

    assert ejecutar.call_args.args[0][4] == "ms-playwright"


def test_matar_arbol_sobrevive_fallo_pkill() -> None:
    with (
        patch("modules.discovery.navegacion.subprocess.run", side_effect=RuntimeError("sin pkill")),
        patch.object(navegacion, "resolver_perfil", return_value=""),
    ):
        matar_arbol_navegador()  # no lanza


# ==== reconstrucción del canal =========================================== #

@patch("modules.discovery.navegacion.cerrar_recursos")
@patch("modules.discovery.navegacion.matar_arbol_navegador")
@patch("modules.discovery.navegacion.registrar_evento")
@patch("modules.discovery.navegacion.obtener_adaptador")
@patch("modules.discovery.navegacion.abrir_canal")
def test_reabrir_navegador_exitoso_actualiza_el_canal(
    abrir: MagicMock,
    adaptador: MagicMock,
    evento: MagicMock,
    _matador: MagicMock,
    _cortesia: MagicMock,
) -> None:
    contexto = _contexto()
    instancia, canal, pagina = MagicMock(), MagicMock(), MagicMock()
    abrir.return_value = (instancia, canal, pagina)
    adaptador.return_value.enter_source.return_value = EntryResult(
        estado="exito", evidencia_acotada="criterio", numero_de_intentos=1
    )

    resultado = reabrir_navegador(contexto, "colapso")

    assert resultado is True
    assert contexto.playwright_instance is instancia
    assert contexto.browser is canal
    assert contexto.handle_sesion is pagina
    assert contexto.id_sesion == "SES-1"  # la sesión lógica no cambia
    assert contexto.navegador_insostenible is False
    assert evento.call_args.kwargs["codigo"] == "navegador_renovado"
    assert evento.call_args.kwargs["tipo"] == "suceso"
    assert "motivo=colapso" in evento.call_args.kwargs["evidencia"]
    adaptador.return_value.enter_source.assert_called_once()


@patch("modules.discovery.navegacion.registrar_evento")
@patch("modules.discovery.navegacion.obtener_adaptador")
def test_reabrir_fallo_de_apertura_deja_insostenible(
    adaptador: MagicMock,
    evento: MagicMock,
) -> None:
    contexto = _contexto()
    with patch(
        "modules.discovery.navegacion.abrir_canal",
        side_effect=RuntimeError("sin navegador"),
    ):
        resultado = reabrir_navegador(contexto, "colapso")

    assert resultado is False
    assert contexto.navegador_insostenible is True
    evento.assert_not_called()


@patch("modules.discovery.navegacion.registrar_evento")
@patch("modules.discovery.navegacion.obtener_adaptador")
@patch("modules.discovery.navegacion.abrir_canal")
def test_reabrir_fallo_de_reingreso_descarta_el_canal(
    abrir: MagicMock,
    adaptador: MagicMock,
    evento: MagicMock,
) -> None:
    contexto = _contexto()
    instancia, canal, pagina = MagicMock(), MagicMock(), MagicMock()
    instancia.stop = MagicMock()
    abrir.return_value = (instancia, canal, pagina)
    adaptador.return_value.enter_source.side_effect = Exception(
        "Target closed: the channel died"
    )

    resultado = reabrir_navegador(contexto, "colapso")

    assert resultado is False
    assert contexto.navegador_insostenible is True
    instancia.stop.assert_called_once()
    evento.assert_not_called()


@patch("modules.discovery.navegacion.registrar_evento")
@patch("modules.discovery.navegacion.obtener_adaptador")
@patch("modules.discovery.navegacion.abrir_canal")
def test_reabrir_reingreso_sin_criterio_deja_insostenible(
    abrir: MagicMock,
    adaptador: MagicMock,
    evento: MagicMock,
) -> None:
    contexto = _contexto()
    instancia, canal, pagina = MagicMock(), MagicMock(), MagicMock()
    abrir.return_value = (instancia, canal, pagina)
    adaptador.return_value.enter_source.return_value = EntryResult(
        estado="fallo",
        codigo_motivo="criterio_no_cumplido",
        evidencia_acotada="manual no completado",
        numero_de_intentos=2,
    )

    resultado = reabrir_navegador(contexto, "renovacion_programada")

    assert resultado is False
    assert contexto.navegador_insostenible is True
    evento.assert_not_called()


# ==== renovación preventiva =============================================== #

@patch("modules.discovery.navegacion.reabrir_navegador", return_value=True)
def test_renovar_si_toca_bajo_umbral_no_toca(reabrir: MagicMock) -> None:
    contexto = _contexto()
    contexto.paginas_desde_renovacion = 5

    assert renovar_si_toca(contexto) is True
    reabrir.assert_not_called()
    assert contexto.paginas_desde_renovacion == 5


@patch("modules.discovery.navegacion.reabrir_navegador", return_value=True)
def test_renovar_si_toca_al_umbral_reconstruye(reabrir: MagicMock) -> None:
    contexto = _contexto()
    contexto.paginas_desde_renovacion = contexto.renovar_navegador_tras_paginas

    assert renovar_si_toca(contexto) is True
    reabrir.assert_called_once()
    assert contexto.paginas_desde_renovacion == 0


def test_renovar_si_toca_con_fallo_no_resetea() -> None:
    contexto = _contexto()
    contexto.paginas_desde_renovacion = 30

    def _reabrir_fallido(ctx: RunContext, motivo: str) -> bool:
        ctx.navegador_insostenible = True
        return False

    with patch("modules.discovery.navegacion.reabrir_navegador", side_effect=_reabrir_fallido):
        assert renovar_si_toca(contexto) is False
    assert contexto.paginas_desde_renovacion == 30
    assert contexto.navegador_insostenible is True


# ==== techos de latido ==================================================== #

def test_techo_por_paginas_escala_con_el_tramo() -> None:
    politicas = PoliticasCaptura(
        max_paginas=5,
        max_ofertas_por_corrida=25,
        pausa_entre_lotes_segundos=10,
        tope_espera_paginas_sucesivas_segundos=10,
    )
    uno = techo_por_paginas(30, politicas, 1)
    treinta = techo_por_paginas(30, politicas, 30)
    # Por página legítima: 30 (navegación) + 10 (espera) + 15 (pausa) = 55 s.
    assert uno == 55.0 + 60.0
    assert treinta == 55.0 * 30 + 60.0
    assert treinta > uno


def test_techo_por_aplicacion_incluye_fallback_ui() -> None:
    assert techo_por_aplicacion(30) == 30 * 4 + 60.0
    assert techo_por_aplicacion(0) == 60.0 + 4 * 1


# ==== latido ============================================================== #

def test_latido_mata_cuando_el_techo_vence() -> None:
    latido = LatidoNavegador()
    muertos: list[int] = []
    with latido._candado:
        latido._limite = time.monotonic() - 1.0
        latido._matador = lambda: muertos.append(1)

    latido._revisar()

    assert muertos == [1]
    with latido._candado:
        assert latido._limite == 0.0
        assert latido._matador is None


def test_latido_no_dispara_con_techo_vigente() -> None:
    latido = LatidoNavegador()
    muertos: list[int] = []
    with latido._candado:
        latido._limite = time.monotonic() + 100.0
        latido._matador = lambda: muertos.append(1)

    latido._revisar()

    assert muertos == []
    with latido._candado:
        assert latido._limite > 0.0


def test_latido_sin_operacion_no_hace_nada() -> None:
    latido = LatidoNavegador()
    muertos: list[int] = []
    with latido._candado:
        latido._matador = lambda: muertos.append(1)
        latido._limite = 0.0

    latido._revisar()

    assert muertos == []


def test_latido_singleton_es_unico() -> None:
    assert navegacion.latido() is navegacion.latido()
