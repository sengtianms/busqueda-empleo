# Especificación canónica densificada — Módulo 3: Evaluación inicial de ofertas

**Base de decisiones:** diagrama general del módulo aprobado (objetivo principal, 4 objetivos secundarios: el de copiar y organizar se retiró al eliminar el nodo, 4 nodos: Inicio, Hay ofertas por procesar, Evaluación inicial, Cierre). La evaluación inicial la realiza la inteligencia artificial elegida con 5 controles de veto sobre 4 datos de la oferta (título, descripción, modalidad, ubicación). Sin tope por vuelta; reintentos 2; la apertura no accede a la inteligencia artificial. El modelo a utilizar se confirma en la ruta existente (`ai_routing.evaluation` + modelo de la nube) sin duplicarlo en la sección `evaluacion:`. Al completar la ficha se reemplazarán las claves viejas de puntaje por las nuevas en ajustes y documentos, todo a la vez. Estructura espejo de las fichas de los Módulos 1 y 2.

## Convenciones comunes

- **Alcance del módulo**: leer las ofertas en `preparada` de `ofertas_descubiertas`, evaluar cada una con la inteligencia artificial (5 controles de veto) y cerrar la corrida con métricas propias. No realiza el análisis profundo (eso corresponde a la fase siguiente).
- **Contexto de ejecución**: única estructura/objeto transmitida a todos los nodos. Ningún nodo posterior reinicializa conexiones ni estado, salvo responsabilidad asignada.
- **Trazabilidad**: todo registro incluye `id_corrida`; los eventos de oferta incluyen `id_oferta` (éxito y fallo). `fuente_id = 'N/A'` en este módulo (sin fuentes; respeta no-vacíos D31).
- **Registro**: en `"errores o sucesos"` (`eventos`); si no está disponible, registro crítico local (consola/archivo documentado). Todo evento incluye `id_corrida`, marca_temporal, tipo y descripción; los eventos de oferta incluyen `id_oferta`.
- **Aborto**: terminación inmediata en `"Finalizar Proceso"` con estado `abortada` y motivo `error_critico`/`aborto`.
- **Terminación controlada/normal**: cierre sin trabajo (`sin_pendientes`) o con trabajo (`corrida_completada`); lo registra `"Finalizar Proceso"`.
- **Reintentos**: máximo global configurable (`retries`, sección `evaluacion:`); solo son reintentables los códigos declarados en cada nodo. Credenciales, tokens y cookies nunca se registran, evidencian ni persisten. La inteligencia artificial nunca frena la vuelta completa (best-effort por oferta: si falla tras los reintentos, la oferta queda pendiente de revisar y se continúa).
- **Regla de datos (D31)**: ningún campo vacío — `N/A`/`N/R` cuando no aplica; exenciones: `id_externo` (dedup) y `fecha_ultima_verificacion` (marcador de verificación del Módulo 2).

---

## Nodo proceso: INICIO — Arranque de la corrida e inicialización del contexto de ejecución
**Versión**: 1.0 (aprobada)

### Posición
Punto de entrada único del módulo; precede toda decisión y acción de negocio. Ninguna decisión posterior puede ejecutarse sin el contexto producido aquí.

### Objetivo
Instanciar la corrida de evaluación (corrida propia del módulo) y preparar el contexto de ejecución: trazabilidad, configuración validada (sección `evaluacion:` completa), BD disponible, concurrencia (bloqueo global compartido con los Módulos 1 y 2), ofertas candidatas y estado inicial. **No evalúa ofertas** (eso corresponde al nodo Evaluación inicial).

