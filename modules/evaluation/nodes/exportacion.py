"""Nodo "Exportar ofertas" del proceso de exportación (M3 v2.0, Fase 2).

Convierte las ofertas en `preparada` en lotes legibles por un chat, con su
ficha de control interna y la instrucción de evaluación al día. No escribe en
las ofertas: la base queda intacta y solo se anotan sucesos en la trazabilidad.

Orden obligatorio de la ficha: comprobar lotes pendientes (guardián),
refrescar la instrucción, agrupar en lotes, escribir texto y ficha de control,
registrar un suceso por lote y entregar control a "Finalizar Proceso" (Fase 3).

Los identificadores de la interfaz son españoles, conforme a la excepción
registrada para los nodos de `modules/evaluation/` (D49 y D76).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

from loguru import logger

from modules.evaluation.run_context import RunContext
from shared.evaluacion import (
    limpiar_descripcion_para_evaluacion,
    validar_evaluacion_manual,
)
from shared.persistence import leer_estados_ofertas, registrar_evento
from shared.retry import ejecutar_con_reintento
from shared.utilidades import ahora

_RAIZ_PROYECTO = Path(__file__).resolve().parents[3]
RUTA_PROMPT = _RAIZ_PROYECTO / "prompts" / "initial_evaluation" / "compatibility.md"

_PATRON_LOTE = re.compile(r"^(?P<base>[A-Z]+-\d{4}_lote_\d{3,})\.(?:md|json)$")
_HUELLA_INSTRUCCION = re.compile(
    r"<!--\s*instruccion_evaluacion\s*\|\s*huella:\s*([0-9a-f]{64})\s*-->"
)

_NOTA_RECORTE = (
    "[Nota: descripción recortada a 6.000 caracteres; el texto completo "
    "permanece en la base.]"
)

_CAMPOS_LOTE = ("Título", "Empresa", "Ubicación", "Modalidad", "Descripción")

_ENCABEZADO_INSTRUCCION = "# Instrucción de evaluación inicial — procesamiento por lotes"

_PREAMBULO_INSTRUCCION = (
    "Esta instrucción se aplica a un lote de ofertas. Cada bloque del archivo "
    "adjunto trae una oferta con su identificador, título, empresa, ubicación, "
    "modalidad y descripción. Evalúa TODAS las ofertas del lote con las reglas "
    "siguientes. Los marcadores {{titulo}}, {{descripcion_original}}, "
    "{{modalidad}} y {{ubicacion}} del prompt se refieren a los datos de cada "
    "bloque."
)

_JSON_EJEMPLO = (
    '{"id": "...", "entregable_principal": "...", "v1": "PASS|FAIL", '
    '"v2": "PASS|FAIL", "v3": "PASS|FAIL", "v4": "PASS|FAIL", '
    '"v5": "PASS|FAIL", "decision": "APROBADA|DESCARTADA", '
    '"justificacion": "..."}'
)

_SALIDA_POR_LOTES = """\
## FORMATO DE RESPUESTA PARA EL LOTE (prevalece sobre la sección SALIDA)

Procesa el archivo del lote adjunto y devuelve una línea JSON por oferta, sin
bloques de código, sin texto adicional y sin líneas vacías. Cada línea tiene
exactamente estos campos:

@@JSON@@

- `id`: el identificador exacto del bloque de la oferta. No lo inventes ni lo
  modifiques.
- `v1` a `v5`: solo `PASS` o `FAIL`, según las cinco reglas de veto.
- `decision`: `APROBADA` solo si los cinco vetos son `PASS`; `DESCARTADA` si al
  menos uno es `FAIL`.
- `entregable_principal`: una sola línea, máximo 20 palabras, sin comillas
  dobles. Se admite `N/A` únicamente cuando la oferta no trae descripción, `v3`
  es `FAIL` y la decisión es `DESCARTADA`.
- `justificacion`: una sola línea, máximo 60 palabras, específica de esta
  oferta y con evidencia concreta de su descripción. Sin comillas dobles,
  barras invertidas ni llaves. Si la decisión es `DESCARTADA`, nombra todos los
  vetos que la descartan.
