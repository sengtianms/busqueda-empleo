# Especificación canónica densificada — Módulo 1: Descubrimiento de oportunidades

## Convenciones comunes

- **Alcance del módulo**: consultar fuentes configuradas, aplicar filtros básicos por `sets_de_filtros`, capturar y almacenar información original de ofertas según `politicas_de_captura`. No interpreta, clasifica, puntúa ni decide adecuación.
- **Contexto de ejecución**: única estructura/objeto transmitida a todos los nodos. Ningún nodo posterior reinicializa conexiones ni estado, salvo responsabilidad asignada.
- **Trazabilidad**: todo registro incluye `id_corrida`; cuando aplica, también `fuente_id`, `id_sesion` y `indice_set`.
- **Registro**: en `"errores o sucesos"` si está disponible; si no, registro crítico local (consola/archivo documentado). Todo evento incluye `id_corrida`, marca_temporal, tipo y descripción; los descartes/fallos por fuente incluyen `fuente_id`.
- **Aborto**: terminación inmediata en `"Finalizar Proceso"` con estado `error`.
- **Terminación controlada/normal**: cierre sin procesamiento o previsto; lo registra `"Finalizar Proceso"`.
- **Reintentos**: máximo global por defecto 2; backoff configurable. Solo son reintentables los códigos declarados en cada nodo. Credenciales, tokens y cookies nunca se registran, evidencian ni persisten.

---

## Nodo proceso: INICIO — Arranque de la corrida e inicialización del contexto de ejecución  
**Versión**: 1.3 (aprobada)

### Posición
Punto de entrada único del módulo; precede toda decisión y acción de negocio. El elemento punteado `"Descubrimiento de oportunidades"` es rótulo/disparador, no nodo ejecutable. Ninguna decisión posterior puede ejecutarse sin el contexto producido aquí.

### Objetivo
Instanciar la corrida y preparar el contexto de ejecución: trazabilidad, configuración validada y filtrada, conexiones, concurrencia y estado inicial.

### Descripción funcional
Al recibir disparador:
1. Crea instancia de corrida con `id_corrida` único y `fecha_inicio`.
2. Carga configuración y valida nivel global.
3. Verifica disponibilidad y permisos de escritura de las BD del módulo.
4. Valida concurrencia mediante bloqueo persistente.
5. Valida ficha por fuente y filtra la lista, descartando fuentes incompletas con evento crítico.
6. Inicializa estado: iterador sobre lista filtrada y contadores.
7. Entrega control al siguiente nodo.

Error fatal de inicialización o concurrencia activa producen terminación controlada en `"Finalizar Proceso"` antes de tocar cualquier fuente.

### Responsabilidad
- **Negocio**: arrancar corrida y verificar precondiciones operativas. No accede fuentes, no aplica filtros, no consulta ofertas, no valida existencia de fuentes.
- **Técnica**: `id_corrida`, conexiones, bloqueo de concurrencia, estado inicial.
- **Límite**: garantiza “ficha completa y consistente”; no garantiza ingreso ni captura exitosos. No accede al almacén seguro de credenciales ni a plataformas.

### Entradas
- Disparador manual o programado.
- Almacén de configuración: fuentes con ficha de acceso, `sets_de_filtros`, `politicas_de_captura`, parámetros globales —incluidos defaults de captura— y parámetros de conexión.
- Estado persistente de bloqueo, si existe.

### Salidas
- Contexto inicializado: `id_corrida`, fecha_inicio, lista filtrada de fuentes válidas —cada una con acceso, `sets_de_filtros` y políticas efectivas—, iterador en “ninguna fuente seleccionada aún”, contadores/variables, conexiones activas, bloqueo adquirido.
- Eventos de descarte por fuente incompleta, si aplica.
- Control normal al nodo siguiente.
- Terminación en `"Finalizar Proceso"` con estado `error` o `concurrencia`.

### Reglas de negocio
- **RN-01**: toda corrida tiene `id_corrida` único; todo registro del módulo queda enlazado a él.
- **RN-02**: solo una ejecución activa del módulo a la vez.
- **RN-03**: el iterador de fuentes se reinicia al inicio de cada corrida; formalizado en `"¿Quedan fuentes por procesar en esta corrida?"` v1.0.
- **RN-04**: este nodo no valida si existen fuentes configuradas; esa validación es del nodo siguiente.
- **RN-05**: este nodo no accede fuentes ni ejecuta búsquedas.
- **RN-06**: todo error fatal de inicialización termina la corrida antes de cualquier procesamiento.
- **RN-07**: identificadores de fuente únicos por configuración; validados aquí y sostienen la trazabilidad por `fuente_id` de nodos posteriores.
- **RN-08**: toda fuente debe tener ficha completa y consistente:
  - esquema de acceso: URL/plataforma, tipo `publico|con_autenticacion`, referencia de credenciales si `con_autenticacion`, criterio verificable de ingreso exitoso, timeout;
  - `sets_de_filtros`: lista no vacía; cada set es lista de filtros, posiblemente vacía = búsqueda base;
  - `politicas_de_captura` consistente si presente.  
  Fuente incompleta/inconsistente se descarta con evento crítico; la corrida continúa con las válidas.
- **RN-09**: este nodo no ejecuta validaciones runtime: resolución de credenciales, validez de credenciales, alcanzabilidad, criterios de éxito y aplicabilidad de filtros pertenecen a `"Entrar a la fuente seleccionada"`.
- **RN-10**: el mecanismo de captura (masivo vs incremental) es del adaptador de plataforma; la configuración solo lo acota vía `politicas_de_captura`. Justificación: el mecanismo depende de la plataforma; configurarlo generaría inconsistencias fuente-adaptador.
- **RN-11**: `politicas_de_captura` ausente o parcial → defaults globales; si presente, validar rangos y tipos.

### Validaciones
- **VAL-01**: `id_corrida` único y no nulo.
- **VAL-02**: configuración global: almacén existente/legible, estructura consistente, identificadores de fuente únicos. No valida completitud por fuente ni lista vacía.
- **VAL-03**: BD: conexiones abiertas y prueba de escritura exitosa con rollback.
- **VAL-04**: bloqueo legible; obsolescencia por marca_temporal contra umbral configurable; marcas temporales coherentes.
- **VAL-05**: contexto completo antes de entregar control.
- **VAL-06**: ficha por fuente completa/consistente; incumplimientos se descartan sin abortar.

### Condiciones
- **Continuación normal**: configuración global válida + BD disponibles + sin concurrencia activa. Descartes ERR-12 no impiden continuar.
- **Terminación**: configuración ausente/ilegible/corrupta; IDs duplicados; BD indisponible/bloqueada/sin permisos; concurrencia activa; estado de bloqueo no decidible.
- **Descarte por fuente**: no termina la corrida; emite evento crítico y filtra la lista. Si no quedan fuentes, el nodo siguiente resuelve `sin_fuentes`.

### Ramas
- **Normal** → `"¿Existe al menos una fuente/plataforma de empleo configurada?"`.
- **Excepción** → `"Finalizar Proceso"` con estado `error` o `concurrencia`.

### Errores y excepciones

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---:|---|---|---|
| ERR-01 | Colisión o fallo de generación de `id_corrida` | 1 | Registro crítico local | Reintento único; si persiste, aborto | `error` |
| ERR-02 | Configuración ausente | 2 | Registro crítico local | Aborto | `error` |
| ERR-03 | Configuración ilegible | 2 | Registro crítico local | Aborto | `error` |
| ERR-04 | Configuración corrupta / estructura global inconsistente | 2 | Registro crítico local | Aborto | `error` |
| ERR-05 | BD indisponible / bloqueada / sin permisos | 3 | Evento crítico en `"errores o sucesos"` si accesible; si no, local | Aborto | `error` |
| ERR-06 | Concurrencia activa | 4 | Evento “finalización por concurrencia” | Terminación controlada | `concurrencia` |
| ERR-07 | Bloqueo obsoleto (antigüedad > umbral) | 4 | Suceso de sobrescritura | Sobrescribir bloqueo y continuar | continúa |
| ERR-08 | Estado de bloqueo no decidible | 4 | Evento crítico | Aborto | `error` |
| ERR-09 | Contienda de adquisición de bloqueo | 4 | — | Atomicidad/unicidad; perdedor cae en ERR-06 | `concurrencia` |
| ERR-10 | Falla interna de inicialización de estado | 6 | Evento crítico en `"errores o sucesos"` | Aborto | `error` |
| ERR-11 | IDs de fuente duplicados | 2 | Registro crítico local | Aborto | `error` |
| ERR-12 | Ficha por fuente incompleta/inconsistente | 5 | Evento crítico con `id_corrida` + `fuente_id` | Descartar fuente y continuar | continúa |

### Dependencias y contratos
- **Antecesor**: ninguno.
- **Sucesor normal**: `"¿Existe al menos una fuente/plataforma de empleo configurada?"`.
- **Sucesor de excepción**: `"Finalizar Proceso"`.
- **Contrato entregado**: contexto completo como única interfaz; lista contiene solo fuentes estructuralmente válidas, con `sets_de_filtros` y políticas resueltas.
- **Impactos aprobados**:
  - `id_corrida` se registra en BD del módulo.
  - `"Finalizar Proceso"` libera el bloqueo.
  - RN-03 formalizada en `"¿Quedan fuentes por procesar…?"` v1.0.
  - RN-07 sostiene trazabilidad por `fuente_id` en `"Seleccionar la siguiente fuente pendiente"`.
  - `"Entrar a la fuente seleccionada"` asume ficha completa y posee validaciones runtime.
  - `"Aplicar filtros básicos"` v1.1 itera `sets_de_filtros`; el iterador de sets se reinicia al cambiar de fuente.
  - `"Capturar ofertas"` consume políticas efectivas; el adaptador define mecanismo de captura.

### Notas de implementación
- Agnóstico de tecnología.
- Contexto como única estructura/objeto.
- Bloqueo persistente con `id_corrida` y marca_temporal; umbral de obsolescencia configurable.
- Registro crítico local documentado.
- Prueba de escritura con rollback.
- Orden obligatorio: configuración antes que BD; validación por fuente después de BD y bloqueo para persistir descartes y evitar trabajo concurrente.
- No acceder al almacén seguro ni a plataformas; referencia de credenciales solo se valida como campo presente y consistente.
- `politicas_de_captura`: resolver defaults en carga y exponer valores efectivos; rangos: `max_paginas` ≥ 1, `max_ofertas_por_corrida` ≥ 1, `pausa_entre_lotes` ≥ 0; `estrategia_anti_bloqueo` dentro del conjunto definido.
- `sets_de_filtros`: preservar orden; set vacío = búsqueda base.
- No implementar lógica de negocio ni validación de existencia de fuentes.

### Pasos funcionales
1. **Recibir disparador e instanciar corrida**. Entrada: evento manual/programado. Proceso: crear instancia, generar `id_corrida`, fecha_inicio. Salida: instancia. Val: VAL-01. Err: ERR-01.
2. **Cargar configuración y validar nivel global**. Entrada: almacén de configuración. Proceso: leer; validar legibilidad, estructura, unicidad de IDs. No valida completitud por fuente ni lista vacía. Salida: configuración cruda en contexto. Val: VAL-02. Err: ERR-02, ERR-03, ERR-04, ERR-11.
3. **Verificar BD**. Entrada: parámetros de conexión de `"Ofertas Totales"`, `"errores o sucesos"`, `"control de sesiones"` y demás. Proceso: abrir conexiones; prueba de escritura con rollback. Salida: conexiones disponibles. Val: VAL-03. Err: ERR-05.
4. **Validar concurrencia**. Entrada: `id_corrida`, estado de bloqueo, umbral. Proceso: leer bloqueo; activo no obsoleto → terminación controlada; obsoleto → sobrescribir y continuar; inexistente → marcar bloqueo. Salida: bloqueo adquirido o terminación. Val: VAL-04. Err: ERR-06, ERR-07, ERR-08, ERR-09.
5. **Validar fichas y filtrar lista**. Entrada: configuración cruda. Proceso: por fuente, validar ficha; resolver políticas efectivas; fuente válida → conservar; inválida → evento crítico y descarte. Salida: lista filtrada con políticas efectivas; eventos. Val: VAL-06. Err: ERR-12.
6. **Inicializar estado**. Entrada: `id_corrida`, lista filtrada. Proceso: fijar iterador en “ninguna fuente seleccionada aún”; inicializar contadores. Salida: contexto completo. Val: iterador/contadores iniciales. Err: ERR-10.
7. **Entregar control**. Entrada: contexto completo. Proceso: cerrar nodo. Salida: flujo a `"¿Existe al menos una fuente/plataforma de empleo configurada?"`. Val: VAL-05. Err: contexto incompleto → ERR-10.

---

## Nodo decisión: “¿Existe al menos una fuente/plataforma de empleo configurada?”  
**Versión**: 1.0 (aprobada)

### Posición
Primera decisión de negocio, inmediatamente después de INICIO. Posición definitiva.

### Objetivo
Decidir si la corrida continúa o termina controladamente según exista al menos una fuente configurada.

### Descripción funcional
Lee la lista de fuentes del contexto en memoria, sin releer almacén. Si hay ≥ 1 fuente, entrega control al nodo siguiente con contrato “lista no vacía”. Si hay 0, fija motivo `sin_fuentes` —suceso, no error— y entrega control a `"Finalizar Proceso"`. No realiza I/O, no accede fuentes, no revalida estructura.

### Entradas
Contexto de INICIO: lista de fuentes, `id_corrida`, conexiones activas, bloqueo adquirido.

### Salidas
- **Sí** → `"¿Es la primera ejecución del ciclo?"` con lista no vacía.
- **No** → `"Finalizar Proceso"` con motivo `sin_fuentes`.
- **Falla interna** → `"Finalizar Proceso"` con estado `error`.

