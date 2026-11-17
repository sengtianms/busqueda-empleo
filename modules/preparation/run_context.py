"""Execution context of a preparation run (nodo INICIO, ficha Módulo 2).

RunContext is the single object passed between the nodes of the official
Preparation flow. It holds the validated `preparacion:` configuration, the
FIFO candidate list loaded from `ofertas_descubiertas`, the per-run counters
and the closure-motive slot that the candidate decision fixes and
"Finalizar Proceso" consumes. It is created by the INICIO node and contains
no node logic: nodes only read and update its fields.

Mirror of `modules/discovery/run_context.py` per the Module 2 sheet
("Estructura espejo de la ficha del Módulo 1"); Spanish identifiers follow
the same convention exception approved for functional modules.
"""

from typing import Any

from modules.preparation.ubicaciones import CatalogoUbicaciones
from shared.persistence import generar_id
from shared.utilidades import ahora


class RunContext:
    """Carries all the state a single preparation run needs across its nodes."""

    def __init__(
        self,
        config_preparacion: dict[str, Any] | None = None,
        candidatas: list[dict[str, Any]] | None = None,
        id_corrida: str | None = None,
        fecha_inicio: str | None = None,
    ) -> None:
        self.id_corrida = id_corrida or generar_id("corridas")
        if not self.id_corrida:
            raise ValueError("id_corrida vacio")
        # La corrida puede fijar la marca de inicio (INICIO la registra en
        # `corridas` antes del bloqueo); sin ella se genera aquí.
        self.fecha_inicio: str = fecha_inicio or ahora()
        self.config_preparacion: dict[str, Any] = (
            config_preparacion if config_preparacion is not None else {}
        )
        self.candidatas: list[dict[str, Any]] = (
            candidatas if candidatas is not None else []
        )
        self.hubo_candidatas: bool = len(self.candidatas) > 0
        self.contador_preparadas: int = 0
        self.contador_duplicadas: int = 0
        self.contador_errores: int = 0
        self.bloqueo_adquirido: bool = False
        # Slot de terminación controlada: la decisión de candidatas fija
        # `sin_pendientes`; "Finalizar Proceso" lo consume y registra.
        self.motivo_cierre: str | None = None
        self.motivo_marca_temporal: str | None = None
        # Recursos de la fase de preparación (nodo "Preparación de ofertas",
        # ficha M2): sesión httpx de invitado creada con pereza y su contador
        # de vida, catálogo de ubicaciones (leído una vez por corrida) y las
        # cachés de corrida (empresas por nombre normalizado y ubicaciones por
        # texto resuelto a identificador).
        self.sesion_http: Any = None
        self.ofertas_en_sesion: int = 0
        self.cache_empresas: dict[str, str] = {}
        self.catalogo_ubicaciones: CatalogoUbicaciones | None = None
        self.cache_ubicaciones: dict[str, str] = {}
        self.cache_creadas: dict[str, str] = {}
        self.cache_ia: dict[str, tuple[str, str, str]] = {}
        # Memoria de puertas caídas de la corrida (D75, espejo de la
        # evaluación/D59): nombre -> motivo. Registro del nodo (log), nunca
        # eventos: los conteos de cierre quedan fieles.
        self.puertas_caidas: dict[str, str] = {}
        # Control del bucle de pasadas (nodo "¿Quedan ofertas en 'descubierta'?",
        # ficha M2): pasadas completadas que ese nodo contabiliza al evaluar
        # `pasadas_actuales < max_pasadas`; 0 hasta la primera evaluación.
        self.pasadas: int = 0
