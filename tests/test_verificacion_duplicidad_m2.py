"""Unit tests for the Verificación de duplicidad node (sub-phase 5.4).

The node is 100 % local (no AI, no HTTP), so only SQLite is exercised — via
the `temp_db_file` fixture — plus patched `leer_tabla`/`actualizar_fila` for
the DB-failure paths. Thresholds and retries come from `CONFIG_RAPIDO`.
"""

from typing import Any

import pytest

import modules.preparation.nodes.verificacion as verificacion
from modules.preparation.nodes.verificacion import (
    _anexar_observaciones,
    ejecutar_verificacion,
)
from modules.preparation.run_context import RunContext
from shared.models import Offer
from shared.persistence import (
    actualizar_fila,
    buscar_por_id,
    escribir_fila,
    leer_tabla,
)
from shared.retry import should_retry
from shared.utilidades import normalizar_texto

CONFIG_RAPIDO: dict[str, Any] = {
    "umbral_titulo": 90,
    "umbral_descripcion": 85,
    "max_pasadas": 2,
    "retries": {
        "max_attempts": 2,
        "base_wait_seconds": 0,
        "max_wait_seconds": 0,
        "multiplier": 1,
    },
}

DESC_A = (
    "Buscamos ingeniero de datos con cinco anos de experiencia en pipelines, "
    "Airflow y dbt. Trabajo remoto para toda Colombia."
)
DESC_B = (
    "Buscamos ingeniero de datos con cinco anos de experiencia en pipelines, "
    "Airflow y dbt. Trabajo remoto para toda Colombia. Se ofrece contrato "
    "directo con beneficios."
)


def _contexto(config: dict[str, Any] | None = None) -> RunContext:
    return RunContext(
        config_preparacion=config if config is not None else dict(CONFIG_RAPIDO),
        candidatas=[],
        id_corrida="COR-VER",
    )


def _insertar(
    oferta_id: str,
    *,
    estado: str = "preparada",
    titulo: str = "Ingeniero de Datos Senior",
    empresa_id: str = "EMP-1",
    descripcion: str = DESC_A,
    marcador: bool = False,
    observaciones: str = "N/A",
    id_duplicidad: str = "N/A",
) -> None:
    datos: dict[str, Any] = {
        "id": oferta_id,
        "enlace": f"https://www.linkedin.com/jobs/view/{oferta_id}",
        "fecha_descubrimiento": "2026-08-20 10:00:00",
        "estado": estado,
        "titulo": titulo,
        "empresa_id": empresa_id,
        "descripcion_original": descripcion,
        "observaciones": observaciones,
        "id_duplicidad": id_duplicidad,
        "ubicacion": "Bogota",
    }
    datos["fecha_ultima_verificacion"] = (
        "2026-08-19 09:00:00" if marcador else ""
    )
    escribir_fila("ofertas_descubiertas", datos)


def _eventos() -> list[dict[str, Any]]:
    return leer_tabla("eventos")


# --- Model / state machine regressions --------------------------------------


def test_offer_tiene_id_duplicidad_por_defecto_na() -> None:
    oferta = Offer(enlace="https://x", titulo="t", descripcion_original="d")
    assert oferta.id_duplicidad == "N/A"


def test_transicion_preparada_duplicada_valida() -> None:
    from shared.models import OfferState
    from shared.state_machine import transition

    assert transition(OfferState.PREPARADA, OfferState.DUPLICADA) == OfferState.DUPLICADA


def test_error_bd_es_codigo_reintenable() -> None:
    assert should_retry("error_bd")


# --- Etapa 1: exacta ---------------------------------------------------------


@pytest.mark.usefixtures("temp_db_file")
def test_etapa_1_exacta_misma_empresa_marca_duplicada() -> None:
    _insertar("OFE-001", marcador=True)  # original verificado antes
    _insertar("OFE-002", titulo="ingeniero de DATOS senior")
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.estado == "completada"
    assert resultado.duplicadas == 1
    copia = buscar_por_id("ofertas_descubiertas", "OFE-002")
    assert copia is not None
    assert copia["estado"] == "duplicada"
    assert copia["id_duplicidad"] == "OFE-001"
    assert "etapa1" in copia["observaciones"]
    assert "original=OFE-001" in copia["observaciones"]
    assert copia["fecha_ultima_verificacion"] != ""


@pytest.mark.usefixtures("temp_db_file")
def test_etapa_1_no_cruza_empresas_con_mismo_titulo() -> None:
    _insertar("OFE-001", marcador=True, empresa_id="EMP-1")
    _insertar("OFE-002", empresa_id="EMP-2")
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.duplicadas == 0
    copia = buscar_por_id("ofertas_descubiertas", "OFE-002")
    assert copia is not None
    assert copia["estado"] == "preparada"


