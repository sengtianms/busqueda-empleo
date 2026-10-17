"""Integration tests for the transversal orchestrator (sub-phase 5.6).

Real scheduled-run node over a temporary SQLite database, following the
integration strategy of `tests/test_orquestador_integracion.py` and
`tests/test_orquestador_flujo_m2.py`: the module registry is replaced with
simulated modules (closures that register and close their own `corridas`
rows), plus one test wiring the REAL Preparation flow (HTTP capture and
location AI mocked at the module boundary). Covers the happy path, module
failure without stopping the run (RN-04), `no_iniciada`, config validation
(ERR-01: missing/corrupt section, `paralelo`, unknown module, bad pause),
ERR-02 run creation failure, attribution isolation between consecutive
modules, pre-existing runs outside the window, best-effort summary events
(ERR-04) and back-to-back scheduled runs.
"""

from typing import Any

import pytest

import modules.orchestrator.orchestrator as orquestador_mod
import modules.preparation.nodes.preparacion as preparacion_mod
from modules.orchestrator.orchestrator import (
    MODULOS,
    ModuloOrquestado,
    ejecutar_corrida_programada,
)
from modules.preparation.nodes.preparacion import DatosCaptura
from shared.persistence import (
    actualizar_corrida,
    escribir_evento,
    escribir_fila,
    generar_id,
    leer_tabla,
    registrar_corrida,
)
from shared.utilidades import ahora

ORQUESTADOR: dict[str, Any] = {
    "modo_ejecucion": "serie",
    "modulos": ["descubrimiento", "preparacion"],
    "pausa_entre_modulos_segundos": 0,
}

CONFIG: dict[str, Any] = {"orquestador": dict(ORQUESTADOR)}


PREPARACION: dict[str, Any] = {
    "umbral_titulo": 90,
    "umbral_descripcion": 85,
    "max_pasadas": 2,
    "pausa_entre_ofertas_segundos": 0,
    "limite_vida_sesion": 50,
    "retries": {
        "max_attempts": 2,
        "base_wait_seconds": 0,
        "max_wait_seconds": 0,
        "multiplier": 1,
    },
}

_CODIGOS_RESUMEN = frozenset(
    {"modulo_ejecutado", "modulo_fallido", "corrida_programada"}
)


def _modulo_simulado(
    nombre: str,
    *,
    cierra: bool = True,
    explota: bool = False,
) -> ModuloOrquestado:
    """Registry entry whose flow registers+closes its own run on demand."""

    def flujo() -> None:
        if explota:
            raise RuntimeError(f"bug simulado en {nombre}")
        if not cierra:
            return
        id_corrida = str(generar_id("corridas"))
        registrar_corrida(
            {
                "id_corrida": id_corrida,
                "fecha_inicio": ahora(),
                "estado": "en_ejecucion",
            }
        )
        actualizar_corrida(
            id_corrida,
            {
                "estado": "completada",
                "fecha_fin": ahora(),
                "motivo_terminacion": "corrida_completada",
            },
        )

    return ModuloOrquestado(nombre, "-", "completada", flujo)


@pytest.fixture
def registro_simulado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        orquestador_mod,
        "MODULOS",
        [
            _modulo_simulado("descubrimiento"),
            _modulo_simulado("preparacion"),
        ],
    )


def _eventos_programada() -> list[dict[str, Any]]:
    ids = {
        e["id_corrida"]
        for e in leer_tabla("eventos")
        if e["codigo"] in _CODIGOS_RESUMEN
    }
    return [e for e in leer_tabla("eventos") if e["id_corrida"] in ids]


def _corridas_programadas() -> list[dict[str, Any]]:
    ids = {e["id_corrida"] for e in _eventos_programada()}
    return [c for c in leer_tabla("corridas") if c["id_corrida"] in ids]


