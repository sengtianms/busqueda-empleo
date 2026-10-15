"""Internal: DDL schemas, indexes and legacy rename mappings."""






PREFIXES: dict[str, str] = {
    "empresas": "EMP",
    "ubicaciones": "UBI",
    "ofertas_descubiertas": "OFE",
    "corridas": "COR",
    "sesiones": "SES",
    "eventos": "EVT",
    "bloqueo": "BLO",
}


ESQUEMAS: dict[str, str] = {
    "secuencia_ids": (
        "CREATE TABLE IF NOT EXISTS secuencia_ids ("
        "tabla_nombre TEXT PRIMARY KEY,"
        "prefijo TEXT NOT NULL,"
        "ultimo_numero INTEGER NOT NULL DEFAULT 0"
        ")"
    ),
    "empresas": (
        "CREATE TABLE IF NOT EXISTS empresas ("
        "id TEXT PRIMARY KEY,"
        "nombre TEXT NOT NULL,"
        "nombre_normalizado TEXT DEFAULT '',"
        "perfil_linkedin TEXT DEFAULT '',"
        "fecha_creacion TEXT DEFAULT '',"
        "fecha_ultima_edicion TEXT DEFAULT ''"
        ")"
    ),
    "ubicaciones": (
        "CREATE TABLE IF NOT EXISTS ubicaciones ("
        "id TEXT PRIMARY KEY,"
        "ciudad TEXT DEFAULT 'N/A',"
        "region TEXT DEFAULT 'N/A',"
        "pais TEXT DEFAULT 'N/A',"
        "fecha_creacion TEXT DEFAULT '',"
        "fecha_ultima_edicion TEXT DEFAULT ''"
        ")"
    ),
    "ofertas_descubiertas": (
        "CREATE TABLE IF NOT EXISTS ofertas_descubiertas ("
        "id TEXT PRIMARY KEY,"
        "enlace TEXT NOT NULL,"
        "titulo TEXT DEFAULT '',"
        "descripcion_original TEXT DEFAULT 'N/A',"
        "fecha_publicacion TEXT DEFAULT 'N/A',"
        "fecha_descubrimiento TEXT DEFAULT '',"
        "estado TEXT DEFAULT 'descubierta' "
        "CHECK(estado IN ('descubierta','preparada','duplicada','evaluada',"
        "'aceptada_ei','descartada_ei',"
        "'aceptada','descartada','procesada','finalizada')),"
        "observaciones TEXT DEFAULT 'N/A',"
        "fecha_creacion TEXT DEFAULT '',"
        "fecha_ultima_edicion TEXT DEFAULT '',"
        "fuente_id TEXT DEFAULT '',"
        "empresa_id TEXT DEFAULT 'N/A',"
        "ubicacion_id TEXT DEFAULT 'N/A',"
        "id_corrida TEXT DEFAULT '',"
        "id_sesion TEXT DEFAULT '',"
        "indice_set INTEGER DEFAULT '',"
        "id_externo TEXT DEFAULT '',"
        "fecha_ultima_verificacion TEXT DEFAULT '',"
        "id_duplicidad TEXT DEFAULT 'N/A',"
        "ubicacion TEXT DEFAULT 'N/A',"
        "modalidad TEXT DEFAULT 'N/A',"
        "empresa TEXT DEFAULT 'N/R',"
        "resultado_evaluacion_inicial TEXT DEFAULT 'N/A'"
        ")"
    ),
    "corridas": (
        "CREATE TABLE IF NOT EXISTS corridas ("
        "id_corrida TEXT PRIMARY KEY,"
        "fecha_inicio TEXT NOT NULL,"
        "estado TEXT NOT NULL,"
        "fecha_fin TEXT DEFAULT '',"
        "motivo_terminacion TEXT DEFAULT '',"
        "total_ofertas INTEGER DEFAULT 0,"
        "total_errores INTEGER DEFAULT 0,"
        "total_sucesos INTEGER DEFAULT 0,"
        "fuentes_procesadas INTEGER DEFAULT 0,"
        "total_preparadas INTEGER DEFAULT 0,"
        "total_duplicadas INTEGER DEFAULT 0,"
        "total_aprobadas INTEGER DEFAULT 0,"
        "total_descartadas INTEGER DEFAULT 0"
        ")"
    ),
    "eventos": (
        "CREATE TABLE IF NOT EXISTS eventos ("
        "evento_id TEXT PRIMARY KEY,"
        "id_corrida TEXT NOT NULL,"
        "fuente_id TEXT DEFAULT 'N/A',"
        "id_sesion TEXT DEFAULT 'N/A',"
        "indice_set INTEGER DEFAULT 'N/A',"
        "marca_temporal TEXT NOT NULL,"
        "tipo TEXT NOT NULL CHECK(tipo IN ('error','suceso')),"
        "codigo TEXT NOT NULL,"
        "evidencia TEXT DEFAULT 'N/A',"
        "id_oferta TEXT DEFAULT 'N/A'"
        ")"
    ),
    "sesiones": (
        "CREATE TABLE IF NOT EXISTS sesiones ("
        "id TEXT PRIMARY KEY,"
        "id_sesion TEXT NOT NULL,"
        "id_corrida TEXT NOT NULL,"
        "fuente_id TEXT NOT NULL,"
        "indice_set INTEGER DEFAULT '',"
        "marca_temporal TEXT NOT NULL,"
        "total_declarado INTEGER DEFAULT '',"
        "conteo INTEGER DEFAULT '',"
        "estado TEXT NOT NULL,"
        "fecha_creacion TEXT DEFAULT '',"
        "fecha_ultima_edicion TEXT DEFAULT ''"
        ")"
    ),
    "bloqueo": (
        "CREATE TABLE IF NOT EXISTS bloqueo ("
        "id_corrida TEXT PRIMARY KEY,"
        "marca_temporal TEXT NOT NULL"
        ")"
    ),
}


