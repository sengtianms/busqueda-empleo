"""Comando del operador: importa lo que devolvió el chat (Fase 4, D76).

Una sola acción: lanza el flujo de importación del Módulo 3, muestra el informe
que calcula su cierre, avisa en el escritorio y devuelve una salida honesta.
No pide argumentos; trabaja sobre la carpeta configurada. La opción `--db`
permite ensayar sobre una copia, como en los mandos de la tanda.

La corrida y su traza las escribe el módulo. Este comando solo informa: un fallo
del aviso nunca cambia el resultado de la importación.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.evaluation.orchestrator_manual import ejecutar_flujo_importacion
from scripts.notificar_veredicto import componer_importacion, enviar_aviso
from shared.persistence import change_path, reset_path

_MOTIVOS_CORRECTOS = frozenset({"corrida_completada", "sin_resultados"})
_ETIQUETAS = {
    "corrida_completada": "completada",
    "sin_resultados": "sin resultados",
    "error_total": "sin resultados aplicables",
    "error_critico": "fallo de infraestructura",
    "aborto": "interrumpida",
    "concurrencia": "omitida: otra corrida activa",
}


def _numero(informe: dict[str, Any], clave: str) -> int:
    valor = informe.get(clave, 0)
    return int(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else 0


def _lista(informe: dict[str, Any], clave: str) -> list[str]:
    valor = informe.get(clave, [])
    return [str(elemento) for elemento in valor] if isinstance(valor, list) else []


def componer_informe(motivo: str, informe: dict[str, Any]) -> str:
    """Informe legible para la pantalla del operador."""
    lineas = ["== IMPORTACIÓN DE EVALUACIONES =="]
    id_corrida = str(informe.get("id_corrida") or "sin corrida")
    lineas.append(f"Corrida: {id_corrida}")
    lineas.append(f"Resultado: {_ETIQUETAS.get(motivo, motivo)}")

    if motivo == "sin_resultados":
        lineas.append("No había respuestas en la carpeta: no se aplicó nada.")
        return "\n".join(lineas)

    aprobadas = _numero(informe, "aprobadas")
    descartadas = _numero(informe, "descartadas")
    rechazadas = _numero(informe, "rechazadas")
    cerrados = _lista(informe, "lotes_cerrados")
    conservados = _lista(informe, "lotes_conservados")
    faltantes = informe.get("faltantes", {})
    apartados = _lista(informe, "archivos_rechazados")
    no_borrados = _lista(informe, "archivos_no_eliminados")

    lineas.append(
        f"Aplicadas: {aprobadas} aprobadas / {descartadas} descartadas "
        f"· Rechazadas: {rechazadas}"
    )
    lineas.append(f"Lotes cerrados: {len(cerrados)} · Conservados: {len(conservados)}")
    if conservados:
        total_pendientes = 0
        for lote in conservados:
            ids = faltantes.get(lote, []) if isinstance(faltantes, dict) else []
            total_pendientes += len(ids) if isinstance(ids, list) else 0
            nombres = ", ".join(str(i) for i in ids) or "N/R"
            lineas.append(f"  · {lote}: quedan pendientes {nombres}")
        lineas.append(f"Ofertas que siguen pendientes: {total_pendientes}")
    else:
        lineas.append("Ofertas que siguen pendientes: ninguna")
    if apartados:
        lineas.append(f"Archivos apartados: {', '.join(apartados)}")
    if no_borrados:
        lineas.append(f"Archivos que no se pudieron borrar: {', '.join(no_borrados)}")
    lineas.append("La traza completa queda en la base de datos.")
    return "\n".join(lineas)


def importar(db: Path | None = None) -> tuple[int, str]:
    """Ejecuta el flujo y devuelve (código de salida, texto del informe)."""
    if db is not None:
        change_path(db)
    try:
        # El propio flujo inicializa el esquema; aquí solo se ejecuta y se informa.
        resultado = ejecutar_flujo_importacion()
    finally:
        if db is not None:
            reset_path()

    if resultado is None:
        mensaje = (
            "== IMPORTACIÓN DE EVALUACIONES ==\n"
            "Resultado: no se pudo iniciar\n"
            "No se registró ninguna corrida; revisa la bitácora del sistema."
        )
        enviar_aviso("Importación no iniciada: revisa la bitácora del sistema", "critical")
        return 1, mensaje

    motivo = resultado.codigo
    informe = resultado.informe or {}
    texto = componer_informe(motivo, informe)
    cuerpo, urgencia = componer_importacion(motivo, informe)
    enviar_aviso(cuerpo, urgencia)
    return (0 if motivo in _MOTIVOS_CORRECTOS else 1), texto


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="ruta alternativa a la base de datos (ensayo)")
    args = parser.parse_args(argv)
    codigo, texto = importar(Path(args.db) if args.db else None)
    print(texto)
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
