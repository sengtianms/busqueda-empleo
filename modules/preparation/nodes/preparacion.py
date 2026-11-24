"""Preparación de ofertas node of the Preparation flow (ficha M2 v2.1).

Process node, single lot per pass (sheet pasos funcionales 1-9). For every
offer in `descubierta` (FIFO): capture the offer page without login (guest
httpx session with browser headers, no Playwright on the critical path —
D4), populate the `empresas` catalog (dedup by `nombre_normalizado`, no AI)
and link the location against the master `ubicaciones` catalogue read once
per run. When the deterministic engine does not recognize the text, Gemma
via OpenRouter resolves; the offer is always linked to a real catalogue row,
creating it (marked as sistema) only when the municipality does not exist.
No writes to `ubicaciones` from the deterministic path. Update the offer and
write the per-offer event with `id_oferta` (RN-09). Duplication is NOT
verified here (next node) and `fecha_ultima_verificacion` is never touched
(RN-11).

Interpretation note: the sheet's functional-step table maps the lot
determination failure to ERR-05, but ERR-05 in this node's error table is
`respuesta_invalida` (capture). A database failure while determining lots is
therefore registered as ERR-09 (persistence corruption family) and aborts
the run, consistent with the abort branch of the sheet.
"""

import random
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag
from loguru import logger
from pydantic import BaseModel, ValidationError

from modules.preparation.nodes.inicio import _validar_preparacion
from modules.preparation.run_context import RunContext
from modules.preparation.ubicaciones import (
    PENDIENTE,
    CatalogoUbicaciones,
    normalizar_pais,
    resolver_area_metropolitana,
)
from shared.ia_service import analyze, analyze_openrouter
from shared.persistence import (
    actualizar_fila,
    crear_o_reutilizar_ubicacion,
    escribir_fila,
    leer_candidatas_descubiertas,
    leer_tabla,
    registrar_evento,
)
from shared.retry import ejecutar_con_reintento
from shared.utilidades import normalizar_nombre_empresa, normalizar_texto

# Technical capture constants (module-level like Module 1 selector constants;
# business parameters — pauses, retries, session lifetime — come from config).
BASE_LINKEDIN = "https://www.linkedin.com"
TIMEOUT_CAPTURA_SEGUNDOS = 15.0
HEADERS_NAVEGADOR = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
}
# Authwall multi-signal heuristic (approved in the 5.3 analysis): atypical
# HTTP statuses, login/authwall redirects, or known wall markers in the body.
ESTADOS_AUTHWALL_HTTP = {999, 429}
MARCADORES_AUTHWALL = (
    "authwall",
    "sign up | linkedin",
    "join linkedin",
    "iniciar sesion para continuar",
)
PROMPT_UBICACION = "preparacion/ubicacion"


class ClasificacionUbicacion(BaseModel):
    """Validated `{municipio, departamento, pais}` JSON returned by PRM-006."""

    municipio: str = "N/A"
    departamento: str = "N/A"
    pais: str = "N/A"


class FalloPreparacion(Exception):
    """Failure carrying a sheet flow code (`codigo_motivo`) for the retry
    helper; created by the capture steps and the local nodes' DB reads."""

    def __init__(self, codigo_motivo: str, detalle: str) -> None:
        super().__init__(f"{codigo_motivo}: {detalle}")
        self.codigo_motivo = codigo_motivo
        self.detalle = detalle


@dataclass
class ResultadoPreparacion:
    """Outcome handed to the flow: `completada` or `abortada` (ERR-01/09)."""

    estado: str
    contexto: RunContext | None = None
    codigo: str = ""
    descripcion: str = ""


@dataclass
class DatosCaptura:
    """Raw data extracted from one offer page (paso 1).

    La ubicación se extrae del span de la página para enriquecer la columna
    `ubicacion` con el texto completo. La modalidad no se extrae aquí.
    """

    titulo_h1: str | None
    descripcion: str
    empresa_nombre: str
    empresa_perfil: str
    ubicacion_pagina: str = ""


