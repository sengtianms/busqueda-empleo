"""Helpers compartidos (catálogo español D7/D8): evidencia acotada, timestamps y normalización."""

import unicodedata
from datetime import datetime
from typing import Any

FORMATO_TIMESTAMP = "%Y-%m-%d %H:%M:%S"

TIPOS_ACCESO = ("publico", "con_autenticacion")

# Ajustes de la ventana del Módulo 1 (sección `browser:` del config):
# tamaño normal de ventana y espera máxima del ingreso manual con memoria.
VENTANA_ANCHO_DEFECTO = 1600
VENTANA_ALTO_DEFECTO = 900
ESPERA_MANUAL_DEFECTO_SEGUNDOS = 300

_SUFIJO_TRUNCAMIENTO = "..."


def acotar_evidencia(texto: str, maximo: int = 300) -> str:
    """Truncates long evidence texts keeping the DB `evidencia` bounded."""
    if len(texto) <= maximo:
        return texto
    return texto[:maximo] + _SUFIJO_TRUNCAMIENTO


def ahora() -> str:
    """Timestamp canónico de corrida (misma marca para BD, eventos y contexto)."""
    return datetime.now().strftime(FORMATO_TIMESTAMP)


def normalizar_texto(texto: str) -> str:
    """Normaliza texto para dedup (D33): minúsculas, sin acentos,
    sin puntuación, espacios simples.

    Usada por el Módulo 2 para la tupla de ubicación y los títulos de la
    verificación de duplicidad. Texto vacío devuelve cadena vacía (el
    llamador aplica la regla D31).
    """
    if not texto:
        return ""
    sin_acentos = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(caracter) != "Mn"
    )
    sin_puntuacion = "".join(
        caracter if caracter.isalnum() else " " for caracter in sin_acentos
    )
    return " ".join(sin_puntuacion.split())


def normalizar_nombre_empresa(texto: str) -> str:
    """Clave del catálogo `empresas.nombre_normalizado` (D41): minúsculas y
    espacios múltiples colapsados; conserva TODOS los caracteres (tildes,
    ñ, puntuación, símbolos como `&`, `.`, paréntesis).

    Sustituye a `normalizar_texto` solo para nombres de empresa — ubicaciones
    y títulos de duplicidad mantienen la regla estricta. Texto vacío
    devuelve cadena vacía (el llamador aplica la regla D31).
    """
    if not texto:
        return ""
    return " ".join(texto.lower().split())


def numero_secuencial_id(id_valor: str) -> int:
    """Número secuencial de un identificador oficial (`PREFIJO-NNNN`, anexo 5A).

    Clave numérica para ordenar y comparar identificadores por ciclo de vida
    (D53): la comparación lexicográfica se rompe a partir de
    10.000 ('OFE-9999' > 'OFE-10000' por texto, aunque 9999 es más antiguo).
    'OFE-0042' → 42; 'OFE-9999' → 9999; 'OFE-10000' → 10000. Devuelve 0 ante
    un valor sin parte numérica final (defensivo; no ocurre en producción).
    """
    if not id_valor:
        return 0
    parte = id_valor.rsplit("-", 1)[-1]
    try:
        return int(parte)
    except ValueError:
        return 0


def _entero_positivo(valor: Any, defecto: int) -> int:
    """Entero positivo tolerante para ajustes numéricos (0/negativo → defecto)."""
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return defecto
    return numero if numero > 0 else defecto


def ruta_perfil_navegador(navegador: Any) -> str:
    """Carpeta de sesión persistente (`browser.profile_path`); "" = sin memoria."""
    if not isinstance(navegador, dict):
        return ""
    valor = navegador.get("profile_path", "")
    return valor.strip() if isinstance(valor, str) else ""


def ventana_navegador(navegador: Any) -> tuple[int, int]:
    """Tamaño normal de la ventana del Módulo 1 (`ventana_ancho/alto`)."""
    if not isinstance(navegador, dict):
        return (VENTANA_ANCHO_DEFECTO, VENTANA_ALTO_DEFECTO)
    return (
        _entero_positivo(navegador.get("ventana_ancho"), VENTANA_ANCHO_DEFECTO),
        _entero_positivo(navegador.get("ventana_alto"), VENTANA_ALTO_DEFECTO),
    )


def espera_manual_navegador(navegador: Any, defecto: int = ESPERA_MANUAL_DEFECTO_SEGUNDOS) -> int:
    """Espera máxima del ingreso manual (`espera_manual_segundos`)."""
    if not isinstance(navegador, dict):
        return defecto
    return _entero_positivo(navegador.get("espera_manual_segundos"), defecto)