### Descripción funcional
Al recibir disparador:
1. Crea instancia de corrida con `id_corrida` único y `fecha_inicio`.
2. Carga configuración y valida nivel global: **toda** la sección `evaluacion:` — reintentos (`max_attempts: 2`), `pausa_entre_ofertas_segundos` — más la ruta existente de la inteligencia (`ai_routing.evaluation` con su modelo en la nube).
3. Verifica disponibilidad y permisos de escritura de la BD del módulo (prueba de escritura con rollback).
4. Valida concurrencia mediante bloqueo persistente **global compartido** con los Módulos 1 y 2.
5. Carga ofertas candidatas: SELECT de `ofertas_descubiertas` con estado `preparada`, orden FIFO (`fecha_descubrimiento ASC, id ASC`).
6. Inicializa estado: contadores (`aprobadas`, `descartadas`, `errores`) abiertos en cero y `hubo_candidatas` (bool) en el contexto — los nodos siguientes los van llenando y `"Finalizar Proceso"` los consume para el resumen y para distinguir `error_total` de `sin_pendientes`.
7. Entrega control al nodo siguiente.

Error fatal de inicialización o concurrencia activa producen terminación controlada en `"Finalizar Proceso"` antes de tocar cualquier oferta.

### Responsabilidad
- **Negocio**: arrancar corrida y verificar precondiciones operativas. No evalúa ofertas ni decide si hay pendientes.
- **Técnica**: `id_corrida`, conexión, bloqueo de concurrencia global, estado inicial, carga FIFO de candidatas.
- **Límite**: garantiza contexto y candidatas cargadas; no garantiza evaluación exitosa. No accede a la inteligencia artificial ni a plataformas.

### Entradas
- Disparador manual (hoy) o programado (futuro).
- Almacén de configuración: sección `evaluacion:` completa (reintentos, pausa) + ruta existente de la inteligencia (`ai_routing.evaluation`) + `concurrencia` (umbral de obsolescencia) + `retries`.
- Estado persistente de bloqueo, si existe.
- BD con `ofertas_descubiertas`.

### Salidas
- Contexto inicializado: `id_corrida`, fecha_inicio, candidatas FIFO, `hubo_candidatas`, contadores, conexión activa, bloqueo adquirido.
- Terminación en `"Finalizar Proceso"` con `abortada`/`concurrencia` si aplica.
- Control normal al nodo de decisión "Hay ofertas por procesar".

### Reglas de negocio
- **RN-01**: toda corrida tiene `id_corrida` único; todo registro del módulo queda enlazado a él.
- **RN-02**: solo una ejecución activa a la vez en todo el pipeline (bloqueo global compartido Módulos 1/2/3).
- **RN-03**: el iterador de candidatas se reinicia al inicio de cada corrida; la corrida procesa la lista cargada en orden.
- **RN-04**: este nodo no valida si hay ofertas pendientes; esa validación es del nodo de decisión siguiente.
- **RN-05**: este nodo no accede a la inteligencia artificial (eso es del nodo Evaluación inicial).
- **RN-06**: la corrida procesa todas las ofertas en `preparada` (sin tope por vuelta); el tiempo se acota por las pausas configuradas.
- **RN-07**: selección FIFO — más antiguas primero; las pendientes de corridas previas que sigan en `preparada` vuelven a juntarse en orden.
- **RN-08**: el modelo a utilizar se confirma en la ruta existente (`ai_routing.evaluation` con su modelo en la nube) y no se duplica en la sección `evaluacion:`.

### Validaciones
- **VAL-01**: `id_corrida` único y no nulo.
- **VAL-02**: configuración global: sección `evaluacion:` completa y con rangos válidos (reintentos coherentes con `max_attempts: 2`, pausas ≥ 0) más ruta `ai_routing.evaluation` existente con su modelo declarado.
- **VAL-03**: BD: conexión abierta y prueba de escritura exitosa con rollback.
- **VAL-04**: bloqueo legible; obsolescencia por marca_temporal contra umbral configurable; marcas temporales coherentes.
- **VAL-05**: contexto completo antes de entregar control (`hubo_candidatas` presente).
- **VAL-06**: candidatas cargadas en orden FIFO; conteo ≥ 0.

### Condiciones
- **Continuación normal**: configuración válida + BD disponible + sin concurrencia activa.
- **Terminación**: configuración ausente/ilegible/corrupta; BD indisponible/bloqueada/sin permisos; concurrencia activa; estado de bloqueo no decidible.
- **Sin candidatas**: no termina aquí; el nodo de decisión siguiente resuelve `sin_pendientes`.

