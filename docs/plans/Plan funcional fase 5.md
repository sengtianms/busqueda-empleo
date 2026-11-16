# Plan funcional fase 5

> **Documento histórico.** Conservado como registro del diseño con el que se construyó la fase 5. Superado por la ficha técnica del Módulo 2 v2.0 y por la decisión D77 (2026-11-15): la ubicación ya no se clasifica con inteligencia artificial y el módulo no crea ni corrige filas del catálogo.

## Orquestador de automatización (capa transversal)

Decisiones tomadas para construir el orquestador que lanza los módulos en orden y supervisa su terminación. Se construye al cierre del Módulo 2.

**Ficha técnica autoritativa:** [`docs/diagrams/Ficha técnica - Diagrama de flujo (Orquestador transversal).md`](../diagrams/Ficha%20técnica%20-%20Diagrama%20de%20flujo%20(Orquestador%20transversal).md) (D34, 2026-08-20).

### Objetivo
Ejecutar los módulos en el orden del pipeline (Módulo 1 → Módulo 2 → …) sin que se conozcan entre sí: **el orquestador solo lanza y supervisa**. No gestiona tablas ni lógica de negocio (eso es de los nodos).

### 1. Decisiones de construcción
- **Capa transversal nueva:** `modules/orchestrator/`, independiente de los módulos funcionales.
- **Estructura del Módulo 2 (H6):** `modules/preparation/` (carpeta en inglés, convención del proyecto) con `orchestrator.py` interno + `nodes/` en español (espejo del Módulo 1): `inicio.py`, `preparar.py`, `duplicidad.py`, `revision.py`, `finalizar.py`. El orquestador transversal solo invoca `ejecutar_flujo()` del módulo.
- **Construcción incremental (Opción A):** se crea el esqueleto al cierre del Módulo 2, con **prueba real de corrida secuencial 1→2** (Módulo 1 ejecutado, luego Módulo 2, ambos contra la BD real).
- **Contrato con cada módulo:** cada módulo expone una función pública `ejecutar_flujo()` + metadatos (nombre, estado de entrada, estado de salida). El orquestador lanza en orden, **espera la terminación** de cada uno y **registra el resultado** de la corrida programada.
- **Basado en el patrón ya existente:** el Módulo 1 ya tiene su orquestador interno (`modules/discovery/orchestrator.py`, 12 nodos con `ejecutar_flujo()`); la capa transversal lo envuelve y coordina los módulos entre sí.
- **Sin valores fijos en el código:** comportamiento configurable (`modo_ejecucion`, pausas) vía configuración central.

### 2. Coordinación por base de datos
- Los módulos **no se conocen entre sí**: cada uno lee su estado de entrada de la BD y escribe su estado de salida.
- Módulo 1: escribe `descubierta`. Módulo 2: lee `descubierta` y escribe `preparada`/`duplicada`.
- Esta coordinación por estados hace que cada módulo sea **auto-reparable**: si una corrida falla a medias, la siguiente ejecución retoma desde el estado que quedó.

### 3. Modelo de ejecución
- **En serie por defecto (recomendado):** cada módulo procesa todo lo que hay de su estado y termina con su evento de terminación; el siguiente arranca después.
- **Paralelo (tubería):** solo se documenta como opción futura (`modo_ejecucion: serie | paralelo`); **no se implementa hoy** — requiere los 5 módulos para probarse y obligaría a revisar el bloqueo global (hoy solo una ejecución activa a la vez en todo el pipeline).

### 4. Fuera de alcance hoy (decidido)
- **Horarios de ejecución:** no se construyen (es trivial añadirlos después; hoy el disparo es manual).
- **Modo paralelo:** no se construye (imposible de probar con 2 módulos).

### 5. Fin de la automatización
- La automatización termina cuando **todos los módulos terminaron sus corridas**, cada una con su evento de terminación en `eventos`.
- El orquestador registra el **resumen de la corrida programada** (módulos ejecutados, estados resultantes) como trazabilidad.

### 6. Relación con la IA
- **La IA no la "arranca" el orquestador:** es un servicio invocado **bajo demanda por los nodos** que la necesitan (p. ej. el Nodo 2 para clasificar ubicaciones).
- El orquestador no conoce ni gestiona la IA; solo supervisa módulos.

---

## Decisiones globales del Módulo 2 (Preparación de ofertas)

Decisiones macro tomadas antes del análisis nodo por nodo; cada nodo las consume y las concreta.

**Ficha técnica autoritativa:** [`docs/diagrams/Ficha técnica - Diagrama de flujo (Preparación de ofertas).md`](../diagrams/Ficha%20técnica%20-%20Diagrama%20de%20flujo%20(Preparación%20de%20ofertas).md) (D33, 2026-08-20).

### D1 — Estado `duplicada`
- Se añade el estado **`duplicada`** (terminal) al vocabulario de `ofertas_descubiertas`.
- El Módulo 2 deja cada oferta en `preparada` (éxito) o `duplicada` (duplicada de otra ya existente).
- `procesada` queda reservada para el final del pipeline (fases posteriores).

### D2 — Columna `id_duplicidad`
- Nueva columna en `ofertas_descubiertas` que **apunta a la oferta original**.
- Varias copias apuntan al mismo original (el `id` de la oferta que se conserva); el original queda en `preparada`.

### D3 — Corrida propia del módulo
- El Módulo 2 tiene **su propia corrida**: `id_corrida` propio, **mismo bloqueo global de concurrencia** que el Módulo 1, y métricas propias.
- Dos columnas nuevas en `corridas`: **`total_preparadas`** y **`total_duplicadas`**.