### Reglas de negocio
- **RN-01**: evaluar solo contexto; prohibido releer almacén.
- **RN-02**: “fuente configurada” = presente en configuración cargada; no hay estados habilitada/deshabilitada.
- **RN-03**: no revalidar estructura; ya lo hizo INICIO.
- **RN-04**: ausencia de fuentes es configuración válida; rama No = terminación controlada `sin_fuentes`, tipo suceso.
- **RN-05**: este nodo no registra; `"Finalizar Proceso"` registra la terminación.
- **RN-06**: rama Sí garantiza lista no vacía; ningún nodo posterior revalida existencia.

### Validaciones
- **VAL-01**: lista de fuentes accesible en contexto.
- **VAL-02**: evaluación sobre lista leída; conteo entero ≥ 0; sin revalidación.
- **VAL-03**: rama Sí solo con conteo > 0.
- **VAL-04**: en rama No, `sin_fuentes` fijado con `id_corrida` y marca_temporal antes de entregar control.

### Condiciones y ramas
- **Sí**: conteo > 0 → `"¿Es la primera ejecución del ciclo?"`.
- **No**: conteo == 0 → `"Finalizar Proceso"` con `sin_fuentes`.
- **Aborto**: contexto sin configuración/incompleto → `"Finalizar Proceso"` con `error`.

### Errores

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---:|---|---|---|
| ERR-01 | Contexto sin configuración o incompleto | 1 | Evento crítico en `"errores o sucesos"` | Aborto | `error` |

### Dependencias y contratos
- **Antecesor**: INICIO.
- **Sucesor Sí**: `"¿Es la primera ejecución del ciclo?"`; pendiente redefinición según RN-03 de INICIO; la salida Sí no cambia.
- **Sucesor No**: `"Finalizar Proceso"` con `sin_fuentes`.
- **Impactos aprobados**: ningún nodo posterior revalida existencia; `"Finalizar Proceso"` incorpora `sin_fuentes`.

### Notas de implementación
- Nodo de evaluación pura: sin I/O, sin red, sin escritura, salvo fijar motivo en rama No.
- No implementar revalidación estructural ni estados de fuente.
- Leer la lista del mismo objeto de contexto; no copiar ni transformar.

### Pasos funcionales
1. **Leer lista del contexto**. Entrada: contexto. Proceso: acceder a lista; no releer almacén. Salida: lista posiblemente vacía. Val: VAL-01. Err: ERR-01.
2. **Evaluar existencia**. Entrada: lista. Proceso: contar; condición = conteo > 0. Salida: Sí/No. Val: VAL-02. Err: ninguna.
3. **Rama Sí**. Entrada: resultado Sí. Proceso: entregar control. Salida: flujo a `"¿Es la primera ejecución del ciclo?"`. Val: VAL-03. Err: ninguna.
4. **Rama No**. Entrada: resultado No, `id_corrida`. Proceso: fijar `sin_fuentes` y entregar control. Salida: flujo a `"Finalizar Proceso"`. Val: VAL-04. Err: ninguna.

---

## Nodo decisión: “¿Quedan fuentes por procesar en esta corrida?”  
**Versión**: 1.0 (aprobada)

### Posición
Punto único de control del bucle de fuentes. Recibe:
- rama Sí de `"¿Existe al menos una fuente/plataforma de empleo configurada?"`;
- retorno desde registro de ingreso fallido;
- retorno desde registro de búsqueda sin ofertas;
- rama No de `"¿Quedan sets de filtros por aplicar en esta fuente?"`.

### Objetivo
Determinar si quedan fuentes pendientes. Sí → selección de fuente. No → terminación normal `corrida_completada`.

### Descripción funcional
Lee lista e iterador del contexto. Calcula pendientes = fuentes no marcadas procesadas, en orden de configuración. No avanza iterador ni marca fuentes; eso pertenece a `"Seleccionar la siguiente fuente pendiente"`.

### Entradas
Contexto: lista de fuentes no vacía, iterador, `id_corrida`.

### Salidas
- **Sí** → `"Seleccionar la siguiente fuente pendiente"` con contrato de siguiente pendiente.
- **No** → `"Finalizar Proceso"` con `corrida_completada`.
- **Falla interna** → `"Finalizar Proceso"` con `error`.

### Reglas de negocio
- **RN-01**: solo contexto; prohibido releer almacén.
- **RN-02**: pendiente = no marcada como procesada; orden de configuración.
- **RN-03**: fuente fallida se considera procesada; no se reselecta. Reintentos internos de `"Entrar a la fuente seleccionada"` ocurren dentro de una pasada y no alteran el iterador.
- **RN-04**: este nodo no avanza ni marca; evaluación pura.
- **RN-05**: rama No = terminación normal `corrida_completada`, tipo suceso; registra `"Finalizar Proceso"`.
- **RN-06**: rama Sí garantiza siguiente fuente pendiente en orden.

### Validaciones
- **VAL-01**: iterador y lista accesibles y coherentes.
- **VAL-02**: cálculo solo sobre datos leídos; conteo ≥ 0; orden respetado.
- **VAL-03**: Sí solo con pendientes > 0.
- **VAL-04**: en No, `corrida_completada` fijado con `id_corrida` y marca_temporal.

### Condiciones y ramas
- **Sí**: pendientes > 0 → `"Seleccionar la siguiente fuente pendiente"`.
- **No**: pendientes == 0 → `"Finalizar Proceso"` con `corrida_completada`.
- **Aborto**: iterador ausente/corrupto → `"Finalizar Proceso"` con `error`.

### Errores

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---:|---|---|---|
| ERR-01 | Iterador ausente o corrupto | 1 | Evento crítico en `"errores o sucesos"` | Aborto | `error` |

### Dependencias y contratos
- **Antecesores**: rama Sí de existencia y tres retornos del bucle.
- **Sucesor Sí**: `"Seleccionar la siguiente fuente pendiente"`.
- **Sucesor No**: `"Finalizar Proceso"`.
- **Impactos aprobados**:
  - `"Seleccionar la siguiente fuente pendiente"` es único responsable de avanzar/marcar.
  - `"Finalizar Proceso"` incorpora `corrida_completada`.
  - Nodos de procesamiento asumen fuente corriente válida.

### Notas de implementación
- Evaluación pura; sin I/O, sin mutación de iterador.
- Iterador como estado de corrida en contexto; reiniciado por corrida; progreso de procesadas; orden de configuración.
- No reintentar ni reevaluar fuentes fallidas.

### Pasos funcionales
1. **Leer estado de iteración**. Entrada: contexto. Proceso: acceder a lista e iterador. Salida: datos de iteración. Val: VAL-01. Err: ERR-01.
2. **Calcular pendientes**. Entrada: lista, iterador. Proceso: pendientes = no procesadas en orden; condición = conteo > 0. Salida: Sí/No. Val: VAL-02. Err: ninguna.
3. **Rama Sí**. Entrada: resultado Sí. Proceso: entregar control. Salida: flujo a `"Seleccionar la siguiente fuente pendiente"`. Val: VAL-03. Err: ninguna.
4. **Rama No**. Entrada: resultado No, `id_corrida`. Proceso: fijar `corrida_completada` y entregar control. Salida: flujo a `"Finalizar Proceso"`. Val: VAL-04. Err: ninguna.

---

## Nodo proceso: “Seleccionar la siguiente fuente pendiente”  
**Versión**: 1.0 (aprobada)

### Posición
Entre rama Sí de `"¿Quedan fuentes por procesar en esta corrida?"` y `"Entrar a la fuente seleccionada"`.

### Objetivo
Avanzar el iterador, marcar como procesada la fuente seleccionada y exponer la fuente corriente con sus parámetros.

### Descripción funcional
Identifica la primera entrada no procesada en orden de configuración, la marca como procesada en el momento de selección, la fija como fuente corriente con `fuente_id`, posición, acceso y filtros básicos, y entrega control.

### Entradas
Contexto con contrato Sí: lista, iterador, `id_corrida`, existencia de fuente pendiente.

### Salidas
- Contexto actualizado: iterador avanzado; fuente marcada procesada; fuente corriente definida.
- Control a `"Entrar a la fuente seleccionada"` con contrato “fuente corriente válida”.
- Falla interna → `"Finalizar Proceso"` con `error`.

### Reglas de negocio
- **RN-01**: solo contexto; prohibido releer almacén.
- **RN-02**: selección = primera entrada no procesada en orden de configuración; clave = posición.
- **RN-03**: marcar procesada al seleccionar garantiza progreso ante fallas posteriores.
- **RN-04**: único nodo que avanza iterador y marca fuentes.
- **RN-05**: fuente corriente expone todos los parámetros requeridos: acceso y filtros básicos.
- **RN-06**: `fuente_id` + `id_corrida` deben incluirse en todo registro posterior.
- **RN-07**: no revalida estructura; responsabilidad de INICIO.

### Validaciones
- **VAL-01**: lista e iterador accesibles/coherentes.
- **VAL-02**: posición seleccionada no procesada y dentro de rango.
- **VAL-03**: tras mutación, iterador refleja procesada y fuente corriente tiene `fuente_id` y parámetros completos.

### Condiciones
- **Normal**: contrato Sí cumplido → selección, mutación y control.
- **Aborto**: iterador ausente/corrupto; ausencia de pendiente pese a contrato; falla al mutar contexto.

### Ramas
- Salida normal única → `"Entrar a la fuente seleccionada"`.
- Aborto → `"Finalizar Proceso"` con `error`.

### Errores

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---:|---|---|---|
| ERR-01 | Iterador ausente o corrupto | 1 | Evento crítico en `"errores o sucesos"` | Aborto | `error` |
| ERR-02 | Ausencia de fuente pendiente pese a contrato Sí | 2 | Evento crítico en `"errores o sucesos"` | Aborto | `error` |
| ERR-03 | Falla interna al mutar contexto | 3 | Evento crítico en `"errores o sucesos"` | Aborto | `error` |

### Dependencias y contratos
- **Antecesor**: `"¿Quedan fuentes por procesar…?"` rama Sí.
- **Sucesor**: `"Entrar a la fuente seleccionada"`.
- **Contrato consumido**: existe siguiente fuente pendiente.
- **Contrato entregado**: fuente corriente válida; ningún nodo posterior reselecta fuente.
- **Impactos aprobados**:
  - Bloque de procesamiento consume fuente corriente.
  - Filtros básicos se consumen en `"Aplicar filtros básicos"`.
  - Registros incorporan `fuente_id`.

### Notas de implementación
- Mutación atómica: marcar procesada + fijar fuente corriente.
- Iteración por posición; `fuente_id` solo trazabilidad.
- Sin red, sin ingreso, sin búsquedas.
- Sin revalidación estructural.

### Pasos funcionales
1. **Leer estado de selección**. Entrada: contexto. Proceso: acceder a lista e iterador. Salida: datos de selección. Val: VAL-01. Err: ERR-01.
2. **Determinar siguiente pendiente**. Entrada: lista, iterador. Proceso: primera entrada no procesada en orden. Salida: posición y `fuente_id`. Val: VAL-02. Err: ERR-02.
3. **Mutar contexto**. Entrada: posición y `fuente_id`. Proceso: marcar procesada; fijar fuente corriente con parámetros. Salida: contexto actualizado. Val: VAL-03. Err: ERR-03.
4. **Entregar control**. Entrada: contexto actualizado. Proceso: cerrar nodo. Salida: flujo a `"Entrar a la fuente seleccionada"` con trazabilidad. Val: contexto completo. Err: ninguna.

---

## Nodo proceso: “Entrar a la fuente seleccionada”  
**Versión**: 1.1 (aprobada)

### Posición
Entre `"Seleccionar la siguiente fuente pendiente"` y `"¿El ingreso fue exitoso?"`. Primer nodo que toca plataformas externas. Posición definitiva.

### Objetivo
Intentar acceso/ingreso a la plataforma de la fuente corriente según ficha de acceso, con reintentos condicionales, autenticar si corresponde, y producir:
- `entry_result` estructurado;
- sesión activa solo en éxito.

### Descripción funcional
Lee ficha de acceso del contexto. Si `con_autenticacion`, resuelve credenciales del almacén seguro. Abre canal y accede dentro del timeout. Autentica si aplica. Evalúa criterio verificable de éxito.

Ciclo de intento:
- códigos reintentables: `fuente_inalcanzable`, `tiempo_agotado_ingreso`;
- con intentos restantes: cerrar canal, backoff y reintentar desde acceso;
- código no reintentable o intentos agotados: evidencia de fallo.

Construye:
```text
entry_result = {
  estado: exito|fallo,
  codigo_motivo,
  evidencia_acotada,
  numero_de_intentos
}
```
En éxito crea `id_sesion` único y guarda handle + `id_sesion`. En fallo cierra canal y garantiza ausencia de sesión. Entrega control a `"¿El ingreso fue exitoso?"`.

### Entradas
- Contexto: fuente corriente con ficha completa: `fuente_id`, URL/plataforma, tipo `publico|con_autenticacion`, referencia de credenciales, criterio de éxito, filtros básicos, timeout; `id_corrida`.
- Parámetros globales de reintento/backoff; máximo por defecto 2.
- Almacén seguro de credenciales, accedido exclusivamente por este nodo.

### Salidas
- `entry_result` en contexto, sin datos sensibles.
- En éxito: sesión activa (`id_sesion` + handle).
- En fallo: canal cerrado, sin sesión.
- Control único a `"¿El ingreso fue exitoso?"`.
- Aborto → `"Finalizar Proceso"` con `error`.

### Reglas de negocio
- **RN-01**: opera sobre contexto; no relee almacén ni revalida ficha.
- **RN-02**: almacén seguro accedido solo aquí; credenciales/tokens nunca se registran ni persisten fuera de memoria.
- **RN-03**: reintentos condicionales hasta N configurables (default 2), con backoff, solo para `fuente_inalcanzable` y `tiempo_agotado_ingreso`. Cada reintento cierra canal previo y reejecuta desde acceso. No reintentables: `credenciales_no_disponibles`, `autenticacion_rechazada`, `bloqueo_plataforma`, `criterio_no_cumplido`, `error_interno_fuente`.
- **RN-04**: toda falla de intento produce evidencia de fallo; la fuente se omite aguas abajo. Aborto solo por violación de contrato/contexto.
- **RN-05**: `id_sesion` solo en éxito; en fallo canal cerrado y sin sesión.
- **RN-06**: evidencia acotada y sin datos sensibles.
- **RN-07**: eventos incluyen `id_corrida` y `fuente_id`.
- **RN-08**: no aplica filtros, no captura ofertas, no interpreta contenido.

