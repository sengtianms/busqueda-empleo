from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class OfferState(str, Enum):
    DESCUBIERTA = "descubierta"
    PREPARADA = "preparada"
    DUPLICADA = "duplicada"
    EVALUADA = "evaluada"
    ACEPTADA_EI = "aceptada_ei"
    DESCARTADA_EI = "descartada_ei"
    ACEPTADA = "aceptada"
    DESCARTADA = "descartada"
    PROCESADA = "procesada"
    FINALIZADA = "finalizada"


class EvaluationResult(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DecisionEvaluation(str, Enum):
    CONTINUE = "continue"
    DISCARD = "discard"


class Source(BaseModel):
    id: str = ""
    nombre: str
    tipo: str = ""
    enlace_base: str = ""
    fecha_creacion: str = ""
    fecha_ultima_edicion: str = ""


class Company(BaseModel):
    id: str = ""
    nombre: str
    nombre_normalizado: str = ""
    perfil_linkedin: str = ""
    fecha_creacion: str = ""
    fecha_ultima_edicion: str = ""


class Location(BaseModel):
    id: str = ""
    ciudad: str = ""
    region: str = ""
    pais: str = ""
    fecha_creacion: str = ""
    fecha_ultima_edicion: str = ""


class Offer(BaseModel):
    id: str = ""
    fuente_id: str = ""
    empresa_id: str = "N/A"
    ubicacion_id: str = "N/A"
    ubicacion: str = "N/A"
    modalidad: str = "N/A"
    empresa: str = "N/R"
    enlace: str
    titulo: str
    descripcion_original: str
    fecha_publicacion: datetime | None = None
    fecha_descubrimiento: datetime | None = None
    estado: OfferState = OfferState.DESCUBIERTA
    id_duplicidad: str = "N/A"
    resultado_evaluacion_inicial: str = "N/A"
    observaciones: str = "N/A"
    fecha_creacion: str = ""
    fecha_ultima_edicion: str = ""
    id_corrida: str | None = None
    id_sesion: str | None = None
    indice_set: int | None = None
    id_externo: str | None = None


class GrupoCodigo(str, Enum):
    GRUPO_A = "grupo_a"
    GRUPO_B = "grupo_b"


class TipoEvento(str, Enum):
    ERROR = "error"
    SUCESO = "suceso"


class EstadoCorrida(str, Enum):
    EN_EJECUCION = "en_ejecucion"
    COMPLETADA = "completada"
    SIN_FUENTES = "sin_fuentes"
    SIN_PENDIENTES = "sin_pendientes"
    ABORTADA = "abortada"


class Corrida(BaseModel):
    """Run row model; validates both INICIO registration and the Finalizar
    Proceso closure update (run vocabulary per decision D4). Module 2 adds
    the preparation metrics `total_preparadas`/`total_duplicadas` (D33);
    Module 3 previo (D48) adds `total_aprobadas`/`total_descartadas`."""

    model_config = ConfigDict(extra="forbid")

    id_corrida: str
    fecha_inicio: datetime | None = None
    estado: EstadoCorrida = EstadoCorrida.EN_EJECUCION
    fecha_fin: datetime | None = None
    motivo_terminacion: str = ""
    total_ofertas: int = 0
    total_sucesos: int = 0
    total_errores: int = 0
    fuentes_procesadas: int = 0
    total_preparadas: int = 0
    total_duplicadas: int = 0
    total_aprobadas: int = 0
    total_descartadas: int = 0


class EventoAlmacen(BaseModel):
    evento_id: str = ""
    id_corrida: str
    fuente_id: str = "N/A"
    id_sesion: str | None = None
    indice_set: int | None = None
    marca_temporal: datetime | None = None
    tipo: TipoEvento
    codigo: str
    evidencia: str = "N/A"
    id_oferta: str = "N/A"


class AuditoriaSesion(BaseModel):
    id_sesion: str
    id_corrida: str
    fuente_id: str
    indice_set: int | None = None
    marca_temporal: datetime | None = None
    total_declarado: int | None = None
    conteo: int = 0
    estado: str = ""


class PoliticasCaptura(BaseModel):
    max_paginas: int = 5
    max_ofertas_por_corrida: int = 25
    pausa_entre_lotes_segundos: int = 10
    tope_espera_paginas_sucesivas_segundos: int = 10
    estrategia_anti_bloqueo: str = "pausa_aleatoria"


class FichaFuente(BaseModel):
    fuente_id: str
    nombre: str
    enlace: str = ""
    tipo_acceso: str = ""
    credenciales_referencia: list[str] = Field(default_factory=list)
    criterio_exito: str = ""
    timeout_segundos: int = 30


class SetFiltros(BaseModel):
    fuente_id: str
    indice: int
    filtros: list[dict[str, str | list[str]]] = Field(default_factory=list)


class EntryResult(BaseModel):
    estado: str = ""
    codigo_motivo: str = ""
    evidencia_acotada: str = ""
    numero_de_intentos: int = 0


class SearchResult(BaseModel):
    estado: str = ""
    codigo_motivo: str = ""
    evidencia_acotada: str = ""
    ofertas_primera_pagina: list[Offer] = Field(default_factory=list)
    estado_paginacion: str = ""
    total_declarado: int | None = None
    indice_set: int | None = None
    numero_de_intentos: int = 0


class CaptureBatch(BaseModel):
    ofertas: list[Offer] = Field(default_factory=list)
    id_corrida: str = ""
    fuente_id: str = ""
    id_sesion: str | None = None
    indice_set: int | None = None
    paginas_consumidas: int = 0


class EstadoCaptura(BaseModel):
    estado: str = ""
    codigo_motivo: str = ""
    paginas_consumidas: int = 0
    capturadas_acumuladas_fuente: int = 0
    limite_alcanzado: bool = False


class ProcessedOffer(BaseModel):
    id: str = ""
    id_oferta: str = ""
    titulo_limpio: str = ""
    descripcion_limpia: str = ""
    salario_min: float | None = None
    salario_max: float | None = None
    moneda: str = ""
    ubicacion_limpia: str = ""
    modalidad: str = ""
    requisitos: list[str] = Field(default_factory=list)
    tecnologias: list[str] = Field(default_factory=list)
    idiomas: list[str] = Field(default_factory=list)
    anos_experiencia: int | None = None
    fecha_procesamiento: datetime | None = None
    fecha_creacion: str = ""
    fecha_ultima_edicion: str = ""


class Evaluation(BaseModel):
    id: str = ""
    id_oferta_procesada: str = ""
    resultado: EvaluationResult
    score: float
    umbral_aprobacion: float = 50.0
    decision: DecisionEvaluation
    justificacion: str
    criterios_evaluados: str = ""
    fecha_evaluacion: datetime | None = None
    version_modelo: str = "v1"
    fecha_creacion: str = ""
    fecha_ultima_edicion: str = ""


class EvaluacionDetallada(BaseModel):
    id: str = ""
    id_oferta_procesada: str = ""
    resultado_organizacional: str = ""
    problema_organizacional: str = ""
    perfil_profesional_requerido: str = ""
    coincidencias_perfil: str = ""
    logica_xyz: str = ""
    hipotesis_valor: str = ""
    informacion_descartada: str = ""
    ajuste_tecnico: float = 0.0
    justificacion_ajuste_tecnico: str = ""
    ajuste_funcional: float = 0.0
    justificacion_ajuste_funcional: str = ""
    ajuste_estrategico: float = 0.0
    justificacion_ajuste_estrategico: str = ""
    riesgo_sobrecalificacion: str = ""
    justificacion_riesgo: str = ""
    recomendacion_final: str = ""
    justificacion_recomendacion: str = ""
    insumos_carta_presentacion: str = ""
    fecha_evaluacion: datetime | None = None
    version_metodologia: str = "v1"
    fecha_creacion: str = ""
    fecha_ultima_edicion: str = ""


class Profile(BaseModel):
    id: str = ""
    tecnologias: dict[str, int] = Field(default_factory=dict)
    anos_experiencia: int = 0
    idiomas: dict[str, str] = Field(default_factory=dict)
    ubicaciones_preferidas: list[str] = Field(default_factory=list)
    modalidades_preferidas: list[str] = Field(default_factory=list)
    salario_minimo: float | None = None
    seniority: str = ""
    empresas_objetivo: list[str] = Field(default_factory=list)
    empresas_excluidas: list[str] = Field(default_factory=list)
    educacion_nivel: str = ""