### D4 — Captura de empresa (validada empíricamente)
- Investigación real (Playwright + httpx, agosto 2026): las **ofertas son capturables sin login** (10+ visitas consecutivas sin muro); los **perfiles de empresa** disparan el muro de login tras ~7-10 visitas en el mismo navegador.
- Estrategia ganadora: **httpx con sesión de invitado fresca por empresa** (~0,9 s por perfil, 6/6 sin muro) con **fallback automático al navegador fresco por empresa** (6/6 sin muro).
- El **enriquecimiento profundo** (web, sector, tamaño, descripción) queda **desacoplado del camino crítico**, por lotes y configurable (`profundidad_catalogo_empresa`).
- Proyección de tiempos: 200 ofertas ≈ 3-5 min en total; 150 empresas ≈ 2-3 min.

### D5 — Capturar primero, verificar después (dos etapas)
- **Orden obligatorio:** captura de datos primero, verificación de duplicidad después.
- La verificación se hace en **dos etapas**: (1) **título normalizado + empresa**; (2) **descripción** con similitud difusa (RapidFuzz).

### Alcance transversal
- El Módulo 2 **no usa IA** para captura, empresas, modalidad ni duplicidad.
- La IA se usa **únicamente** para clasificar la ubicación en el Nodo 2 (servicio invocado bajo demanda; el nodo dirige la BD).

---

# Nodo 1 — INICIO (Arranque de la corrida)

## Objetivo
Instanciar la corrida de preparación y preparar el contexto de ejecución: trazabilidad, configuración validada, BD disponible, concurrencia, ofertas candidatas y estado inicial. **No captura datos ni verifica duplicidad** (eso corresponde a los Nodos 2 y 3).

---

## 1. Flujo funcional (orden obligatorio, espejo del Módulo 1)

| # | Paso | Qué hace | Depende de |
|---|---|---|---|
| 1 | **Recibir disparador e instanciar corrida** | Crear `id_corrida` único + `fecha_inicio` (corrida propia del módulo, decisión D3) | — |
| 2 | **Cargar configuración y validar nivel global** | Políticas de preparación (sección `preparacion:` **completa**): `profundidad_catalogo_empresa`, `umbral_titulo`, `umbral_descripcion`, `max_pasadas`, `pausa_entre_ofertas_segundos`, `limite_vida_sesion`, reintentos | Paso 1 |
| 3 | **Verificar BD** | Conexión + prueba de escritura con rollback | Paso 2 |
| 4 | **Validar concurrencia** | Bloqueo persistente **global compartido** con el Módulo 1 | Paso 3 |
| 5 | **Cargar ofertas candidatas** | SELECT de `ofertas_descubiertas` con estado `descubierta`, **orden FIFO** (más antiguas primero) | Paso 3 |
| 6 | **Inicializar estado** | Iterador de candidatas + contadores (`preparadas`, `duplicadas`, `errores`) + **`hubo_candidatas` (bool)** en el contexto (lo consume el Nodo 5 para distinguir `error_total` de `sin_pendientes`) | Paso 5 |
| 7 | **Entregar control** | Al nodo siguiente (decisión "¿Quedan ofertas por preparar?") | Paso 6 |

**Si no hay candidatas:** el nodo siguiente resuelve la terminación `sin_pendientes` (sin trabajo, sin riesgo, en segundos).

---

## 2. Decisiones específicas del Nodo 1

### 2.1 Disparador — manual hoy, automatizable mañana
- **Hoy (MVP):** disparo **manual** (el usuario lanza el módulo).
- **Condición interna obligatoria:** al arrancar se evalúa "¿existe ≥1 oferta en `descubierta`?" — si no, termina al instante con `sin_pendientes`.
- **Futuro:** la automatización lanzará el módulo en horarios programados; la condición interna es la misma, por lo que **no se acopla al Módulo 1** (un fallo intermedio de una corrida se retoma solo en la siguiente ejecución).

### 2.2 Bloqueo de concurrencia — global compartido
- **Un solo bloqueo persistente** para todo el pipeline: mientras corre el Módulo 1 no puede correr el Módulo 2 y viceversa.
- Elimina carreras de escritura sobre `ofertas_descubiertas`. Mecanismo idéntico al Módulo 1 (bloqueo obsoleto → sobrescribir y continuar).

### 2.3 Terminación sin pendientes — estado nuevo aprobado
- **Nuevo estado en el vocabulario de `EstadoCorrida`:** `sin_pendientes` (junto a `en_ejecucion`, `completada`, `sin_fuentes`, `abortada`).
- Análogo a `sin_fuentes` del Módulo 1: distingue una corrida sin trabajo de una corrida que sí preparó ofertas (`completada`).

### 2.4 Límite por corrida — sin límite (aprobado)
- La corrida procesa **todas** las ofertas en `descubierta` (sin `max_ofertas_por_corrida`).
- El tiempo queda acotado por las pausas configuradas y el enriquecimiento desacoplado (decisión D4).

### 2.5 Selección de candidatas — FIFO
- **Más antiguas primero** (`fecha_descubrimiento ASC, id ASC`): las ofertas fallidas de corridas previas quedaron en `descubierta` y **vuelven a intentarse** en orden.
- **Cada pasada re-consulta la BD:** el Nodo 2 consulta su lote al inicio de cada pasada del bucle (Nodo 4); el iterador del Nodo 1 es solo el del arranque y no se congela entre pasadas.

---

## 3. Reglas de negocio

- **RN-01:** toda corrida tiene `id_corrida` único; todo registro del módulo queda enlazado a él.
- **RN-02:** solo una ejecución activa a la vez (bloqueo global compartido).
- **RN-03:** el iterador de candidatas se reinicia al inicio de cada corrida; dentro de la corrida, cada pasada del bucle (Nodo 4) re-consulta la BD en lugar de reutilizar un iterador congelado.
- **RN-04:** este nodo no valida si hay ofertas pendientes; esa validación es del nodo siguiente (decisión "¿Quedan ofertas por preparar?").
- **RN-05:** este nodo no accede a LinkedIn ni a páginas de ofertas (eso es del Nodo 2).

