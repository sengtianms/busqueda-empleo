"""Tests de los mandos operativos (D64): pausar, reanudar, detener, limpiar."""

import os
import signal
import subprocess
from pathlib import Path
from typing import Any

import pytest

import scripts.control_tandas as control

_RELOJ = "busqueda-empleo.timer"
_VIGIA = "busqueda-empleo-vigilante.timer"
_UNIT_TANDA = "busqueda-empleo.service"


class _AvisosGrabadora:
    """Sustituto de la ventana de avisos: graba cuerpos sin tocar escritorio."""

    def __init__(self) -> None:
        self.cuerpos: list[str] = []

    def __call__(self, cuerpo: str, urgencia: str) -> None:
        self.cuerpos.append(f"[{urgencia}] {cuerpo}")


class _SistemaGrabadora:
    """Sustituto del programador del sistema: estados programables."""

    def __init__(self, estados: dict[str, str] | None = None) -> None:
        self.ordenes: list[tuple[str, ...]] = []
        self.estados = estados or {}

    def __call__(self, *argumentos: str) -> subprocess.CompletedProcess[str]:
        self.ordenes.append(argumentos)
        if argumentos[0] == "stop" and len(argumentos) > 1:
            # Comportamiento real del programador: tras una parada la unidad
            # deja de estar viva (y no queda marcada como fallida).
            self.estados[f"is-active {argumentos[1]}"] = "inactive"
        texto = self.estados.get(" ".join(argumentos), "")
        if argumentos[0] == "list-timers":
            cuerpo = (
                "NEXT LEFT LAST PASSED UNIT ACTIVATES\n"
                + (texto or "Tue 2026-10-27 20:00:00 UTC 2h 13min left - -")
                + "\n"
            )
            return subprocess.CompletedProcess(argumentos, 0, cuerpo, "")
        return subprocess.CompletedProcess(argumentos, 0, texto + "\n", "")

    def contiene(self, *fragmentos: str) -> bool:
        return any(tuple(fragmentos) == orden for orden in self.ordenes)


class _PistasGrabadora:
    """Sustituto del sondeo de procesos: salidas programables por llamado."""

    def __init__(self, salidas: list[tuple[set[int], set[int]]]) -> None:
        self.salidas = list(salidas)
        self.usos = 0

    def __call__(self) -> tuple[set[int], set[int]]:
        self.usos += 1
        return self.salidas[min(self.usos - 1, len(self.salidas) - 1)]


class _CortesGrabadora:
    """Sustituto de la señal a procesos: registra (pids, señal)."""

    def __init__(self, avisos: _AvisosGrabadora) -> None:
        self.registros: list[tuple[set[int], int]] = []
        self.avisos = avisos

    def __call__(self, pids: set[int], senal: int = signal.SIGTERM) -> None:
        self.registros.append((set(pids), senal))
        self.avisos.cuerpos.append(f"CORTE {sorted(pids)}")


def _instalar(
    monkeypatch: pytest.MonkeyPatch, sistema: _SistemaGrabadora
) -> tuple[_AvisosGrabadora, _CortesGrabadora]:
    avisos = _AvisosGrabadora()
    cortes = _CortesGrabadora(avisos)
    monkeypatch.setattr(control, "_ctl", sistema)
    monkeypatch.setattr(control, "enviar_aviso", avisos)
    monkeypatch.setattr(control, "_cortar", cortes)
    monkeypatch.setattr(control, "_pausa", lambda segundos: None)
    return avisos, cortes


def _procesos_inertes(monkeypatch: pytest.MonkeyPatch) -> _PistasGrabadora:
    vacia: tuple[set[int], set[int]] = (set(), set())
    pistas = _PistasGrabadora([vacia])
    monkeypatch.setattr(control, "_pistas_de_procesos", pistas)
    return pistas


def _corrida(id_corrida: str, fecha_inicio: str) -> None:
    from shared.persistence import registrar_corrida

    registrar_corrida(
        {"id_corrida": id_corrida, "fecha_inicio": fecha_inicio, "estado": "en_ejecucion"}
    )


def _evento(id_corrida: str, codigo: str, marca: str, evidencia: str = "dato=1") -> None:
    from shared.persistence import escribir_evento

    escribir_evento(
        {
            "id_corrida": id_corrida,
            "tipo": "suceso",
            "codigo": codigo,
            "evidencia": evidencia,
            "marca_temporal": marca,
        }
    )


def _silla(id_corrida: str, marca: str) -> None:
    from shared.persistence import adquirir_bloqueo

    assert adquirir_bloqueo(id_corrida, marca, forzar=True)


def _leer(id_corrida: str) -> dict[str, Any] | None:
    from shared.persistence import leer_tabla

    return next(
        (fila for fila in leer_tabla("corridas") if str(fila["id_corrida"]) == id_corrida),
        None,
    )


