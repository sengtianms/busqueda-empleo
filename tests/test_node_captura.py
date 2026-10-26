from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from modules.discovery.adapters.linkedin import FlowError
from modules.discovery.nodes.captura import (
    _escribir_auditoria_sesion,
    capturar_ofertas,
    quedan_sets_por_aplicar,
    registrar_ofertas,
)
from modules.discovery.run_context import RunContext
from shared.models import CaptureBatch, EstadoCaptura, Offer, SetFiltros
from shared.persistence import leer_tabla


def _run_context(sets: int = 1) -> RunContext:
    config_fuentes = [
        {
            "fuente_id": "LI-01",
            "nombre": "LinkedIn",
            "ficha_acceso": {
                "enlace": "https://www.linkedin.com/jobs",
                "tipo_acceso": "publico",
                "criterio_exito": "global-nav",
                "timeout_segundos": 10,
            },
            "sets_de_filtros": [
                {"indice_set": i, "filtros": []} for i in range(sets)
            ],
        }
    ]
    contexto = RunContext(config_fuentes=config_fuentes)
    contexto.fuente_corriente = contexto.fuentes_filtradas[0]
    return contexto


def _oferta(enlace: str = "https://www.linkedin.com/jobs/view/123") -> Offer:
    return Offer(
        enlace=enlace,
        titulo="Desarrollador Python",
        descripcion_original="Descripcion de la vacante.",
        fuente_id="LI-01",
        indice_set=0,
        id_externo="123",
    )


@pytest.fixture
def contexto() -> RunContext:
    return _run_context()


@pytest.fixture
def adapter() -> Generator[MagicMock, None, None]:
    with patch("modules.discovery.nodes.captura.obtener_adaptador") as mock:
        yield mock.return_value


def test_captura_exitosa_guarda_resultados(
    contexto: RunContext, adapter: MagicMock
) -> None:
    contexto.handle_sesion = MagicMock()
    contexto.set_corriente = SetFiltros(fuente_id="LI-01", indice=0, filtros=[])
    lote = CaptureBatch(
        ofertas=[_oferta()],
        id_corrida=contexto.id_corrida,
        fuente_id="LI-01",
        id_sesion="SES-1",
        indice_set=0,
        paginas_consumidas=2,
    )
    estado = EstadoCaptura(
        estado="exito",
        paginas_consumidas=2,
        capturadas_acumuladas_fuente=1,
        limite_alcanzado=False,
    )
    adapter.capture_batch.return_value = (lote, estado)

    res = capturar_ofertas(contexto)

    assert res.estado == "ok"
    assert contexto.capture_batch is lote
    assert contexto.estado_captura is estado


def test_captura_handle_ausente(contexto: RunContext) -> None:
    contexto.handle_sesion = None
    res = capturar_ofertas(contexto)
    assert res.estado == "error"
    assert res.codigo == "ERR-01"


def test_captura_fuente_ausente(contexto: RunContext) -> None:
    contexto.fuente_corriente = None
    contexto.handle_sesion = MagicMock()

    res = capturar_ofertas(contexto)
    assert res.estado == "error"
    assert res.codigo == "ERR-01"


def test_captura_set_ausente(contexto: RunContext) -> None:
    contexto.handle_sesion = MagicMock()
    contexto.set_corriente = None

    res = capturar_ofertas(contexto)
    assert res.estado == "error"
    assert res.codigo == "ERR-01"


def test_captura_reintento_timeout_exito(
    contexto: RunContext, adapter: MagicMock
) -> None:
    contexto.handle_sesion = MagicMock()
    contexto.set_corriente = SetFiltros(fuente_id="LI-01", indice=0, filtros=[])
    lote = CaptureBatch(ofertas=[_oferta()], indice_set=0)
    estado = EstadoCaptura(estado="exito", capturadas_acumuladas_fuente=1)
    adapter.capture_batch.side_effect = [
        FlowError("tiempo_agotado_captura", "Page timeout"),
        (lote, estado),
    ]

    with patch("shared.retry.time.sleep"):
        res = capturar_ofertas(contexto)

    assert res.estado == "ok"
    assert contexto.estado_captura is estado
    assert adapter.capture_batch.call_count == 2


