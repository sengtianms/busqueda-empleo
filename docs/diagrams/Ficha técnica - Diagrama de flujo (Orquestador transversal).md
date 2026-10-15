# Especificación canónica densificada — Orquestador transversal (capa transversal)

**Base de decisiones:** `docs/plans/Plan funcional fase 5.md` — sección "Orquestador de automatización (capa transversal)". Patrones as-built del orquestador interno del Módulo 1 (`modules/discovery/orchestrator.py`: decisiones D14, D17, D22, D25). Contratos de los módulos según sus fichas técnicas (Descubrimiento de oportunidades; Preparación de ofertas).

## Convenciones comunes (transversal)

- **Naturaleza**: capa transversal, NO módulo funcional. Solo **lanza, supervisa y registra**. No gestiona tablas de negocio, no accede a plataformas, no invoca la IA (la IA es invocada bajo demanda por los nodos que la necesitan).
- **Coordinación por base de datos**: los módulos no se conocen entre sí; cada uno lee su estado de entrada de la BD y escribe su estado de salida (Módulo 1 escribe `descubierta`; Módulo 2 lee `descubierta` y escribe `preparada`/`duplicada`). Esto hace cada módulo **auto-reparable**: si una corrida falla a medias, la siguiente ejecución retoma desde el estado que quedó.
- **Ejecución en serie por defecto**: `modo_ejecucion: serie` — cada módulo procesa todo lo que hay de su estado y termina con su evento de terminación; el siguiente arranca después. El modo paralelo se documenta como opción futura (`serie | paralelo`) y **no se implementa hoy** (requiere los 5 módulos para probarse y revisar el bloqueo global).
- **Disparo**: manual (hoy). Horarios de ejecución: fuera de alcance (decidido; trivial añadirlos después).
- **Bloqueo global**: NO lo gestiona el orquestador. Cada módulo lo toma en su INICIO y lo libera en su "Finalizar Proceso" (una sola ejecución activa a la vez en todo el pipeline). El orquestador asume que, mientras un módulo corre, ninguna otra corrida puede existir.
- **Trazabilidad**: cada módulo termina con su corrida y su evento de terminación en `eventos`; el orquestador registra además la **corrida programada** (resumen de módulos ejecutados y estados resultantes).
- **Regla de datos (D31)**: aplica a lo que el orquestador persiste — evidencia no vacía; `N/A` cuando no aplica. `EventoAlmacen` ya valida escrituras.
- **Sin valores fijos en el código**: comportamiento configurable vía `config.yaml` (sección `orquestador:`).

---

## Nodo proceso: "Corrida programada — lanzar y supervisar módulos"

**Versión**: 1.0 (aprobada)

### Posición
Capa transversal que precede a los módulos funcionales en cada disparo manual. Sin nodo antecesor; sucesor: ninguno (fin de la automatización).

### Objetivo
Ejecutar los módulos en el orden del pipeline (Módulo 1 → Módulo 2 → …) **sin que se conozcan entre sí**, esperar la terminación de cada uno y registrar el **resumen de la corrida programada** (módulos ejecutados, estados resultantes) como trazabilidad. El orquestador solo lanza y supervisa: no conoce la lógica interna de los módulos, no gestiona tablas de negocio ni lógica de negocio.

### Descripción funcional
Al recibir disparador manual:

1. **Cargar y validar configuración** `orquestador:` (claves, rangos, `modo_ejecucion`).
2. **Crear corrida programada**: `id_corrida` único (COR-xxxx, `generar_id`), `fecha_inicio` (T0), estado `en_ejecucion` — fila en `corridas` como contenedor de trazabilidad del resumen.
3. **Por cada módulo en orden** (lista de configuración):
   a. Hito informativo con Loguru ("Módulo X iniciado").
   b. Invocar `ejecutar_flujo()` del módulo y **esperar su terminación**.
   c. **Derivar el resultado** desde la BD: corrida del módulo cerrada dentro de la ventana de ejecución (corridas con `fecha_inicio ≥ T0` y `fecha_fin ≠ ''`, la más reciente). El bloqueo global garantiza que solo la corrida del módulo recién ejecutado puede cerrarse en esa ventana. Si no hay corrida cerrada (fallo previo a registrar corrida en el módulo) → `no_iniciada` (valor de evidencia, no estado del vocabulario de corridas).
   d. Escribir evento `modulo_ejecutado` (suceso) con evidencia `modulo=<nombre>;estado=<estado>;motivo=<motivo>;id_corrida=<id>`.
   e. Pausa configurable entre módulos (`pausa_entre_modulos_segundos`).
4. **Registrar el resumen**: evento `corrida_programada` (suceso final) con evidencia `modulo=estado;modulo=estado;…` (todos los módulos de la corrida programada).
5. **Cerrar la corrida programada**: `actualizar_corrida` con los campos del modelo `Corrida` (D25, `extra="forbid"`) — estado `completada` (normal) o `abortada` (fallo propio del orquestador), `fecha_fin`, `motivo_terminacion`; métricas del resumen: `total_sucesos` = eventos `modulo_ejecutado` (semántica D30: el evento de terminación nunca se cuenta), `total_errores` = eventos `modulo_fallido`, `total_ofertas` = 0 y `fuentes_procesadas` = 0 (no aplican a la corrida programada; el detalle vive en la evidencia de los eventos).
6. **Fin de la automatización**: log del resumen con Loguru y terminar. La automatización termina cuando **todos los módulos terminaron sus corridas**, cada una con su evento de terminación en `eventos`.

### Entradas
- Disparador manual (hoy) o programado (futuro, fuera de alcance).
- Almacén de configuración: sección `orquestador:` (`modo_ejecucion`, `modulos`, `pausa_entre_modulos_segundos`).
- Registro declarativo de módulos (código): nombre, `estado_entrada`, `estado_salida`, función pública `ejecutar_flujo()`.
- BD: `corridas` y `eventos` (lectura para derivar resultados; escritura del resumen).

### Salidas
- Corrida programada cerrada en `corridas` con su resumen.
- Eventos `modulo_ejecutado` (por módulo) y `corrida_programada` (resumen final) en `eventos`.
- Logs de hitos con Loguru.
- Fin del proceso (sin sucesor).

### Reglas de negocio
- **RN-01**: el orquestador no gestiona tablas de negocio ni lógica de negocio; solo lanza, supervisa y registra.
- **RN-02**: orden estricto del pipeline; no lanza el siguiente módulo hasta que el anterior terminó (serie).
- **RN-03**: no invoca la IA, no accede a plataformas, no toma ni libera el bloqueo global (eso es de los INICIO/Finalizar de cada módulo).
- **RN-04**: fallo de un módulo (corrida `abortada`, motivo de error, o excepción no capturada) **no detiene** la corrida programada: se registra el resultado real y se continúa con el siguiente módulo (auto-reparación; el resumen refleja el estado real; el disparo manual puede repetirse sin consecuencias).
- **RN-05**: el resultado de cada módulo se deriva de la BD (corrida cerrada en la ventana de ejecución), no de un contrato de retorno (el `ejecutar_flujo()` del Módulo 1 no retorna resultado hoy).
- **RN-06**: el resumen se registra siempre, complete la corrida programada en `completada` o en `abortada`.
- **RN-07**: `id_corrida` de la corrida programada es distinto de los `id_corrida` de los módulos; los eventos del resumen se enlazan a ella (`EventoAlmacen.id_corrida`).
- **RN-08**: `modo_ejecucion: paralelo` en configuración es error de configuración (`error_critico`) hasta que se implemente (decisión del plan).
- **RN-09**: el estado de salida del pipeline no se escribe en ninguna tabla de negocio: los estados por módulo ya viven en `ofertas_descubiertas` (coordinación por BD, sección 2 del plan).