### Validaciones
- **VAL-01**: ficha accesible en contexto.
- **VAL-02**: si `con_autenticacion`, credenciales resueltas y no vacías antes de abrir canal.
- **VAL-03**: acceso/autenticación acotados por timeout.
- **VAL-04**: `entry_result` estructurado completo.
- **VAL-05**: éxito → sesión con `id_sesion` y handle; fallo → canal cerrado y sin sesión.
- **VAL-06**: reintentos ≤ máximo; backoff; solo códigos reintentables; cada reintento desde canal cerrado.

### Condiciones
- **Normal**: `entry_result` construido → decisión.
- **Reintento**: código reintentable con intentos restantes.
- **Fallo de fuente**: no aborto; `entry_result` fallo.
- **Aborto**: ficha ausente/corrupta; corrupción de contexto.

### Ramas
- Normal única → `"¿El ingreso fue exitoso?"`.
- Aborto → `"Finalizar Proceso"` con `error`.
- Flujo interno con salida temprana a construcción de `entry_result`.

### Errores y excepciones

| Código | Error / excepción | Reintentable | Detección | Registro / acción | Estado |
|---|---|:---:|---:|---|---|
| ERR-01 | Ficha ausente o corrupta en contexto | No | 1 | Evento crítico; aborto | `error` |
| ERR-02 | `credenciales_no_disponibles`: referencia no resoluble o vacías | No | 2 | Evidencia de fallo; no abrir canal; salto a `entry_result` | fallo de fuente |
| ERR-03 | `fuente_inalcanzable`: red/DNS/plataforma caída | Sí | 3 | Con intentos: cerrar canal, backoff, reintentar; agotados: evidencia de fallo | fallo de fuente |
| ERR-04 | `tiempo_agotado_ingreso` | Sí | 3/4 | Ídem ERR-03 | fallo de fuente |
| ERR-05 | `autenticacion_rechazada` | No | 4 | Evidencia de fallo | fallo de fuente |
| ERR-06 | `bloqueo_plataforma`: captcha/anti-bot/desafío | No | 4 | Evidencia de fallo | fallo de fuente |
| ERR-07 | `criterio_no_cumplido` | No | 5 | Evidencia de fallo | fallo de fuente |
| ERR-08 | `error_interno_fuente` | No | 3–5 | Evidencia de fallo; cerrar canal si quedó abierto | fallo de fuente |
| ERR-09 | Corrupción del contexto | No | 5 | Evento crítico; aborto | `error` |

**Contrato de códigos**: `ingreso_exitoso`, `credenciales_no_disponibles`, `fuente_inalcanzable`, `tiempo_agotado_ingreso`, `autenticacion_rechazada`, `bloqueo_plataforma`, `criterio_no_cumplido`, `error_interno_fuente`.

### Escenarios límite
- Fuente `publico`: pasos de credenciales/autenticación sin efecto.
- Almacén seguro caído con fuente autenticada: ERR-02, sin reintento.
- Cambio de layout: ERR-07.
- Caída transitoria o lentitud: ERR-03/ERR-04 con reintento acotado.
- Canal parcialmente abierto: cierre garantizado en todo camino.
- Credenciales nunca expuestas en evidencia o registros.

### Dependencias y contratos
- **Antecesor**: `"Seleccionar la siguiente fuente pendiente"`.
- **Sucesor normal**: `"¿El ingreso fue exitoso?"`.
- **Sucesor de aborto**: `"Finalizar Proceso"`.
- **Contratos consumidos**: ficha completa; trazabilidad; parámetros de reintento/backoff.
- **Contratos entregados**: `entry_result`; sesión solo en éxito.
- **Impactos aprobados**:
  - decisión siguiente evalúa solo `entry_result`;
  - registro de fallo consume código, intentos y evidencia;
  - `id_sesion` alimenta `"control de sesiones"` y registros de ofertas;
  - filtros se consumen en nodo de filtros.

### Notas de implementación
- Canal puede ser navegador o API; contrato funcional idéntico.
- El adaptador se resuelve por `fuente_id` vía registro (`obtener_adaptador`, D13); fuente sin adaptador → `fuente_no_soportada` (sin reintentos).
- Intentos totales = 1 + máx. reintentos.
- Cada reintento parte de canal cerrado y reejecuta acceso.
- Nunca reintentar códigos no reintentables.
- Garantizar cierre de canal en todo fallo.
- Timeout por fuente con default global.
- Evidencia sin credenciales/tokens/cookies.
- `id_sesion` único y vinculado a `id_corrida` y `fuente_id`.

### Pasos funcionales
1. **Leer ficha**. Entrada: contexto. Proceso: acceder a URL, tipo, referencia, criterio, timeout. Salida: parámetros de acceso. Val: VAL-01. Err: ERR-01.
2. **Resolver credenciales si aplica**. Entrada: tipo/referencia/almacén seguro. Proceso: si `con_autenticacion`, obtener y verificar no vacías; si fallo, salto a `entry_result`; si `publico`, sin efecto. Salida: credenciales en memoria o N/A. Val: VAL-02. Err: ERR-02.
3. **Abrir canal y acceder**. Entrada: parámetros, timeout, reintentos. Proceso: abrir canal y acceder; fallo reintentable → cerrar, backoff, repetir; fallo no reintentable/agotado → salto a `entry_result`. Salida: canal abierto. Val: VAL-03, VAL-06. Err: ERR-03, ERR-04, ERR-08.
4. **Autenticar si aplica**. Entrada: canal, credenciales. Proceso: autenticar dentro de timeout; `tiempo_agotado_ingreso` reintentable → reejecutar desde paso 3; `autenticacion_rechazada`/`bloqueo_plataforma` → fallo; `publico` sin efecto. Salida: estado post-autenticación. Val: VAL-03, VAL-06. Err: ERR-04, ERR-05, ERR-06, ERR-08.
5. **Evaluar criterio y construir `entry_result`**. Entrada: estado del canal, criterio, contador. Proceso: aplicar criterio; construir `entry_result`; éxito → `id_sesion` + handle; fallo → cerrar canal sin sesión. Salida: `entry_result`; sesión lista o ausente. Val: VAL-04, VAL-05. Err: ERR-07, ERR-08, ERR-09.
6. **Entregar control**. Entrada: contexto con `entry_result`. Proceso: cerrar nodo. Salida: flujo a `"¿El ingreso fue exitoso?"`. Val: `entry_result` presente. Err: ninguna.

---

## Nodo decisión: “¿El ingreso fue exitoso?”  
**Versión**: 1.0 (aprobada)

### Posición
Entre `"Entrar a la fuente seleccionada"` v1.1 y el bloque de procesamiento. Sí → `"Aplicar los filtros básicos…"`. No → `"Registrar error o suceso en 'errores o sucesos'"`.

### Objetivo
Evaluar `entry_result` y bifurcar: procesar fuente con sesión activa o derivar fallo a registro.

### Descripción funcional
Lee `entry_result`, valida estructura y, si éxito, presencia de sesión. Evalúa `estado == exito`. Es decisión pura: no sondea plataforma, no registra. Inconsistencia de contrato aborta.

### Entradas
Contexto: `entry_result`, sesión si éxito, `id_corrida`, `fuente_id`.

### Salidas
- **Sí** → `"Aplicar los filtros básicos…"` con sesión activa disponible.
- **No** → `"Registrar error o suceso en 'errores o sucesos'"` con `entry_result` como carga.
- **Aborto** → `"Finalizar Proceso"` con `error`.

### Reglas de negocio
- **RN-01**: evaluación pura sobre `entry_result`; prohibido sondear plataforma/sesión.
- **RN-02**: condición = `entry_result.estado == exito`.
- **RN-03**: validar consistencia: estructura completa y, si éxito, sesión presente. Violación = aborto visible.
- **RN-04**: este nodo no registra; el registro del fallo pertenece a la rama No.
- **RN-05**: contratos: Sí garantiza sesión; No garantiza `entry_result` disponible.

### Validaciones
- **VAL-01**: `entry_result` presente.
- **VAL-02**: estructura completa: estado, `codigo_motivo`, evidencia, `numero_de_intentos`.
- **VAL-03**: si éxito, sesión presente con handle y `id_sesion`.

### Condiciones y ramas
- **Sí**: estado = `exito` y consistencia validada.
- **No**: estado = `fallo` y consistencia validada.
- **Aborto**: `entry_result` ausente/corrupto o estructura inválida/éxito sin sesión.

### Errores

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---:|---|---|---|
| ERR-01 | `entry_result` ausente o corrupto | 1 | Evento crítico con `id_corrida` + `fuente_id` | Aborto | `error` |
| ERR-02 | Estructura inválida o éxito sin sesión | 2 | Evento crítico con `id_corrida` + `fuente_id` | Aborto | `error` |

### Dependencias y contratos
- **Antecesor**: `"Entrar a la fuente seleccionada"` v1.1.
- **Sucesor Sí**: `"Aplicar los filtros básicos…"`.
- **Sucesor No**: `"Registrar error o suceso en 'errores o sucesos'"`.
- **Impactos aprobados**:
  - registro consume `entry_result` completo;
  - nodo de filtros consume sesión sin revalidarla.

### Notas de implementación
- Evaluación pura; sin I/O externo salvo evento crítico de aborto.
- No ramificar por `codigo_motivo`; solo por estado.
- No registrar fallo aquí.

### Pasos funcionales
1. **Leer `entry_result`**. Entrada: contexto. Proceso: acceder sin sondear. Salida: `entry_result`. Val: VAL-01. Err: ERR-01.
2. **Validar consistencia**. Entrada: `entry_result`. Proceso: verificar estructura; si éxito, sesión. Salida: validado. Val: VAL-02, VAL-03. Err: ERR-02.
3. **Evaluar**. Entrada: validado. Proceso: `estado == exito`. Salida: Sí/No. Err: ninguna.
4. **Rama Sí**. Entrada: Sí, sesión. Proceso: entregar control. Salida: flujo a filtros. Val: VAL-03. Err: ninguna.
5. **Rama No**. Entrada: No, `entry_result`. Proceso: entregar control sin registrar. Salida: flujo a registro. Err: ninguna.

---

## Nodo proceso: “Aplicar los filtros básicos establecidos para esa fuente/plataforma para encontrar ofertas laborales”  
**Versión**: 1.1 (aprobada)

### Posición
Entre:
- rama Sí de `"¿El ingreso fue exitoso?"` en primera pasada;
- rama Sí de `"¿Quedan sets de filtros por aplicar en esta fuente?"` en pasadas siguientes.

Sucesor: `"¿Se encontraron ofertas?"`. Nodo re-entrante por set.

### Objetivo
Seleccionar el siguiente set pendiente, ejecutar la búsqueda con ese set dentro de la sesión, interpretar la respuesta y producir `search_result` con primera página de referencias, paginación, metadatos y `indice_set`.

### Descripción funcional
Lee sesión, `sets_de_filtros` e iterador de sets. Si cambió la fuente, reinicia iterador a “ninguno”. Selecciona primer set no procesado en orden de configuración, lo marca procesado al seleccionarlo y lo fija como `set_corriente`. Aplica filtros mediante adaptador, ejecuta consulta con timeout y reintentos condicionales, interpreta respuesta cruda y produce:
```text
search_result = {
  estado: exito|fallo,
  codigo_motivo,
  evidencia_acotada,
  ofertas_primera_pagina: [referencias],
  estado_paginacion,
  total_declarado | indeterminado,
  indice_set,
  numero_de_intentos
}
```
Entrega control a `"¿Se encontraron ofertas?"`.

### Límites
No decide si hay ofertas; no decide si quedan sets; no captura información completa; no interpreta contenido; no recorre páginas posteriores.

### Entradas
- Sesión activa: `id_sesion` + handle.
- `sets_de_filtros` de fuente corriente: lista no vacía, ordenada; cada set posiblemente vacío.
- Iterador de sets.
- `fuente_id`, `id_corrida`, `id_sesion`.
- Timeout de consulta, máx. reintentos, backoff.

### Salidas
- `set_corriente` fijado e iterador avanzado.
- `search_result` en contexto.
- Control único a `"¿Se encontraron ofertas?"`.
- Aborto → `"Finalizar Proceso"` con `error`.

### Reglas de negocio
- **RN-01**: solo contexto; no releer almacén.
- **RN-02**: aplicar únicamente filtros del `set_corriente`; adaptador los mapea al mecanismo de la plataforma.
- **RN-03**: set vacío = búsqueda base; configuración válida.
- **RN-04**: filtros configurados pero no aplicables en runtime = fallo `filtros_no_aplicables`; prohibido continuar sin filtros. Falla descarta el set, no la fuente.
- **RN-05**: alcance perezoso: primera página y estado de paginación; páginas posteriores pertenecen al bucle de captura.
- **RN-06**: reintentos solo para `fuente_inalcanzable` y `tiempo_agotado_consulta`; resto fallo inmediato.
- **RN-07**: sesión expirada = `sesion_expirada`; sin re-ingreso automático.
- **RN-08**: produce referencias de oferta (identificador/URL en orden de plataforma); no captura contenido ni interpreta.
- **RN-09**: evidencia acotada; trazabilidad `id_corrida` + `fuente_id` + `id_sesion` + `indice_set`.
- **RN-10**: iterador de sets propiedad de este nodo: se reinicia al cambiar fuente; selecciona primer set pendiente y lo marca procesado al seleccionar.
- **RN-11**: no decide si quedan sets; eso pertenece a `"¿Quedan sets de filtros…?"`.

### Validaciones
- **VAL-01**: sesión, sets e iterador presentes.
- **VAL-02**: consulta acotada por timeout.
- **VAL-03**: política de reintentos cumplida.
- **VAL-04**: interpretación produce referencias ordenadas + paginación; no interpretable = `respuesta_invalida`.
- **VAL-05**: `search_result` completo con `indice_set` antes de entregar control.
- **VAL-06**: iterador coherente; set seleccionado existe/rango; queda marcado procesado.