def test_captura_timeout_todos_intentos(contexto: RunContext, adapter: MagicMock) -> None:
    contexto.handle_sesion = MagicMock()
    contexto.set_corriente = SetFiltros(fuente_id="LI-01", indice=0, filtros=[])
    adapter.capture_batch.side_effect = FlowError("tiempo_agotado_captura", "Timeout")

    with patch("shared.retry.time.sleep"):
        with patch("modules.discovery.nodes.captura.registrar_evento"):
            res = capturar_ofertas(contexto)

    assert res.estado == "ok"
    assert contexto.estado_captura is not None
    assert contexto.estado_captura.estado == "fallo"
    assert contexto.estado_captura.codigo_motivo == "tiempo_agotado_captura"
    assert contexto.capture_batch is None
    assert adapter.capture_batch.call_count == 3


def test_captura_bloqueo_inmediato(contexto: RunContext, adapter: MagicMock) -> None:
    contexto.handle_sesion = MagicMock()
    contexto.set_corriente = SetFiltros(fuente_id="LI-01", indice=0, filtros=[])
    adapter.capture_batch.side_effect = FlowError("bloqueo_plataforma", "Captcha")

    with patch("modules.discovery.nodes.captura.registrar_evento"):
        res = capturar_ofertas(contexto)

    assert res.estado == "ok"
    assert contexto.estado_captura is not None
    assert contexto.estado_captura.estado == "fallo"
    assert contexto.estado_captura.codigo_motivo == "bloqueo_plataforma"
    assert adapter.capture_batch.call_count == 1


def test_captura_sesion_expirada_inmediato(
    contexto: RunContext, adapter: MagicMock
) -> None:
    contexto.handle_sesion = MagicMock()
    contexto.set_corriente = SetFiltros(fuente_id="LI-01", indice=0, filtros=[])
    adapter.capture_batch.side_effect = FlowError("sesion_expirada", "Authwall")

    with patch("modules.discovery.nodes.captura.registrar_evento"):
        res = capturar_ofertas(contexto)

    assert res.estado == "ok"
    assert contexto.estado_captura is not None
    assert contexto.estado_captura.estado == "fallo"
    assert contexto.estado_captura.codigo_motivo == "sesion_expirada"
    assert adapter.capture_batch.call_count == 1


def test_captura_auditoria_sesion_escrita(
    contexto: RunContext, adapter: MagicMock
) -> None:
    contexto.handle_sesion = MagicMock()
    contexto.id_sesion = "SES-1"
    contexto.set_corriente = SetFiltros(fuente_id="LI-01", indice=0, filtros=[])
    lote = CaptureBatch(
        ofertas=[_oferta()], indice_set=0, fuente_id="LI-01"
    )
    estado = EstadoCaptura(estado="exito")
    adapter.capture_batch.return_value = (lote, estado)

    with patch("modules.discovery.nodes.captura.escribir_fila") as mock_write_row:
        res = capturar_ofertas(contexto)

    assert res.estado == "ok"
    mock_write_row.assert_called_once()
    args = mock_write_row.call_args.args
    assert args[0] == "sesiones"
    assert "id" not in args[1]
    assert args[1]["id_sesion"] == "SES-1"
    assert args[1]["conteo"] == 1
    assert args[1]["estado"] == "completa"


def test_auditoria_sesion_una_fila_por_set(contexto: RunContext) -> None:
    contexto.id_sesion = "SES-1"

    for indice in (0, 1):
        _escribir_auditoria_sesion(
            contexto,
            CaptureBatch(
                ofertas=[_oferta()],
                id_corrida=contexto.id_corrida,
                fuente_id="LI-01",
                id_sesion="SES-1",
                indice_set=indice,
            ),
        )

    filas = leer_tabla("sesiones", {"id_sesion": "SES-1"})

    assert len(filas) == 2
    assert sorted(fila["indice_set"] for fila in filas) == [0, 1]
    assert {fila["id_sesion"] for fila in filas} == {"SES-1"}
    assert len({fila["id"] for fila in filas}) == 2
    assert all(fila["id"].startswith("SES-") for fila in filas)
    assert all(fila["id"] != "SES-1" for fila in filas)


