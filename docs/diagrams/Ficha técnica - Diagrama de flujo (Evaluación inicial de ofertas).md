# Especificación canónica densificada — Módulo 3: Evaluación inicial de ofertas

**Base de decisiones:** rediseño del módulo en **dos procesos independientes y consecutivos**, aprobado por el usuario el 2026-11-15. Proceso **A — Exportación**, lanzado por la tanda programada: convierte las ofertas en `preparada` en lotes de archivos legibles por un chat y cierra su corrida con `evaluacion_pendiente`. Proceso **B — Importación**, lanzado a mano con un comando: valida lo que devolvió el chat, aplica el resultado, cambia el estado de cada oferta y cierra su corrida. La espera entre ambos **no es un nodo**: es el tiempo entre dos corridas cortas, cada una con su propio bloqueo y su propio cierre; ninguna corrida espera a una persona. El módulo deja de usar inteligencia artificial: se retiran las puertas, las llaves, las cuotas, las esperas máximas, las pausas entre ofertas, la política D50/D59 y el motivo `cupo_agotado`. Los 5 controles de veto, la regla de oro y el prompt `compatibility.md` v6 (D58) no cambian (el prompt pasa a ser la instrucción del chat); del resultado guardado solo cambia el campo que identificaba la puerta, que pasa a ser el modelo evaluador. Sin cambios de esquema: `resultado_evaluacion_inicial` se conserva y el campo de la puerta que respondió se reemplaza por el modelo evaluador declarado en configuración. Cuatro nodos por proceso (arranque, decisión, proceso, cierre), estructura espejo de las fichas de los Módulos 1 y 2.

## Convenciones comunes

- **Alcance del módulo**: dos procesos sobre las ofertas en `preparada` de `ofertas_descubiertas` — exportar los lotes para evaluación manual y aplicar después lo devuelto por el chat, cerrando cada proceso con métricas propias. No realiza el análisis profundo (eso corresponde a la fase siguiente).
- **Dos corridas, no una**: cada proceso instancia su propia corrida, toma el bloqueo global, ejecuta en segundos y lo libera. El intervalo entre ambos es tiempo real de espera, nunca un paso de una corrida.
- **Contexto de ejecución**: única estructura/objeto transmitida a todos los nodos de un mismo flujo. Ningún nodo posterior reinicializa conexiones ni estado, salvo responsabilidad asignada.
- **Carpeta de trabajo**: `data/evaluacion_manual/` con `instruccion_evaluacion.md` (la instrucción del chat), `lotes/` (lo que se sube al chat y su ficha de control) y `resultados/` (lo que devuelve el chat). Los archivos de resultados que no corresponden a ningún lote se apartan en `resultados/rechazados/` (se crea al usarse). La ruta base se toma de configuración.
- **Intercambio**: lote en texto (`.md`) con cabecera y un bloque por oferta; ficha de control interna (`.json`) con los identificadores esperados; respuesta del chat en JSON por línea (`.jsonl`), una línea por oferta.
- **Nombres de archivo**: todo archivo generado lleva el `id_corrida` que lo produjo — `<id_corrida>_lote_<NNN>.md`, `<id_corrida>_lote_<NNN>.json` y `<id_corrida>_lote_<NNN>.jsonl` (con sufijo `_parteN` cuando la respuesta se entrega en varias partes). Dos exportaciones nunca se mezclan.
- **Trazabilidad**: todo registro incluye `id_corrida`; los eventos de oferta incluyen `id_oferta` (éxito y rechazo). `fuente_id = 'N/A'` en este módulo (sin fuentes; respeta no-vacíos D31).
- **Registro**: en `"errores o sucesos"` (`eventos`); si no está disponible, registro crítico local (consola/archivo documentado). Todo evento incluye `id_corrida`, marca_temporal, tipo y descripción.
- **Aborto**: terminación inmediata en el `"Finalizar Proceso"` del flujo en curso, con estado `abortada` y motivo `error_critico`/`aborto`.
- **Terminación controlada/normal**: cierre sin trabajo (`sin_pendientes` en exportación, `sin_resultados` en importación) o con trabajo (`evaluacion_pendiente` en exportación, `corrida_completada` en importación); lo registra el cierre de cada flujo.
- **Reintentos**: máximo global configurable (`retries`, sección `evaluacion_manual:`); solo son reintentables los códigos declarados en cada nodo. Aplican a escritura y borrado de archivos y a escrituras de base. Una línea rechazada nunca se reintenta: se informa y la oferta sigue pendiente.
- **Sin inteligencia artificial**: el módulo no llama a ningún modelo, no usa red, llaves ni credenciales. La evaluación la realiza el operador en un chat externo; el sistema prepara el material y aplica lo que vuelve.
- **Nada se descarta por duda**: una línea inválida o faltante deja la oferta en `preparada`; solo un resultado válido y completo cambia su estado.
- **Regla de datos (D31)**: ningún campo vacío — `N/A`/`N/R` cuando no aplica; exenciones: `id_externo` (dedup) y `fecha_ultima_verificacion` (marcador de verificación del Módulo 2). Cuando la oferta no trae descripción y se descarta por `v3 = FAIL`, el entregable principal se guarda `N/A` (cumple D31) como única excepción a la validación de contenido de D52.

---

## Flujo A — Exportación de ofertas (lo lanza la tanda programada)

## Nodo proceso: INICIO — Arranque de la corrida de exportación
**Versión**: 2.0 (aprobada)

### Posición
Punto de entrada único del flujo de exportación; precede toda decisión y acción de negocio. Ninguna decisión posterior puede ejecutarse sin el contexto producido aquí.

### Objetivo
Instanciar la corrida de exportación (corrida propia del módulo) y preparar el contexto de ejecución: trazabilidad, configuración validada (sección `evaluacion_manual:` completa), BD disponible, concurrencia (bloqueo global compartido con los Módulos 1 y 2), carpeta de trabajo disponible, ofertas candidatas y estado inicial. **No escribe lotes** (eso corresponde al nodo Exportar ofertas).

### Descripción funcional
Al recibir disparador:
1. Crea instancia de corrida con `id_corrida` único y `fecha_inicio`, **antes** de intentar el bloqueo, para que toda corrida registrada pueda cerrarse.
2. Carga configuración y valida nivel global: **toda** la sección `evaluacion_manual:` — `carpeta_base`, `tamano_lote`, `modelo_evaluador` y `retries`. No valida ninguna ruta de inteligencia artificial.
3. Verifica disponibilidad y permisos de escritura de la BD del módulo (prueba de escritura con rollback).
4. Valida concurrencia mediante bloqueo persistente **global compartido** con los Módulos 1 y 2.
5. Comprueba la carpeta de trabajo: crea `carpeta_base`, `lotes/` y `resultados/` si faltan, y verifica permiso de escritura.
6. Carga ofertas candidatas: SELECT de `ofertas_descubiertas` con estado `preparada`, orden FIFO (`fecha_descubrimiento ASC, id ASC`).
7. Inicializa estado: contadores (`exportadas`, `lotes`, `errores`) abiertos en cero y `hubo_candidatas` (bool) en el contexto — los nodos siguientes los van llenando y el cierre los consume para el resumen y para distinguir `error_total` de `sin_pendientes`.
8. Entrega control al nodo siguiente.

Error fatal de inicialización, carpeta no disponible o concurrencia activa producen terminación controlada en `"Finalizar Proceso"` antes de escribir cualquier archivo.

### Responsabilidad
- **Negocio**: arrancar la corrida de exportación y verificar precondiciones operativas. No decide si hay pendientes ni escribe lotes.
- **Técnica**: `id_corrida`, conexión, bloqueo de concurrencia global, carpeta de trabajo, estado inicial, carga FIFO de candidatas.
- **Límite**: garantiza contexto y candidatas cargadas; no garantiza la escritura de los lotes. No accede a inteligencia artificial ni a red.

### Entradas
- Disparador programado (tanda) o manual.
- Almacén de configuración: sección `evaluacion_manual:` completa (`carpeta_base`, `tamano_lote`, `modelo_evaluador`, `retries`) + `concurrencia` (umbral de obsolescencia).
- Estado persistente de bloqueo, si existe.
- BD con `ofertas_descubiertas`.
- Sistema de archivos con permiso de escritura en la carpeta base.

### Salidas
- Contexto inicializado: `id_corrida`, fecha_inicio, candidatas FIFO, `hubo_candidatas`, contadores, conexión activa, bloqueo adquirido, rutas de carpeta resueltas.
- Terminación en `"Finalizar Proceso"` con `abortada`/`concurrencia` si aplica.
- Control normal al nodo de decisión "¿Hay ofertas preparadas?".

### Reglas de negocio
- **RN-01**: toda corrida tiene `id_corrida` único; todo registro del proceso queda enlazado a él.
- **RN-02**: solo una ejecución activa a la vez en todo el pipeline (bloqueo global compartido Módulos 1/2/3).
- **RN-03**: el iterador de candidatas se reinicia al inicio de cada corrida; la corrida procesa la lista cargada en orden.
- **RN-04**: este nodo no valida si hay ofertas pendientes; esa validación es del nodo de decisión siguiente.
- **RN-05**: este nodo no escribe archivos de lote ni modifica ofertas.
- **RN-06**: la corrida exporta todas las ofertas en `preparada` (sin tope); el tamaño de lote solo acota el trabajo por archivo.
- **RN-07**: selección FIFO — más antiguas primero; las pendientes de corridas previas que sigan en `preparada` vuelven a juntarse en orden. *(As-built D53: el desempate por identificador compara su NÚMERO secuencial (`numero_secuencial_id`) — la comparación textual invierte el orden a partir de 10.000 ofertas por prefijo.)*
- **RN-08**: este nodo no accede a inteligencia artificial, red ni credenciales.
- **RN-09**: la corrida se registra antes de intentar el bloqueo, para que toda corrida abierta sea cerrable (mismo criterio que el Módulo 2).