### Condiciones
- **Normal**: `search_result` construido, éxito con lista posiblemente vacía o fallo.
- **Fallo de set**: no aborta ni descarta fuente.
- **Aborto**: sesión/sets/iterador ausentes/corruptos; ausencia de set pendiente; corrupción de contexto.

### Ramas
- Salida normal única → `"¿Se encontraron ofertas?"`.
- Aborto → `"Finalizar Proceso"` con `error`.
- Re-entrada desde `"¿Quedan sets de filtros…?"`.

### Errores y excepciones

| Código | Error / excepción | Reintentable | Detección | Registro / acción | Estado |
|---|---|:---:|---:|---|---|
| ERR-01 | Sesión, sets o iterador ausentes/corruptos; o ausencia de set pendiente | No | 1–2 | Evento crítico; aborto | `error` |
| ERR-02 | `filtros_no_aplicables` | No | 3 | Evidencia de fallo; set omitido | fallo de set |
| ERR-03 | `fuente_inalcanzable` | Sí | 3 | Backoff/reintento; agotado → evidencia | fallo de set |
| ERR-04 | `tiempo_agotado_consulta` | Sí | 3 | Ídem ERR-03 | fallo de set |
| ERR-05 | `sesion_expirada` | No | 3 | Evidencia de fallo; sin re-ingreso | fallo de set |
| ERR-06 | `respuesta_invalida` | No | 4 | Evidencia de fallo | fallo de set |
| ERR-07 | `error_interno_consulta` | No | 3–5 | Evidencia de fallo | fallo de set |
| ERR-08 | Corrupción del contexto al construir `search_result` | No | 5 | Evento crítico; aborto | `error` |

**Contrato de códigos**: `consulta_exitosa`, `filtros_no_aplicables`, `respuesta_invalida`, `fuente_inalcanzable`, `tiempo_agotado_consulta`, `sesion_expirada`, `error_interno_consulta`.

**Éxito del nodo**: consulta ejecutada, filtros aplicados si configurados, respuesta interpretada; lista puede ser vacía.

### Escenarios límite
- Set vacío → búsqueda base.
- Plataforma sin soporte de filtros → ERR-02; set omitido, fuente continúa.
- Respuesta vacía válida vs corrupta: éxito con lista vacía vs ERR-06.
- Sesión expirada durante consulta → ERR-05.
- Caída transitoria → ERR-03/ERR-04 con reintento.
- Cambio de fuente → reinicio de iterador.
- Re-entrada por siguiente set → iterador ya avanzado.

### Dependencias y contratos
- **Antecesores**: rama Sí de ingreso; rama Sí de sets.
- **Sucesor normal**: `"¿Se encontraron ofertas?"`.
- **Sucesor de aborto**: `"Finalizar Proceso"`.
- **Contratos consumidos**: sesión activa; sets no vacíos/ordenados; timeout/reintentos/backoff.
- **Contratos entregados**: `search_result` con `indice_set`; iterador avanzado.
- **Impactos aprobados**:
  - `"¿Se encontraron ofertas?"` v1.1: Sí → captura; No → registro y luego decisión de sets.
  - `"¿Quedan sets…?"` lee iterador; su No retorna a fuentes.
  - Bucle de captura consume `ofertas_primera_pagina` y `estado_paginacion`.
  - Registros incorporan `indice_set`.
  - `"Seleccionar la siguiente fuente pendiente"` no requiere reedición por iterador de sets.

### Notas de implementación
- Adaptador por fuente encapsula filtros e interpretación.
- El adaptador se resuelve por `fuente_id` vía registro (`obtener_adaptador`, D13); fuente sin adaptador → `fuente_no_soportada` (sin reintentos).
- Iterador vinculado a `fuente_id`; reiniciar si cambió fuente; marcar al seleccionar.
- Referencias = identificador/URL en orden de plataforma.
- `total_declarado` solo si la plataforma lo expone; si no, indeterminado.
- `estado_paginacion` debe permitir pedir página siguiente sin re-ejecutar búsqueda.
- Nunca continuar sin filtros ante `filtros_no_aplicables`.
- Evidencia sin credenciales/tokens/cookies.
- **As-built 2026-08-17 (decisión D28):** `ofertas_primera_pagina` del `search_result` lleva los campos de tarjeta (empresa, ubicación, fecha relativa en `observaciones` y `fecha_publicacion` aproximada) — extiende el alcance de RN-08/Límites: el nodo entrega contenido de tarjeta, no solo referencias; la persistencia sigue haciéndose exclusivamente en `"Capturar ofertas"`. El total declarado se lee solo del texto **visible** del DOM (excluye `script`/`style` y comentarios HTML, que pueden contener "N resultados") — endurece la nota D27 (e).

### Pasos funcionales
1. **Leer insumos**. Entrada: sesión, sets, iterador, IDs, timeout/reintentos. Proceso: acceder desde contexto. Salida: insumos. Val: VAL-01. Err: ERR-01.
2. **Seleccionar set pendiente**. Entrada: sets, iterador, `fuente_id`. Proceso: reiniciar si cambió fuente; seleccionar primer no procesado; marcar procesado; fijar `set_corriente`. Salida: `set_corriente`, iterador avanzado. Val: VAL-06. Err: ERR-01.
3. **Aplicar filtros y ejecutar consulta**. Entrada: sesión, filtros, timeout, reintentos. Proceso: mapear filtros; set vacío = base; consulta; reintentos según código. Salida: respuesta cruda. Val: VAL-02, VAL-03. Err: ERR-02, ERR-03, ERR-04, ERR-05, ERR-07.
4. **Interpretar respuesta**. Entrada: respuesta cruda. Proceso: convertir a referencias ordenadas; extraer paginación y total si existe; no interpretable = `respuesta_invalida`. Salida: referencias + paginación + total. Val: VAL-04. Err: ERR-06, ERR-07.
5. **Construir `search_result`**. Entrada: resultados o fallo, `indice_set`, intentos. Proceso: construir estructura completa. Salida: `search_result` en contexto. Val: VAL-05. Err: ERR-07, ERR-08.
6. **Entregar control**. Entrada: contexto con `search_result`. Proceso: cerrar nodo. Salida: flujo a `"¿Se encontraron ofertas?"`. Err: ninguna.

---

## Nodo decisión: “¿Se encontraron ofertas?”  
**Versión**: 1.1 (aprobada)

### Posición y cambios aprobados
Entre `"Aplicar los filtros básicos…"` v1.1 y:
- Sí → `"Capturar ofertas"`;
- No → `"Registrar suceso o error en 'errores o sucesos'"`.

Cambios oficializados:
1. Se elimina el nodo de conteo; auditoría de sesión vive dentro de `"Capturar ofertas"`.
2. Rama No, tras registro, se enruta a `"¿Quedan sets de filtros por aplicar en esta fuente?"`, no a iteración de fuentes.
3. Bucle por oferta reemplazado por captura por lote con políticas por fuente.

### Objetivo
Evaluar `search_result` del set corriente y bifurcar: capturar ofertas o registrar resultado del set y continuar con sets restantes.

### Descripción funcional
Lee `search_result`, valida consistencia, evalúa:
```text
estado == exito y conteo(ofertas_primera_pagina) > 0
```
Decisión pura: no re-consulta plataforma, no registra, no tipifica. Inconsistencia aborta.

### Entradas
Contexto: `search_result`, `id_corrida`, `fuente_id`, `id_sesion`.

### Salidas
- **Sí** → `"Capturar ofertas"` con referencias no vacías + paginación.
- **No** → `"Registrar suceso o error en 'errores o sucesos'"` con `search_result` como carga.
- **Aborto** → `"Finalizar Proceso"` con `error`.

### Reglas de negocio
- **RN-01**: evaluación pura; prohibido re-consultar plataforma.
- **RN-02**: condición = éxito y conteo > 0.
- **RN-03**: éxito con conteo 0 = válido sin ofertas → rama No; registro como suceso aguas abajo.
- **RN-04**: validar estructura completa y, si éxito, lista presente con conteo ≥ 0; violación = aborto.
- **RN-05**: no registra ni tipifica; lo hace nodo de rama No.
- **RN-06**: contratos: Sí garantiza referencias no vacías + paginación; No garantiza carga de registro.
- **RN-07**: no existe nodo de conteo; auditoría de sesión pertenece a `"Capturar ofertas"`.
- **RN-08**: rama No omite el set corriente, no la fuente; continuación decide `"¿Quedan sets…?"`.

### Validaciones
- **VAL-01**: `search_result` presente.
- **VAL-02**: estructura completa incluido `indice_set`; si éxito, lista presente con conteo ≥ 0.
- **VAL-03**: Sí solo con éxito y conteo > 0.

### Condiciones y ramas
- **Sí**: éxito y conteo > 0.
- **No**: fallo cualquier código, o éxito con conteo 0.
- **Aborto**: `search_result` ausente/corrupto o estructura inválida/éxito sin lista.

### Errores

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---:|---|---|---|
| ERR-01 | `search_result` ausente o corrupto | 1 | Evento crítico con `id_corrida`, `fuente_id`, `id_sesion`, `indice_set` | Aborto | `error` |
| ERR-02 | Estructura inválida o éxito sin lista | 2 | Evento crítico con `id_corrida`, `fuente_id`, `id_sesion`, `indice_set` | Aborto | `error` |

### Escenarios límite
- Búsqueda fallida con cualquier código → No; set omitido, fuente continúa.
- Éxito sin ofertas → No; suceso aguas abajo.
- Éxito con ofertas → Sí.
- Violación de contrato → aborto visible.

### Dependencias y contratos
- **Antecesor**: `"Aplicar los filtros básicos…"` v1.1.
- **Sucesor Sí**: `"Capturar ofertas"`.
- **Sucesor No**: registro, que enruta a `"¿Quedan sets…?"`.
- **Impactos aprobados**:
  - registro consume `search_result`, tipifica error/suceso, incluye `indice_set`, enruta a sets;
  - `"Capturar ofertas"` consume primera página/paginación, aplica políticas y escribe auditoría;
  - `"¿Quedan sets…?"` cierra fuente o reentra.

### Notas de implementación
- Evaluación pura; sin I/O externo salvo evento crítico de aborto.
- No ramificar por `codigo_motivo`.
- No registrar aquí.
- Rama No nunca descarta fuente por sí misma.

### Pasos funcionales
1. **Leer `search_result`**. Entrada: contexto. Proceso: acceder sin re-consultar. Salida: `search_result`. Val: VAL-01. Err: ERR-01.
2. **Validar consistencia**. Entrada: `search_result`. Proceso: estructura y lista si éxito. Salida: validado. Val: VAL-02. Err: ERR-02.
3. **Evaluar**. Entrada: validado. Proceso: éxito y conteo > 0. Salida: Sí/No. Err: ninguna.
4. **Rama Sí**. Entrada: Sí. Proceso: entregar control. Salida: flujo a `"Capturar ofertas"`. Val: VAL-03. Err: ninguna.
5. **Rama No**. Entrada: No, `search_result`. Proceso: entregar control sin registrar; set omitido. Salida: flujo a registro. Err: ninguna.

---

## Nodo proceso: “Capturar ofertas”  
**Versión**: 1.2 (aprobada)  
**Nota de implementación aprobada**: reedición 2026-08-12 — captura por listado (D11): el adaptador recorre páginas `?start=N` del listado sin entrar al detalle de cada oferta (descripciones vacías en MVP; enriquecimiento en Módulo de Preparación); fin del recorrido por ausencia del botón de paginación ("Siguiente"/"Página N") o página vacía; navegación directa a `/jobs/search-results/` con `wait_until="commit"` reutilizando la página 1 ya cargada tras aplicar filtros (elimina la doble carga por redirect); `tope_espera_paginas_sucesivas_segundos` en políticas efectivas; el suceso `captura_completada` (evidencia "páginas=N | ofertas=M") reemplaza a `captura_exitosa` en el contrato de códigos. También: reedición 2026-08-11 — `estado_captura` incorpora `indice_set` (implementado desde 2026-08-09).

### Posición
Entre:
- rama Sí de `"¿Se encontraron ofertas?"`.

Sucesor: `"Registrar ofertas capturadas en 'Ofertas Totales'"`.

### Objetivo
Capturar información completa disponible de las ofertas del lote corriente, aplicar `politicas_de_captura` efectivas mediante adaptador, actualizar progreso y escribir auditoría de sesión en `"control de sesiones"` en el primer lote del set. No registra ofertas en `"Ofertas Totales"`.

### Descripción funcional
Lee insumos de captura. En primer lote del par `(id_sesion, indice_set)` escribe auditoría con tolerancia a degradación. Determina alcance del lote:
- primera pasada: referencias de `search_result`;
- pasadas siguientes: página siguiente vía `estado_paginacion`, con pausas y estrategia anti-bloqueo.

Verifica límites antes de capturar:
- `max_paginas` por búsqueda/set;
- `max_ofertas_por_corrida` con alcance `(corrida, fuente)`.

Captura información original de las ofertas del lote recorriendo el listado de la plataforma (paginación `?start=N`, scroll infinito o detalle según mecanismo del adaptador; actual: listado sin acceso a detalle). Falla individual excluye la oferta con evento `oferta_no_capturada`; el lote continúa. El recorrido termina por ausencia del botón de paginación o página sin tarjetas, o por límites. Evalúa resultado del lote, actualiza progreso y guarda `capture_batch` + `estado_captura`; registra `captura_completada` con evidencia "páginas=N | ofertas=M".

### Entradas
- `search_result`: `ofertas_primera_pagina`, `estado_paginacion`, `indice_set`, `total_declarado`.
- Sesión activa: `id_sesion` + handle.
- Políticas efectivas: `max_paginas`, `max_ofertas_por_corrida`, `pausa_entre_lotes`, `estrategia_anti_bloqueo`, `tope_espera_paginas_sucesivas_segundos`.
- Progreso: `paginas_consumidas`, `capturadas_acumuladas_fuente`.
- `id_corrida`, `fuente_id`.
- Reintentos/backoff globales.