### Validaciones
- **VAL-01**: configuración `orquestador:` completa y con rangos válidos (`modo_ejecucion ∈ {serie, paralelo}`, lista de módulos no vacía, `pausa_entre_modulos_segundos ≥ 0`).
- **VAL-02**: solo `serie` es aceptado hoy; `paralelo` → `error_critico`.
- **VAL-03**: cada módulo de la lista está registrado (nombre, estados de entrada/salida, `ejecutar_flujo` invocable).
- **VAL-04**: cada módulo terminó con corrida cerrada en la ventana o se registró su fallo (`modulo_ejecutado` con el estado real).
- **VAL-05**: eventos del resumen con evidencia no vacía (D31).

### Condiciones y ramas
- **Normal**: todos los módulos terminaron sus corridas (cada una con su evento de terminación) → resumen + cierre `completada`.
- **Fallo de módulo**: no altera el flujo (RN-04); la corrida programada cierra `completada` con el estado real de cada módulo en la evidencia.
- **Excepción propia**: configuración inválida, fallo al crear/cerrar la corrida programada o fallo persistente de registro → `error_critico`; aborto sin lanzar (o sin continuar) los módulos.

### Errores y eventos

| Código | Error / evento | Reint. | Detección | Registro / acción | Estado |
|---|---|---|---|:---:|---|---|
| ERR-01 | Configuración ausente / ilegible / corrupta / `paralelo` | No | 1 | Evento crítico si accesible; aborto | `abortada` (`error_critico`) |
| ERR-02 | Fallo al crear la corrida programada / generar id | Sí | 2 | Reintento único; si persiste, aborto | `abortada` (`error_critico`) |
| ERR-03 | Excepción no capturada de `ejecutar_flujo()` del módulo | No | 3b | Capturar, evento error `modulo_fallido`, continuar (RN-04) | continúa |
| ERR-04 | Fallo al escribir evento del resumen | No | 3d/4 | Best-effort: log local y continuar (patrón "Finalizar Proceso") | continúa |
| ERR-05 | Fallo al cerrar la corrida programada | Sí | 5 | Reintento único; si persiste, log local (la traza queda en `eventos`) | continúa |
| EVT-01 | `modulo_ejecutado` | No | 3d | Suceso con evidencia `modulo=<nombre>;estado=<estado>;motivo=<motivo>;id_corrida=<id>` | continúa |
| EVT-02 | `corrida_programada` | No | 4 | Suceso final con evidencia `modulo=estado;…` | continúa |
| EVT-03 | `modulo_fallido` | No | 3b | Error con evidencia `modulo=<nombre>;estado=<estado>;motivo=<motivo>;id_corrida=<id>` (formato `campo=valor` — D34, D-6) | continúa |

**Contrato de códigos**: `modulo_ejecutado` (suceso), `corrida_programada` (suceso), `modulo_fallido` (error).

### Escenarios límite
- Módulo 1 termina `abortada` (p. ej. credenciales inválidas) → el orquestador continúa al Módulo 2, que resuelve `sin_pendientes`; el resumen registra ambos estados reales.
- Excepción lanzada por un módulo (bug) → ERR-03; no aborta la corrida programada.
- Módulo que falló antes de registrar su corrida → resultado `no_iniciada`; la evidencia lo refleja.
- Configuración con `paralelo` → ERR-01 antes de lanzar nada.
- Corrida programada lanzada dos veces seguidas (disparo manual repetido) → cada ejecución es independiente; los módulos deduplican por sus propios mecanismos (Módulo 1: `id_externo`; Módulo 2: duplicidad por título+empresa con descripción difusa — el marcador `fecha_ultima_verificacion` solo evita re-verificar, no deduplica).
- Pausa entre módulos: evita ráfagas de actividad de red consecutivas (prudencia anti-bloqueo, misma filosofía del Módulo 2).

