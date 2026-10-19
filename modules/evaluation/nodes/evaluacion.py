"""Nodo proceso "Evaluación inicial" del flujo de Evaluación (ficha M3 v1.0).

Process node, batch over the whole candidate list (sheet pasos funcionales
1-8). For every offer in `preparada` (FIFO order from INICIO): take the 4
fields as stored (VAL-02, no interpretation), request the role's main
deliverable plus the 5-veto evaluation from the routed AI (paso 3, up to 2
attempts per sheet `max_attempts: 2` with pause between offers), validate
the answer (paso 4, VAL-04: deliverable + vetos + coherent decision +
justification), and persist immediately per offer (RN-02: final state +
full result column + event with `id_oferta` + counter) before taking the
next one.

Golden rule (RN-05): on doubt or missing information the offer passes — with
one approved exception: an empty, `N/A`/`N/R` or unreported description is a
V3 FAIL and the offer is discarded without calling the AI. Modality and
location apply literally even when the data is missing (V4/V5).

Door policy (RN-07): a verified door failure (quota, down door, key
rejected) rotates to the next ordered alternate door of the same model; an
invalid answer retries on the SAME door. Exhausted attempts on one offer
leave it pending in `preparada` with `resultado_evaluacion_inicial = 'N/A'`
and continue with the next (RN-06/RN-09). When every door reports an
exhausted quota, calls stop and the rest stays pending for a quota-ordered
close (`cupo_agotado` fixed on the context for Finalizar Proceso).
"""

import json
import random
import time
from dataclasses import dataclass
from typing import Any

from loguru import logger
from pydantic import BaseModel

from modules.evaluation.run_context import RunContext
from shared.errors import InternalError
from shared.ia_service import analyze, analyze_openrouter
from shared.models import OfferState
from shared.persistence import actualizar_fila, registrar_evento
from shared.retry import ejecutar_con_reintento
from shared.state_machine import transition
from shared.utilidades import ahora

PROMPT_EVALUACION = "initial_evaluation/compatibility"

# Señales de cupo agotado en el detalle de un fallo de puerta (ficha M3:
# "cupo lleno" verificado frena las llamadas y cierra por cupo).
_SENALES_CUPO = (
    "429",
    "quota",
    "cupo",
    "rate limit",
    "too many requests",
    "límite de uso",
    "limite de uso",
)

# Descripción sin contenido evaluable → V3 FAIL sin llamar a la IA (excepción
# aprobada a la REGLA DE ORO; la oferta queda descartada, no pendiente).
_DESCRIPCIONES_VACIAS = {"", "n/a", "n/r", "no reportada", "no_reportada", "nr"}
_SALTOS_DE_LINEA = "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"


class ResultadoVetos(BaseModel):
    """Validated `{entregable_principal, v1..v5, decision, justificacion}` JSON."""

    entregable_principal: str
    v1: str
    v2: str
    v3: str
    v4: str
    v5: str
    decision: str
    justificacion: str


class FalloEvaluacion(Exception):
    """Failure carrying a retryable flow code for the shared retry helper."""

    def __init__(self, codigo_motivo: str, detalle: str) -> None:
        super().__init__(f"{codigo_motivo}: {detalle}")
        self.codigo_motivo = codigo_motivo
        self.detalle = detalle


@dataclass
class ResultadoEvaluacion:
    """Outcome handed to the flow: `completada` or `abortada` (ERR-01/04)."""

    estado: str
    contexto: RunContext | None = None
    codigo: str = ""
    descripcion: str = ""


def _es_descripcion_vacia(descripcion: str) -> bool:
    """V3-FAIL exception: empty, sentinel or unreported description.

    The unreported marker only triggers as the whole content or as a
    leading marker ("No reportada por la fuente") — never as a passing
    mention inside a real description (golden rule).
    """
    texto = (descripcion or "").strip().lower()
    if texto in _DESCRIPCIONES_VACIAS:
        return True
    return texto.startswith(("no reportada", "no reportado"))


# Tope de seguridad para la entrada de la IA (caracteres): la descripción
# original se conserva intacta en la base; esto solo acota lo que se envía
# al modelo tras quitar el ruido. Por encima del promedio observado.
_LIMITE_DESCRIPCION_IA = 6000

# Encabezados de secciones de ruido (empresa, beneficios, avisos legales):
# solo coinciden con la línea completa del encabezado, nunca con menciones
# dentro del texto del rol. Comparación insensible a mayúsculas y ":" final.
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

# Encabezados del rol: al aparecer, se retoma la conservación (la propaganda
# de la empresa suele ir primero y el rol después).
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


