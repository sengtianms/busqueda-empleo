"""Persistence layer facade (D42): same public API, cohesive internals."""

from ._conexion import (
    _DB_PATH as _DB_PATH,
)
from ._conexion import (  # noqa: F401
    JSON_COLUMNS as JSON_COLUMNS,
)
from ._conexion import (
    _connection as _connection,
)
from ._conexion import (
    _db_path as _db_path,
)
from ._conexion import (
    _deserialize as _deserialize,
)
from ._conexion import (
    _serialize as _serialize,
)
from ._conexion import (
    change_path as change_path,
)
from ._conexion import (
    reset_path as reset_path,
)
from ._consultas import (  # noqa: F401
    buscar_por_id as buscar_por_id,
)
from ._consultas import (
    consultar_bloqueo as consultar_bloqueo,
)
from ._consultas import (
    contar_distintos as contar_distintos,
)
from ._consultas import (
    contar_filas as contar_filas,
)
from ._consultas import (
    leer_candidatas_descubiertas as leer_candidatas_descubiertas,
)
from ._consultas import (
    leer_candidatas_preparadas as leer_candidatas_preparadas,
)
from ._consultas import (
    leer_tabla as leer_tabla,
)
from ._consultas import (
    leer_ultima_corrida_cerrada as leer_ultima_corrida_cerrada,
)
from ._escrituras import (  # noqa: F401
    _generar_id_en as _generar_id_en,
)
from ._escrituras import (
    _upsert_ofertas_en as _upsert_ofertas_en,
)
from ._escrituras import (
    actualizar_corrida as actualizar_corrida,
)
from ._escrituras import (
    actualizar_fila as actualizar_fila,
)
from ._escrituras import (
    adquirir_bloqueo as adquirir_bloqueo,
)
from ._escrituras import (
    escribir_evento as escribir_evento,
)
from ._escrituras import (
    escribir_evento_seguro as escribir_evento_seguro,
)
from ._escrituras import (
    escribir_fila as escribir_fila,
)
from ._escrituras import (
    generar_id as generar_id,
)
from ._escrituras import (
    liberar_bloqueo as liberar_bloqueo,
)
from ._escrituras import (
    registrar_corrida as registrar_corrida,
)
from ._escrituras import (
    registrar_evento as registrar_evento,
)
from ._escrituras import (
    sondear_escritura as sondear_escritura,
)
from ._escrituras import (
    umbral_obsolescencia_minutos as umbral_obsolescencia_minutos,
)
from ._escrituras import (
    upsert_lote_ofertas as upsert_lote_ofertas,
)
from ._escrituras import (
    upsert_oferta as upsert_oferta,
)
from ._esquemas import (
    _ADICIONES_EVALUACION as _ADICIONES_EVALUACION,
)
from ._esquemas import (
    _ADICIONES_PREPARACION as _ADICIONES_PREPARACION,
)
from ._esquemas import (
    _COLUMNAS_ENRIQUECIMIENTO_RETIRADAS_D40 as _COLUMNAS_ENRIQUECIMIENTO_RETIRADAS_D40,
)
from ._esquemas import (
    _COLUMNAS_FINALIZACION_CORRIDAS as _COLUMNAS_FINALIZACION_CORRIDAS,
)
from ._esquemas import (
    _INDICES as _INDICES,
)
from ._esquemas import (
    _TABLAS_ESQUEMA as _TABLAS_ESQUEMA,
)
from ._esquemas import (  # noqa: F401
    ESQUEMAS as ESQUEMAS,
)
from ._esquemas import (
    MAPA_COLUMNAS_ESPANOL as MAPA_COLUMNAS_ESPANOL,
)
from ._esquemas import (
    PREFIXES as PREFIXES,
)
from ._migraciones import (  # noqa: F401
    _migrar_espanol_total as _migrar_espanol_total,
)
from ._migraciones import (
    _migrate_corridas_finalizacion as _migrate_corridas_finalizacion,
)
from ._migraciones import (
    _migrate_evaluacion_d48 as _migrate_evaluacion_d48,
)
from ._migraciones import (
    _migrate_limpieza_d31 as _migrate_limpieza_d31,
)
from ._migraciones import (
    _migrate_normalizacion_nombres_d41 as _migrate_normalizacion_nombres_d41,
)
from ._migraciones import (
    _migrate_ofertas as _migrate_ofertas,
)
from ._migraciones import (
    _migrate_ofertas_descubiertas as _migrate_ofertas_descubiertas,
)
from ._migraciones import (
    _migrate_ofertas_empresa_nombre as _migrate_ofertas_empresa_nombre,
)
from ._migraciones import (
    _migrate_preparacion_d33 as _migrate_preparacion_d33,
)
from ._migraciones import (
    _migrate_revertir_enriquecimiento_d40 as _migrate_revertir_enriquecimiento_d40,
)
from ._migraciones import (
    _migrate_sesiones_id as _migrate_sesiones_id,
)
from ._migraciones import (
    _migrate_ubicacion_rename as _migrate_ubicacion_rename,
)
from ._migraciones import (
    inicializar_si_ausente as inicializar_si_ausente,
)
from ._migraciones import (
    init_db as init_db,
)