---

## 4. Errores y excepciones (espejo del Módulo 1, numeración propia)

| Código | Error / excepción | Acción | Estado |
|---|---:|---|---|
| ERR-01 | Colisión o fallo de generación de `id_corrida` | Reintento único; si persiste, aborto | `abortada` |
| ERR-02 | Configuración ausente | Aborto | `abortada` |
| ERR-03 | Configuración ilegible | Aborto | `abortada` |
| ERR-04 | Configuración corrupta / estructura inconsistente | Aborto | `abortada` |
| ERR-05 | BD indisponible / bloqueada / sin permisos | Aborto | `abortada` |
| ERR-06 | Concurrencia activa | Terminación controlada | `concurrencia` |
| ERR-07 | Bloqueo obsoleto (antigüedad > umbral) | Sobrescribir bloqueo y continuar | continúa |
| ERR-08 | Estado de bloqueo no decidible | Aborto | `abortada` |
| ERR-09 | Contienda de adquisición de bloqueo | Perdedor cae en ERR-06 | `concurrencia` |
| ERR-10 | Falla interna de inicialización de estado | Aborto | `abortada` |

---

## 5. Contrato de integración con la automatización (futuro)

- **Coordinación por base de datos:** los módulos no se conocen entre sí; cada uno lee su estado de entrada de la BD y escribe su estado de salida. El Módulo 2 lee `descubierta` y escribe `preparada`/`duplicada`.
- **Modelo de ejecución:** en serie por defecto (recomendado): cada módulo procesa todo lo que hay de su estado y termina con su evento de terminación; el siguiente arranca después. La **tubería (paralelismo real)** queda como opción futura configurable (`modo_ejecucion: serie | paralelo`) — no se implementa hoy (requiere los 5 módulos para probarse y revisa el bloqueo global).
- **Fin de la automatización:** cuando todos los módulos terminaron sus corridas, cada una con su evento de terminación en `eventos`; el orquestador registra el resumen de la corrida programada.
- **El orquestador global** es una capa transversal (`modules/orchestrator/`) que lanza los módulos en orden y supervisa su terminación; no gestiona tablas ni lógica de negocio. Se construye **incrementalmente** al cierre del Módulo 2, con prueba real de corrida secuencial 1→2.

---

## 6. Dependencias de esquema (migraciones necesarias)

1. `corridas`: añadir columnas `total_preparadas` y `total_duplicadas` (decisión D3).
2. `EstadoCorrida`: añadir el valor `sin_pendientes` al vocabulario (decisión aprobada en este nodo).
3. `eventos`: re-añadir columna `id_oferta` (aprobado; `N/A` en eventos de módulo, respeta no-vacíos D31).

---

## 7. Decisiones cerradas que sostienen el Nodo 1 (resumen)
- **Disparador:** manual hoy + condición interna "¿existe ≥1 oferta en `descubierta`?"; automatizable mañana sin acoplamiento al Módulo 1.
- **Bloqueo:** global compartido con el Módulo 1 (una ejecución activa a la vez en todo el pipeline).
- **Terminación:** estado nuevo `sin_pendientes` en `EstadoCorrida`.
- **Límite:** sin límite por corrida (todas las ofertas en `descubierta`).
- **Selección:** FIFO (más antiguas primero); fallidas de corridas previas se reintentan.
- **Orquestador:** capa transversal `modules/orchestrator/`, construida incrementalmente al cierre del Módulo 2 con prueba real de corrida secuencial 1→2.

---

# Nodo 2 — Preparación de ofertas (captura de datos)

## Objetivo
Para cada oferta en estado `descubierta` (iteradas en orden FIFO desde el Nodo 1): capturar la descripción completa desde la página de la oferta (sin login), y poblar los catálogos `empresas` y `ubicaciones`, enlazando la oferta por sus IDs de catálogo. **No verifica duplicidad** (eso corresponde al Nodo 3, en dos etapas según la decisión D5).

**Dos lotes por corrida (decisión H1):** (a) las `descubierta` — captura completa (pasos 1-5); (b) las `preparada` con `ubicacion_id = 'N/A'` (ubicaciones pendientes por IA caída) — solo los pasos 3-5 (clasificar, buscar/crear, actualizar), **sin re-capturar** la página: el texto crudo ya está en `ubicacion_nombre`. El lote (b) corre después del (a), así las ofertas recién preparadas con IA caída se gestionan en la misma pasada.

---

## 1. Flujo por oferta (orden obligatorio, por dependencia natural)

Cada paso necesita el anterior; el orden evita errores y repeticiones:

| # | Paso | Qué hace | Fuente | Depende de |
|---|---|---|---|---|
| 1 | **Capturar la página** | HTTP directo (httpx): extraer **título** (sobrescribe el de la tarjeta), descripción completa, empresa (nombre + link de perfil), modalidad y ubicación cruda | Página de la oferta (`/jobs/view/N`) | — |
| 2 | **Diligenciar empresa** | Upsert en `empresas` (dedup por `nombre_normalizado`, sin IA) → obtener `empresa_id` | Paso 1 | Paso 1 |
| 3 | **Diligenciar ubicación (con IA)** | Clasificar texto crudo → tupla `{ciudad, región, país}` → buscar/crear en `ubicaciones` → `ubicacion_id` (o `N/R` si es remoto) | Paso 1 | Paso 1 |
| 4 | **Actualizar la oferta** | Guardar `descripcion_original`, `empresa_id`, `ubicacion_id`, `modalidad` (NO toca `fecha_ultima_verificacion`: es marcador exclusivo del Nodo 3) | Pasos 2-3 | Pasos 2-3 |
| 5 | **Escribir evento** | `oferta_preparada` (suceso) con `id_oferta` | Paso 4 | Paso 4 |

