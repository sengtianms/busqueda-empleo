"""Tests del núcleo de la traza (punto 5): umbrales desde la configuración.

El tablero, el centinela y los mandos comparten un solo origen de números de
decisión: la sección `visibilidad:` de la configuración, con respaldo (600/900)
cuando la sección falta o trae valores inválidos.
"""

from typing import Any

import pytest

import scripts.modelo_tanda as nucleo


def _config_con(valores: dict[str, Any] | None) -> dict[str, Any]:
    cfg: dict[str, Any] = {}
    if valores is not None:
        cfg["visibilidad"] = valores
    return cfg


def test_respaldos_sin_seccion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nucleo, "load", lambda: _config_con(None))
    assert nucleo.umbral_congelada_segundos() == 600
    assert nucleo.ventana_tanda_segundos() == 900


def test_valores_de_la_configuracion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nucleo,
        "load",
        lambda: _config_con(
            {"umbral_congelada_segundos": 500, "ventana_tanda_segundos": 700}
        ),
    )
    assert nucleo.umbral_congelada_segundos() == 500
    assert nucleo.ventana_tanda_segundos() == 700


@pytest.mark.parametrize("malo", [-1, 0, "600", 6.5, True, None])
def test_valores_invalidos_ceden_al_respaldo(
    monkeypatch: pytest.MonkeyPatch, malo: Any
) -> None:
    valores_malos: dict[str, Any] = {
        "umbral_congelada_segundos": malo,
        "ventana_tanda_segundos": malo,
    }
    monkeypatch.setattr(nucleo, "load", lambda: _config_con(valores_malos))
    assert nucleo.umbral_congelada_segundos() == 600
    assert nucleo.ventana_tanda_segundos() == 900


def test_configuracion_rota_cede_al_respaldo(monkeypatch: pytest.MonkeyPatch) -> None:
    def _roto() -> dict[str, Any]:
        raise RuntimeError("config no disponible")

    monkeypatch.setattr(nucleo, "load", _roto)
    assert nucleo.umbral_congelada_segundos() == 600
    assert nucleo.ventana_tanda_segundos() == 900


@pytest.mark.parametrize("raiz", [[], "texto", None])
def test_raiz_no_dict_cede_al_respaldo(
    monkeypatch: pytest.MonkeyPatch, raiz: Any
) -> None:
    monkeypatch.setattr(nucleo, "load", lambda: raiz)
    assert nucleo.umbral_congelada_segundos() == 600
    assert nucleo.ventana_tanda_segundos() == 900
