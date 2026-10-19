# Tablas de la base de datos — `job_search.db`

Reporte as-built de la base de datos SQLite del proyecto (ruta: `data/job_search.db`). Para cada tabla se documenta el propósito, sus columnas, qué hace cada una y en qué momento del flujo se diligencia (quién la escribe y desde qué nodo o función).

Fuente de verdad: `shared/persistence.py` (esquemas y funciones de escritura) y los nodos del módulo de descubrimiento (`modules/discovery/`).

## 1. Resumen

La BD tiene 8 tablas. Se habilita con `init_db()` (crea tablas y aplica migraciones idempotentes, incluida la migración al catálogo español D7/D8, la limpieza D31 y la creación de índices, decisión D16). Fechas en formato `YYYY-MM-DD HH:MM:SS` (hora local). IDs secuenciales con prefijo por tabla (`EMP`, `UBI`, `OFE`, `COR`, `SES`, `EVT`, `BLO`) generados por `generar_id()`.

**Regla de gestión de datos (decisión D31, 2026-08-18):** ningún campo persistido puede quedar vacío (`''`/NULL); cuando un valor no aplica o no está disponible se guarda `N/A` (o `N/R`). La normalización ocurre en la frontera de persistencia (`escribir_evento()`, `_upsert_ofertas_en()`) y las columnas afectadas declaran `DEFAULT 'N/A'`. Exenciones: `id_externo` (colisionaría en la deduplicación) y `fecha_ultima_verificacion` (por instrucción explícita del usuario; vacía hasta que una re-visita la refresca). Las consultas de conteo tratan `N/A` como vacío (`contar_distintos` excluye NULL, `''` y `'N/A'`).

Índices (creados con `CREATE INDEX IF NOT EXISTS`, no únicos — la unicidad estricta es del Módulo 2, decisión D4): `idx_ofertas_id_externo` (deduplicación por oferta), `idx_ofertas_id_corrida` y `idx_eventos_id_corrida` (métricas de cierre y auditoría).

Estado actual (conteos tras la vuelta completa del 2026-10-15 sobre la base limpiada del barrido de pruebas; última migración con `init_db`/`_migrate_evaluacion_d48`, D49):

| Tabla | Filas | Escritor principal |
|---|---|---|
| `secuencia_ids` | 6 | Automática (generador de IDs) |
| `empresas` | 49 | Módulo 2 — Nodo 2 (upsert por `nombre_normalizado`; catálogo mínimo de identidad tras D40) |
| `ubicaciones` | 5 | Módulo 2 — Nodo 2 (upsert por tupla `(ciudad, region, pais)` normalizada; "Remoto" no crea fila) |
| `ofertas_descubiertas` | 65 | Módulo 1 — Nodo Captura → `upsert_oferta()` (incluye `empresa`, `ubicacion` y `modalidad` crudas de la tarjeta, D41/traspaso D45); Módulo 2 — Nodo 2 (sobrescribe `titulo`/`descripcion_original`/`empresa_id`/`ubicacion_id`); Módulo 2 — Nodo 3 (escribe `estado`, `id_duplicidad`, `fecha_ultima_verificacion`, `observaciones`); Módulo 3 — Nodo Evaluación inicial (escribe `estado` y `resultado_evaluacion_inicial`; verificado en vueltas reales: COR-0004 solo 42 `aceptada_ei` + 27 `descartada_ei` antes del barrido, D49; vuelta completa posterior 14 `aceptada_ei` + 47 `descartada_ei`, mismo COR-0004 por reinicio de contadores) |
| `corridas` | 4 | Módulo 1/2/3 — Nodo INICIO → `registrar_corrida()`; Nodo Finalizar → `actualizar_corrida()`; Orquestador transversal → `registrar_corrida()` para la corrida programada |
| `eventos` | 142 | Nodos del flujo → `escribir_evento()` (incluye los eventos del Módulo 2 — `oferta_preparada`/`preparacion_fallida`/`oferta_duplicada`/`revision_pendientes` —, del Módulo 3 — `oferta_aprobada`/`oferta_descartada`/`evaluacion_fallida` — y del orquestador — `modulo_ejecutado`/`corrida_programada`/`modulo_fallido`) |
| `sesiones` | 1 | Módulo 1 — Nodo Captura → `escribir_fila("sesiones")` |
| `bloqueo` | 0 | Módulo 1/2/3 — Nodo INICIO → `adquirir_bloqueo()` (global del pipeline); Nodo Finalizar → `liberar_bloqueo()` |