_INDICES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_ofertas_id_externo "
    "ON ofertas_descubiertas(id_externo)",
    "CREATE INDEX IF NOT EXISTS idx_ofertas_id_corrida "
    "ON ofertas_descubiertas(id_corrida)",
    "CREATE INDEX IF NOT EXISTS idx_eventos_id_corrida ON eventos(id_corrida)",
)



MAPA_COLUMNAS_ESPANOL: dict[str, dict[str, str]] = {
    "empresas": {
        "normalized_name": "nombre_normalizado",
        "linkedin": "perfil_linkedin",
        "creation_date": "fecha_creacion",
        "last_edit_date": "fecha_ultima_edicion",
    },
    "ubicaciones": {
        "creation_date": "fecha_creacion",
        "last_edit_date": "fecha_ultima_edicion",
    },
    "ofertas_descubiertas": {
        "url": "enlace",
        "discovery_date": "fecha_descubrimiento",
        "creation_date": "fecha_creacion",
        "last_edit_date": "fecha_ultima_edicion",
        "run_id": "id_corrida",
        "session_id": "id_sesion",
        "set_indice": "indice_set",
        "id_externo_url": "id_externo",
        "timestamp_ultima_verificacion": "fecha_ultima_verificacion",
    },
    "corridas": {
        "run_id": "id_corrida",
        "timestamp_inicio": "fecha_inicio",
        "timestamp_fin": "fecha_fin",
    },
    "eventos": {
        "run_id": "id_corrida",
        "source_id": "fuente_id",
        "session_id": "id_sesion",
        "set_indice": "indice_set",
        "timestamp": "marca_temporal",
    },
    "sesiones": {
        "session_id": "id_sesion",
        "run_id": "id_corrida",
        "source_id": "fuente_id",
        "set_indice": "indice_set",
        "timestamp": "marca_temporal",
        "creation_date": "fecha_creacion",
        "last_edit_date": "fecha_ultima_edicion",
    },
    "bloqueo": {
        "run_id": "id_corrida",
        "timestamp": "marca_temporal",
    },
}


_TABLAS_ESQUEMA: tuple[str, ...] = (
    "empresas", "ubicaciones", "ofertas_descubiertas",
    "corridas", "eventos", "sesiones", "bloqueo",
)



_ADICIONES_PREPARACION: tuple[tuple[str, str], ...] = (
    ("ofertas_descubiertas", "id_duplicidad TEXT DEFAULT 'N/A'"),
    ("ofertas_descubiertas", "modalidad TEXT DEFAULT 'N/A'"),
    ("ofertas_descubiertas", "empresa TEXT DEFAULT 'N/R'"),
    ("corridas", "total_preparadas INTEGER DEFAULT 0"),
    ("corridas", "total_duplicadas INTEGER DEFAULT 0"),
    ("eventos", "id_oferta TEXT DEFAULT 'N/A'"),
)


_ADICIONES_EVALUACION: tuple[tuple[str, str], ...] = (
    ("ofertas_descubiertas", "resultado_evaluacion_inicial TEXT DEFAULT 'N/A'"),
    ("corridas", "total_aprobadas INTEGER DEFAULT 0"),
    ("corridas", "total_descartadas INTEGER DEFAULT 0"),
)



_COLUMNAS_ENRIQUECIMIENTO_RETIRADAS_D40: tuple[str, ...] = (
    "sitio_web",
    "sector",
    "tamano",
    "descripcion",
    "sede",
    "tipo",
    "fundacion",
    "especialidades",
)



_COLUMNAS_FINALIZACION_CORRIDAS: tuple[str, ...] = (
    "fecha_fin TEXT DEFAULT ''",
    "motivo_terminacion TEXT DEFAULT ''",
    "total_ofertas INTEGER DEFAULT 0",
    "total_errores INTEGER DEFAULT 0",
    "total_sucesos INTEGER DEFAULT 0",
    "fuentes_procesadas INTEGER DEFAULT 0",
)
