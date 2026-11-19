"""Pruebas del cierre compartido de los dos procesos (M3 v2.0, Fase 3)."""

from pathlib import Path
from typing import Any

import pytest

from modules.evaluation.nodes import finalizar_manual
from modules.evaluation.nodes.finalizar_manual import finalizar_proceso
from modules.evaluation.run_context import RunContext
from shared.persistence import (
    adquirir_bloqueo,
    contar_filas,
    escribir_evento,
    leer_tabla,
    registrar_corrida,
)
from shared.utilidades import ahora

_CORRIDA = "COR-0001"


def _corrida(identificador: str = _CORRIDA) -> dict[str, Any]:
    registrar_corrida(
        {
            "id_corrida": identificador,
            "fecha_inicio": ahora(),
            "estado": "en_ejecucion",
        }
    )
    return next(f for f in leer_tabla("corridas") if f["id_corrida"] == identificador)


def _evento(
    codigo: str,
    *,
    tipo: str = "suceso",
    evidencia: str = "N/A",
    id_oferta: str = "N/A",
    id_corrida: str = _CORRIDA,
) -> None:
    escribir_evento(
        {
            "id_corrida": id_corrida,
            "tipo": tipo,
            "codigo": codigo,
            "evidencia": evidencia,
            "id_oferta": id_oferta,
            "marca_temporal": ahora(),
        }
    )


def _contexto(
    proceso: str, identificador: str = _CORRIDA, *, con_trabajo: bool = True
) -> RunContext:
    contexto = RunContext(id_corrida=identificador)
    if proceso == "exportacion":
        contexto.candidatas = [{"id": "OFE-0001"}] if con_trabajo else []
        contexto.hubo_candidatas = con_trabajo
        contexto.contador_lotes = 2
        contexto.contador_exportadas = 5
    else:
        contexto.archivos_resultados = (
            [Path(f"{_CORRIDA}_lote_001.jsonl")] if con_trabajo else []
        )
        contexto.hubo_resultados = con_trabajo
        contexto.contador_aprobadas = 1
        contexto.contador_descartadas = 1
    contexto.bloqueo_adquirido = True
    return contexto


def _fila_corrida(identificador: str = _CORRIDA) -> dict[str, Any]:
    return next(
        f for f in leer_tabla("corridas") if f["id_corrida"] == identificador
    )


def _eventos_de(identificador: str = _CORRIDA) -> list[dict[str, Any]]:
    return [e for e in leer_tabla("eventos") if e["id_corrida"] == identificador]


# ------------------------------------------------------------- Exportación


def test_exportacion_pendiente_metricas_y_cierre() -> None:
    _corrida()
    _evento(
        "ofertas_exportadas",
        evidencia="lote=001;cantidad=3",
    )
    _evento(
        "ofertas_exportadas",
        evidencia="lote=002;cantidad=2",
    )
    _evento("ERR-03", tipo="error", evidencia="lote=003;fallo")
    _evento("tic_modulo_iniciado", evidencia="modulo=evaluacion")
    contexto = _contexto("exportacion")

    resultado = finalizar_proceso(contexto, "exportacion")

    assert resultado.estado == "ok"
    assert resultado.codigo == "evaluacion_pendiente"
    assert resultado.metricas is not None
    assert resultado.metricas["lotes"] == 2
    assert resultado.metricas["total_ofertas"] == 5
    assert resultado.metricas["pendientes"] == 0
    assert resultado.metricas["total_errores"] == 1
    assert resultado.metricas["total_sucesos"] == 2
    fila = _fila_corrida()
    assert fila["estado"] == "completada"
    assert fila["motivo_terminacion"] == "evaluacion_pendiente"
    assert fila["total_ofertas"] == 5
    assert fila["total_errores"] == 1
    assert fila["total_sucesos"] == 2
    assert fila["fuentes_procesadas"] == 0
    terminacion = [
        e for e in _eventos_de() if e["codigo"] == "evaluacion_pendiente"
    ]
    assert len(terminacion) == 1
    assert "lotes=2" in terminacion[0]["evidencia"]
    assert resultado.informe["exportadas"] == 5