### Momentos del flujo que diligencian las tablas

1. **INICIO**: prueba de escritura (`sondear_escritura()`, insert+rollback en `bloqueo`), adquisición del bloqueo (`adquirir_bloqueo()` → `bloqueo`) y registro de la corrida (`registrar_corrida()` → `corridas` con estado `en_ejecucion`). Ante fallos escribe eventos de error (`eventos`).
2. **Control de fuentes / Ingreso / Búsqueda**: no escriben en BD; en caso de aborto o error crítico registran eventos de error (`eventos`).
3. **Registro**: registra el resultado del registro de la fuente como evento de éxito o fallo (`eventos`).
4. **Captura**: audita cada lote capturado escribiendo la sesión de plataforma (`sesiones`) y registra las ofertas (`upsert_oferta()` → `ofertas_descubiertas`); emite eventos de éxito/registro parcial (`eventos`).
5. **Finalizar**: cierra la corrida con estado final y métricas (`actualizar_corrida()` → `corridas`), escribe el evento de terminación (`eventos`) y libera el bloqueo (`liberar_bloqueo()` → `bloqueo`).

## 2. Detalle por tabla

### 2.1. `secuencia_ids`

Control interno del generador de IDs secuenciales (`PREFIJO-NNNN`). No se escribe manualmente: `generar_id()` la inserta (`ultimo_numero = 1`) o incrementa (`ultimo_numero + 1`) al crear cualquier ID de otra tabla.

| Columna | Tipo | Qué hace | Cuándo se diligencia |
|---|---|---|---|
| `tabla_nombre` | TEXT (PK) | Nombre de la tabla para la que se lleva la secuencia | En el primer `generar_id()` de esa tabla (automático) |
| `prefijo` | TEXT NOT NULL | Prefijo del ID de esa tabla (`EMP`, `UBI`, `OFE`, `COR`, `SES`, `EVT`, `BLO`) | En el primer `generar_id()` de esa tabla (automático) |
| `ultimo_numero` | INTEGER NOT NULL DEFAULT 0 | Último número asignado (se incrementa en 1 por cada ID) | En cada `generar_id()` (automático) |

> **D31:** la secuencia de `fuentes` fue eliminada junto con la tabla (2026-08-18).

### 2.2. `empresas`

Catálogo de empresas. **El Módulo 1 no escribe en esta tabla** (0 filas): desde D41 extrae de las tarjetas únicamente el texto crudo hacia la columna display `ofertas_descubiertas.empresa`, pero **este catálogo lo puebla solo el Módulo 2** (decisión D33): el Nodo 2 (Preparación de ofertas) hace upsert por `nombre_normalizado` sin IA. La tabla es un catálogo mínimo de identidad: el enriquecimiento de perfiles (D39) fue retirado por la decisión D40 (2026-08-25) tras medirse como cuello de botella (~96% del tiempo de una corrida completa); si algún futuro módulo necesitara atributos de empresa, se obtendrán selectivamente y fuera del camino crítico.

> **D40:** las ocho columnas de enriquecimiento (`sitio_web`, `sector`, `tamano`, `descripcion`, `sede`, `tipo`, `fundacion`, `especialidades`) fueron eliminadas por la migración idempotente `_migrate_revertir_enriquecimiento_d40`; el catálogo conserva solo identidad (`id`, `nombre`, `nombre_normalizado`, `perfil_linkedin`) y trazabilidad (`fecha_creacion`, `fecha_ultima_edicion`).
>
> **D41:** `nombre_normalizado` usa `normalizar_nombre_empresa` — minúsculas y espacios simples, **conservando todos los caracteres** (tildes, ñ, puntuación, símbolos como `&`, `.`, paréntesis). La migración `_migrate_normalizacion_nombres_d41` recalcula las claves existentes desde `nombre`. Las tuplas de ubicación y los títulos de duplicidad siguen con la regla estricta (`normalizar_texto`).