### Validaciones
- **VAL-01**: `id_corrida` único y no nulo.
- **VAL-02**: configuración global: sección `evaluacion_manual:` completa y con rangos válidos (`carpeta_base` no vacía, `tamano_lote` entero ≥ 1, `modelo_evaluador` no vacío, `retries` coherente). Sin ruta de inteligencia artificial.
- **VAL-03**: BD: conexión abierta y prueba de escritura exitosa con rollback.
- **VAL-04**: bloqueo legible; obsolescencia por marca_temporal contra umbral configurable; marcas temporales coherentes.
- **VAL-05**: carpeta de trabajo accesible y escribible (base, `lotes/`, `resultados/`).
- **VAL-06**: contexto completo antes de entregar control (`hubo_candidatas` presente).
- **VAL-07**: candidatas cargadas en orden FIFO; conteo ≥ 0.

### Condiciones
- **Continuación normal**: configuración válida + BD disponible + carpeta disponible + sin concurrencia activa.
- **Terminación**: configuración ausente/ilegible/corrupta; BD indisponible/bloqueada/sin permisos; carpeta no disponible o sin permisos; concurrencia activa; estado de bloqueo no decidible.
- **Sin candidatas**: no termina aquí; el nodo de decisión siguiente resuelve `sin_pendientes`.

### Ramas
- **Normal** → `"¿Hay ofertas preparadas?"`.
- **Excepción** → `"Finalizar Proceso"` con estado `abortada` o motivo `concurrencia`.

### Errores y excepciones

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---|---|---|---|
| ERR-01 | Colisión o fallo de generación de `id_corrida` | 1 | Registro crítico local | Reintento único; si persiste, aborto | `abortada` |
| ERR-02 | Configuración ausente | 2 | Registro crítico local | Aborto | `abortada` |
| ERR-03 | Configuración ilegible | 2 | Registro crítico local | Aborto | `abortada` |
| ERR-04 | Configuración corrupta / estructura inconsistente | 2 | Registro crítico local | Aborto | `abortada` |
| ERR-05 | BD indisponible / bloqueada / sin permisos | 3 | Evento crítico si accesible; si no, local | Aborto | `abortada` |
| ERR-06 | Concurrencia activa | 4 | Evento "finalización por concurrencia" | Terminación controlada | `concurrencia` |
| ERR-07 | Bloqueo obsoleto (antigüedad > umbral) | 4 | Suceso de sobrescritura | Sobrescribir bloqueo y continuar | continúa |
| ERR-08 | Estado de bloqueo no decidible | 4 | Evento crítico | Aborto | `abortada` |
| ERR-09 | Contienda de adquisición de bloqueo | 4 | — | Atomicidad/unicidad; perdedor cae en ERR-06 | `concurrencia` |
| ERR-10 | Carpeta de trabajo no disponible o sin permiso de escritura | 5 | Evento crítico si accesible | Aborto | `abortada` |
| ERR-11 | Falla interna de inicialización de estado | 7 | Evento crítico si accesible | Aborto | `abortada` |

### Dependencias y contratos
- **Antecesor**: ninguno.
- **Sucesor normal**: `"¿Hay ofertas preparadas?"`.
- **Sucesor de excepción**: `"Finalizar Proceso"`.
- **Contrato entregado**: contexto completo como única interfaz; candidatas FIFO con `hubo_candidatas`; rutas de carpeta resueltas.
- **Impactos aprobados**:
  - `"Finalizar Proceso"` libera el bloqueo y consume `hubo_candidatas` para `error_total`.
  - El nodo Exportar ofertas procesa la lista en el orden entregado.
  - `corridas` conserva el vocabulario `sin_pendientes` y suma `evaluacion_pendiente`.

### Notas de implementación
- Espejo del INICIO de los Módulos 1 y 2: mismo mecanismo de bloqueo, `sondear_escritura`, `registrar_corrida` y `generar_id`.
- Orden obligatorio: configuración antes que BD; carpeta después del bloqueo; candidatas después de BD y bloqueo.
- No acceder a inteligencia artificial, red ni plataformas; sin credenciales.
- Sin valores fijos: carpeta, tamaño de lote y modelo evaluador desde la sección `evaluacion_manual:`.
- El `id_corrida` generado aquí viaja en el nombre de todos los archivos del proceso.

### Pasos funcionales
1. **Recibir disparador e instanciar corrida**. Entrada: evento programado/manual. Proceso: crear instancia, generar `id_corrida`, fecha_inicio. Salida: instancia. Val: VAL-01. Err: ERR-01.
2. **Cargar configuración y validar nivel global**. Entrada: almacén de configuración. Proceso: leer y validar la sección `evaluacion_manual:` completa (claves y rangos). Salida: configuración cruda en contexto. Val: VAL-02. Err: ERR-02, ERR-03, ERR-04.
3. **Verificar BD**. Entrada: parámetros de conexión. Proceso: abrir conexión; prueba de escritura con rollback. Salida: conexión disponible. Val: VAL-03. Err: ERR-05.
4. **Validar concurrencia**. Entrada: `id_corrida`, estado de bloqueo, umbral. Proceso: leer bloqueo global compartido; activo no obsoleto → terminación controlada; obsoleto → sobrescribir y continuar; inexistente → marcar bloqueo. Salida: bloqueo adquirido o terminación. Val: VAL-04. Err: ERR-06, ERR-07, ERR-08, ERR-09.
5. **Comprobar carpeta de trabajo**. Entrada: `carpeta_base`. Proceso: crear carpetas faltantes y verificar escritura. Salida: rutas resueltas. Val: VAL-05. Err: ERR-10.
6. **Cargar ofertas candidatas**. Entrada: BD. Proceso: SELECT `preparada` orden FIFO (`fecha_descubrimiento ASC, id ASC`). Salida: lista de candidatas. Val: VAL-07. Err: ERR-05.
7. **Inicializar estado**. Entrada: candidatas. Proceso: abrir contadores (`exportadas`, `lotes`, `errores`) en cero y fijar `hubo_candidatas` (bool). Salida: contexto completo. Val: VAL-06. Err: ERR-11.
8. **Entregar control**. Entrada: contexto completo. Proceso: cerrar nodo. Salida: flujo a la decisión de candidatas. Val: VAL-06. Err: contexto incompleto → ERR-11.

---

## Nodo decisión: "¿Hay ofertas preparadas?"
**Versión**: 2.0 (aprobada)

### Posición
Primera decisión de negocio del flujo de exportación, inmediatamente después del INICIO. Análoga a "¿Quedan ofertas por preparar en esta corrida?" del Módulo 2.

### Objetivo
Decidir si la corrida exporta o termina controladamente según exista al menos una oferta en `preparada`.

### Descripción funcional
Lee la lista de candidatas del contexto en memoria, sin releer la BD. Si hay ≥ 1 candidata, entrega control al nodo Exportar ofertas con contrato "lista no vacía". Si hay 0, fija motivo `sin_pendientes` —suceso, no error— y entrega control a `"Finalizar Proceso"`. No realiza I/O, no accede a archivos ni a red, no revalida estructura.

### Entradas
Contexto de INICIO: lista de candidatas, `hubo_candidatas`, `id_corrida`, conexión activa, bloqueo adquirido, rutas de carpeta.

### Salidas
- **Sí** → Exportar ofertas con lista no vacía.
- **No** → `"Finalizar Proceso"` con motivo `sin_pendientes`.
- **Falla interna** → `"Finalizar Proceso"` con estado `abortada`.

### Reglas de negocio
- **RN-01**: evaluar solo contexto; prohibido releer la BD.
- **RN-02**: "candidata" = oferta cargada por INICIO en `preparada`; no hay estados adicionales.
- **RN-03**: no revalidar estructura; ya lo hizo INICIO.
- **RN-04**: ausencia de candidatas es terminación controlada `sin_pendientes`, tipo suceso (estado `sin_pendientes` en `corridas`).
- **RN-05**: este nodo no registra; `"Finalizar Proceso"` registra la terminación.
- **RN-06**: rama Sí garantiza lista no vacía; ningún nodo posterior revalida existencia.

### Validaciones
- **VAL-01**: lista de candidatas accesible en contexto.
- **VAL-02**: evaluación sobre lista leída; conteo entero ≥ 0; sin revalidación.
- **VAL-03**: rama Sí solo con conteo > 0.
- **VAL-04**: en rama No, `sin_pendientes` fijado con `id_corrida` y marca_temporal antes de entregar control.

### Condiciones y ramas
- **Sí**: conteo > 0 → Exportar ofertas.
- **No**: conteo == 0 → `"Finalizar Proceso"` con `sin_pendientes`.
- **Aborto**: contexto sin lista de candidatas o incompleto → `"Finalizar Proceso"` con `abortada`.

### Errores

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---|---|---|---|
| ERR-01 | Contexto sin lista de candidatas o incompleto | 1 | Evento crítico si accesible | Aborto | `abortada` |

### Dependencias y contratos
- **Antecesor**: INICIO.
- **Sucesor Sí**: Exportar ofertas.
- **Sucesor No**: `"Finalizar Proceso"` con `sin_pendientes`.
- **Impactos aprobados**: ningún nodo posterior revalida existencia; `"Finalizar Proceso"` incorpora `sin_pendientes`; la rama Sí entrega la lista en el orden FIFO cargado por INICIO.

### Notas de implementación
- Nodo de evaluación pura: sin I/O, sin red, sin escritura, salvo fijar motivo en rama No.
- Leer la lista del mismo objeto de contexto; no copiar ni transformar.