def test_auditoria_sesion_reentrada_no_duplica(contexto: RunContext) -> None:
    contexto.id_sesion = "SES-1"
    lote_1 = CaptureBatch(
        ofertas=[_oferta()],
        id_corrida=contexto.id_corrida,
        fuente_id="LI-01",
        id_sesion="SES-1",
        indice_set=0,
    )
    lote_2 = CaptureBatch(
        ofertas=[_oferta(), _oferta()],
        id_corrida=contexto.id_corrida,
        fuente_id="LI-01",
        id_sesion="SES-1",
        indice_set=0,
    )

    _escribir_auditoria_sesion(contexto, lote_1)
    _escribir_auditoria_sesion(contexto, lote_2)

    filas = leer_tabla("sesiones", {"id_sesion": "SES-1"})

    assert len(filas) == 1
    assert filas[0]["indice_set"] == 0
    assert filas[0]["conteo"] == 2


def test_captura_auditoria_falla_no_aborta(
    contexto: RunContext, adapter: MagicMock
) -> None:
    contexto.handle_sesion = MagicMock()
    contexto.set_corriente = SetFiltros(fuente_id="LI-01", indice=0, filtros=[])
    lote = CaptureBatch(ofertas=[_oferta()], indice_set=0)
    estado = EstadoCaptura(estado="exito")
    adapter.capture_batch.return_value = (lote, estado)

    with patch(
        "modules.discovery.nodes.captura.escribir_fila", side_effect=RuntimeError("db")
    ) as mock_write_row:
        with patch("modules.discovery.nodes.captura.logger"):
            res = capturar_ofertas(contexto)

    assert res.estado == "ok"
    assert contexto.estado_captura is estado
    assert mock_write_row.call_count == 2


def test_captura_exito_evidencia_con_duracion(
    contexto: RunContext, adapter: MagicMock
) -> None:
    """D30: la evidencia de `captura_completada` incluye la duración en segundos."""
    contexto.handle_sesion = MagicMock()
    contexto.set_corriente = SetFiltros(fuente_id="LI-01", indice=0, filtros=[])
    lote = CaptureBatch(ofertas=[_oferta()], indice_set=0)
    estado = EstadoCaptura(estado="exito", paginas_consumidas=2)
    adapter.capture_batch.return_value = (lote, estado)

    with patch("modules.discovery.nodes.captura.registrar_evento") as mock_evento:
        res = capturar_ofertas(contexto)

    assert res.estado == "ok"
    evento = mock_evento.call_args.kwargs
    assert evento["codigo"] == "captura_completada"
    assert evento["evidencia"].startswith("páginas=2 | ofertas=1 | duracion_s=")
    assert evento["evidencia"].split("duracion_s=")[1].isdigit()


def test_registrar_una_oferta_upsert(
    contexto: RunContext,
) -> None:
    contexto.id_sesion = "SES-1"
    contexto.capture_batch = CaptureBatch(ofertas=[_oferta()], indice_set=0)

    with patch(
        "modules.discovery.nodes.captura.upsert_lote_ofertas",
        return_value=(1, 0),
    ) as mock_upsert:
        with patch("modules.discovery.nodes.captura.registrar_evento"):
            res = registrar_ofertas(contexto)

    assert res.estado == "ok"
    mock_upsert.assert_called_once()
    filas = mock_upsert.call_args.args[0]
    assert len(filas) == 1
    fila = filas[0]
    assert fila["titulo"] == "Desarrollador Python"
    assert fila["fuente_id"] == "LI-01"
    assert fila["id_externo"] == "123"
    assert fila["id_corrida"] == contexto.id_corrida


def test_registrar_oferta_persiste_empresa_de_tarjeta_d41(
    contexto: RunContext,
) -> None:
    contexto.id_sesion = "SES-1"
    oferta = _oferta()
    oferta.empresa = "CI&T S.A."
    contexto.capture_batch = CaptureBatch(ofertas=[oferta], indice_set=0)

    with patch(
        "modules.discovery.nodes.captura.upsert_lote_ofertas",
        return_value=(1, 0),
    ) as mock_upsert:
        with patch("modules.discovery.nodes.captura.registrar_evento"):
            res = registrar_ofertas(contexto)

    assert res.estado == "ok"
    fila = mock_upsert.call_args.args[0][0]
    assert fila["empresa"] == "CI&T S.A."


def test_registrar_lote_vacio(contexto: RunContext) -> None:
    contexto.capture_batch = CaptureBatch(ofertas=[], indice_set=0)

    with patch("modules.discovery.nodes.captura.upsert_lote_ofertas") as mock_upsert:
        res = registrar_ofertas(contexto)

    assert res.estado == "ok"
    mock_upsert.assert_not_called()


