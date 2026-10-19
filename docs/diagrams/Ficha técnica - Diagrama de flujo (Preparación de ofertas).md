# Especificación canónica densificada — Módulo 2: Preparación de ofertas

**Base de decisiones:** `docs/plans/Plan funcional fase 5.md` (decisiones globales D1-D5, análisis aprobado: 3 correcciones, huecos H1-H7 y 6 optimizaciones). Estructura espejo de la ficha del Módulo 1.

## Convenciones comunes

- **Alcance del módulo**: leer las ofertas en `descubierta` de `ofertas_descubiertas`, capturar la página de cada oferta (sin login), poblar los catálogos `empresas` y `ubicaciones` (la IA clasifica únicamente la ubicación), verificar duplicidad en dos etapas y cerrar la corrida con métricas propias. No interpreta, clasifica, puntúa ni decide adecuación.
- **Contexto de ejecución**: única estructura/objeto transmitida a todos los nodos. Ningún nodo posterior reinicializa conexiones ni estado, salvo responsabilidad asignada.
- **Trazabilidad**: todo registro incluye `id_corrida`; los eventos de oferta incluyen `id_oferta` (éxito y fallo). `fuente_id = 'N/A'` en este módulo (sin fuentes; respeta no-vacíos D31).
- **Registro**: en `"errores o sucesos"` (`eventos`); si no está disponible, registro crítico local (consola/archivo documentado). Todo evento incluye `id_corrida`, marca_temporal, tipo y descripción; los eventos de oferta incluyen `id_oferta`.
- **Aborto**: terminación inmediata en `"Finalizar Proceso"` con estado `abortada` y motivo `error_critico`/`aborto`.
- **Terminación controlada/normal**: cierre sin trabajo (`sin_pendientes`) o con trabajo (`corrida_completada`); lo registra `"Finalizar Proceso"`.
- **Reintentos**: máximo global configurable (`retries`, sección `preparacion:`); solo son reintentables los códigos declarados en cada nodo. Credenciales, tokens y cookies nunca se registran, evidencian ni persisten. La IA nunca bloquea la captura (best-effort).
- **Regla de datos (D31)**: ningún campo vacío — `N/A`/`N/R` cuando no aplica; exenciones: `id_externo` (dedup) y `fecha_ultima_verificacion` (marcador del Nodo 3).

---

## Nodo proceso: INICIO — Arranque de la corrida e inicialización del contexto de ejecución
**Versión**: 1.0 (aprobada)

### Posición
Punto de entrada único del módulo; precede toda decisión y acción de negocio. Ninguna decisión posterior puede ejecutarse sin el contexto producido aquí.

### Objetivo
Instanciar la corrida de preparación (corrida propia del módulo, decisión D3) y preparar el contexto de ejecución: trazabilidad, configuración validada (sección `preparacion:` completa), BD disponible, concurrencia (bloqueo global compartido con el Módulo 1), ofertas candidatas y estado inicial. **No captura datos ni verifica duplicidad** (eso corresponde a los nodos Preparación y Verificación de duplicidad).

### Descripción funcional
Al recibir disparador:
1. Crea instancia de corrida con `id_corrida` único y `fecha_inicio`.
2. Carga configuración y valida nivel global: **toda** la sección `preparacion:` — `umbral_titulo`, `umbral_descripcion`, `max_pasadas`, `pausa_entre_ofertas_segundos`, `limite_vida_sesion`, reintentos *(as-built D40: sin claves de enriquecimiento)*.
3. Verifica disponibilidad y permisos de escritura de la BD del módulo (prueba de escritura con rollback).
4. Valida concurrencia mediante bloqueo persistente **global compartido** con el Módulo 1.
5. Carga ofertas candidatas: SELECT de `ofertas_descubiertas` con estado `descubierta`, orden FIFO (`fecha_descubrimiento ASC, id ASC`).
6. Inicializa estado: contadores (`preparadas`, `duplicadas`, `errores`) y `hubo_candidatas` (bool) en el contexto — lo consume `"Finalizar Proceso"` para distinguir `error_total` de `sin_pendientes`.
7. Entrega control al nodo siguiente.

Error fatal de inicialización o concurrencia activa producen terminación controlada en `"Finalizar Proceso"` antes de tocar cualquier página.

### Responsabilidad
- **Negocio**: arrancar corrida y verificar precondiciones operativas. No accede a LinkedIn ni a páginas de ofertas, no captura, no verifica duplicidad.
- **Técnica**: `id_corrida`, conexión, bloqueo de concurrencia global, estado inicial, carga FIFO de candidatas.
- **Límite**: garantiza contexto y candidatas cargadas; no garantiza captura ni preparación exitosas. No accede a la IA ni a plataformas.

### Entradas
- Disparador manual (hoy) o programado (futuro).
- Almacén de configuración: sección `preparacion:` completa + `concurrencia` (umbral de obsolescencia) + `retries`.
- Estado persistente de bloqueo, si existe.
- BD con `ofertas_descubiertas`.

### Salidas
- Contexto inicializado: `id_corrida`, fecha_inicio, candidatas FIFO, `hubo_candidatas`, contadores, conexión activa, bloqueo adquirido.
- Terminación en `"Finalizar Proceso"` con `abortada`/`concurrencia` si aplica.
- Control normal al nodo de decisión "¿Quedan ofertas por preparar en esta corrida?".

### Reglas de negocio
- **RN-01**: toda corrida tiene `id_corrida` único; todo registro del módulo queda enlazado a él.
- **RN-02**: solo una ejecución activa a la vez en todo el pipeline (bloqueo global compartido Módulo 1/Módulo 2).
- **RN-03**: el iterador de candidatas se reinicia al inicio de cada corrida; dentro de la corrida, cada pasada del bucle re-consulta la BD en lugar de reutilizar un iterador congelado.
- **RN-04**: este nodo no valida si hay ofertas pendientes; esa validación es del nodo de decisión siguiente.
- **RN-05**: este nodo no accede a LinkedIn ni a páginas de ofertas (eso es del nodo Preparación).
- **RN-06**: la corrida procesa todas las ofertas en `descubierta` (sin `max_ofertas_por_corrida`); el tiempo se acota por las pausas configuradas. *(As-built D42: la pausa entre ofertas es aleatoria uniforme en [base − jitter, base + jitter] — `pausa_jitter_segundos`, 0 = fija; más humana que un intervalo idéntico y ~30 % más rápida con base 1,2 s.)*
- **RN-07**: selección FIFO — más antiguas primero; las fallidas de corridas previas quedaron en `descubierta` y vuelven a intentarse en orden. *(As-built D53: el desempate por identificador compara su NÚMERO secuencial (`numero_secuencial_id`) — la comparación textual invierte el orden a partir de 10.000 ofertas por prefijo.)*

### Validaciones
- **VAL-01**: `id_corrida` único y no nulo.
- **VAL-02**: configuración global: sección `preparacion:` completa y con rangos válidos (`0 ≤ umbral ≤ 100`, `max_pasadas ≥ 1`, pausas ≥ 0, `limite_vida_sesion ≥ 1`, `profundidad ≥ 0`, reintentos coherentes).
- **VAL-03**: BD: conexión abierta y prueba de escritura exitosa con rollback.
- **VAL-04**: bloqueo legible; obsolescencia por marca_temporal contra umbral configurable; marcas temporales coherentes.
- **VAL-05**: contexto completo antes de entregar control (`hubo_candidatas` presente).
- **VAL-06**: candidatas cargadas en orden FIFO; conteo ≥ 0.

### Condiciones
- **Continuación normal**: configuración válida + BD disponible + sin concurrencia activa.
- **Terminación**: configuración ausente/ilegible/corrupta; BD indisponible/bloqueada/sin permisos; concurrencia activa; estado de bloqueo no decidible.
- **Sin candidatas**: no termina aquí; el nodo de decisión siguiente resuelve `sin_pendientes`.

### Ramas
- **Normal** → `"¿Quedan ofertas por preparar en esta corrida?"`.
- **Excepción** → `"Finalizar Proceso"` con estado `abortada` o motivo `concurrencia`.