**En fallo del paso 1:** evento `preparacion_fallida` (error) con `id_oferta` (trazabilidad completa de qué oferta falló) + reintento configurable; si persiste, la oferta permanece en `descubierta` para la próxima corrida. **Todos los eventos de oferta llevan `id_oferta`, éxito y fallo.**

**Título desde la página (decisión confirmada):** el Nodo 2 sobrescribe `titulo` con el título del `<h1>` de la página de la oferta **solo si el `<h1>` existe** (best-effort; nunca deja el campo vacío — regla D31). El Módulo 1 ya lo capturó de la tarjeta del listado (decisión D28; verificado: 136/136 ofertas pobladas), pero el de la tarjeta puede venir truncado — el de la página es más fiel. La columna `titulo` ya existe en `ofertas_descubiertas`; **no requiere migración**.

---

## 2. Decisiones específicas del Nodo 2

### 2.1 Sesión HTTP
- **Sesión reutilizada** para todas las ofertas (las páginas de oferta son permisivas sin login — verificado empíricamente: 10+ navegaciones sin muro).
- **Límite de vida de sesión configurable** (renovar cada N ofertas, p. ej. 50).
- **Fallback de seguridad:** si se detecta muro de login (authwall) → nueva sesión de invitado y se reintenta la oferta.
- **Pausa entre ofertas (H4):** `pausa_entre_ofertas_segundos` configurable (p. ej. 1-2 s) para prudencia anti-bloqueo (ya se detectó `uc=scraping` en la investigación de LinkedIn).

### 2.2 Reintentos por oferta
- **Reintento configurable** dentro de la corrida (número de intentos por oferta).
- Si persiste el fallo → oferta queda en `descubierta` y la próxima corrida la retoma.

### 2.3 Tabla `empresas`
- Upsert por `nombre_normalizado` (dedup): si la empresa ya existe → reutilizar `id`; si no → crear con `nombre` + `perfil_linkedin`.
- **El enriquecimiento profundo (web, sector, tamaño, descripción) NO se hace en este nodo** — lo hace el **paso 6 del Nodo 5** (tarea desacoplada de la decisión D4), con profundidad configurable (`profundidad_catalogo_empresa`).
- **Caché en memoria de la corrida** (simétrica a la de ubicaciones): empresa → `empresa_id`; evita una consulta a BD por oferta repetida (136 ofertas ≈ 60-80 empresas únicas).
- Sin IA.

### 2.4 Tabla `ubicaciones` — rediseño aprobado
**Estructura final:**
```
ubicaciones (
    id,                      -- UBI-xxxx
    ciudad,                  -- 'N/A' si la oferta no la especificó
    region,                  -- 'N/A' si no aplica o no vino
    pais,                    -- 'N/A' si la oferta solo dio ciudad
    fecha_creacion,
    fecha_ultima_edicion
)
```
- **Eliminadas:** `nombre`, `nombre_normalizado`, `modalidad` (decisión del usuario).
- El **texto crudo** de la ubicación va en `ofertas_descubiertas.ubicacion_nombre` (columna nueva; la re-añadimos — reversión parcial justificada de D29, documentada en el decision log).
- La **modalidad** va en `ofertas_descubiertas.modalidad` (columna nueva). Es dato de la oferta; la IA no la toca.

**Reglas de deduplicación (regla del usuario + decisión aprobada):**
- Dedup por **tupla completa** `(ciudad, región, país)` normalizada.
- La IA completa país/región por conocimiento seguro para que las variantes converjan: "Medellín" y "Medellín, Colombia" → misma tupla → mismo registro.
- "Colombia" solo → tupla `(N/A, N/A, Colombia)` → **un único ID compartido por todas las ofertas que digan solo "Colombia"**.
- "Remoto" → **no se crea ubicación**; `ubicacion_id = 'N/R'` (no reporta).

### 2.5 IA para la tabla `ubicaciones`
- **Rol:** clasificar texto únicamente. Recibe el texto crudo y devuelve `{ciudad, región, país}` en JSON validado con Pydantic.
- **La IA no selecciona ofertas, no lee la BD, no escribe, no tiene memoria del catálogo.** Todo eso lo hace el Nodo 2.
- **Regla de completitud:** completa país/región solo si es conocimiento seguro; si no → `N/A`. Nunca inventa datos (regla D31 intacta).
- **Prompt:** vive en `prompts/` (separado del código, convención del proyecto).
- **Optimización (aprobada):** caché en memoria **del contexto de la corrida** (perdura entre pasadas del bucle del Nodo 4) + consulta a la BD por tupla → la IA se invoca **una vez por texto de ubicación distinto** (50-100 llamadas por 200 ofertas, no 200).
- **Robustez:** si la IA falla u Ollama está caído → la oferta se captura igual y queda `ubicacion_id = 'N/A'` (pendiente). **La IA jamás bloquea la captura.**

### 2.6 Mecanismo "¿la IA ya intervino?" — tres estados de `ubicacion_id`
| Valor | Significado |
|---|---|
| `N/A` | Pendiente — la IA aún no la gestionó |
| `N/R` | Gestionada — remoto / ubicación no reportada |
| `ID real (UBI-xxxx)` | Gestionada — ubicación identificada |

La guía/IA revisa todas las ofertas con `ubicacion_id = 'N/A'`, las gestiona y las marca (con ID o `N/R`). Esto da resiliencia: si una corrida captura ofertas y la IA no está disponible, quedan `N/A` y la siguiente corrida las retoma.

### 2.7 División de responsabilidades (confirmada)
| Actor | Responsabilidad |
|---|---|
| **IA** | Solo clasificar texto (recibe el prompt, devuelve la clasificación) |
| **Nodo 2** | Dirige las tablas: consulta, crea, actualiza, escribe eventos |
| **Orquestador** | Lanza los nodos en orden y supervisa la corrida (no gestiona tablas) |

---

## 3. Dependencias de esquema (migraciones necesarias)