| Columna | Tipo | Qué hace | Cuándo se diligencia |
|---|---|---|---|
| `id` | TEXT (PK) | ID único (prefijo `EMP`) | Módulo 2 — Nodo 2 (`generar_id` al insertar) |
| `nombre` | TEXT NOT NULL | Nombre oficial de la empresa | Módulo 2 — Nodo 2 (desde la página de la oferta); el Módulo 1 no escribe |
| `nombre_normalizado` | TEXT DEFAULT '' | Nombre estandarizado para evitar duplicados (clave del upsert) | Módulo 2 — Nodo 2 (vía `normalizar_nombre_empresa` en `shared/utilidades.py`, D41) |
| `perfil_linkedin` | TEXT DEFAULT '' | URL del perfil de LinkedIn | Módulo 2 — Nodo 2 (capturado de la página de la oferta) |
| `fecha_creacion` | TEXT DEFAULT '' | Fecha/hora de alta del registro | Automática al insertar |
| `fecha_ultima_edicion` | TEXT DEFAULT '' | Fecha/hora de la última actualización | Automática en cada insert/update |

### 2.3. `ubicaciones`

Catálogo de ubicaciones. **El Módulo 1 no escribe en esta tabla** (0 filas): desde D41/D45 extrae el texto crudo de la ubicación de la tarjeta hacia `ofertas_descubiertas.ubicacion`, pero poblar el catálogo sigue siendo del Módulo 2 (D29 eliminó la extracción con vínculo; D33 la asignó al Nodo 2). **El Módulo 2 la puebla** (decisión D33): el Nodo 2 (Preparación de ofertas) hace upsert por **tupla normalizada `(ciudad, region, pais)`** (la IA solo clasifica el texto crudo; el Nodo 2 dirige la BD). **D46:** si no existe igualdad exacta, una variante de nombre con alta similitud (`umbral_alias_ubicacion`, default 90) **reutiliza la fila existente** en lugar de crear otra — misma ciudad, sin duplicados de catálogo. Cada componente guarda `'N/A'` cuando la fuente no lo especificó (p. ej. "Colombia" solo → tupla `(N/A, N/A, Colombia)` con un único ID compartido). **"Remoto" no crea fila**; la oferta queda con `ubicacion_id = 'N/R'` (no requerido). La columna `modalidad` se eliminó de esta tabla (D33); la modalidad vive en `ofertas_descubiertas.modalidad`.

| Columna | Tipo | Qué hace | Cuándo se diligencia |
|---|---|---|---|
| `id` | TEXT (PK) | ID único (prefijo `UBI`) | Módulo 2 — Nodo 2 (`generar_id` al insertar) |
| `ciudad` | TEXT DEFAULT 'N/A' | Ciudad de la vacante (`'N/A'` si la fuente no la especificó — regla D31) | Módulo 2 — Nodo 2 (tras clasificación por IA) |
| `region` | TEXT DEFAULT 'N/A' | Estado, provincia o departamento (`'N/A'` si no aplica o no vino) | Módulo 2 — Nodo 2 (tras clasificación por IA) |
| `pais` | TEXT DEFAULT 'N/A' | País (`'N/A'` si la oferta solo dio ciudad) | Módulo 2 — Nodo 2 (tras clasificación por IA) |
| `fecha_creacion` | TEXT DEFAULT '' | Fecha/hora de alta del registro | Automática al insertar |
| `fecha_ultima_edicion` | TEXT DEFAULT '' | Fecha/hora de la última actualización | Automática en cada insert/update |

### 2.4. `ofertas_descubiertas`

Oportunidades (vacantes) descubiertas. **Módulo 1 — Nodo Captura** la escribe mediante `upsert_oferta()`: si ya existe una fila con el mismo `id_externo` no inserta de nuevo, solo refresca `fecha_ultima_verificacion` y devuelve el `id` existente; si no, genera un ID (`OFE-NNNN`) e inserta la fila. Desde el traspaso aprobado (2026-08-25; D45), la inserción también trae `ubicacion`, `modalidad` y `empresa` extraídas de la tarjeta del listado. **Módulo 2** la actualiza en pasos posteriores: el Nodo 2 (Preparación) sobrescribe `titulo` (best-effort con el `<h1>` de la página), rellena `descripcion_original` desde la página y escribe `empresa_id`/`ubicacion_id` (sin tocar `fecha_ultima_verificacion`, `ubicacion` ni `modalidad`); el Nodo 3 (Verificación de duplicidad) escribe `estado`, `id_duplicidad` y actualiza `fecha_ultima_verificacion` + `observaciones` con la evidencia del duplicado. **Módulo 3 — Nodo Evaluación inicial (construido Fase 6, D49; prompt v5 D52):** escribe `estado` (`aceptada_ei`/`descartada_ei` vía `evaluada` en el mismo movimiento) y `resultado_evaluacion_inicial` con el resultado completo (entregable principal, v1–v5, decisión, justificación); los fallos persistentes dejan la oferta en `preparada` con `'N/A'`. Higiene D49: la IA recibe la descripción sin secciones de ruido (tope alto de seguridad); el original guardado no se toca. Regla D31: los campos sin valor se guardan como `N/A` (nunca `''`/NULL); `fecha_ultima_verificacion` queda exenta (vacía hasta que el Módulo 1 refresca en dedup hits **o** el Módulo 2 Nodo 3 escribe tras verificar). El `id_corrida` de la oferta sigue siendo el del descubrimiento — la trazabilidad de preparación/evaluación vive en `eventos` con su propio `id_corrida` (D33).