@pytest.mark.usefixtures("temp_db_file", "registro_simulado")
def test_camino_feliz_dos_modulos_resumen_completo() -> None:
    ejecutar_corrida_programada(dict(CONFIG))
    programadas = _corridas_programadas()
    assert len(programadas) == 1
    fila = programadas[0]
    assert fila["estado"] == "completada"
    assert fila["total_sucesos"] == 2
    assert fila["total_errores"] == 0
    assert fila["total_ofertas"] == 0
    assert fila["fuentes_procesadas"] == 0
    eventos = _eventos_programada()
    assert sorted(e["codigo"] for e in eventos) == [
        "corrida_programada",
        "modulo_ejecutado",
        "modulo_ejecutado",
    ]
    resumen = next(e for e in eventos if e["codigo"] == "corrida_programada")
    assert resumen["tipo"] == "suceso"
    assert (
        resumen["evidencia"] == "descubrimiento=completada;preparacion=completada"
    )


@pytest.mark.usefixtures("temp_db_file", "registro_simulado")
def test_excepcion_de_modulo_no_detiene_la_corrida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orquestador_mod,
        "MODULOS",
        [
            _modulo_simulado("descubrimiento", explota=True),
            _modulo_simulado("preparacion"),
        ],
    )
    ejecutar_corrida_programada(dict(CONFIG))
    fila = _corridas_programadas()[0]
    # RN-04: the module bug does not abort the scheduled run.
    assert fila["estado"] == "completada"
    assert fila["total_errores"] == 1
    assert fila["total_sucesos"] == 1
    fallo = next(
        e for e in _eventos_programada() if e["codigo"] == "modulo_fallido"
    )
    assert fallo["tipo"] == "error"
    assert "modulo=descubrimiento" in fallo["evidencia"]
    assert "estado=no_iniciada" in fallo["evidencia"]
    resumen = next(
        e for e in _eventos_programada() if e["codigo"] == "corrida_programada"
    )
    assert "preparacion=completada" in resumen["evidencia"]


@pytest.mark.usefixtures("temp_db_file", "registro_simulado")
def test_modulo_silencioso_reporta_no_iniciada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orquestador_mod,
        "MODULOS",
        [_modulo_simulado("descubrimiento", cierra=False)],
    )
    ejecutar_corrida_programada(
        {"orquestador": {**ORQUESTADOR, "modulos": ["descubrimiento"]}}
    )
    resumen = next(
        e for e in _eventos_programada() if e["codigo"] == "corrida_programada"
    )
    assert resumen["evidencia"] == "descubrimiento=no_iniciada"


@pytest.mark.usefixtures("temp_db_file", "registro_simulado")
@pytest.mark.parametrize(
    "seccion",
    [
        None,
        {},
        {**ORQUESTADOR, "modo_ejecucion": "paralelo"},
        {**ORQUESTADOR, "modulos": []},
        {**ORQUESTADOR, "modulos": ["inexistente"]},
        {**ORQUESTADOR, "pausa_entre_modulos_segundos": -1},
    ],
)
def test_configuracion_invalida_no_lanza_nada(seccion: Any) -> None:
    config: dict[str, Any] = {} if seccion is None else {"orquestador": seccion}
    antes = len(leer_tabla("corridas"))
    ejecutar_corrida_programada(config)
    # ERR-01: abort before launching anything; no row, no events.
    assert len(leer_tabla("corridas")) == antes
    assert leer_tabla("eventos") == []


@pytest.mark.usefixtures("temp_db_file")
def test_fallo_al_crear_la_corrida_no_lanza_modulos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lanzados: list[str] = []

    def flujo_espio() -> None:
        lanzados.append("llamado")

    monkeypatch.setattr(
        orquestador_mod,
        "MODULOS",
        [ModuloOrquestado("descubrimiento", "-", "-", flujo_espio)],
    )
    intentos: list[int] = []

    def registrar_roto(datos: dict[str, Any]) -> None:
        intentos.append(1)
        raise RuntimeError("bd caida")

    monkeypatch.setattr(orquestador_mod, "registrar_corrida", registrar_roto)
    ejecutar_corrida_programada(
        {"orquestador": {**ORQUESTADOR, "modulos": ["descubrimiento"]}}
    )
    # ERR-02: single retry exercised against the REAL helper path (BD
    # failures carry no retryable code, so the retry is unconditional).
    assert len(intentos) == 2
    # Nothing launched, nothing closable.
    assert lanzados == []
    assert leer_tabla("corridas") == []