1. `ofertas_descubiertas`: añadir `duplicada` al CHECK de `estado` (decisión D1).
2. `ofertas_descubiertas`: añadir columna `id_duplicidad` (decisión D2).
3. `corridas`: añadir columnas `total_preparadas` y `total_duplicadas` (decisión D3).
4. `eventos`: re-añadir columna `id_oferta` (aprobado; `N/A` en eventos de módulo, respeta no-vacíos D31).
5. `ubicaciones`: **eliminar** `nombre`, `nombre_normalizado`, `modalidad`; conservar `ciudad`, `region`, `pais`.
6. `ofertas_descubiertas`: añadir columnas `ubicacion_nombre` y `modalidad`.

---

## 4. Decisiones cerradas que sostienen el Nodo 2 (resumen)
- **D1:** estado `duplicada` (terminal); Módulo 2 deja ofertas en `preparada` o `duplicada`; `procesada` queda para el final del pipeline.
- **D2:** columna `id_duplicidad` apuntando a la oferta original.
- **D3:** corrida propia del módulo, mismo bloqueo global, métricas propias (`total_preparadas`/`total_duplicadas`).
- **D4:** captura de empresa: detalle + perfil vía httpx con sesión fresca (~0,9 s) con fallback a navegador fresco; enriquecimiento desacoplado y configurable (`profundidad_catalogo_empresa`), ejecutado en el paso 6 del Nodo 5; ofertas capturables sin login.
- **D5:** capturar primero, verificar duplicidad después, en dos etapas.
- **Nodo 1:** disparo manual hoy + condición interna "¿existe ≥1 oferta en `descubierta`?"; bloqueo global compartido; estado `sin_pendientes`; sin límite por corrida.
- **Orquestador:** capa transversal `modules/orchestrator/`, construida incrementalmente al cierre del Módulo 2 con prueba real de corrida secuencial 1→2.

---

# Nodo 3 — Verificación de duplicidad

## Objetivo
Detectar, entre las ofertas ya preparadas, cuáles son **la misma oferta publicada dos veces** (misma empresa re-publicando el mismo cargo) y marcarlas como `duplicada` (terminal), apuntando a la oferta original. Nodo **100 % local**: sin IA, sin HTTP, sin catálogos — solo compara datos ya capturados con similitud difusa (RapidFuzz, misma librería que usa la evaluación).

---

## 1. Cuándo corre (flujo del módulo)

1. El Nodo 2 procesa **todas** las `descubierta` → quedan en `preparada` (con título, empresa y descripción ya capturados).
2. El Nodo 3 toma **todas** las `preparada` pendientes de verificación (`fecha_ultima_verificacion = ''`) y verifica duplicidad contra el universo de originales.
3. Duplicadas → `duplicada` + `id_duplicidad`; no duplicadas → se quedan en `preparada`.

## 2. Datos disponibles (sin captura adicional)

| Dato | Columna | Quién lo captura |
|---|---|---|
| Título | `titulo` | Módulo 1 (tarjeta, D28) + Nodo 2 lo sobrescribe con el `<h1>` de la página (ver Nodo 2) |
| Empresa | `empresa_id` | Nodo 2 (catálogo `empresas`) |
| Descripción | `descripcion_original` | **Nodo 2** (captura la página de la oferta; el Módulo 1 no la captura — D28/D29, la columna queda `N/A` hasta aquí) |

---

## 3. Alcance de comparación (decisión confirmada)

Cada oferta X **en verificación** se compara contra **todas** las ofertas en `preparada` con `id_duplicidad = 'N/A'` (los "originales candidatos" — el universo de comparación), **incluidas las del propio lote actual**:

- Incluir el lote actual es imprescindible: si el Módulo 1 capturó la misma oferta dos veces, ambas copias viven en la misma corrida de descubrimiento.
- Se excluyen las ya marcadas `duplicada` (evita cadenas: X ≈ Y ≈ Z → X siempre apunta a Z, el original).
- Se excluyen las `descubierta` pendientes (aún no tienen descripción que comparar; las capturará la próxima corrida).
- **El original nunca cambia:** si X coincide con Y → X pasa a `duplicada` con `id_duplicidad = Y.id`; Y queda intacta. El FIFO del Nodo 1 ya garantiza que el más antiguo se preparó primero y es el original.
- **Universo vs. conjunto a evaluar:** el universo (contra quién se compara) son todas las `preparada` con `id_duplicidad = 'N/A'` (verificadas o no); el conjunto a **evaluar** (qué ofertas se verifican) son solo las pendientes con `fecha_ultima_verificacion = ''` (sección 7).

---

## 4. Las dos etapas (decisión D5 + confirmación)

| Etapa | Criterio | Coste | Resultado |
|---|---|---|---|
| **1. Título normalizado + empresa** | Título normalizado **idéntico** (sin acentos, minúsculas, sin puntuación) **y misma `empresa_id`** | Mínimo — índice en memoria por clave `(título_normalizado, empresa_id)`, búsqueda O(1) | Coincidencia → **duplicado directo** (sin comparar descripción) |
| **2. Descripción difusa** | Para las que no pasaron la etapa 1: título difuso ≥ `umbral_titulo` **y** descripción difusa ≥ `umbral_descripcion` (ambas con RapidFuzz) | Solo sobre candidatos preseleccionados | Coincidencia → duplicado |

**Misma empresa es requisito en ambas etapas** (confirmado): un duplicado real es la misma empresa republicando; títulos genéricos ("Desarrollador") con empresas distintas **no** son duplicados.

---

## 5. Umbrales (configurables, sin valores fijos)

Sección nueva `preparacion:` en `config/config.yaml` — **toda la configuración del módulo vive aquí** (el Nodo 1 la valida completa en su paso 2):