@pytest.mark.usefixtures("temp_db_file")
def test_duplicado_intra_lote_apunta_al_mas_antiguo() -> None:
    """RN-05: the universe includes the current lot's pendings; T4/T6: only
    the OLDER id can be the original."""
    _insertar("OFE-001")
    _insertar("OFE-002", titulo="ingeniero de datos senior!")
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.duplicadas == 1
    copia = buscar_por_id("ofertas_descubiertas", "OFE-002")
    original = buscar_por_id("ofertas_descubiertas", "OFE-001")
    assert copia is not None and original is not None
    assert copia["id_duplicidad"] == "OFE-001"
    assert original["estado"] == "preparada"  # el original nunca cambia
    assert original["id_duplicidad"] == "N/A"


@pytest.mark.usefixtures("temp_db_file")
def test_par_intra_lote_no_se_marcan_mutuamente() -> None:
    """T6 regression: without the smaller-id rule both offers would point at
    each other."""
    _insertar("OFE-001")
    _insertar("OFE-002", titulo="ingeniero de datos senior!")
    ejecutar_verificacion(_contexto())
    primera = buscar_por_id("ofertas_descubiertas", "OFE-001")
    segunda = buscar_por_id("ofertas_descubiertas", "OFE-002")
    assert primera is not None and segunda is not None
    assert not (primera["estado"] == "duplicada" and segunda["estado"] == "duplicada")


@pytest.mark.usefixtures("temp_db_file")
def test_cadena_de_tres_intra_lote_apunta_al_primero() -> None:
    _insertar("OFE-001")
    _insertar("OFE-002", titulo="ingeniero de datos senior!")
    _insertar("OFE-003", titulo="INGENIERO DE DATOS SENIOR")
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.duplicadas == 2
    for copia_id in ("OFE-002", "OFE-003"):
        fila = buscar_por_id("ofertas_descubiertas", copia_id)
        assert fila is not None
        assert fila["id_duplicidad"] == "OFE-001"


# --- P1: empresas N/A excluidas ----------------------------------------------

def test_indice_exacto_desempate_numerico_miles_d53() -> None:
    """T4: collision on the same `(titulo, empresa)` with ids of 4 and 5
    digits — the OLDEST sequential number wins even though the raw-text
    order would keep the newer one ('OFE-9998' > 'OFE-10001' as text)."""
    universo: list[dict[str, Any]] = [
        {
            "id": "OFE-10001",
            "titulo": "Ingeniero de Datos Senior",
            "empresa_id": "EMP-1",
            "descripcion_original": DESC_A,
        },
        {
            "id": "OFE-9998",
            "titulo": "INGENIERO DE DATOS SENIOR",
            "empresa_id": "EMP-1",
            "descripcion_original": DESC_A,
        },
    ]
    indice_exacto, _ = verificacion._construir_indice(universo)
    assert indice_exacto[("ingeniero de datos senior", "EMP-1")] == "OFE-9998"


@pytest.mark.usefixtures("temp_db_file")
def test_pendiente_sin_empresa_nunca_matchea() -> None:
    _insertar("OFE-001", marcador=True)
    _insertar("OFE-002", empresa_id="N/A")
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.duplicadas == 0
    copia = buscar_por_id("ofertas_descubiertas", "OFE-002")
    assert copia is not None
    assert copia["estado"] == "preparada"
    assert copia["fecha_ultima_verificacion"] != ""


@pytest.mark.usefixtures("temp_db_file")
def test_candidato_sin_empresa_no_entra_al_indice() -> None:
    _insertar("OFE-001", marcador=True, empresa_id="N/A")
    _insertar("OFE-002")
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.duplicadas == 0


# --- Etapa 2: difusa ----------------------------------------------------------

@pytest.mark.usefixtures("temp_db_file")
def test_etapa_2_titulo_y_descripcion_suficientes() -> None:
    """Same words in different order defeat stage 1 but pass token_sort;
    the extended description scores high on partial_ratio."""
    _insertar("OFE-001", marcador=True)
    _insertar("OFE-002", titulo="Datos Senior Ingeniero de", descripcion=DESC_B)
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.duplicadas == 1
    copia = buscar_por_id("ofertas_descubiertas", "OFE-002")
    assert copia is not None
    assert copia["estado"] == "duplicada"
    assert "etapa2" in copia["observaciones"]
    assert "% desc" in copia["observaciones"]