def test_exportacion_sin_pendientes_usa_motivo_del_contexto() -> None:
    _corrida()
    contexto = _contexto("exportacion", con_trabajo=False)
    contexto.motivo_cierre = "sin_pendientes"
    resultado = finalizar_proceso(contexto, "exportacion")
    assert resultado.codigo == "sin_pendientes"
    assert _fila_corrida()["estado"] == "sin_pendientes"
    terminacion = [e for e in _eventos_de() if e["codigo"] == "sin_pendientes"]
    assert len(terminacion) == 1
    assert terminacion[0]["tipo"] == "suceso"


def test_exportacion_error_total_sin_exitos_y_con_errores() -> None:
    _corrida()
    _evento("ERR-01", tipo="error", evidencia="insumos")
    resultado = finalizar_proceso(_contexto("exportacion"), "exportacion")
    assert resultado.codigo == "error_total"
    assert _fila_corrida()["estado"] == "abortada"
    assert [e for e in _eventos_de() if e["codigo"] == "error_total"][0][
        "tipo"
    ] == "error"


def test_guadian_con_lotes_pendientes_deriva_evaluacion_pendiente() -> None:
    _corrida()
    _evento("exportacion_omitida", evidencia="lotes=1;COR-0009_lote_001:pendientes=2")
    resultado = finalizar_proceso(_contexto("exportacion"), "exportacion")
    assert resultado.codigo == "evaluacion_pendiente"
    assert resultado.metricas is not None
    assert resultado.metricas["pendientes"] == 1
    assert "pendientes=1" in _eventos_de()[-1]["evidencia"]


# ------------------------------------------------------------- Importación


def test_importacion_completada_metricas_y_columnas() -> None:
    _corrida()
    _evento("oferta_aprobada", id_oferta="OFE-0001")
    _evento("oferta_aprobada", id_oferta="OFE-0001")
    _evento("oferta_descartada", id_oferta="OFE-0002")
    _evento("evaluaciones_importadas", evidencia="lote=001;aplicadas=2")
    _evento(
        "evaluacion_rechazada", tipo="error", id_oferta="OFE-0003", evidencia="ERR-04"
    )
    _evento("tic_modulo_iniciado", evidencia="modulo=evaluacion")
    contexto = _contexto("importacion")
    contexto.lotes_cerrados = ["COR-0009_lote_001"]

    resultado = finalizar_proceso(contexto, "importacion")

    assert resultado.codigo == "corrida_completada"
    assert resultado.metricas is not None
    assert resultado.metricas["total_aprobadas"] == 1
    assert resultado.metricas["total_descartadas"] == 1
    assert resultado.metricas["total_ofertas"] == 2
    assert resultado.metricas["rechazadas"] == 1
    assert resultado.metricas["total_errores"] == 1
    assert resultado.metricas["total_sucesos"] == 4
    fila = _fila_corrida()
    assert fila["estado"] == "completada"
    assert fila["total_aprobadas"] == 1
    assert fila["total_descartadas"] == 1
    assert fila["total_ofertas"] == 2
    assert fila["total_errores"] == 1
    assert fila["total_sucesos"] == 4
    evidencia = [e for e in _eventos_de() if e["codigo"] == "corrida_completada"][0][
        "evidencia"
    ]
    assert "rechazadas=1" in evidencia
    assert "lotes_cerrados=1" in evidencia
    assert resultado.informe["lotes_cerrados"] == ["COR-0009_lote_001"]


def test_importacion_sin_resultados() -> None:
    _corrida()
    contexto = _contexto("importacion", con_trabajo=False)
    contexto.motivo_cierre = "sin_resultados"
    resultado = finalizar_proceso(contexto, "importacion")
    assert resultado.codigo == "sin_resultados"
    assert _fila_corrida()["estado"] == "sin_pendientes"
    assert [e for e in _eventos_de() if e["codigo"] == "sin_resultados"][0][
        "tipo"
    ] == "suceso"


def test_importacion_error_total_con_rechazos_y_sin_aplicadas() -> None:
    _corrida()
    _evento(
        "evaluacion_rechazada", tipo="error", id_oferta="OFE-0001", evidencia="ERR-05"
    )
    resultado = finalizar_proceso(_contexto("importacion"), "importacion")
    assert resultado.codigo == "error_total"
    assert _fila_corrida()["estado"] == "abortada"