def test_registrar_sin_lote(contexto: RunContext) -> None:
    contexto.capture_batch = None

    with patch("modules.discovery.nodes.captura.upsert_lote_ofertas") as mock_upsert:
        res = registrar_ofertas(contexto)

    assert res.estado == "ok"
    mock_upsert.assert_not_called()


def test_registrar_dedup_id_externo(contexto: RunContext) -> None:
    contexto.capture_batch = CaptureBatch(ofertas=[_oferta()], indice_set=0)

    with patch(
        "modules.discovery.nodes.captura.upsert_lote_ofertas",
        return_value=(1, 0),
    ) as mock_upsert:
        registrar_ofertas(contexto)

    fila = mock_upsert.call_args.args[0][0]
    assert fila["id_externo"] == "123"


def test_registrar_ofertas_exito_registra_suceso(
    contexto: RunContext,
) -> None:
    contexto.id_sesion = "SES-9"
    contexto.fuente_corriente = _run_context().fuentes_filtradas[0]
    oferta_a = _oferta("https://www.linkedin.com/jobs/view/11")
    oferta_b = _oferta("https://www.linkedin.com/jobs/view/22")
    contexto.capture_batch = CaptureBatch(
        ofertas=[oferta_a, oferta_b], indice_set=0
    )
    contexto.set_corriente = SetFiltros(fuente_id="LI-01", indice=0, filtros=[])

    with patch(
        "modules.discovery.nodes.captura.upsert_lote_ofertas",
        return_value=(2, 0),
    ) as mock_upsert:
        with patch("modules.discovery.nodes.captura.registrar_evento") as mock_evento:
            res = registrar_ofertas(contexto)

    assert res.estado == "ok"
    mock_upsert.assert_called_once()
    assert len(mock_upsert.call_args.args[0]) == 2
    mock_evento.assert_called_once()
    evento = mock_evento.call_args.kwargs
    assert evento["tipo"] == "suceso"
    assert evento["codigo"] == "ofertas_registradas"
    assert evento["evidencia"] == "ofertas registradas: 2 | total: 2"
    assert evento["id_corrida"] == contexto.id_corrida
    assert evento["id_sesion"] == "SES-9"
    assert evento["fuente_id"] == "LI-01"


def test_registrar_fallo_parcial(contexto: RunContext) -> None:
    oferta_a = _oferta("https://www.linkedin.com/jobs/view/1")
    oferta_b = _oferta("https://www.linkedin.com/jobs/view/2")
    contexto.capture_batch = CaptureBatch(ofertas=[oferta_a, oferta_b], indice_set=0)

    with patch(
        "modules.discovery.nodes.captura.upsert_lote_ofertas",
        side_effect=[RuntimeError("db"), (1, 1)],
    ) as mock_upsert:
        with patch("modules.discovery.nodes.captura.registrar_evento") as mock_evento:
            with patch("modules.discovery.nodes.captura.logger"):
                res = registrar_ofertas(contexto)

    assert res.estado == "ok"
    assert mock_upsert.call_count == 2
    assert mock_evento.call_count == 2
    assert mock_evento.call_args_list[0].kwargs["codigo"] == "ofertas_registradas"
    assert mock_evento.call_args_list[1].kwargs["codigo"] == "registro_parcial"


def test_registrar_fallo_total(contexto: RunContext) -> None:
    oferta_a = _oferta("https://www.linkedin.com/jobs/view/1")
    oferta_b = _oferta("https://www.linkedin.com/jobs/view/2")
    contexto.capture_batch = CaptureBatch(ofertas=[oferta_a, oferta_b], indice_set=0)

    with patch(
        "modules.discovery.nodes.captura.upsert_lote_ofertas",
        side_effect=RuntimeError("db"),
    ) as mock_upsert:
        with patch("modules.discovery.nodes.captura.registrar_evento") as mock_evento:
            with patch("modules.discovery.nodes.captura.logger"):
                res = registrar_ofertas(contexto)

    assert res.estado == "ok"
    assert mock_upsert.call_count == 2
    mock_evento.assert_called_once()
    assert mock_evento.call_args.kwargs["codigo"] == "lote_degradado"


def test_quedan_sets_si() -> None:
    contexto = _run_context(sets=3)
    contexto.iterador_sets["LI-01"] = 0
    res = quedan_sets_por_aplicar(contexto)
    assert res.estado == "ok"
    assert res.decision == "si"