### Salidas
- `capture_batch`: ofertas capturadas con información original + trazabilidad por oferta.
- `estado_captura`: `{estado, codigo_motivo, paginas_consumidas, capturadas_acumuladas_fuente, limite_alcanzado, indice_set}`.
- Auditoría de sesión en `"control de sesiones"` o marca degradada.
- Control único a `"Registrar ofertas capturadas en 'Ofertas Totales'"`.
- Aborto → `"Finalizar Proceso"` con `error`.

### Reglas de negocio
- **RN-01**: solo contexto; no releer almacén.
- **RN-02**: granularidad del lote y mecanismo de recorrido definidos por adaptador: masivo/incremental, paginación, scroll infinito o detalle uno a uno (RN-10); configuración solo acota límites. Mecanismo actual (LinkedIn): listado `?start=N` sin acceso a detalle.
- **RN-03**: capturar toda la información original disponible; prohibido interpretar/clasificar/evaluar.
- **RN-04**: falla por oferta = exclusión + evento `oferta_no_capturada`; lote continúa.
- **RN-05**: límites verificados antes de capturar. Límite alcanzado → lote vacío + `limite_alcanzado = true`.
- **RN-06**: reintentos solo para `fuente_inalcanzable` y `tiempo_agotado_captura`; resto fallo inmediato. Ante fallo de lote, conservar lote parcial.
- **RN-07**: auditoría por `(id_sesion, indice_set)` en primer lote:
  ```text
  id_sesion, id_corrida, fuente_id, indice_set, marca_temporal,
  total_declarado, conteo_primera_pagina, hay_mas_paginas,
  coherencia, estado_auditoria
  ```
  Fallo de escritura: reintento único; si persiste, evento crítico y continuación degradada.
- **RN-08**: no escribe en `"Ofertas Totales"`; registro pertenece al nodo siguiente.
- **RN-09**: evidencia acotada; trazabilidad completa en eventos y ofertas.
- **RN-10**: `limite_alcanzado` es señal de cierre: `"¿Quedan sets…?"` lo trata como cierre de fuente.

### Validaciones
- **VAL-01**: insumos presentes.
- **VAL-02**: límites verificados antes de capturar.
- **VAL-03**: política de reintentos cumplida.
- **VAL-04**: en incremental, pausas y anti-bloqueo aplicados.
- **VAL-05**: `capture_batch` y `estado_captura` completos con trazabilidad.
- **VAL-06**: auditoría completa o marca degradada documentada.

### Condiciones
- **Normal**: `estado_captura` construido: éxito completo/parcial, fallo con lote parcial, o lote vacío por límite.
- **Fallo de lote**: no aborto; lote parcial conservado.
- **Aborto**: insumos ausentes/corruptos; corrupción de contexto.

### Ramas
- Normal única → `"Registrar ofertas capturadas en 'Ofertas Totales'"`.
- Aborto → `"Finalizar Proceso"` con `error`.

### Errores y eventos

| Código | Error / evento | Reint. | Detección | Registro / acción | Estado |
|---|---|:---:|---:|---|---|
| ERR-01 | Insumos ausentes/corruptos | No | 1 | Evento crítico; aborto | `error` |
| ERR-02 | Fallo de auditoría tras reintento único | No | 2 | Evento crítico; continuar degradado | continúa |
| ERR-03 | `fuente_inalcanzable` | Sí | 3–4 | Backoff/reintento; agotado → fallo de lote con parcial | fallo de lote |
| ERR-04 | `tiempo_agotado_captura` | Sí | 3–4 | Ídem ERR-03 | fallo de lote |
| ERR-05 | `sesion_expirada` | No | 4 | Fallo de lote con parcial; sin re-ingreso | fallo de lote |
| ERR-06 | `bloqueo_plataforma` | No | 4 | Fallo de lote con parcial | fallo de lote |
| ERR-07 | `respuesta_invalida` | No | 3–4 | Fallo de lote con parcial | fallo de lote |
| ERR-08 | `error_interno_captura` | No | 3–5 | Fallo de lote con parcial | fallo de lote |
| ERR-09 | Corrupción del contexto al guardar | No | 6 | Evento crítico; aborto | `error` |
| EVT-01 | `oferta_no_capturada` | No | 4 | Evento con referencia; excluir oferta; lote continúa | continúa |
| EVT-02 | `captura_completada` | No | 5 | Suceso con evidencia "páginas=N \| ofertas=M"; cierre del recorrido | continúa |

**Contrato de códigos**: `captura_completada` (suceso de cierre; reemplaza a `captura_exitosa`), `fuente_inalcanzable`, `fuente_no_soportada`, `tiempo_agotado_captura`, `sesion_expirada`, `bloqueo_plataforma`, `respuesta_invalida`, `error_interno_captura`; evento por oferta: `oferta_no_capturada`. `fuente_no_soportada` (adaptador no registrado para la fuente, D13) se emite en la resolución del adaptador y nunca se reintenta.

### Escenarios límite
- Mecanismo masivo vs incremental; fin de recorrido por ausencia del botón de paginación o página vacía.
- Límite de páginas u ofertas alcanzado → lote vacío + `limite_alcanzado`.
- Oferta individual defectuosa → EVT-01.
- Caída transitoria de página → ERR-03/ERR-04 con reintento.
- Bloqueo o sesión expirada a mitad de lote → lote parcial conservado.
- Lote vacío por límites entregado al registro como no-op.

### Dependencias y contratos
- **Antecesores**: `"¿Se encontraron ofertas?"`.
- **Sucesor normal**: `"Registrar ofertas capturadas en 'Ofertas Totales'"`.
- **Sucesor de aborto**: `"Finalizar Proceso"`.
- **Contratos consumidos**: `search_result`, sesión, políticas efectivas, progreso.
- **Contratos entregados**: `capture_batch`, `estado_captura`, auditoría por `(id_sesion, indice_set)`.
- **Impactos aprobados**:
  - registro consume `capture_batch`; lote vacío = no-op; deduplicación se define allí;
  - `"¿Quedan sets…?"` trata `limite_alcanzado` como cierre de fuente.

### Notas de implementación
- Adaptador encapsula el mecanismo de recorrido (RN-10): listado con paginación, scroll infinito o detalle uno a uno; actual (LinkedIn) = listado `?start=N` sin acceso a detalle.
- Navegación directa a `/jobs/search-results/` con `wait_until="commit"`; reutilizar página 1 ya cargada tras aplicar filtros; fin por ausencia del botón de paginación o página vacía.
- En páginas sucesivas, el tope de espera de tarjetas se acota con `tope_espera_paginas_sucesivas_segundos` (mín con el timeout de la ficha).
- Aplicar `pausa_entre_lotes` y `estrategia_anti_bloqueo` en incremental.
- El adaptador se resuelve por `fuente_id` vía registro (`obtener_adaptador`, D13); fuente sin adaptador → `fuente_no_soportada` (sin reintentos).
- Progreso persiste en contexto entre pasadas.
- Conservar lote parcial ante fallo.
- Auditoría única por `(id_sesion, indice_set)`; idempotencia ante reentradas.
- No escribir en `"Ofertas Totales"`; no interpretar contenido.
- **As-built 2026-08-17 (decisión D28, extracción de campos de tarjeta):** el adaptador extrae de cada tarjeta SDUi — además de enlace/título — empresa, ubicación y fecha relativa desde el texto de sus `<p>` (las clases CSS reales están hasheadas por página): primer `p` = título (`span[aria-hidden='true']`), último `p` con "Publicado hace N <unidad>" = fecha, resto = empresa y ubicación en orden tras excluir el ruido fijo de la UI (`Visto`, `·`, `Adelántate a solicitar el empleo`, `Solicitar`, `Evaluando solicitudes de forma activa`); las ubicaciones pueden llevar sufijo de modalidad "(En remoto)/(Híbrido)/(Presencial)". `fecha_publicacion` se persiste como timestamp absoluto aproximado (`FORMATO_TIMESTAMP`; precisión ±1 h por redondeo de LinkedIn, unidad mes = 30 días) y el texto crudo se conserva íntegro en `observaciones` — desviación aprobada de RN-03 (aditiva y reversible: la información original nunca se destruye; el enriquecimiento/normalización de fechas sigue siendo competencia del Módulo 2). La variante clásica (`base-search-card`) expone empresa/ubicación pero no fecha (best-effort: fecha vacía).

### Pasos funcionales
1. **Leer insumos**. Entrada: `search_result`, sesión, políticas, progreso, IDs. Proceso: acceder desde contexto. Salida: insumos. Val: VAL-01. Err: ERR-01.
2. **Auditoría de sesión**. Entrada: `id_sesion`, `indice_set`, `search_result`. Proceso: si primer lote, escribir registro completo; fallo → reintento único y degradado. Salida: registro o marca degradada. Val: VAL-06. Err: ERR-02.
3. **Determinar lote y límites**. Entrada: progreso, políticas, `estado_paginacion`. Proceso: primera pasada usa referencias; siguientes, página siguiente con pausas/anti-bloqueo; verificar límites; límite → lote vacío + `limite_alcanzado`. Salida: alcance del lote o lote vacío. Val: VAL-02, VAL-03. Err: ERR-03, ERR-04, ERR-08.
4. **Capturar lote recorriendo el listado**. Entrada: referencias, sesión, adaptador, políticas. Proceso: recorrer páginas por el mecanismo del adaptador (actual: paginación `?start=N` sin detalle); fin por ausencia del botón de paginación o página vacía; fallas individuales excluyen con evento; registrar `captura_completada` al cerrar el recorrido. Salida: ofertas capturadas. Val: VAL-04. Err: EVT-01, EVT-02; ERR-05, ERR-06, ERR-07, ERR-08.
5. **Evaluar lote y progreso**. Entrada: capturas, progreso, intentos. Proceso: éxito/fallo; actualizar `paginas_consumidas`, `capturadas_acumuladas_fuente`; calcular `limite_alcanzado`. Salida: `estado_captura` + lote. Err: ERR-03 a ERR-08.
6. **Guardar en contexto**. Entrada: lote, `estado_captura`. Proceso: persistir con trazabilidad por oferta. Salida: contexto actualizado. Val: VAL-05. Err: ERR-09.
7. **Entregar control**. Entrada: contexto. Proceso: cerrar nodo. Salida: flujo a `"Registrar ofertas capturadas en 'Ofertas Totales'"`. Err: ninguna.

---

## Nodo proceso: “Registrar ofertas capturadas en 'Ofertas Totales'”  
**Versión**: 1.0 (aprobada)  
**Nota de implementación aprobada**: Sub-fase 4.4, 2026-08-09.

### Posición
Entre `"Capturar ofertas"` v1.0 y `"¿Quedan sets de filtros por aplicar en esta fuente?"`. Posición definitiva.

### Objetivo
Persistir `capture_batch` en `"Ofertas Totales"` conservando información original, trazabilidad e `id_externo` crudo cuando exista, y liberar el lote. No normaliza ni verifica identidad más allá de `id_externo`. La deduplicación avanzada en dos capas pertenece al Módulo 2.

### NOTA — Desvío aprobado Sub-fase 4.4
- Se introdujo deduplicación por `id_externo` vía `upsert_oferta`.
- Si la fila existe: solo se refresca `fecha_ultima_verificacion` y se conserva el `id`.
- Si no existe: se inserta fila nueva.
- Persistencia por oferta; RN-06 de transacción única de lote queda relajada a nivel de oferta.
- MVP: catálogos `empresas`/`ubicaciones` no resueltos:
  - `empresa_id` y `ubicacion_id` = `NULL`;
  - ~~crudo del adaptador en `empresa_nombre` y `ubicacion_nombre`~~ (D29: columnas eliminadas);
  - `fuente_id` guardado en `fuente_id` sin constraint FK.
- Documentado en DOC-13/13-A y tracker, 2026-08-09.

### NOTA as-built 2026-08-14 (decisión D22, Lote A)
La persistencia por oferta (NOTA 4.4 anterior) queda **derogada**: el lote completo se persiste en **una sola conexión** mediante `upsert_lote_ofertas(filas) -> (registradas, fallidas)` (núcleo `_upsert_ofertas_en`; `upsert_oferta` pasa a ser wrapper fino que lanza `PersistenceError` descriptivo ante fila inválida). Semántica de dedup idéntica a la NOTA 4.4 (D4): existente refresca `fecha_ultima_verificacion` y conserva `id`; nuevo inserta; se detectan también duplicados intra-lote. Un fallo de fila se registra con `id_externo`/`id_corrida` y **no aborta el lote**; el reintento único (RN-07) aplica al **lote completo** y solo ante excepción de conexión/transacción (los errores de fila son de datos y no se reintentan). Los ids generados se capturan con `RETURNING` (`_generar_id_en`), sin SELECT extra. Actualizan esta nota: RN-06, VAL-03, paso 3 y "Notas de implementación".

### Descripción funcional
Lee `capture_batch`:
- lote vacío → no-op, sin escritura ni error;
- lote no vacío → persistir ofertas.

Base 1.0: persistencia como filas nuevas en única transacción.  
Bajo NOTA 4.4: persistencia por oferta mediante upsert por `id_externo`.  
As-built D22 (vigente): lote completo en una sola conexión mediante `upsert_lote_ofertas`; dedup por `id_externo` idéntico; errores por fila no abortan el lote.

Fallo de escritura: reintento único; si persiste, evento crítico y aborto. Tras persistir o no-op, libera lote.

### Entradas
Contexto: `capture_batch` con información original, `id_externo` best-effort, metadatos `id_corrida`, `fuente_id`, `id_sesion`, `indice_set`, referencia; conexión a `"Ofertas Totales"`.

### Salidas
- Lote persistido o ninguna escritura si vacío.
- Contexto con `capture_batch` liberado.
- Control único a `"¿Quedan sets de filtros por aplicar en esta fuente?"`.
- Aborto → `"Finalizar Proceso"` con `error`.