### Errores y excepciones

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---|---:|---|---|---|
| ERR-01 | Colisión o fallo de generación de `id_corrida` | 1 | Registro crítico local | Reintento único; si persiste, aborto | `abortada` |
| ERR-02 | Configuración ausente | 2 | Registro crítico local | Aborto | `abortada` |
| ERR-03 | Configuración ilegible | 2 | Registro crítico local | Aborto | `abortada` |
| ERR-04 | Configuración corrupta / estructura inconsistente | 2 | Registro crítico local | Aborto | `abortada` |
| ERR-05 | BD indisponible / bloqueada / sin permisos | 3 | Evento crítico si accesible; si no, local | Aborto | `abortada` |
| ERR-06 | Concurrencia activa | 4 | Evento "finalización por concurrencia" | Terminación controlada | `concurrencia` |
| ERR-07 | Bloqueo obsoleto (antigüedad > umbral) | 4 | Suceso de sobrescritura | Sobrescribir bloqueo y continuar | continúa |
| ERR-08 | Estado de bloqueo no decidible | 4 | Evento crítico | Aborto | `abortada` |
| ERR-09 | Contienda de adquisición de bloqueo | 4 | — | Atomicidad/unicidad; perdedor cae en ERR-06 | `concurrencia` |
| ERR-10 | Falla interna de inicialización de estado | 6 | Evento crítico si accesible | Aborto | `abortada` |

### Dependencias y contratos
- **Antecesor**: ninguno.
- **Sucesor normal**: `"¿Quedan ofertas por preparar en esta corrida?"`.
- **Sucesor de excepción**: `"Finalizar Proceso"`.
- **Contrato entregado**: contexto completo como única interfaz; candidatas FIFO con `hubo_candidatas`.
- **Impactos aprobados**:
  - `"Finalizar Proceso"` libera el bloqueo y consume `hubo_candidatas` para `error_total`.
  - El nodo Preparación re-consulta su lote por pasada (RN-03).
  - `corridas` incorpora `total_preparadas`/`total_duplicadas` (D3) y el vocabulario `sin_pendientes` (decisión aprobada).

### Notas de implementación
- Espejo del INICIO del Módulo 1: mismo mecanismo de bloqueo, `sondear_escritura`, `registrar_corrida` y `generar_id`.
- Orden obligatorio: configuración antes que BD; candidatas después de BD y bloqueo.
- No acceder a la IA ni a plataformas; sin credenciales.
- Sin valores fijos: todo desde la sección `preparacion:`.

### Pasos funcionales
1. **Recibir disparador e instanciar corrida**. Entrada: evento manual/programado. Proceso: crear instancia, generar `id_corrida`, fecha_inicio. Salida: instancia. Val: VAL-01. Err: ERR-01.
2. **Cargar configuración y validar nivel global**. Entrada: almacén de configuración. Proceso: leer y validar la sección `preparacion:` completa (claves y rangos). Salida: configuración cruda en contexto. Val: VAL-02. Err: ERR-02, ERR-03, ERR-04.
3. **Verificar BD**. Entrada: parámetros de conexión. Proceso: abrir conexión; prueba de escritura con rollback. Salida: conexión disponible. Val: VAL-03. Err: ERR-05.
4. **Validar concurrencia**. Entrada: `id_corrida`, estado de bloqueo, umbral. Proceso: leer bloqueo global compartido; activo no obsoleto → terminación controlada; obsoleto → sobrescribir y continuar; inexistente → marcar bloqueo. Salida: bloqueo adquirido o terminación. Val: VAL-04. Err: ERR-06, ERR-07, ERR-08, ERR-09.
5. **Cargar ofertas candidatas**. Entrada: BD. Proceso: SELECT `descubierta` orden FIFO (`fecha_descubrimiento ASC, id ASC`). Salida: lista de candidatas. Val: VAL-06. Err: ERR-05.
6. **Inicializar estado**. Entrada: candidatas. Proceso: fijar contadores y `hubo_candidatas` (bool). Salida: contexto completo. Val: VAL-05. Err: ERR-10.
7. **Entregar control**. Entrada: contexto completo. Proceso: cerrar nodo. Salida: flujo a la decisión de candidatas. Val: VAL-05. Err: contexto incompleto → ERR-10.

---

## Nodo decisión: “¿Quedan ofertas por preparar en esta corrida?”
**Versión**: 1.0 (aprobada)

### Posición
Primera decisión de negocio, inmediatamente después de INICIO. Análoga a "¿Existe al menos una fuente…?" del Módulo 1.

### Objetivo
Decidir si la corrida continúa o termina controladamente según exista al menos una oferta candidata en `descubierta`.

### Descripción funcional
Lee la lista de candidatas del contexto en memoria, sin releer la BD. Si hay ≥ 1 candidata, entrega control al nodo Preparación con contrato "lista no vacía". Si hay 0, fija motivo `sin_pendientes` —suceso, no error— y entrega control a `"Finalizar Proceso"`. No realiza I/O, no accede a LinkedIn, no revalida estructura.

### Entradas
Contexto de INICIO: lista de candidatas, `hubo_candidatas`, `id_corrida`, conexión activa, bloqueo adquirido.

### Salidas
- **Sí** → Preparación con lista no vacía.
- **No** → `"Finalizar Proceso"` con motivo `sin_pendientes`.
- **Falla interna** → `"Finalizar Proceso"` con estado `abortada`.

### Reglas de negocio
- **RN-01**: evaluar solo contexto; prohibido releer la BD.
- **RN-02**: "candidata" = oferta cargada por INICIO en `descubierta`; no hay estados adicionales.
- **RN-03**: no revalidar estructura; ya lo hizo INICIO.
- **RN-04**: ausencia de candidatas es terminación controlada `sin_pendientes`, tipo suceso (estado `sin_pendientes` en `corridas` — vocabulario nuevo aprobado).
- **RN-05**: este nodo no registra; `"Finalizar Proceso"` registra la terminación.
- **RN-06**: rama Sí garantiza lista no vacía; ningún nodo posterior revalida existencia.

### Validaciones
- **VAL-01**: lista de candidatas accesible en contexto.
- **VAL-02**: evaluación sobre lista leída; conteo entero ≥ 0; sin revalidación.
- **VAL-03**: rama Sí solo con conteo > 0.
- **VAL-04**: en rama No, `sin_pendientes` fijado con `id_corrida` y marca_temporal antes de entregar control.

### Condiciones y ramas
- **Sí**: conteo > 0 → Preparación.
- **No**: conteo == 0 → `"Finalizar Proceso"` con `sin_pendientes`.
- **Aborto**: contexto sin configuración/incompleto → `"Finalizar Proceso"` con `abortada`.

### Errores

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---|---:|---|---|---|
| ERR-01 | Contexto sin candidatas o incompleto | 1 | Evento crítico si accesible | Aborto | `abortada` |

### Dependencias y contratos
- **Antecesor**: INICIO.
- **Sucesor Sí**: Preparación.
- **Sucesor No**: `"Finalizar Proceso"` con `sin_pendientes`.
- **Impactos aprobados**: ningún nodo posterior revalida existencia; `"Finalizar Proceso"` incorpora `sin_pendientes`.

### Notas de implementación
- Nodo de evaluación pura: sin I/O, sin red, sin escritura, salvo fijar motivo en rama No.
- Leer la lista del mismo objeto de contexto; no copiar ni transformar.

### Pasos funcionales
1. **Leer lista del contexto**. Entrada: contexto. Proceso: acceder a lista; no releer la BD. Salida: lista posiblemente vacía. Val: VAL-01. Err: ERR-01.
2. **Evaluar existencia**. Entrada: lista. Proceso: contar; condición = conteo > 0. Salida: Sí/No. Val: VAL-02. Err: ninguna.
3. **Rama Sí**. Entrada: resultado Sí. Proceso: entregar control. Salida: flujo a Preparación. Val: VAL-03. Err: ninguna.
4. **Rama No**. Entrada: resultado No, `id_corrida`. Proceso: fijar `sin_pendientes` y entregar control. Salida: flujo a `"Finalizar Proceso"`. Val: VAL-04. Err: ninguna.

---

## Nodo proceso: “Preparación de ofertas”
**Versión**: 1.0 (aprobada)

