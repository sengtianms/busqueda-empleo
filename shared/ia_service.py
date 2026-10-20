import json
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from shared.config import load
from shared.errors import ConfigurationError, LLMError
from shared.retry import retry_decorator

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PROMPTS_PATH = _PROJECT_ROOT / "prompts"


def _prompt_path(prompt_id: str) -> Path:
    path = _PROMPTS_PATH / prompt_id
    if not path.suffix:
        path = path.with_suffix(".md")
    return path


def load_prompt(prompt_id: str) -> str:
    path = _prompt_path(prompt_id)
    if not path.exists():
        raise ConfigurationError(
            "001",
            f"Prompt not found: {path}",
            source_module="ia_service",
        )
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, context: dict[str, Any]) -> str:
    result = template
    for key, value in context.items():
        result = result.replace("{{ " + key + " }}", str(value))
        result = result.replace("{{" + key + "}}", str(value))
    return result


def _route_provider(purpose: str) -> str:
    config = load()
    routing = config.get("ai_routing", {})
    provider = routing.get(purpose, "local")
    if not isinstance(provider, str):
        provider = "local"
    if provider not in ("local", "cloud"):
        raise ConfigurationError(
            "003",
            f"Invalid AI provider for purpose '{purpose}': '{provider}'. "
            f"Allowed values: 'local', 'cloud'",
            source_module="ia_service",
        )
    return provider


def _get_local_config() -> dict[str, Any]:
    config = load()
    local_cfg = config.get("ai_local", {})
    env = config.get("_env", {})
    options = local_cfg.get("options", {})
    if not isinstance(options, dict):
        raise ConfigurationError(
            "003",
            f"'ai_local.options' must be a mapping, got {type(options).__name__}",
            source_module="ia_service",
        )
    return {
        "host": env.get("OLLAMA_HOST") or local_cfg.get("host", "localhost"),
        "port": int(env.get("OLLAMA_PORT") or local_cfg.get("port", 11434)),
        "model": env.get("OLLAMA_MODEL") or local_cfg.get("model", "qwen3.5:4b"),
        "timeout": int(local_cfg.get("timeout_seconds", 60)),
        "options": dict(options),
    }


def _get_cloud_config() -> dict[str, Any]:
    config = load()
    cloud_cfg = config.get("ai_cloud", {})
    env = config.get("_env", {})
    options = cloud_cfg.get("options", {})
    if not isinstance(options, dict):
        raise ConfigurationError(
            "003",
            f"'ai_cloud.options' must be a mapping, got {type(options).__name__}",
            source_module="ia_service",
        )
    return {
        "endpoint": env.get("IA_CLOUD_ENDPOINT") or cloud_cfg.get("endpoint", ""),
        "model": cloud_cfg.get("model", "gemma4:31b"),
        "api_key": env.get("IA_CLOUD_API_KEY") or "",
        "timeout": int(cloud_cfg.get("timeout_seconds", 120)),
        "options": dict(options),
    }


def _enviar(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
    servicio: str,
) -> str:
    """POST a un endpoint IA con el mapeo de errores común (LLM-001..003)."""
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return str(data.get("response", ""))
    except httpx.ConnectError:
        raise LLMError(
            "001",
            f"Could not connect to {servicio} at {url}",
            source_module="ia_service",
        )
    except httpx.TimeoutException:
        raise LLMError(
            "002",
            f"Timeout connecting to {servicio} ({timeout}s)",
            source_module="ia_service",
        )
    except httpx.HTTPStatusError as e:
        raise LLMError(
            "003",
            f"{servicio} responded with code {e.response.status_code}",
            source_module="ia_service",
        )


@retry_decorator()
def _send_local(prompt: str) -> str:
    cfg = _get_local_config()
    payload: dict[str, Any] = {
        "model": cfg["model"],
        "prompt": prompt,
        "stream": False,
    }
    if cfg["options"]:
        payload["options"] = cfg["options"]
    return _enviar(
        f"http://{cfg['host']}:{cfg['port']}/api/generate",
        {"Content-Type": "application/json"},
        payload,
        cfg["timeout"],
        "local Ollama",
    )


def _send_cloud(prompt: str, timeout: float | None = None) -> str:
    """Un intento a la ruta cloud, sin reintentos internos (D59).

    El llamador decide la política: la evaluación rota de puerta al primer
    fallo (su nodo es dueño de los intentos); los propósitos que no rotan
    usan `_send_cloud_con_reintentos`.
    """
    cfg = _get_cloud_config()
    headers: dict[str, str] = {
        "Content-Type": "application/json",
    }
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    payload: dict[str, Any] = {
        "model": cfg["model"],
        "prompt": prompt,
        "stream": False,
    }
    if cfg["options"]:
        payload["options"] = cfg["options"]
    return _enviar(
        f"{cfg['endpoint']}/api/generate",
        headers,
        payload,
        float(timeout) if timeout is not None else cfg["timeout"],
        "AI Cloud",
    )