@pytest.mark.usefixtures("temp_db_file")
def test_etapa_2_rechaza_con_descripcion_insuficiente() -> None:
    """RN-04: fuzzy title passes (word-order variant, ~100 %) but the
    description is unrelated (< 85) → NOT a duplicate."""
    _insertar("OFE-001", marcador=True)
    _insertar(
        "OFE-002",
        titulo="Datos Senior Ingeniero de",
        descripcion="Puesto operativo de bodega turno noche sabados.",
    )
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.duplicadas == 0


@pytest.mark.usefixtures("temp_db_file")
def test_etapa_2_rechaza_con_titulo_bajo_umbral() -> None:
    _insertar("OFE-001", marcador=True)
    _insertar("OFE-002", titulo="Auxiliar administrativo de cartera")
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.duplicadas == 0


@pytest.mark.usefixtures("temp_db_file")
def test_rn08_descripcion_sin_dato_no_compara_difuso() -> None:
    """Etapa 1 exige identidad exacta (falla con orden de palabras); etapa 2
    se salta al candidato sin descripción utilizable (RN-08)."""
    _insertar("OFE-001", marcador=True, descripcion="N/A")
    _insertar("OFE-002", titulo="Datos Senior Ingeniero de")
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.duplicadas == 0


def test_etapa_2_t6_acepta_original_de_miles_d53() -> None:
    """T6: the candidate must be numerically OLDER. The text rule would
    wrongly block a 4-digit original ('OFE-9998') against a 5-digit pending
    ('OFE-10002') because 'OFE-9998' >= 'OFE-10002' as text — the numeric
    comparison (D53) keeps the real order: 9998 < 10002, so the pending
    matches its true original."""
    pendiente: dict[str, Any] = {
        "id": "OFE-10002",
        "titulo": "Ingeniero de Datos Senior",
        "descripcion_original": DESC_B,
    }
    candidatos: list[tuple[str, str, str]] = [
        ("OFE-9998", "ingeniero de datos senior", normalizar_texto(DESC_A)),
    ]
    mejor = verificacion._buscar_etapa_2(pendiente, candidatos, 90.0, 85.0, set())
    assert mejor is not None
    assert mejor[0] == "OFE-9998"


# --- Universo -----------------------------------------------------------------

@pytest.mark.usefixtures("temp_db_file")
def test_universo_excluye_duplicadas_previas_sin_cadenas() -> None:
    """X ≈ Y ≈ Z: X siempre apunta al original Z, nunca a la copia Y."""
    _insertar("OFE-001", marcador=True)  # Z original
    _insertar(
        "OFE-002",
        estado="duplicada",
        id_duplicidad="OFE-001",
        observaciones="DUP | etapa previa",
    )
    _insertar("OFE-003", titulo="ingeniero de datos senior!")  # X nueva copia
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.duplicadas == 1
    copia = buscar_por_id("ofertas_descubiertas", "OFE-003")
    assert copia is not None
    # La copia apunta al ORIGINAL, no a la otra duplicada (sin cadenas).
    assert copia["id_duplicidad"] == "OFE-001"


@pytest.mark.usefixtures("temp_db_file")
def test_descubierta_nunca_es_candidata_ni_evaluada() -> None:
    _insertar("OFE-001", estado="descubierta")
    _insertar("OFE-002")
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.duplicadas == 0
    assert resultado.verificadas == 1  # solo las preparadas sin marcador


@pytest.mark.usefixtures("temp_db_file")
def test_auto_reparacion_e_idempotencia() -> None:
    """RN-06: pendings from earlier runs are re-checked; a second run over
    marked offers evaluates nothing."""
    _insertar("OFE-001", marcador=True)
    _insertar("OFE-002")
    primera = ejecutar_verificacion(_contexto())
    assert primera.verificadas == 1
    segunda = ejecutar_verificacion(_contexto())
    assert segunda.verificadas == 0


# --- Marcadores y eventos -----------------------------------------------------

@pytest.mark.usefixtures("temp_db_file")
def test_marcador_actualizado_en_todas_las_evaluadas() -> None:
    _insertar("OFE-001", marcador=True)
    _insertar("OFE-002", titulo="Analista de nomina")
    ejecutar_verificacion(_contexto())
    no_dup = buscar_por_id("ofertas_descubiertas", "OFE-002")
    original = buscar_por_id("ofertas_descubiertas", "OFE-001")
    assert no_dup is not None and original is not None
    assert no_dup["fecha_ultima_verificacion"] != ""
    assert original["fecha_ultima_verificacion"] != ""
    assert no_dup["id_corrida"] in (None, "")  # RN-12


