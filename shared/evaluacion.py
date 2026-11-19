"""Validación de la evaluación inicial sin inteligencia artificial (D76).

Valida la sección `evaluacion_manual:` de los dos procesos (exportación e
importación) y reúne la limpieza de descripción compartida por la exportación
de lotes. El validador del antiguo flujo con IA y su ruta de modelo se
retiraron al cerrar la Fase 4; el prompt de compatibilidad sigue vigente como
fuente de la instrucción que se entrega al chat.
"""

from typing import Any, TypeGuard


def _es_numero(valor: Any) -> TypeGuard[int | float]:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _es_entero(valor: Any, minimo: int) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= minimo


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