> **D41:** nueva columna `empresa` (texto crudo de la tarjeta, escrita por el Módulo 1 junto a `ubicacion`/`modalidad`; `'N/R'` cuando la tarjeta no la trae; filas históricas quedan en `'N/R'`; el alta nunca la sobreescribe). La extracción de `descripcion_original` pasa a respetar la estructura visible del anuncio (párrafos/listas/saltos) para las preparaciones posteriores a D41; y `empresas.nombre_normalizado` usa la regla que conserva todos los caracteres (ver §2.2).

> **D32:** la tabla se llamaba `ofertas` y fue renombrada a `ofertas_descubiertas` (2026-08-19) para distinguirla de las tablas de etapas posteriores (Preparación, Evaluación, Procesamiento). El prefijo `OFE`, la secuencia y los índices conservan su nombre; la migración `_migrate_ofertas_descubiertas` en `init_db()` es idempotente. **D33:** añade `ubicacion_nombre`, `modalidad`, `id_duplicidad` y `duplicada` al CHECK de `estado` (8 valores); `eventos.id_oferta` se re-añade para la trazabilidad por oferta del Módulo 2. **D45:** `ubicacion_nombre` pasa a llamarse `ubicacion` y su captura se traslada al Módulo 1 (tarjeta del listado, junto con `modalidad`).

