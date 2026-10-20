import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from shared.errors import ConfigurationError, LLMError
from shared.ia_service import (
    _get_cloud_config,
    _get_local_config,
    _route_provider,
    _send_cloud,
    _send_local,
    _validate_response,
    analyze,
    load_prompt,
    render_prompt,
)


@pytest.fixture(autouse=True)
def _sin_esperas_de_reintento() -> Generator[None, None, None]:
    """Tenacity waits real time between retries; tests only exercise the
    error-mapping logic, so the retry sleep is neutralized."""
    with patch("time.sleep"):
        yield


def test_render_prompt_simple() -> None:
    template = "Evalua la oferta {{ titulo }} para el rol {{ rol }}"
    context = {"titulo": "Data Engineer", "rol": "Ingeniero de Datos"}
    result = render_prompt(template, context)
    assert "Data Engineer" in result
    assert "Ingeniero de Datos" in result


def test_load_prompt_missing() -> None:
    with pytest.raises(ConfigurationError, match="ER-CFG-001"):
        load_prompt("initial_evaluation/nonexistent")


@patch("shared.ia_service.httpx.post")
def test_send_local_success(mock_post: MagicMock) -> None:
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"response": '{"ok": true}'}

    result = _send_local("test prompt")
    assert result == '{"ok": true}'
    mock_post.assert_called_once()


@patch("shared.ia_service.httpx.post")
def test_send_local_connection_error(mock_post: MagicMock) -> None:
    mock_post.side_effect = httpx.ConnectError("No se pudo conectar")

    with pytest.raises(LLMError, match="ER-LLM-001"):
        _send_local("test prompt")


@patch("shared.ia_service.httpx.post")
def test_send_local_timeout(mock_post: MagicMock) -> None:
    mock_post.side_effect = httpx.TimeoutException("Timeout")

    with pytest.raises(LLMError, match="ER-LLM-002"):
        _send_local("test prompt")


@patch("shared.ia_service.httpx.post")
def test_send_local_incluye_options_del_config(mock_post: MagicMock) -> None:
    """Muestreo determinista (análisis Pereira 2026-08-25): el payload
    local lleva las opciones de muestreo del config oficial ai_local,
    evitando la varianza de los defaults de Ollama (temperature 0.8)."""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"response": "{}"}

    _send_local("test prompt")

    payload = mock_post.call_args.kwargs["json"]
    assert payload["options"] == {"temperature": 0.0}


@patch("shared.ia_service.load")
def test_local_config_sin_options_da_diccionario_vacio(
    mock_load: MagicMock,
) -> None:
    mock_load.return_value = {"ai_local": {"model": "m"}}
    assert _get_local_config()["options"] == {}


@patch("shared.ia_service.load")
def test_local_config_options_invalidas_rechazadas(
    mock_load: MagicMock,
) -> None:
    mock_load.return_value = {"ai_local": {"options": "temperature=0"}}
    with pytest.raises(ConfigurationError, match="ER-CFG-003"):
        _get_local_config()


@patch("shared.ia_service.httpx.post")
def test_send_cloud_success(mock_post: MagicMock) -> None:
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"response": '{"ok": true}'}

    result = _send_cloud("test prompt")
    assert result == '{"ok": true}'
    mock_post.assert_called_once()


@patch("shared.ia_service.httpx.post")
def test_send_cloud_incluye_options_del_config(mock_post: MagicMock) -> None:
    """Espejo del camino local: el payload cloud lleva las opciones de
    muestreo del config oficial ai_cloud."""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"response": "{}"}

    _send_cloud("test prompt")

    payload = mock_post.call_args.kwargs["json"]
    assert payload["options"] == {"temperature": 0.0}


@patch("shared.ia_service.load")
def test_cloud_config_sin_options_da_diccionario_vacio(
    mock_load: MagicMock,
) -> None:
    mock_load.return_value = {"ai_cloud": {"endpoint": "http://x"}}
    assert _get_cloud_config()["options"] == {}


@patch("shared.ia_service.load")
def test_cloud_config_options_invalidas_rechazadas(
    mock_load: MagicMock,
) -> None:
    mock_load.return_value = {"ai_cloud": {"options": [1, 2]}}
    with pytest.raises(ConfigurationError, match="ER-CFG-003"):
        _get_cloud_config()


@patch("shared.ia_service.httpx.post")
def test_send_cloud_connection_error(mock_post: MagicMock) -> None:
    mock_post.side_effect = httpx.ConnectError("No se pudo conectar")

    with pytest.raises(LLMError, match="ER-LLM-001"):
        _send_cloud("test prompt")


@patch("shared.ia_service.httpx.post")
def test_send_cloud_http_error(mock_post: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=mock_response
    )
    mock_post.return_value = mock_response

    with pytest.raises(LLMError, match="ER-LLM-003"):
        _send_cloud("test prompt")


def test_route_provider_ok() -> None:
    assert _route_provider("evaluation") == "cloud"
    assert _route_provider("processing") == "cloud"