# -------------------------------------------------------------- Motivos


def test_motivo_explicito_gana_al_del_contexto() -> None:
    _corrida()
    contexto = _contexto("importacion")
    contexto.motivo_cierre = "sin_resultados"
    resultado = finalizar_proceso(contexto, "importacion", "aborto")
    assert resultado.codigo == "aborto"


def test_motivo_del_contexto_gana_al_derivado() -> None:
    _corrida()
    _evento("ofertas_exportadas", evidencia="cantidad=2")
    contexto = _contexto("exportacion")
    contexto.motivo_cierre = "sin_pendientes"
    assert finalizar_proceso(contexto, "exportacion").codigo == "sin_pendientes"


def test_sin_metricas_y_sin_motivo_deriva_aborto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def sin_eventos(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("lectura de eventos no disponible")

    monkeypatch.setattr(finalizar_manual, "leer_eventos_de_corridas", sin_eventos)
    _corrida()
    resultado = finalizar_proceso(_contexto("importacion"), "importacion")
    assert resultado.codigo == "aborto"
    assert resultado.metricas is None


def test_proceso_desconocido_levanta_error() -> None:
    with pytest.raises(ValueError):
        finalizar_proceso(None, "otro")


def test_informe_importacion_incluye_conservados_y_faltantes() -> None:
    _corrida()
    contexto = _contexto("importacion")
    contexto.lotes_conservados = ["COR-0009_lote_002"]
    contexto.faltantes_por_lote = {"COR-0009_lote_002": ["OFE-0009"]}
    contexto.archivos_rechazados = ["respuesta.txt"]
    resultado = finalizar_proceso(contexto, "importacion")
    assert resultado.informe["lotes_conservados"] == ["COR-0009_lote_002"]
    assert resultado.informe["faltantes"] == {"COR-0009_lote_002": ["OFE-0009"]}
    assert resultado.informe["archivos_rechazados"] == ["respuesta.txt"]
    assert resultado.informe["archivos_no_eliminados"] == []


# --------------------------------------------------------- Best-effort


def test_sin_contexto_cierra_por_id_con_motivo_explicito() -> None:
    _corrida()
    resultado = finalizar_proceso(None, "exportacion", "concurrencia", _CORRIDA)
    assert resultado.codigo == "concurrencia"
    assert resultado.informe == {"proceso": "exportacion"}
    terminacion = [e for e in _eventos_de() if e["codigo"] == "concurrencia"]
    assert len(terminacion) == 1
    assert terminacion[0]["tipo"] == "suceso"
    assert _fila_corrida()["estado"] == "abortada"


def test_evento_de_terminacion_no_se_cuenta_como_suceso() -> None:
    _corrida()
    _evento("ofertas_exportadas", evidencia="cantidad=1")
    resultado = finalizar_proceso(_contexto("exportacion"), "exportacion")
    assert resultado.metricas is not None
    assert resultado.metricas["total_sucesos"] == 1
    assert contar_filas("eventos", {"id_corrida": _CORRIDA, "tipo": "suceso"}) == 2


def test_fallo_al_persistir_el_cierre_no_aborta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fallar(*_args: Any, **_kwargs: Any) -> bool:
        raise RuntimeError("base no disponible")

    monkeypatch.setattr(finalizar_manual, "actualizar_corrida", fallar)
    _corrida()
    resultado = finalizar_proceso(_contexto("exportacion"), "exportacion")
    assert resultado.estado == "ok"
    assert _eventos_de("COR-0001")


def test_bloqueo_ajeno_no_se_libera() -> None:
    _corrida()
    adquirir_bloqueo("COR-9999", ahora())
    finalizar_proceso(_contexto("exportacion"), "exportacion")
    assert [fila["id_corrida"] for fila in leer_tabla("bloqueo")] == ["COR-9999"]


def test_bloqueo_propio_se_libera() -> None:
    _corrida()
    adquirir_bloqueo(_CORRIDA, ahora())
    finalizar_proceso(_contexto("exportacion"), "exportacion")
    assert leer_tabla("bloqueo") == []
