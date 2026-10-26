"""Tests del sentinela de tanda (Lote 3): avisos, fantasmas y propiedad."""

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

import scripts.vigilante_tanda as vigia

REF = datetime(2026, 10, 22, 21, 0, 0)


class _AvisosGrabadora:
    """Sustituto de la ventana de avisos: graba cuerpos sin tocar escritorio."""

    def __init__(self) -> None:
        self.cuerpos: list[str] = []

    def __call__(self, cuerpo: str, nivel: str) -> None:
        self.cuerpos.append(f"[{nivel}] {cuerpo}")


def _corrida(id_corrida: str, fecha_inicio: str) -> None:
    from shared.persistence import registrar_corrida

    registrar_corrida(
        {"id_corrida": id_corrida, "fecha_inicio": fecha_inicio, "estado": "en_ejecucion"}
    )


def _cerrar(id_corrida: str, fecha_fin: str) -> None:
    from shared.persistence import actualizar_corrida

    actualizar_corrida(
        id_corrida,
        {
            "estado": "completada",
            "fecha_fin": fecha_fin,
            "motivo_terminacion": "corrida_completada",
        },
    )


def _evento(id_corrida: str, codigo: str, marca: str) -> None:
    from shared.persistence import escribir_evento

    escribir_evento(
        {
            "id_corrida": id_corrida,
            "tipo": "suceso",
            "codigo": codigo,
            "evidencia": "set=0 | total=5",
            "marca_temporal": marca,
        }
    )


def _silla(id_corrida: str, marca: str) -> None:
    from shared.persistence import adquirir_bloqueo

    assert adquirir_bloqueo(id_corrida, marca)


def _pasada(
    monkeypatch: pytest.MonkeyPatch,
    marcador: Path,
    avisos: _AvisosGrabadora,
    *,
    umbral_congelada: int = 600,
    horizonte_minutos: int | None = None,
) -> str:
    monkeypatch.setattr(vigia, "enviar_aviso", avisos)
    return vigia.pasada(
        umbral_congelada=umbral_congelada,
        horizonte_minutos=horizonte_minutos,
        marcador=marcador,
        referencia=REF,
    )


def test_sin_corridas_abiertas_no_toca_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shared.persistence import leer_tabla

    mensaje = _pasada(monkeypatch, tmp_path / "m.json", _AvisosGrabadora())
    assert "Sin corridas abiertas" in mensaje
    assert leer_tabla("corridas") == []