### Reglas de negocio
- **RN-01**: solo contexto; no releer almacenes ni re-consultar plataformas.
- **RN-02** (con NOTA): upsert por `id_externo`; existente refresca `fecha_ultima_verificacion` y conserva `id`; nuevo inserta. Deduplicación dos capas del Módulo 2 no se ejecuta aquí.
- **RN-03**: cada fila conserva información original íntegra, `id_externo` nullable, `empresa_id`/`ubicacion_id` NULL en MVP (D29: las columnas crudas `empresa_nombre`/`ubicacion_nombre` fueron eliminadas del modelo; la fecha relativa cruda se conserva en `observaciones`), y trazabilidad: `id_corrida`, `fuente_id`, `id_sesion`, `indice_set`, marcas temporales de captura y última verificación.
- **RN-04**: prohibido transformar, normalizar o limpiar contenido o URLs; crudo se conserva crudo.
- **RN-05**: lote vacío = no-op.
- **RN-06**: base: transacción única por lote; NOTA 4.4 (derogada por D22): persistencia por oferta; actual (D22): lote completo en una conexión (`upsert_lote_ofertas`), errores por fila registrados sin abortar el lote.
- **RN-07**: fallo de escritura/transacción: reintento único; si persiste, evento crítico y aborto. `"Ofertas Totales"` es salida esencial.
- **RN-08**: liberar lote tras persistir o no-op.

### Validaciones
- **VAL-01**: `capture_batch` presente.
- **VAL-02**: cada oferta tiene información original y metadatos; `id_externo` nullable.
- **VAL-03**: base: transacción única; NOTA 4.4 (derogada por D22): persistencia por oferta; actual (D22): lote completo en una conexión; filas fallidas registradas sin abortar.
- **VAL-04**: lote liberado y control entregado.

### Condiciones
- **Normal**: lote persistido o lote vacío.
- **Aborto**: `capture_batch` ausente/corrupto; fallo de escritura tras reintento.

### Ramas
- Normal única → `"¿Quedan sets de filtros por aplicar en esta fuente?"`.
- Aborto → `"Finalizar Proceso"` con `error`.

### Errores

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---:|---|---|---|
| ERR-01 | `capture_batch` ausente o corrupto | 1 | Evento crítico con `id_corrida`, `fuente_id`, `id_sesion`, `indice_set` | Aborto | `error` |
| ERR-02 | Fallo de escritura/transacción tras reintento único | 3 | Evento crítico con `id_corrida`, `fuente_id`, `id_sesion`, `indice_set` | Aborto | `error` |

### Escenarios límite
- Lote vacío por límite o fallo → no-op.
- Ofertas sin `id_externo` → campo nulo; Módulo 2 resolverá por capa difusa.
- Fallo parcial → rollback/base según modo; reintento único; aborto si persiste.
- Caída tras persistir → lo persistido queda; lote liberado no se reprocesa.

### Dependencias y contratos
- **Antecesor**: `"Capturar ofertas"` v1.0.
- **Sucesor normal**: `"¿Quedan sets de filtros por aplicar en esta fuente?"`.
- **Sucesor de aborto**: `"Finalizar Proceso"`.
- **Contrato entregado**: `"Ofertas Totales"` como almacén crudo con trazabilidad e `id_externo`; lote liberado.
- **Impactos aprobados**:
  - decisión siguiente no depende de este nodo;
  - Módulo 2 aplicará deduplicación dos capas: estricta por `fuente_id` + `id_externo` normalizado; difusa por título+empresa+ubicación.

### Notas de implementación
- Base 1.0: insertar filas nuevas, transacción única, rollback completo.
- NOTA 4.4 (derogada por D22): upsert por `id_externo` y persistencia por oferta.
- D22 (vigente): lote completo en una conexión (`upsert_lote_ofertas`); dedup por `id_externo` incl. duplicados intra-lote; fallo de fila registrado con `id_externo`/`id_corrida` sin abortar; reintento único del lote solo ante excepción de conexión/transacción; ids por `RETURNING`.
- No normalizar URLs ni contenido.
- Reintento único; aborto si persiste.
- Liberar lote inmediatamente.
- No interpretar contenido.

### Pasos funcionales
1. **Leer lote**. Entrada: contexto, conexión. Proceso: acceder a `capture_batch`. Salida: lote. Val: VAL-01. Err: ERR-01.
2. **Evaluar lote vacío**. Entrada: lote. Proceso: si vacío, no-op y salto a liberación. Salida: señal de continuación. Err: ninguna.
3. **Persistir**. Entrada: lote. Proceso: upsert del lote completo en una conexión según D22: existente refresca `fecha_ultima_verificacion`; nuevo inserta con información original, crudos y trazabilidad; fila fallida se registra y no aborta. Fallo de conexión/transacción → reintento único del lote; si persiste, aborto. Salida: lote persistido. Val: VAL-02, VAL-03. Err: ERR-02.
4. **Liberar y entregar**. Entrada: contexto. Proceso: liberar `capture_batch`; cerrar nodo. Salida: flujo a `"¿Quedan sets…?"`. Val: VAL-04. Err: ninguna.

---

## NOTA — Nodo retirado: “¿Quedan ofertas por capturar en la búsqueda actual (según políticas)?”  
**As-built 2026-08-12 (D17)**: con la captura por listado (D11, v1.2) el adaptador resuelve toda la paginación en una sola pasada por set; este nodo decisión siempre respondía `no` (decisión constante), por lo que se retiró del flujo, del orquestador y de sus pruebas. `"Registrar ofertas capturadas en 'Ofertas Totales'"` entrega control directamente a `"¿Quedan sets de filtros por aplicar en esta fuente?"`. Historial completo del nodo v1.0 en el commit que lo retira (2026-08-12).

---

## Nodo decisión: “¿Quedan sets de filtros por aplicar en esta fuente?”  
**Versión**: 1.0 (aprobada)

### Posición
Entre `"Registrar ofertas capturadas en 'Ofertas Totales'"` y:
- Sí → `"Aplicar los filtros básicos…"`;
- No → `"¿Quedan fuentes por procesar en esta corrida?"`.

Cierra el ciclo de sets de la fuente corriente.

### Objetivo
Evaluar si quedan sets pendientes y si la fuente puede continuar. Sí reentra a filtros; No cierra fuente y retorna a iteración de fuentes.

### Descripción funcional
Lee iterador de sets, `search_result` del set corriente, `estado_captura` si `indice_set` coincide, y `limite_alcanzado`. Valida consistencia. Clasifica si la fuente está comprometida por fallo Grupo A. Evalúa:
```text
quedan sets no procesados
y limite_alcanzado == false
y fuente_comprometida == false
```
No muta iterador; el iterador pertenece a `"Aplicar filtros básicos"`.

### Entradas
Contexto: iterador de sets, `search_result`, `estado_captura`, `limite_alcanzado`, `id_corrida`, `fuente_id`, `id_sesion`.

### Salidas
- **Sí** → `"Aplicar los filtros básicos…"` con siguiente set.
- **No** → `"¿Quedan fuentes por procesar en esta corrida?"`.
- **Aborto** → `"Finalizar Proceso"` con `error`.

### Reglas de negocio
- **RN-01**: evaluación pura; prohibido consultar plataforma.
- **RN-02**: condición Sí = conjunción completa.
- **RN-03**: clasificación Grupo A / Grupo B propiedad exclusiva de este nodo:
  - **Grupo A — comprometen la fuente**: `sesion_expirada`, `bloqueo_plataforma`, `fuente_inalcanzable`, `tiempo_agotado_consulta`, `tiempo_agotado_captura`, `error_interno_consulta`, `error_interno_captura`.
  - **Grupo B — propios del set**: `filtros_no_aplicables`, `respuesta_invalida`.
- **RN-04**: resultado del set corriente se lee de `search_result` si búsqueda falló; de `estado_captura` solo si `estado_captura.indice_set == indice_set` corriente.
- **RN-05**: validar consistencia: iterador coherente con `fuente_id`; `search_result.indice_set` == set corriente.
- **RN-06**: no registra, no reintenta, no muta estado; iterador de sets lo avanza `"Aplicar filtros básicos"`.
- **RN-07**: fuente corriente ya figura procesada en iterador de fuentes; rama No no requiere mutación adicional.

### Validaciones
- **VAL-01**: insumos presentes.
- **VAL-02**: iterador coherente; `indice_set` alineado.
- **VAL-03**: Sí solo con condición completa.

### Condiciones y ramas
- **Sí**: quedan sets, límite no alcanzado, fuente no comprometida.
- **No**: sin sets restantes, límite alcanzado o fuente comprometida por Grupo A.
- **Aborto**: insumos ausentes/corruptos o iterador/`indice_set` incoherente.

### Errores

| Código | Error / excepción | Detección | Registro | Acción | Estado |
|---|---|---:|---|---|---|
| ERR-01 | Insumos ausentes/corruptos | 1 | Evento crítico con `id_corrida`, `fuente_id`, `id_sesion` | Aborto | `error` |
| ERR-02 | Iterador incoherente o `indice_set` desalineado | 2 | Evento crítico con `id_corrida`, `fuente_id`, `id_sesion` | Aborto | `error` |

### Escenarios límite
- Sesión expirada o bloqueo anti-bot → fuente comprometida, cierre limpio.
- Límite de ofertas alcanzado con sets pendientes → No.
- Todos los sets procesados → No.
- Fallo Grupo B → Sí, siguiente set.
- Búsqueda exitosa sin captura posterior → fuente no comprometida por eso.

### Dependencias y contratos
- **Antecesor**: `"Registrar ofertas capturadas en 'Ofertas Totales'"`.
- **Sucesor Sí**: `"Aplicar los filtros básicos…"`.
- **Sucesor No**: `"¿Quedan fuentes por procesar…?"`.
- **Impactos aprobados**:
  - rama No retorna sin mutación adicional;
  - reedición `"Capturar ofertas"` v1.1 con `indice_set` en `estado_captura` implementada (sub-fase 4.4) y documentada en este documento (2026-08-11).

### Notas de implementación
- Evaluación pura; sin I/O, sin mutación.
- Política Grupo A/B vive solo aquí.
- No avanzar/reiniciar iterador de sets.
- Validación defensiva, no lógica de negocio.

### Pasos funcionales
1. **Leer insumos**. Entrada: iterador, `search_result`, `estado_captura`, límite, IDs. Proceso: acceder desde contexto. Salida: insumos. Val: VAL-01. Err: ERR-01.
2. **Validar consistencia**. Entrada: insumos. Proceso: iterador con `fuente_id`; `indice_set` corriente. Salida: validados. Val: VAL-02. Err: ERR-02.
3. **Clasificar compromiso**. Entrada: `search_result`, `estado_captura` si coincide. Proceso: `fuente_comprometida` = fallo Grupo A en búsqueda o captura del set corriente. Salida: bandera. Err: ninguna.
4. **Evaluar condición**. Entrada: validados, bandera. Proceso: conjunción RN-02. Salida: Sí/No. Err: ninguna.
5. **Rama Sí**. Entrada: Sí. Proceso: entregar control. Salida: flujo a `"Aplicar los filtros básicos…"`. Val: VAL-03. Err: ninguna.
6. **Rama No**. Entrada: No. Proceso: entregar control a iteración de fuentes. Salida: flujo a `"¿Quedan fuentes…?"`. Err: ninguna.

---

## Nodo terminal: “Finalizar Proceso”

### Identificación
Último nodo pendiente del Módulo 1. Punto de convergencia de todas las terminaciones. Oficializa motivos/estados acumulados.

### Objetivo
Cerrar la corrida de forma determinista:
1. persistir evento de terminación;
2. liberar bloqueo de concurrencia si esta corrida lo posee;
3. cerrar recursos abiertos;
4. terminar proceso.

### Entradas
Contexto best-effort:
- motivo/estado de terminación: `corrida_completada`, `sin_fuentes`, `concurrencia`, o `error`;
- `id_corrida`;
- iterador de fuentes/progreso;
- estado de bloqueo;
- handle de sesión abierto, si existe;
- conexiones de BD.

### Salidas
- Evento de terminación persistido en `"errores o sucesos"` o registro crítico local si falla escritura.
- Bloqueo liberado si esta corrida lo poseía.
- Recursos cerrados.
- Sin sucesor: fin del proceso.

### Ramas
No es nodo de decisión.

### Estados/motivos oficiales

| Estado | Motivos | Tipo |
|---|---|---|
| `normal` | `corrida_completada`, `sin_fuentes` | suceso |
| `concurrencia` | `concurrencia` | suceso |
| `error` | cualquier aborto; evento crítico de la causa ya escrito por el productor | error |

### Decisiones de diseño

| Decisión | Alternativas | Recomendación y justificación |
|---|---|---|
| Contenido del evento de terminación | A. Minimal: `id_corrida`, marca_temporal, estado, motivo, `fuentes_procesadas` si disponible. B. Resumen completo. | **A**: el detalle ya existe en eventos por nodo; duplicar resúmenes acopla y ensucia. |
| Liberación del bloqueo | A. Incondicional. B. Condicional a propiedad: lock owner == `id_corrida`. | **B**: en ruta `concurrencia` esta corrida no posee el bloqueo; liberarlo rompería la corrida activa. |
| Fallo de liberación del bloqueo | A. Aborto/error fatal. B. Reintento único + registro local + continuar. | **B**: ya en terminación; obsolescencia de bloqueo auto-sana en próxima corrida. |
| Contexto corrupto al llegar | A. Aborto sin cierre. B. Cierre best-effort con motivo por defecto. | **B**: productor ya escribió evento crítico; Finalizar debe intentar liberar/cerrar con lo disponible. |
| Limpieza de recursos | A. Implícita por fin de proceso. B. Cierre explícito best-effort. | **B**: canal de navegador/API puede sobrevivir según implementación; cierre explícito evita fugas. |