- `umbral_titulo: 90` — por encima, el título es "el mismo" a efectos de la etapa 2.
- `umbral_descripcion: 85` — por encima, la descripción es "la misma".
- `max_pasadas: 2` — límite del bucle del Nodo 4.
- `pausa_entre_ofertas_segundos` — prudencia anti-bloqueo del Nodo 2 (H4).
- `limite_vida_sesion` y reintentos — Nodo 2.
- `profundidad_catalogo_empresa` — enriquecimiento desacoplado (D4, paso 6 del Nodo 5).

---

## 6. Normalización (nueva utilidad compartida)

No existe hoy ninguna función de normalización. Se crea **una sola** en `shared/utilidades.py` (`normalizar_texto`): minúsculas, sin acentos, sin puntuación, espacios simples. La reutilizan:

- **Nodo 2** → `empresas.nombre_normalizado` (dedup de empresas).
- **Nodo 3** → títulos (etapa 1).

---

## 7. Auto-reparación (decidido + marcador confirmado)

**Marcador:** `ofertas_descubiertas.fecha_ultima_verificacion` pasa a significar **"última verificación de duplicidad"**; `''` = pendiente de verificar. La escribe **solo el Nodo 3** al completar la verificación de cada oferta (el Nodo 2 **no la toca** — corrección aprobada). La columna está exenta de la regla no-vacíos D31, ideal para este uso.

El Nodo 3 **evalúa** todas las `preparada` con `fecha_ultima_verificacion = ''` (pendientes, de esta corrida o de corridas anteriores) y las **compara contra todas** las `preparada` con `id_duplicidad = 'N/A'` (universo de originales, verificadas o no):

- Si una corrida anterior falló a mitad de la verificación, sus ofertas quedaron `preparada` con `fecha_ultima_verificacion = ''` → la siguiente corrida las re-verifica.
- Re-verificar es idempotente (da el mismo resultado). Coste aceptable: etapa 1 indexada; peor caso ~40 000 comparaciones difusas ≈ segundos.
- **Sin este marcador, el nodo no sabría qué ofertas ya fueron verificadas** (originales verificadas y pendientes tienen ambas `id_duplicidad = 'N/A'`) y re-verificaría todo el histórico en cada corrida.

---

## 8. Qué se escribe (trazabilidad)

| Objeto | Cambio |
|---|---|
| `ofertas_descubiertas.estado` | `preparada` → `duplicada` (solo la copia) |
| `ofertas_descubiertas.id_duplicidad` | id de la original (`OFE-xxx`) |
| `ofertas_descubiertas.observaciones` | Evidencia: "Duplicado de OFE-xxx — título 100 %, descripción 96 %" |
| `ofertas_descubiertas.fecha_ultima_verificacion` | Marcador de verificación completada (verificada, duplicada o no) |
| `eventos` | **`oferta_duplicada`** (suceso, `id_oferta` = la copia, evidencia con % y original) |
| Oferta original | Intacta (sin cambios, sin evento) |

**Métricas (D3):** `total_preparadas`/`total_duplicadas` de la corrida se cuentan **por eventos** (`contar_filas(eventos, id_corrida, codigo='oferta_preparada'/'oferta_duplicada')`). Así **no se sobrescribe `ofertas_descubiertas.id_corrida`** (sigue siendo la corrida de descubrimiento; la trazabilidad de preparación vive en `eventos`).

---

## 9. Errores

- Fallo de BD durante la verificación → reintento (`ejecutar_con_reintento`, `shared/retry.py`).
- Si persiste → la oferta **queda `preparada`** (nunca se penaliza sin verificar) y la próxima corrida la retoma.
- Sin errores de red posibles (nodo 100 % local).

---

## 10. Dependencias de esquema (migraciones necesarias)

1. `ofertas_descubiertas.estado` CHECK: añadir `duplicada` (D1) y columna `id_duplicidad` (D2).
2. `shared/models.py` `OfferState`: añadir `DUPLICADA`.
3. `shared/state_machine.py`: transición nueva `preparada → duplicada` (Nodo 3); la transición `descubierta → preparada` ya existe.
4. `corridas`: columnas `total_preparadas` y `total_duplicadas` (D3).
5. `eventos.id_oferta`: re-añadida (ya decidido en el Nodo 1).

---

## 11. Decisiones cerradas que sostienen el Nodo 3 (resumen)
- **Etapa 1 exacta:** título normalizado idéntico + misma empresa → duplicado directo, indexado en memoria.
- **Etapa 2 difusa:** título ≥ 90 y descripción ≥ 85 (ambas con RapidFuzz) para el resto.
- **Misma empresa = requisito en ambas etapas** (sin falsos positivos con títulos genéricos).
- **Alcance:** evaluar las pendientes (`fecha_ultima_verificacion = ''`) contra el universo de originales (`preparada` con `id_duplicidad = 'N/A'`, incluidas las del lote actual).
- **Descripción disponible:** la captura el Nodo 2 (el Módulo 1 no la captura — D28/D29).
- **Título disponible:** ya lo captura el Módulo 1 (D28); el Nodo 2 lo sobrescribe con el título de la página (detalle en el Nodo 2).
- **Auto-reparación:** marcador `fecha_ultima_verificacion` (lo escribe solo el Nodo 3); re-verificación idempotente; oferta nunca penalizada sin verificar.
- **Métricas por eventos:** `total_preparadas`/`total_duplicadas` contadas en `eventos`; no se sobrescribe `id_corrida` de la oferta.

---

# Nodo 4 — Verificación de más ofertas procesadas (bucle de decisión)

## Objetivo
Decidir si quedan más ofertas en estado `descubierta` en `ofertas_descubiertas` tras la preparación (Nodo 2) y la verificación de duplicidad (Nodo 3). **Nodo de decisión pura** (como `quedan_fuentes_por_procesar` / `quedan_sets_por_aplicar` del Módulo 1): no captura, no verifica, no escribe catálogos — solo consulta y decide el flujo.