def test_pausar_apaga_el_reloj(monkeypatch: pytest.MonkeyPatch) -> None:
    sistema = _SistemaGrabadora(
        {
            f"is-enabled {_RELOJ}": "enabled",
            f"is-active {_UNIT_TANDA}": "active",
        }
    )
    avisos, _ = _instalar(monkeypatch, sistema)
    salida = control.pausar()
    assert sistema.contiene("stop", _RELOJ)
    assert sistema.contiene("disable", _RELOJ)
    assert "Pausa activa" in salida
    assert "termina con normalidad" in salida
    assert any("Pausa activa" in cuerpo for cuerpo in avisos.cuerpos)


def test_pausar_idempotente_no_toca_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    sistema = _SistemaGrabadora({f"is-enabled {_RELOJ}": "disabled"})
    avisos, _ = _instalar(monkeypatch, sistema)
    salida = control.pausar()
    assert "ya estaba apagado" in salida
    assert not sistema.contiene("stop", _RELOJ)
    assert not sistema.contiene("disable", _RELOJ)
    assert not avisos.cuerpos


def test_reanudar_arma_el_reloj(monkeypatch: pytest.MonkeyPatch) -> None:
    sistema = _SistemaGrabadora(
        {
            f"is-enabled {_RELOJ}": "disabled",
            f"is-enabled {_VIGIA}": "enabled",
        }
    )
    avisos, _ = _instalar(monkeypatch, sistema)
    salida = control.reanudar()
    assert sistema.contiene("enable", _RELOJ)
    assert sistema.contiene("start", _RELOJ)
    assert "reanudadas" in salida
    assert "Próximo disparo" in salida
    assert any("reanudadas" in cuerpo for cuerpo in avisos.cuerpos)


def test_reanudar_restaura_la_salud_del_vigia(monkeypatch: pytest.MonkeyPatch) -> None:
    sistema = _SistemaGrabadora(
        {
            f"is-enabled {_RELOJ}": "disabled",
            f"is-enabled {_VIGIA}": "disabled",
        }
    )
    _instalar(monkeypatch, sistema)
    monkeypatch.setattr(
        control,
        "_instalar_salud",
        lambda: "salud del sistema de tandas restaurada (grabada)",
    )
    salida = control.reanudar()
    assert "restaurada (grabada)" in salida


def test_reanudar_ya_armada_no_toca_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    sistema = _SistemaGrabadora(
        {
            f"is-enabled {_RELOJ}": "enabled",
            f"is-active {_RELOJ}": "active",
            f"is-enabled {_VIGIA}": "enabled",
        }
    )
    avisos, _ = _instalar(monkeypatch, sistema)
    salida = control.reanudar()
    assert "ya está armado" in salida
    assert not sistema.contiene("enable", _RELOJ)
    assert not sistema.contiene("start", _RELOJ)
    assert not avisos.cuerpos


def test_detener_sin_nada_que_hacer(monkeypatch: pytest.MonkeyPatch) -> None:
    sistema = _SistemaGrabadora({f"is-active {_UNIT_TANDA}": "inactive"})
    avisos, cortes = _instalar(monkeypatch, sistema)
    _procesos_inertes(monkeypatch)
    salida = control.detener(gracia=0.1)
    assert "No hay tanda en marcha" in salida
    assert not avisos.cuerpos
    assert cortes.registros == []


def test_detener_corta_el_servicio_programado(monkeypatch: pytest.MonkeyPatch) -> None:
    sistema = _SistemaGrabadora({f"is-active {_UNIT_TANDA}": "active"})
    avisos, _ = _instalar(monkeypatch, sistema)
    _procesos_inertes(monkeypatch)
    salida = control.detener(gracia=0.1)
    assert sistema.contiene("stop", _UNIT_TANDA)
    assert "Tanda programada detenida por el programador." in salida
    assert "nada que cerrar" in salida
    assert avisos.cuerpos


def test_detener_para_la_tanda_que_esta_arrancando(monkeypatch: pytest.MonkeyPatch) -> None:
    """Una unidad en 'arrancando' tambien se para por la via ordenada.

    El caso real que lo destapo (2026-10-23) fue el antiguo Type=oneshot, que
    figura 'activating' durante TODA la tanda: mirando solo 'active', la
    parada ordenada nunca se ejecutaba y el mando caia al corte por nombre,
    dejando la unidad 'failed' y el aviso critico falso de unidad muerta.
    El tipo se corrigio a Type=exec (D65); esta prueba mantiene la tolerancia.
    """
    sistema = _SistemaGrabadora({f"is-active {_UNIT_TANDA}": "activating"})
    avisos, cortes = _instalar(monkeypatch, sistema)
    _procesos_inertes(monkeypatch)
    salida = control.detener(gracia=0.1)
    assert sistema.contiene("stop", _UNIT_TANDA)
    assert "Tanda programada detenida por el programador." in salida
    assert "barrido forzoso" not in salida
    assert "manual" not in salida
    assert cortes.registros == []
    assert not sistema.contiene("reset-failed", _UNIT_TANDA)
    assert sistema.estados[f"is-active {_UNIT_TANDA}"] == "inactive"
    assert avisos.cuerpos