### Ramas
- **Normal** → `"Hay ofertas por procesar"`.
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
- **Sucesor normal**: `"Hay ofertas por procesar"`.
- **Sucesor de excepción**: `"Finalizar Proceso"`.
- **Contrato entregado**: contexto completo como única interfaz; candidatas FIFO con `hubo_candidatas`.
- **Impactos aprobados**:
  - `"Finalizar Proceso"` libera el bloqueo y consume `hubo_candidatas` para `error_total`.
  - El nodo Evaluación inicial procesa la lista en el orden entregado.
  - `corridas` incorpora el vocabulario `sin_pendientes` (decisión aprobada).

### Notas de implementación
- Espejo del INICIO de los Módulos 1 y 2: mismo mecanismo de bloqueo, `sondear_escritura`, `registrar_corrida` y `generar_id`.
- Orden obligatorio: configuración antes que BD; candidatas después de BD y bloqueo.
- No acceder a la inteligencia artificial ni a plataformas; sin credenciales.
- Sin valores fijos: reintentos y pausas desde la sección `evaluacion:`; el modelo desde la ruta existente.
- Pausa por defecto espejo de Preparación (base 1,2 s con variación 0,4 s).

### Pasos funcionales
1. **Recibir disparador e instanciar corrida**. Entrada: evento manual/programado. Proceso: crear instancia, generar `id_corrida`, fecha_inicio. Salida: instancia. Val: VAL-01. Err: ERR-01.
2. **Cargar configuración y validar nivel global**. Entrada: almacén de configuración. Proceso: leer y validar la sección `evaluacion:` completa (claves y rangos) más la ruta `ai_routing.evaluation` con su modelo. Salida: configuración cruda en contexto. Val: VAL-02. Err: ERR-02, ERR-03, ERR-04.
3. **Verificar BD**. Entrada: parámetros de conexión. Proceso: abrir conexión; prueba de escritura con rollback. Salida: conexión disponible. Val: VAL-03. Err: ERR-05.
4. **Validar concurrencia**. Entrada: `id_corrida`, estado de bloqueo, umbral. Proceso: leer bloqueo global compartido; activo no obsoleto → terminación controlada; obsoleto → sobrescribir y continuar; inexistente → marcar bloqueo. Salida: bloqueo adquirido o terminación. Val: VAL-04. Err: ERR-06, ERR-07, ERR-08, ERR-09.
5. **Cargar ofertas candidatas**. Entrada: BD. Proceso: SELECT `preparada` orden FIFO (`fecha_descubrimiento ASC, id ASC`). Salida: lista de candidatas. Val: VAL-06. Err: ERR-05.
6. **Inicializar estado**. Entrada: candidatas. Proceso: abrir contadores (`aprobadas`, `descartadas`, `errores`) en cero y fijar `hubo_candidatas` (bool). Salida: contexto completo. Val: VAL-05. Err: ERR-10.
7. **Entregar control**. Entrada: contexto completo. Proceso: cerrar nodo. Salida: flujo a la decisión de candidatas. Val: VAL-05. Err: contexto incompleto → ERR-10.

---

## Nodo decisión: "Hay ofertas por procesar"
**Versión**: 1.0 (aprobada)

### Posición
Primera decisión de negocio, inmediatamente después de INICIO. Análoga a "¿Quedan ofertas por preparar en esta corrida?" del Módulo 2.

### Objetivo
Decidir si la corrida continúa o termina controladamente según exista al menos una oferta candidata en `preparada`.

### Descripción funcional
Lee la lista de candidatas del contexto en memoria, sin releer la BD. Si hay ≥ 1 candidata, entrega control al nodo Evaluación inicial con contrato "lista no vacía". Si hay 0, fija motivo `sin_pendientes` —suceso, no error— y entrega control a `"Finalizar Proceso"`. No realiza I/O, no accede a la inteligencia artificial, no revalida estructura.

### Entradas
Contexto de INICIO: lista de candidatas, `hubo_candidatas`, `id_corrida`, conexión activa, bloqueo adquirido.