---

## 1. Función y flujo

- Si tras el Nodo 3 quedan ofertas en `descubierta` → **volver al Nodo 2** para reprocesarlas (las ya `preparada`/`duplicada` no se tocan; en cada pasada el Nodo 2 re-consulta su lote de `descubierta` en la BD).
- Si no quedan → **continuar al Nodo 5** (FINALIZAR).

**Flujo completo del Módulo 2 con el bucle:**
1. Nodo 1 — INICIO (arranca la corrida).
2. Nodo 2 — Preparación (procesa todas las `descubierta`).
3. Nodo 3 — Verificación de duplicidad (todas las `preparada` con `id_duplicidad = 'N/A'`).
4. Nodo 4 — ¿Quedan `descubierta`?
   - **Sí** → volver al paso 2 (mientras `pasadas < max_pasadas`).
   - **No** → pasar al paso 5.
5. Nodo 5 — FINALIZAR (consolida métricas, escribe evento de terminación, libera el bloqueo).

---

## 2. Decisiones específicas

### 2.1 Combinación confirmada (Nodo 4 del usuario + aporte del análisis)
- **Nodo 4 = decisión pura de bucle** (propuesta del usuario): el bucle da **recuperación dentro de la misma corrida** — si una oferta falló por un corte de red transitorio, en la siguiente pasada se reintenta en la misma corrida, no en la próxima ejecución.
- **Nodo 5 = consolidación y cierre** (lo que en el análisis se propuso para el Nodo 4): consolida métricas (`total_preparadas`, `total_duplicadas`, `total_errores` por eventos), escribe el evento de terminación y libera el bloqueo — espejo de `finalizar_proceso` del Módulo 1.

### 2.2 Límite de pasadas — `max_pasadas` (configurable)
- Sin límite, una oferta que **nunca** podrá capturarse (p. ej. página borrada o 404 en LinkedIn) haría el bucle infinito en cada corrida.
- `max_pasadas: 2` (configurable): tras N pasadas la corrida cierra y las fallidas quedan `descubierta` para la próxima corrida.
- Total de intentos por oferta = `max_attempts` × `max_pasadas` (ambos configurables).

---

## 3. Respuestas a las preguntas planteadas

### 3.1 Errores del Nodo 4
El nodo solo ejecuta un SELECT de `ofertas_descubiertas` — el único error posible es **fallo de BD**:
- **Acción:** reintento (`ejecutar_con_reintento`); si persiste → fallo sistémico → la corrida aborta (`error_critico`).
- **Registro:** en `eventos` (tipo `error`) y en logs.
- No hay errores de red ni de captura en este nodo.

### 3.2 ¿Registrar eventos?
Siguiendo el patrón del Módulo 1, los nodos de decisión pura **no escriben eventos por cada comprobación** (evita ruido). Se escribe **un solo evento suceso `revision_pendientes`** al cerrar el bucle **siempre** (también cuando no hubo bucle: pasadas=1, pendientes=0), con el número de pasadas y cuántas ofertas quedaron para la próxima corrida. Así la trazabilidad es uniforme entre corridas.

### 3.3 ¿Otras acciones?
- (a) **Límite de pasadas** (`max_pasadas`) — imprescindible (ver 2.2).
- (b) **Refinamiento futuro (anotado, no se construye ahora):** contador por oferta (`intentos_fallidos`) para dejar de reintentar ofertas permanentemente rotas.

---

## 4. Reglas de negocio

- **RN-01:** el bucle solo vuelve al Nodo 2 mientras haya `descubierta` y no se supere `max_pasadas`.
- **RN-02:** las ofertas `preparada`/`duplicada` nunca se reprocesan en pasadas posteriores.
- **RN-03:** al agotar `max_pasadas`, las ofertas que siguen `descubierta` quedan para la próxima corrida (auto-reparación entre corridas, FIFO del Nodo 1).
- **RN-04:** este nodo no accede a LinkedIn ni a páginas de ofertas (eso es del Nodo 2).

---

## 5. Errores y excepciones

| Código | Error / excepción | Acción | Estado |
|---|---:|---|---|
| ERR-01 | Falla al consultar ofertas `descubierta` (BD) | Reintento; si persiste, aborto | `abortada` (`error_critico`) |
| ERR-02 | Se alcanzó `max_pasadas` con pendientes | Cierre normal con evento `revision_pendientes` | continúa → Nodo 5 |

---

## 6. Dependencias de esquema

Ninguna nueva: `max_pasadas` es configuración, no esquema. Las columnas de `corridas` ya están en las migraciones de los Nodos 1-3.

---

## 7. Decisiones cerradas que sostienen el Nodo 4 (resumen)
- **Decisión pura de bucle** (patrón del Módulo 1): ¿quedan `descubierta`? Sí → Nodo 2; No → Nodo 5.
- **`max_pasadas` configurable** (evita bucle infinito; total de intentos = `max_attempts` × `max_pasadas`).
- **Consolidación de errores y cierre** movidos al Nodo 5 (FINALIZAR), espejo del Módulo 1.
- **Eventos:** un solo `revision_pendientes` al cerrar el bucle (no eventos por comprobación).
- **Refinamiento futuro anotado:** contador `intentos_fallidos` por oferta (no se construye ahora).

---

# Nodo 5 — FINALIZAR (Cierre de la corrida)

## Objetivo
Cerrar la corrida de preparación de forma determinista y con trazabilidad completa: consolidar las métricas, escribir el evento de terminación, persistir el cierre en `corridas`, cerrar los recursos abiertos y liberar el bloqueo de concurrencia. **Espejo de `finalizar_proceso` del Módulo 1** (`modules/discovery/nodes/finalizar.py`): punto de convergencia de todas las terminaciones de la corrida.

---

## 1. Pasos del Nodo 5 (orden obligatorio)