### Pasos funcionales
1. **Leer lista del contexto**. Entrada: contexto. Proceso: acceder a lista; no releer la BD. Salida: lista posiblemente vacía. Val: VAL-01. Err: ERR-01.
2. **Evaluar existencia**. Entrada: lista. Proceso: contar; condición = conteo > 0. Salida: Sí/No. Val: VAL-02. Err: ninguna.
3. **Rama Sí**. Entrada: resultado Sí. Proceso: entregar control. Salida: flujo a Exportar ofertas. Val: VAL-03. Err: ninguna.
4. **Rama No**. Entrada: resultado No, `id_corrida`. Proceso: fijar `sin_pendientes` y entregar control. Salida: flujo a `"Finalizar Proceso"`. Val: VAL-04. Err: ninguna.

---

## Nodo proceso: "Exportar ofertas"
**Versión**: 2.0 (aprobada)

### Posición
Entre la rama Sí de `"¿Hay ofertas preparadas?"` y `"Finalizar Proceso"`. Nodo de proceso por lotes: escribe todos los lotes antes de entregar control. Sucesor único: `"Finalizar Proceso"`.

### Objetivo
Convertir las ofertas en `preparada` en lotes legibles por un chat, con su ficha de control, y dejar la instrucción de evaluación al día. **No modifica la base ni el estado de ninguna oferta.**

### Descripción funcional
Flujo por lotes, en orden FIFO (orden obligatorio):

| # | Paso | Qué hace | Fuente |
|---|---|---|---|
| 1 | **Comprobar lotes pendientes** | Lee `lotes/`. Si algún lote todavía contiene ofertas en `preparada`, no exporta: registra el suceso y pasa al cierre con `evaluacion_pendiente`. Los lotes ya resueltos se retiran (no bloquean) | Carpeta + BD |
| 2 | **Refrescar la instrucción** | Escribe `instruccion_evaluacion.md` si falta o si la huella del prompt oficial no coincide con la registrada en su cabecera; deja constancia en el registro | Prompt oficial |
| 3 | **Agrupar en lotes** | De `tamano_lote` en `tamano_lote` (30 por defecto), respetando el orden | Lista del contexto |
| 4 | **Escribir el archivo del lote** | Cabecera (corrida, lote, fecha, cantidad) y un bloque por oferta con identificador, título, empresa, ubicación, modalidad y descripción | Candidatas |
| 5 | **Escribir la ficha de control** | Identificadores esperados, corrida, lote y fecha; archivo interno que no se sube al chat | Mismo lote |
| 6 | **Registrar y contar** | Suceso por lote con nombre de archivo, cantidad y corrida; suma en exportadas y lotes | Eventos |

Un fallo de escritura de un lote descarta sus archivos a medias, cuenta error y continúa con el siguiente: como el lote a medias no queda en la carpeta, no bloquea el guardián y sus ofertas, que siguen en `preparada`, se exportan en la corrida siguiente. **Todos los eventos de lote llevan `id_corrida`.**

### Entradas
- Contexto: lista de candidatas no vacía, `id_corrida`, configuración (`carpeta_base`, `tamano_lote`), contadores.
- BD (solo lectura): `ofertas_descubiertas` de las candidatas — identificador, título, empresa, ubicación, modalidad y descripción.
- Prompt oficial `prompts/initial_evaluation/compatibility.md`, fuente de la instrucción del chat.
- Carpeta de trabajo (`lotes/`, `resultados/`).

### Salidas
- `instruccion_evaluacion.md` al día.
- Por lote: `<id_corrida>_lote_<NNN>.md` y `<id_corrida>_lote_<NNN>.json`.
- Sucesos por lote; contadores al día.
- Control único a `"Finalizar Proceso"`.
- Aborto → `"Finalizar Proceso"` con `abortada`.

### Reglas de negocio
- **RN-01**: por lotes: este nodo escribe todos los lotes antes de entregar control.
- **RN-02**: no modifica la base: ni estados, ni `resultado_evaluacion_inicial`, ni `id_corrida` de la oferta.
- **RN-03**: el nombre de cada archivo lleva el `id_corrida`, de modo que dos exportaciones nunca se mezclan; el número de lote es correlativo desde `001`.
- **RN-04**: el tamaño de lote sale de configuración (30 por defecto); el último lote puede ser menor.
- **RN-05**: contenido exacto por oferta — identificador, título, empresa, ubicación, modalidad y descripción. La descripción usa la higiene de ruido vigente (empresa, beneficios, avisos) y el tope de 6.000 caracteres, con nota visible cuando se recorta; el original guardado no se toca.
- **RN-06**: la ficha de control es interna: no se sube al chat, no la edita el operador y su lista de identificadores debe coincidir exactamente con la del lote.
- **RN-07**: guardián de lotes: con lotes que aún contienen ofertas en `preparada` no se generan nuevos (evita evaluar dos veces lo mismo); los lotes cuyas ofertas ya no están pendientes se retiran y no bloquean.
- **RN-08**: la instrucción del chat se genera desde el prompt oficial; se reescribe solo si falta o si la huella del prompt oficial no coincide con la registrada en su cabecera. Es un archivo generado: las ediciones manuales no se conservan cuando se regenera, y la regeneración deja constancia en el registro.
- **RN-09**: escritura atómica por lote: el archivo de texto y la ficha se escriben juntos y se verifican; un lote a medias se descarta y cuenta error.
- **RN-10**: un suceso por lote (no por oferta), para no inflar las métricas de cierre.
- **RN-11**: las ofertas se escriben en orden FIFO, dentro del lote y entre lotes.

### Validaciones
- **VAL-01**: insumos presentes (lista no vacía, configuración, carpetas, prompt).
- **VAL-02**: lote no mayor que `tamano_lote`; último lote ≥ 1.
- **VAL-03**: nombre de archivo con `id_corrida` y número de lote correlativo desde `001`.
- **VAL-04**: cada bloque tiene los seis campos; la descripción nunca se omite (si la oferta trae `N/A`/`N/R`, se escribe el marcador).
- **VAL-05**: la ficha de control contiene exactamente los identificadores del lote, más corrida, número de lote y fecha.
- **VAL-06**: instrucción escrita o vigente.
- **VAL-07**: escritura verificada (archivo existente, no vacío y legible tras escribir).

### Condiciones
- **Normal**: lotes escritos y verificados.
- **Guardián**: hay lotes con ofertas pendientes → no se exporta y el cierre es `evaluacion_pendiente`.
- **Fallo de un lote**: no aborta; se descarta el lote a medias, se cuenta error y se continúa.
- **Aborto**: insumos ausentes/corruptos, carpeta no escribible, corrupción de contexto.

### Ramas
- Normal única → `"Finalizar Proceso"`.
- Aborto → `"Finalizar Proceso"` con `abortada`.

### Errores y eventos

| Código | Error / evento | Reint. | Detección | Registro / acción | Estado |
|---|---|---|:---:|---|---|
| ERR-01 | Insumos ausentes/corruptos | No | 1 | Evento crítico; aborto | `abortada` |
| ERR-02 | Carpeta de trabajo no escribible | No | 1 | Evento crítico; aborto | `abortada` |
| ERR-03 | Fallo de escritura de un lote | Sí (`retries`) | 4-5 | Reintento de escritura; agotado → se descartan los archivos del lote, se cuenta error y se continúa | `preparada` (sin cambios) |
| ERR-04 | Ficha de control inconsistente con el lote | No | 5 | Se descarta el lote completo y se cuenta error | `preparada` (sin cambios) |
| ERR-05 | Fallo persistente al registrar el suceso del lote | No | 6 | Registro local; continúa (best-effort) | continúa |
| EVT-01 | `ofertas_exportadas` | No | 6 | Suceso con lote, archivos, cantidad y corrida | continúa |
| EVT-02 | `exportacion_omitida` | No | 1 | Suceso con lotes y ofertas pendientes detectadas | continúa |
| EVT-03 | `lotes_retirados` | No | 1 | Suceso con los lotes ya resueltos retirados y sus archivos | continúa |

### Escenarios límite
- **Guardián activo** (lotes con ofertas pendientes): no se generan archivos; el cierre es `evaluacion_pendiente` con el conteo de pendientes en la evidencia.
- **Lotes ya resueltos sin borrar**: se retiran y la exportación continúa; no bloquean el proceso.
- **Último lote incompleto** (menos ofertas que el tamaño configurado): se escribe igual y se cierra.
- **Descripción vacía, `N/A` o no reportada**: se exporta igual; el criterio se aplica al evaluar, no aquí.
- **Descripción recortada**: se escribe la nota de recorte; el texto original en la base no se altera.
- **Cero candidatas**: este nodo no se ejecuta; lo resuelve la decisión anterior con `sin_pendientes`.
- **Fallo a mitad de una corrida**: los lotes ya escritos y verificados se conservan; lo no escrito sigue en `preparada` y se exporta en la corrida siguiente.

### Dependencias y contratos
- **Antecesor**: `"¿Hay ofertas preparadas?"` rama Sí.
- **Sucesor normal**: `"Finalizar Proceso"`.
- **Sucesor de aborto**: `"Finalizar Proceso"`.
- **Contratos consumidos**: lista FIFO no vacía; configuración de evaluación manual; carpeta de trabajo; prompt oficial.
- **Contratos entregados**: lotes y fichas de control en `lotes/`; instrucción del chat al día; sucesos por lote; contadores al día.
- **Impactos aprobados**:
  - `"Finalizar Proceso"` cuenta lotes y ofertas exportadas y fija `evaluacion_pendiente`.
  - El proceso de importación consume los lotes, las fichas de control y la instrucción generada aquí.
  - La base queda intacta: ninguna oferta cambia de estado en este proceso.