| Columna | Tipo | Qué hace | Cuándo se diligencia |
|---|---|---|---|
| `id` | TEXT (PK) | ID único de la oferta (prefijo `OFE`) | Automático en la inserción (`upsert_oferta`) |
| `enlace` | TEXT NOT NULL | Enlace original de la oferta | Módulo 1 — Nodo Captura: en la inserción, desde la oferta capturada (obligatorio) |
| `titulo` | TEXT DEFAULT '' | Título original de la oferta | Módulo 1 — Nodo Captura: en la inserción, desde la tarjeta; Módulo 2 — Nodo 2 lo sobrescribe best-effort con el `<h1>` de la página de la oferta si existe (RN-10, D33); nunca deja el campo vacío |
| `descripcion_original` | TEXT DEFAULT 'N/A' | Contenido original obtenido en el descubrimiento (no se sobrescribe tras preparación); `N/A` si no hay descripción (D31) | Módulo 1 — Nodo Captura la deja `N/A` (no captura la página completa); Módulo 2 — Nodo 2 la rellena desde la página de la oferta |
| `fecha_publicacion` | TEXT DEFAULT 'N/A' | Fecha de publicación indicada por la fuente; en el Módulo 1 es timestamp aproximado derivado de "Publicado hace N <unidad>" (±1 h; mes = 30 días) (D28); `N/A` si la tarjeta no muestra fecha relativa (D31) | Módulo 1 — Nodo Captura: en la inserción |
| `fecha_descubrimiento` | TEXT DEFAULT '' | Fecha/hora en que la automatización descubrió la oferta | Módulo 1 — Nodo Captura: en la inserción, con la hora actual (`_now()`) |
| `estado` | TEXT DEFAULT 'descubierta' | Estado en el flujo de procesamiento (10 valores: `descubierta`, `preparada`, `duplicada`, `evaluada`, `aceptada_ei`, `descartada_ei`, `aceptada`, `descartada`, `procesada`, `finalizada` — `duplicada` añadido por D33; `aceptada_ei`/`descartada_ei` aprobados por M3-docs D48, migración at build) | Módulo 1 — Nodo Captura: `descubierta` por defecto; Módulo 2 — Nodo 2: `preparada`; Módulo 2 — Nodo 3: `duplicada` (terminal) cuando confirma duplicado; Módulo 3 — Nodo Evaluación: `aceptada_ei`/`descartada_ei` (vía `evaluada`) |
| `observaciones` | TEXT DEFAULT 'N/A' | Información adicional relevante; en el Módulo 1 conserva el texto crudo de la fecha relativa (p. ej. "Publicado hace 9 horas") (D28); el Módulo 2 escribe la evidencia de duplicado (D33); `N/A` si vacío (D31) | Módulo 1 — Nodo Captura: texto de la tarjeta; Módulo 2 — Nodo 3: evidencia del duplicado |
| `fecha_creacion` | TEXT DEFAULT '' | Fecha/hora de alta del registro | Automática en la inserción |
| `fecha_ultima_edicion` | TEXT DEFAULT '' | Fecha/hora de la última actualización | Automática en la inserción y en cada actualización |
| `fuente_id` | TEXT DEFAULT '' | Fuente de origen de la oferta (identificador de la fuente configurada) | Módulo 1 — Nodo Captura: en la inserción |
| `empresa_id` | TEXT DEFAULT 'N/A' | Referencia a la empresa del catálogo (`EMP-xxxx`); `N/A` si la página de la oferta no expone empresa (D31) | Módulo 1 — no escribe; Módulo 2 — Nodo 2: upsert por `nombre_normalizado` → `empresa_id` (o `N/A`) |
| `ubicacion_id` | TEXT DEFAULT 'N/A' | Referencia a la ubicación del catálogo (`UBI-xxxx`); `N/R` si remoto/no reportada; `N/A` si la IA no clasificó | Módulo 1 — no escribe; Módulo 2 — Nodo 2: upsert por tupla `(ciudad, region, pais)` → `ubicacion_id` (o `N/R`/`N/A`) |
| `id_corrida` | TEXT DEFAULT '' | Corrida que descubrió la oferta (no se sobrescribe) | Módulo 1 — Nodo Captura: en la inserción; el Módulo 2 nunca lo sobrescribe |
| `id_sesion` | TEXT DEFAULT '' | Sesión de plataforma usada al descubrirla | Módulo 1 — Nodo Captura: en la inserción |
| `indice_set` | INTEGER DEFAULT '' | Índice del set de filtros que la produjo | Módulo 1 — Nodo Captura: en la inserción |
| `id_externo` | TEXT DEFAULT '' | Identificador externo de la oferta en la fuente; clave de deduplicación del upsert (no se normaliza a `N/A` — D31) | Módulo 1 — Nodo Captura: en la inserción |
| `fecha_ultima_verificacion` | TEXT DEFAULT '' | Marcador con semántica dual (D33): re-visita de dedup (Módulo 1, upsert) **o** verificación de duplicidad (Módulo 2 Nodo 3); `''` = pendiente. Exenta de la regla `N/A` (D31, punto 4) | Módulo 1 — Nodo Captura: re-Visita de dedup (D4); Módulo 2 — Nodo 3: tras evaluar la oferta |
| `ubicacion` | TEXT DEFAULT 'N/A' | Texto crudo de la ubicación tal como aparece en la tarjeta del listado (traspaso D45; antes `ubicacion_nombre` capturado por el Módulo 2 desde la página) | Módulo 1 — Nodo Captura: en la inserción, desde la tarjeta (`'N/R'` si no viene); el lote (b) del Nodo 2 lo reusa para clasificar sin re-capturar la página |
| `modalidad` | TEXT DEFAULT 'N/A' | Modalidad de trabajo de la oferta (presencial / remoto / híbrido); dato de la oferta, la IA no la toca | Módulo 1 — Nodo Captura: en la inserción, desde la tarjeta (traspaso D45); el Módulo 2 nunca la sobrescribe |
| `empresa` | TEXT DEFAULT 'N/R' | Nombre crudo de la empresa tal como aparece en la tarjeta del listado (espejo de `ubicacion`; el enlace al catálogo sigue siendo `empresa_id`) | Módulo 1 — Nodo Captura (D41); `'N/R'` si la tarjeta no lo trae; filas previas a D41 quedan en `'N/R'` |
| `id_duplicidad` | TEXT DEFAULT 'N/A' | ID de la oferta original cuando esta es `duplicada`; `N/A` para ofertas originales o sin verificar | Módulo 2 — Nodo 3: cuando confirma duplicado (terminal) |
| `resultado_evaluacion_inicial` | TEXT DEFAULT 'N/A' | Resultado completo de la evaluación inicial (entregable principal, v1–v5, decisión APROBADA/DESCARTADA, justificación una línea); `'N/A'` = pendiente | Módulo 3 — Nodo Evaluación inicial (D49): pasos 5–6 lo diligencian; fallos persistentes dejan `'N/A'`. D52: incluye `entregable_principal` (una línea, ≤20 palabras); la ruta V3-FAIL sin descripción (exenta de VAL-04) guarda `entregable_principal = 'N/A'` (D31) |

