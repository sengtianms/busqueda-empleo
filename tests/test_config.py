from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from shared import config as config_module


def _yaml_temporal(tmp_path: Path, contenido: str) -> Path:
    ruta = tmp_path / "config.yaml"
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def test_carga_yaml_y_env_y_cachea(tmp_path: Path) -> None:
    ruta_yaml = _yaml_temporal(tmp_path, "perfil:\n  nombre: Prueba\n")
    ruta_env = tmp_path / ".env"
    ruta_env.write_text("CLAVE=valor\nVACIA=\n", encoding="utf-8")
    with (
        patch.object(config_module, "_CONFIG_PATH", ruta_yaml),
        patch.object(config_module, "_ENV_PATH", ruta_env),
    ):
        config_module.reload_config()
        primera = config_module.load()
        segunda = config_module.load()

    assert primera is segunda
    assert primera["perfil"]["nombre"] == "Prueba"
    assert primera["_env"] == {"CLAVE": "valor", "VACIA": ""}


def test_carga_sin_env_asigna_env_vacio(tmp_path: Path) -> None:
    ruta_yaml = _yaml_temporal(tmp_path, "perfil:\n  nombre: Prueba\n")
    ruta_env = tmp_path / ".env"
    with (
        patch.object(config_module, "_CONFIG_PATH", ruta_yaml),
        patch.object(config_module, "_ENV_PATH", ruta_env),
    ):
        config_module.reload_config()
        config = config_module.load()

    assert config["_env"] == {}


def test_yaml_vacio_se_carga_como_diccionario(tmp_path: Path) -> None:
    ruta = _yaml_temporal(tmp_path, "")
    with (
        patch.object(config_module, "_CONFIG_PATH", ruta),
        patch.object(config_module, "_ENV_PATH", tmp_path / ".env"),
    ):
        config_module.reload_config()
        config = config_module.load()

    assert config == {"_env": {}}


def test_reload_invalida_caché(tmp_path: Path) -> None:
    ruta_yaml = _yaml_temporal(tmp_path, "perfil:\n  nombre: Uno\n")
    ruta_env = tmp_path / ".env"
    with (
        patch.object(config_module, "_CONFIG_PATH", ruta_yaml),
        patch.object(config_module, "_ENV_PATH", ruta_env),
    ):
        config_module.reload_config()
        primera = config_module.load()

        ruta_yaml.write_text("perfil:\n  nombre: Dos\n", encoding="utf-8")
        config_module.reload_config()
        segunda = config_module.load()

    assert primera is not segunda
    assert segunda["perfil"]["nombre"] == "Dos"


def test_yaml_invalido_propaga_error(tmp_path: Path) -> None:
    ruta_yaml = _yaml_temporal(tmp_path, "perfil: [no cerrado\n")
    ruta_env = tmp_path / ".env"
    with (
        patch.object(config_module, "_CONFIG_PATH", ruta_yaml),
        patch.object(config_module, "_ENV_PATH", ruta_env),
    ):
        with pytest.raises(yaml.YAMLError):
            config_module.reload_config()


def test_config_real_define_seccion_preparacion_y_ruteo() -> None:
    """D33 dependency 10: the real config.yaml carries the `preparacion:`
    section with the keys Module 2 nodes validate (ficha VAL-02) and routes
    location classification to the local provider."""
    config_module.reload_config()
    config = config_module.load()

    preparacion = config["preparacion"]
    assert 0 <= preparacion["umbral_titulo"] <= 100
    assert 0 <= preparacion["umbral_descripcion"] <= 100
    assert preparacion["max_pasadas"] >= 1
    assert preparacion["pausa_entre_ofertas_segundos"] >= 0
    assert preparacion["limite_vida_sesion"] >= 1
    assert preparacion["retries"]["max_attempts"] >= 1

    assert config["ai_routing"]["preparacion"] == "local"
    assert "evaluacion" not in config
    assert "evaluation" not in config["ai_routing"]
    assert config["evaluacion_manual"]["tamano_lote"] >= 1