### Posición
Entre:
- rama Sí de `"¿Quedan ofertas por preparar en esta corrida?"` (primera pasada);
- rama Sí de `"¿Quedan ofertas en 'descubierta'?"` (pasadas siguientes del bucle).

Sucesor: `"Verificación de duplicidad"`. Nodo re-entrante por pasada.

### Objetivo
Para cada oferta en `descubierta` (FIFO): capturar la página de la oferta (sin login), poblar los catálogos `empresas` y `ubicaciones` (IA solo para clasificar la ubicación), actualizar la oferta y escribir el evento. No verifica duplicidad (eso corresponde al nodo siguiente, en dos etapas según D5).

**Dos lotes por pasada (H1):** (a) `descubierta` — captura completa (pasos 1-5); (b) `preparada` con `ubicacion_id = 'N/A'` (ubicaciones pendientes por IA caída) — solo pasos 3-5 (clasificar, buscar/crear, actualizar), sin re-capturar la página (el texto crudo ya está en `ubicacion`). El lote (b) corre después del (a): las ofertas recién preparadas con IA caída se gestionan en la misma pasada.

### Descripción funcional
Flujo por oferta (orden obligatorio, por dependencia natural):

| # | Paso | Qué hace | Fuente |
|---|---|---|---|
| 1 | **Capturar la página** | HTTP directo (httpx): extraer título (sobrescribe el de la tarjeta **solo si existe `<h1>`**), descripción completa con su estructura visible (párrafos/listas/saltos, D41) y empresa (nombre + link de perfil). La ubicación cruda y la modalidad ya vienen escritas por el Módulo 1 desde la tarjeta (traspaso D45 — este nodo ya no las extrae) | Página de la oferta (`/jobs/view/N`) |
| 2 | **Diligenciar empresa** | Upsert en `empresas` (dedup por `nombre_normalizado`, sin IA) → `empresa_id` (o `N/A` si la página no la muestra) | Paso 1 |
| 3 | **Diligenciar ubicación (con IA)** | Clasificar texto crudo → tupla `{ciudad, región, país}` (JSON validado) → buscar/crear en `ubicaciones` → `ubicacion_id` (o `N/R` si remoto) | Texto almacenado en `ubicacion` (Módulo 1) |
| 4 | **Actualizar la oferta** | Guardar `titulo` (si `<h1>`), `descripcion_original`, `empresa_id`, `ubicacion_id`. **NO toca `fecha_ultima_verificacion`** (marcador exclusivo del nodo de Verificación), ni `ubicacion`/`modalidad` (proiedad del Módulo 1, D45) | Pasos 2-3 |
| 5 | **Escribir evento** | `oferta_preparada` (suceso) con `id_oferta` | Paso 4 |

En fallo del paso 1: evento `preparacion_fallida` (error) con `id_oferta` + reintento configurable; si persiste, la oferta permanece en `descubierta` para la siguiente pasada/corrida. **Todos los eventos de oferta llevan `id_oferta`, éxito y fallo.**

### Entradas
- Contexto: candidatas, `id_corrida`, configuración `preparacion:` (`pausa_entre_ofertas_segundos`, `limite_vida_sesion`, reintentos), sesión HTTP de invitado, cachés de corrida (empresas, ubicaciones, IA por texto). *(As-built D40: sin claves ni cachés de enriquecimiento.)*
- BD: `ofertas_descubiertas`, `empresas`, `ubicaciones`.
- Servicio de IA (bajo demanda, solo ubicación; best-effort).

### Salidas
- Ofertas en `preparada` con título fiel, descripción, `empresa_id`, `ubicacion_id` (ID, `N/R` o `N/A` pendiente) y `modalidad`.
- Catálogos `empresas`/`ubicaciones` poblados (upserts idempotentes).
- Eventos `oferta_preparada`/`preparacion_fallida`.
- Control único a `"Verificación de duplicidad"`.
- Aborto → `"Finalizar Proceso"` con `abortada`.

### Reglas de negocio
- **RN-01**: dos lotes por pasada: (a) `descubierta` (pasos 1-5), (b) `preparada` con `ubicacion_id = 'N/A'` (pasos 3-5); el lote (b) después del (a).
- **RN-02**: cada pasada re-consulta su lote en la BD (no usa el iterador congelado de INICIO).
- **RN-03**: sesión HTTP reutilizada para todas las ofertas; **límite de vida configurable** (renovar cada N ofertas, p. ej. 50); **fallback authwall** → nueva sesión de invitado y se reintenta la oferta; **pausa entre ofertas** configurable (`pausa_entre_ofertas_segundos`, prudencia anti-bloqueo — se detectó `uc=scraping` en la investigación).
- **RN-04**: reintento por oferta configurable; si persiste → oferta queda en `descubierta` (siguiente pasada/corrida).
- **RN-05**: empresa — upsert por `nombre_normalizado` (sin IA); **caché en memoria de la corrida** (empresa → `empresa_id`). **As-built D40 (2026-08-25):** el enriquecimiento de perfiles introducido por D39 fue retirado — el nodo ya no visita perfiles de empresa; el catálogo `empresas` guarda solo identidad (`id`, `nombre`, `nombre_normalizado`, `perfil_linkedin`) y fechas de auditoría. **As-built D41 (2026-08-25):** la clave del upsert usa `normalizar_nombre_empresa` — minúsculas y espacios simples **conservando todos los caracteres** (tildes, ñ, puntuación, `&`, `.`, paréntesis); ubicaciones y títulos de duplicidad mantienen la regla estricta (`normalizar_texto`). La extracción de la descripción preserva la estructura visible del anuncio: cada párrafo/bloque en su línea, `<br>` como salto y viñetas `<li>` con guion (`- `); aplica a preparaciones posteriores a D41.
- **RN-06**: ubicaciones — dedup por **tupla completa `(ciudad, región, país)` normalizada**; la IA completa país/región solo por conocimiento seguro; "Colombia" solo → `(N/A, N/A, Colombia)` con ID compartido; "Remoto" → **no se crea ubicación**; `ubicacion_id = 'N/R'`; la **modalidad es dato de la oferta** (la IA no la toca).
- **RN-07**: IA — solo clasifica texto (recibe prompt, devuelve `{ciudad, región, país}` JSON validado con Pydantic); no selecciona ofertas, no lee la BD, no escribe, no tiene memoria del catálogo; **caché por texto distinto en el contexto de la corrida** (la IA se invoca una vez por texto de ubicación distinto); si la IA falla u Ollama está caído → la oferta se captura igual y queda `ubicacion_id = 'N/A'` (pendiente). **La IA jamás bloquea la captura.**
- **RN-08**: tres estados de `ubicacion_id`: `N/A` (pendiente — la IA aún no la gestionó), `N/R` (gestionada — remoto/no reportada), `UBI-xxxx` (gestionada — identificada).
- **RN-09**: todos los eventos de oferta llevan `id_oferta` (éxito y fallo).
- **RN-10**: `titulo` se sobrescribe solo si el `<h1>` existe (best-effort; nunca deja el campo vacío — D31).
- **RN-11**: este nodo no verifica duplicidad (nodo siguiente) ni toca `fecha_ultima_verificacion` (marcador del nodo siguiente).
- **RN-12**: evidencia acotada; trazabilidad `id_corrida` + `id_oferta`.

### Validaciones
- **VAL-01**: insumos presentes (contexto, configuración, sesión).
- **VAL-02**: lote (a) FIFO; lote (b) solo `preparada` con `ubicacion_id = 'N/A'`.
- **VAL-03**: política de reintentos cumplida; pausa aplicada entre ofertas.
- **VAL-04**: oferta actualizada respeta D31 (sin vacíos); tupla de ubicación normalizada antes de buscar.
- **VAL-05**: evento escrito con `id_oferta`; evidencia acotada.
- **VAL-06**: cachés coherentes (empresa → `empresa_id`, texto → tupla).

### Condiciones
- **Normal**: ofertas procesadas (éxito o fallo individual), catálogos actualizados.
- **Fallo de oferta**: no aborta; oferta queda `descubierta` o `preparada` según el paso fallido.
- **Aborto**: insumos ausentes/corruptos; corrupción de contexto.