### Dependencias y contratos
- **Antecesor**: disparo manual (hoy).
- **Sucesores**: los módulos en orden — `modules/discovery/orchestrator.ejecutar_flujo` (existe) y `modules/preparation/orchestrator.ejecutar_flujo` (a construir con el Módulo 2).
- **Contratos consumidos**: `generar_id`, `registrar_corrida`, `actualizar_corrida`, `escribir_evento`, `contar_filas` (`shared/persistence.py`); nueva helper `leer_ultima_corrida_cerrada` (o equivalente) para derivar el resultado del módulo; registro declarativo de módulos en código.
- **Contratos entregados**: corrida programada cerrada + eventos del resumen; sin salida de datos de negocio.

### Decisiones de diseño

| Decisión | Alternativas | Recomendación y justificación |
|---|---|---|
| Resultado por módulo | A. Los módulos devuelven `ResultadoModulo` (el Módulo 1 requiere cambiar la firma de `ejecutar_flujo()`). B. Derivarlo de `corridas` (corrida cerrada dentro de la ventana de ejecución). | **B**: uniforme sin tocar el Módulo 1; el bloqueo global garantiza que solo la corrida del módulo ejecutado puede cerrarse en la ventana (T0 = `fecha_inicio` de la corrida programada). El contrato de retorno queda como contrato futuro para módulos nuevos. |
| Registro del resumen | A. Fila propia en `corridas` + eventos `modulo_ejecutado`/`corrida_programada`. B. Solo log con Loguru. | **A**: trazabilidad durable y consultable en el almacén oficial (`eventos`), sin migraciones — las tablas y el vocabulario de estados (`completada`/`abortada`) ya existen. |
| Fallo de un módulo | A. Abortar la corrida programada. B. Registrar el estado real y continuar con el siguiente. | **B**: auto-reparación (cada módulo retoma en la siguiente ejecución); el resumen refleja el estado real; el disparo manual puede repetirse sin consecuencias. |
| Orden y comportamiento | A. Lista de módulos fija en código. B. `modulos`, `modo_ejecucion` y pausas en `config.yaml` (`orquestador:`). | **B**: sin valores fijos en el código (decisión del plan); el mapeo nombre → función es cableado en código (registro declarativo). |
| Excepción no capturada de un módulo | A. Abortar. B. Capturar, evento `modulo_fallido`, continuar. | **B**: consistente con la decisión de fallo de módulo (mismo criterio de no detener la corrida programada). |

### Notas de implementación

**Nota as-built 2026-08-25 (decisión D42):** el arranque (`ejecutar_corrida_programada`) inicializa el esquema automáticamente cuando la base no tiene tablas; el chequeo prevuelo de este lote vive en `scripts/preflight.py` y el diagnóstico post-corrida en `scripts/reporte_corrida.py`.

**Nota aprobado M3-docs (decisión D48, previo a construcción):** el Módulo 3 «Evaluación inicial» se suma tercero tras Preparación, solo después de su vuelta real de verificación en solo (`orquestador.modulos: [descubrimiento, preparacion, evaluacion]`; hasta entonces la lista sigue con 2). Su resultado se lee desde la base como los demás; sin migraciones propias del orquestador.
- Estructura: `modules/orchestrator/orchestrator.py` con la función pública `ejecutar_corrida_programada()` (distinta de `ejecutar_flujo()` de los módulos) y el registro declarativo `MODULOS: list[ModuloOrquestado]` (nombre, `estado_entrada`, `estado_salida`, `ejecutar_flujo`). Tests de integración en `tests/test_orquestador_transversal.py` (patrón de `tests/test_orquestador_integracion.py`: flujo completo con nodos reales y arranque de plataforma simulado).
- Configuración nueva en `config/config.yaml` → `orquestador:` (`modo_ejecucion: serie`, `modulos: [descubrimiento, preparacion]`, `pausa_entre_modulos_segundos`).
- Sin migraciones de esquema propias: `corridas` y `eventos` ya existen; `motivo_terminacion` es TEXT libre; `EstadoCorrida` reutiliza `completada`/`abortada`. *(As-built D42: el arranque además crea el esquema completo si la base está vacía, vía `inicializar_si_ausente`.)*
- Hitos informativos con Loguru (patrón del orquestador del Módulo 1); el evento final nunca se cuenta en métricas de módulos (semántica D30 intacta: el resumen es trazabilidad de la corrida programada, no de los módulos).
- La **prueba real 1→2** (al cierre del Módulo 2) valida: Módulo 1 termina su corrida, Módulo 2 la suya (lee `descubierta`, escribe `preparada`/`duplicada`), y la corrida programada queda con sus eventos `modulo_ejecutado` × 2 + `corrida_programada`. La **prueba real 1→2→3** (al cierre del Módulo 3, D48) añade: Módulo 3 lee `preparada` y escribe `aceptada_ei`/`descartada_ei`, con `modulo_ejecutado` × 3.