- No repitas ofertas y no omitas ninguna.
- Si la respuesta se corta, continúa en un mensaje nuevo; el operador lo
  guardará como una parte.
""".replace("@@JSON@@", _JSON_EJEMPLO)

T = TypeVar("T")


@dataclass
class ResultadoExportacion:
    """Outcome handed to the export flow orchestrator (built in Fase 3)."""

    estado: str  # "ok" | "error"
    contexto: RunContext | None = None
    codigo: str = ""
    descripcion: str = ""


class ErrorArchivo(Exception):
    """File operation failure carrying a retryable flow code."""

    def __init__(self, mensaje: str) -> None:
        super().__init__(mensaje)
        self.codigo_motivo = "error_archivo"


@dataclass
class _LoteEncontrado:
    base: str
    ficha: Path | None = None
    texto: Path | None = None


def _fallo(
    contexto: RunContext | None, codigo: str, descripcion: str
) -> ResultadoExportacion:
    if contexto is not None:
        registrar_evento(
            id_corrida=contexto.id_corrida,
            tipo="error",
            codigo=codigo,
            evidencia=descripcion,
        )
    logger.error(f"{codigo} | exportacion | {descripcion}")
    return ResultadoExportacion(
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


def _verificar_escritura(carpeta: Path) -> None:
    """Sonda de escritura: crea y borra un archivo temporal en la carpeta."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=carpeta,
        prefix=".sonda_",
        suffix=".tmp",
        delete=True,
        encoding="utf-8",
    ) as sonda:
        sonda.write("ok")


def _validar_insumos(contexto: RunContext | None) -> tuple[str, str] | None:
    """VAL-01/VAL-05: insumos presentes, configuración válida y carpeta escribible."""
    if contexto is None:
        return "ERR-01", "contexto ausente"
    if not isinstance(contexto.candidatas, list) or not contexto.candidatas:
        return "ERR-01", "lista de candidatas vacia o no accesible"
    seccion = contexto.config_evaluacion_manual
    if not isinstance(seccion, dict):
        return "ERR-01", "configuracion manual ausente"
    problema = validar_evaluacion_manual(seccion)
    if problema is not None:
        return "ERR-01", f"configuracion manual invalida: {problema}"
    if not contexto.carpetas_resueltas or contexto.carpeta_lotes is None:
        return "ERR-01", "carpetas de trabajo no resueltas"
    if not contexto.carpeta_lotes.is_dir():
        return "ERR-01", "carpeta de lotes no disponible"
    if contexto.carpeta_base is None or not contexto.carpeta_base.is_dir():
        return "ERR-01", "carpeta base no disponible"
    try:
        _verificar_escritura(contexto.carpeta_lotes)
    except OSError as error:
        return "ERR-02", f"carpeta de lotes no escribible: {error}"
    return None


def _descubrir_lotes(carpeta: Path) -> list[_LoteEncontrado]:
    """Pares texto/ficha existentes, agrupados por nombre base."""
    lotes: dict[str, _LoteEncontrado] = {}
    for ruta in sorted(carpeta.iterdir()):
        if not ruta.is_file():
            continue
        encontrado = _PATRON_LOTE.match(ruta.name)
        if encontrado is None:
            continue
        base = encontrado.group("base")
        lote = lotes.setdefault(base, _LoteEncontrado(base=base))
        if ruta.suffix == ".json":
            lote.ficha = ruta
        else:
            lote.texto = ruta
    return list(lotes.values())


def _leer_ficha(ruta: Path) -> tuple[list[str] | None, str | None]:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return None, str(error)
    if not isinstance(datos, dict):
        return None, "la ficha no es un objeto"
    for clave in ("id_corrida", "lote", "fecha"):
        if not isinstance(datos.get(clave), str) or not datos[clave]:
            return None, f"campo {clave} ausente en la ficha"
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


def _archivos_del_lote(carpeta: Path, base: str) -> list[Path]:
    """Texto, ficha y posibles partes de respuesta de un mismo lote."""
    return sorted(
        ruta
        for ruta in carpeta.iterdir()
        if ruta.is_file()
        and (
            ruta.name in (f"{base}.md", f"{base}.json", f"{base}.jsonl")
            or (
                ruta.name.startswith(f"{base}_parte")
                and ruta.suffix == ".jsonl"
            )
        )
    )