### Ramas
- Normal única → `"Verificación de duplicidad"`.
- Aborto → `"Finalizar Proceso"` con `abortada`.

### Errores y eventos

| Código | Error / evento | Reint. | Detección | Registro / acción | Estado |
|---|---|---|:---:|---|---|---|
| ERR-01 | Insumos ausentes/corruptos | No | 1 | Evento crítico; aborto | `abortada` |
| ERR-02 | `pagina_inalcanzable` (red/DNS/404) | Sí | Paso 1 | Backoff/reintento; agotado → `preparacion_fallida`; oferta queda `descubierta` | fallo de oferta |
| ERR-03 | `tiempo_agotado_captura` | Sí | Paso 1 | Ídem ERR-02 | fallo de oferta |
| ERR-04 | `authwall_detectado` | Sí | Paso 1 | Renovar sesión de invitado y reintentar; agotado → `preparacion_fallida` | fallo de oferta |
| ERR-05 | `respuesta_invalida` (HTML no interpretable) | No | Paso 1 | `preparacion_fallida`; oferta queda `descubierta` | fallo de oferta |
| ERR-06 | `error_interno_captura` | No | Paso 1 | Ídem ERR-05 | fallo de oferta |
| ERR-07 | `empresa_no_disponible` (página sin empresa) | No | Paso 2 | `empresa_id = 'N/A'`; continúa | continúa |
| ERR-08 | `ubicacion_no_clasificada` (IA caída/Ollama) | No | Paso 3 | `ubicacion_id = 'N/A'` (pendiente); continúa — la IA jamás bloquea | continúa |
| ERR-09 | Corrupción del contexto al guardar | No | Paso 4-5 | Evento crítico; aborto | `abortada` |
| EVT-01 | `oferta_preparada` | No | Paso 5 | Suceso con `id_oferta`; evidencia acotada | continúa |
| EVT-02 | `preparacion_fallida` | No | Paso 1 | Error con `id_oferta`; oferta queda `descubierta` | fallo de oferta |

**Contrato de códigos**: `oferta_preparada` (suceso), `preparacion_fallida` (error), `pagina_inalcanzable`, `tiempo_agotado_captura`, `authwall_detectado`, `respuesta_invalida`, `error_interno_captura`, `empresa_no_disponible`, `ubicacion_no_clasificada`.

### Escenarios límite
- Muro de login (authwall) en una oferta → ERR-04 con renovación de sesión.
- Página borrada / 404 permanente → ERR-02; oferta queda `descubierta`; el bucle la reintenta hasta `max_pasadas` y luego queda para la próxima corrida.
- IA caída u Ollama inactivo → ERR-08; oferta `preparada` con `ubicacion_id = 'N/A'`; el lote (b) de la misma corrida o la siguiente corrida la gestiona.
- Página sin empresa → ERR-07; `empresa_id = 'N/A'` (D31).
- "Remoto" → sin creación de ubicación; `ubicacion_id = 'N/R'`.
- "Colombia" solo → `(N/A, N/A, Colombia)` compartido entre ofertas.
- Título sin `<h1>` → se conserva el de la tarjeta (RN-10).
- Límite de vida de sesión agotado → renovar entre ofertas (sin afectar las procesadas).

### Dependencias y contratos
- **Antecesores**: rama Sí de la decisión de candidatas; rama Sí de `"¿Quedan ofertas en 'descubierta'?"`.
- **Sucesor normal**: `"Verificación de duplicidad"`.
- **Sucesor de aborto**: `"Finalizar Proceso"`.
- **Contratos consumidos**: candidatas FIFO; configuración `preparacion:`; contexto de corrida.
- **Contratos entregados**: ofertas `preparada` con título fiel, descripción, `empresa_id`, `ubicacion_id` y `modalidad`; catálogos poblados; eventos con `id_oferta`.
- **Impactos aprobados**:
  - `"Verificación de duplicidad"` consume `titulo`, `empresa_id` y `descripcion_original` (la descripción la captura este nodo; el Módulo 1 no la captura — D28/D29).
  - `"¿Quedan ofertas en 'descubierta'?"` consulta lo que quede sin procesar.
  - `"Finalizar Proceso"` cierra la sesión HTTP. *(As-built D40: el enriquecimiento del catálogo ya no existe en ninguna parte del flujo — retirado por decisión D40.)*

### Notas de implementación
- httpx con sesión de invitado y headers de navegador; sin Playwright en el camino crítico (D4).
- `normalizar_texto` (nueva utilidad en `shared/utilidades.py`): minúsculas, sin acentos, sin puntuación, espacios simples — usada para `empresas.nombre_normalizado` y para la tupla de ubicación.
- Prompt de clasificación de ubicación en `prompts/` (separado del código); propósito de ruteo `ai_routing.preparacion` en `config.yaml`.
- Cachés en el contexto de la corrida: empresas, ubicaciones (por tupla) e IA (por texto distinto) — perduran entre pasadas del bucle.
- Validación Pydantic de la tupla `{ciudad, región, país}` en el nodo; la IA devuelve JSON.
- No escribir `fecha_ultima_verificacion`; no sobrescribir `id_corrida` de la oferta.
- Texto crudo de ubicación en `ubicacion` — propiedad del Módulo 1 desde el traspaso aprobado (2026-08-25; registrado como D45): este nodo ya no lo extrae de la página.
- Sin valores fijos: sesión, pausas, reintentos y límite de vida desde configuración.
- **Nota as-built 2026-08-25 (decisión D43):** el paso 3 resuelve de forma determinista los textos que SOLO nombran un departamento colombiano (`REGIONES_COLOMBIA`, forma `normalizar_texto`; sufijo opcional "colombia") ANTES de invocar la IA — p. ej. "CAUCA" → `(N/A, cauca, colombia)`; los aciertos se cachean como éxitos (RN-07). Los textos con ciudad no cubiertos por los alias (p. ej. direcciones completas como "Bogotá, Distrito Capital, Colombia") siguen su camino normal hacia PRM-006 v3. Las filas legadas pendientes (`preparada`+`N/A`) se auto-reparan por el lote (b) sin HTTP.
- **Nota as-built 2026-08-25 (decisión D44):** la ruta local de clasificación usa `gpt-oss:120b-cloud` (swap desde gpt-oss:20b-cloud tras experimento comparado — igual calidad, ~3x más rápido). PRM-006 v3: guía de reconocimiento confiado (formato inusual — mayúsculas, sin tildes, abreviaturas, sin país — jamás justifica N/A por sí solo), contrato de salida estricto (primer carácter `{`), y cuatro ejemplos resueltos (CAUCA, ESTADO DE MEXICO, Medellín, solo-país) orientados a la expansión América. La chuleta D43 sigue activa como vía rápida.
- **Nota as-built 2026-08-26 (decisión D46):** el paso 3 resuelve la fila de catálogo con UNA sola lectura (filtro por país): igualdad exacta primero y, con `umbral_alias_ubicacion` > 0 (default 90; 0 desactiva), fusión por similitud RapidFuzz para variantes del mismo lugar — sin conflictos de componente y al menos una coincidencia real; un N/A jamás fusiona por sí solo; las filas solo-país nunca se crean por vía difusa. Alias deterministas de tupla COMPLETA (`ALIAS_UBICACIONES`: "Bogotá D.C." → bogota/distrito capital/colombia) se consultan antes de la tabla departamental D43; cada fusión queda registrada en el log (`alias_ubicacion_fusionado`).
- **Nota as-built 2026-08-26 (decisión D45, traspaso registrado):** la columna se llama `ubicacion` (renombrada desde `ubicacion_nombre`) y su escritor es el Módulo 1 desde la tarjeta del listado, junto con `modalidad` — este nodo ya no las extrae de la página ni las sobrescribe; PRM-006 clasifica el texto almacenado. La métrica `total_ofertas` del Finalizar es la unión DISTINCT de ofertas únicas entre `oferta_preparada` y `oferta_duplicada` (sustituye la suma literal).