### Pasos funcionales
1. **Cargar y validar configuración**. Entrada: `config.yaml` (`orquestador:`). Proceso: leer y validar claves, rangos y `modo_ejecucion`. Salida: configuración. Val: VAL-01, VAL-02. Err: ERR-01.
2. **Crear corrida programada**. Entrada: configuración. Proceso: `generar_id` + `registrar_corrida` (estado `en_ejecucion`, `fecha_inicio` = T0). Salida: `id_corrida` programada. Val: VAL-03. Err: ERR-02.
3. **Ejecutar módulos en orden**. Entrada: `id_corrida` programada, lista de módulos. Proceso: por módulo — hito log; invocar `ejecutar_flujo()`; esperar terminación; derivar resultado (`leer_ultima_corrida_cerrada`, ventana desde T0); evento `modulo_ejecutado` (o `modulo_fallido` si excepción); pausa entre módulos. Salida: resultados por módulo. Val: VAL-04. Err: ERR-03, ERR-04.
4. **Registrar resumen**. Entrada: resultados. Proceso: evento `corrida_programada` con evidencia `modulo=estado;…` (best-effort). Salida: evento. Val: VAL-05. Err: ERR-04.
5. **Cerrar corrida programada**. Entrada: estado, motivo, métricas del resumen. Proceso: `actualizar_corrida` (`completada` o `abortada`, `fecha_fin`, `motivo_terminacion`). Salida: corrida cerrada. Err: ERR-05.
6. **Terminar proceso**. Entrada: —. Proceso: log del resumen; cerrar nodo. Salida: fin de la automatización. Err: ninguna.

---

## Estado del módulo

Pendiente de implementación — se construye **al cierre del Módulo 2** con la prueba real de corrida secuencial 1→2 (decisión del plan; construcción incremental). Este documento es la base autoritativa de construcción. El Módulo 1 ya aporta su `ejecutar_flujo()` (`modules/discovery/orchestrator.py`); el Módulo 2 aportará el suyo al implementarse (`modules/preparation/orchestrator.py`).

## Dependencias (consolidadas)

1. `config/config.yaml`: sección nueva `orquestador:` (`modo_ejecucion: serie`, `modulos: [descubrimiento, preparacion]`, `pausa_entre_modulos_segundos`).
2. `shared/persistence.py`: nueva helper `leer_ultima_corrida_cerrada(...)` (derivar el resultado por módulo desde `corridas`); `shared/retry.py`: `ejecutar_con_reintento` para los reintentos del nodo (ERR-02/ERR-05).
3. `modules/orchestrator/`: `orchestrator.py` (público `ejecutar_corrida_programada()`) + registro declarativo de módulos; tests `tests/test_orquestador_transversal.py`.
4. `modules/preparation/`: contrato público `ejecutar_flujo()` (se implementa con el Módulo 2).
5. Sin migraciones de esquema propias (las tablas `corridas`/`eventos` y el vocabulario de estados ya existen). *(As-built D42: si la base no tiene tablas, el arranque las crea antes de registrar la corrida.)*