@pytest.mark.usefixtures("temp_db_file")
def test_evento_oferta_duplicada_campos_correctos() -> None:
    _insertar("OFE-001", marcador=True)
    _insertar("OFE-002", titulo="ingeniero de datos senior")
    ejecutar_verificacion(_contexto())
    eventos = [e for e in _eventos() if e["codigo"] == "oferta_duplicada"]
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento["tipo"] == "suceso"
    assert evento["id_oferta"] == "OFE-002"  # la copia (RN-11)
    assert evento["id_corrida"] == "COR-VER"
    assert len(str(evento["evidencia"])) <= 303


@pytest.mark.usefixtures("temp_db_file")
def test_evidencia_anexa_preserva_observaciones_previas() -> None:
    _insertar("OFE-001", marcador=True)
    _insertar(
        "OFE-002",
        observaciones="DESC VACIA → N/R (evidencia captura)",
    )
    ejecutar_verificacion(_contexto())
    copia = buscar_por_id("ofertas_descubiertas", "OFE-002")
    assert copia is not None
    assert "DESC VACIA" in copia["observaciones"]
    assert "DUP" in copia["observaciones"]


def test_anexar_observaciones_colapsa_placeholders() -> None:
    assert _anexar_observaciones("N/A", "EVI") == "EVI"
    assert _anexar_observaciones("previo", "EVI") == "previo; EVI"


@pytest.mark.usefixtures("temp_db_file")
def test_resultado_contadores_coherentes() -> None:
    _insertar("OFE-001", marcador=True)  # no es pendiente
    _insertar("OFE-002", titulo="ingeniero de datos senior!")  # dup
    _insertar("OFE-003", titulo="Contador publico")  # no dup
    resultado = ejecutar_verificacion(_contexto())
    assert (resultado.verificadas, resultado.duplicadas, resultado.errores) == (2, 1, 0)


# --- Errores -------------------------------------------------------------------

@pytest.mark.usefixtures("temp_db_file")
def test_err01_consulta_bd_agota_y_aborta(monkeypatch: pytest.MonkeyPatch) -> None:
    def estalla(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("bd caida")

    monkeypatch.setattr(verificacion, "leer_tabla", estalla)
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.estado == "abortada"
    assert resultado.codigo == "ERR-01"
    eventos = [e for e in _eventos() if e["tipo"] == "error"]
    assert eventos


@pytest.mark.usefixtures("temp_db_file")
def test_err02_escritura_persistente_deja_pendiente_y_continua(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _insertar("OFE-001", marcador=True)
    _insertar("OFE-002", titulo="ingeniero de datos senior")

    real_actualizar = actualizar_fila

    def actualiza(tabla: str, id_valor: str, datos: dict[str, Any]) -> bool:
        if id_valor == "OFE-002":
            raise RuntimeError("disco lleno")
        return real_actualizar(tabla, id_valor, datos)

    monkeypatch.setattr(verificacion, "actualizar_fila", actualiza)
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.estado == "completada"
    assert resultado.errores == 1
    pendiente = buscar_por_id("ofertas_descubiertas", "OFE-002")
    assert pendiente is not None
    assert pendiente["estado"] == "preparada"
    assert pendiente["fecha_ultima_verificacion"] == ""


@pytest.mark.parametrize(
    ("clave", "valor"),
    [("umbral_titulo", 101), ("umbral_descripcion", -1), ("umbral_titulo", True)],
)
@pytest.mark.usefixtures("temp_db_file")
def test_val01_umbral_invalido_aborta_err03(clave: str, valor: Any) -> None:
    config = dict(CONFIG_RAPIDO)
    config[clave] = valor
    resultado = ejecutar_verificacion(_contexto(config))
    assert resultado.estado == "abortada"
    assert resultado.codigo == "ERR-03"


@pytest.mark.usefixtures("temp_db_file")
def test_contexto_ausente_aborta() -> None:
    resultado = ejecutar_verificacion(None)
    assert resultado.estado == "abortada"
    assert resultado.codigo == "ERR-01"


@pytest.mark.usefixtures("temp_db_file")
def test_err01_fallo_transitorio_reintenta_y_tiene_exito(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First read fails with a generic exception, second succeeds: proves the
    `error_bd` wrapping actually dispatches a retry through the helper."""
    _insertar("OFE-001", marcador=True)
    _insertar("OFE-002")
    intentos: list[int] = []
    real_leer = leer_tabla

    def lee_con_fallo(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        intentos.append(1)
        if len(intentos) == 1:
            raise RuntimeError("lock momentaneo")
        return real_leer(*args, **kwargs)

    monkeypatch.setattr(verificacion, "leer_tabla", lee_con_fallo)
    resultado = ejecutar_verificacion(_contexto())
    assert resultado.estado == "completada"
    # 1 falla + 1 reintento exitoso (pendientes) + 1 consulta del universo.
    assert len(intentos) == 3
    assert resultado.verificadas == 1