### Pasos funcionales
1. **Leer insumos**. Entrada: contexto, configuración, sesión HTTP, cachés. Proceso: acceder desde contexto; resolver parámetros efectivos. Salida: insumos. Val: VAL-01. Err: ERR-01.
2. **Determinar lotes**. Entrada: BD. Proceso: re-consultar (a) `descubierta` FIFO y (b) `preparada` con `ubicacion_id = 'N/A'`. Salida: lotes. Val: VAL-02. Err: ERR-05.
3. **Capturar página (lote a, paso 1)**. Entrada: oferta, sesión, reintentos. Proceso: GET a `/jobs/view/N`; authwall → renovar sesión y reintentar; extraer título (`<h1>` si existe), descripción y empresa (la ubicación cruda y la modalidad las escribió el Módulo 1 desde la tarjeta — traspaso D45); pausa entre ofertas. Salida: datos crudos o `preparacion_fallida`. Val: VAL-03. Err: ERR-02..ERR-06, EVT-02.
4. **Diligenciar empresa (paso 2)**. Entrada: nombre + perfil. Proceso: caché → normalizar → upsert por `nombre_normalizado` → `empresa_id` (o `N/A`). Salida: `empresa_id`. Val: VAL-06. Err: ERR-07.
5. **Diligenciar ubicación (paso 3)**. Entrada: texto crudo. Proceso: caché por texto → si nuevo, IA (JSON validado) → tupla → buscar/crear en `ubicaciones` → `ubicacion_id`; remoto → `N/R`; fallo IA → `N/A`. Salida: `ubicacion_id`. Val: VAL-06. Err: ERR-08.
6. **Actualizar oferta (paso 4)**. Entrada: datos crudos, `empresa_id`, `ubicacion_id`. Proceso: actualizar `titulo` (si `<h1>`), `descripcion_original`, `empresa_id`, `ubicacion_id`; sin tocar `fecha_ultima_verificacion`, `ubicacion` ni `modalidad`. Salida: oferta actualizada. Val: VAL-04. Err: ERR-09.
7. **Escribir evento (paso 5)**. Entrada: oferta, `id_corrida`. Proceso: `oferta_preparada` con `id_oferta`. Salida: evento. Val: VAL-05. Err: ERR-09.
8. **Lote (b)**. Entrada: pendientes de ubicación. Proceso: pasos 3-5 sin captura (texto crudo de `ubicacion`). Salida: `ubicacion_id` resuelto o `N/A`. Val: VAL-02. Err: ERR-08, ERR-09.
9. **Entregar control**. Entrada: contexto. Proceso: cerrar nodo. Salida: flujo a `"Verificación de duplicidad"`. Err: ninguna.

---

## Nodo proceso: “Verificación de duplicidad”
**Versión**: 1.0 (aprobada)

### Posición
Entre `"Preparación de ofertas"` y `"¿Quedan ofertas en 'descubierta'?"`.

### Objetivo
Detectar, entre las ofertas ya preparadas, cuáles son la misma oferta publicada dos veces (misma empresa re-publicando el mismo cargo) y marcarlas como `duplicada` (terminal, D1), apuntando a la oferta original (`id_duplicidad`, D2). Nodo **100 % local**: sin IA, sin HTTP, sin catálogos — solo compara datos ya capturados con similitud difusa (RapidFuzz, misma librería que usa la evaluación).

### Descripción funcional
1. Consulta el **conjunto a evaluar**: `preparada` con `fecha_ultima_verificacion = ''` (pendientes, de esta corrida o de corridas anteriores — auto-reparación).
2. Consulta el **universo de comparación**: `preparada` con `id_duplicidad = 'N/A'` (originales candidatos, verificadas o no, incluidas las del lote actual).
3. Construye el índice de la etapa 1 en memoria por clave `(titulo_normalizado, empresa_id)` — búsqueda O(1).
4. Por cada oferta pendiente X:
   - **Etapa 1 — exacta**: título normalizado idéntico y misma `empresa_id` → **duplicado directo** (sin comparar descripción).
   - **Etapa 2 — difusa**: para las que no pasaron la etapa 1, título ≥ `umbral_titulo` (90) **y** descripción ≥ `umbral_descripcion` (85), ambas con RapidFuzz, solo entre candidatos de la misma empresa → duplicado.
5. Duplicado → `estado = duplicada`, `id_duplicidad = id del original`, evidencia en `observaciones`, evento `oferta_duplicada`, `fecha_ultima_verificacion` actualizada. No duplicado → solo `fecha_ultima_verificacion` actualizada.

**Misma empresa es requisito en ambas etapas** (confirmado): un duplicado real es la misma empresa republicando; títulos genéricos ("Desarrollador") con empresas distintas no son duplicados.

### Entradas
- BD: `ofertas_descubiertas` (título, `empresa_id`, `descripcion_original`, `estado`, `id_duplicidad`, `fecha_ultima_verificacion`).
- Configuración: `umbral_titulo`, `umbral_descripcion` (sección `preparacion:`).
- `normalizar_texto` (utilidad compartida).

### Salidas
- Ofertas marcadas `duplicada` + `id_duplicidad` + evidencia en `observaciones`.
- `fecha_ultima_verificacion` actualizada en todas las evaluadas (marcador: `''` = pendiente).
- Eventos `oferta_duplicada`.
- Oferta original intacta (sin cambios, sin evento).
- Control único a `"¿Quedan ofertas en 'descubierta'?"`.
- Aborto → `"Finalizar Proceso"` con `abortada`.

### Reglas de negocio
- **RN-01**: nodo 100 % local; sin IA, sin HTTP, sin catálogos.
- **RN-02**: misma `empresa_id` es requisito en ambas etapas (sin falsos positivos).
- **RN-03**: etapa 1 = título normalizado idéntico + misma empresa → duplicado directo, indexado en memoria.
- **RN-04**: etapa 2 = título difuso ≥ `umbral_titulo` **y** descripción difusa ≥ `umbral_descripcion` (ambas, RapidFuzz), solo sobre candidatos de la misma empresa.
- **RN-05**: universo = `preparada` con `id_duplicidad = 'N/A'` (incluidas las del lote actual — el Módulo 1 puede haber capturado la misma oferta dos veces en la misma corrida); se excluyen las `duplicada` (evita cadenas: X ≈ Y ≈ Z → X siempre apunta a Z, el original) y las `descubierta` (aún sin descripción).
- **RN-06**: conjunto a evaluar = `preparada` con `fecha_ultima_verificacion = ''` (pendientes, de esta corrida o corridas anteriores). Sin este marcador el nodo no sabría qué ofertas ya fueron verificadas y re-verificaría todo el histórico en cada corrida.
- **RN-07**: el original nunca cambia; el FIFO de INICIO garantiza que el más antiguo se preparó primero y es el original. *(As-built D53: los desempates T4/T6 de duplicidad comparan el NÚMERO secuencial del id, no su texto — el orden textual se rompe a partir de 10.000 ofertas por prefijo.)*
- **RN-08**: descripción `N/A` → sin candidato de etapa 2 (similitud 0; sin falsos positivos).
- **RN-09**: `fecha_ultima_verificacion` la escribe **solo este nodo** (marcador "última verificación de duplicidad"; columna exenta de D31).
- **RN-10**: fallo de BD en una oferta → reintento (`ejecutar_con_reintento`); si persiste → la oferta queda `preparada` sin verificar (pendiente) y se continúa; la próxima corrida la retoma. Oferta nunca penalizada sin verificar.
- **RN-11**: evento `oferta_duplicada` con `id_oferta` de la copia y evidencia con porcentajes y original.
- **RN-12**: no se sobrescribe `ofertas_descubiertas.id_corrida` (sigue siendo la corrida de descubrimiento; la trazabilidad de preparación vive en `eventos`).

### Validaciones
- **VAL-01**: umbrales válidos (0 ≤ umbral ≤ 100) y presentes.
- **VAL-02**: pendientes y universo consultados; sin ofertas duplicadas en el universo.
- **VAL-03**: índice de etapa 1 construido por `(titulo_normalizado, empresa_id)`.
- **VAL-04**: escritura por oferta respeta D31 (evidencia con `N/A` si falta campo).
- **VAL-05**: evento `oferta_duplicada` con `id_oferta` y evidencia acotada.

### Condiciones
- **Normal**: evaluación completa (todas las pendientes con marcador actualizado).
- **Fallo de oferta**: no aborta; oferta queda pendiente para la próxima corrida.
- **Aborto**: insumos ausentes/corruptos; fallo sistémico de BD.

