"""Nodo "Importar evaluaciones" del proceso de importación (M3 v2.0, Fase 3).

Aplica a cada oferta lo que devolvió el chat, con validación estricta, y cierra
cada lote: lo aplicado queda en la base y los archivos se eliminan. No completa,
no corrige y no adivina nada: una línea inválida se rechaza y su oferta sigue
pendiente. Los archivos son transporte; la evaluación evaluated vive en la base.

Orden obligatorio de la ficha: insumos, emparejamiento por nombre base, lectura
y limpieza, validación y aplicación por línea, comparación con la ficha de
control, cierre del lote y registro del suceso del lote. Los identificadores de
la interfaz son españoles, conforme a la excepción de `modules/evaluation/`
(D49 y D76).
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TypeVar

from loguru import logger

from modules.evaluation.run_context import RunContext
from shared.errors import InternalError
from shared.evaluacion import validar_evaluacion_manual
from shared.models import OfferState
from shared.persistence import (
    actualizar_fila,
    leer_estados_ofertas,
    registrar_evento,
)
from shared.retry import ejecutar_con_reintento
from shared.state_machine import transition

_PATRON_RESPUESTA = re.compile(
    r"^(?P<base>[A-Z]+-\d{4}_lote_\d{3,})"
    r"(?:_parte(?P<parte>\d+))?\.jsonl$"
)
_CAMPOS_LINEA = (
    "id",
    "eje_organizacional",
    "v1",
    "v2",
    "v3",
    "v4",
    "v5",
    "decision",
    "justificacion",
)
_VETOS = ("v1", "v2", "v3", "v4", "v5")
_VALORES_VETO = frozenset({"PASS", "FAIL"})
_DECISIONES = frozenset({"APROBADA", "DESCARTADA"})
_EJES = frozenset(
    {
        "SISTEMAS_OPERACIONALES",
        "SISTEMAS_DECISION_E_INFORMACION",
        "DISENO_Y_TRANSFORMACION_ORGANIZACIONAL",
        "MULTIPLE",
        "NO_APLICA",
    }
)
_VACIOS = frozenset({"", "n/a", "n/r"})

_MOTIVOS_ERR03 = frozenset(
    {
        "linea_no_objeto",
        "linea_ilegible",
        "id_ausente",
        "veto_ausente",
        "veto_invalido",
        "archivo_sin_lineas",
    }
)
_MOTIVOS_ERR04 = frozenset(
    {
        "id_invalido",
        "oferta_inexistente",
        "no_pendiente",
        "repetida",
        "fuera_de_lote",
    }
)

T = TypeVar("T")


@dataclass
class ResultadoImportacion:
    """Outcome handed to the import flow orchestrator."""

    estado: str  # "ok" | "error"
    contexto: RunContext | None = None
    codigo: str = ""
    descripcion: str = ""


class FalloManual(Exception):
    """File/database failure carrying a retryable flow code."""

    def __init__(self, codigo_motivo: str, detalle: str) -> None:
        super().__init__(f"{codigo_motivo}: {detalle}")
        self.codigo_motivo = codigo_motivo
        self.detalle = detalle


@dataclass
class _Linea:
    texto: str
    datos: dict[str, Any] | None = None
    motivo: str | None = None

    @property
    def candidata(self) -> bool:
        return self.datos is not None or self.motivo is not None


@dataclass
class _Lote:
    base: str
    ficha: Path
    texto: Path
    respuestas: list[Path] = field(default_factory=list)


def _fallo(
    contexto: RunContext | None, codigo: str, descripcion: str
) -> ResultadoImportacion:
    if contexto is not None:
        registrar_evento(
            id_corrida=contexto.id_corrida,
            tipo="error",
            codigo=codigo,
            evidencia=descripcion,
        )
    logger.error(f"{codigo} | importacion | {descripcion}")
    return ResultadoImportacion(
        estado="error", contexto=contexto, codigo=codigo, descripcion=descripcion
    )


def _politica_reintentos(seccion: dict[str, Any]) -> dict[str, int | float]:
    reintentos = seccion["retries"]
    return {
        "max_attempts": int(reintentos["max_attempts"]),
        "base_wait": float(reintentos["base_wait_seconds"]),
        "max_wait": float(reintentos["max_wait_seconds"]),
        "multiplier": float(reintentos["multiplier"]),
    }


def _con_reintento(
    operacion: Callable[[], T], politica: dict[str, int | float], contexto_log: str
) -> T | None:
    def fallo(_error: BaseException, _intentos: int) -> None:
        return None

    resultado, _ = ejecutar_con_reintento(
        operacion,
        al_fallo_final=fallo,
        al_error_interno=fallo,
        max_attempts=int(politica["max_attempts"]),
        base_wait=politica["base_wait"],
        max_wait=politica["max_wait"],
        multiplier=politica["multiplier"],
        contexto_log=contexto_log,
    )
    return resultado


def _validar_insumos(contexto: RunContext | None) -> tuple[str, str] | None:
    """VAL-01: insumos presentes antes de tocar los archivos."""
    if contexto is None:
        return "ERR-01", "contexto ausente"
    if not isinstance(contexto.archivos_resultados, list):
        return "ERR-01", "lista de resultados no accesible"
    problema = validar_evaluacion_manual(contexto.config_evaluacion_manual)
    if problema is not None:
        return "ERR-01", f"configuracion manual invalida: {problema}"
    if not contexto.carpetas_resueltas:
        return "ERR-01", "carpetas de trabajo no resueltas"
    for ruta in (contexto.carpeta_lotes, contexto.carpeta_resultados):
        if ruta is None or not ruta.is_dir():
            return "ERR-01", f"carpeta no disponible: {ruta}"
    return None


def _leer_ficha(ruta: Path) -> tuple[list[str] | None, str | None]:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return None, str(error)
    if not isinstance(datos, dict):
        return None, "la ficha no es un objeto"
    ids = datos.get("ids")
    if (
        not isinstance(ids, list)
        or not ids
        or not all(isinstance(i, str) and i for i in ids)
    ):
        return None, "lista de identificadores invalida"
    if len(set(ids)) != len(ids):
        return None, "identificadores repetidos en la ficha"
    return ids, None


def _mover_a_rechazados(
    contexto: RunContext, ruta: Path, politica: dict[str, int | float]
) -> bool:
    destino_carpeta = contexto.carpeta_rechazados
    if destino_carpeta is None:
        return False
    destino = destino_carpeta / ruta.name

    def operacion() -> bool:
        try:
            destino_carpeta.mkdir(parents=True, exist_ok=True)
            shutil.move(str(ruta), str(destino))
        except OSError as error:
            raise FalloManual("error_archivo", str(error)) from error
        return destino.exists()

    return _con_reintento(
        operacion, politica, f"{contexto.id_corrida} apartar {ruta.name}"
    ) is True


def _rechazar_archivo(
    contexto: RunContext,
    ruta: Path,
    codigo: str,
    motivo: str,
    politica: dict[str, int | float],
) -> None:
    movido = _mover_a_rechazados(contexto, ruta, politica)
    if movido:
        contexto.archivos_rechazados.append(ruta.name)
    else:
        logger.error(
            f"ERR-08 | run={contexto.id_corrida} | no se pudo apartar {ruta.name}"
        )
    registrar_evento(
        id_corrida=contexto.id_corrida,
        tipo="error",
        codigo=codigo,
        evidencia=f"archivo={ruta.name};motivo={motivo};apartado={'si' if movido else 'no'}",
    )


def _lineas_de_texto(texto: str) -> list[_Linea]:
    """Quita adornos del chat y devuelve solo líneas candidatas a respuesta."""
    resultado: list[_Linea] = []
    en_bloque = False
    for crudo in texto.splitlines():
        linea = crudo.strip()
        if linea.startswith("```"):
            en_bloque = not en_bloque
            continue
        if en_bloque or not linea:
            continue
        if "{" not in linea or "}" not in linea:
            continue
        candidato = linea[linea.index("{") : linea.rindex("}") + 1]
        try:
            datos = json.loads(candidato)
            if not isinstance(datos, dict):
                raise ValueError("la línea no es un objeto")
            resultado.append(_Linea(texto=linea, datos=datos))
        except (ValueError, TypeError):
            resultado.append(_Linea(texto=linea, motivo="linea_ilegible"))
    return resultado


def _codigo_de(motivo: str) -> str:
    if motivo in _MOTIVOS_ERR03:
        return "ERR-03"
    if motivo in _MOTIVOS_ERR04:
        return "ERR-04"
    return "ERR-05"


def _validar_linea(
    datos: dict[str, Any],
    estados: dict[str, str],
    ids_ficha: set[str],
    ya_aplicadas: set[str],
) -> tuple[dict[str, Any] | None, str | None]:
    """VAL-04: validación estricta, sin completar ni reinterpretar nada."""
    for clave in _CAMPOS_LINEA:
        if clave not in datos:
            if clave == "id":
                return None, "id_ausente"
            if clave in _VETOS:
                return None, "veto_ausente"
            return None, f"falta_{clave}"
    identificador = str(datos["id"]).strip()
    if not identificador or identificador.lower() in _VACIOS:
        return None, "id_invalido"
    for veto in _VETOS:
        if str(datos[veto]).strip().upper() not in _VALORES_VETO:
            return None, "veto_invalido"
    decision = str(datos["decision"]).strip().upper()
    if decision not in _DECISIONES:
        return None, "decision_invalida"
    votos = [str(datos[veto]).strip().upper() for veto in _VETOS]
    if decision == "APROBADA" and any(voto != "PASS" for voto in votos):
        return None, "decision_incoherente"
    if decision == "DESCARTADA" and not any(voto == "FAIL" for voto in votos):
        return None, "decision_incoherente"

    justificacion = str(datos["justificacion"]).strip()
    if not justificacion or justificacion.lower() in _VACIOS:
        return None, "justificacion_vacia"
    eje = str(datos["eje_organizacional"]).strip().upper()
    if eje not in _EJES:
        return None, "eje_invalido"
    if votos[0] == "FAIL" and eje != "NO_APLICA":
        return None, "eje_incoherente"
    if votos[0] == "PASS" and eje == "NO_APLICA":
        return None, "eje_incoherente"

    # El contrato del lote se comprueba primero: un identificador ajeno a la
    # ficha se rechaza como "fuera_de_lote" aunque exista en la base.
    if identificador not in ids_ficha:
        return None, "fuera_de_lote"
    if identificador not in estados:
        return None, "oferta_inexistente"
    if estados[identificador] != "preparada":
        return None, "no_pendiente"
    if identificador in ya_aplicadas:
        return None, "repetida"
    return datos, None


def _aplicar(
    contexto: RunContext,
    datos: dict[str, Any],
    politica: dict[str, int | float],
    evaluador: str,
) -> bool:
    """Pasos 5-6: transición, resultado completo, evento y contador."""
    identificador = str(datos["id"]).strip()
    aprobada = str(datos["decision"]).strip().upper() == "APROBADA"
    destino = OfferState.ACEPTADA_EI if aprobada else OfferState.DESCARTADA_EI
    try:
        transition(OfferState.PREPARADA, OfferState.EVALUADA)
        transition(OfferState.EVALUADA, destino)
    except InternalError as error:
        logger.error(f"ERR-06 | run={contexto.id_corrida} | {error}")
        return False

    resultado = {
        "eje_organizacional": str(datos["eje_organizacional"]).strip().upper(),
        "v1": str(datos["v1"]).strip().upper(),
        "v2": str(datos["v2"]).strip().upper(),
        "v3": str(datos["v3"]).strip().upper(),
        "v4": str(datos["v4"]).strip().upper(),
        "v5": str(datos["v5"]).strip().upper(),
        "decision": str(datos["decision"]).strip().upper(),
        "justificacion": str(datos["justificacion"]).strip(),
        "evaluador": evaluador,
    }
    resultado_json = json.dumps(resultado, ensure_ascii=False)

    def operacion() -> bool:
        try:
            actualizado = actualizar_fila(
                "ofertas_descubiertas",
                identificador,
                {
                    "estado": destino.value,
                    "resultado_evaluacion_inicial": resultado_json,
                },
            )
        except Exception as error:
            raise FalloManual("error_bd", str(error)) from error
        if not actualizado:
            raise FalloManual("error_bd", f"la oferta {identificador} no existe")
        return True

    if _con_reintento(
        operacion, politica, f"{contexto.id_corrida} oferta {identificador}"
    ) is not True:
        registrar_evento(
            id_corrida=contexto.id_corrida,
            tipo="error",
            codigo="ERR-06",
            evidencia=f"id={identificador};fallo persistente al aplicar",
            id_oferta=identificador,
        )
        return False

    if aprobada:
        contexto.contador_aprobadas += 1
        registrar_evento(
            id_corrida=contexto.id_corrida,
            tipo="suceso",
            codigo="oferta_aprobada",
            evidencia=f"evaluador={evaluador};decision=APROBADA",
            id_oferta=identificador,
        )
    else:
        contexto.contador_descartadas += 1
        registrar_evento(
            id_corrida=contexto.id_corrida,
            tipo="suceso",
            codigo="oferta_descartada",
            evidencia=(
                f"evaluador={evaluador};veto={_primer_veto(resultado)};"
                "decision=DESCARTADA"
            ),
            id_oferta=identificador,
        )
    return True


def _primer_veto(resultado: dict[str, Any]) -> str:
    return next(
        (veto for veto in _VETOS if resultado[veto] == "FAIL"),
        "N/A",
    )


def _borrar(ruta: Path, politica: dict[str, int | float], id_corrida: str) -> bool:
    def operacion() -> bool:
        try:
            ruta.unlink(missing_ok=True)
        except OSError as error:
            raise FalloManual("error_archivo", str(error)) from error
        return not ruta.exists()

    return _con_reintento(operacion, politica, f"{id_corrida} borrar {ruta.name}") is True


def _emparejar(
    contexto: RunContext, politica: dict[str, int | float]
) -> list[_Lote]:
    """Paso 2: pares lote/respuesta por nombre base; sin pareja se apartan."""
    agrupados: dict[str, list[tuple[int, Path]]] = {}
    for ruta in contexto.archivos_resultados:
        encontrado = _PATRON_RESPUESTA.match(ruta.name)
        if encontrado is None:
            _rechazar_archivo(
                contexto, ruta, "ERR-02", "nombre_no_reconocido", politica
            )
            continue
        base = encontrado.group("base")
        parte = int(encontrado.group("parte") or 0)
        agrupados.setdefault(base, []).append((parte, ruta))

    assert contexto.carpeta_lotes is not None
    lotes: list[_Lote] = []
    for base in sorted(agrupados):
        ficha = contexto.carpeta_lotes / f"{base}.json"
        texto = contexto.carpeta_lotes / f"{base}.md"
        if not ficha.is_file() or not texto.is_file():
            for _, ruta in agrupados[base]:
                _rechazar_archivo(contexto, ruta, "ERR-02", "lote_ausente", politica)
            continue
        _, problema = _leer_ficha(ficha)
        if problema is not None:
            for _, ruta in agrupados[base]:
                _rechazar_archivo(
                    contexto, ruta, "ERR-02", "ficha_ilegible", politica
                )
            continue
        respuestas = [
            ruta
            for _, ruta in sorted(
                agrupados[base], key=lambda par: (par[0], par[1].name)
            )
        ]
        lotes.append(
            _Lote(
                base=base,
                ficha=ficha,
                texto=texto,
                respuestas=respuestas,
            )
        )
    return lotes


def _procesar_lote(
    contexto: RunContext,
    lote: _Lote,
    ids: list[str],
    politica: dict[str, int | float],
    evaluador: str,
    ya_aplicadas: set[str],
) -> bool:
    """Pasos 3-8 de un lote; False si hubo un fallo crítico (ERR-06)."""
    lineas: list[_Linea] = []
    for ruta in lote.respuestas:
        try:
            contenido = ruta.read_text(encoding="utf-8")
        except OSError as error:
            _rechazar_archivo(contexto, ruta, "ERR-02", str(error), politica)
            continue
        lineas.extend(_lineas_de_texto(contenido))

    if not lineas:
        for ruta in lote.respuestas:
            _rechazar_archivo(
                contexto, ruta, "ERR-03", "archivo_sin_lineas", politica
            )
        return True

    estados = leer_estados_ofertas(ids)
    ids_ficha = set(ids)
    aplicadas: list[str] = []
    rechazadas: list[tuple[str, str, str]] = []
    for linea in lineas:
        if linea.motivo is not None:
            rechazadas.append(("N/A", linea.motivo, linea.texto))
            continue
        assert linea.datos is not None
        valida, motivo = _validar_linea(
            linea.datos, estados, ids_ficha, ya_aplicadas
        )
        if motivo is not None:
            rechazadas.append(
                (str(linea.datos.get("id", "N/A")), motivo, linea.texto)
            )
            continue
        assert valida is not None
        identificador = str(valida["id"]).strip()
        if not _aplicar(contexto, valida, politica, evaluador):
            return False
        aplicadas.append(identificador)
        ya_aplicadas.add(identificador)

    for identificador, motivo, texto in rechazadas:
        contexto.contador_rechazadas += 1
        registrar_evento(
            id_corrida=contexto.id_corrida,
            tipo="error",
            codigo="evaluacion_rechazada",
            evidencia=(
                f"lote={lote.base};codigo={_codigo_de(motivo)};motivo={motivo};"
                f"id={identificador};linea={texto[:120]}"
            ),
            id_oferta=identificador,
        )

    estados_finales = leer_estados_ofertas(ids)
    faltantes = [
        identificador
        for identificador in ids
        if estados_finales.get(identificador) == "preparada"
    ]
    archivos = [lote.texto, lote.ficha, *lote.respuestas]
    eliminados = 0
    if not faltantes:
        for ruta in archivos:
            if _borrar(ruta, politica, contexto.id_corrida):
                eliminados += 1
            else:
                contexto.archivos_no_eliminados.append(ruta.name)
                logger.error(
                    f"ERR-08 | run={contexto.id_corrida} | "
                    f"no se pudo borrar {ruta.name}"
                )
        contexto.lotes_cerrados.append(lote.base)
    else:
        contexto.lotes_conservados.append(lote.base)
        contexto.faltantes_por_lote[lote.base] = faltantes
        registrar_evento(
            id_corrida=contexto.id_corrida,
            tipo="suceso",
            codigo="lote_conservado",
            evidencia=(
                f"lote={lote.base};faltantes={len(faltantes)};"
                f"ids={','.join(faltantes[:10])}"
            ),
        )

    registrar_evento(
        id_corrida=contexto.id_corrida,
        tipo="suceso",
        codigo="evaluaciones_importadas",
        evidencia=(
            f"lote={lote.base};aplicadas={len(aplicadas)};"
            f"rechazadas={len(rechazadas)};faltantes={len(faltantes)};"
            f"eliminados={eliminados};"
            f"no_eliminados={len(contexto.archivos_no_eliminados)}"
        ),
    )
    contexto.contador_lotes += 1
    return True


def ejecutar_importacion(contexto: RunContext | None) -> ResultadoImportacion:
    """Paso 1-9 del nodo Importar evaluaciones, en orden obligatorio."""
    problema = _validar_insumos(contexto)
    if problema is not None:
        codigo, detalle = problema
        return _fallo(contexto, codigo, detalle)
    assert contexto is not None
    try:
        politica = _politica_reintentos(contexto.config_evaluacion_manual)
    except (KeyError, TypeError, ValueError) as error:
        return _fallo(contexto, "ERR-01", f"configuracion no usable: {error}")
    evaluador = str(contexto.config_evaluacion_manual["modelo_evaluador"]).strip()

    lotes = _emparejar(contexto, politica)
    ya_aplicadas: set[str] = set()
    for lote in lotes:
        ids, problema_ficha = _leer_ficha(lote.ficha)
        if ids is None:
            # La ficha se validó al emparejar: cambios entre medias se informan.
            registrar_evento(
                id_corrida=contexto.id_corrida,
                tipo="error",
                codigo="ERR-02",
                evidencia=f"lote={lote.base};ficha={problema_ficha}",
            )
            continue
        if not _procesar_lote(
            contexto, lote, ids, politica, evaluador, ya_aplicadas
        ):
            # El evento ERR-06 ya lo escribió `_aplicar`; no duplicar la huella.
            return ResultadoImportacion(
                estado="error",
                contexto=contexto,
                codigo="ERR-06",
                descripcion=f"fallo critico al aplicar el lote {lote.base}",
            )

    return ResultadoImportacion(estado="ok", contexto=contexto)