### Salidas
- **Sí** → Evaluación inicial con lista no vacía.
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
- **Sí**: conteo > 0 → Evaluación inicial.
- **No**: conteo == 0 → `"Finalizar Proceso"` con `sin_pendientes`.
- **Aborto**: contexto sin lista de candidatas o incompleto → `"Finalizar Proceso"` con `abortada`.

### Errores

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---|---:|---|---|---|
| ERR-01 | Contexto sin lista de candidatas o incompleto | 1 | Evento crítico si accesible | Aborto | `abortada` |

### Dependencias y contratos
- **Antecesor**: INICIO.
- **Sucesor Sí**: Evaluación inicial.
- **Sucesor No**: `"Finalizar Proceso"` con `sin_pendientes`.
- **Impactos aprobados**: ningún nodo posterior revalida existencia; `"Finalizar Proceso"` incorpora `sin_pendientes`; la rama Sí entrega la lista en el orden FIFO cargado por INICIO.

### Notas de implementación
- Nodo de evaluación pura: sin I/O, sin red, sin escritura, salvo fijar motivo en rama No.
- Leer la lista del mismo objeto de contexto; no copiar ni transformar.

### Pasos funcionales
1. **Leer lista del contexto**. Entrada: contexto. Proceso: acceder a lista; no releer la BD. Salida: lista posiblemente vacía. Val: VAL-01. Err: ERR-01.
2. **Evaluar existencia**. Entrada: lista. Proceso: contar; condición = conteo > 0. Salida: Sí/No. Val: VAL-02. Err: ninguna.
3. **Rama Sí**. Entrada: resultado Sí. Proceso: entregar control. Salida: flujo a Evaluación inicial. Val: VAL-03. Err: ninguna.
4. **Rama No**. Entrada: resultado No, `id_corrida`. Proceso: fijar `sin_pendientes` y entregar control. Salida: flujo a `"Finalizar Proceso"`. Val: VAL-04. Err: ninguna.

---

## Nodo proceso: "Evaluación inicial"
**Versión**: 1.0 (aprobada)

### Posición
Entre la rama Sí de `"Hay ofertas por procesar"` y `"Finalizar Proceso"`. Nodo de proceso por lotes: evalúa toda la lista antes de entregar control. Sucesor único: `"Finalizar Proceso"`.

### Objetivo
Aplicar los 5 controles de veto a cada oferta candidata y dejarla marcada como aprobada, descartada o pendiente de revisar. Este nodo solo decide.

### Descripción funcional
Flujo por oferta, en orden FIFO (orden obligatorio):

| # | Paso | Qué hace | Fuente |
|---|---|---|---|
| 1 | **Armar los datos** | Toma título, descripción, modalidad y ubicación tal cual vienen | Lista del contexto |
| 2 | **Pedir la evaluación** | Llama a la inteligencia con los 5 controles; ante fallo de puerta reintenta hasta 2 veces; pausa entre ofertas | Inteligencia elegida |
| 3 | **Validar la respuesta** | Verifica 5 controles presentes, decisión coherente con ellos y explicación corta en una línea | Respuesta del paso 2 |
| 4 | **Anotar el resultado** | Marca estado, guarda el resultado completo, escribe el evento y suma en su cuenta | Pasos 2-3 |

En fallo persistente del paso 2 o respuesta inválida tras los reintentos: evento de error con `id_oferta`; la oferta queda pendiente de revisar en `preparada` y se continúa con la siguiente. **Todos los eventos de oferta llevan `id_oferta`, éxito y fallo.**

### Entradas
- Contexto: lista de candidatas no vacía, `id_corrida`, configuración (`pausa_entre_ofertas_segundos`, reintentos `max_attempts: 2`), contadores (`aprobadas`, `descartadas`, `errores`).
- BD: `ofertas_descubiertas`.
- Servicio de inteligencia (puerta principal + puertas alternas del mismo modelo).

### Salidas
- Ofertas aprobadas en `aceptada_ei` con `resultado_evaluacion_inicial` diligenciado.
- Ofertas descartadas en `descartada_ei` con `resultado_evaluacion_inicial` diligenciado.
- Ofertas con fallo persistente en `preparada` con `resultado_evaluacion_inicial = 'N/A'` (pendientes).
- Eventos por oferta con `id_oferta`.
- Contadores al día.
- Control único a `"Finalizar Proceso"`.
- Aborto → `"Finalizar Proceso"` con `abortada`.