def _escribir_temporal(destino: Path, contenido: str) -> Path:
    descriptor, nombre = tempfile.mkstemp(
        prefix=".tmp_", suffix=destino.suffix, dir=destino.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
            archivo.write(contenido)
            archivo.flush()
            os.fsync(archivo.fileno())
        return Path(nombre)
    except Exception:
        Path(nombre).unlink(missing_ok=True)
        raise


def _escribir_archivo(destino: Path, contenido: str) -> None:
    if not contenido.strip():
        raise ErrorArchivo(f"contenido vacio para {destino.name}")
    try:
        temporal = _escribir_temporal(destino, contenido)
    except OSError as error:
        raise ErrorArchivo(str(error)) from error
    try:
        os.replace(temporal, destino)
    except OSError as error:
        temporal.unlink(missing_ok=True)
        raise ErrorArchivo(str(error)) from error


def _escribir_par(
    ruta_md: Path, texto_md: str, ruta_json: Path, texto_json: str
) -> None:
    """Escribe texto y ficha juntos; si falla, no deja archivos a medias."""
    temporales: list[Path] = []
    finales: list[Path] = []
    try:
        for destino, contenido in ((ruta_md, texto_md), (ruta_json, texto_json)):
            if not contenido.strip():
                raise ErrorArchivo(f"contenido vacio para {destino.name}")
            temporales.append(_escribir_temporal(destino, contenido))
        os.replace(temporales[0], ruta_md)
        finales.append(ruta_md)
        os.replace(temporales[1], ruta_json)
        finales.append(ruta_json)
    except Exception as error:
        for ruta in finales:
            ruta.unlink(missing_ok=True)
        if isinstance(error, ErrorArchivo):
            raise
        raise ErrorArchivo(str(error)) from error
    finally:
        for temporal in temporales:
            temporal.unlink(missing_ok=True)


def _borrar_archivo(ruta: Path) -> None:
    try:
        ruta.unlink(missing_ok=True)
    except OSError as error:
        raise ErrorArchivo(str(error)) from error


def _con_reintento(
    operacion: Callable[[], T], politica: dict[str, int | float], contexto_log: str
) -> T | None:
    """Runs `operacion` with the manual-process retry policy.

    Returns its result or ``None`` when every attempt failed. Only file
    failures carrying `error_archivo` back off; deterministic errors surface
    immediately as ``None`` as well.
    """

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


def _borrar_con_reintento(
    ruta: Path, politica: dict[str, int | float], contexto_log: str
) -> bool:
    def operacion() -> bool:
        _borrar_archivo(ruta)
        return True

    return _con_reintento(operacion, politica, contexto_log) is True


def _escribir_archivo_con_reintento(
    ruta: Path,
    contenido: str,
    politica: dict[str, int | float],
    contexto_log: str,
) -> bool:
    def operacion() -> bool:
        _escribir_archivo(ruta, contenido)
        return True

    return _con_reintento(operacion, politica, contexto_log) is True


def _escribir_par_con_reintento(
    ruta_md: Path,
    texto_md: str,
    ruta_json: Path,
    texto_json: str,
    politica: dict[str, int | float],
    contexto_log: str,
) -> bool:
    def operacion() -> bool:
        _escribir_par(ruta_md, texto_md, ruta_json, texto_json)
        return True

    return _con_reintento(operacion, politica, contexto_log) is True


def _comprobar_lotes(
    contexto: RunContext, politica: dict[str, int | float]
) -> bool:
    """Guardián RN-07: True means "se puede exportar".

    Una ficha ilegible bloquea (no se puede saber si sus ofertas siguen
    pendientes). Un texto sin ficha y sin respuestas es un lote a medias: se
    descarta conforme a RN-09 en vez de bloquear futuras exportaciones. Las
    respuestas huérfanas se retiran también: el proceso de importación las
    rechazaría de todos modos.
    """
    if contexto.carpeta_lotes is None:
        return True
    carpeta = contexto.carpeta_lotes
    encontrados = _descubrir_lotes(carpeta)
    conocidos = {lote.base for lote in encontrados}
    bloqueantes: list[str] = []
    retirar: list[Path] = []
    bases_resueltas: set[str] = set()
    descartados = 0

    for lote in encontrados:
        archivos = _archivos_del_lote(carpeta, lote.base)
        if lote.ficha is None:
            con_respuestas = any(ruta.suffix == ".jsonl" for ruta in archivos)
            if con_respuestas:
                bloqueantes.append(f"{lote.base}:sin_ficha")
            else:
                retirar.extend(archivos)
                descartados += 1
                contexto.contador_errores += 1
                registrar_evento(
                    id_corrida=contexto.id_corrida,
                    tipo="error",
                    codigo="ERR-04",
                    evidencia=(
                        f"lote={lote.base};texto_sin_ficha;"
                        "lote a medias descartado (RN-09)"
                    ),
                )
                logger.warning(
                    f"lote_a_medias_descartado | run={contexto.id_corrida} | "
                    f"{lote.base}"
                )
            continue
        ids, problema = _leer_ficha(lote.ficha)
        if problema is not None:
            bloqueantes.append(f"{lote.base}:ficha_ilegible")
            continue
        assert ids is not None
        estados = leer_estados_ofertas(ids)
        pendientes = sum(
            1 for identificador in ids if estados.get(identificador) == "preparada"
        )
        if pendientes:
            bloqueantes.append(f"{lote.base}:pendientes={pendientes}")
        else:
            bases_resueltas.add(lote.base)
            retirar.extend(archivos)

    for ruta in sorted(carpeta.iterdir()):
        if not ruta.is_file() or ruta.suffix != ".jsonl":
            continue
        if any(
            ruta.name == f"{base}.jsonl" or ruta.name.startswith(f"{base}_parte")
            for base in conocidos
        ):
            continue
        retirar.append(ruta)

    retirados = 0
    nombres: list[str] = []
    for ruta in sorted(set(retirar), key=lambda ruta: ruta.name):
        borrado = _borrar_con_reintento(
            ruta, politica, f"{contexto.id_corrida} retiro {ruta.name}"
        )
        if borrado:
            retirados += 1
            nombres.append(ruta.name)
        else:
            logger.error(
                f"ERR-02 | run={contexto.id_corrida} | no se pudo retirar {ruta.name}"
            )

    if retirados:
        bases = ";".join(sorted(bases_resueltas)[:10])
        registrar_evento(
            id_corrida=contexto.id_corrida,
            tipo="suceso",
            codigo="lotes_retirados",
            evidencia=(
                f"lotes={len(bases_resueltas)};archivos={retirados};"
                f"descarte={descartados};bases={bases};"
                f"nombres={';'.join(nombres[:6])}"
            ),
        )

    if bloqueantes:
        detalle = ";".join(bloqueantes[:10])
        registrar_evento(
            id_corrida=contexto.id_corrida,
            tipo="suceso",
            codigo="exportacion_omitida",
            evidencia=f"lotes={len(bloqueantes)};{detalle}",
        )
        logger.info(f"exportacion_omitida | run={contexto.id_corrida} | {detalle}")
        return False
    return True


def _cuerpo_instruccion(prompt: str) -> str:
    """Prompt oficial íntegro + contexto de lote + formato de respuesta."""
    return "\n\n".join(
        (
            _ENCABEZADO_INSTRUCCION,
            _PREAMBULO_INSTRUCCION,
            "---",
            prompt.strip(),
            "---",
            _SALIDA_POR_LOTES.strip(),
        )
    )


def _refrescar_instruccion(
    contexto: RunContext, politica: dict[str, int | float]
) -> tuple[str, str] | None:
    """VAL-06: deja la instrucción vigente; ``(codigo, detalle)`` si falla."""
    try:
        prompt = RUTA_PROMPT.read_text(encoding="utf-8")
    except OSError as error:
        return "ERR-01", f"prompt oficial no legible: {error}"
    if not prompt.strip():
        return "ERR-01", "prompt oficial vacio"

    cuerpo = _cuerpo_instruccion(prompt)
    huella = hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()
    contenido = f"<!-- instruccion_evaluacion | huella: {huella} -->\n\n{cuerpo}\n"
    if contexto.carpeta_base is None:
        return "ERR-01", "carpeta base no resuelta"
    ruta = contexto.carpeta_base / "instruccion_evaluacion.md"

    if ruta.exists():
        try:
            actual = ruta.read_text(encoding="utf-8")
        except OSError as error:
            return "ERR-02", f"instruccion existente no legible: {error}"
        vigente = _HUELLA_INSTRUCCION.search(actual)
        if vigente is not None and vigente.group(1) == huella:
            logger.debug(f"instruccion_vigente | run={contexto.id_corrida}")
            return None

    escrita = _escribir_archivo_con_reintento(
        ruta,
        contenido,
        politica,
        f"{contexto.id_corrida} instruccion_evaluacion.md",
    )
    if not escrita:
        return "ERR-02", "no se pudo escribir la instruccion del chat"
    try:
        comprobada = ruta.read_text(encoding="utf-8")
    except OSError as error:
        return "ERR-02", f"instruccion escrita no verificable: {error}"
    if not comprobada.strip() or huella not in comprobada:
        return "ERR-02", "instruccion escrita no verificada"
    logger.info(
        f"instruccion_refrescada | run={contexto.id_corrida} | huella={huella[:12]}"
    )
    return None


def _agrupar(
    candidatas: list[dict[str, Any]], tamano: int
) -> list[list[dict[str, Any]]]:
    return [candidatas[i : i + tamano] for i in range(0, len(candidatas), tamano)]


def _valor_campo(valor: Any) -> str:
    texto = " ".join(str(valor if valor is not None else "").split())
    return texto or "N/A"


def _descripcion_para_lote(valor: Any) -> str:
    texto, recortado = limpiar_descripcion_para_evaluacion(str(valor or ""))
    resultado = texto or "N/A"
    if recortado:
        resultado += f"\n\n{_NOTA_RECORTE}"
    return resultado


def _texto_del_lote(
    id_corrida: str,
    numero: int,
    fecha: str,
    ofertas: list[dict[str, Any]],
) -> str:
    cabecera = (
        f"# Evaluación inicial — lote {numero:03d}\n\n"
        f"- Corrida: {id_corrida}\n"
        f"- Lote: {numero:03d}\n"
        f"- Fecha: {fecha}\n"
        f"- Ofertas: {len(ofertas)}\n"
    )
    bloques: list[str] = []
    for indice, oferta in enumerate(ofertas, 1):
        identificador = _valor_campo(oferta.get("id"))
        bloques.append(
            "\n".join(
                (
                    f"## Oferta {indice} — {identificador}",
                    "",
                    f"- Título: {_valor_campo(oferta.get('titulo'))}",
                    f"- Empresa: {_valor_campo(oferta.get('empresa'))}",
                    f"- Ubicación: {_valor_campo(oferta.get('ubicacion'))}",
                    f"- Modalidad: {_valor_campo(oferta.get('modalidad'))}",
                    "- Descripción:",
                    _descripcion_para_lote(oferta.get("descripcion_original")),
                )
            )
        )
    return cabecera + "\n---\n\n" + "\n\n---\n\n".join(bloques) + "\n"


def _ficha_del_lote(
    id_corrida: str, numero: int, fecha: str, ids: list[str]
) -> str:
    datos = {
        "id_corrida": id_corrida,
        "lote": f"{numero:03d}",
        "fecha": fecha,
        "ids": ids,
    }
    return json.dumps(datos, ensure_ascii=False, indent=2) + "\n"


def _verificar_lote(
    ruta_md: Path, ruta_json: Path, ids: list[str]
) -> str | None:
    try:
        texto = ruta_md.read_text(encoding="utf-8")
        ficha = json.loads(ruta_json.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return f"verificacion fallida: {error}"
    if not texto.strip():
        return "archivo de lote vacio"
    if not isinstance(ficha, dict) or ficha.get("ids") != ids:
        return "la ficha de control no coincide con el lote"
    for identificador in ids:
        if identificador not in texto:
            return f"identificador ausente en el lote: {identificador}"
    for campo in _CAMPOS_LOTE:
        if campo not in texto:
            return f"campo ausente en el lote: {campo}"
    return None


def _descartar_lote(ruta_md: Path, ruta_json: Path) -> None:
    for ruta in (ruta_md, ruta_json):
        try:
            ruta.unlink(missing_ok=True)
        except OSError as error:
            logger.error(f"ERR-03 | no se pudo descartar {ruta.name}: {error}")


def ejecutar_exportacion(contexto: RunContext | None) -> ResultadoExportacion:
    """Paso 1-7 del nodo Exportar ofertas, en orden obligatorio."""
    problema = _validar_insumos(contexto)
    if problema is not None:
        codigo, detalle = problema
        return _fallo(contexto, codigo, detalle)
    assert contexto is not None
    seccion = contexto.config_evaluacion_manual
    try:
        politica = _politica_reintentos(seccion)
        tamano = int(seccion["tamano_lote"])
    except (KeyError, TypeError, ValueError) as error:
        return _fallo(contexto, "ERR-01", f"configuracion manual no usable: {error}")

    # Paso 1 — guardián de lotes.
    try:
        if not _comprobar_lotes(contexto, politica):
            return ResultadoExportacion(estado="ok", contexto=contexto)
    except Exception as error:
        return _fallo(contexto, "ERR-01", f"guardián de lotes no decidible: {error}")

    # Paso 2 — instrucción del chat.
    error_instruccion = _refrescar_instruccion(contexto, politica)
    if error_instruccion is not None:
        codigo, detalle = error_instruccion
        return _fallo(contexto, codigo, detalle)

    # Pasos 3-6 — lotes, fichas y sucesos.
    assert contexto.carpeta_lotes is not None
    fecha = ahora()
    for numero, grupo in enumerate(_agrupar(contexto.candidatas, tamano), 1):
        base = f"{contexto.id_corrida}_lote_{numero:03d}"
        ruta_md = contexto.carpeta_lotes / f"{base}.md"
        ruta_json = contexto.carpeta_lotes / f"{base}.json"
        ids = [_valor_campo(oferta.get("id")) for oferta in grupo]
        texto_md = _texto_del_lote(contexto.id_corrida, numero, fecha, grupo)
        texto_json = _ficha_del_lote(contexto.id_corrida, numero, fecha, ids)

        escrito = _escribir_par_con_reintento(
            ruta_md,
            texto_md,
            ruta_json,
            texto_json,
            politica,
            f"{contexto.id_corrida} lote {numero:03d}",
        )
        if not escrito:
            _descartar_lote(ruta_md, ruta_json)
            contexto.contador_errores += 1
            registrar_evento(
                id_corrida=contexto.id_corrida,
                tipo="error",
                codigo="ERR-03",
                evidencia=f"lote={numero:03d};archivo={ruta_md.name};escritura agotada",
            )
            logger.error(f"ERR-03 | run={contexto.id_corrida} | lote {numero:03d}")
            continue

        inconsistencia = _verificar_lote(ruta_md, ruta_json, ids)
        if inconsistencia is not None:
            _descartar_lote(ruta_md, ruta_json)
            contexto.contador_errores += 1
            registrar_evento(
                id_corrida=contexto.id_corrida,
                tipo="error",
                codigo="ERR-04",
                evidencia=f"lote={numero:03d};archivo={ruta_md.name};{inconsistencia}",
            )
            logger.error(
                f"ERR-04 | run={contexto.id_corrida} | lote {numero:03d} | "
                f"{inconsistencia}"
            )
            continue

        try:
            registrar_evento(
                id_corrida=contexto.id_corrida,
                tipo="suceso",
                codigo="ofertas_exportadas",
                evidencia=(
                    f"lote={numero:03d};archivo={ruta_md.name};"
                    f"ficha={ruta_json.name};cantidad={len(grupo)}"
                ),
            )
        except Exception as error:
            logger.error(
                f"ERR-05 | run={contexto.id_corrida} | suceso del lote "
                f"{numero:03d} no registrado: {error}"
            )
        contexto.contador_exportadas += len(grupo)
        contexto.contador_lotes += 1

    # Paso 7 — entrega única de control a "Finalizar Proceso" (Fase 3).
    return ResultadoExportacion(estado="ok", contexto=contexto)