### Notas de implementación
- La higiene de la descripción es la misma que ya usaba la evaluación (D49): se quitan secciones de ruido al inicio y al final y se recorta a 6.000 caracteres; se ejecuta aquí, no en la importación, para que el chat reciba el texto listo.
- Codificación UTF-8 y saltos de línea `\n` en los tres formatos.
- Sin escrituras en BD; ninguna transacción abierta durante la escritura de archivos.
- La carpeta de datos no se versiona; los archivos son transporte y desaparecen al importar.
- La instrucción se compara contra la huella del prompt oficial registrada en su cabecera: solo se reescribe si falta o si el prompt cambió. Es un archivo generado y sus ediciones manuales no se conservan al regenerarse; cada regeneración queda en el registro.
- Sin valores fijos: carpeta, tamaño de lote y nombre de archivo desde configuración y del `id_corrida`.

### Pasos funcionales
1. **Leer insumos**. Entrada: contexto, configuración, carpetas, prompt. Proceso: verificar lista no vacía, ajustes completos y carpeta escribible. Salida: insumos. Val: VAL-01. Err: ERR-01, ERR-02.
2. **Comprobar lotes pendientes**. Entrada: `lotes/`, BD. Proceso: identificar lotes con ofertas aún en `preparada`; retirar los ya resueltos. Salida: decisión guardián / continuar. Val: VAL-01. Err: ERR-01, EVT-02, EVT-03.
3. **Refrescar la instrucción**. Entrada: prompt oficial, `instruccion_evaluacion.md`. Proceso: escribir si falta o si la huella del prompt no coincide con la registrada; dejar constancia. Salida: instrucción vigente. Val: VAL-06. Err: ERR-02.
4. **Agrupar en lotes**. Entrada: lista FIFO, `tamano_lote`. Proceso: cortar en grupos correlativos desde `001`. Salida: lotes. Val: VAL-02. Err: ninguna.
5. **Escribir el lote y su ficha**. Entrada: ofertas del lote, rutas. Proceso: escribir `.md` y `.json`, verificar contenido y coherencia. Salida: archivos verificados. Val: VAL-03, VAL-04, VAL-05, VAL-07. Err: ERR-03, ERR-04.
6. **Registrar y contar**. Entrada: lote escrito. Proceso: suceso con archivos y cantidad; sumar exportadas y lotes. Salida: métricas al día. Val: VAL-07. Err: ERR-05, EVT-01.
7. **Repetir y entregar control**. Entrada: lotes restantes. Proceso: siguiente lote hasta agotar; cerrar nodo. Salida: flujo a `"Finalizar Proceso"`. Err: ninguna.

---

## Nodo terminal: "Finalizar Proceso (exportación)"
**Versión**: 2.0 (aprobada)

### Identificación
Punto de convergencia de todas las terminaciones del flujo de exportación. Espejo de `"Finalizar Proceso"` de los Módulos 1 y 2, con motivos y métricas propios. Sin sucesor: fin de la corrida de exportación.

### Objetivo
Cerrar la corrida de exportación de forma determinista y con trazabilidad completa:
1. consultar métricas por eventos;
2. escribir evento de terminación;
3. persistir cierre de corrida;
4. cerrar recursos abiertos;
5. liberar bloqueo de concurrencia si esta corrida lo posee;
6. terminar proceso.

### Descripción funcional (pasos en orden obligatorio)

| # | Paso | Qué hace | Fuente |
|---|---|---|---|
| 1 | **Consultar métricas** | Contar por eventos de la corrida: lotes, ofertas exportadas, errores y sucesos; definir motivo según tabla oficial | `eventos` |
| 2 | **Escribir evento de terminación** | Suceso o error según el motivo; evidencia con métricas (`campo=valor`) | `eventos` |
| 3 | **Persistir cierre de corrida** | Estado, `fecha_fin`, `motivo_terminacion`, métricas (1 reintento, nunca aborta) | `corridas` |
| 4 | **Cerrar recursos** | Cerrar la conexión (best-effort; este flujo no deja archivos abiertos) | — |
| 5 | **Liberar bloqueo** | Solo si la corrida lo posee | `bloqueo` |

### Entradas
Contexto best-effort:
- motivo/estado de terminación: `evaluacion_pendiente`, `sin_pendientes`, `error_total`, `error_critico`, `aborto`, `concurrencia`;
- `id_corrida`; `hubo_candidatas` (bool, del INICIO); contadores (`exportadas`, `lotes`, `errores`);
- estado de bloqueo; conexión de BD.

### Salidas
- Evento de terminación persistido en `"errores o sucesos"` o registro crítico local si falla escritura.
- Corrida cerrada (estado, `fecha_fin`, motivo y métricas).
- Recursos cerrados; bloqueo liberado si esta corrida lo poseía.
- Sin sucesor: fin de la corrida de exportación.

### Ramas
No es nodo de decisión.

### Estados/motivos oficiales

| Motivo | Cuándo | Estado `corridas` | Tipo de evento |
|---|---|---|---|
| `evaluacion_pendiente` | Se generaron lotes, o ya había lotes con ofertas pendientes sin importar | `completada` | suceso |
| `sin_pendientes` | Sin ofertas en `preparada` | `sin_pendientes` | suceso |
| `error_total` | `hubo_candidatas` = sí pero ninguna oferta exportada y ≥ 1 error | `abortada` | error |
| `error_critico` | Fallo crítico de BD/config/carpeta en cualquier nodo | `abortada` | error |
| `aborto` | Fallo de un nodo en el flujo | `abortada` | error |
| `concurrencia` | INICIO ERR-06 (no obtuvo el bloqueo global) | `abortada` | suceso |

**Fuente del dato:** `hubo_candidatas` (bool) lo registra el INICIO en el contexto; el paso 1 lo usa para distinguir `error_total` de `sin_pendientes`.

### Métricas (por eventos)
- `lotes` = número de eventos `ofertas_exportadas` de la corrida (queda en la evidencia del cierre; no hay columna propia).
- `ofertas exportadas` = suma de la cantidad declarada en cada evento `ofertas_exportadas` → `total_ofertas`.
- `errores` = eventos de error de la corrida → `total_errores`.
- `sucesos` = sucesos escritos **antes** del evento de terminación (el evento de cierre nunca se cuenta) → `total_sucesos`.
- `fuentes_procesadas` = 0 (sin fuentes).

No se sobrescribe `ofertas_descubiertas.id_corrida` (sigue siendo la corrida de descubrimiento; la trazabilidad de la exportación vive en `eventos` y en el nombre de los archivos).

### Especificación funcional
1. **Consultar métricas**. Entrada: `eventos`, `id_corrida`, `hubo_candidatas`. Proceso: contar por eventos; decidir motivo según tabla oficial. Salida: métricas + motivo. Excepción: fallo de conteo → reintento único; si persiste, motivo por defecto `aborto` con métricas vacías y continuar.
2. **Escribir evento de terminación**. Entrada: estado, motivo, `id_corrida`, métricas. Proceso: suceso o error según motivo con evidencia `campo=valor`; fallo → reintento único; si persiste, registro crítico local y continuar. Salida: evento persistido o registro local. Excepción: fallo tras reintento no aborta.
3. **Persistir cierre de corrida**. Entrada: estado, motivo, métricas. Proceso: guardar estado, `fecha_fin`, `motivo_terminacion` y métricas; 1 reintento; nunca aborta. Salida: corrida cerrada. Excepción: fallo tras reintento → registro local y continuar.
4. **Cerrar recursos (best-effort)**. Entrada: conexión BD. Proceso: cerrar; errores se registran localmente y no impiden terminación. Salida: recursos cerrados. Excepción: errores de cierre no abortan.
5. **Liberar bloqueo si corresponde**. Entrada: estado de bloqueo, `id_corrida`. Proceso: si el bloqueo existe y el propietario == `id_corrida`, liberar; fallo → reintento único; si persiste, registro local y continuar; si no propietario, sin acción. Salida: bloqueo liberado o sin acción. Excepción: fallo tras reintento no aborta.
6. **Terminar proceso**. Entrada: —. Proceso: cerrar nodo. Salida: fin de la corrida. Excepción: ninguna.

### Dependencias y contratos
- **Antecesores**: rama No de la decisión de candidatas (`sin_pendientes`); Exportar ofertas; abortos de cualquier nodo (`error_critico`/`aborto`); INICIO ERR-06 (`concurrencia`).
- **Sucesor**: ninguno (fin de la corrida de exportación).
- **Contratos consumidos**: `id_corrida`, `hubo_candidatas`, contadores, motivo/estado, estado de bloqueo.
- **Impactos aprobados**: el bloqueo global se libera para la siguiente corrida de cualquier módulo; los lotes quedan disponibles para la importación manual; el orquestador transversal lee el cierre desde la base como en los demás módulos.

### Notas de implementación
- Liberación de bloqueo condicional a propiedad; fallo cubierto por obsolescencia.
- Cierre best-effort ante contexto corrupto: ningún error de los pasos 1-5 aborta.
- Métricas por eventos, no por tablas completas.
- El aviso de la tanda programada lee `evaluacion_pendiente` para informar "evaluación exportada, pendiente de importar" con el número de lotes en espera.

---

## Flujo B — Importación de evaluaciones (lo lanza el operador con un comando)

## Nodo proceso: INICIO — Arranque de la corrida de importación
**Versión**: 2.0 (aprobada)

### Posición
Punto de entrada único del flujo de importación; precede toda decisión y acción de negocio. Ninguna decisión posterior puede ejecutarse sin el contexto producido aquí.

### Objetivo
Instanciar la corrida de importación (corrida propia del módulo) y preparar el contexto de ejecución: trazabilidad, configuración validada (sección `evaluacion_manual:` completa), BD disponible, concurrencia (bloqueo global compartido con los Módulos 1 y 2), carpeta de trabajo disponible, archivos de resultados y estado inicial. **No aplica evaluaciones** (eso corresponde al nodo Importar evaluaciones).