@pytest.mark.usefixtures("temp_db_file")
def test_fallo_propio_del_orquestador_cierra_abortada_con_resumen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Own unexpected failure after registration: RN-06 keeps the summary."""
    ejecutados: list[str] = []
    monkeypatch.setattr(
        orquestador_mod,
        "MODULOS",
        [
            ModuloOrquestado(
                "descubrimiento",
                "-",
                "descubierta",
                lambda: ejecutados.append("descubrimiento"),
            ),
            _modulo_simulado("preparacion"),
        ],
    )

    derivaciones: list[int] = []

    def lectura_rota(desde: str, excluir_ids: Any = None) -> dict[str, Any]:
        derivaciones.append(1)
        if len(derivaciones) >= 2:  # fails while deriving the SECOND module
            raise RuntimeError("bd caida en la derivacion")
        return {
            "estado": "completada",
            "motivo_terminacion": "corrida_completada",
            "id_corrida": "COR-0002",
        }

    monkeypatch.setattr(
        orquestador_mod, "leer_ultima_corrida_cerrada", lectura_rota
    )
    ejecutar_corrida_programada(dict(CONFIG))
    programadas = _corridas_programadas()
    assert len(programadas) == 1
    fila = programadas[0]
    assert fila["estado"] == "abortada"
    assert fila["motivo_terminacion"] == "error_critico"
    resumenes = [
        e for e in _eventos_programada() if e["codigo"] == "corrida_programada"
    ]
    # RN-06: the partial summary is recorded even on the abort path.
    assert len(resumenes) == 1
    assert resumenes[0]["evidencia"] == "descubrimiento=completada"


@pytest.mark.usefixtures("temp_db_file", "registro_simulado")
def test_cierre_persistente_fallido_deja_corrida_abierta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intentos: list[int] = []

    def cierre_roto(id_corrida: str, campos: dict[str, Any]) -> bool:
        intentos.append(1)
        raise RuntimeError("bd caida en el cierre")

    monkeypatch.setattr(orquestador_mod, "actualizar_corrida", cierre_roto)
    ejecutar_corrida_programada(
        {"orquestador": {**ORQUESTADOR, "modulos": ["descubrimiento"]}}
    )
    # ERR-05: single retry exhausted; the trace lives in events, no crash.
    assert len(intentos) == 2
    assert any(
        e["codigo"] == "corrida_programada" for e in _eventos_programada()
    )


@pytest.mark.usefixtures("temp_db_file", "registro_simulado")
def test_atribucion_aislada_entre_modulos_consecutivos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A silent second module must NOT inherit the first module's run."""
    monkeypatch.setattr(
        orquestador_mod,
        "MODULOS",
        [
            _modulo_simulado("descubrimiento"),
            _modulo_simulado("preparacion", cierra=False),
        ],
    )
    ejecutar_corrida_programada(dict(CONFIG))
    resumen = next(
        e for e in _eventos_programada() if e["codigo"] == "corrida_programada"
    )
    assert resumen["evidencia"] == (
        "descubrimiento=completada;preparacion=no_iniciada"
    )


@pytest.mark.usefixtures("temp_db_file")
def test_corridas_previas_fuera_de_ventra_se_ignoran(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orquestador_mod,
        "MODULOS",
        [_modulo_simulado("descubrimiento", cierra=False)],
    )
    registrar_corrida(
        {
            "id_corrida": str(generar_id("corridas")),
            "fecha_inicio": "2026-08-21 07:00:00",
            "estado": "en_ejecucion",
        }
    )
    vieja = leer_tabla("corridas")[0]["id_corrida"]
    actualizar_corrida(
        vieja,
        {
            "estado": "completada",
            "fecha_fin": ahora(),
            "motivo_terminacion": "corrida_completada",
        },
    )
    ejecutar_corrida_programada(
        {"orquestador": {**ORQUESTADOR, "modulos": ["descubrimiento"]}}
    )
    # The pre-existing closed run started BEFORE T0: the window excludes it.
    resumen = next(
        e for e in _eventos_programada() if e["codigo"] == "corrida_programada"
    )
    assert resumen["evidencia"] == "descubrimiento=no_iniciada"


