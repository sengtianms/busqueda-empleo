"""Execution context of an evaluation run (nodo INICIO, ficha Módulo 3).

RunContext is the single object passed between the nodes of the official
Evaluation flow. It holds the validated `evaluacion:` configuration, the
FIFO candidate list loaded from `ofertas_descubiertas` (state `preparada`),
the per-run counters and the closure-motive slot that the candidate decision
fixes (`sin_pendientes`) — or the evaluation node fixes (`cupo_agotado`) —
and "Finalizar Proceso" consumes. It is created by the INICIO node and
contains no node logic: nodes only read and update its fields.

Since the Module 3 redesign (D76) the same context also carries the manual
two-process state, kept additive so the old AI flow keeps working during the
transition: the validated `evaluacion_manual:` section, the work-folder
paths, the result files listed by the import INICIO, `hubo_resultados` and
the export/import counters. Export runs leave the result-file fields empty;
import runs leave the candidate list empty.

Mirror of `modules/preparation/run_context.py` per the Module 3 sheet
("Estructura espejo de las fichas de los Módulos 1 y 2"); Spanish identifiers
follow the same convention exception approved for functional modules.
"""

from pathlib import Path
from typing import Any

from shared.persistence import generar_id
from shared.utilidades import ahora


class RunContext:
    """Carries all the state a single evaluation run needs across its nodes."""

    def __init__(
        self,
        config_evaluacion: dict[str, Any] | None = None,
        candidatas: list[dict[str, Any]] | None = None,
        id_corrida: str | None = None,
        fecha_inicio: str | None = None,
        config_evaluacion_manual: dict[str, Any] | None = None,
        archivos_resultados: list[Path] | None = None,
    ) -> None:
        self.id_corrida = id_corrida or generar_id("corridas")
        if not self.id_corrida:
            raise ValueError("id_corrida vacio")
        # La corrida puede fijar la marca de inicio (INICIO la registra en
        # `corridas` antes del bloqueo); sin ella se genera aquí.
        self.fecha_inicio: str = fecha_inicio or ahora()
        self.config_evaluacion: dict[str, Any] = (
            config_evaluacion if config_evaluacion is not None else {}
        )
        self.candidatas: list[dict[str, Any]] = (
            candidatas if candidatas is not None else []
        )
        self.hubo_candidatas: bool = len(self.candidatas) > 0
        self.contador_aprobadas: int = 0
        self.contador_descartadas: int = 0
        self.contador_errores: int = 0
        self.bloqueo_adquirido: bool = False
        # Memoria de puertas caídas de la corrida (D59): nombre -> motivo.
        # Una puerta que no responde a tiempo se salta en las ofertas
        # siguientes; la memoria se reinicia en cada corrida.
        self.puertas_caidas: dict[str, str] = {}
        # Slot de terminación controlada: la decisión de candidatas fija
        # `sin_pendientes` y el nodo de evaluación fija `cupo_agotado`;
        # "Finalizar Proceso" lo consume y registra.
        self.motivo_cierre: str | None = None
        self.motivo_marca_temporal: str | None = None
        # --- Procesos manuales (D76), aditivos: el flujo viejo los ignora ---
        self.config_evaluacion_manual: dict[str, Any] = (
            config_evaluacion_manual if config_evaluacion_manual is not None else {}
        )
        self.archivos_resultados: list[Path] = (
            list(archivos_resultados) if archivos_resultados is not None else []
        )
        self.hubo_resultados: bool = len(self.archivos_resultados) > 0
        self.contador_exportadas: int = 0
        self.contador_lotes: int = 0
        self.contador_rechazadas: int = 0
        # Rutas de carpeta resueltas por el INICIO manual (base, lotes,
        # resultados y la de rechazados, que solo se crea al usarse).
        self.carpeta_base: Path | None = None
        self.carpeta_lotes: Path | None = None
        self.carpeta_resultados: Path | None = None
        self.carpeta_rechazados: Path | None = None
        # Seguimiento del proceso de importación (Fase 3), aditivo: el cierre
        # necesita saber qué lotes se cerraron, cuáles se conservaron y qué
        # ofertas siguen pendientes para el informe del operador.
        self.lotes_cerrados: list[str] = []
        self.lotes_conservados: list[str] = []
        self.faltantes_por_lote: dict[str, list[str]] = {}
        self.archivos_rechazados: list[str] = []
        self.archivos_no_eliminados: list[str] = []
        self.informe: dict[str, Any] = {}

    @property
    def carpetas_resueltas(self) -> bool:
        """True when the manual INICIO resolved every work-folder path."""
        return all(
            ruta is not None
            for ruta in (
                self.carpeta_base,
                self.carpeta_lotes,
                self.carpeta_resultados,
                self.carpeta_rechazados,
            )
        )