### Descripción funcional
Al recibir disparador:
1. Crea instancia de corrida con `id_corrida` único y `fecha_inicio`, **antes** de intentar el bloqueo, para que toda corrida registrada pueda cerrarse.
2. Carga configuración y valida nivel global: **toda** la sección `evaluacion_manual:` — `carpeta_base`, `tamano_lote`, `modelo_evaluador` y `retries`. No valida ninguna ruta de inteligencia artificial.
3. Verifica disponibilidad y permisos de escritura de la BD del módulo (prueba de escritura con rollback).
4. Valida concurrencia mediante bloqueo persistente **global compartido** con los Módulos 1 y 2.
5. Comprueba la carpeta de trabajo: crea `carpeta_base`, `lotes/` y `resultados/` si faltan y verifica lectura y escritura; la ausencia se resuelve creando, solo un fallo de permisos aborta.
6. Carga archivos de resultados: listado de `resultados/` ordenado por nombre (corrida, lote y parte), sin leer su contenido.
7. Inicializa estado: contadores (`aprobadas`, `descartadas`, `rechazadas`, `errores`, `lotes`) abiertos en cero y `hubo_resultados` (bool) en el contexto.
8. Entrega control al nodo siguiente.

Error fatal de inicialización, carpeta no disponible o concurrencia activa producen terminación controlada en `"Finalizar Proceso"` antes de tocar cualquier archivo.

### Responsabilidad
- **Negocio**: arrancar la corrida de importación y verificar precondiciones operativas. No decide si hay resultados ni aplica evaluaciones.
- **Técnica**: `id_corrida`, conexión, bloqueo de concurrencia global, carpeta de trabajo, listado de resultados, estado inicial.
- **Límite**: garantiza contexto y archivos listados; no garantiza que el contenido sea válido. No accede a inteligencia artificial ni a red.

### Entradas
- Disparador manual (comando de importación).
- Almacén de configuración: sección `evaluacion_manual:` completa (`carpeta_base`, `tamano_lote`, `modelo_evaluador`, `retries`) + `concurrencia` (umbral de obsolescencia).
- Estado persistente de bloqueo, si existe.
- BD con `ofertas_descubiertas`.
- Carpeta de trabajo con los archivos que dejó el chat.

### Salidas
- Contexto inicializado: `id_corrida`, fecha_inicio, archivos de resultados ordenados, `hubo_resultados`, contadores, conexión activa, bloqueo adquirido, rutas de carpeta resueltas.
- Terminación en `"Finalizar Proceso"` con `abortada`/`concurrencia` si aplica.
- Control normal al nodo de decisión "¿Hay resultados para importar?".

### Reglas de negocio
- **RN-01**: toda corrida tiene `id_corrida` único; todo registro del proceso queda enlazado a él.
- **RN-02**: solo una ejecución activa a la vez en todo el pipeline (bloqueo global compartido Módulos 1/2/3).
- **RN-03**: el iterador de archivos se reinicia al inicio de cada corrida; la corrida procesa la lista cargada en orden.
- **RN-04**: este nodo no valida si hay resultados; esa validación es del nodo de decisión siguiente.
- **RN-05**: este nodo no lee el contenido de los archivos ni escribe en la base de ofertas.
- **RN-06**: los archivos se ordenan por nombre, que codifica corrida, número de lote y parte; el orden es determinista.
- **RN-07**: este nodo no accede a inteligencia artificial, red ni credenciales.
- **RN-08**: la corrida se registra antes de intentar el bloqueo, para que toda corrida abierta sea cerrable.

### Validaciones
- **VAL-01**: `id_corrida` único y no nulo.
- **VAL-02**: configuración global: sección `evaluacion_manual:` completa y con rangos válidos (`carpeta_base` no vacía, `tamano_lote` entero ≥ 1, `modelo_evaluador` no vacío, `retries` coherente). Sin ruta de inteligencia artificial.
- **VAL-03**: BD: conexión abierta y prueba de escritura exitosa con rollback.
- **VAL-04**: bloqueo legible; obsolescencia por marca_temporal contra umbral configurable; marcas temporales coherentes.
- **VAL-05**: carpeta de trabajo accesible y escribible (base, `lotes/`, `resultados/`); se crea lo que falte.
- **VAL-06**: contexto completo antes de entregar control (`hubo_resultados` presente).
- **VAL-07**: listado de resultados ordenado por nombre; conteo ≥ 0.

### Condiciones
- **Continuación normal**: configuración válida + BD disponible + carpeta disponible + sin concurrencia activa.
- **Terminación**: configuración ausente/ilegible/corrupta; BD indisponible/bloqueada/sin permisos; carpeta no creable o no escribible; concurrencia activa; estado de bloqueo no decidible.
- **Sin resultados**: no termina aquí; el nodo de decisión siguiente resuelve `sin_resultados`.

### Ramas
- **Normal** → `"¿Hay resultados para importar?"`.
- **Excepción** → `"Finalizar Proceso"` con estado `abortada` o motivo `concurrencia`.

### Errores y excepciones

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---|---|---|---|
| ERR-01 | Colisión o fallo de generación de `id_corrida` | 1 | Registro crítico local | Reintento único; si persiste, aborto | `abortada` |
| ERR-02 | Configuración ausente | 2 | Registro crítico local | Aborto | `abortada` |
| ERR-03 | Configuración ilegible | 2 | Registro crítico local | Aborto | `abortada` |
| ERR-04 | Configuración corrupta / estructura inconsistente | 2 | Registro crítico local | Aborto | `abortada` |
| ERR-05 | BD indisponible / bloqueada / sin permisos | 3 | Evento crítico si accesible; si no, local | Aborto | `abortada` |
| ERR-06 | Concurrencia activa | 4 | Evento "finalización por concurrencia" | Terminación controlada | `concurrencia` |
| ERR-07 | Bloqueo obsoleto (antigüedad > umbral) | 4 | Suceso de sobrescritura | Sobrescribir bloqueo y continuar | continúa |
| ERR-08 | Estado de bloqueo no decidible | 4 | Evento crítico | Aborto | `abortada` |
| ERR-09 | Contienda de adquisición de bloqueo | 4 | — | Atomicidad/unicidad; perdedor cae en ERR-06 | `concurrencia` |
| ERR-10 | Carpeta de trabajo no creable o sin permiso de escritura | 5 | Evento crítico si accesible | Aborto | `abortada` |
| ERR-11 | Falla interna de inicialización de estado | 7 | Evento crítico si accesible | Aborto | `abortada` |

### Dependencias y contratos
- **Antecesor**: ninguno.
- **Sucesor normal**: `"¿Hay resultados para importar?"`.
- **Sucesor de excepción**: `"Finalizar Proceso"`.
- **Contrato entregado**: contexto completo como única interfaz; archivos de resultados ordenados con `hubo_resultados`; rutas de carpeta resueltas.
- **Impactos aprobados**:
  - `"Finalizar Proceso"` libera el bloqueo y consume `hubo_resultados` para `error_total`.
  - El nodo Importar evaluaciones procesa la lista en el orden entregado.
  - `corridas` suma el vocabulario `sin_resultados`.

### Notas de implementación
- Espejo del INICIO de los Módulos 1 y 2: mismo mecanismo de bloqueo, `sondear_escritura`, `registrar_corrida` y `generar_id`.
- Orden obligatorio: configuración antes que BD; carpeta después del bloqueo; listado después de BD y bloqueo.
- No acceder a inteligencia artificial, red ni plataformas; sin credenciales.
- Sin valores fijos: carpeta y modelo evaluador desde la sección `evaluacion_manual:`.
- El disparador es un comando de operador de una línea; el módulo no lo llama solo.

### Pasos funcionales
1. **Recibir disparador e instanciar corrida**. Entrada: comando del operador. Proceso: crear instancia, generar `id_corrida`, fecha_inicio. Salida: instancia. Val: VAL-01. Err: ERR-01.
2. **Cargar configuración y validar nivel global**. Entrada: almacén de configuración. Proceso: leer y validar la sección `evaluacion_manual:` completa (claves y rangos). Salida: configuración cruda en contexto. Val: VAL-02. Err: ERR-02, ERR-03, ERR-04.
3. **Verificar BD**. Entrada: parámetros de conexión. Proceso: abrir conexión; prueba de escritura con rollback. Salida: conexión disponible. Val: VAL-03. Err: ERR-05.
4. **Validar concurrencia**. Entrada: `id_corrida`, estado de bloqueo, umbral. Proceso: leer bloqueo global compartido; activo no obsoleto → terminación controlada; obsoleto → sobrescribir y continuar; inexistente → marcar bloqueo. Salida: bloqueo adquirido o terminación. Val: VAL-04. Err: ERR-06, ERR-07, ERR-08, ERR-09.
5. **Comprobar carpeta de trabajo**. Entrada: `carpeta_base`. Proceso: crear las carpetas faltantes y verificar lectura y escritura. Salida: rutas resueltas. Val: VAL-05. Err: ERR-10.
6. **Cargar archivos de resultados**. Entrada: `resultados/`. Proceso: listar y ordenar por nombre, sin leer contenido. Salida: lista de archivos. Val: VAL-07. Err: ERR-10.
7. **Inicializar estado**. Entrada: archivos listados. Proceso: abrir contadores (`aprobadas`, `descartadas`, `rechazadas`, `errores`, `lotes`) en cero y fijar `hubo_resultados` (bool). Salida: contexto completo. Val: VAL-06. Err: ERR-11.
8. **Entregar control**. Entrada: contexto completo. Proceso: cerrar nodo. Salida: flujo a la decisión de resultados. Val: VAL-06. Err: contexto incompleto → ERR-11.

---

## Nodo decisión: "¿Hay resultados para importar?"
**Versión**: 2.0 (aprobada)

### Posición
Primera decisión de negocio del flujo de importación, inmediatamente después del INICIO. Espejo de `"¿Hay ofertas preparadas?"` del flujo de exportación.