def _construir_cliente() -> httpx.Client:
    """Guest-session factory; tests replace it with a MockTransport client."""
    return httpx.Client(
        headers=HEADERS_NAVEGADOR,
        follow_redirects=True,
        timeout=TIMEOUT_CAPTURA_SEGUNDOS,
    )


def _obtener_sesion(contexto: RunContext, renovar: bool = False) -> httpx.Client:
    """RN-03: reuse the session; renew at `limite_vida_sesion` or on demand."""
    limite = int(contexto.config_preparacion["limite_vida_sesion"])
    cliente = contexto.sesion_http
    if (
        isinstance(cliente, httpx.Client)
        and not renovar
        and contexto.ofertas_en_sesion < limite
    ):
        return cliente
    if isinstance(cliente, httpx.Client):
        try:
            cliente.close()
        except Exception:  # pragma: no cover - close is best-effort
            pass
    cliente = _construir_cliente()
    contexto.sesion_http = cliente
    contexto.ofertas_en_sesion = 0
    return cliente


def _es_authwall(respuesta: httpx.Response) -> bool:
    """Multi-signal wall detection: status, final URL and body markers."""
    if respuesta.status_code in ESTADOS_AUTHWALL_HTTP:
        return True
    url_final = str(respuesta.url).lower()
    if "/authwall" in url_final or "login" in url_final:
        return True
    cuerpo = respuesta.text[:20000].lower()
    return any(marcador in cuerpo for marcador in MARCADORES_AUTHWALL)


_ETIQUETAS_BLOQUE: tuple[str, ...] = (
    "p", "div", "li", "tr", "section",
    "h1", "h2", "h3", "h4", "h5", "h6",
)

_MARCA_SALTO = "\u0001"


def _texto_con_estructura(nodo: Tag) -> str:
    """Texto visible del anuncio respetando su estructura (D41): cada
    párrafo/bloque en su propia línea, `<br>` como salto y viñetas de lista
    con guion (`- `).

    Los saltos se inyectan con un marcador interno (`_MARCA_SALTO`) para
    distinguirlos del espacio en blanco original del HTML: la indentación o
    los saltos de línea del fuente colapsan a espacio simple dentro de cada
    línea y SOLO los saltos deliberados producen líneas nuevas.
    """
    for basura in nodo.find_all(["script", "style", "noscript"]):
        basura.decompose()
    for item in nodo.find_all("li"):
        item.insert(0, "- ")
    for salto in nodo.find_all("br"):
        salto.replace_with(_MARCA_SALTO)
    for bloque in nodo.find_all(list(_ETIQUETAS_BLOQUE)):
        bloque.insert_before(_MARCA_SALTO)
        bloque.insert_after(_MARCA_SALTO)
    texto = nodo.get_text("")
    lineas = (" ".join(linea.split()) for linea in texto.split(_MARCA_SALTO))
    return "\n".join(linea for linea in lineas if linea)


def _primer_texto_estructurado(soup: BeautifulSoup, selectores: list[str]) -> str:
    """Extrae el primer selector con contenido, preservando la estructura."""
    for selector in selectores:
        nodo = soup.select_one(selector)
        if nodo is not None:
            texto = _texto_con_estructura(nodo)
            if texto:
                return texto
    return ""