> **D31:** la columna `identificador_origen` fue eliminada (duplicado muerto de `id_externo`, nunca escrita). **D33:** se re-añade `eventos.id_oferta` (`DEFAULT 'N/A'`) para la trazabilidad por oferta del Módulo 2.

### 2.5. `corridas`

Registro de cada corrida (ejecución completa del flujo). Se crea en el **nodo INICIO** con `registrar_corrida()` (insert idempotente por `id_corrida`) y se cierra en el **nodo Finalizar** con `actualizar_corrida()`. La escriben también el **orquestador transversal** (`modules/orchestrator/orchestrator.py` → `ejecutar_corrida_programada`) para la corrida programada (resumen de módulos) — fila propia con su `id_corrida` distinto de los de los módulos (D34). Vocabulario de `estado` alineado al `EstadoCorrida` de `shared/models.py`: `en_ejecucion`, `completada`, `sin_fuentes`, `sin_pendientes`, `abortada` (D25 + D33 — `sin_pendientes` añadido por el Módulo 2; `error`/`concurrencia` retirados del vocabulario y mantenidos solo como `motivo_terminacion`; el Módulo 3 usa los mismos estados — D48).

| Columna | Tipo | Qué hace | Cuándo se diligencia |
|---|---|---|---|
| `id_corrida` | TEXT (PK) | ID único de la corrida (prefijo `COR`) | En el INICIO del módulo (Módulo 1/2), al crear la corrida; también por el orquestador transversal al iniciar la corrida programada |
| `fecha_inicio` | TEXT NOT NULL | Fecha/hora de inicio de la corrida | En el INICIO / orquestador (`T0` del orquestador) |
| `estado` | TEXT NOT NULL | Estado de la corrida (`en_ejecucion`, `completada`, `sin_fuentes`, `sin_pendientes`, `abortada`) | En el INICIO queda `en_ejecucion`; en el Finalizar se actualiza al estado final (vocabulario `EstadoCorrida`) |
| `fecha_fin` | TEXT DEFAULT '' | Fecha/hora de fin de la corrida | En el Finalizar, al cerrar la corrida |
| `motivo_terminacion` | TEXT DEFAULT '' | Motivo de terminación (`corrida_completada`, `sin_fuentes`, `sin_pendientes`, `cupo_agotado`, `error_total`, `error_critico`, `aborto`, `concurrencia` — `cupo_agotado` del Módulo 3: pare ordenado por cupo, `completada`/suceso — D48) | En el Finalizar, al cerrar la corrida; el orquestador usa `corrida_completada`/`aborto` |
| `total_ofertas` | INTEGER DEFAULT 0 | Ofertas únicas de la corrida; para Mód2 = unión DISTINCT entre los eventos `oferta_preparada` y `oferta_duplicada` vía `contar_distintos` (D45 — sustituye la suma literal `total_preparadas + total_duplicadas`; comparable entre módulos); para Mód3 = unión DISTINCT entre `oferta_aprobada` y `oferta_descartada` (D48) | En el Finalizar, desde las métricas del cierre |
| `total_errores` | INTEGER DEFAULT 0 | Total de eventos de error de la corrida | En el Finalizar, desde las métricas del cierre |
| `total_sucesos` | INTEGER DEFAULT 0 | Total de eventos de éxito de la corrida (semántica D30: escritos antes del evento de terminación; este último nunca se incluye) | En el Finalizar, desde las métricas del cierre |
| `fuentes_procesadas` | INTEGER DEFAULT 0 | Número de fuentes procesadas en la corrida (D31: `contar_distintos` excluye `''`/`NULL`/`'N/A'`) | En el Finalizar, desde las métricas del cierre |
| `total_preparadas` | INTEGER DEFAULT 0 | Ofertas preparadas por la corrida del Módulo 2 (`contar_filas(eventos, {id_corrida, codigo='oferta_preparada'})`) | En el Finalizar del Módulo 2, desde las métricas por eventos |
| `total_duplicadas` | INTEGER DEFAULT 0 | Ofertas marcadas como duplicadas por la corrida del Módulo 2 (`contar_filas(eventos, {id_corrida, codigo='oferta_duplicada'})`) | En el Finalizar del Módulo 2, desde las métricas por eventos |
| `total_aprobadas` | INTEGER DEFAULT 0 | Ofertas aprobadas por la corrida del Módulo 3 (DISTINCT `id_oferta` sobre `eventos` con `codigo='oferta_aprobada'`) — D49 | En el Finalizar del Módulo 3, desde las métricas por eventos |
| `total_descartadas` | INTEGER DEFAULT 0 | Ofertas descartadas por la corrida del Módulo 3 (DISTINCT `id_oferta` sobre `eventos` con `codigo='oferta_descartada'`) — D49 | En el Finalizar del Módulo 3, desde las métricas por eventos |

