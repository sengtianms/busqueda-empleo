"""Integration tests for the Module 2 flow orchestrator (sub-phase 5.5).

Real nodes over a temporary SQLite database; only the HTTP capture and the
location AI are replaced (module boundary), mirroring the M1 integration
strategy. Covers the happy path, zero-candidates short-circuit (P2),
duplicate marking, `max_pasadas` exhaustion with `error_total`, critical
node failures, the `concurrencia` route with a foreign lock intact (P2-A)
and back-to-back runs.
"""

from typing import Any

import pytest

import modules.preparation.nodes.preparacion as preparacion_mod
import modules.preparation.nodes.verificacion as verificacion_mod
from modules.preparation.nodes.preparacion import DatosCaptura, FalloPreparacion
from modules.preparation.orchestrator import ejecutar_flujo
from shared.persistence import (
    adquirir_bloqueo,
    consultar_bloqueo,
    escribir_fila,
    leer_tabla,
    liberar_bloqueo,
)

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
    "timeout_puerta_segundos": 60,
    "puertas_alternas": [],
}

CONFIG: dict[str, Any] = {
    "concurrencia": {"umbral_obsolescencia_minutos": 120},
    "preparacion": PREPARACION,
}


def _sembrar_oferta(oferta_id: str, fecha: str) -> None:
    escribir_fila(
        "ofertas_descubiertas",
        {
            "id": oferta_id,
            "enlace": f"https://www.linkedin.com/jobs/view/{oferta_id}",
            "fecha_descubrimiento": fecha,
            "estado": "descubierta",
        },
    )


_TITULOS_DISTINTOS = (
    "Analista de seguridad informatica",
    "Desarrollador backend java",
    "Cientifico de datos python",
    "Arquitecto cloud aws",
)


@pytest.fixture
def flujo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replaces the HTTP capture and the location AI (module boundaries).

    Capture derives a genuinely different title per offer (low similarity,
    below `umbral_titulo`) so generic scenarios produce no duplicates.
    """
    # Seed the country row so the catalogue-incomplete check passes.
    escribir_fila(
        "ubicaciones",
        {"municipio": "N/A", "departamento": "N/A", "pais": "Colombia"},
    )

    def captura_variable(ctx: Any, enlace: str) -> DatosCaptura:
        digitos = int("".join(c for c in str(enlace) if c.isdigit()) or 0)
        return DatosCaptura(
            _TITULOS_DISTINTOS[digitos % len(_TITULOS_DISTINTOS)],
            "Descripcion de prueba suficientemente larga para la oferta.",
            "Acme Corp",
            "",
        )

    monkeypatch.setattr(preparacion_mod, "_capturar_pagina", captura_variable)
    monkeypatch.setattr(
        preparacion_mod, "_diligenciar_ubicacion", lambda ctx, texto: "UBI-TEST"
    )
    return None


@pytest.fixture
def flujo_duplicado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same as `flujo` but with an IDENTICAL capture for every offer."""
    escribir_fila(
        "ubicaciones",
        {"municipio": "N/A", "departamento": "N/A", "pais": "Colombia"},
    )
    monkeypatch.setattr(
        preparacion_mod,
        "_capturar_pagina",
        lambda ctx, enlace: DatosCaptura(
            "Ingeniero de Datos Senior",
            "Descripcion de prueba suficientemente larga para la oferta.",
            "Acme Corp",
            "",
        ),
    )
    monkeypatch.setattr(
        preparacion_mod, "_diligenciar_ubicacion", lambda ctx, texto: "UBI-TEST"
    )
    return None


def _corrida(id_corrida: str) -> dict[str, Any]:
    return next(
        c for c in leer_tabla("corridas") if c["id_corrida"] == id_corrida
    )


@pytest.mark.usefixtures("temp_db_file", "flujo")
def test_flujo_feliz_prepara_y_cierra_completada() -> None:
    _sembrar_oferta("OFE-0001", "2026-08-21 08:00:00")
    _sembrar_oferta("OFE-0002", "2026-08-21 09:00:00")
    ejecutar_flujo(dict(CONFIG))
    corridas = leer_tabla("corridas")
    assert len(corridas) == 1
    c = corridas[0]
    assert c["estado"] == "completada"
    assert c["motivo_terminacion"] == "corrida_completada"
    assert c["total_preparadas"] == 2
    assert c["total_ofertas"] == 2
    assert c["total_errores"] == 0
    estados = {o["id"]: o["estado"] for o in leer_tabla("ofertas_descubiertas")}
    assert estados == {"OFE-0001": "preparada", "OFE-0002": "preparada"}
    cierre = leer_tabla("eventos")[-1]
    assert cierre["codigo"] == "corrida_completada"
    assert cierre["tipo"] == "suceso"
    assert consultar_bloqueo() is None  # bloqueo liberado


@pytest.mark.usefixtures("temp_db_file", "flujo")
def test_flujo_sin_candidatas_cierre_sin_pendientes_p2() -> None:
    ejecutar_flujo(dict(CONFIG))
    c = leer_tabla("corridas")[0]
    assert c["estado"] == "sin_pendientes"
    assert c["motivo_terminacion"] == "sin_pendientes"
    codigos = [e["codigo"] for e in leer_tabla("eventos")]
    assert "sin_pendientes" in codigos
    # P2: la decisión de candidatas corta antes del bucle; el nodo de bucle
    # nunca corrió y `revision_pendientes` no se escribe.
    assert "revision_pendientes" not in codigos