### Ramas
- Normal única → `"¿Quedan ofertas en 'descubierta'?"`.
- Aborto → `"Finalizar Proceso"` con `abortada`.

### Errores y eventos

| Código | Error / evento | Reint. | Detección | Registro / acción | Estado |
|---|---|---|:---:|---|---|---|
| ERR-01 | BD indisponible en consulta | Sí | 1-2 | Reintento; si persiste, aborto (`error_critico`) | `abortada` |
| ERR-02 | Fallo persistente de escritura de una oferta | Sí | 4 | Reintento; si persiste, oferta queda pendiente sin verificar y se continúa | continúa |
| ERR-03 | Corrupción del contexto | No | 4 | Evento crítico; aborto | `abortada` |
| EVT-01 | `oferta_duplicada` | No | 4 | Suceso con `id_oferta` (la copia) y evidencia "% título | % descripción | original" | continúa |

**Contrato de códigos**: `oferta_duplicada` (suceso). Sin errores de red posibles (nodo 100 % local).

### Escenarios límite
- Duplicado dentro del lote actual (Módulo 1 capturó dos veces la misma oferta) → se detecta porque el universo incluye el lote actual.
- Cadenas evitadas: las `duplicada` nunca son candidatas; X apunta siempre al original.
- Original ya `duplicada` en una corrida anterior → no es candidata (RN-05).
- Corrida anterior falló a mitad de la verificación → sus pendientes (`fecha_ultima_verificacion = ''`) se re-verifican (idempotente).
- Título truncado de tarjeta vs. `<h1>` → la etapa 2 difusa cubre variantes; etapa 1 exige identidad exacta.
- Descripción `N/A` → sin candidato de etapa 2 (RN-08).
- Coste: etapa 1 indexada (O(1)); peor caso ~40 000 comparaciones difusas ≈ segundos.

### Dependencias y contratos
- **Antecesor**: `"Preparación de ofertas"`.
- **Sucesor normal**: `"¿Quedan ofertas en 'descubierta'?"`.
- **Sucesor de aborto**: `"Finalizar Proceso"`.
- **Contratos consumidos**: ofertas `preparada` con `titulo` (fiel), `empresa_id` y `descripcion_original` (capturada por Preparación — el Módulo 1 no la captura, D28/D29).
- **Contratos entregados**: ofertas `duplicada` con `id_duplicidad` y evidencia; marcador `fecha_ultima_verificacion` actualizado; eventos `oferta_duplicada`.
- **Impactos aprobados**:
  - `"¿Quedan ofertas en 'descubierta'?"` decide el bucle sobre lo que quedó sin preparar.
  - `"Finalizar Proceso"` cuenta métricas por eventos (`oferta_preparada`/`oferta_duplicada`).

### Notas de implementación
- RapidFuzz ya está en el proyecto (`shared/decision_engine.py`).
- `normalizar_texto` compartida con Preparación (Nodo 2 → `empresas.nombre_normalizado`; este nodo → títulos).
- Umbrales desde configuración; sin valores fijos.
- Reintentos vía `ejecutar_con_reintento` (`shared/retry.py`).
- `shared/models.py`: `OfferState.DUPLICADA`; `shared/state_machine.py`: transición `preparada → duplicada` (la transición `descubierta → preparada` ya existe).
- No re-verificar ofertas con marcador; idempotencia natural.

### Pasos funcionales
1. **Leer insumos**. Entrada: BD, umbrales. Proceso: acceder a configuración y conexión. Salida: insumos. Val: VAL-01. Err: ERR-01.
2. **Consultar pendientes y universo**. Entrada: BD. Proceso: SELECT pendientes (`preparada` con `fecha_ultima_verificacion = ''`) y universo (`preparada` con `id_duplicidad = 'N/A'`). Salida: conjuntos. Val: VAL-02. Err: ERR-01.
3. **Construir índice de etapa 1**. Entrada: universo. Proceso: índice en memoria por `(titulo_normalizado, empresa_id)`. Salida: índice. Val: VAL-03. Err: ERR-03.
4. **Evaluar por oferta**. Entrada: pendientes, índice, umbrales. Proceso: por X: etapa 1 (exacta) → si no, etapa 2 (difusa, ambas umbrales); resultado: duplicado o no. Salida: resultados. Err: ERR-01, ERR-03.
5. **Escribir resultado**. Entrada: resultados, `id_corrida`. Proceso: duplicado → `duplicada` + `id_duplicidad` + `observaciones` + `oferta_duplicada` + marcador; no duplicado → solo marcador. Reintento por oferta; persiste → pendiente. Salida: ofertas actualizadas. Val: VAL-04, VAL-05. Err: ERR-02.
6. **Entregar control**. Entrada: contexto. Proceso: cerrar nodo. Salida: flujo a la decisión de bucle. Err: ninguna.

---

## Nodo decisión: “¿Quedan ofertas en 'descubierta'?”
**Versión**: 1.0 (aprobada)

### Posición
Punto único de control del bucle de pasadas, entre `"Verificación de duplicidad"` y:
- **Sí** → `"Preparación de ofertas"` (siguiente pasada);
- **No** → `"Finalizar Proceso"`.

### Objetivo
Decidir si quedan ofertas en `descubierta` tras la preparación y la verificación, dando recuperación dentro de la misma corrida. Es un **nodo de decisión pura con única excepción**: consulta la BD (a diferencia de las demás decisiones, que solo leen contexto) — justificado porque cada pasada debe ver el estado real de lo que quedó.

### Descripción funcional
Consulta la BD (SELECT de `ofertas_descubiertas` en `descubierta`). Evalúa:
```text
quedan_descubierta == true  y  pasadas < max_pasadas
```
- **Sí** → control a Preparación (incrementa pasadas).
- **No, quedan pero se alcanzó `max_pasadas`** → cierre normal: escribe el evento `revision_pendientes` (pasadas, pendientes para la próxima corrida) y control a `"Finalizar Proceso"`.
- **No, no quedan** → escribe `revision_pendientes` (pasadas=1, pendientes=0 si no hubo bucle) y control a `"Finalizar Proceso"`.

El evento `revision_pendientes` se escribe **siempre** al cerrar el bucle (trazabilidad uniforme entre corridas).

### Entradas
- BD: `ofertas_descubiertas` (conteo `descubierta`).
- Contexto: `max_pasadas`, pasadas acumuladas, `id_corrida`.

### Salidas
- **Sí** → Preparación con pasadas + 1.
- **No** → `"Finalizar Proceso"` con evento `revision_pendientes`.
- **Aborto** → `"Finalizar Proceso"` con `abortada` (`error_critico`).

### Reglas de negocio
- **RN-01**: el bucle solo vuelve a Preparación mientras haya `descubierta` y no se supere `max_pasadas`.
- **RN-02**: las ofertas `preparada`/`duplicada` nunca se reprocesan en pasadas posteriores.
- **RN-03**: al agotar `max_pasadas`, las ofertas que siguen `descubierta` quedan para la próxima corrida (auto-reparación entre corridas; FIFO de INICIO).
- **RN-04**: este nodo no accede a LinkedIn ni a páginas de ofertas (eso es del nodo Preparación).
- **RN-05**: este nodo consulta la BD — única decisión con I/O del módulo; sin ella, el bucle no podría observar el estado real por pasada.
- **RN-06**: no captura, no verifica, no escribe catálogos; solo consulta, cuenta pasadas y decide.
- **RN-07**: el total de intentos por oferta = `max_attempts` × `max_pasadas` (ambos configurables).

### Validaciones
- **VAL-01**: contexto con `max_pasadas` y pasadas coherentes.
- **VAL-02**: conteo entero ≥ 0.
- **VAL-03**: Sí solo con pendientes > 0 y pasadas < `max_pasadas`.
- **VAL-04**: en rama No, `revision_pendientes` escrito antes de entregar control.

### Condiciones y ramas
- **Sí**: quedan `descubierta` y pasadas < `max_pasadas`.
- **No**: sin pendientes, o pendientes con `max_pasadas` agotado.
- **Aborto**: contexto corrupto; fallo persistente de BD.

### Errores y eventos