### 2.6. `eventos`

Bitácora de eventos (errores y sucesos) de las corridas, con `tipo` `error` o `suceso` y código de negocio. La escribe `escribir_evento()` desde los nodos: INICIO (fallos de inicialización, p. ej. ERR-10), Control de fuentes (abortos, ERR-01), Registro (resultado del registro), Captura (éxito `ofertas_registradas`, `registro_parcial`), Finalizar (terminación: `corrida_completada` como suceso o el motivo como error). El Módulo 2 añade: `oferta_preparada` (suceso, Nodo 2), `preparacion_fallida` (error, Nodo 2), `oferta_duplicada` (suceso, Nodo 3), `revision_pendientes` (suceso, Nodo 4). El Módulo 3 añade (D48): `oferta_aprobada` (suceso), `oferta_descartada` (suceso, con el veto que frenó), `evaluacion_fallida` (error, la oferta queda `preparada`). El orquestador transversal añade: `modulo_ejecutado` (suceso), `corrida_programada` (suceso final), `modulo_fallido` (error). Nunca se eliminan (auditoría). Regla D31: los campos sin valor se guardan como `N/A` (p. ej. el evento de terminación no tiene fuente ni sesión); `indice_set` conserva `0` como valor válido. En el Módulo 3, `fuente_id = 'N/A'` siempre (sin fuentes).

| Columna | Tipo | Qué hace | Cuándo se diligencia |
|---|---|---|---|
| `evento_id` | TEXT (PK) | ID único del evento (prefijo `EVT`) | Automático en cada `escribir_evento()` |
| `id_corrida` | TEXT NOT NULL | Corrida a la que pertenece el evento (obligatorio) | En cada `escribir_evento()`, desde el contexto de la corrida |
| `id_oferta` | TEXT DEFAULT 'N/A' | Oferta a la que se refiere el evento (re-añadido por D33 — supersede D31 D-1); `N/A` en eventos de módulo/orquestador | Módulo 2: eventos por oferta (`oferta_preparada`, `preparacion_fallida`, `oferta_duplicada`); Módulo 3 (D48): `oferta_aprobada`, `oferta_descartada`, `evaluacion_fallida`; `N/A` en el resto (D33) |
| `fuente_id` | TEXT DEFAULT 'N/A' | Fuente sobre la que ocurrió el evento; `N/A` en eventos de corrida (INICIO, Finalizar) y en el Módulo 2 / Módulo 3 / orquestador (sin fuentes) | En eventos con contexto de fuente (Captura, Registro); `N/A` en el resto (D31) |
| `id_sesion` | TEXT DEFAULT 'N/A' | Sesión de plataforma del evento; `N/A` si el evento no es de sesión | En eventos de Captura/Registro con sesión activa; `N/A` en el resto (D31) |
| `indice_set` | INTEGER DEFAULT 'N/A' | Índice del set de filtros donde ocurrió; `N/A` si no aplica (`0` es válido) | En eventos de Captura/Registro con set activo; `N/A` en el resto (D31) |
| `marca_temporal` | TEXT NOT NULL | Fecha/hora exacta del evento | En cada `escribir_evento()` (o automática si no se provee) |
| `tipo` | TEXT NOT NULL | Clasificación: `error` o `suceso` | En cada `escribir_evento()`, según el resultado del nodo |
| `codigo` | TEXT NOT NULL | Código de negocio (`ERR-01`, `ERR-10`, `ofertas_registradas`, `registro_parcial`, `oferta_preparada`, `preparacion_fallida`, `oferta_duplicada`, `revision_pendientes`, `oferta_aprobada`, `oferta_descartada`, `evaluacion_fallida`, `modulo_ejecutado`, `corrida_programada`, `modulo_fallido`, motivo de terminación, etc.) | En cada `escribir_evento()` |
| `evidencia` | TEXT DEFAULT 'N/A' | Evidencia: trazas, fragmentos, métricas asociadas; `N/A` si no hay payload | En cada `escribir_evento()` (nunca credenciales); formato `campo=valor` en eventos del orquestador (D34); `N/A` si vacío (D31) |