### Especificación funcional
1. **Leer estado y recursos (best-effort)**. Entrada: contexto. Proceso: leer con tolerancia; contexto ilegible/parcial → estado `error`, motivo `desconocido`; motivo fuera del conjunto → normalizar a `error`/`desconocido`. Salida: estado y recursos a cerrar. Excepción: no aborta; continuar best-effort.
2. **Registrar evento de terminación**. Entrada: estado, motivo, `id_corrida`, `fuentes_procesadas` si disponible. Proceso: escribir `{id_corrida, marca_temporal, estado, tipo, motivo, fuentes_procesadas}`; fallo → reintento único; si persiste, registro crítico local y continuar. Salida: evento persistido o registro local. Excepción: fallo tras reintento no aborta.
3. **Liberar bloqueo si corresponde**. Entrada: estado de bloqueo, `id_corrida`. Proceso: si bloqueo existe y propietario == `id_corrida`, liberar; fallo → reintento único; si persiste, registro local y continuar; si no propietario, sin acción. Salida: bloqueo liberado o sin acción. Excepción: fallo tras reintento no aborta.
4. **Cerrar recursos abiertos (best-effort)**. Entrada: handle de sesión si existe; conexiones BD. Proceso: cerrar canal y conexiones; errores se registran localmente y no impiden terminación. Salida: recursos cerrados. Excepción: errores de cierre no abortan.
5. **Terminar proceso**. Entrada: —. Proceso: cerrar nodo. Salida: fin de corrida. Excepción: ninguna.

### Puntos de aprobación
- Conjunto oficial de estados/motivos y tipo de evento.
- Evento de terminación minimal con `fuentes_procesadas` opcional.
- Liberación de bloqueo condicional a propiedad; fallo cubierto por obsolescencia.
- Cierre best-effort ante contexto corrupto.
- Cierre explícito de recursos.
- Tabla funcional tal como está.

### Estado del módulo
Con este nodo queda completo el conjunto de nodos del Módulo 1. Pendientes de implementación: ninguno. La reedición `"Capturar ofertas"` v1.1 con `indice_set` en `estado_captura` quedó implementada y documentada (2026-08-11); el documento pasa a ser el registro as-built del Módulo 1. Identificadores alineados al catálogo español (decisiones D7/D8, 2026-08-11): `run_id`→`id_corrida`, `source_id`→`fuente_id`, `session_id`→`id_sesion`, `set_indice`→`indice_set`, `id_externo_url`→`id_externo`, `timestamp_ultima_verificacion`→`fecha_ultima_verificacion`, timeout `tiempo_agotado_ingreso/consulta/captura`.

**Nota as-built 2026-08-12 (decisión D14, limpieza Lote 1):** sin cambio de contrato ni de nodos: (a) el progreso de captura vive exclusivamente en `estado_captura` — se eliminaron los espejos de contexto `paginas_consumidas`/`capturadas_acumuladas_fuente`/`limite_alcanzado` (no documentados); (b) las ramas No de "¿Existe…?" y "¿Quedan fuentes…?" ya no fijan `motivo_terminacion`/`fecha_terminacion` en el contexto; el motivo oficial se entrega a "Finalizar Proceso" por parámetro del orquestador (mismo resultado final: evento de terminación con `sin_fuentes`/`corrida_completada`); (c) "Finalizar Proceso" consulta métricas una sola vez y las reutiliza para el evento de terminación y el cierre de corrida.

**Nota as-built 2026-08-12 (decisión D15, Lote 2):** los nombres de función de `shared/persistence.py` usados por los nodos se alinearon al catálogo español D7/D8 (`generar_id`, `leer_tabla`, `escribir_fila`, `adquirir_bloqueo`, `liberar_bloqueo`, `consultar_bloqueo`, `sondear_escritura`, `registrar_corrida`, `escribir_evento`, `actualizar_corrida`); los alias ingleses se eliminaron. Sin cambio de esquema ni de comportamiento; defecto cosmético conocido y no migrado: `indice_set INTEGER DEFAULT ''` en `ofertas_descubiertas`, `eventos` y `sesiones` (inerte).

**Nota as-built 2026-08-12 (decisión D17, Lote 4):** (a) el nodo decisión "¿Quedan ofertas por capturar…?" se retiró del flujo, del orquestador y de sus pruebas (decisión constante `no` desde la captura por listado D11; ver nota en su sección); "Registrar ofertas…" entrega control directamente a "¿Quedan sets…?"; (b) el cierre de sesión se delega al contrato `close_session` del adaptador (D13) en el orquestador y en "Finalizar Proceso" en lugar de `page.close()` directo; (c) se añadieron pruebas de integración del flujo completo con nodos reales (adaptador y arranque de Chromium simulados) y pruebas dedicadas de `shared/config.py`.

**Nota as-built 2026-08-14 (decisión D22, Lote A):** (a) "Registrar ofertas capturadas" persiste el lote completo en una sola conexión (`upsert_lote_ofertas`); ver nota as-built D22 en su sección — deroga NOTA 4.4 y actualiza RN-06, VAL-03, paso 3 y notas de implementación. (b) `RunContext` incorpora los campos tipados `browser`/`playwright_instance`; "Ingresar a la plataforma" los asigna en éxito y los limpia en fallo definitivo; "Finalizar Proceso" expone `cerrar_recursos(contexto)` como función pública (página → browser → instancia, resetea los tres campos, idempotente) y el orquestador la reutiliza al cambiar de fuente (`_cerrar_sesion_anterior`), con lo que cambiar de fuente ya no fuga el contexto de navegador anterior; el contrato `close_session` del adaptador (D17) no cambia. (c) "Finalizar Proceso" computa las métricas de cierre por SQL (`contar_filas`/`contar_distintos`, valores vacíos excluidos) en lugar de leer tablas completas a Python (`leer_tabla`); `generar_id` captura ids con `RETURNING` sin SELECT extra.

**Nota as-built 2026-08-14 (decisión D24, Lote C):** sin cambio de contrato ni de nodos — unificaciones internas de duplicados (P3 del plan de mejora): (a) `shared/utilidades.py` expone `ahora()`, `FORMATO_TIMESTAMP` y `TIPOS_ACCESO`; los nodos, `run_context` y `persistence` usan `ahora()` (se eliminaron `_ahora`/`_now` propios). (b) `escribir_evento_seguro` en `shared/persistence.py` reemplaza los envoltorios de escritura tolerante de INICIO, Capturar, control de fuentes, Registrar y Finalizar — RN-04 intacto: fallo de escritura se registra y no aborta; cada nodo conserva su dict exacto de evento. (c) `shared/ia_service.py` unifica el envío en `_enviar` (LLM-001..003 intactos); mensajes sin cambio contractual (solo capitalización local y evidencia "Empty page content."). (d) las políticas de captura se combinan con `{**global, **por_fuente}` (mismos defaults). (e) el adaptador usa un único `_revisar_estado` y "Buscar ofertas" un único `_resultado_fallo`. F-003 (drift pre-existente documentado): el evento de terminación de "Finalizar Proceso" se escribe en un solo intento con fallback a Loguru — solo `actualizar_corrida` conserva el reintento único; la redacción de la ficha queda como drift conocido (alinear si se autoriza el reintento).

**Nota as-built 2026-08-14 (decisión D25, Lote D):** sin cambio de contrato ni de nodos — cierre del plan de mejora P4 (ítems 13–18): (a) el catálogo oficial de estados de corrida de "Finalizar Proceso" es `en_ejecucion`, `completada`, `sin_fuentes`, `abortada` (decisión D4; la redacción de esta ficha que menciona `error`/`concurrencia` queda superada — F-001 corregido); el modelo `Corrida` valida los 10 campos de la tabla `corridas`, incluidos los de cierre (`fecha_fin`, `motivo_terminacion`, `total_ofertas`, `total_sucesos`, `total_errores`, `fuentes_procesadas`), y `actualizar_corrida` rechaza en runtime cualquier campo fuera del modelo (`extra="forbid"`). (b) los chequeos de consistencia de "Entrar a la plataforma" y "Buscar ofertas" validan valores reales (`estado` ∈ {`exito`, `fallo`}) en lugar de estructura — el contrato ERR-02 no cambia. (c) el cambio de fuente resetea iteradores y resultados de búsqueda vía `RunContext.marcar_cambio_de_fuente` (encapsulación; el nodo ya no muta estado interno del contexto). (d) el orquestador unifica la rama de error de nodo en `_ejecutar_nodo` (mismo flujo y motivos). (e) las credenciales de "Entrar a la plataforma" se resuelven una sola vez al inicio del nodo (una lectura de `.env`; antes una por intento) — mismo contrato `username`/`password` y mismo ERR-02. (f) la ruta de logs es configurable (`logging.logs_path` en `config/config.yaml`, default `logs`).

**Nota as-built 2026-08-14 (decisión D26, entrada directa al listado SDUi):** en "Buscar ofertas" (nodo "Aplicar filtros básicos") el adaptador ya no navega a la URL canónica `/jobs/search` sino directo al listado `/jobs/search-results/` (vía el mismo `_construir_url_resultados` de "Capturar ofertas", D11) y con `wait_until="commit"`: (a) la vista `/jobs/search` es un intermediario que LinkedIn redirige (`currentJobId`) y muestra un total de resultados falso e inconsistente (evidencia 2026-08-14: label "18 ofertas" vs conjunto real ~105-107); el listado SDUi sirve el conjunto real con su total fiel. (b) el `goto` tras el login con `wait_until="load"` fallaba transitoriamente (`fuente_inalcanzable`) y el reintento (D23) duplicaba la carga — `wait_until="commit"` (patrón ya probado en la paginación desde D11) elimina el fallo y la duplicación; el reintento D23 queda como red de seguridad sin dispararse. (c) "Capturar ofertas" ahora reutiliza la página 1 (su condición `"jobs/search-results" in page.url` se cumple) — una sola carga de búsqueda + paginación directa (COR-2140: `login → search-results → start=25/50/75/100/105`, sin reintentos, 0 errores). La validación (render de tarjetas, anti-bloqueo) y la evidencia `url: <search-results> | total: N` del nodo no cambian de contrato.

**Nota as-built 2026-08-17 (decisión D27, filtros SDUi verificados y endurecidos):** la UI nueva (`/jobs/search-results`) descarta `f_WT` y `location` de la URL y solo honra buckets de fecha canónicos; `f_WT=2` dejó de funcionar (COR-0001 capturó ofertas no conformes). Verificado empíricamente (Exp 1–8, 2026-08-17): (a) en "Aplicar los filtros básicos" (RN-02/RN-04 intactos) la modalidad `remoto` se codifica como `f_SAL=f_SA_id_225001:272001` (id interno de taxonomía, estable en el alcance probado) — `presencial`/`hibrido` NO son representables en la UI nueva y fallan con `filtros_no_aplicables` (ERR-02: el set se descarta, nunca se reintenta); (b) `fecha_publicacion` solo admite los 3 buckets canónicos `r86400` (Últimas 24 horas) / `r604800` (Última semana) / `r2592000` (Último mes) — cualquier otro `r<N>` (p. ej. `r18000` de 5 h) lo degrada LinkedIn silenciosamente a 24 h, por lo que falla con `filtros_no_aplicables`; la config pasa a `r86400`; (c) tras cargar el listado se **verifica el estado real de los filtros en el DOM** (chips): remoto como `div[role='radio'][aria-label='Filtrar por En remoto'][aria-checked='true']` y fecha como checkbox marcado cuyo `label[for]` coincide exactamente con el bucket (el DOM real usa `input` + `label[for]` HERMANOS, no anidados; el id del input es inestable por render — se resuelve siempre vía `label[for]`); (d) si la verificación falla, se intenta un **fallback por clics en la UI solo de los filtros faltantes** (clicar un radio activo lo DESACTIVA — verificado): chip remoto, pill de fecha `div[role='button'][aria-expanded='false'][componentkey^='SearchResults_filter_pill_JobSearchFacetSuggestionType_TIME_POSTED']` → opción del menú `div[role='radio'][aria-label='<bucket>']` → `Mostrar resultados`; tras el fallback se re-verifica y si sigue fallando → `filtros_no_aplicables` (nunca captura silenciosa de datos no conformes); (e) el total declarado se parsea del texto plano "N resultados" (`^(\d+) resultados$`; "Más de N resultados" → `None`) — el span `jobs-search-results__total-count` murió en la UI nueva; (f) en "Capturar ofertas" la base de paginación pasa a ser la URL **aplicada** (`page.url` cuando es `search-results`), que puede incluir artefactos de sesión (`currentJobId`, `origin`, `referralSearchId`) — extiende las notas D11/D26 (la evidencia no contiene credenciales); (g) el default de la config quedó **sin modalidad** (captura todas las modalidades: remoto, presencial e híbrido; el remoto se restringe descomentando `modalidad: remoto` en `config.yaml`, comentario D27). Verificado en producción (COR-0344, COR-0481): verificación superada sin fallback; COR-0481 sin `f_SAL` (sin modalidad) capturó 17 ofertas nuevas con 0 errores. Riesgo conocido: el id de taxonomía `f_SA_id_225001` es un enumerado semántico de LinkedIn sujeto a reordenación; si se rompe, la verificación falla ruidosamente con `filtros_no_aplicables` (nunca silencioso).