@pytest.mark.usefixtures("temp_db_file", "registro_simulado")
def test_evento_resumen_fallido_es_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = escribir_evento

    def escribir_selectivo(datos: dict[str, Any]) -> str:
        if datos["codigo"] == "corrida_programada":
            raise RuntimeError("disco lleno")
        return real(datos)

    monkeypatch.setattr(orquestador_mod, "escribir_evento", escribir_selectivo)
    ejecutar_corrida_programada(
        {"orquestador": {**ORQUESTADOR, "modulos": ["descubrimiento"]}}
    )
    # ERR-04: summary-event failure never blocks closing the scheduled run.
    fila = _corridas_programadas()[0]
    assert fila["estado"] == "completada"
    assert fila["total_sucesos"] == 1


@pytest.mark.usefixtures("temp_db_file", "registro_simulado")
def test_dos_corridas_programadas_consecutivas_son_independientes() -> None:
    ejecutar_corrida_programada(dict(CONFIG))
    ejecutar_corrida_programada(dict(CONFIG))
    programadas = _corridas_programadas()
    assert len(programadas) == 2
    ids_programadas = {c["id_corrida"] for c in programadas}
    # RN-07: summary events link to their own scheduled run...
    for evento in _eventos_programada():
        assert evento["id_corrida"] in ids_programadas
    # ...and each module kept its own separate run row.
    ids_modulos = {
        c["id_corrida"] for c in leer_tabla("corridas")
    } - ids_programadas
    assert len(ids_modulos) == 4


@pytest.mark.usefixtures("temp_db_file")
def test_flujo_real_de_preparacion_como_modulo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real Preparation orchestrator runs inside a scheduled execution."""
    escribir_fila(
        "ofertas_descubiertas",
        {
            "id": "OFE-0001",
            "enlace": "https://www.linkedin.com/jobs/view/OFE-0001",
            "fecha_descubrimiento": "2026-08-21 08:00:00",
            "estado": "descubierta",
        },
    )

    def captura_ok(ctx: Any, enlace: str) -> DatosCaptura:
        return DatosCaptura(
            titulo_h1="Analista de datos",
            descripcion="Oferta de prueba para la corrida programada",
            empresa_nombre="Acme",
            empresa_perfil="Tecnologia",
        )

    monkeypatch.setattr(preparacion_mod, "_capturar_pagina", captura_ok)
    monkeypatch.setattr(
        preparacion_mod, "_diligenciar_ubicacion", lambda ctx, texto: "UBI-TEST"
    )
    config = {
        "concurrencia": {"umbral_obsolescencia_minutos": 120},
        "preparacion": PREPARACION,
        "orquestador": {**ORQUESTADOR, "modulos": ["preparacion"]},
    }
    ejecutar_corrida_programada(config)
    resumen = next(
        e for e in _eventos_programada() if e["codigo"] == "corrida_programada"
    )
    assert resumen["evidencia"] == "preparacion=completada"
    ofertas = leer_tabla("ofertas_descubiertas")
    assert ofertas[0]["estado"] == "preparada"
    assert any(c["total_preparadas"] == 1 for c in leer_tabla("corridas"))


def test_registro_declara_los_tres_modulos_del_pipeline() -> None:
    # Fase 6: evaluacion se declara tercero tras preparacion; el `orquestador:`
    # de ajustes lo habilita solo tras su vuelta de verificacion solo (D48).
    assert [m.nombre for m in MODULOS] == ["descubrimiento", "preparacion", "evaluacion"]
    estados = {(m.estado_entrada, m.estado_salida) for m in MODULOS}
    assert ("-", "descubierta") in estados
    assert ("descubierta", "preparada/duplicada") in estados
    assert ("preparada", "aceptada_ei/descartada_ei") in estados
