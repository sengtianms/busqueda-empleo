"""Validación de los ajustes de Evaluación inicial (Previo Fase 6, D48).

Valida la sección `evaluacion:` completa más la ruta existente de la
inteligencia (`ai_routing.evaluation` con su modelo declarado). La usa el
prevuelo desde ya; el INICIO del Módulo 3 (6.1) la reutilizará en espejo
de `_validar_preparacion` en lugar de duplicarla.
"""

from typing import Any, TypeGuard


def _es_numero(valor: Any) -> TypeGuard[int | float]:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _es_entero(valor: Any, minimo: int) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= minimo


def validar_evaluacion(
    seccion: Any, configuracion: Any = None
) -> str | None:
    """VAL-02 del Módulo 3: valida sección y ruta; devuelve explicación o None."""
    if not isinstance(seccion, dict):
        return "seccion 'evaluacion' ausente o no es un objeto"
    pausa = seccion.get("pausa_entre_ofertas_segundos")
    if not _es_numero(pausa) or pausa < 0:
        return "pausa_entre_ofertas_segundos invalida (numerico >= 0)"
    jitter = seccion.get("pausa_jitter_segundos")
    if jitter is not None and (not _es_numero(jitter) or jitter < 0):
        return "pausa_jitter_segundos invalida (numerico >= 0)"
    timeout_puerta = seccion.get("timeout_puerta_segundos")
    if not _es_numero(timeout_puerta) or timeout_puerta <= 0:
        return "timeout_puerta_segundos invalido (numerico > 0)"
    reintentos = seccion.get("retries")
    if not isinstance(reintentos, dict):
        return "retries ausente o no es un objeto"
    if reintentos.get("max_attempts") != 2:
        return "retries.max_attempts invalido (ficha M3: exactamente 2)"
    espera_base = reintentos.get("base_wait_seconds")
    if not _es_numero(espera_base) or espera_base < 0:
        return "retries.base_wait_seconds invalido (numerico >= 0)"
    espera_max = reintentos.get("max_wait_seconds")
    if not _es_numero(espera_max) or espera_max < espera_base:
        return "retries.max_wait_seconds invalido (numerico >= base_wait_seconds)"
    multiplicador = reintentos.get("multiplier")
    if not _es_numero(multiplicador) or multiplicador < 1:
        return "retries.multiplier invalido (numerico >= 1)"
    puertas = seccion.get("puertas_alternas")
    if puertas is None:
        return "puertas_alternas ausente (lista, vacia hasta la construccion)"
    if not isinstance(puertas, list):
        return "puertas_alternas invalida (debe ser lista en orden)"
    for puerta in puertas:
        if not isinstance(puerta, dict):
            return "puertas_alternas invalida (cada puerta debe ser un objeto)"
        nombre = puerta.get("nombre", "")
        if not isinstance(nombre, str):
            return "puertas_alternas invalida (nombre de puerta debe ser texto)"
        modelo = puerta.get("modelo", "")
        if not isinstance(modelo, str) or not modelo.strip():
            return "puertas_alternas invalida (cada puerta requiere 'modelo')"
        clave_ref = puerta.get("clave_ref", "")
        if not isinstance(clave_ref, str) or not clave_ref.strip():
            return "puertas_alternas invalida (cada puerta requiere 'clave_ref')"
    if configuracion is None:
        return "configuracion global ausente (ruta ai_routing.evaluation)"
    if not isinstance(configuracion, dict):
        return "configuracion global invalida (no es un objeto)"
    ruteo = configuracion.get("ai_routing")
    if not isinstance(ruteo, dict) or ruteo.get("evaluation") not in (
        "cloud",
        "local",
    ):
        return "ai_routing.evaluation invalida (debe ser 'cloud' o 'local')"
    destino = str(ruteo["evaluation"])
    seccion_ia = configuracion.get(f"ai_{destino}")
    modelo = seccion_ia.get("model") if isinstance(seccion_ia, dict) else None
    if not modelo or not str(modelo).strip():
        return f"modelo de la ruta '{destino}' ausente (ai_{destino}.model)"
    return None