def test_quedan_sets_no() -> None:
    contexto = _run_context(sets=3)
    contexto.iterador_sets["LI-01"] = 2
    res = quedan_sets_por_aplicar(contexto)
    assert res.estado == "ok"
    assert res.decision == "no"


def test_quedan_sets_fuente_ausente(contexto: RunContext) -> None:
    contexto.fuente_corriente = None
    res = quedan_sets_por_aplicar(contexto)
    assert res.estado == "error"
    assert res.codigo == "ERR-01"


# ==== D61: resiliencia del navegador en la captura ======================== #

_MUERTE_NAVEGADOR = Exception("Page.goto: Batch navigation failed: Target crashed")


def _run_context_resiliencia(
    renovar: int = 30,
    tope_muertes: int = 3,
) -> RunContext:
    base = RunContext(
        config_fuentes=[
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
        ],
        config_captura={
            "max_paginas": 5,
            "max_ofertas_por_corrida": 10,
            "pausa_entre_lotes_segundos": 0,
            "estrategia_anti_bloqueo": "none",
        },
        config_descubrimiento={
            "renovar_navegador_tras_paginas": renovar,
            "tope_muertes_sin_avance": tope_muertes,
        },
    )
    base.fuente_corriente = base.fuentes_filtradas[0]
    return base


def _lote(oferta_id: str, indice_set: int = 0) -> CaptureBatch:
    return CaptureBatch(
        ofertas=[_oferta(f"https://www.linkedin.com/jobs/view/{oferta_id}")],
        indice_set=indice_set,
        paginas_consumidas=1,
    )


def _estado_tramo(
    desplazamiento: int,
    hay_mas: bool,
) -> EstadoCaptura:
    return EstadoCaptura(
        estado="ok",
        paginas_consumidas=1,
        capturadas_acumuladas_fuente=1,
        limite_alcanzado=False,
        desplazamiento_final=desplazamiento,
        hay_mas_ofertas=hay_mas,
    )


@contextmanager
def _canal_resiliente(
    efecto_reabrir: bool = True,
) -> Generator[MagicMock, None, None]:
    """Aisla el canal: reabrir simulado y sin esperas de reintento."""
    with (
        patch(
            "modules.discovery.nodes.captura.reabrir_navegador",
            return_value=efecto_reabrir,
        ) as mock_reabrir,
        patch("shared.retry.time.sleep"),
    ):
        yield mock_reabrir


def _preparar_set(contexto: RunContext) -> None:
    contexto.handle_sesion = MagicMock()
    contexto.set_corriente = SetFiltros(fuente_id="LI-01", indice=0, filtros=[])


def test_captura_reanuda_tras_muerte_navegador() -> None:
    """D61: muerte del canal → reconstrucción → reanudación en su paginación.

    La búsqueda camina la página 1 (tramo aprobado) y muere caminando la
    página 2; al volver del reconstructor, la paginación retoma EXACTA en
    donde murió (```?start=20```), sin repetir lo ya caminado.
    """
    contexto = _run_context_resiliencia()
    _preparar_set(contexto)
    lote_a = _lote("A")
    estado_a = _estado_tramo(desplazamiento=20, hay_mas=True)
    lote_c = _lote("C")
    estado_c = _estado_tramo(desplazamiento=40, hay_mas=False)
    adapter = MagicMock()
    adapter.capture_batch.side_effect = [
        (lote_a, estado_a),
        _MUERTE_NAVEGADOR,
        (lote_c, estado_c),
    ]

    with (
        patch("modules.discovery.nodes.captura.obtener_adaptador", return_value=adapter),
        _canal_resiliente() as mock_reabrir,
    ):
        res = capturar_ofertas(contexto)

    assert res.estado == "ok"
    assert mock_reabrir.call_count == 1
    assert adapter.capture_batch.call_count == 3
    primera, segunda, tercera = adapter.capture_batch.call_args_list
    assert primera.kwargs["desde_desplazamiento"] == 0
    assert segunda.kwargs["desde_desplazamiento"] == 20  # página 2 del tramo
    assert tercera.kwargs["desde_desplazamiento"] == 20  # reanuda EXACTA
    # Dos tramos aprobados se agregan: la página que murió se recamina.
    assert contexto.capture_batch is not None
    assert len(contexto.capture_batch.ofertas) == 2
    assert contexto.capture_batch.paginas_consumidas == 2
    assert contexto.muertes_sin_avance == 0  # el progreso perdona