### Objetivo
Decidir si la corrida importa o termina controladamente según exista al menos un archivo de resultados en la carpeta.

### Descripción funcional
Lee del contexto la lista de archivos de resultados, sin releer la carpeta. Si hay ≥ 1 archivo, entrega control al nodo Importar evaluaciones con contrato "lista no vacía". Si hay 0, fija motivo `sin_resultados` —suceso, no error— y entrega control a `"Finalizar Proceso"`. No realiza I/O, no accede a red, no revalida estructura.

### Entradas
Contexto de INICIO: lista de archivos, `hubo_resultados`, `id_corrida`, conexión activa, bloqueo adquirido, rutas de carpeta.

### Salidas
- **Sí** → Importar evaluaciones con lista no vacía.
- **No** → `"Finalizar Proceso"` con motivo `sin_resultados`.
- **Falla interna** → `"Finalizar Proceso"` con estado `abortada`.

### Reglas de negocio
- **RN-01**: evaluar solo contexto; prohibido releer la carpeta o la BD.
- **RN-02**: "resultado" = archivo listado por INICIO en `resultados/`; no hay otras fuentes.
- **RN-03**: no revalidar estructura; ya lo hizo INICIO.
- **RN-04**: ausencia de archivos es terminación controlada `sin_resultados`, tipo suceso (estado `sin_pendientes` en `corridas`).
- **RN-05**: este nodo no registra; `"Finalizar Proceso"` registra la terminación.
- **RN-06**: rama Sí garantiza lista no vacía; ningún nodo posterior revalida existencia.

### Validaciones
- **VAL-01**: lista de archivos accesible en contexto.
- **VAL-02**: evaluación sobre lista leída; conteo entero ≥ 0; sin revalidación.
- **VAL-03**: rama Sí solo con conteo > 0.
- **VAL-04**: en rama No, `sin_resultados` fijado con `id_corrida` y marca_temporal antes de entregar control.

### Condiciones y ramas
- **Sí**: conteo > 0 → Importar evaluaciones.
- **No**: conteo == 0 → `"Finalizar Proceso"` con `sin_resultados`.
- **Aborto**: contexto sin lista de archivos o incompleto → `"Finalizar Proceso"` con `abortada`.

### Errores

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---|---|---|---|
| ERR-01 | Contexto sin lista de archivos o incompleto | 1 | Evento crítico si accesible | Aborto | `abortada` |

### Dependencias y contratos
- **Antecesor**: INICIO.
- **Sucesor Sí**: Importar evaluaciones.
- **Sucesor No**: `"Finalizar Proceso"` con `sin_resultados`.
- **Impactos aprobados**: ningún nodo posterior revalida existencia; `"Finalizar Proceso"` incorpora `sin_resultados`; la rama Sí entrega la lista en el orden de nombre cargado por INICIO.

### Notas de implementación
- Nodo de evaluación pura: sin I/O, sin red, sin escritura, salvo fijar motivo en rama No.
- Leer la lista del mismo objeto de contexto; no copiar ni transformar.

### Pasos funcionales
1. **Leer lista del contexto**. Entrada: contexto. Proceso: acceder a lista; no releer la carpeta. Salida: lista posiblemente vacía. Val: VAL-01. Err: ERR-01.
2. **Evaluar existencia**. Entrada: lista. Proceso: contar; condición = conteo > 0. Salida: Sí/No. Val: VAL-02. Err: ninguna.
3. **Rama Sí**. Entrada: resultado Sí. Proceso: entregar control. Salida: flujo a Importar evaluaciones. Val: VAL-03. Err: ninguna.
4. **Rama No**. Entrada: resultado No, `id_corrida`. Proceso: fijar `sin_resultados` y entregar control. Salida: flujo a `"Finalizar Proceso"`. Val: VAL-04. Err: ninguna.

---

## Nodo proceso: "Importar evaluaciones"
**Versión**: 2.0 (aprobada)

### Posición
Entre la rama Sí de `"¿Hay resultados para importar?"` y `"Finalizar Proceso"`. Nodo de proceso por lotes: recorre todos los archivos antes de entregar control. Sucesor único: `"Finalizar Proceso"`.

### Objetivo
Aplicar a cada oferta el resultado que devolvió el chat, con validación estricta, y dejar cerrado cada lote: lo aplicado queda en la base y los archivos se eliminan. **No completa, no corrige y no adivina nada**: una línea inválida se rechaza y su oferta sigue pendiente.

### Descripción funcional
Flujo por lote, en orden de nombre (orden obligatorio):

| # | Paso | Qué hace | Fuente |
|---|---|---|---|
| 1 | **Emparejar** | Une cada archivo de resultados con su lote y su ficha de control por el nombre base (corrida + lote + parte). Sin lote conocido, el archivo se rechaza completo | `resultados/` + `lotes/` |
| 2 | **Leer y limpiar** | Una línea por oferta; descarta adornos del chat (bloques de código, texto suelto, líneas vacías) | Archivo de resultados |
| 3 | **Validar cada línea** | Formato, existencia de la oferta, estado `preparada`, 5 vetos, decisión coherente, justificación y entregable con contenido, sin duplicados | Línea + BD |
| 4 | **Aplicar las válidas** | Estado `aceptada_ei`/`descartada_ei`, resultado completo con el modelo evaluador, evento y contador | BD |
| 5 | **Rechazar las inválidas** | Evento de error con el motivo exacto; la oferta sigue en `preparada`; suma en rechazadas | BD |
| 6 | **Comparar con lo esperado** | Identifica los identificadores de la ficha de control que no llegaron o no se aplicaron | Ficha de control |
| 7 | **Cerrar el lote** | Si todas sus ofertas quedaron resueltas, borra los tres archivos; si falta alguna, conserva el lote completo y lo informa | Carpeta + BD |
| 8 | **Registrar el lote** | Suceso con aplicadas, rechazadas, faltantes y archivos eliminados | `eventos` |

Un lote con faltantes no se borra mientras conserve ofertas pendientes. Un lote resuelto se borra completo (texto, ficha y respuesta, incluidas sus partes). **Todos los eventos de oferta llevan `id_oferta`; los de lote llevan el nombre del archivo y el `id_corrida`.** En la importación ese campo es el id de la corrida de importación (para que el cierre pueda medir sus propios eventos); el id de la exportación viaja dentro del nombre del lote (`<id_corrida>_lote_<NNN>`).

### Entradas
- Contexto: lista de archivos no vacía, `id_corrida`, configuración (`carpeta_base`, `modelo_evaluador`, `retries`), contadores.
- BD: `ofertas_descubiertas`.
- Carpetas: `lotes/` (lotes y fichas de control) y `resultados/` (respuestas del chat).

### Salidas
- Ofertas aprobadas en `aceptada_ei` con `resultado_evaluacion_inicial` diligenciado.
- Ofertas descartadas en `descartada_ei` con `resultado_evaluacion_inicial` diligenciado.
- Ofertas rechazadas que siguen en `preparada` con `resultado_evaluacion_inicial = 'N/A'`.
- Eventos por oferta y por lote.
- Lotes resueltos eliminados de la carpeta; lotes incompletos conservados.
- Contadores al día.
- Control único a `"Finalizar Proceso"`.
- Aborto → `"Finalizar Proceso"` con `abortada`.

### Reglas de negocio
- **RN-01**: por lotes: este nodo recorre todos los archivos antes de entregar control.
- **RN-02**: manda el archivo: se aplica lo que trae, sin completar campos ausentes ni reinterpretar la decisión.
- **RN-03**: validación estricta: 5 vetos con valor válido, decisión coherente con ellos, justificación con contenido real y entregable con contenido real —única excepción: `N/A` admitido en el descarte por falta de descripción (`v3 = FAIL` y `DESCARTADA`)—, oferta existente y en `preparada`, e identificador incluido en la ficha de control del lote (aprobado en la Fase 3: una respuesta no puede evaluar ofertas de otro lote).
- **RN-04**: una línea inválida se rechaza entera; la oferta no cambia de estado. Nunca se descarta por una duda ni por un dato faltante.
- **RN-05**: una oferta no se aplica dos veces: si ya no está en `preparada`, la línea se rechaza como "ya no pendiente" y se informa.
- **RN-06**: la aprobada se marca `aceptada_ei` y la descartada `descartada_ei`, pasando por `evaluada` en el mismo movimiento. `aceptada_ei`/`descartada_ei` son estados propios de esta fase.
- **RN-07**: `resultado_evaluacion_inicial` guarda el resultado completo (entregable principal, v1–v5, decisión, justificación y `evaluador`). `DEFAULT 'N/A'`; pendiente de evaluar = `'N/A'`. El entregable solo puede ser `'N/A'` en el descarte por falta de descripción (`v3 = FAIL` y `DESCARTADA`): única excepción a la validación de contenido de D52, cumpliendo D31.
- **RN-08**: persistencia inmediata por oferta: cada resultado válido se escribe de una vez (estado + resultado + evento + cuenta) antes de tomar la siguiente.
- **RN-09**: cierre de lote: se considera resuelto cuando todas sus ofertas están aplicadas o ya no están en `preparada`; solo entonces se borran los tres archivos. Con una oferta todavía pendiente, el lote completo se conserva.
- **RN-10**: el borrado es definitivo y ocurre únicamente después de verificar en la base lo aplicado; lo evaluado vive en la base y los archivos eran transporte.
- **RN-11**: no se sobrescribe `ofertas_descubiertas.id_corrida` (sigue siendo la de descubrimiento); la trazabilidad de la importación vive en `eventos`.
- **RN-12**: el modelo evaluador sale de configuración y queda escrito en cada resultado; reemplaza al campo de la puerta que respondió.
- **RN-13**: descartar es decisión de negocio (suceso), no error. Solo el rechazo de una línea es error.