def _limpiar_descripcion_para_ia(descripcion: str) -> str:
    """Limpieza no destructiva solo para la entrada de la IA.

    Quita secciones de ruido (empresa, beneficios, avisos) donde aparezcan
    —al inicio o al final— y aplica un tope alto de seguridad. Nunca corta
    a ciegas por el inicio: el núcleo del rol suele estar en el medio. La
    descripción original en la base no se toca. Si la limpieza lo vaciara
    todo, se devuelve el original.
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
        return descripcion
    if len(limpio) > _LIMITE_DESCRIPCION_IA:
        limpio = limpio[:_LIMITE_DESCRIPCION_IA].rstrip()
    return limpio


def _validar_respuesta(respuesta: Any) -> ResultadoVetos:
    """VAL-04: deliverable (one line, ≤20 words) and veto answer validation."""
    if not isinstance(respuesta, dict):
        raise ValueError("la respuesta no es un objeto JSON")
    try:
        validada = ResultadoVetos.model_validate(respuesta)
    except Exception as exc:
        raise ValueError(f"respuesta con campos faltantes o tipos invalidos: {exc}") from exc
    entregable = (validada.entregable_principal or "").strip()
    if not entregable:
        raise ValueError("entregable_principal vacio")
    if any(c in entregable for c in _SALTOS_DE_LINEA):
        raise ValueError("entregable_principal debe ser una sola linea")
    if entregable.upper() in {"N/A", "N/R"}:
        raise ValueError("entregable_principal sin contenido")
    if len(entregable.split()) > 20:
        raise ValueError("entregable_principal supera 20 palabras")
    if '"' in entregable:
        raise ValueError("entregable_principal con comillas dobles")
    validada = validada.model_copy(update={"entregable_principal": entregable})
    for campo in ("v1", "v2", "v3", "v4", "v5"):
        if getattr(validada, campo) not in ("PASS", "FAIL"):
            raise ValueError(f"{campo} debe ser PASS o FAIL")
    if validada.decision not in ("APROBADA", "DESCARTADA"):
        raise ValueError("decision debe ser APROBADA o DESCARTADA")
    todos_pass = all(getattr(validada, c) == "PASS" for c in ("v1", "v2", "v3", "v4", "v5"))
    coherente = (validada.decision == "APROBADA") == todos_pass
    if not coherente:
        raise ValueError("decision incoherente con los vetos")
    justificacion = validada.justificacion or ""
    if not justificacion.strip():
        raise ValueError("justificacion vacia")
    if any(c in justificacion for c in _SALTOS_DE_LINEA):
        raise ValueError("justificacion debe ser una sola linea")
    if len(justificacion.split()) > 60:
        raise ValueError("justificacion supera 60 palabras")
    for prohibido in ('"', "\\", "{", "}"):
        if prohibido in justificacion:
            raise ValueError("justificacion con caracteres prohibidos")
    return validada


def _es_cupo_agotado(detalle: str) -> bool:
    """Detects a verified quota-exhaustion signal in a door failure."""
    texto = (detalle or "").lower()
    return any(senal in texto for senal in _SENALES_CUPO)


def _puertas(contexto: RunContext) -> list[dict[str, str]]:
    """Ordered doors: principal first, then the configured alternates.

    Alternate doors share the model family (sheet pending item 1, D50):
    each entry carries its display name, the provider model id and the
    private-key reference — keys stay in `config/.env`, never here. With
    the approved empty list, only the principal door is attempted.
    """
    puertas: list[dict[str, str]] = [{"nombre": "principal", "modelo": "", "clave_ref": ""}]
    alternas = contexto.config_evaluacion.get("puertas_alternas") or []
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


def _pedir_evaluacion(
    contexto: RunContext, datos_ia: dict[str, str]
) -> tuple[ResultadoVetos | None, str, FalloEvaluacion | None]:
    """Requests the veto evaluation with door rotation (RN-07, ≤ 2 attempts).

    Returns (validated answer or None, responding door name, final failure or
    None). A door failure rotates to the next door on retry; an invalid
    answer retries on the same door.
    """
    reintentos = contexto.config_evaluacion["retries"]
    puertas = _puertas(contexto)
    puerta_actual = [0]
    ultimo_fallo: list[FalloEvaluacion] = []

    def _intentar() -> tuple[ResultadoVetos, str]:
        puerta = puertas[puerta_actual[0]]
        try:
            if puerta["clave_ref"]:
                respuesta = analyze_openrouter(
                    PROMPT_EVALUACION, datos_ia, puerta["modelo"], puerta["clave_ref"]
                )
            else:
                respuesta = analyze(PROMPT_EVALUACION, datos_ia, purpose="evaluation")
        except Exception as exc:
            raise FalloEvaluacion(
                "puerta_evaluacion_no_disponible", f"{puerta['nombre']}: {exc}"
            ) from exc
        try:
            return _validar_respuesta(respuesta), puerta["nombre"]
        except ValueError as exc:
            raise FalloEvaluacion(
                "respuesta_evaluacion_invalida", f"{puerta['nombre']}: {exc}"
            ) from exc

    def _intentar_registrado() -> tuple[ResultadoVetos, str]:
        try:
            return _intentar()
        except FalloEvaluacion as fallo:
            ultimo_fallo.append(fallo)
            raise

    def _al_reintento() -> None:
        if (
            ultimo_fallo
            and ultimo_fallo[-1].codigo_motivo == "puerta_evaluacion_no_disponible"
            and puerta_actual[0] + 1 < len(puertas)
        ):
            puerta_actual[0] += 1

    resultado, _intentos = ejecutar_con_reintento(
        _intentar_registrado,
        al_reintento=_al_reintento,
        al_fallo_final=lambda exc, n: exc,
        max_attempts=int(reintentos["max_attempts"]),
        base_wait=float(reintentos["base_wait_seconds"]),
        max_wait=float(reintentos["max_wait_seconds"]),
        multiplier=float(reintentos["multiplier"]),
        contexto_log=contexto.id_corrida,
    )
    if isinstance(resultado, FalloEvaluacion):
        return None, puertas[puerta_actual[0]]["nombre"], resultado
    if isinstance(resultado, BaseException):
        fallo = FalloEvaluacion("puerta_evaluacion_no_disponible", str(resultado))
        return None, puertas[puerta_actual[0]]["nombre"], fallo
    validada, puerta = resultado
    return validada, puerta, None


def _primer_veto(validada: ResultadoVetos) -> str:
    """Blocking veto for the discard evidence (first FAIL in v1..v5 order)."""
    for campo in ("v1", "v2", "v3", "v4", "v5"):
        if getattr(validada, campo) == "FAIL":
            return campo
    return "ninguno"


def _anotar_oferta(
    contexto: RunContext,
    oferta: dict[str, Any],
    validada: ResultadoVetos,
    puerta: str,
) -> bool:
    """Pasos 5-6: final state via `evaluada` + full result + success event.

    Returns False on ERR-04 (persistent annotation failure → abort).
    """
    id_oferta = str(oferta["id"])
    aprobada = validada.decision == "APROBADA"
    destino = OfferState.ACEPTADA_EI if aprobada else OfferState.DESCARTADA_EI
    try:
        transition(OfferState.PREPARADA, OfferState.EVALUADA)
        transition(OfferState.EVALUADA, destino)
    except InternalError as exc:
        logger.error(f"ERR-04 | run={contexto.id_corrida} | {exc}")
        return False
    resultado_json = json.dumps(
        {
            "entregable_principal": validada.entregable_principal,
            "v1": validada.v1,
            "v2": validada.v2,
            "v3": validada.v3,
            "v4": validada.v4,
            "v5": validada.v5,
            "decision": validada.decision,
            "justificacion": validada.justificacion,
            "puerta": puerta,
        },
        ensure_ascii=False,
    )
    try:
        ok = actualizar_fila(
            "ofertas_descubiertas",
            id_oferta,
            {"estado": destino.value, "resultado_evaluacion_inicial": resultado_json},
        )
        if not ok:
            raise ValueError(f"la oferta {id_oferta} no existe en la base")
    except Exception as exc:
        registrar_evento(
            id_corrida=contexto.id_corrida,
            tipo="error",
            codigo="ERR-04",
            evidencia=f"fallo persistente de anotacion de la oferta: {exc}",
            id_oferta=id_oferta,
        )
        return False
    if aprobada:
        contexto.contador_aprobadas += 1
        registrar_evento(
            id_corrida=contexto.id_corrida,
            tipo="suceso",
            codigo="oferta_aprobada",
            evidencia=f"puerta={puerta} decision=APROBADA",
            id_oferta=id_oferta,
        )
    else:
        contexto.contador_descartadas += 1
        registrar_evento(
            id_corrida=contexto.id_corrida,
            tipo="suceso",
            codigo="oferta_descartada",
            evidencia=f"puerta={puerta} veto={_primer_veto(validada)} decision=DESCARTADA",
            id_oferta=id_oferta,
        )
    return True


def _v3_fail() -> ResultadoVetos:
    """Synthetic V3-FAIL result for the empty-description fast path."""
    return ResultadoVetos(
        entregable_principal="N/A",
        v1="PASS",
        v2="PASS",
        v3="FAIL",
        v4="PASS",
        v5="PASS",
        decision="DESCARTADA",
        justificacion="Sin descripción: calidad mínima no verificable",
    )


def ejecutar_evaluacion(contexto: RunContext | None) -> ResultadoEvaluacion:
    """Run the Evaluación inicial node (sheet pasos funcionales 1-8)."""
    if contexto is None or not isinstance(contexto, RunContext):
        logger.error(
            "ERR-01 | sin id_corrida | contexto ausente o corrupto: "
            "no se puede ejecutar la evaluación"
        )
        return ResultadoEvaluacion(
            estado="abortada",
            codigo="ERR-01",
            descripcion="contexto ausente o corrupto",
        )
    id_corrida = contexto.id_corrida

    # Paso 1 — VAL-01: insumos presentes (lista no vacía garantizada por la
    # rama Sí de la decisión; ajustes validados por INICIO).
    seccion = contexto.config_evaluacion
    if (
        not isinstance(contexto.candidatas, list)
        or len(contexto.candidatas) == 0
        or not isinstance(seccion, dict)
        or not isinstance(seccion.get("retries"), dict)
        or seccion.get("retries", {}).get("max_attempts") != 2
    ):
        registrar_evento(
            id_corrida=id_corrida,
            tipo="error",
            codigo="ERR-01",
            evidencia="insumos ausentes o corruptos para la evaluación",
            id_oferta="N/A",
        )
        return ResultadoEvaluacion(
            estado="abortada",
            contexto=contexto,
            codigo="ERR-01",
            descripcion="insumos ausentes o corruptos",
        )

    pausa = float(seccion.get("pausa_entre_ofertas_segundos", 0))
    jitter = float(seccion.get("pausa_jitter_segundos", 0))
    total = len(contexto.candidatas)
    for indice, oferta in enumerate(contexto.candidatas):
        id_oferta = str(oferta.get("id", ""))
        if not id_oferta:
            registrar_evento(
                id_corrida=id_corrida,
                tipo="error",
                codigo="ERR-01",
                evidencia="candidata sin id en la lista del contexto",
                id_oferta="N/A",
            )
            return ResultadoEvaluacion(
                estado="abortada",
                contexto=contexto,
                codigo="ERR-01",
                descripcion="candidata sin id",
            )

        # Paso 2 — tomar los 4 datos tal cual (VAL-02: sin interpretar).
        titulo = str(oferta.get("titulo", "") or "")
        descripcion = str(oferta.get("descripcion_original", "") or "")
        modalidad = str(oferta.get("modalidad", "") or "")
        ubicacion = str(oferta.get("ubicacion", "") or "")

        # Excepción V3-FAIL: sin descripción no se llama a la IA.
        if _es_descripcion_vacia(descripcion):
            if not _anotar_oferta(contexto, oferta, _v3_fail(), "sin_llamada"):
                return ResultadoEvaluacion(
                    estado="abortada",
                    contexto=contexto,
                    codigo="ERR-04",
                    descripcion="persistence failure annotating offer",
                )
        else:
            # Pasos 3-4 — pedir la evaluación y validar la respuesta. La IA
            # recibe la descripción limpia de ruido (el original guardado no
            # se toca); título, modalidad y ubicación van tal cual.
            validada, puerta, fallo = _pedir_evaluacion(
                contexto,
                {
                    "titulo": titulo,
                    "descripcion_original": _limpiar_descripcion_para_ia(descripcion),
                    "modalidad": modalidad,
                    "ubicacion": ubicacion,
                },
            )
            if validada is None:
                assert fallo is not None
                # Paso 7 — fallo persistente: pendiente en `preparada` (EVT-03).
                contexto.contador_errores += 1
                registrar_evento(
                    id_corrida=id_corrida,
                    tipo="error",
                    codigo="evaluacion_fallida",
                    evidencia=f"{fallo.codigo_motivo}: {fallo.detalle}",
                    id_oferta=id_oferta,
                )
                if _es_cupo_agotado(fallo.detalle):
                    # Cupo agotado en las puertas: se deja de llamar; el
                    # resto queda pendiente y el cierre es por cupo.
                    contexto.motivo_cierre = "cupo_agotado"
                    contexto.motivo_marca_temporal = ahora()
                    logger.warning(
                        f"cupo_agotado | run={id_corrida} | "
                        f"ofertas restantes quedan pendientes"
                    )
                    break
            else:
                # Pasos 5-6 — anotar aprobada o descartada.
                if not _anotar_oferta(contexto, oferta, validada, puerta):
                    return ResultadoEvaluacion(
                        estado="abortada",
                        contexto=contexto,
                        codigo="ERR-04",
                        descripcion="persistence failure annotating offer",
                    )

        if indice < total - 1 and pausa > 0:
            espera = (
                random.uniform(pausa - jitter, pausa + jitter) if jitter > 0 else pausa
            )
            time.sleep(max(0.0, espera))  # VAL-03: entre ofertas, no tras la última

    # Paso 8 — entregar control a "Finalizar Proceso".
    return ResultadoEvaluacion(estado="completada", contexto=contexto)