> **D31:** la columna `id_oferta` se eliminó inicialmente (nunca escrita en el Módulo 1; la trazabilidad evento-oferta no estaba implementada). **D33:** la columna se **re-añade** (`DEFAULT 'N/A'`) para soportar la trazabilidad por oferta del Módulo 2.

### 2.7. `sesiones`

Auditoría de las sesiones de plataforma por lote capturado. La escribe el **nodo Captura** con `escribir_fila("sesiones")` tras procesar cada lote (con reintento si falla).

| Columna | Tipo | Qué hace | Cuándo se diligencia |
|---|---|---|---|
| `id` | TEXT (PK) | ID único del registro de sesión (prefijo `SES`; en migración hereda el valor de `id_sesion`) | Automático en la inserción |
| `id_sesion` | TEXT NOT NULL | Identificador de la sesión asignado por la plataforma/fuente | En la Captura, desde el contexto de la sesión |
| `id_corrida` | TEXT NOT NULL | Corrida bajo la cual se estableció la sesión | En la Captura, desde el contexto de la corrida |
| `fuente_id` | TEXT NOT NULL | Fuente sobre la que se estableció la sesión | En la Captura, desde la fuente corriente |
| `indice_set` | INTEGER DEFAULT '' | Índice del set de filtros de la sesión | En la Captura, desde el set corriente |
| `marca_temporal` | TEXT NOT NULL | Fecha/hora de establecimiento de la sesión | En la Captura, con la hora actual |
| `total_declarado` | INTEGER DEFAULT '' | Total de ofertas declarado por la fuente, cuando lo expone | En la Captura, desde la página de resultados |
| `conteo` | INTEGER DEFAULT '' | Ofertas capturadas en el lote | En la Captura: tamaño del lote procesado |
| `estado` | TEXT NOT NULL | Estado final de la sesión | En la Captura, al auditar el lote (`completa`) |
| `fecha_creacion` | TEXT DEFAULT '' | Fecha/hora de alta del registro | Automática en la inserción |
| `fecha_ultima_edicion` | TEXT DEFAULT '' | Fecha/hora de la última actualización | Automática en la inserción y en cada actualización |

### 2.8. `bloqueo`

Bloqueo de concurrencia de corridas (una sola corrida activa a la vez **en todo el pipeline** — Módulos 1, 2 y 3 comparten el mismo bloqueo global, D3/D33/D48). Máximo una fila. La escribe el **nodo INICIO** con `adquirir_bloqueo()` (insert, o update por obsolescencia o con `forzar`) y la elimina el **nodo Finalizar** con `liberar_bloqueo()`. El INICIO también hace una prueba de escritura con `sondear_escritura()` (insert + rollback, sin dejar datos). El orquestador transversal **no gestiona el bloqueo** — lo asume tomado por el módulo en su INICIO.

| Columna | Tipo | Qué hace | Cuándo se diligencia |
|---|---|---|---|
| `id_corrida` | TEXT (PK) | Corrida dueña del bloqueo | En el INICIO, al adquirir el bloqueo (insert o update por obsolescencia/forzado) |
| `marca_temporal` | TEXT NOT NULL | Fecha/hora de adquisición del bloqueo; base para el umbral de obsolescencia | En el INICIO, al adquirir el bloqueo; se actualiza al renovar el bloqueo |