### Validaciones
- **VAL-01**: insumos presentes (lista no vacía, configuración, carpetas, BD).
- **VAL-02**: todo archivo de resultados tiene lote y ficha de control con el mismo nombre base; un archivo sin pareja se rechaza completo, se informa y se aparta a `resultados/rechazados/` (no se borra y no se vuelve a procesar).
- **VAL-03**: lectura línea por línea; una línea es un objeto JSON con `id`; los adornos se descartan antes de validar.
- **VAL-04**: por línea — identificador incluido en la ficha de control del lote; oferta existente; estado `preparada`; `v1`–`v5` presentes con valor `PASS`/`FAIL`; `decision` ∈ {`APROBADA`, `DESCARTADA`} y coherente (aprobada exige los cinco `PASS`; descartada exige al menos un `FAIL`); `justificacion` con contenido real (no vacía, no `N/A`/`N/R`); `entregable_principal` con contenido real, con una única excepción: se admite `N/A` cuando `v3 = FAIL` y la decisión es `DESCARTADA` (oferta sin descripción; excepción a la validación de contenido de D52, cumpliendo D31); oferta no repetida en el lote ni en otro archivo.
- **VAL-05**: la comparación con la ficha de control identifica con nombre y número los identificadores faltantes.
- **VAL-06**: lo aplicado respeta D31 (sin vacíos; el único `'N/A'` admitido en el entregable es el del descarte por falta de descripción); el estado final corresponde a la decisión; el resultado queda completo.
- **VAL-07**: el borrado ocurre solo tras verificar en la base todas las ofertas del lote (aplicadas o ya no pendientes), y borra las tres piezas del lote.
- **VAL-08**: evento escrito con `id_oferta`; evidencia acotada.

### Condiciones
- **Normal**: líneas aplicadas, rechazadas o lotes conservados.
- **Rechazo de línea**: no aborta; la oferta queda pendiente y se continúa.
- **Lote incompleto**: no aborta; se conserva y se informa.
- **Aborto**: insumos ausentes/corruptos; fallo persistente al aplicar una línea válida; corrupción de contexto.

### Ramas
- Normal única → `"Finalizar Proceso"`.
- Aborto → `"Finalizar Proceso"` con `abortada`.

### Errores y eventos

| Código | Error / evento | Reint. | Detección | Registro / acción | Estado |
|---|---|---|:---:|---|---|
| ERR-01 | Insumos ausentes/corruptos | No | 1 | Evento crítico; aborto | `abortada` |
| ERR-02 | Archivo de resultados sin lote o ficha de control | No | 1 | Se rechaza el archivo completo; evento de error con su nombre y se aparta a `resultados/rechazados/` (no se borra y no se repite el error) | `preparada` (sin cambios) |
| ERR-03 | Línea ilegible, sin `id` o sin los 5 vetos | No | 2-3 | Se rechaza la línea; se informa; se cuenta rechazo | `preparada` |
| ERR-04 | Oferta inexistente, no pendiente, repetida o fuera de la ficha del lote | No | 3 | Se rechaza la línea; nunca se cambia el estado | `preparada` |
| ERR-05 | Decisión incoherente con los vetos, o justificación/entregable vacíos (salvo `entregable_principal = 'N/A'` en el descarte por falta de descripción) | No | 3 | Se rechaza la línea; se informa | `preparada` |
| ERR-06 | Fallo persistente al aplicar una línea válida | Sí (`retries`) | 4 | Reintento; agotado → aborto (no se puede garantizar integridad) | `abortada` |
| ERR-07 | Faltantes contra la ficha de control | No | 6-7 | El lote no se cierra: se conserva completo y se informa qué falta | `preparada` |
| ERR-08 | Fallo al borrar los archivos de un lote resuelto | Sí (`retries`) | 7 | Reintento; agotado → registro local y se informa; la base ya está escrita | continúa |
| EVT-01 | `oferta_aprobada` | No | 4 | Suceso con `id_oferta` | continúa |
| EVT-02 | `oferta_descartada` | No | 4 | Suceso con `id_oferta` | continúa |
| EVT-03 | `evaluacion_rechazada` | No | 2-3 | Error con `id_oferta` y motivo del rechazo | `preparada` |
| EVT-04 | `evaluaciones_importadas` | No | 8 | Suceso con lote, aplicadas, rechazadas, faltantes y archivos eliminados | continúa |
| EVT-05 | `lote_conservado` | No | 7 | Suceso con el lote, los archivos conservados y los identificadores faltantes | continúa |

### Escenarios límite
- **Respuesta cortada a mitad**: se guarda la continuación como `<id_corrida>_lote_<NNN>_parte2.jsonl`; el nodo une las partes en orden. Si aun así falta una oferta, el lote se conserva y se informa.
- **Oferta ya evaluada** (llegó en dos lotes): la segunda línea se rechaza como "ya no pendiente"; el lote se cierra si el resto está resuelto.
- **Archivo vacío o solo con adornos**: se rechaza el archivo completo (ERR-02/ERR-03) y se informa.
- **Todos los lotes completos**: se aplican y se borran; la carpeta queda vacía y la siguiente exportación no encuentra pendientes.
- **Un lote con rechazos**: se conserva con lo rechazado y lo faltante; las ofertas afectadas siguen en `preparada` dentro de ese lote y se resuelven completando su respuesta (añadiendo las líneas que faltan al mismo archivo), no con una exportación nueva: mientras el lote exista, el guardián no genera lotes.
- **Descripción vacía**: no afecta la importación; el chat debió marcarla V3 `FAIL`, la decisión coherente la descarta y el entregable puede venir como `N/A`.
- **Fallo de la base a mitad de un lote**: lo aplicado persiste; lo no aplicado sigue pendiente; el lote no se cierra.

### Dependencias y contratos
- **Antecesor**: `"¿Hay resultados para importar?"` rama Sí.
- **Sucesor normal**: `"Finalizar Proceso"`.
- **Sucesor de aborto**: `"Finalizar Proceso"`.
- **Contratos consumidos**: lista de archivos; lotes y fichas de control de la exportación; configuración de evaluación manual.
- **Contratos entregados**: ofertas en `aceptada_ei`/`descartada_ei` con resultado completo; rechazadas en `preparada`; eventos con `id_oferta`; lotes resueltos eliminados; contadores al día.
- **Impactos aprobados**:
  - `"Finalizar Proceso"` cuenta `aprobadas`, `descartadas` y `rechazadas`.
  - El catálogo de estados mantiene `aceptada_ei`/`descartada_ei` sin cambios.
  - La carpeta queda limpia de lotes resueltos: no se acumulan archivos ni trabajo repetido.

### Notas de implementación
- Formato de línea: `{"id","entregable_principal","v1","v2","v3","v4","v5","decision","justificacion"}`; una por oferta; UTF-8.
- El limpiador de adornos descarta bloques de código, líneas de relleno y texto fuera de las llaves.
- La justificación y el entregable se guardan íntegros; los topes de la instrucción (60 y 20 palabras) son criterio de redacción, no de rechazo, para no destruir datos.
- Transiciones `preparada → evaluada → aceptada_ei` y `preparada → evaluada → descartada_ei` en el mismo movimiento (la máquina de estados no admite salto directo).
- El borrado se hace por lote, con verificación previa en la base; nunca se borra un lote con ofertas pendientes y nunca se borra antes de escribir.
- `evaluador` sale de `evaluacion_manual.modelo_evaluador` (por ejemplo `chat: gemini`); queda dentro del resultado guardado.
- La importación no genera instrucciones ni lotes; eso corresponde al flujo de exportación.
- Sin valores fijos: carpeta y modelo evaluador desde configuración.

### Pasos funcionales
1. **Leer insumos**. Entrada: contexto, configuración, carpetas. Proceso: verificar lista no vacía, ajustes completos y carpetas legibles. Salida: insumos. Val: VAL-01. Err: ERR-01.
2. **Emparejar archivos**. Entrada: `resultados/`, `lotes/`. Proceso: unir cada respuesta con su lote y ficha por nombre base; descartar archivos sin pareja. Salida: pares listos. Val: VAL-02. Err: ERR-02.
3. **Leer y limpiar líneas**. Entrada: archivo de resultados. Proceso: quitar adornos; obtener una línea por oferta. Salida: líneas. Val: VAL-03. Err: ERR-03.
4. **Validar cada línea**. Entrada: línea, BD, ficha. Proceso: aplicar VAL-04 completa. Salida: válidas y rechazadas con motivo. Val: VAL-04. Err: ERR-03, ERR-04, ERR-05.
5. **Aplicar las válidas**. Entrada: líneas válidas. Proceso: `aceptada_ei`/`descartada_ei` vía `evaluada`; guardar resultado con `evaluador`; evento de éxito; sumar. Salida: ofertas aplicadas. Val: VAL-06, VAL-08. Err: ERR-06, EVT-01, EVT-02.
6. **Rechazar las inválidas**. Entrada: líneas rechazadas. Proceso: evento de error con motivo; oferta sigue `preparada`; sumar en rechazadas. Salida: ofertas pendientes. Val: VAL-08. Err: EVT-03.
7. **Comparar con lo esperado**. Entrada: ficha de control, aplicadas. Proceso: identificar faltantes o no aplicadas. Salida: lista de faltantes. Val: VAL-05. Err: ERR-07.
8. **Cerrar el lote**. Entrada: lote, ficha, faltantes. Proceso: si todo está resuelto, borrar los tres archivos; si no, conservarlos. Salida: lote cerrado o conservado. Val: VAL-07. Err: ERR-07, ERR-08, EVT-04, EVT-05.
9. **Repetir y entregar control**. Entrada: archivos restantes. Proceso: siguiente lote hasta agotar; cerrar nodo. Salida: flujo a `"Finalizar Proceso"`. Err: ninguna.

---

## Nodo terminal: "Finalizar Proceso (importación)"
**Versión**: 2.0 (aprobada)