### Reglas de negocio
- **RN-01**: por lotes: este nodo evalúa toda la lista antes de entregar control.
- **RN-02**: persistencia inmediata por oferta: cada resultado validado se escribe en la tabla de una vez (estado + columna de resultado + evento + cuenta) antes de tomar la siguiente.
- **RN-03**: la aprobada se marca `aceptada_ei` y la descartada `descartada_ei`, pasando por `evaluada` en el mismo movimiento. `aceptada_ei` / `descartada_ei` son estados propios de esta fase y se suman al catálogo oficial (la fase profunda usará los suyos).
- **RN-04**: la columna `resultado_evaluacion_inicial` guarda el resultado completo (v1–v5, decisión, explicación). `DEFAULT 'N/A'`; pendiente de evaluar = `'N/A'`.
- **RN-05**: la inteligencia recibe exactamente 4 datos (título, descripción, modalidad, ubicación). Ante duda o falta de información en tema, nivel o calidad, no descarta — con una excepción aprobada: sin descripción o con marca de no reportada → V3 FAIL. Modalidad y ubicación se aplican al pie de la letra aunque falte el dato.
- **RN-06**: reintento por oferta hasta 2 veces ante fallo de puerta o respuesta inválida; si persiste → pendiente en `preparada` (siguiente oferta, siguiente vuelta).
- **RN-07**: cambio de puerta ante fallo verificado de puerta (cupo lleno, puerta caída o sin respuesta, llave rechazada); ante respuesta mal formada se reintenta en la misma puerta sin tocar la siguiente. Puertas agotadas → pendientes y cierre por cupo.
- **RN-08**: pausa entre ofertas siempre, configurable.
- **RN-09**: descartar es decisión de negocio (suceso), no error. Solo el fallo de inteligencia es error.
- **RN-10**: evidencia acotada con la puerta que respondió; trazabilidad `id_corrida` + `id_oferta`. Credenciales, tokens y llaves nunca se registran.

### Validaciones
- **VAL-01**: insumos presentes (lista no vacía, configuración, ruta de inteligencia).
- **VAL-02**: los 4 datos tomados tal cual (sin interpretar ni completar).
- **VAL-03**: política de reintentos cumplida (≤ 2 por oferta); pausa aplicada entre ofertas.
- **VAL-04**: respuesta con v1–v5 presentes, decisión coherente con ellos y explicación en una línea de máximo 60 palabras con evidencia de la oferta (v4, D51).
- **VAL-05**: oferta anotada respeta D31 (sin vacíos); columna de resultado diligenciada o `'N/A'` si pendiente.
- **VAL-06**: evento escrito con `id_oferta`; evidencia acotada.

### Condiciones
- **Normal**: ofertas procesadas (aprobada, descartada o pendiente individual).
- **Fallo de oferta**: no aborta; oferta queda pendiente para la próxima vuelta.
- **Aborto**: insumos ausentes/corruptos; corrupción de contexto.

### Ramas
- Normal única → `"Finalizar Proceso"`.
- Aborto → `"Finalizar Proceso"` con `abortada`.

### Errores y eventos

| Código | Error / evento | Reint. | Detección | Registro / acción | Estado |
|---|---|---|:---:|---|---|---|
| ERR-01 | Insumos ausentes/corruptos | No | 1 | Evento crítico; aborto | `abortada` |
| ERR-02 | Fallo de puerta (cupo, caída, llave) | Sí | Paso 2 | Reintento y cambio de puerta verificado; agotadas → pendiente y se continúa | pendiente de revisar |
| ERR-03 | Respuesta inválida | Sí | Paso 3 | Reintento en la misma puerta; agotado → pendiente y se continúa | pendiente de revisar |
| ERR-04 | Fallo persistente de anotación de una oferta | No | Paso 4 | Evento crítico; aborto | `abortada` |
| EVT-01 | `oferta_aprobada` | No | Paso 4 | Suceso con `id_oferta` | continúa |
| EVT-02 | `oferta_descartada` | No | Paso 4 | Suceso con `id_oferta` y control que frenó | continúa |
| EVT-03 | `evaluacion_fallida` | No | Paso 2-3 | Error con `id_oferta`; oferta queda `preparada` | pendiente de revisar |