def test_esperar_parada_no_cuelga_si_la_unidad_no_cede(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una unidad que no termina ('deactivating' eterno) agota el tope y el
    mando completa la orden con el barrido forzoso."""
    sistema = _SistemaGrabadora({f"is-active {_UNIT_TANDA}": "deactivating"})
    _instalar(monkeypatch, sistema)
    assert control._esperar_parada(_UNIT_TANDA, tope=0.0) is False


def test_detener_corta_procesos_manuales_con_fuerza_si_resisten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sistema = _SistemaGrabadora({f"is-active {_UNIT_TANDA}": "inactive"})
    avisos, cortes = _instalar(monkeypatch, sistema)
    monkeypatch.setattr(
        control,
        "_pistas_de_procesos",
        _PistasGrabadora([({11, 12}, {99}), ({11}, set())]),
    )
    salida = control.detener(gracia=0.1)
    assert "3 proceso(s) de tanda manual cortado(s)." in salida
    assert cortes.registros[0] == ({11, 12, 99}, signal.SIGTERM)
    assert cortes.registros[1] == ({11}, signal.SIGKILL)
    assert any("CORTE [11, 12, 99]" in cuerpo for cuerpo in avisos.cuerpos)


def test_detener_nunca_corta_la_mano_que_lo_invoca(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lección del humo en vivo: un operador puede consultar los patrones en
    su propia orden; el mando jamás corta a su terminal ni a sus antepasados."""
    sistema = _SistemaGrabadora({f"is-active {_UNIT_TANDA}": "inactive"})
    avisos, cortes = _instalar(monkeypatch, sistema)
    _procesos_inertes(monkeypatch)
    yo = os.getpid()
    monkeypatch.setattr(
        control,
        "_pistas_de_procesos",
        _PistasGrabadora([({yo, 4242}, set()), ({yo, 4242}, set())]),
    )
    control.detener(gracia=0.1)
    cortados = {pid for registro, _ in cortes.registros for pid in registro}
    assert yo not in cortados
    assert 4242 in cortados


def test_detener_cierra_la_tanda_al_instante(monkeypatch: pytest.MonkeyPatch) -> None:
    sistema = _SistemaGrabadora({f"is-active {_UNIT_TANDA}": "inactive"})
    _instalar(monkeypatch, sistema)
    _procesos_inertes(monkeypatch)
    _corrida("COR-T", "2026-10-22 20:55:00")
    _evento("COR-T", "corrida_programada", "2026-10-22 20:55:01")
    _corrida("COR-D", "2026-10-22 20:55:05")
    _evento("COR-D", "tic_modulo_iniciado", "2026-10-22 20:55:10", "modulo=descubrimiento")
    _silla("COR-D", "2026-10-22 20:55:06")
    salida = control.detener(gracia=0.1)
    fila_tanda = _leer("COR-T")
    fila_modulo = _leer("COR-D")
    assert fila_tanda is not None and fila_modulo is not None
    assert fila_tanda["estado"] == "abortada"
    assert fila_tanda["motivo_terminacion"] == "proceso_desaparecido"
    assert fila_modulo["estado"] == "abortada"
    assert fila_modulo["motivo_terminacion"] == "proceso_desaparecido"
    from shared.persistence import consultar_bloqueo, leer_tabla

    evidencias = [
        str(e["evidencia"])
        for e in leer_tabla("eventos")
        if "cierre=" in str(e["evidencia"])
    ]
    assert any("cierre=orden_operador" in evidencia for evidencia in evidencias)
    assert consultar_bloqueo() is None  # la silla de la tanda quedó suelta
    assert "COR-T" in salida and "COR-D" in salida


def test_detener_deja_los_sobrantes_al_vigia(monkeypatch: pytest.MonkeyPatch) -> None:
    sistema = _SistemaGrabadora({f"is-active {_UNIT_TANDA}": "inactive"})
    _instalar(monkeypatch, sistema)
    _procesos_inertes(monkeypatch)
    _corrida("COR-T", "2026-10-22 20:55:00")
    _evento("COR-T", "corrida_programada", "2026-10-22 20:55:01")
    _corrida("COR-D", "2026-10-22 20:55:05")
    _evento("COR-D", "tic_modulo_iniciado", "2026-10-22 20:55:10", "modulo=descubrimiento")
    _corrida("COR-VIEJA", "2026-10-22 10:00:00")
    _evento("COR-VIEJA", "tic_modulo_iniciado", "2026-10-22 20:10:09", "modulo=descubrimiento")
    _silla("COR-VIEJA", "2026-10-22 10:00:01")
    salida = control.detener(gracia=0.1)
    fila_vieja = _leer("COR-VIEJA")
    assert fila_vieja is not None
    assert fila_vieja["estado"] == "en_ejecucion"
    assert fila_vieja["motivo_terminacion"] != "proceso_desaparecido"
    from shared.persistence import consultar_bloqueo

    silla = consultar_bloqueo()
    assert silla is not None
    assert str(silla["id_corrida"]) == "COR-VIEJA"  # su silla sigue suya
    assert "sobrante(s)" in salida


def test_detener_sin_anclas_cierra_todas_las_abiertas(monkeypatch: pytest.MonkeyPatch) -> None:
    sistema = _SistemaGrabadora({f"is-active {_UNIT_TANDA}": "inactive"})
    _instalar(monkeypatch, sistema)
    _procesos_inertes(monkeypatch)
    _corrida("COR-CIEGA", "2026-10-22 20:59:59")
    salida = control.detener(gracia=0.1)
    fila_ciega = _leer("COR-CIEGA")
    assert fila_ciega is not None
    assert fila_ciega["estado"] == "abortada"
    assert "COR-CIEGA" in salida


def test_limpiar_barrido_completo(monkeypatch: pytest.MonkeyPatch) -> None:
    sistema = _SistemaGrabadora(
        {
            f"is-active {_UNIT_TANDA}": "inactive",
            f"is-enabled {_RELOJ}": "enabled",
        }
    )
    _instalar(monkeypatch, sistema)
    _procesos_inertes(monkeypatch)
    _corrida("COR-T", "2026-10-22 20:55:00")
    _evento("COR-T", "corrida_programada", "2026-10-22 20:55:01")
    _corrida("COR-D", "2026-10-22 20:55:05")
    _evento("COR-D", "tic_modulo_iniciado", "2026-10-22 20:55:10", "modulo=descubrimiento")
    _silla("COR-D", "2026-10-22 20:55:06")
    _corrida("COR-ANTIGUA", "2026-10-22 10:00:00")
    _evento("COR-ANTIGUA", "tic_modulo_iniciado", "2026-10-22 20:10:09", "modulo=preparacion")
    salida = control.limpiar(gracia=0.1)
    from shared.persistence import consultar_bloqueo

    for id_corrida in ("COR-T", "COR-D", "COR-ANTIGUA"):
        fila = _leer(id_corrida)
        assert fila is not None
        assert fila["estado"] == "abortada"
        assert fila["motivo_terminacion"] == "proceso_desaparecido"
    assert consultar_bloqueo() is None
    assert "Todo en cero" in salida
    assert "reloj sigue armado" in salida
    assert "COR-T" in salida and "COR-ANTIGUA" in salida


def test_vigia_dispara_cada_dos_minutos() -> None:
    """Cuadratura del calendario del vigía (Punto 3/D68, observación 3.3).

    Los umbrales del vigía son de 10 min (aviso de tanda congelada y cierre
    de zombis); una pasada cada 2 min cubre esa ventana con 5 revisiones,
    sin el gasto de revisar cada minuto. Congelado en el archivo del
    temporizador para que nadie lo revierta sin querer.
    """
    ruta = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "systemd"
        / "busqueda-empleo-vigilante.timer"
    )
    contenido = ruta.read_text(encoding="utf-8")
    assert "OnCalendar=" in contenido, "el temporizador perdió su calendario"
    calendario = next(
        linea.split("=", 1)[1].strip()
        for linea in contenido.splitlines()
        if linea.startswith("OnCalendar=")
    )
    assert calendario == "*:0/2"
    assert "every 2 minutes" in contenido
    assert "OnCalendar=*:*:00" not in contenido


def test_limpiar_suelta_silla_desconocida(monkeypatch: pytest.MonkeyPatch) -> None:
    sistema = _SistemaGrabadora(
        {
            f"is-active {_UNIT_TANDA}": "inactive",
            f"is-enabled {_RELOJ}": "disabled",
        }
    )
    _instalar(monkeypatch, sistema)
    _procesos_inertes(monkeypatch)
    _silla("COR-ANON", "2026-10-22 20:00:00")
    salida = control.limpiar(gracia=0.1)
    from shared.persistence import consultar_bloqueo

    assert consultar_bloqueo() is None
    assert "Silla restante de COR-ANON liberada." in salida
    assert "Todo en cero" in salida
    assert "reloj de tandas está en pausa" in salida
