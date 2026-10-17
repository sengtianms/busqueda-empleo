import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

from tenacity import (
    before_sleep_log,
    stop_after_attempt,
    wait_exponential,
)
from tenacity import (
    retry as tenacity_retry,
)

from shared.config import load

_logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")
TResult = TypeVar("TResult")

# Codes that may be retried (DOC-06, Section 11 / RN-03-RN-06 of the technical
# sheet). Includes network-level unavailability and timeouts; excludes codes
# that compromise the source (Grupo A, e.g. bloqueo_plataforma) and those that
# would not change on retry (e.g. autenticacion_rechazada).
_CODIGOS_REINTENTABLES = (
    "fuente_inalcanzable",
    "tiempo_agotado_ingreso",
    "tiempo_agotado_consulta",
    "tiempo_agotado_captura",
    # Module 2 capture codes (ficha M2 ERR-02/03/04): same retryable nature —
    # a fresh guest session or backoff can succeed on a later attempt.
    "pagina_inalcanzable",
    "authwall_detectado",
    # Module 2 local nodes (ficha M2 Verificación ERR-01 / decisión de bucle
    # ERR-01): a transient SQLite failure can succeed on a later attempt.
    "error_bd",
    # Module 3 evaluation (ficha M3 ERR-02/ERR-03): a down door/quota wall or
    # an invalid AI answer can succeed on a later attempt (same door for an
    # invalid answer, next door for a verified door failure).
    "puerta_evaluacion_no_disponible",
    "respuesta_evaluacion_invalida",
)


def _policies() -> dict[str, Any]:
    cfg = load().get("retries", {})
    return {
        "max_attempts": cfg.get("max_attempts", 3),
        "base_wait": cfg.get("base_wait_seconds", 2),
        "max_wait": cfg.get("max_wait_seconds", 30),
        "multiplier": cfg.get("multiplier", 2),
    }


def retry_decorator(
    max_attempts: int | None = None,
    base_wait: float | None = None,
    max_wait: float | None = None,
    multiplier: float | None = None,
) -> Callable[[F], F]:
    policy = _policies()
    return tenacity_retry(
        stop=stop_after_attempt(max_attempts or policy["max_attempts"]),
        wait=wait_exponential(
            multiplier=multiplier or policy["multiplier"],
            min=base_wait or policy["base_wait"],
            max=max_wait or policy["max_wait"],
        ),
        before_sleep=before_sleep_log(_logger, logging.WARNING),
        reraise=True,
    )


def should_retry(codigo_motivo: str) -> bool:
    return codigo_motivo in _CODIGOS_REINTENTABLES


def _codigo_motivo(exc: BaseException) -> str | None:
    """Devuelve el `codigo_motivo` solo si es un código de flujo (str).

    No se considera el atributo `code` de `BaseError`/`NetworkError`: el
    despacho del helper es exclusivamente por código de flujo, y las
    excepciones de la capa de errores caen en `al_error_interno` (o se
    re-lanzan), como hacían los bucles manuales previos (`except Exception`).
    """
    codigo = getattr(exc, "codigo_motivo", None)
    if isinstance(codigo, str):
        return codigo
    return None


def ejecutar_con_reintento(
    fn: Callable[[], T],
    *,
    al_fallo_final: Callable[[BaseException, int], TResult] | None = None,
    al_error_interno: Callable[[Exception, int], TResult] | None = None,
    al_reintento: Callable[[], None] | None = None,
    max_attempts: int | None = None,
    base_wait: float | None = None,
    multiplier: float | None = None,
    max_wait: float | None = None,
    contexto_log: str = "",
) -> tuple[T | TResult, int]:
    """Runs `fn` with conditional retry (`should_retry`) and config-driven backoff.

    Returns `(resultado, intentos)`. A failure carrying a retryable
    `codigo_motivo` backs off (calling `al_reintento` first) up to
    `max_attempts`; once exhausted — or when the code is not retryable —
    `al_fallo_final(exc, intentos)` is called if provided, otherwise the
    exception is re-raised. Any other exception goes to
    `al_error_interno(exc, intentos)` if provided, otherwise it is re-raised.
    """
    policy = _policies()
    max_attempts = (
        max_attempts if max_attempts is not None else int(policy["max_attempts"])
    )
    base_wait = (
        base_wait if base_wait is not None else float(policy["base_wait"])
    )
    multiplier = (
        multiplier if multiplier is not None else float(policy["multiplier"])
    )
    max_wait = max_wait if max_wait is not None else float(policy["max_wait"])

    if max_attempts < 1:
        error = RuntimeError("no attempts configured")
        if al_error_interno is not None:
            return al_error_interno(error, 0), 0
        raise error

    intento = 0
    while intento < max_attempts:
        intento += 1
        try:
            return fn(), intento
        except Exception as exc:
            codigo = _codigo_motivo(exc)
            if codigo is not None and should_retry(codigo) and intento < max_attempts:
                if al_reintento is not None:
                    al_reintento()
                _logger.warning(
                    f"Reintentando tras {codigo} (intento {intento}/{max_attempts})"
                    f"{f' | {contexto_log}' if contexto_log else ''}"
                )
                wait_time = min(
                    base_wait * (multiplier ** (intento - 1)), max_wait
                )
                time.sleep(wait_time)
                continue
            if codigo is not None and al_fallo_final is not None:
                return al_fallo_final(exc, intento), intento
            if al_error_interno is not None:
                return al_error_interno(exc, intento), intento
            raise

    # Unreachable with max_attempts >= 1; satisfies mypy strict.
    raise RuntimeError("no attempts configured")