### Escenarios límite
- Descripción vacía, `N/A` o con marca de no reportada → V3 FAIL (excepción aprobada a la regla principal); la oferta queda descartada.
- Modalidad o ubicación ausentes → V4/V5 literales.
- Cupo agotado en todas las puertas → se deja de llamar; el resto queda pendiente; cierre por cupo.
- Vuelta frenada a mitad → lo anotado persiste; lo no tomado sigue en `preparada`.
- Sin aprobadas → entrega control igual al Cierre.

### Dependencias y contratos
- **Antecesor**: `"Hay ofertas por procesar"` rama Sí.
- **Sucesor normal**: `"Finalizar Proceso"`.
- **Sucesor de aborto**: `"Finalizar Proceso"`.
- **Contratos consumidos**: lista FIFO no vacía; configuración; ruta de inteligencia.
- **Contratos entregados**: ofertas en `aceptada_ei` / `descartada_ei` con resultado completo; pendientes en `preparada`; eventos con `id_oferta`; contadores al día.
- **Impactos aprobados**:
  - `"Finalizar Proceso"` cuenta `aprobadas` / `descartadas` / `errores` y distingue cierre por cupo.
  - El catálogo de estados suma `aceptada_ei` / `descartada_ei` (se registra con los documentos al cerrar la ficha).

### Notas de implementación
- Transiciones `preparada → evaluada → aceptada_ei` y `preparada → evaluada → descartada_ei` en el mismo movimiento (la máquina de estados no admite salto directo).
- Higiene de entrada (D49): la descripción enviada a la IA se limpia de secciones de ruido (empresa, beneficios, avisos EN/ES) con tope alto de seguridad; el original guardado no se toca (desviación aprobada de VAL-02 solo para la descripción; título, modalidad y ubicación van tal cual).
- Prompt `compatibility.md` v3 (D49): V1 con prueba del beneficiario final y exclusión estructural de fontanería de datos e infraestructura.
- Prompt `compatibility.md` v4 (D51): la justificación exige evidencia concreta de la oferta (eje + cita del texto + viabilidad, o veto + dato que lo activa), prohibición de frases genéricas y tope de 60 palabras (antes 20 en v3).
- Columna nueva `resultado_evaluacion_inicial` (`TEXT DEFAULT 'N/A'`, migración aditiva idempotente).
- Puertas alternas del mismo modelo con rotación de llaves (llaves solo en el archivo privado); la puerta que respondió queda en la evidencia.
- Sin valores fijos: reintentos, pausas y modelo desde ajustes.

### Pasos funcionales
1. **Leer insumos**. Entrada: contexto, configuración, ruta de inteligencia. Proceso: verificar lista no vacía, ajustes completos y ruta existente. Salida: insumos. Val: VAL-01. Err: ERR-01.
2. **Tomar la siguiente oferta**. Entrada: lista FIFO. Proceso: la más antigua sin procesar de esta vuelta; tomar sus 4 datos tal cual. Salida: oferta en mano. Val: VAL-02. Err: ERR-01.
3. **Pedir la evaluación**. Entrada: 4 datos, reintentos, puertas. Proceso: llamar con los 5 controles; fallo de puerta → reintento y cambio de puerta verificado; pausa entre ofertas. Salida: respuesta o fallo persistente. Val: VAL-03. Err: ERR-02, EVT-03.
4. **Validar la respuesta**. Entrada: respuesta. Proceso: 5 controles presentes, decisión coherente, explicación en una línea. Salida: válida o inválida. Val: VAL-04. Err: ERR-03, EVT-03.
5. **Anotar aprobada**. Entrada: respuesta válida aprobada. Proceso: marcar `aceptada_ei` vía `evaluada`; guardar resultado completo; evento de éxito; sumar en aprobadas. Salida: oferta anotada. Val: VAL-05, VAL-06. Err: ERR-04.
6. **Anotar descartada**. Entrada: respuesta válida descartada. Proceso: marcar `descartada_ei` vía `evaluada`; guardar resultado completo; evento con control que frenó; sumar en descartadas. Salida: oferta anotada. Val: VAL-05, VAL-06. Err: ERR-04.
7. **Anotar pendiente**. Entrada: fallo persistente. Proceso: evento de error; oferta sigue en `preparada` con resultado `'N/A'`; sumar en errores; continuar. Salida: oferta pendiente. Val: VAL-05, VAL-06. Err: ninguna.
8. **Repetir y entregar control**. Entrada: lista y cuentas. Proceso: una por una hasta acabar; cerrar nodo. Salida: flujo a `"Finalizar Proceso"`. Err: ninguna.