def test_tanda_viva_no_toca_nada(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from shared.persistence import leer_tabla

    _corrida("COR-V10", "2026-10-22 20:50:00")
    _corrida("COR-V11", "2026-10-22 20:50:05")
    _silla("COR-V11", "2026-10-22 20:50:05")
    _evento("COR-V11", "tic_modulo_iniciado", "2026-10-22 20:59:30")
    grabadora = _AvisosGrabadora()
    mensaje = _pasada(monkeypatch, tmp_path / "m.json", grabadora)
    assert "viva" in mensaje
    assert grabadora.cuerpos == []
    filas = {str(f["id_corrida"]): str(f["estado"]) for f in leer_tabla("corridas")}
    assert filas["COR-V10"] == "en_ejecucion"
    assert filas["COR-V11"] == "en_ejecucion"


def test_fantasma_sin_silla_se_cierra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from shared.persistence import consultar_bloqueo, leer_tabla

    _corrida("COR-F1", "2026-10-22 18:00:00")  # fantasma de hace 3 horas, sin señal
    _corrida("COR-SANA0", "2026-10-22 17:00:00")
    _cerrar("COR-SANA0", "2026-10-22 17:10:00")  # cerrada sana: intocable
    avisos = _AvisosGrabadora()
    mensaje = _pasada(monkeypatch, tmp_path / "m.json", avisos)

    assert "Silla libre" in mensaje and "COR-F1" in mensaje
    filas = {str(f["id_corrida"]): f for f in leer_tabla("corridas")}
    fantasma = filas["COR-F1"]
    assert str(fantasma["estado"]) == "abortada"
    assert str(fantasma["motivo_terminacion"]) == vigia.MOTIVO_FANTASMA
    assert str(filas["COR-SANA0"]["estado"]) == "completada"
    codigos = [str(e["codigo"]) for e in leer_tabla("eventos", {"id_corrida": "COR-F1"})]
    assert vigia.MOTIVO_FANTASMA in codigos
    assert consultar_bloqueo() is None
    assert avisos.cuerpos  # el cierre de fantasmas se anuncia


def test_fantasma_con_silla_vencida_se_cierra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shared.persistence import consultar_bloqueo, leer_tabla

    _corrida("COR-F2", "2026-10-22 18:00:00")
    _silla("COR-F2", "2026-10-22 19:30:00")  # marca 90 min antes de REF
    avisos = _AvisosGrabadora()
    mensaje = _pasada(
        monkeypatch, tmp_path / "m.json", avisos, horizonte_minutos=30
    )

    assert "Silla vencida" in mensaje and "COR-F2" in mensaje
    filas = {str(f["id_corrida"]): f for f in leer_tabla("corridas")}
    assert str(filas["COR-F2"]["estado"]) == "abortada"
    assert str(filas["COR-F2"]["motivo_terminacion"]) == vigia.MOTIVO_FANTASMA
    assert consultar_bloqueo() is None
    assert avisos.cuerpos


def test_silla_fresca_avisa_sin_cerrar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from shared.persistence import consultar_bloqueo, leer_tabla

    _corrida("COR-D10", "2026-10-22 20:00:00")
    _corrida("COR-D11", "2026-10-22 20:00:05")
    _silla("COR-D11", "2026-10-22 20:59:00")  # fresca (1 min antes de REF)
    _evento("COR-D11", "consulta_exitosa", "2026-10-22 20:29:00")  # 31 min de silencio
    avisos = _AvisosGrabadora()
    mensaje = _pasada(monkeypatch, tmp_path / "m.json", avisos)

    assert "solo aviso" in mensaje
    assert len(avisos.cuerpos) == 1  # una sola vez por ofensa
    filas = {str(f["id_corrida"]): str(f["estado"]) for f in leer_tabla("corridas")}
    assert filas["COR-D11"] == "en_ejecucion"  # corrida con silla fresca: intocable
    assert consultar_bloqueo() is not None  # silla intacta (dueño podría estar vivo)
    assert "[critical]" in avisos.cuerpos[0]


def test_tanda_viva_con_fantasma_liberado_cierra_solo_al_fantasma(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Caso del humo real: tanda detenida con silla fresca + huérfana de hace 3 h."""
    from shared.persistence import consultar_bloqueo, leer_tabla

    # Huérfana antigua, sin eventos y sin silla: zombi probado.
    _corrida("COR-FANT", "2026-10-22 18:00:00")
    # Tanda real de hace 40 min con módulo dueño de silla fresca.
    _corrida("COR-D10", "2026-10-22 20:00:00")
    _corrida("COR-D11", "2026-10-22 20:00:05")
    _silla("COR-D11", "2026-10-22 20:59:00")
    _evento("COR-D11", "consulta_exitosa", "2026-10-22 20:25:00")
    avisos = _AvisosGrabadora()
    mensaje = _pasada(monkeypatch, tmp_path / "m.json", avisos)

    assert "Residuos de tandas viejas: 1 fantasma cerrado (COR-FANT)" in mensaje
    assert "solo aviso" in mensaje  # la congelación de la tanda viva también avisa
    filas = {str(f["id_corrida"]): str(f["estado"]) for f in leer_tabla("corridas")}
    assert filas["COR-FANT"] == "abortada"
    assert filas["COR-D10"] == "en_ejecucion"  # tanda viva: intocable
    assert filas["COR-D11"] == "en_ejecucion"  # dueño de silla fresca: intocable
    assert consultar_bloqueo() is not None
    congelaciones = [c for c in avisos.cuerpos if "sin señales" in c]
    cierres = [c for c in avisos.cuerpos if "fantasma cerradas" in c]
    assert len(cierres) == 1
    assert len(congelaciones) == 1


def test_fallo_de_cierre_no_suelta_silla_ni_anuncia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hallazgo del revisor: fila no cerrada ⇒ toque nada de silla/evento/aviso."""
    from shared.persistence import consultar_bloqueo, leer_tabla

    _corrida("COR-VENC", "2026-10-22 18:00:00")
    _silla("COR-VENC", "2026-10-22 19:30:00")  # marca vencida con horizonte 30 min
    avisos = _AvisosGrabadora()

    def _caida_escribir(*_a: object, **_k: object) -> None:
        raise RuntimeError("base de datos caída")

    monkeypatch.setattr(vigia, "actualizar_corrida", _caida_escribir)
    mensaje = _pasada(
        monkeypatch, tmp_path / "m.json", avisos, horizonte_minutos=30
    )

    filas = {str(f["id_corrida"]): str(f["estado"]) for f in leer_tabla("corridas")}
    assert filas["COR-VENC"] == "en_ejecucion"  # la fila sigue abierta
    assert consultar_bloqueo() is not None  # su silla NO se suelta
    codigos = [str(e["codigo"]) for e in leer_tabla("eventos", {"id_corrida": "COR-VENC"})]
    assert codigos == []  # sin evento de cierre (solo cierra fila cerrada de verdad)
    assert "fantasmas cerrados" not in mensaje  # falso anuncio prohibido
    avisos_de_cierre = [c for c in avisos.cuerpos if "fantasma" in c]
    assert avisos_de_cierre == []


def test_silla_heredada_de_dueno_cerrado_se_suelta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shared.persistence import consultar_bloqueo

    _corrida("COR-H1", "2026-10-22 19:00:00")
    _cerrar("COR-H1", "2026-10-22 19:12:00")
    _silla("COR-H1", "2026-10-22 20:59:00")  # fresca, pero dueño ya cerrado
    grabadora = _AvisosGrabadora()
    mensaje = _pasada(monkeypatch, tmp_path / "m.json", grabadora)

    assert "silla heredada" in mensaje
    assert consultar_bloqueo() is None
    assert grabadora.cuerpos == []


def test_silla_de_dueno_desconocido_no_se_toca(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shared.persistence import consultar_bloqueo

    _silla("COR-ANONIMO", "2026-10-22 20:00:00")  # silla sin fila en corridas
    grabadora = _AvisosGrabadora()
    mensaje = _pasada(monkeypatch, tmp_path / "m.json", grabadora)

    assert "Sin corridas abiertas" in mensaje
    assert consultar_bloqueo() is not None  # id anónimo: el vigía no se mete


def test_pasada_solo_lee_eventos_de_corridas_abiertas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(30):
        _corrida(f"COR-H{i:02d}", "2026-10-22 10:00:00")
        _evento(f"COR-H{i:02d}", "ingreso_exitoso", "2026-10-22 10:05:00")
        _cerrar(f"COR-H{i:02d}", "2026-10-22 10:10:00")

    _corrida("COR-VIVA", "2026-10-22 20:50:00")
    _silla("COR-VIVA", "2026-10-22 20:50:05")
    _evento("COR-VIVA", "tic_modulo_iniciado", "2026-10-22 20:59:30")

    from shared.persistence import leer_eventos_de_corridas as real_eventos

    consultados: list[list[str]] = []
    real = real_eventos

    def espia(ids: list[str]) -> list[dict[str, Any]]:
        consultados.append(list(ids))
        return real(ids)

    monkeypatch.setattr(vigia, "leer_eventos_de_corridas", espia)
    tablas: list[str] = []

    def espia_tabla(tabla: str, filtros: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        tablas.append(tabla)
        raise AssertionError(f"lectura completa inesperada de {tabla}")

    monkeypatch.setattr(vigia, "leer_tabla", espia_tabla, raising=False)
    mensaje = _pasada(monkeypatch, tmp_path / "m.json", _AvisosGrabadora())

    assert "viva" in mensaje
    assert consultados == [["COR-VIVA"]]
    assert tablas == []


def test_pasada_sin_abiertas_no_consulta_sin_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shared.persistence import leer_eventos_de_corridas as real_eventos

    consultados: list[list[str]] = []
    real = real_eventos

    def espia(ids: list[str]) -> list[dict[str, Any]]:
        consultados.append(list(ids))
        return real(ids)

    monkeypatch.setattr(vigia, "leer_eventos_de_corridas", espia)
    mensaje = _pasada(monkeypatch, tmp_path / "m.json", _AvisosGrabadora())

    assert "Sin corridas abiertas" in mensaje
    assert consultados == [[]]


def test_pasada_con_base_ausente_no_crea_archivo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shared.persistence import change_path

    ruta = tmp_path / "no_existe.db"
    change_path(ruta)

    mensaje = _pasada(monkeypatch, tmp_path / "m.json", _AvisosGrabadora())

    assert "Base de datos no disponible" in mensaje
    assert not ruta.exists()


def test_aviso_una_vez_por_ofensa_y_vuelve_al_crecer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    avisos = _AvisosGrabadora()
    marcador = tmp_path / "m.json"
    monkeypatch.setattr(vigia, "enviar_aviso", avisos)
    vigia._avisar("primera", "COR-X|detenida|2", marcador, REF)
    vigia._avisar("repetida", "COR-X|detenida|2", marcador, REF)
    vigia._avisar("creció", "COR-X|detenida|5", marcador, REF)

    contenido = marcador.read_text(encoding="utf-8")
    assert "COR-X|detenida|5" in contenido
    assert len(avisos.cuerpos) == 2  # la repetida se silencia; el crecimiento avisa
    assert "repetida" not in avisos.cuerpos[1]