**Nota as-built 2026-08-17 (decisión D28, extracción de campos de tarjeta — grupo grande):** la evaluación de COR-0001 encontró 89/89 ofertas con `empresa_nombre`/`ubicacion_nombre`/`fecha_publicacion` vacíos aunque el DOM real de la tarjeta SDUi contiene esos datos. Verificado empíricamente (Exp 9, 2026-08-17, 3 páginas reales / 75 tarjetas únicas, clasificador 75/75; evidencia en `/tmp/opencode/evidencia_tarjetas_20260817/`): (a) en "Capturar ofertas" el adaptador extrae de cada tarjeta SDUi enlace (href canónico `/jobs/view/<id>` vía `componentkey`) + título (`span[aria-hidden='true']`, a veces 2 segmentos con "(Empleo verificado)") + empresa/ubicación/fecha relativa por clasificación de los `<p>` de la tarjeta — las clases CSS reales están **hasheadas por página** (no seleccionables), el texto es la única señal estable; el ruido fijo de la UI (`Visto`, `·`, `Adelántate a solicitar el empleo`, `Solicitar`, `Evaluando solicitudes de forma activa`) se excluye; las ubicaciones pueden llevar sufijo de modalidad "(En remoto)/(Híbrido)/(Presencial)"; la variante clásica (`base-search-card__subtitle`/`__location`) expone empresa/ubicación pero NO fecha (best-effort: fecha vacía); (b) `fecha_publicacion` se persiste como timestamp absoluto **aproximado** derivado de "Publicado hace N <unidad>" (minutos/horas/días/semanas/meses; mes = 30 días; precisión ±1 h por redondeo de LinkedIn, aceptable para el bucket `r86400`) y el **texto crudo se conserva íntegro en `observaciones`** — desviación aprobada de RN-03 (aditiva y reversible; la normalización de fechas del Módulo 2 sigue vigente sobre el crudo); (c) el total declarado se lee solo del DOM **visible** (excluye `script`/`style` y comentarios HTML) — endurece la nota D27 (e); (d) en "Aplicar los filtros básicos", `ofertas_primera_pagina` lleva los campos de tarjeta (extiende RN-08/Límites: el nodo entrega contenido, no solo referencias; la persistencia sigue en "Capturar ofertas"); (e) mapeo as-built D4: `Offer.empresa_id`/`ubicacion_id` transportan los strings crudos del adaptador a las columnas `empresa_nombre`/`ubicacion_nombre`; `empresa_id`/`ubicacion_id` permanecen NULL; el dedup D4/D22 no refresca estos campos en re-ejecución (solo `fecha_ultima_verificacion`). Verificado en producción (COR-0001, BD limpia, 2026-08-17): 89 ofertas, 0 errores, 89/89 `empresa_nombre`/`ubicacion_nombre`/`fecha_publicacion` (formato `%Y-%m-%d %H:%M:%S`)/`observaciones` (crudo "Publicado hace N horas") poblados. Fixtures regenerados desde markup real (3+2 tarjetas, total "89 resultados", botón "Siguiente" real). 323 tests (5 nuevos); ruff/mypy limpios.

**Nota as-built 2026-08-17 (decisión D29, revertido de la extracción de empresa/ubicación):** por decisión del usuario, la extracción de empresa y ubicación de la nota D28 se **revierte**: (a) en "Capturar ofertas" y "Aplicar los filtros básicos" el adaptador ya no extrae empresa/ubicación de las tarjetas (SDUi ni variante clásica); se conservan únicamente enlace, título, **fecha relativa** ("Publicado hace N <unidad>") y el total declarado visible (D28 (c) intacto); el crudo de la fecha sigue en `observaciones` (D28 (b) vigente); (b) las columnas `empresa_nombre`/`ubicacion_nombre` se **eliminan** de la tabla `ofertas_descubiertas` (esquema y BD vía `ALTER TABLE ... DROP COLUMN`; migración idempotente); `empresa_id`/`ubicacion_id` se mantienen como NULL en el MVP (D4/PMD-021: catálogos no poblados — fuera de alcance); (c) la BD se reinició (ofertas, corridas, eventos, sesiones, bloqueo y secuencias de ids) con backup `data/backup/job_search_pre_d29_20260817_211232.db`, **sin corrida** (según lo solicitado); (d) actualizan esta nota: NOTA 4.4 (crudo del adaptador en `empresa_nombre`/`ubicacion_nombre`), RN-03 y la nota as-built D28 (parcialmente derogada en (a)/(e)). 322 tests (1 eliminado, 3 reducidos a título/fecha/observaciones); ruff/mypy limpios.

**Nota as-built 2026-08-17 (decisión D30, trazabilidad de éxito, duración, logs y semántica de métricas):** alinea la implementación con los contratos de códigos ya listados en esta ficha y endurece la observabilidad sin cambiar contratos de nodos: (a) en "Entrar a la plataforma", el éxito de `ejecutar_ingreso` ahora escribe el evento `ingreso_exitoso` (suceso; evidencia acotada `sesion=<id>`, nunca credenciales — RN-08); los fallos siguen tipificándose en el nodo de registro (rama No); (b) en "Aplicar los filtros básicos", el éxito **con ofertas** escribe el evento `consulta_exitosa` (suceso; evidencia `set=<indice> | total=<total_declarado>`); el éxito sin ofertas y los fallos siguen tipificándose en el registro — un evento por resultado de búsqueda, sin duplicados; (c) en "Capturar ofertas", la evidencia de `captura_completada` incluye `duracion_s=<N>` (segundos del bloque de captura con reintentos, `time.monotonic()`); (d) en "Finalizar Proceso", la semántica de `total_sucesos` queda documentada: **sucesos del flujo previos al cierre** — el evento de terminación se escribe después del conteo y nunca se incluye (el conteo no cambia de comportamiento); (e) nivel de logs por defecto `INFO` (config); `LOG_LEVEL=DEBUG` en `.env` para depurar (documentado en `.env.template`). Verificado corrida real COR-0001 (2026-08-17, BD limpia): 98 ofertas, 0 errores, traza con `ingreso_exitoso` + `consulta_exitosa` + `captura_completada` (con `duracion_s`) + `ofertas_registradas`, `total_sucesos=4`; 327 tests (5 nuevos); ruff/mypy limpios.

**Nota as-built 2026-08-18 (decisión D31, limpieza de esquema y regla de no-vacíos):** por solicitud del usuario: (a) la columna `id_oferta` de `eventos` se **elimina** (era reservada y nunca se escribió; la trazabilidad evento-oferta no está implementada en el Módulo 1); (b) la tabla `fuentes` y el prefijo `FNT-` se **eliminan** (nunca poblada: las fuentes se definen en `config/config.yaml` y el flujo las usa en memoria — el concepto "fuente" del flujo permanece intacto); (c) la columna `identificador_origen` de `ofertas_descubiertas` se **elimina** (duplicado muerto de `id_externo`, que sigue siendo la clave de deduplicación del upsert); (d) **regla fundamental de gestión de datos: ningún campo vacío** — cuando un valor no aplica o no está disponible se guarda `N/A`/`N/R`, nunca `''`/NULL; se normaliza en la frontera de persistencia (`escribir_evento` y `_upsert_ofertas_en`, sin cambios en los nodos): `fuente_id`/`id_sesion`/`indice_set`/`evidencia` en eventos (el evento de terminación queda con `N/A`; `indice_set` conserva `0` como válido) y `descripcion_original`/`fecha_publicacion`/`observaciones`/`empresa_id`/`ubicacion_id` en ofertas (NULL → `N/A`; deroga D4/D29 en esas dos columnas; catálogos siguen sin poblar — PMD-021); exenciones: `id_externo` (colisionaría en la deduplicación) y `fecha_ultima_verificacion` (instrucción explícita del usuario: vacía hasta una re-visita); (e) `contar_distintos` trata `N/A` como vacío, así el evento de terminación no infla `fuentes_procesadas` en "Finalizar Proceso" (las métricas de cierre no cambian de comportamiento); (f) migración idempotente en `init_db` (`_migrate_limpieza_d31`): DROP de `fuentes` + su fila de `secuencia_ids`, DROP COLUMN protegido de las dos columnas y relleno `N/A` de vacíos previos; BD viva migrada (9→8 tablas) con backup `data/backup/job_search_pre_d31_20260818_123148.db`: 62 ofertas preservadas, sin vacíos en las columnas normalizadas, `fecha_ultima_verificacion` intacta (exenta), `fuentes_procesadas` de COR-0001 sigue en 1. 329 tests (2 nuevos); ruff/mypy limpios.

**Nota as-built 2026-08-19 (decisión D32, renombre de tabla):** por solicitud del usuario, la tabla física `ofertas` se **renombra** a `ofertas_descubiertas` (esquema, fila de `secuencia_ids`, queries, nodos, tests y documentación) para distinguirla de las tablas de etapas posteriores (Preparación, Evaluación, Procesamiento). El prefijo `OFE` y el contador de `secuencia_ids` no cambian; los índices conservan su nombre (`idx_ofertas_id_externo`, `idx_ofertas_id_corrida` — SQLite los preserva al renombrar); los nombres de función tampoco cambian (`upsert_oferta`, `upsert_lote_ofertas`, `_upsert_ofertas_en`, `_migrate_ofertas`...). Migración idempotente `_migrate_ofertas_descubiertas` al inicio de `init_db()` (antes del bucle de creación de esquemas, para que el `CREATE TABLE IF NOT EXISTS` no cree una copia vacía): `ALTER TABLE ... RENAME` solo si existe el nombre viejo y no el nuevo; actualización de `secuencia_ids` protegida por existencia de la tabla. BD viva migrada en sitio vía `init_db()`, **sin backup** (por instrucción del usuario): 62 ofertas preservadas, `secuencia_ids` con `ofertas_descubiertas|OFE|62`. 331 tests (2 nuevos: renombre + secuencia conservada, idempotencia); ruff/mypy limpios.

**Nota as-built 2026-08-20 (decisión D33, semántica dual de `fecha_ultima_verificacion`):** la columna `ofertas_descubiertas.fecha_ultima_verificacion` queda con **semántica dual** entre los dos módulos. El Módulo 1 (descubrimiento) la refresca en cada dedup hit de `upsert_oferta()` — смысла "última vez que la oferta fue vista en una captura"; el Módulo 2 (preparación) la reinterpreta como **marcador de verificación de duplicidad** — el nodo de Verificación de duplicidad es el único escritor dentro del Módulo 2 (`''` = pendiente de verificar). Ambos escritores son correctos dentro de su módulo; la columna lleva la marca temporal del escritor más reciente. El upsert del Módulo 1 sigue siendo válido y no se modifica (RN-02 / NOTA 4.4). La regla de no-vacíos (D31 punto 4) exenta esta columna: `''` significa "sin escritura", ni `N/A` ni otro placeholder. Decisión, semántica completa y notas D33/D34 documentadas en `docs/history/decision log.md` (D33 sub-decisión D-2) y en DOC-13A §2.1/§5.5.1 v1.11.

**Nota as-built 2026-08-25 (decisión D42, operación y rendimiento):** (a) el arranque del flujo (`ejecutar_flujo`) crea el esquema automáticamente si la base no tiene tablas (`inicializar_si_ausente`; corridas normales no ejecutan migraciones); (b) el parser de tarjetas vive ahora en el módulo puro `modules/discovery/adapters/tarjetas.py` (selección/clasificación/fecha relativa), re-importado por el adaptador — sin cambios de conducta.

**Nota as-built 2026-08-25 (decisión D41, columna `empresa` cruda desde la tarjeta):** espejo exacto del traspaso de `ubicacion`/`modalidad`: el clasificador de `<p>` de la tarjeta SDUi ya identificaba la empresa como **primer candidato utilizable** (lo descartaba para hallar la ubicación); ahora ese texto se conserva y se escribe en la nueva columna `ofertas_descubiertas.empresa TEXT DEFAULT 'N/R'` al registrar cada oferta nueva (`_ubicacion_sdui` refactorizada a `_texto_tarjeta_sdui`, que devuelve empresa+ubicación+modalidad en una pasada; con un solo candidato hay empresa sin ubicación; sin candidatos todo va vacío/'N/R'). Es SOLO display: el enlace al catálogo sigue siendo `empresa_id` (Módulo 2, página del anuncio). El upsert nunca la sobreescribe en re-registro (misma regla que `ubicacion`/`modalidad`); filas previas a D41 quedan en `'N/R'` (sin relleno retroactivo, decisión del usuario); variantes de tarjeta no SDUi no lo extraen.

**Nota as-built 2026-08-26 (decisión D45, traspaso registrado):** el capturador de tarjetas escribe también la columna `ubicacion` (renombrada desde `ubicacion_nombre`) y `modalidad` en la inserción — traspaso aprobado el 2026-08-25 desde el Módulo 2, que ya no extrae esos datos de la página ni los sobrescribe (PRM-006 clasifica el texto almacenado). El parser además empareja segmentos individuales de títulos multi-parte con barras verticales para no confundir empresa con ubicación.

**Nota as-built 2026-11-09 (decisión D70, filtro de nivel de experiencia + matriz de 9 grupos):** sin cambio de contrato ni de nodos — RN-02/RN-04/ERR-02 intactos. (a) "Aplicar los filtros básicos" acepta el nuevo filtro `nivel_experiencia`: los grupos lo declaran por etiqueta humana (Sénior/Administrador/Director/Ejecutivo), validada contra la taxonomía del listado SDUi comprobada en vivo (facet 227001: 277001·278001·272003·279001; el mapeo muerto `f_JT` del buscador clásico se retira); la URL emite siempre en orden canónico `f_SAL=f_SA_id_227001:277001,278001,272003,279001` con independencia del orden declarado; etiquetas desconocidas o repetidas, y la combinación con `modalidad` (comparten el espacio `f_SAL`), fallan con `filtros_no_aplicables`. (b) la verificación de DOM se extiende con `nivel_experiencia`: con una sola opción declarada debe estar marcada la casilla por nombre; con dos o más, la fila resumen contadora `<n>Nivel de experiencia` (formato observado en vivo: el número va pegado a la palabra); mismo patrón `label[for]`+input vía `_casilla_marcada`. (c) el fallback por clics (D27) gana la vía del nivel, probada en vivo: clic en la fila plegable del grupo (`label:has-text('Nivel de experiencia')`), marcar cada casilla oculta `input[type='checkbox'][aria-label='<nivel>']` con foco+espacio (el clic directo no es posible: la entrada no es visible) y confirmar con «Mostrar resultados»; la URL queda con el `f_SAL` canónico. (d) la configuración pasa a la matriz de 9 grupos definitivos del usuario (índices 0–8), cada uno con geoid Colombia `100876405`, `r86400` y los 4 niveles; D60 queda recortada por decisión del usuario. (e) evidencia de la sonda viva (solo lectura, copia aislada del perfil de sesión, sin tanda en curso): con la consulta de prueba el barrido pasó de 57 a 28 ofertas con los cuatro niveles (por nivel: Sénior 28, Administrador 17, Director 7, Ejecutivo 14); en tandas reales se espera menos volumen por grupo (el filtro excluye los niveles que la evaluación descartaba con veto).