def _extraer_datos(html: str) -> DatosCaptura:
    """Extract title/description/company/location (paso 1).

    La ubicación se extrae del primer span con las clases `topcard__flavor`
    y `topcard__flavor--bullet` (texto completo, sin recortes). La modalidad
    no se extrae de la página. Esta extracción degrada con gracia
    (vacío → `N/R`/`N/A` downstream).
    """
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.select_one("h1")
    titulo_h1 = h1.get_text(" ", strip=True) if isinstance(h1, Tag) else None
    if titulo_h1 == "":
        titulo_h1 = None
    descripcion = _primer_texto_estructurado(
        soup,
        [
            ".show-more-less-html__markup",
            "div[class*='description__text']",
            "main",
            "section",
        ],
    )
    ancla = soup.select_one(
        "a.topcard__org-name-link, a.jobs-unified-top-card__company-name"
    ) or soup.select_one("a[href^='/company/']")
    empresa_nombre = ""
    empresa_perfil = ""
    if isinstance(ancla, Tag):
        empresa_nombre = ancla.get_text(" ", strip=True)
        href = ancla.get("href")
        if isinstance(href, str) and href:
            empresa_perfil = urljoin(BASE_LINKEDIN, href)
    ubicacion_span = soup.select_one("span.topcard__flavor.topcard__flavor--bullet")
    ubicacion_pagina = (
        ubicacion_span.get_text(strip=True)
        if isinstance(ubicacion_span, Tag)
        else ""
    )
    if not any([titulo_h1, descripcion, empresa_nombre]):
        raise ValueError("html sin contenido interpretable")
    return DatosCaptura(
        titulo_h1=titulo_h1,
        descripcion=descripcion,
        empresa_nombre=empresa_nombre,
        empresa_perfil=empresa_perfil,
        ubicacion_pagina=ubicacion_pagina,
    )