| # | Paso | Qué hace | Fuente |
|---|---|---|---|
| 1 | **Consultar métricas** | Contar por **eventos** de la corrida: `total_preparadas`, `total_duplicadas`, `total_errores`, `total_sucesos` | `eventos` |
| 2 | **Escribir evento de terminación** | Suceso o error según el motivo; evidencia con métricas (`campo=valor`) | `eventos` |
| 3 | **Persistir cierre de corrida** | `actualizar_corrida`: estado, `fecha_fin`, `motivo_terminacion`, métricas (1 reintento, nunca aborta) | `corridas` |
| 4 | **Cerrar recursos** | Cerrar la **sesión HTTP reutilizada** del Nodo 2 (best-effort). Si el paso 6 usó el fallback de navegador Playwright del enriquecimiento, cerrarlo también | — |
| 5 | **Liberar bloqueo** | `liberar_bloqueo(id_corrida)` — solo si la corrida lo posee | `bloqueo` |
| 6 | **Enriquecer catálogo de empresas (desacoplado, H2)** | Solo si `profundidad_catalogo_empresa > 0`: enriquecer por lotes las empresas del catálogo (httpx sesión fresca, fallback navegador fresco — decisión D4). Corre **después** de liberar el bloqueo: no bloquea el camino crítico ni a otras corridas | `corridas`/`empresas` |

---

## 2. Las 3 diferencias con el Módulo 1

1. **Métricas por eventos, no por ofertas.** Decisión del Nodo 3: no se sobrescribe `id_corrida` de las ofertas, así que `total_ofertas` **no se puede contar** como en el Módulo 1 (`contar_filas(ofertas_descubiertas, {id_corrida})`). Aquí todo se cuenta en `eventos`:
   - `total_preparadas` = `contar_filas(eventos, {id_corrida, codigo='oferta_preparada'})`
   - `total_duplicadas` = `contar_filas(eventos, {id_corrida, codigo='oferta_duplicada'})`
   - `total_errores` = `contar_filas(eventos, {id_corrida, tipo='error'})`
   - `total_sucesos` = sucesos escritos **antes** del evento de terminación (semántica D30 intacta: el evento de cierre nunca se cuenta)
2. **Cierre de recursos:** cerrar la sesión httpx del Nodo 2 (best-effort); si el enriquecimiento (paso 6) usó el fallback de navegador, cerrarlo también.
3. **Nuevos motivos de terminación** (tabla abajo) — incluye `sin_pendientes` (Nodo 1) y `error_total` (nuevo, "todas fallaron").

---

## 3. Motivos de terminación (confirmados)

| Motivo | Cuándo | Estado `corridas` | Evento |
|---|---|---|---|
| `sin_pendientes` | Sin ofertas candidatas (Nodo 1 lo detectó) | `sin_pendientes` | suceso |
| `corrida_completada` | ≥1 oferta preparada o duplicada | `completada` | suceso |
| `error_total` | `hubo_candidatas` = sí (contexto del Nodo 1) pero **todas fallaron** (0 éxitos + ≥1 error) | `abortada` | error |
| `error_critico` | Fallo crítico de BD/config en cualquier nodo | `abortada` | error |
| `aborto` | Fallo de un nodo en el flujo | `abortada` | error |
| `concurrencia` | INICIO ERR-06 (no obtuvo el bloqueo global) | `abortada` | suceso |

**Fuente del dato:** `hubo_candidatas` (bool) lo registra el Nodo 1 en el contexto de la corrida (H3); el Nodo 5 lo usa para distinguir `error_total` de `sin_pendientes`.

**Justificación de `error_total` → `abortada` (confirmado):** con 200 ofertas fallidas en una corrida, la red o LinkedIn está bloqueada y conviene la señal de alerta (el usuario revisa), en vez de un "completada" engañoso.

---

## 4. `total_ofertas` (confirmado)

**`total_ofertas` = `total_preparadas + total_duplicadas`** (ofertas procesadas por esta corrida) — el campo queda poblado y comparable entre módulos. En el Módulo 1 era "ofertas registradas por esta corrida"; aquí la corrida no registra ofertas nuevas, así que el valor pasa a significar "procesadas".

---

## 5. Errores del Nodo 5

**Ningún error del cierre aborta** — cada paso se reintenta una vez y se degrada con log (patrón best-effort de `finalizar.py`). El cierre siempre se ejecuta; este nodo no puede fallar la corrida (las fallas de cierre solo quedan registradas en logs y en el evento de terminación si fue posible escribirlo).

---

## 6. Dependencias de esquema

**Ninguna nueva:** `total_preparadas`/`total_duplicadas` (D3) y `sin_pendientes` (Nodo 1) ya están contemplados. `total_errores`, `total_sucesos` y `motivo_terminacion` ya existen en `corridas`.

---

## 7. Decisiones cerradas que sostienen el Nodo 5 (resumen)
- **Espejo de `finalizar_proceso` del Módulo 1** (6 pasos, best-effort, el cierre nunca aborta; paso 6 = enriquecimiento desacoplado de empresas si `profundidad_catalogo_empresa > 0`).
- **Métricas por eventos** (decisión del Nodo 3): `total_preparadas`, `total_duplicadas`, `total_errores`, `total_sucesos` — sin sobrescribir `id_corrida` de las ofertas.
- **Semántica D30 intacta:** el evento de terminación nunca se cuenta en `total_sucesos`.
- **Motivos confirmados:** `sin_pendientes`, `corrida_completada`, `error_total` (→ `abortada`, vía `hubo_candidatas` del Nodo 1), `error_critico`, `aborto`, `concurrencia` (INICIO ERR-06).
- **`total_ofertas` = preparadas + duplicadas** (ofertas procesadas).
- **Cierre de recursos:** sesión httpx + navegador Playwright si el enriquecimiento (paso 6) lo usó.