| Código | Error / evento | Reint. | Detección | Registro / acción | Estado |
|---|---|---|:---:|---|---|---|
| ERR-01 | Falla al consultar `descubierta` (BD) | Sí | 1 | Reintento; si persiste, aborto (`error_critico`) | `abortada` |
| ERR-02 | Se alcanzó `max_pasadas` con pendientes | No | 2 | Cierre normal con `revision_pendientes` | continúa → `"Finalizar Proceso"` |
| EVT-01 | `revision_pendientes` | No | 2 | Suceso con pasadas y pendientes para la próxima corrida (siempre al cerrar el bucle) | continúa |

**Contrato de códigos**: `revision_pendientes` (suceso).

### Escenarios límite
- Oferta permanentemente rota (página borrada/404) → reintentada cada pasada; tras `max_pasadas` queda `descubierta` para la próxima corrida (no bucle infinito).
- Corte de red transitorio en la pasada 1 → la pasada 2 la recupera dentro de la misma corrida.
- Sin pendientes desde el inicio → una pasada y cierre con `revision_pendientes` (pasadas=1, pendientes=0).
- Fallo sistémico de BD → ERR-01 → `error_critico`.

### Dependencias y contratos
- **Antecesor**: `"Verificación de duplicidad"`.
- **Sucesor Sí**: `"Preparación de ofertas"` (que re-consulta su lote por pasada).
- **Sucesor No**: `"Finalizar Proceso"`.
- **Impactos aprobados**: Preparación re-consulta la BD en cada pasada (no usa iterador congelado); `"Finalizar Proceso"` consume el evento `revision_pendientes` en las métricas de éxito.

### Notas de implementación
- Única decisión con I/O; las demás son de evaluación pura sobre contexto.
- `max_pasadas` es configuración, no esquema.
- Refinamiento futuro anotado (no se construye ahora): contador por oferta (`intentos_fallidos`) para dejar de reintentar ofertas permanentemente rotas.

### Pasos funcionales
1. **Consultar pendientes**. Entrada: BD, contexto. Proceso: SELECT conteo de `descubierta`; reintento si falla. Salida: conteo. Val: VAL-02. Err: ERR-01.
2. **Evaluar condición**. Entrada: conteo, pasadas, `max_pasadas`. Proceso: `pendientes > 0 y pasadas < max_pasadas`. Salida: Sí/No. Val: VAL-01, VAL-03. Err: ninguna.
3. **Rama Sí**. Entrada: Sí. Proceso: incrementar pasadas; entregar control. Salida: flujo a Preparación. Err: ninguna.
4. **Rama No**. Entrada: No, `id_corrida`. Proceso: escribir `revision_pendientes` (pasadas, pendientes) y entregar control. Salida: flujo a `"Finalizar Proceso"`. Val: VAL-04. Err: ERR-02.

---

## Nodo terminal: “Finalizar Proceso”
**Versión**: 1.0 (aprobada)

### Identificación
Punto de convergencia de todas las terminaciones de la corrida. Espejo de `"Finalizar Proceso"` del Módulo 1 (`modules/discovery/nodes/finalizar.py`), con dos diferencias: métricas por eventos y nuevos motivos de terminación. *(As-built D40: el enriquecimiento del catálogo no existe en ninguna parte del flujo — el antiguo paso 6 fue retirado primero por D39 y su sucesor inline eliminado por D40.)*

### Objetivo
Cerrar la corrida de preparación de forma determinista y con trazabilidad completa:
1. consultar métricas por eventos;
2. escribir evento de terminación;
3. persistir cierre de corrida;
4. cerrar recursos abiertos;
5. liberar bloqueo de concurrencia si esta corrida lo posee;
6. *(retirado por D39/D40)* enriquecer el catálogo de empresas — el enriquecimiento ya no existe en el proyecto.

### Descripción funcional (pasos en orden obligatorio)

| # | Paso | Qué hace | Fuente |
|---|---|---|---|
| 1 | **Consultar métricas** | Contar por eventos de la corrida: `total_preparadas`, `total_duplicadas`, `total_errores`, `total_sucesos` | `eventos` |
| 2 | **Escribir evento de terminación** | Suceso o error según el motivo; evidencia con métricas (`campo=valor`) | `eventos` |
| 3 | **Persistir cierre de corrida** | `actualizar_corrida`: estado, `fecha_fin`, `motivo_terminacion`, métricas (1 reintento, nunca aborta) | `corridas` |
| 4 | **Cerrar recursos** | Cerrar la sesión HTTP reutilizada de Preparación (best-effort) | — |
| 5 | **Liberar bloqueo** | `liberar_bloqueo(id_corrida)` — solo si la corrida lo posee | `bloqueo` |
| 6 | **Enriquecer catálogo de empresas** *(retirado: H2 en origen, movido por D39 al paso 2 y eliminado definitivamente por D40)* | Ya no existe en el proyecto | — |

### Entradas
Contexto best-effort:
- motivo/estado de terminación: `sin_pendientes`, `corrida_completada`, `error_total`, `error_critico`, `aborto`, `concurrencia`;
- `id_corrida`; `hubo_candidatas` (bool, del INICIO);
- sesión HTTP abierta, si existe;
- estado de bloqueo; conexión de BD.

### Salidas
- Evento de terminación persistido en `"errores o sucesos"` o registro crítico local si falla escritura.
- Corrida cerrada (`corridas` con estado, `fecha_fin`, motivo y métricas).
- Recursos cerrados; bloqueo liberado si esta corrida lo poseía.
- El catálogo `empresas` no se enriquece en ninguna parte del flujo *(retirado definitivamente por D40)*.
- Sin sucesor: fin del proceso.

### Ramas
No es nodo de decisión.

### Estados/motivos oficiales

| Motivo | Cuándo | Estado `corridas` | Tipo de evento |
|---|---|---|---|
| `sin_pendientes` | Sin ofertas candidatas (INICIO/decisión de candidatas lo detectó) | `sin_pendientes` | suceso |
| `corrida_completada` | ≥ 1 oferta preparada o duplicada | `completada` | suceso |
| `error_total` | `hubo_candidatas` = sí pero todas fallaron (0 éxitos + ≥ 1 error) | `abortada` | error |
| `error_critico` | Fallo crítico de BD/config en cualquier nodo | `abortada` | error |
| `aborto` | Fallo de un nodo en el flujo | `abortada` | error |
| `concurrencia` | INICIO ERR-06 (no obtuvo el bloqueo global) | `abortada` | suceso |

**Fuente del dato:** `hubo_candidatas` (bool) lo registra el INICIO en el contexto; el paso 1 lo usa para distinguir `error_total` de `sin_pendientes`.

**Justificación de `error_total` → `abortada` (confirmado):** con todas las ofertas fallidas en una corrida, la red o LinkedIn está bloqueada y conviene la señal de alerta (el usuario revisa), en vez de un "completada" engañoso.

### Métricas (por eventos, decisión del nodo Verificación)

- `total_preparadas` = `contar_filas(eventos, {id_corrida, codigo='oferta_preparada'})`.
- `total_duplicadas` = `contar_filas(eventos, {id_corrida, codigo='oferta_duplicada'})`.
- `total_errores` = `contar_filas(eventos, {id_corrida, tipo='error'})`.
- `total_sucesos` = sucesos escritos **antes** del evento de terminación (semántica D30 intacta: el evento de cierre nunca se cuenta).
- `total_ofertas` = unión DISTINCT de ofertas únicas entre los eventos `oferta_preparada` y `oferta_duplicada` vía `contar_distintos` (D45; sustituye la fórmula literal `total_preparadas + total_duplicadas`) — comparable entre módulos.

No se sobrescribe `ofertas_descubiertas.id_corrida` (sigue siendo la corrida de descubrimiento; la trazabilidad de preparación vive en `eventos`).

### Decisiones de diseño