@retry_decorator()
def _send_cloud_con_reintentos(prompt: str, timeout: float | None = None) -> str:
    """Cloud route with the shared retry policy (default `analyze` path)."""
    return _send_cloud(prompt, timeout)


def _validate_response(raw_response: str) -> dict[str, Any]:
    if not raw_response.strip():
        raise LLMError(
            "003",
            "Empty response from AI model",
            source_module="ia_service",
        )
    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError:
        raise LLMError(
            "003",
            "Response is not valid JSON",
            source_module="ia_service",
        )
    if not isinstance(data, dict):
        raise LLMError(
            "004",
            "Unexpected response format: expected a dictionary",
            source_module="ia_service",
        )
    return data


def analyze(
    prompt_id: str,
    context: dict[str, Any],
    purpose: str = "evaluation",
    *,
    timeout: float | None = None,
    reintentar: bool = True,
) -> dict[str, Any]:
    """Renders a prompt and asks the routed provider.

    `timeout` overrides the route's configured wait. `reintentar=False`
    skips the shared retry wrapper so the caller can rotate providers on
    the first failure (evaluation door policy, D59).
    """
    template = load_prompt(prompt_id)
    final_prompt = render_prompt(template, context)

    provider = _route_provider(purpose)
    logger.debug("Sending prompt to AI | prompt_id={} | provider={}", prompt_id, provider)

    if provider == "cloud":
        if reintentar:
            raw_response = _send_cloud_con_reintentos(final_prompt, timeout)
        else:
            raw_response = _send_cloud(final_prompt, timeout)
    else:
        raw_response = _send_local(final_prompt)

    logger.debug("Response received from AI | prompt_id={} | provider={}", prompt_id, provider)
    return _validate_response(raw_response)


_URL_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"


def _clave_openrouter(referencia: str) -> str:
    """Reads an alternate-door key from the private file (never the repo).

    Keys live only in `config/.env` (loaded into `config["_env"]`); here
    only their reference names travel (ficha M3 pending item 1).
    """
    env = load().get("_env", {})
    clave = env.get(referencia, "") if isinstance(env, dict) else ""
    if not clave or not str(clave).strip():
        raise ConfigurationError(
            "003",
            f"Missing private key '{referencia}' (config/.env)",
            source_module="ia_service",
        )
    return str(clave)


def _send_openrouter(
    prompt: str, modelo: str, referencia_clave: str, timeout: float | None = None
) -> str:
    """POST a prompt to an OpenRouter alternate door (same-model rotation).

    No retry decorator here: the evaluation node owns attempts and door
    rotation (ficha M3 RN-07). Quota exhaustion surfaces with its status so
    the node can close by quota in order. Timeout and sampling follow the
    `ai_cloud` settings (D45 determinism), like the principal cloud route;
    `timeout` overrides the configured wait per door (D59).
    """
    clave = _clave_openrouter(referencia_clave)
    nube = _get_cloud_config()
    espera = float(timeout) if timeout is not None else float(nube.get("timeout", 120))
    opciones = nube.get("options", {})
    temperatura = float(opciones.get("temperature", 0.0)) if isinstance(opciones, dict) else 0.0
    try:
        respuesta = httpx.post(
            _URL_OPENROUTER,
            json={
                "model": modelo,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperatura,
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {clave}",
            },
            timeout=espera,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
        opciones = datos.get("choices", [])
        if not opciones:
            raise LLMError(
                "003",
                "OpenRouter response without choices",
                source_module="ia_service",
            )
        return str(opciones[0].get("message", {}).get("content", ""))
    except httpx.ConnectError:
        raise LLMError(
            "001",
            "Could not connect to OpenRouter",
            source_module="ia_service",
        )
    except httpx.TimeoutException:
        raise LLMError(
            "002",
            f"Timeout connecting to OpenRouter ({espera}s)",
            source_module="ia_service",
        )
    except httpx.HTTPStatusError as e:
        codigo = e.response.status_code
        if codigo in (401, 403):
            raise LLMError(
                "003",
                f"OpenRouter key rejected (status {codigo})",
                source_module="ia_service",
            )
        if codigo == 429:
            raise LLMError(
                "003",
                "OpenRouter quota exhausted (status 429)",
                source_module="ia_service",
            )
        raise LLMError(
            "003",
            f"OpenRouter responded with code {codigo}",
            source_module="ia_service",
        )


def analyze_openrouter(
    prompt_id: str,
    context: dict[str, Any],
    modelo: str,
    referencia_clave: str,
    *,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Evaluates a prompt through an OpenRouter alternate door."""
    template = load_prompt(prompt_id)
    final_prompt = render_prompt(template, context)
    logger.debug(
        "Sending prompt to alternate door | prompt_id={} | model={}",
        prompt_id,
        modelo,
    )
    raw_response = _send_openrouter(final_prompt, modelo, referencia_clave, timeout)
    logger.debug(
        "Response received from alternate door | prompt_id={} | model={}",
        prompt_id,
        modelo,
    )
    return _validate_response(raw_response)