def _capturar_pagina(contexto: RunContext, enlace: str) -> DatosCaptura:
    """Paso 1 with the configured retry policy (ERR-02/03/04 retryable).

    On `authwall_detectado` the guest session is renewed before the next
    attempt (ERR-04); exhausted retries raise `FalloPreparacion` and the
    offer stays `descubierta` (RN-04).
    """
    reintentos = contexto.config_preparacion["retries"]
    ultimo_codigo: list[str] = []

    def _intentar() -> DatosCaptura:
        cliente = _obtener_sesion(contexto)
        try:
            respuesta = cliente.get(enlace)
        except httpx.TimeoutException as exc:
            # TimeoutException es subclase de HTTPError: capturar primero.
            raise FalloPreparacion("tiempo_agotado_captura", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise FalloPreparacion("pagina_inalcanzable", str(exc)) from exc
        if _es_authwall(respuesta):
            raise FalloPreparacion(
                "authwall_detectado",
                f"status={respuesta.status_code} url={respuesta.url}",
            )
        if respuesta.status_code >= 400:
            raise FalloPreparacion(
                "pagina_inalcanzable", f"status={respuesta.status_code}"
            )
        contexto.ofertas_en_sesion += 1
        try:
            return _extraer_datos(respuesta.text)
        except ValueError as exc:
            raise FalloPreparacion("respuesta_invalida", str(exc)) from exc
        except Exception as exc:
            raise FalloPreparacion("error_interno_captura", str(exc)) from exc

    def _intentar_registrado() -> DatosCaptura:
        try:
            return _intentar()
        except FalloPreparacion as fallo:
            ultimo_codigo.append(fallo.codigo_motivo)
            raise

    def _al_reintento() -> None:
        if ultimo_codigo and ultimo_codigo[-1] == "authwall_detectado":
            _obtener_sesion(contexto, renovar=True)

    resultado, _intentos = ejecutar_con_reintento(
        _intentar_registrado,
        al_reintento=_al_reintento,
        max_attempts=int(reintentos["max_attempts"]),
        base_wait=float(reintentos["base_wait_seconds"]),
        max_wait=float(reintentos["max_wait_seconds"]),
        multiplier=float(reintentos["multiplier"]),
        contexto_log=contexto.id_corrida,
    )
    return resultado


def _diligenciar_empresa(
    contexto: RunContext, nombre: str, perfil: str
) -> str:
    """Paso 2: cache → normalize → upsert by `nombre_normalizado` (RN-05).

    D41: la clave usa `normalizar_nombre_empresa` (minúsculas + espacios
    simples, conserva todos los caracteres).
    """
    if not nombre or not nombre.strip():
        # ERR-07: página sin empresa; continúa con `N/A` (D31).
        logger.warning(
            f"ERR-07 | run={contexto.id_corrida} | empresa_no_disponible"
        )
        return "N/A"
    clave = normalizar_nombre_empresa(nombre)
    en_cache = contexto.cache_empresas.get(clave)
    if en_cache:
        return en_cache
    existentes = leer_tabla("empresas", {"nombre_normalizado": clave})
    if existentes:
        empresa_id = str(existentes[0]["id"])
    else:
        empresa_id = escribir_fila(
            "empresas",
            {
                "nombre": nombre.strip(),
                "nombre_normalizado": clave,
                "perfil_linkedin": perfil.strip() if perfil.strip() else "N/A",
            },
        )
    contexto.cache_empresas[clave] = empresa_id
    return empresa_id


def _diligenciar_ubicacion(contexto: RunContext, texto_crudo: str) -> str:
    """Paso 3: cascade — deterministic engine, then AI, then fallbacks.

    Without catalogue loaded, returns the pending sentinel with ERR-08.
    Step 0: metropolitan area — strip prefix and resolve the city.
    Step 1: resolver with text cache. Step 2: AI components via
    _clasificar_con_puertas (cached in cache_ia by full text),
    buscar_por_componentes, create if unknown with normalized components
    (reused within the run by full tuple, not by municipality name alone).
    Step 3: departamento_en_texto. Step 4: country row. Step 5: sentinel.
    """
    catalogo = contexto.catalogo_ubicaciones
    if catalogo is None:
        logger.warning(
            f"ERR-08 | run={contexto.id_corrida} | ubicacion_no_clasificada"
            f" | catalogo no cargado"
        )
        return PENDIENTE

    # Paso 0: área metropolitana — resolver por ciudad sin crear fila
    ciudad_am = resolver_area_metropolitana(texto_crudo)
    if ciudad_am is not None:
        resultado_am = catalogo.resolver(ciudad_am, contexto.cache_ubicaciones)
        if resultado_am != PENDIENTE:
            return resultado_am
        # Área metropolitana: si la ciudad no se resolvió, saltar pasos 1-2
        # (no consultar IA ni crear fila); ir directo a pasos 3-5.
        dept_id = catalogo.departamento_en_texto(texto_crudo)
        if dept_id is not None:
            return dept_id
        if catalogo.fila_pais_id is not None:
            return catalogo.fila_pais_id
        return PENDIENTE

    # Paso 1: resolver determinista
    resultado = catalogo.resolver(texto_crudo, contexto.cache_ubicaciones)
    if resultado != PENDIENTE:
        return resultado

    # Paso 2: IA resuelve componentes (cache_ia evita repetir por texto)
    texto_clave = texto_crudo.strip()
    tupla_ia = contexto.cache_ia.get(texto_clave)
    if tupla_ia is None:
        clasificacion = _clasificar_con_puertas(contexto, texto_crudo)
        if clasificacion is not None:
            tupla_ia = (
                clasificacion.municipio,
                clasificacion.departamento,
                clasificacion.pais,
            )
    if tupla_ia is not None:
        mun, dept_raw, pais_raw = tupla_ia
        if not mun or mun in ("N/A", "N/R"):
            # Municipio sin valor útil: saltar a paso 3
            pass
        else:
            mun_limpiado = CatalogoUbicaciones.limpiar_municipio(
                normalizar_texto(mun)
            )
            if not mun_limpiado:
                # Municipio vacío tras normalización: saltar a paso 3
                pass
            else:
                contexto.cache_ia[texto_clave] = tupla_ia
                fila_id = catalogo.buscar_por_componentes(mun, dept_raw, pais_raw)
                if fila_id is not None:
                    return fila_id
                if not catalogo.municipio_conocido(mun, pais_raw):
                    # Municipio desconocido: crear o reutilizar por tupla COMPLETA.
                    # Indexar solo por municipio haría compartir la fila a dos
                    # homónimos de departamentos o países distintos.
                    dept_norm = (
                        normalizar_texto(dept_raw)
                        if dept_raw and dept_raw not in ("", "N/A", "N/R")
                        else "N/A"
                    ) or "N/A"
                    pais_norm = normalizar_pais(pais_raw) or "N/A"
                    clave_creada = (mun_limpiado, dept_norm, pais_norm)
                    if clave_creada in contexto.cache_creadas:
                        return contexto.cache_creadas[clave_creada]
                    nueva_id = crear_o_reutilizar_ubicacion(
                        {
                            "municipio": mun_limpiado,
                            "departamento": dept_norm,
                            "pais": pais_norm,
                            "origen": "sistema",
                        }
                    )
                    contexto.cache_creadas[clave_creada] = nueva_id
                    return nueva_id

    # Paso 3: departamento en texto
    dept_id = catalogo.departamento_en_texto(texto_crudo)
    if dept_id is not None:
        return dept_id

    # Paso 4: fila de país
    if catalogo.fila_pais_id is not None:
        return catalogo.fila_pais_id

    # Paso 5: centinela
    return PENDIENTE


def _puertas_clasificacion(seccion: dict[str, Any]) -> list[dict[str, str]]:
    """Puertas ordenadas del clasificador con interruptor de puerta principal.

    Si `puerta_principal_activa` está ausente o es True, la puerta local
    va primero. Si es False, solo se devuelven las alternas en orden.
    """
    principal_activa = seccion.get("puerta_principal_activa", True)
    puertas: list[dict[str, str]] = []
    if principal_activa is not False:
        puertas.append(
            {"nombre": "principal", "modelo": "", "clave_ref": ""}
        )
    alternas = seccion.get("puertas_alternas") or []
    for indice, puerta in enumerate(alternas):
        nombre = puerta.get("nombre") if isinstance(puerta, dict) else ""
        modelo = puerta.get("modelo", "") if isinstance(puerta, dict) else ""
        clave_ref = puerta.get("clave_ref", "") if isinstance(puerta, dict) else ""
        puertas.append(
            {
                "nombre": str(nombre) if nombre else f"alterna-{indice + 1}",
                "modelo": str(modelo),
                "clave_ref": str(clave_ref),
            }
        )
    return puertas


def _es_respuesta_no_json(exc: Exception) -> bool:
    """True cuando la puerta respondió pero la respuesta no es JSON válido."""
    texto = str(exc)
    return "not valid JSON" in texto or "expected a dictionary" in texto


def _marcar_puerta_caida(contexto: RunContext, nombre: str, motivo: str) -> None:
    """D75: recuerda una puerta caída durante el resto de la corrida del módulo."""
    if nombre in contexto.puertas_caidas:
        return
    contexto.puertas_caidas[nombre] = motivo
    logger.warning(
        f"D75 | run={contexto.id_corrida} | puerta_descartada | {nombre} | {motivo}"
    )


def _clasificar_con_puertas(
    contexto: RunContext, texto: str
) -> ClasificacionUbicacion | None:
    """Paso 3, subpaso de IA para una ubicación con rotación de puertas (D75)."""
    seccion = contexto.config_preparacion
    timeout = float(seccion["timeout_puerta_segundos"])
    detalles: list[str] = []
    for puerta in _puertas_clasificacion(seccion):
        nombre = puerta["nombre"]
        if nombre in contexto.puertas_caidas:
            continue
        try:
            if puerta["clave_ref"]:
                respuesta = analyze_openrouter(
                    PROMPT_UBICACION,
                    {"texto_ubicacion": texto},
                    puerta["modelo"],
                    puerta["clave_ref"],
                    timeout=timeout,
                )
            else:
                respuesta = analyze(
                    PROMPT_UBICACION,
                    {"texto_ubicacion": texto},
                    purpose="preparacion",
                    timeout=timeout,
                    reintentar=False,
                )
        except Exception as exc:
            if _es_respuesta_no_json(exc):
                logger.warning(
                    f"ubicacion_ia_no_disponible | run={contexto.id_corrida}"
                    f" | respuesta no JSON de {nombre}"
                )
                return None
            detalles.append(f"{nombre}: {exc}")
            _marcar_puerta_caida(contexto, nombre, str(exc))
            continue
        try:
            return ClasificacionUbicacion.model_validate(respuesta)
        except ValidationError as exc:
            logger.warning(
                f"ubicacion_ia_no_disponible | run={contexto.id_corrida}"
                f" | respuesta invalida de {nombre} | {exc}"
            )
            return None
    if detalles:
        detalle_final = "; ".join(detalles)
    else:
        detalle_final = "; ".join(
            f"{nombre}: {motivo}"
            for nombre, motivo in contexto.puertas_caidas.items()
        ) or "sin puertas disponibles"
    logger.warning(
        f"ubicacion_ia_no_disponible | run={contexto.id_corrida}"
        f" | todas las puertas caidas ({detalle_final})"
    )
    return None


def _actualizar_oferta(
    oferta: dict[str, Any], datos: DatosCaptura, empresa_id: str, ubicacion_id: str
) -> None:
    """Pasos 4: faithful update; never `fecha_ultima_verificacion` (RN-11).

    `ubicacion` se actualiza con el texto de la página si llega con contenido;
    si la página no trajo ubicación, se conserva el valor de la tarjeta.
    `modalidad` no se toca.
    """
    campos: dict[str, Any] = {
        "empresa_id": empresa_id,
        "ubicacion_id": ubicacion_id,
        "estado": "preparada",
    }
    if datos.ubicacion_pagina:
        campos["ubicacion"] = datos.ubicacion_pagina
    if datos.titulo_h1:
        campos["titulo"] = datos.titulo_h1  # RN-10: solo si existe el <h1>
    if datos.descripcion:
        campos["descripcion_original"] = datos.descripcion
    else:
        # Punto 1 aprobado (análisis 5.3): sin descripción extraíble → `N/R`
        # con evidencia en `observaciones`, preservando el texto previo.
        campos["descripcion_original"] = "N/R"
        marca = "descripcion no extraible en la captura"
        base = str(oferta.get("observaciones", "N/A"))
        if marca not in base:
            campos["observaciones"] = (
                f"{base} | {marca}" if base and base != "N/A" else marca
            )
    for clave, valor in list(campos.items()):
        if valor is None or str(valor).strip() == "":
            campos[clave] = "N/A"  # VAL-04/D31: sin vacíos
    actualizar_fila("ofertas_descubiertas", str(oferta["id"]), campos)


def _registrar_evento(
    id_corrida: str, tipo: str, codigo: str, evidencia: str, id_oferta: str
) -> None:
    """RN-09/VAL-05: every offer event carries `id_oferta`; evidence bounded.

    D42: delega en el emisor unico compartido."""
    registrar_evento(
        id_corrida=id_corrida,
        tipo=tipo,
        codigo=codigo,
        evidencia=evidencia,
        id_oferta=id_oferta,
    )


def _procesar_lote(contexto: RunContext, lote: list[dict[str, Any]]) -> bool:
    """Single lot steps 1-5 per offer; returns False on ERR-09 (abort)."""
    pausa = float(contexto.config_preparacion["pausa_entre_ofertas_segundos"])
    jitter = float(contexto.config_preparacion.get("pausa_jitter_segundos", 0))
    total = len(lote)
    for indice, oferta in enumerate(lote):
        id_oferta = str(oferta["id"])
        try:
            datos = _capturar_pagina(contexto, str(oferta["enlace"]))
        except FalloPreparacion as fallo:
            contexto.contador_errores += 1
            _registrar_evento(
                contexto.id_corrida,
                "error",
                "preparacion_fallida",
                f"{fallo.codigo_motivo}: {fallo.detalle}",
                id_oferta,
            )
            continue  # RN-04: queda `descubierta` para la siguiente pasada
        try:
            empresa_id = _diligenciar_empresa(
                contexto, datos.empresa_nombre, datos.empresa_perfil
            )
            # Usar la ubicación de la página si está disponible;
            # si no, usar la guardada en la tarjeta.
            texto_para_resolver = (
                datos.ubicacion_pagina
                if datos.ubicacion_pagina
                else str(oferta.get("ubicacion", "") or "")
            )
            ubicacion_id = _diligenciar_ubicacion(
                contexto, texto_para_resolver
            )
            _actualizar_oferta(oferta, datos, empresa_id, ubicacion_id)
            contexto.contador_preparadas += 1
            _registrar_evento(
                contexto.id_corrida,
                "suceso",
                "oferta_preparada",
                f"empresa={empresa_id} ubicacion={ubicacion_id} "
                f"modalidad={str(oferta.get('modalidad', 'N/R') or 'N/R')}",
                id_oferta,
            )
        except Exception as error:
            _registrar_evento(
                contexto.id_corrida,
                "error",
                "ERR-09",
                f"corrupcion al persistir la oferta: {error}",
                id_oferta,
            )
            return False
        if indice < total - 1 and pausa > 0:
            # D42: pausa con jitter — aleatoria en [base-jitter, base+jitter]
            # (mas humana que un intervalo identico); jitter 0 => fija.
            espera = (
                random.uniform(pausa - jitter, pausa + jitter)
                if jitter > 0
                else pausa
            )
            time.sleep(max(0.0, espera))  # VAL-03: entre ofertas, no tras la última
    return True


def ejecutar_preparacion(contexto: RunContext | None) -> ResultadoPreparacion:
    """Run the Preparación de ofertas node (sheet pasos funcionales 1-9)."""
    if contexto is None or not isinstance(contexto, RunContext):
        logger.error(
            "ERR-01 | sin id_corrida | contexto ausente o corrupto: "
            "no se puede ejecutar la preparación"
        )
        return ResultadoPreparacion(
            estado="abortada",
            codigo="ERR-01",
            descripcion="contexto ausente o corrupto",
        )
    id_corrida = contexto.id_corrida

    # Paso 1 — VAL-01: insumos presentes (configuración validada por INICIO).
    problema = _validar_preparacion(contexto.config_preparacion)
    if problema is not None:
        _registrar_evento(
            id_corrida, "error", "ERR-01", f"insumos invalidos: {problema}", "N/A"
        )
        return ResultadoPreparacion(
            estado="abortada",
            contexto=contexto,
            codigo="ERR-01",
            descripcion=f"insumos ausentes o corruptos: {problema}",
        )

    # Cargar catálogo de ubicaciones una sola vez por corrida (D78).
    try:
        filas_ubicaciones = leer_tabla("ubicaciones")
    except Exception as error:
        _registrar_evento(
            id_corrida, "error", "ERR-09",
            f"fallo al leer catálogo de ubicaciones: {error}", "N/A",
        )
        return ResultadoPreparacion(
            estado="abortada",
            contexto=contexto,
            codigo="ERR-09",
            descripcion="database failure reading locations catalogue",
        )
    contexto.catalogo_ubicaciones = CatalogoUbicaciones(filas_ubicaciones)

    # Validar catálogo incompleto: si falta la fila "no aplica" o la de país,
    # la corrida termina abortada sin procesar ninguna oferta.
    if (
        contexto.catalogo_ubicaciones.fila_no_aplica_id is None
        or contexto.catalogo_ubicaciones.fila_pais_id is None
    ):
        _registrar_evento(
            id_corrida,
            "error",
            "ERR-09",
            "catalogo_ubicaciones_incompleto: faltan filas sistema o país",
            "N/A",
        )
        return ResultadoPreparacion(
            estado="abortada",
            contexto=contexto,
            codigo="ERR-09",
            descripcion="locations catalogue incomplete (missing system or country row)",
        )

    # Paso 2 — re-consulta FIFO (RN-02).
    try:
        lote = leer_candidatas_descubiertas()
    except Exception as error:
        _registrar_evento(
            id_corrida, "error", "ERR-09", f"fallo al determinar lotes: {error}",
            "N/A",
        )
        return ResultadoPreparacion(
            estado="abortada",
            contexto=contexto,
            codigo="ERR-09",
            descripcion="database failure determining lots",
        )

    # Pasos 3-7 — lote único: captura completa.
    if not _procesar_lote(contexto, lote):
        return ResultadoPreparacion(
            estado="abortada",
            contexto=contexto,
            codigo="ERR-09",
            descripcion="persistence corruption processing lot",
        )

    # Paso 9 — entregar control a "Verificación de duplicidad".
    return ResultadoPreparacion(estado="completada", contexto=contexto)
