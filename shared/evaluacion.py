"""Validación de los ajustes de Evaluación inicial (Previo Fase 6, D48).

Valida la sección `evaluacion:` completa más la ruta existente de la
inteligencia (`ai_routing.evaluation` con su modelo declarado). La usa el
prevuelo desde ya; el INICIO del Módulo 3 (6.1) la reutilizará en espejo
de `_validar_preparacion` en lugar de duplicarla.

Desde el rediseño del Módulo 3 (D76) convive con `validar_evaluacion_manual`,
que valida la sección `evaluacion_manual:` de los dos procesos sin
inteligencia artificial. Ambas coexisten hasta que la Fase 4 retire la ruta
antigua; el validador viejo no cambia en la Fase 1.

La Fase 2 añade la limpieza de descripción compartida por la exportación de
lotes. Reproduce el criterio D49 que ya aplicaba el nodo de evaluación con IA
(el cual se conserva intacto hasta la Fase 4) y devuelve además si hubo
recorte, para que el lote pueda avisar al evaluador.
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


def _validar_reintentos_manual(reintentos: Any) -> str | None:
    """Coherencia del bloque `retries` de la sección manual."""
    if not isinstance(reintentos, dict):
        return "retries ausente o no es un objeto"
    if not _es_entero(reintentos.get("max_attempts"), 1):
        return "retries.max_attempts invalido (entero >= 1)"
    espera_base = reintentos.get("base_wait_seconds")
    if not _es_numero(espera_base) or espera_base < 0:
        return "retries.base_wait_seconds invalido (numerico >= 0)"
    espera_max = reintentos.get("max_wait_seconds")
    if not _es_numero(espera_max) or espera_max < espera_base:
        return "retries.max_wait_seconds invalido (numerico >= base_wait_seconds)"
    multiplicador = reintentos.get("multiplier")
    if not _es_numero(multiplicador) or multiplicador < 1:
        return "retries.multiplier invalido (numerico >= 1)"
    return None


def validar_evaluacion_manual(seccion: Any) -> str | None:
    """VAL-02 del Módulo 3 v2.0: valida toda la sección `evaluacion_manual:`.

    Exige `carpeta_base` no vacía, `tamano_lote` entero >= 1, `modelo_evaluador`
    no vacío y `retries` coherente. No valida ninguna ruta de inteligencia
    artificial: los dos procesos manuales no la usan. Devuelve la explicación
    del primer problema o None si la sección es válida.
    """
    if not isinstance(seccion, dict):
        return "seccion 'evaluacion_manual' ausente o no es un objeto"
    carpeta = seccion.get("carpeta_base")
    if not isinstance(carpeta, str) or not carpeta.strip():
        return "carpeta_base invalida (texto no vacio)"
    if not _es_entero(seccion.get("tamano_lote"), 1):
        return "tamano_lote invalido (entero >= 1)"
    modelo = seccion.get("modelo_evaluador")
    if not isinstance(modelo, str) or not modelo.strip():
        return "modelo_evaluador invalido (texto no vacio)"
    return _validar_reintentos_manual(seccion.get("retries"))


# --- Limpieza de la descripción para la evaluación (Fase 2, D76) ------------
# Mismo criterio que el nodo de IA (`_limpiar_descripcion_para_ia`, D49): se
# quitan las secciones de ruido al inicio y al final y se acota el texto a un
# tope alto de seguridad. El original de la base nunca se modifica; aquí solo
# se prepara lo que se entrega al evaluador en el archivo del lote.

LIMITE_DESCRIPCION_EVALUACION = 6000

_ENCABEZADOS_RUIDO = frozenset(
    {
        "about us",
        "about the company",
        "who we are",
        "why join us",
        "what we offer",
        "what we can offer you",
        "benefits",
        "your benefits",
        "perks",
        "equal opportunity",
        "equal opportunity employer",
        "diversity and inclusion",
        "diversity & inclusion",
        "reasonable accommodation",
        "disclaimer",
        "privacy notice",
        "privacy policy",
        "eeo statement",
        "quienes somos",
        "quiénes somos",
        "acerca de la empresa",
        "sobre nosotros",
        "nuestra empresa",
        "beneficios",
        "lo que ofrecemos",
        "igualdad de oportunidades",
        "diversidad e inclusion",
        "diversidad e inclusión",
        "aviso de privacidad",
        "descargo de responsabilidad",
    }
)

_ENCABEZADOS_ROL = frozenset(
    {
        "about the role",
        "the role",
        "the position",
        "position overview",
        "job description",
        "job summary",
        "responsibilities",
        "key responsibilities",
        "essential duties",
        "what you'll do",
        "what you will do",
        "requirements",
        "qualifications",
        "basic qualifications",
        "preferred qualifications",
        "what you bring",
        "skills and experience",
        "responsabilidades",
        "requisitos",
        "calificaciones",
        "funciones",
        "funciones principales",
        "perfil requerido",
        "acerca del rol",
        "descripcion del puesto",
        "descripción del puesto",
        "lo que haras",
        "lo que harás",
    }
)


def _es_encabezado(linea: str, encabezados: frozenset[str]) -> bool:
    norma = " ".join(linea.strip().lower().split())
    if norma.endswith(":"):
        norma = norma[:-1]
    return norma in encabezados


def limpiar_descripcion_para_evaluacion(descripcion: str) -> tuple[str, bool]:
    """Devuelve ``(texto, recortado)`` con la higiene D49 del evaluador.

    Si la limpieza vaciara todo, devuelve el original intacto y ``False``.
    El texto original sigue en la base; este resultado es solo para el lote.
    """
    lineas = (descripcion or "").split("\n")
    conservadas: list[str] = []
    saltando = False
    for linea in lineas:
        if _es_encabezado(linea, _ENCABEZADOS_RUIDO):
            saltando = True
            continue
        if _es_encabezado(linea, _ENCABEZADOS_ROL):
            saltando = False
            conservadas.append(linea)
            continue
        if not saltando:
            conservadas.append(linea)
    limpio = "\n".join(conservadas).strip()
    if not limpio:
        return descripcion, False
    recortado = len(limpio) > LIMITE_DESCRIPCION_EVALUACION
    if recortado:
        limpio = limpio[:LIMITE_DESCRIPCION_EVALUACION].rstrip()
    return limpio, recortado