---

## Nodo terminal: "Finalizar Proceso"
**Versión**: 1.0 (aprobada)

### Identificación
Punto de convergencia de todas las terminaciones de la corrida. Espejo de `"Finalizar Proceso"` de los Módulos 1 y 2, con motivos y métricas propios. Sin sucesor: fin del proceso.

### Objetivo
Cerrar la corrida de evaluación de forma determinista y con trazabilidad completa:
1. consultar métricas por eventos;
2. escribir evento de terminación;
3. persistir cierre de corrida;
4. cerrar recursos abiertos;
5. liberar bloqueo de concurrencia si esta corrida lo posee;
6. terminar proceso.

### Descripción funcional (pasos en orden obligatorio)

| # | Paso | Qué hace | Fuente |
|---|---|---|---|
| 1 | **Consultar métricas** | Contar por eventos de la corrida: `aprobadas`, `descartadas`, `errores`, `sucesos`; definir motivo según tabla oficial | `eventos` |
| 2 | **Escribir evento de terminación** | Suceso o error según el motivo; evidencia con métricas (`campo=valor`) | `eventos` |
| 3 | **Persistir cierre de corrida** | Estado, `fecha_fin`, `motivo_terminacion`, métricas (1 reintento, nunca aborta) | `corridas` |
| 4 | **Cerrar recursos** | Cerrar la conexión (best-effort; este módulo no deja sesiones abiertas) | — |
| 5 | **Liberar bloqueo** | Solo si la corrida lo posee | `bloqueo` |

### Entradas
Contexto best-effort:
- motivo/estado de terminación: `sin_pendientes`, `corrida_completada`, `cupo_agotado`, `error_total`, `error_critico`, `aborto`, `concurrencia`;
- `id_corrida`; `hubo_candidatas` (bool, del INICIO); contadores (`aprobadas`, `descartadas`, `errores`);
- estado de bloqueo; conexión de BD.

### Salidas
- Evento de terminación persistido en `"errores o sucesos"` o registro crítico local si falla escritura.
- Corrida cerrada (estado, `fecha_fin`, motivo y métricas).
- Recursos cerrados; bloqueo liberado si esta corrida lo poseía.
- Sin sucesor: fin del proceso.

### Ramas
No es nodo de decisión.

### Estados/motivos oficiales

| Motivo | Cuándo | Estado `corridas` | Tipo de evento |
|---|---|---|---|
| `sin_pendientes` | Sin ofertas candidatas | `sin_pendientes` | suceso |
| `corrida_completada` | ≥ 1 oferta evaluada entre aprobadas y descartadas | `completada` | suceso |
| `cupo_agotado` | Pare ordenado por cupo de inteligencia con pendientes | `completada` | suceso |
| `error_total` | `hubo_candidatas` = sí pero ninguna evaluada y ≥ 1 error | `abortada` | error |
| `error_critico` | Fallo crítico de BD/config en cualquier nodo | `abortada` | error |
| `aborto` | Fallo de un nodo en el flujo | `abortada` | error |
| `concurrencia` | INICIO ERR-06 (no obtuvo el bloqueo global) | `abortada` | suceso |

**Fuente del dato:** `hubo_candidatas` (bool) lo registra el INICIO en el contexto; el paso 1 lo usa para distinguir `error_total` de `sin_pendientes`.

