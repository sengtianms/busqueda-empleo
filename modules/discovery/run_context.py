"""Execution context of a discovery run (nodo INICIO, DOC-04 Section 15).

RunContext is the single object passed between the twelve nodes of the
official Discovery flow. It holds the validated configuration, the filtered
source list, the iterators (sources and filter sets), the run lock reference
and the result slots of each node. It is created by the INICIO node and does
not contain any node logic: nodes only read and update its fields.
"""

from typing import Any

from shared.config import load
from shared.errors import ConfigurationError
from shared.models import (
    CaptureBatch,
    EntryResult,
    EstadoCaptura,
    FichaFuente,
    PoliticasCaptura,
    SearchResult,
    SetFiltros,
)
from shared.persistence import generar_id
from shared.utilidades import TIPOS_ACCESO, ahora


def _entero_positivo(valor: Any, defecto: int) -> int:
    """Normaliza un entero >= 1 de configuración; defecto si no es usable."""
    try:
        resultado = int(valor)
    except (TypeError, ValueError):
        return defecto
    return resultado if resultado >= 1 else defecto


class RunContext:
    """Carries all the state a single discovery run needs across its nodes."""

    def __init__(
        self,
        config_fuentes: list[dict[str, Any]],
        config_captura: dict[str, Any] | None = None,
        id_corrida: str | None = None,
        permitir_vacio: bool = False,
        config_descubrimiento: dict[str, Any] | None = None,
    ) -> None:
        if not config_fuentes and not permitir_vacio:
            raise ConfigurationError(
                "12", "No sources defined in configuration.", source_module="run_context"
            )
        if config_captura is None:
            config_captura = load().get("captura", {})
        self.id_corrida = id_corrida or generar_id("corridas")
        self.fecha_inicio: str = ahora()
        self.fuentes_filtradas: list[FichaFuente] = []
        self._sets_validos: dict[str, list[SetFiltros]] = {}
        self._politicas_por_fuente: dict[str, PoliticasCaptura] = {}
        for conf in config_fuentes:
            ficha = self._construir_ficha(conf, config_captura)
            self.fuentes_filtradas.append(ficha)
        self.iterador_fuentes = -1
        self.iterador_sets: dict[str, int] = {
            f.fuente_id: -1 for f in self.fuentes_filtradas
        }
        self.bloqueo_adquirido = False
        self.id_sesion: str | None = None
        self.handle_sesion: Any | None = None
        self.browser: Any | None = None
        self.playwright_instance: Any | None = None
        self.fuente_corriente: FichaFuente | None = None
        self.entry_result: EntryResult | None = None
        self.search_result: SearchResult | None = None
        self.capture_batch: CaptureBatch | None = None
        self.estado_captura: EstadoCaptura | None = None
        self.set_corriente: SetFiltros | None = None
        self._ultimo_fuente_id_sets: str | None = None
        # Resiliencia del navegador (D61): renovación por tramos y límite
        # honesto de muertes consecutivas sin avance (entorno roto).
        descubrimiento = config_descubrimiento if config_descubrimiento else {}
        self.renovar_navegador_tras_paginas: int = _entero_positivo(
            descubrimiento.get("renovar_navegador_tras_paginas"), 30
        )
        self.tope_muertes_sin_avance: int = _entero_positivo(
            descubrimiento.get("tope_muertes_sin_avance"), 3
        )
        self.paginas_desde_renovacion: int = 0
        self.muertes_sin_avance: int = 0
        self.navegador_insostenible: bool = False

    def _construir_ficha(
        self, conf: dict[str, Any], config_captura: dict[str, Any]
    ) -> FichaFuente:
        if not isinstance(conf, dict):
            raise ConfigurationError(
                "12", "Malformed source entry (not a mapping).", source_module="run_context"
            )
        ficha_raw = conf.get("ficha_acceso")
        if not isinstance(ficha_raw, dict):
            raise ConfigurationError(
                "12",
                "Source without ficha_acceso (ERR-12, INICIO RN-08).",
                source_module="run_context",
            )
        try:
            ficha = FichaFuente(
                fuente_id=str(conf.get("fuente_id", "")),
                nombre=str(conf.get("nombre", "")),
                enlace=str(ficha_raw.get("enlace", "")),
                tipo_acceso=str(ficha_raw.get("tipo_acceso", "")),
                credenciales_referencia=[
                    str(c) for c in ficha_raw.get("credenciales_referencia", [])
                ],
                criterio_exito=str(ficha_raw.get("criterio_exito", "")),
                timeout_segundos=int(ficha_raw.get("timeout_segundos", 30)),
            )
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                "12",
                f"Invalid access sheet fields ({exc}).",
                source_module="run_context",
            ) from exc
        if not ficha.fuente_id or not ficha.nombre or not ficha.enlace:
            raise ConfigurationError(
                "12",
                "Incomplete access sheet (ERR-12): "
                "fuente_id, nombre and enlace are mandatory.",
                source_module="run_context",
            )
        if not ficha.criterio_exito:
            raise ConfigurationError(
                "12",
                "Incomplete access sheet (ERR-12): criterio_exito is mandatory.",
                source_module="run_context",
            )
        if ficha.tipo_acceso not in TIPOS_ACCESO:
            raise ConfigurationError(
                "12",
                f"Invalid tipo_acceso '{ficha.tipo_acceso}'",
                source_module="run_context",
            )
        if ficha.tipo_acceso == "con_autenticacion" and not ficha.credenciales_referencia:
            raise ConfigurationError(
                "12",
                "Authenticated source without credential references.",
                source_module="run_context",
            )
        sets = self._construir_sets(conf, ficha.fuente_id)
        self._sets_validos[ficha.fuente_id] = sets
        self._politicas_por_fuente[ficha.fuente_id] = self._construir_politicas(
            conf, config_captura
        )
        return ficha

    def _construir_sets(
        self, conf: dict[str, Any], fuente_id: str
    ) -> list[SetFiltros]:
        sets_raw = conf.get("sets_de_filtros")
        if not isinstance(sets_raw, list) or not sets_raw:
            return [SetFiltros(fuente_id=fuente_id, indice=0, filtros=[])]
        sets: list[SetFiltros] = []
        for item in sets_raw:
            if not isinstance(item, dict):
                continue
            indice = item.get("indice_set")
            filtros = item.get("filtros", [])
            if not isinstance(indice, int) or not isinstance(filtros, list):
                continue
            if any(f.fuente_id == fuente_id and f.indice == indice for f in sets):
                continue
            sets.append(
                SetFiltros(
                    fuente_id=fuente_id,
                    indice=indice,
                    filtros=[f for f in filtros if isinstance(f, dict)],
                )
            )
        sets.sort(key=lambda s: s.indice)
        return sets

    def _construir_politicas(
        self, conf: dict[str, Any], config_captura: dict[str, Any]
    ) -> PoliticasCaptura:
        politicas_raw = conf.get("politicas_de_captura")
        por_fuente = politicas_raw if isinstance(politicas_raw, dict) else {}
        combinadas = {**config_captura, **por_fuente}
        return PoliticasCaptura(
            max_paginas=int(combinadas.get("max_paginas", 5)),
            max_ofertas_por_corrida=int(
                combinadas.get("max_ofertas_por_corrida", 25)
            ),
            pausa_entre_lotes_segundos=int(
                combinadas.get("pausa_entre_lotes_segundos", 10)
            ),
            tope_espera_paginas_sucesivas_segundos=int(
                combinadas.get("tope_espera_paginas_sucesivas_segundos", 10)
            ),
            estrategia_anti_bloqueo=str(
                combinadas.get("estrategia_anti_bloqueo", "pausa_aleatoria")
            ),
        )

    def set_filtros(self, fuente: FichaFuente, indice: int = 0) -> SetFiltros | None:
        sets = self._sets_validos.get(fuente.fuente_id)
        if not sets:
            return None
        for s in sets:
            if s.indice == indice:
                return s
        return None

    def sets_validos(self, fuente: FichaFuente) -> list[SetFiltros]:
        return self._sets_validos.get(fuente.fuente_id, [])

    def politicas(self, fuente: FichaFuente) -> PoliticasCaptura:
        return self._politicas_por_fuente.get(
            fuente.fuente_id, PoliticasCaptura()
        )

    def reset_iteradores(self) -> None:
        self.iterador_fuentes = -1
        self.iterador_sets = {f.fuente_id: -1 for f in self.fuentes_filtradas}
        self.bloqueo_adquirido = False
        self.id_sesion = None
        self.handle_sesion = None
        self.browser = None
        self.playwright_instance = None
        self.fuente_corriente = None
        self.entry_result = None
        self.search_result = None
        self.capture_batch = None
        self.estado_captura = None
        self.set_corriente = None
        self._ultimo_fuente_id_sets = None
        self.paginas_desde_renovacion = 0
        self.muertes_sin_avance = 0
        self.navegador_insostenible = False

    def marcar_cambio_de_fuente(self, fuente_id: str) -> None:
        """Resets the per-source set iterator when the flow switches sources:
        previous results no longer belong to the current run segment. No-op
        while iterating the same source (keeps set progression intact)."""
        if self._ultimo_fuente_id_sets != fuente_id:
            self.search_result = None
            self.iterador_sets[fuente_id] = -1
            self._ultimo_fuente_id_sets = fuente_id

    def seleccionar_siguiente_set(self, fuente_id: str) -> int:
        if fuente_id not in self.iterador_sets:
            raise ValueError(f"Unknown source in context: {fuente_id}")
        self.iterador_sets[fuente_id] += 1
        return self.iterador_sets[fuente_id]