@pytest.mark.usefixtures("temp_db_file", "flujo_duplicado")
def test_flujo_marca_duplicado_y_cuenta_distinto() -> None:
    _sembrar_oferta("OFE-0001", "2026-08-21 08:00:00")
    _sembrar_oferta("OFE-0002", "2026-08-21 09:00:00")
    ejecutar_flujo(dict(CONFIG))
    ofertas = {o["id"]: o for o in leer_tabla("ofertas_descubiertas")}
    assert ofertas["OFE-0001"]["estado"] == "preparada"
    assert ofertas["OFE-0002"]["estado"] == "duplicada"
    assert ofertas["OFE-0002"]["id_duplicidad"] == "OFE-0001"
    c = _corrida(leer_tabla("corridas")[0]["id_corrida"])
    # D36: ambas fueron preparadas (eventos DISTINCT=2); la copia añade 1.
    assert c["total_preparadas"] == 2
    assert c["total_duplicadas"] == 1


@pytest.mark.usefixtures("temp_db_file", "flujo")
def test_flujo_captura_fallida_agota_pasadas_error_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fallo(ctx: Any, enlace: str) -> DatosCaptura:
        raise FalloPreparacion("pagina_inalcanzable", "simulado")

    monkeypatch.setattr(preparacion_mod, "_capturar_pagina", _fallo)
    config = dict(CONFIG)
    config["preparacion"] = {**PREPARACION, "max_pasadas": 1}
    _sembrar_oferta("OFE-0001", "2026-08-21 08:00:00")
    ejecutar_flujo(config)
    c = leer_tabla("corridas")[0]
    assert c["estado"] == "abortada"
    assert c["motivo_terminacion"] == "error_total"
    codigos = [e["codigo"] for e in leer_tabla("eventos")]
    assert "revision_pendientes" in codigos  # el bucle sí corrió: 1 pasada
    assert leer_tabla("ofertas_descubiertas")[0]["estado"] == "descubierta"


@pytest.mark.usefixtures("temp_db_file", "flujo")
def test_flujo_fallo_bd_en_verificacion_error_critico(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _estalla(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("bd caida")

    monkeypatch.setattr(verificacion_mod, "leer_tabla", _estalla)
    _sembrar_oferta("OFE-0001", "2026-08-21 08:00:00")
    ejecutar_flujo(dict(CONFIG))
    c = leer_tabla("corridas")[0]
    assert c["estado"] == "abortada"
    assert c["motivo_terminacion"] == "error_critico"
    assert consultar_bloqueo() is None


@pytest.mark.usefixtures("temp_db_file", "flujo")
def test_flujo_excepcion_inesperada_ruta_aborto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modules.preparation.orchestrator as orch

    def _explota(ctx: Any) -> Any:
        raise RuntimeError("fallo no estructurado")

    monkeypatch.setattr(orch, "ejecutar_preparacion", _explota)
    _sembrar_oferta("OFE-0001", "2026-08-21 08:00:00")
    ejecutar_flujo(dict(CONFIG))
    c = leer_tabla("corridas")[0]
    assert c["estado"] == "abortada"
    assert c["motivo_terminacion"] == "aborto"


@pytest.mark.usefixtures("temp_db_file", "flujo")
def test_flujo_concurrencia_bloqueo_ajeno_intacto() -> None:
    import datetime

    marca = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    adquirir_bloqueo("COR-OTRA", marca)
    try:
        ejecutar_flujo(dict(CONFIG))
        corridas = leer_tabla("corridas")
        assert len(corridas) == 1
        c = corridas[0]
        assert c["estado"] == "abortada"
        assert c["motivo_terminacion"] == "concurrencia"
        cierre = leer_tabla("eventos")[-1]
        assert cierre["tipo"] == "suceso"  # concurrencia es suceso
        bloqueo = consultar_bloqueo()
        assert bloqueo is not None
        assert bloqueo["id_corrida"] == "COR-OTRA"  # ajeno intacto
        assert leer_tabla("ofertas_descubiertas") == []
    finally:
        liberar_bloqueo("COR-OTRA")


@pytest.mark.usefixtures("temp_db_file", "flujo")
def test_dos_corridas_consecutivas_sanas() -> None:
    _sembrar_oferta("OFE-0001", "2026-08-21 08:00:00")
    ejecutar_flujo(dict(CONFIG))
    _sembrar_oferta("OFE-0002", "2026-08-21 09:00:00")
    ejecutar_flujo(dict(CONFIG))
    corridas = leer_tabla("corridas")
    assert len(corridas) == 2
    assert all(c["estado"] == "completada" for c in corridas)
    assert {c["total_preparadas"] for c in corridas} == {1}
    assert consultar_bloqueo() is None


@pytest.mark.usefixtures("temp_db_file", "flujo")
def test_flujo_inicio_falla_con_fila_registrada_cierra_aborto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P2-A core contract: a post-registration INICIO failure is closable."""
    import modules.preparation.nodes.inicio as inicio_mod

    def _estalla() -> list[dict[str, Any]]:
        raise RuntimeError("lectura de candidatas caida")

    monkeypatch.setattr(inicio_mod, "leer_candidatas_descubiertas", _estalla)
    _sembrar_oferta("OFE-0001", "2026-08-21 08:00:00")
    ejecutar_flujo(dict(CONFIG))
    c = leer_tabla("corridas")[0]
    assert c["estado"] == "abortada"
    assert c["motivo_terminacion"] == "aborto"
    cierre = leer_tabla("eventos")[-1]
    assert cierre["codigo"] == "aborto"
    assert consultar_bloqueo() is None