| Decisión | Alternativas | Recomendación y justificación |
|---|---|---|
| Contenido del evento de terminación | A. Minimal: `id_corrida`, marca_temporal, estado, motivo, métricas (`campo=valor`). B. Resumen completo. | **A**: el detalle ya existe en eventos por nodo; duplicar resúmenes acopla y ensucia. |
| Métricas | A. Por ofertas (`contar_filas(ofertas_descubiertas, {id_corrida})`, patrón Módulo 1). B. Por eventos. | **B**: `id_corrida` de la oferta no se sobrescribe; las métricas de preparación solo existen en `eventos`. |
| Liberación del bloqueo | A. Incondicional. B. Condicional a propiedad: propietario == `id_corrida`. | **B**: en la ruta `concurrencia` esta corrida no posee el bloqueo; liberarlo rompería la corrida activa. |
| Fallo de liberación del bloqueo | A. Aborto/error fatal. B. Reintento único + registro local + continuar. | **B**: ya en terminación; la obsolescencia del bloqueo auto-sana en la próxima corrida. |
| Contexto corrupto al llegar | A. Aborto sin cierre. B. Cierre best-effort con motivo por defecto. | **B**: el productor ya escribió el evento crítico; Finalizar debe intentar liberar/cerrar con lo disponible. |
| Limpieza de recursos | A. Implícita por fin de proceso. B. Cierre explícito best-effort. | **B**: la sesión HTTP/navegador puede sobrevivir según implementación; cierre explícito evita fugas. |
| Enriquecimiento desacoplado | A. Antes de liberar el bloqueo. B. Después de liberar (paso 6). C. Fuera de la corrida. | **B** al construirse; **superado por D39** (en línea, paso 2); **eliminado por D40**: el enriquecimiento ya no existe en el proyecto — esta tabla conserva la decisión histórica. |

### Especificación funcional
1. **Consultar métricas**. Entrada: `eventos`, `id_corrida`, `hubo_candidatas`. Proceso: contar por eventos (paso 1); decidir motivo según tabla oficial (si `hubo_candidatas` y 0 éxitos y ≥ 1 error → `error_total`). Salida: métricas + motivo. Excepción: fallo de conteo → reintento único; si persiste, motivo por defecto `aborto` con métricas vacías y continuar.
2. **Escribir evento de terminación**. Entrada: estado, motivo, `id_corrida`, métricas. Proceso: suceso o error según motivo con evidencia `campo=valor`; fallo → reintento único; si persiste, registro crítico local y continuar. Salida: evento persistido o registro local. Excepción: fallo tras reintento no aborta.
3. **Persistir cierre de corrida**. Entrada: estado, motivo, métricas. Proceso: `actualizar_corrida` (estado, `fecha_fin`, `motivo_terminacion`, `total_preparadas`, `total_duplicadas`, `total_ofertas`, `total_sucesos`, `total_errores`); 1 reintento; nunca aborta. Salida: corrida cerrada. Excepción: fallo tras reintento → registro local y continuar.
4. **Cerrar recursos (best-effort)**. Entrada: sesión HTTP; conexión BD. Proceso: cerrar; errores se registran localmente y no impiden terminación. Salida: recursos cerrados. Excepción: errores de cierre no abortan.
5. **Liberar bloqueo si corresponde**. Entrada: estado de bloqueo, `id_corrida`. Proceso: si el bloqueo existe y el propietario == `id_corrida`, liberar; fallo → reintento único; si persiste, registro local y continuar; si no propietario, sin acción. Salida: bloqueo liberado o sin acción. Excepción: fallo tras reintento no aborta.
6. **Enriquecer catálogo de empresas** *(retirado definitivamente por D40)*. Ya no existe en el proyecto; el nodo termina tras liberar el bloqueo.
7. **Terminar proceso**. Entrada: —. Proceso: cerrar nodo. Salida: fin de corrida. Excepción: ninguna.

### Puntos de aprobación
- Conjunto oficial de motivos/estados y tipo de evento (tabla de estados/motivos).
- Métricas por eventos; `total_ofertas` = unión DISTINCT de ofertas únicas (D45); semántica D30.
- `hubo_candidatas` como fuente del dato para `error_total` vs `sin_pendientes`.
- Liberación de bloqueo condicional a propiedad; fallo cubierto por obsolescencia.
- Cierre best-effort ante contexto corrupto; cierre explícito de recursos.
- Enriquecimiento del catálogo eliminado del proyecto *(D40)*.

### Dependencias y contratos
- **Antecesores**: rama No de la decisión de candidatas (`sin_pendientes`); rama No de la decisión de bucle; abortos de cualquier nodo (`error_critico`/`aborto`); INICIO ERR-06 (`concurrencia`).
- **Sucesor**: ninguno (fin del proceso).
- **Contratos consumidos**: `id_corrida`, `hubo_candidatas`, motivo/estado, recursos abiertos, estado de bloqueo.
- **Impactos aprobados**: `corridas` con `total_preparadas`/`total_duplicadas` (D3) y estado `sin_pendientes` (decisión de INICIO); el bloqueo global se libera para la siguiente corrida de cualquier módulo.

### Notas de implementación
- Espejo de `finalizar_proceso` del Módulo 1: `_ESTADOS_POR_MOTIVO` ampliado (`sin_pendientes`, `completada`, `abortada`), `cerrar_recursos` público y reutilizable, liberación condicional a propiedad.
- Métricas por SQL (`contar_filas` sobre `eventos`), no por tablas completas.
- Semántica D30: el evento de terminación nunca se cuenta en `total_sucesos`.
- Best-effort en todo el cierre: ningún error del paso 1-6 aborta.
- **As-built D40 (2026-08-25):** el enriquecimiento fue eliminado del proyecto — el antiguo paso 6 H2 había sido retirado por D39 (movido al paso 2) y su sucesor inline fue revertido por D40 tras medirse como cuello de botella (~96% de una corrida completa); el nodo termina tras liberar el bloqueo.

### Estado del módulo
Con este nodo queda completo el conjunto de nodos del Módulo 2 (INICIO, "¿Quedan ofertas por preparar…?", Preparación de ofertas, Verificación de duplicidad, "¿Quedan ofertas en 'descubierta'?", Finalizar Proceso). Pendientes de implementación: todos — este documento es la base autoritativa de construcción, derivada del `Plan funcional fase 5` (decisiones D1-D5, correcciones, H1-H7 y optimizaciones aprobadas). El orquestador transversal (`modules/orchestrator/`, capa separada de este módulo) se construirá al cierre del Módulo 2 con prueba real de corrida secuencial 1→2 — especificado en su propia ficha técnica: `docs/diagrams/Ficha técnica - Diagrama de flujo (Orquestador transversal).md`.

---

## Dependencias de esquema (migraciones necesarias — consolidadas)

1. `ofertas_descubiertas.estado` CHECK: añadir `duplicada` (D1).
2. `ofertas_descubiertas`: añadir columna `id_duplicidad` (D2).
3. `ofertas_descubiertas`: añadir columnas `ubicacion_nombre` y `modalidad` (reversión parcial de D29, documentada). *(As-built D45: la columna se renombró a `ubicacion` y su captura se trasladó al Módulo 1.)*
4. `corridas`: añadir columnas `total_preparadas` y `total_duplicadas` (D3).
5. `eventos`: re-añadir columna `id_oferta` (`N/A` en eventos de módulo; respeta D31).
6. `ubicaciones`: eliminar `nombre`, `nombre_normalizado`, `modalidad`; conservar `ciudad`, `region`, `pais` (rediseño aprobado).
7. `shared/models.py`: `OfferState.DUPLICADA`, `EstadoCorrida.SIN_PENDIENTES`, `Corrida` con `total_preparadas`/`total_duplicadas`, `EventoAlmacen` con `id_oferta`, `Location` sin `modalidad`.
8. `shared/state_machine.py`: transición `preparada → duplicada` (`descubierta → preparada` ya existe).
9. `shared/utilidades.py`: nueva función `normalizar_texto`.
10. `config/config.yaml`: sección nueva `preparacion:` (`umbral_titulo: 90`, `umbral_descripcion: 85`, `max_pasadas: 2`, `pausa_entre_ofertas_segundos`, `limite_vida_sesion`, reintentos) y `ai_routing.preparacion`. *(As-built D40: las claves de enriquecimiento `profundidad_catalogo_empresa` y `pausa_entre_empresas_segundos` fueron retiradas.)*
11. `prompts/`: prompt de clasificación de ubicación (`prompts/preparacion/ubicacion.md`).