def test_captura_muertes_consecutivas_sin_avance_abortan() -> None:
    """D61: entorno roto (muertes sin NINGUNA página de avance) → cierre honesto."""
    contexto = _run_context_resiliencia(tope_muertes=1)
    _preparar_set(contexto)
    adapter = MagicMock()
    adapter.capture_batch.side_effect = [_MUERTE_NAVEGADOR, _MUERTE_NAVEGADOR]

    with (
        patch("modules.discovery.nodes.captura.obtener_adaptador", return_value=adapter),
        _canal_resiliente() as mock_reabrir,
    ):
        res = capturar_ofertas(contexto)

    assert res.estado == "error"
    assert res.codigo == "ERR-09"
    assert mock_reabrir.call_count == 1  # primera muerte: reapertura; segunda: fin
    assert contexto.capture_batch is None


def test_captura_reabrir_fallido_cierra_honesto() -> None:
    """D61: la reconstrucción falla (p. ej. ventana manual vencida) → ERR-09."""
    contexto = _run_context_resiliencia()
    _preparar_set(contexto)
    adapter = MagicMock()
    adapter.capture_batch.side_effect = [_MUERTE_NAVEGADOR]

    with (
        patch("modules.discovery.nodes.captura.obtener_adaptador", return_value=adapter),
        _canal_resiliente(efecto_reabrir=False),
    ):
        res = capturar_ofertas(contexto)

    assert res.estado == "error"
    assert res.codigo == "ERR-09"
    assert contexto.capture_batch is None


def test_captura_renovacion_programada_divide_tramos() -> None:
    """D61: al alcanzar el umbral de páginas, el canal se renueva en la frontera."""
    contexto = _run_context_resiliencia(renovar=1)
    _preparar_set(contexto)
    lote_a = _lote("A")
    estado_a = _estado_tramo(desplazamiento=20, hay_mas=True)
    lote_b = _lote("B")
    estado_b = _estado_tramo(desplazamiento=40, hay_mas=False)
    adapter = MagicMock()
    adapter.capture_batch.side_effect = [(lote_a, estado_a), (lote_b, estado_b)]
    renovaciones: list[RunContext] = []

    def _renovar(ctx: RunContext) -> bool:
        ctx.paginas_desde_renovacion = 0
        renovaciones.append(ctx)
        return True

    with (
        patch("modules.discovery.nodes.captura.obtener_adaptador", return_value=adapter),
        patch("shared.retry.time.sleep"),
        patch("modules.discovery.nodes.captura.renovar_si_toca", side_effect=_renovar),
    ):
        res = capturar_ofertas(contexto)

    assert res.estado == "ok"
    assert len(renovaciones) == 1
    primera, segunda = adapter.capture_batch.call_args_list
    assert primera.kwargs["desde_desplazamiento"] == 0
    assert segunda.kwargs["desde_desplazamiento"] == 20
    # Dos tramos se agregan en un lote único con el avance total.
    assert contexto.capture_batch is not None
    assert len(contexto.capture_batch.ofertas) == 2
    assert contexto.capture_batch.paginas_consumidas == 2
    assert contexto.estado_captura is not None
    assert contexto.estado_captura.hay_mas_ofertas is False


def test_captura_insostenible_guarda_de_frente() -> None:
    """D61: el canal declarado insostenible no reintentela captura."""
    contexto = _run_context_resiliencia()
    contexto.navegador_insostenible = True
    res = capturar_ofertas(contexto)
    assert res.estado == "error"
    assert res.codigo == "ERR-09"


def test_captura_muertes_pendientes_frenan_hoy() -> None:
    """D61: muertes acumuladas sin avance exceden el tope → freno inmediato."""
    contexto = _run_context_resiliencia()
    _preparar_set(contexto)
    contexto.muertes_sin_avance = 4  # tope 3
    adapter = MagicMock()
    with (
        patch("modules.discovery.nodes.captura.obtener_adaptador", return_value=adapter),
        patch("shared.retry.time.sleep"),
    ):
        res = capturar_ofertas(contexto)
    assert res.estado == "error"
    assert res.codigo == "ERR-09"
    assert adapter.capture_batch.call_count == 0