### Identificación
Punto de convergencia de todas las terminaciones del flujo de importación. Espejo de `"Finalizar Proceso"` de los Módulos 1 y 2, con motivos y métricas propios. Sin sucesor: fin de la corrida de importación.

### Objetivo
Cerrar la corrida de importación de forma determinista, con trazabilidad completa y con el informe que el operador necesita:
1. consultar métricas por eventos;
2. escribir evento de terminación;
3. persistir cierre de corrida;
4. cerrar recursos abiertos;
5. liberar bloqueo de concurrencia si esta corrida lo posee;
6. informar al operador;
7. terminar proceso.

### Descripción funcional (pasos en orden obligatorio)

| # | Paso | Qué hace | Fuente |
|---|---|---|---|
| 1 | **Consultar métricas** | Contar por eventos de la corrida: aprobadas, descartadas, rechazadas, errores y sucesos; definir motivo según tabla oficial | `eventos` |
| 2 | **Escribir evento de terminación** | Suceso o error según el motivo; evidencia con métricas (`campo=valor`) | `eventos` |
| 3 | **Persistir cierre de corrida** | Estado, `fecha_fin`, `motivo_terminacion`, métricas (1 reintento, nunca aborta) | `corridas` |
| 4 | **Cerrar recursos** | Cerrar la conexión (best-effort) | — |
| 5 | **Liberar bloqueo** | Solo si la corrida lo posee | `bloqueo` |
| 6 | **Informar al operador** | Resumen en pantalla y aviso de escritorio: aplicadas, rechazadas, lotes cerrados y ofertas que siguen pendientes | — |

**Nota as-built (Fase 3, decisión aprobada):** el cierre calcula y devuelve el informe del operador, pero no lo imprime ni envía el aviso de escritorio; el paso 6 lo ejecuta el comando de importación de la Fase 4. Así la capa de operación sigue intacta durante la construcción.

### Entradas
Contexto best-effort:
- motivo/estado de terminación: `corrida_completada`, `sin_resultados`, `error_total`, `error_critico`, `aborto`, `concurrencia`;
- `id_corrida`; `hubo_resultados` (bool, del INICIO); contadores (`aprobadas`, `descartadas`, `rechazadas`, `errores`, `lotes`);
- estado de bloqueo; conexión de BD.

### Salidas
- Evento de terminación persistido en `"errores o sucesos"` o registro crítico local si falla escritura.
- Corrida cerrada (estado, `fecha_fin`, motivo y métricas).
- Recursos cerrados; bloqueo liberado si esta corrida lo poseía.
- Informe del operador y aviso de escritorio.
- Sin sucesor: fin de la corrida de importación.

### Ramas
No es nodo de decisión.

### Estados/motivos oficiales

| Motivo | Cuándo | Estado `corridas` | Tipo de evento |
|---|---|---|---|
| `corrida_completada` | ≥ 1 oferta aplicada entre aprobadas y descartadas | `completada` | suceso |
| `sin_resultados` | Sin archivos en `resultados/` | `sin_pendientes` | suceso |
| `error_total` | `hubo_resultados` = sí pero ninguna línea válida y ≥ 1 rechazo o error | `abortada` | error |
| `error_critico` | Fallo crítico de BD/config/carpeta en cualquier nodo | `abortada` | error |
| `aborto` | Fallo de un nodo en el flujo | `abortada` | error |
| `concurrencia` | INICIO ERR-06 (no obtuvo el bloqueo global) | `abortada` | suceso |

**Fuente del dato:** `hubo_resultados` (bool) lo registra el INICIO en el contexto; el paso 1 lo usa para distinguir `error_total` de `sin_resultados`.

### Métricas (por eventos)
- `aprobadas` = eventos `oferta_aprobada` de la corrida → columna propia `total_aprobadas` en `corridas`.
- `descartadas` = eventos `oferta_descartada` de la corrida → columna propia `total_descartadas` en `corridas`.
- `rechazadas` = eventos `evaluacion_rechazada` de la corrida (queda en la evidencia del cierre; no hay columna propia).
- `errores` = eventos de error de la corrida → `total_errores`.
- `sucesos` = sucesos escritos **antes** del evento de terminación (el evento de cierre nunca se cuenta) → `total_sucesos`.
- `ofertas únicas evaluadas` = unión sin repetir entre aprobadas y descartadas → `total_ofertas`; `fuentes_procesadas` = 0 (sin fuentes).
- `lotes` = parejas lote/respuesta procesadas (aplicadas, conservadas o rechazadas).

No se sobrescribe `ofertas_descubiertas.id_corrida` (sigue siendo la corrida de descubrimiento; la trazabilidad de la evaluación vive en `eventos`).

### Especificación funcional
1. **Consultar métricas**. Entrada: `eventos`, `id_corrida`, `hubo_resultados`. Proceso: contar por eventos; decidir motivo según tabla oficial. Salida: métricas + motivo. Excepción: fallo de conteo → reintento único; si persiste, motivo por defecto `aborto` con métricas vacías y continuar.
2. **Escribir evento de terminación**. Entrada: estado, motivo, `id_corrida`, métricas. Proceso: suceso o error según motivo con evidencia `campo=valor`; fallo → reintento único; si persiste, registro crítico local y continuar. Salida: evento persistido o registro local. Excepción: fallo tras reintento no aborta.
3. **Persistir cierre de corrida**. Entrada: estado, motivo, métricas. Proceso: guardar estado, `fecha_fin`, `motivo_terminacion` y métricas; 1 reintento; nunca aborta. Salida: corrida cerrada. Excepción: fallo tras reintento → registro local y continuar.
4. **Cerrar recursos (best-effort)**. Entrada: conexión BD. Proceso: cerrar; errores se registran localmente y no impiden terminación. Salida: recursos cerrados. Excepción: errores de cierre no abortan.
5. **Liberar bloqueo si corresponde**. Entrada: estado de bloqueo, `id_corrida`. Proceso: si el bloqueo existe y el propietario == `id_corrida`, liberar; fallo → reintento único; si persiste, registro local y continuar; si no propietario, sin acción. Salida: bloqueo liberado o sin acción. Excepción: fallo tras reintento no aborta.
6. **Informar al operador**. Entrada: métricas, lotes cerrados y conservados, ofertas pendientes. Proceso: resumen legible en pantalla y aviso de escritorio; best-effort, nunca altera el resultado ni el cierre. Salida: informe entregado. Excepción: fallo del aviso → solo registro local.
7. **Terminar proceso**. Entrada: —. Proceso: cerrar nodo. Salida: fin de la corrida. Excepción: ninguna.

### Dependencias y contratos
- **Antecesores**: rama No de la decisión de resultados (`sin_resultados`); Importar evaluaciones; abortos de cualquier nodo (`error_critico`/`aborto`); INICIO ERR-06 (`concurrencia`).
- **Sucesor**: ninguno (fin de la corrida de importación).
- **Contratos consumidos**: `id_corrida`, `hubo_resultados`, contadores, motivo/estado, estado de bloqueo.
- **Impactos aprobados**: el bloqueo global se libera para la siguiente corrida de cualquier módulo; las ofertas quedan evaluadas y la fase profunda lee `aceptada_ei` con su resultado; la carpeta queda limpia de lotes resueltos.

### Notas de implementación
- Liberación de bloqueo condicional a propiedad; fallo cubierto por obsolescencia.
- Cierre best-effort ante contexto corrupto: ningún error de los pasos 1-6 aborta.
- Métricas por eventos, no por tablas completas.
- El aviso de escritorio es el mismo mecanismo del veredicto de la tanda, con texto propio de la importación; nunca modifica el resultado de la corrida.
- El informe nombra los lotes conservados y las ofertas que siguen pendientes, para que el operador sepa qué volver a evaluar.

---

## Pendientes de construcción e integración (aprobados)

1. **Instrucción del chat:** `instruccion_evaluacion.md` se genera en la exportación desde el prompt oficial `prompts/initial_evaluation/compatibility.md` (v6, D58), con una sección nueva de formato de salida (una línea JSON por oferta, incluida la excepción de `entregable_principal = 'N/A'` cuando la oferta no trae descripción y se descarta por `v3 = FAIL`) y la orden de procesar el archivo del lote. Sin llaves, sin ruta de modelo y sin ejemplos de puertas.
2. **Comando de importación (nuevo):** pieza de la capa de operación, de una línea, que lanza el flujo de importación, muestra el informe y envía el aviso de escritorio. No requiere argumentos; opera sobre la carpeta configurada.
3. **Orquestador del módulo:** dos entradas públicas — la exportación (la usa la tanda programada) y la importación (la usa el comando manual), con el mismo patrón de cierre para toda corrida registrada.
4. **Orquestador transversal:** el módulo sigue tercero en la lista, ahora exportando; el resultado se lee desde la base como los demás y el cierre del módulo es `evaluacion_pendiente` cuando hay lotes esperando. La importación no forma parte de la tanda.
5. **Notificador de veredicto:** textos nuevos para "evaluación exportada, pendiente de importar" (con número de lotes) y para el resultado de la importación.
6. **Tablero y centinela:** el catálogo de motivos suma `evaluacion_pendiente` y `sin_resultados`; sin cambios estructurales, porque las corridas siguen durando segundos.
7. **Prevuelo:** deja de exigir modelos y llaves de evaluación; valida la sección `evaluacion_manual:` y la carpeta de trabajo.
8. **Retiro de la ruta de IA de evaluación:** se eliminan de configuración `ai_routing.evaluation` y la sección `evaluacion:` completa (pausa, jitter, espera por puerta, reintentos y puertas alternas). Las entradas `OPENROUTER_API_KEY_1/2/3` y todas las claves de la sección `preparacion:` **se conservan**: las usa el clasificador de ubicaciones (D75), que no forma parte de este rediseño y no debe tocarse.