@patch("shared.ia_service.load")
def test_route_provider_invalid(mock_load: MagicMock) -> None:
    mock_load.return_value = {
        "ai_routing": {"evaluation": "local", "processing": "aws"}
    }
    with pytest.raises(ConfigurationError, match="ER-CFG-003"):
        _route_provider("processing")


def test_validate_response_ok() -> None:
    result = _validate_response('{"compatibilidad": "alta"}')
    assert result == {"compatibilidad": "alta"}


def test_validate_response_empty() -> None:
    with pytest.raises(LLMError, match="ER-LLM-003"):
        _validate_response("")


def test_validate_response_not_json() -> None:
    with pytest.raises(LLMError, match="ER-LLM-003"):
        _validate_response("no es json")


def test_validate_response_not_dict() -> None:
    with pytest.raises(LLMError, match="ER-LLM-004"):
        _validate_response('["lista", "no valida"]')


@patch("shared.ia_service.httpx.post")
def test_analyze_local(mock_post: MagicMock, tmp_path: Path) -> None:
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    category = prompts_dir / "test_category"
    category.mkdir(parents=True, exist_ok=True)
    prompt_file = category / "test_prompt.md"
    prompt_file.write_text("Evalua {{ titulo }}", encoding="utf-8")

    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "response": json.dumps({"compatibilidad": "alta"})
    }

    result = analyze(
        "test_category/test_prompt",
        {"titulo": "Data Engineer"},
        purpose="evaluation",
    )
    assert result == {"compatibilidad": "alta"}

    prompt_file.unlink()
    category.rmdir()


def test_analyze_sin_reintento_hace_un_solo_intento(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D59: la evaluación desactiva el reintento interno y pasa su espera."""
    from shared import ia_service

    monkeypatch.setattr(ia_service, "load_prompt", lambda _: "plantilla")
    monkeypatch.setattr(ia_service, "render_prompt", lambda template, _: template)
    monkeypatch.setattr(ia_service, "_route_provider", lambda _: "cloud")
    llamado = {"n": 0}

    def _send(prompt: str, timeout: float | None = None) -> str:
        llamado["n"] += 1
        assert timeout == 30
        raise LLMError(
            "002", "Timeout connecting to AI Cloud (30s)", source_module="ia_service"
        )

    monkeypatch.setattr(ia_service, "_send_cloud", _send)
    monkeypatch.setattr(
        ia_service,
        "_send_cloud_con_reintentos",
        MagicMock(side_effect=AssertionError("no debe reintentar")),
    )
    with pytest.raises(LLMError):
        ia_service.analyze("p", {}, timeout=30, reintentar=False)
    assert llamado["n"] == 1


def test_analyze_por_defecto_conserva_el_reintento_compartido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Los propósitos que no rotan siguen usando la política de reintentos."""
    from shared import ia_service

    monkeypatch.setattr(ia_service, "load_prompt", lambda _: "plantilla")
    monkeypatch.setattr(ia_service, "render_prompt", lambda template, _: template)
    monkeypatch.setattr(ia_service, "_route_provider", lambda _: "cloud")
    llamado = {"n": 0}

    def _send(prompt: str, timeout: float | None = None) -> str:
        llamado["n"] += 1
        assert timeout == 45
        return '{"ok": true}'

    monkeypatch.setattr(ia_service, "_send_cloud_con_reintentos", _send)
    monkeypatch.setattr(
        ia_service,
        "_send_cloud",
        MagicMock(side_effect=AssertionError("debe usar el envoltorio")),
    )
    assert ia_service.analyze("p", {}, timeout=45) == {"ok": True}
    assert llamado["n"] == 1


def test_analyze_openrouter_pasa_el_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    from shared import ia_service

    monkeypatch.setattr(ia_service, "load_prompt", lambda _: "plantilla")
    monkeypatch.setattr(ia_service, "render_prompt", lambda template, _: template)
    llamado: dict[str, object] = {}

    def _send(
        prompt: str, modelo: str, referencia_clave: str, timeout: float | None = None
    ) -> str:
        llamado.update(modelo=modelo, clave=referencia_clave, timeout=timeout)
        return '{"ok": true}'

    monkeypatch.setattr(ia_service, "_send_openrouter", _send)
    res = ia_service.analyze_openrouter(
        "p", {}, "google/gemma-4-31b-it", "OPENROUTER_API_KEY_1", timeout=25
    )
    assert res == {"ok": True}
    assert llamado == {
        "modelo": "google/gemma-4-31b-it",
        "clave": "OPENROUTER_API_KEY_1",
        "timeout": 25,
    }


def test_send_openrouter_pasa_el_timeout_a_httpx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D59: la espera por puerta llega al POST de la puerta alterna."""
    from shared import config as config_module
    from shared import ia_service

    real = config_module.load()
    fake = {**real, "_env": {"OPENROUTER_API_KEY_1": "clave"}}
    monkeypatch.setattr(ia_service, "load", lambda: fake)
    with patch("shared.ia_service.httpx.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "{}"}}]
        }
        ia_service._send_openrouter(
            "prompt", "google/gemma-4-31b-it", "OPENROUTER_API_KEY_1", timeout=25
        )
    assert mock_post.call_args.kwargs["timeout"] == 25