### Métricas (por eventos)
- `aprobadas` = eventos `oferta_aprobada` de la corrida → columna propia `total_aprobadas` en `corridas` (migración aditiva idempotente, espejo de Preparación).
- `descartadas` = eventos `oferta_descartada` de la corrida → columna propia `total_descartadas` en `corridas` (idem).
- `errores` = eventos de error de la corrida → `total_errores`.
- `sucesos` = sucesos escritos **antes** del evento de terminación (el evento de cierre nunca se cuenta) → `total_sucesos`.
- `ofertas únicas evaluadas` = unión sin repetir entre aprobadas y descartadas → `total_ofertas`; `fuentes_procesadas` = 0 (sin fuentes).

No se sobrescribe `ofertas_descubiertas.id_corrida` (sigue siendo la corrida de descubrimiento; la trazabilidad de evaluación vive en `eventos`).

### Especificación funcional
1. **Consultar métricas**. Entrada: `eventos`, `id_corrida`, `hubo_candidatas`. Proceso: contar por eventos; decidir motivo según tabla oficial. Salida: métricas + motivo. Excepción: fallo de conteo → reintento único; si persiste, motivo por defecto `aborto` con métricas vacías y continuar.
2. **Escribir evento de terminación**. Entrada: estado, motivo, `id_corrida`, métricas. Proceso: suceso o error según motivo con evidencia `campo=valor`; fallo → reintento único; si persiste, registro crítico local y continuar. Salida: evento persistido o registro local. Excepción: fallo tras reintento no aborta.
3. **Persistir cierre de corrida**. Entrada: estado, motivo, métricas. Proceso: guardar estado, `fecha_fin`, `motivo_terminacion` y métricas; 1 reintento; nunca aborta. Salida: corrida cerrada. Excepción: fallo tras reintento → registro local y continuar.
4. **Cerrar recursos (best-effort)**. Entrada: conexión BD. Proceso: cerrar; errores se registran localmente y no impiden terminación. Salida: recursos cerrados. Excepción: errores de cierre no abortan.
5. **Liberar bloqueo si corresponde**. Entrada: estado de bloqueo, `id_corrida`. Proceso: si el bloqueo existe y el propietario == `id_corrida`, liberar; fallo → reintento único; si persiste, registro local y continuar; si no propietario, sin acción. Salida: bloqueo liberado o sin acción. Excepción: fallo tras reintento no aborta.
6. **Terminar proceso**. Entrada: —. Proceso: cerrar nodo. Salida: fin de corrida. Excepción: ninguna.

### Dependencias y contratos
- **Antecesores**: rama No de la decisión de candidatas (`sin_pendientes`); Evaluación inicial; abortos de cualquier nodo (`error_critico`/`aborto`/`cupo_agotado`); INICIO ERR-06 (`concurrencia`).
- **Sucesor**: ninguno (fin del proceso).
- **Contratos consumidos**: `id_corrida`, `hubo_candidatas`, contadores, motivo/estado, estado de bloqueo.
- **Impactos aprobados**: el bloqueo global se libera para la siguiente corrida de cualquier módulo; la fase profunda lee `aceptada_ei` con su resultado.

### Notas de implementación
- Liberación de bloqueo condicional a propiedad; fallo cubierto por obsolescencia.
- Cierre best-effort ante contexto corrupto: ningún error de los pasos 1-5 aborta.
- Métricas por eventos, no por tablas completas.

---

## Pendientes de construcción e integración (aprobados)

1. **Puertas alternas (D50, construido):** sección propia en ajustes con el modelo y la lista de llaves en orden — la primera que responde manda. Tres puertas OpenRouter con el mismo Gemma 4 31B (`google/gemma-4-31b-it`, refs `OPENROUTER_API_KEY_1/2/3`). Las llaves viven solo en el archivo privado; aquí solo sus nombres.
2. **Orquestador del módulo:** espejo del de Preparación — recorrido lineal INICIO → decisión → Evaluación → Cierre, con cierre para toda vuelta registrada.
3. **Orquestador transversal:** tras la vuelta real de verificación del módulo solo, este módulo se suma tercero en la lista tras Preparación, con su resultado leído desde la base como los demás.
