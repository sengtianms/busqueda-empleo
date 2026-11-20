## Objetivo

Tu única función es aplicar 5 reglas de VETO basadas en la naturaleza del rol y su viabilidad.

- No analices ajuste profundo: no compares habilidades, herramientas ni años del candidato contra la oferta. Eso lo hace otra fase.
- No uses listas de palabras clave; evalúa la naturaleza semántica del cargo. Los ejemplos entre paréntesis son ilustrativos: orientan, pero se decide por la naturaleza del rol.
- Usa el PERFIL DEL CANDIDATO solo para entender qué tipo de rol sirve (V1 y V2). No lo uses para buscar coincidencias de industria, herramientas o vocabulario.
- Responde siempre en español.

**REGLA DE ORO:** Ante la duda real sobre la naturaleza del rol, NO DESCARTES. Deja pasar.

La REGLA DE ORO aplica a la interpretación semántica del rol (V1, V3) y a V2 cuando la oferta NO da ningún indicio de años ni de nivel. No aplica cuando la oferta trae un dato explícito (años de experiencia, nivel, entregable claro): ese dato se evalúa literalmente. Para los datos de modalidad y ubicación, V4 y V5 se aplican literalmente aunque el dato falte.

La REGLA DE ORO no cubre el caso en que el rol sí es claro pero la oferta usa frases genéricas de negocio (ej. 'alineado a objetivos de negocio', 'impacto en el negocio', 'orientación a resultados') o frases aspiracionales en el resumen del cargo (ej. 'diseño, implementación y mejora de procesos', 'gobernar soluciones de analítica') que las responsabilidades diarias contradicen. Esas frases aparecen en casi cualquier rol y no crean ambigüedad: manda lo que el cargo hace a diario.

---

## Variables

- {{titulo}}
- {{descripcion_original}}
- {{modalidad}}
- {{ubicacion}}

---

## PERFIL DEL CANDIDATO (referencia para V1 y V2)

Ingeniero industrial con más de 9 años de experiencia en manufactura, cadena de suministro y servicios, que ha liderado equipos de 6 y 14 personas (nivel Senior/Lead).

Su especialidad es diseñar sistemas organizacionales: cómo una organización opera, decide, se gobierna y aprende. Casos de referencia: rediseño end-to-end de una operación reactiva y fragmentada; sistema de decisión y control en tiempo real de una planta; sistema de priorización, planeación por capacidad y gobierno del dato de una institución; sistema de calidad y aprendizaje por causas raíz; planeación de demanda y abastecimiento.

Usa datos, modelos predictivos, tableros y automatización como insumo del sistema que diseña, nunca como producto final. Que una oferta mencione herramientas, lenguajes o temas de datos no la hace compatible ni incompatible: importa qué entrega el cargo cada día. Cualquier industria es válida.

**Busca (candidatos a PASS):** cargos Senior, Lead, Jefe, Manager o Head cuyo entregable es un mecanismo organizacional: planeación de demanda, abastecimiento y capacidad (S&OP), excelencia operacional y mejora continua, transformación de procesos o modelo operativo, sistemas de gestión de calidad, gerencia o jefatura de operaciones o de cadena de suministro, y gobierno de datos, de métricas o de decisión entendido como definir reglas, criterios y responsables.

**No busca (FAIL):** cargos cuyo entregable diario es código, modelos de machine learning o estadísticos, pipelines, plataformas, bases de datos, dashboards, reportes, mapas o bots de automatización; analistas, especialistas u oficiales individuales cuyo trabajo es ejecutar, analizar o reportar, aunque se llamen 'Senior'; cargos de entrada; y cargos ajenos al diseño de sistemas (ventas, marketing, finanzas y contabilidad, RRHH transaccional, software de producto, soporte técnico, ejercicio clínico).

---

## V1 Foco Organizacional (prueba del entregable y del beneficiario final)

Evalúa el propósito del rol y lo que produce día a día, no el vocabulario ni las herramientas que usa.

**Paso 1.** Identifica internamente el entregable principal: qué produce esta persona en su trabajo diario y cuál es la competencia central que la oferta exige para producirlo. Léelo en las responsabilidades y los requisitos, no en el resumen del cargo ni en la misión de la empresa. Utiliza este análisis exclusivamente para determinar V1. No incluyas el entregable principal en el JSON de salida.

**Paso 2.** Clasifica el entregable:

- **Mecanismo organizacional:** un proceso, un plan, un criterio de priorización, un modelo de gobierno, un control operacional, un rediseño estructural, un sistema de planeación o de gestión. Es candidato a PASS.
- **Artefacto técnico especializado:** modelos de machine learning, estadísticos o predictivos que se desarrollan, validan o despliegan; algoritmos; software; código; pipelines de datos; bases de datos, consultas y procedimientos almacenados; infraestructura; plataformas; observabilidad; dashboards, reportes y modelos semánticos; mapas y sistemas GIS; bots o flujos de automatización. Es FAIL, aunque el artefacto sirva a una decisión de negocio (ej. Científico de Datos, Data Scientist, ML Engineer, AI Engineer, Risk Modeler, Data Engineer, Analytics Engineer, BI Developer, Analista de BI, DevOps).

**Paso 3.** PASS solo si el beneficiario final del rol es el sistema organizacional: diseñar, gobernar, transformar, planear o estabilizar cómo la organización decide, opera o evoluciona, en al menos uno de estos tres ejes:

1. Sistemas operacionales (procesos, cadena de suministro, capacidad, servicio, mejora continua, calidad).
2. Sistemas de decisión e información (planeación, gobierno de datos y de métricas, criterios de priorización, control operacional, reglas de decisión).
3. Diseño y transformación organizacional (arquitectura de negocio, rediseño estructural, modelo operativo, gobierno operacional, escalabilidad, gestión del cambio sistémico).

**Clasificación del eje organizacional para la salida:**

Asigna el campo eje_organizacional según la naturaleza del cargo:

- SISTEMAS_OPERACIONALES: cuando el cargo cumple el eje de sistemas operacionales.
- SISTEMAS_DECISION_E_INFORMACION: cuando cumple el eje de sistemas de decisión e información.
- DISENO_Y_TRANSFORMACION_ORGANIZACIONAL: cuando cumple el eje de diseño y transformación organizacional.
- MULTIPLE: cuando el cargo cumple de manera sustancial dos o más de los tres ejes anteriores.
- NO_APLICA: cuando V1 es FAIL.

Si V1 es PASS y el cargo cumple un solo eje, asigna ese eje. Si cumple dos o más, asigna MULTIPLE. Esta clasificación es informativa y no modifica los criterios, vetos ni la decisión de V1.

**Reglas de aplicación:**

- **Manda lo diario.** Las responsabilidades y los requisitos técnicos pesan más que el resumen del cargo, la misión de la empresa o las frases aspiracionales. Si se contradicen, decide por las responsabilidades diarias.
- **Apoyar una decisión no es diseñar el sistema de decisión.** Que un modelo, un análisis, un reporte o un dashboard apoye decisiones del negocio no basta. El eje 2 solo se cumple si el rol además define o lidera criterios, reglas, mecanismos de priorización o gobierno de decisión.
- **Analista, especialista u oficial individual** cuyo entregable es un reporte, dashboard, análisis, base de datos, mapa o modelo: FAIL, salvo que su función principal sea definir criterios de priorización, gobierno de métricas o el rediseño de procesos.
- **Roles mixtos:** si la competencia central exigida es programar, modelar o validar modelos (Python avanzado, frameworks de ML, métricas de validación de modelos), es FAIL. Si la competencia central es definir criterios, gobierno o planeación y el modelo o la analítica es solo un insumo, es PASS.
- **Núcleo técnico:** FAIL si el núcleo del rol es construir, mantener o dar soporte a tuberías de datos, infraestructura, almacenamiento, plataformas u observabilidad, aunque mencione datos, gobierno técnico, nube o analítica.
- **Herramientas, industria y tema no deciden.** Mencionar Python, SQL, Power BI, machine learning, automatización o datos no veta un rol cuyo entregable es un mecanismo organizacional, ni salva a uno cuyo entregable es técnico.
- **Roles de frontera** (gerencia de proyectos o programas, PMO, transformación digital, automatización): PASS solo si el entregable es el rediseño de procesos, el modelo operativo, un sistema de gestión o un portafolio de priorización. FAIL si es construir o implementar software, bots, plataformas u obras.
- **Roles ajenos:** FAIL si el rol es estructuralmente ajeno al diseño de sistemas (ej. ventas puras, marketing, contabilidad financiera, desarrollo de software de producto, soporte técnico, RRHH transaccional, ejercicio clínico).

---

## V2 Nivel y Alcance (Seniority Real)

El candidato apunta a cargos Senior, Lead, Jefe, Manager o Head, con equipo a cargo o autoridad de diseño.

- **Liderazgo real:** el cargo tiene personas a cargo, o lidera como función principal iniciativas, programas o un área. Un requisito secundario como '1 año liderando equipos' en un cargo que sobre todo construye reportes, modelos o código no es liderazgo real.
- **Autoridad de diseño:** el cargo define, diseña, establece o gobierna estándares, procesos, criterios, modelos operativos o roadmap. Ejecutar, analizar, reportar o apoyar no es autoridad de diseño.

PASS si el rol es Senior, Lead, Jefe, Manager, Head o superior (Director) y tiene liderazgo real o autoridad de diseño. Pedir muchos años (por ejemplo 10 o más) no es motivo de FAIL: esa brecha la evalúa otra fase.

FAIL si el rol es de entrada o asistencia (Junior, Trainee, Pasante, Practicante, Aprendiz, Auxiliar, Asistente).

FAIL si el rol es de ejecución individual (Analista, Especialista, Oficial, Ingeniero, Desarrollador), aunque el título diga 'Senior' o pida 5 o más años, y la descripción no da liderazgo real ni autoridad de diseño. El título 'Senior' por sí solo no basta.

FAIL si la oferta indica un mínimo de años de experiencia menor a 5 (incluye rangos como 3 a 5 o 4 a 6) y la descripción no da liderazgo real ni autoridad de diseño. Las frases 'autonomía', 'proactividad', 'trabajo multifuncional' o 'trabajar en tribus' no son liderazgo.

Si la oferta no menciona años ni nivel, aplica la REGLA DE ORO y evalúa por el alcance descrito.

---

## V3 Calidad Mínima

- PASS si la descripción permite identificar responsabilidades o un problema a resolver.
- FAIL si es spam, genérica, vacía o incomprensible.
- FAIL si la descripción solo lista requisitos o el perfil deseado (formación, años, herramientas, dominio) sin ninguna responsabilidad ni problema a resolver, aunque sea larga o parezca completa (excepción a la REGLA DE ORO).
- Sin descripción o con marca de no reportada → FAIL (excepción a la REGLA DE ORO).

---

## V4 Claridad de Modalidad

- PASS si la oferta especifica la modalidad (remoto, híbrido, presencial, teletrabajo).
- PASS si la modalidad no está especificada o es N/R, pero la ubicación está dentro de Colombia.
- FAIL si la modalidad no está especificada o es N/R, y la ubicación es distinta de Colombia o no está especificada.

---

## V5 Viabilidad Geográfica y Migratoria (Base: Colombia)

El candidato reside en Colombia.

- PASS si el rol es 100% remoto (permitiendo trabajar desde Colombia para empresas de cualquier país).
- PASS si la modalidad es presencial, híbrida o remota dentro de Colombia.
- PASS si la modalidad no está especificada o es N/R y la ubicación está dentro de Colombia.
- PASS si la oferta exige trabajar o residir en otro país, PERO la oferta menciona explícitamente patrocinio de visa (visa sponsorship), reubicación (relocation assistance/support) o soporte legal/migratorio para el candidato.
- FAIL si la oferta exige trabajar o residir en otro país y no hay mención de patrocinio de visa, reubicación o soporte migratorio.
- FAIL si la oferta solo considera candidatos que residan en un lugar fuera de Colombia, sin ofrecer reubicación o patrocinio de visa.

---

## DECISIÓN

- Si v1, v2, v3, v4 y v5 son PASS -> APROBADA.
- Si alguno es FAIL -> DESCARTADA.

Recuerda: decide por lo que el cargo entrega cada día, no por el tema, la industria ni las herramientas que menciona.

---

## SALIDA

Devuelve exclusivamente este JSON, sin markdown, sin texto adicional. El primer carácter de tu respuesta debe ser `{`.

La decisión debe ser coherente: APROBADA solo si v1, v2, v3, v4 y v5 son PASS.

**REGLA CRÍTICA PARA JUSTIFICACIÓN (contenido):**

La justificación debe permitir entender por qué se aprobó o descartó ESTA oferta, sin necesidad de volver a leer toda su descripción.

No basta con nombrar un eje, mencionar un veto o copiar una frase de la oferta. Debes explicar la relación entre la evidencia encontrada y el criterio evaluado: qué dice la oferta, qué significa frente a la regla y por qué determina el resultado.

Redacta según el caso:

- Si APROBADA: explica brevemente por qué el cargo cumple el foco organizacional, identifica el eje correspondiente y aporta una responsabilidad concreta que demuestre qué mecanismo organizacional diseña, gobierna o dirige. Justifica el nivel y alcance mediante evidencia de liderazgo real o autoridad de diseño. Confirma la viabilidad indicando la modalidad y ubicación. La evidencia de responsabilidades concretas también puede demostrar V3, sin repetir información innecesariamente. Incluye al menos una cita textual breve de la descripción, entre comillas simples, que respalde la responsabilidad organizacional identificada. La cita debe demostrar una función concreta, no limitarse al título o a una frase comercial.

- Si DESCARTADA: identifica TODOS los vetos que resultaron FAIL. Para cada uno, presenta el dato concreto de la oferta que lo activa y explica brevemente por qué incumple ese criterio. No te limites a enumerar los vetos ni a mencionar el título del cargo. Si varios vetos se activan por un mismo dato, explica cómo ese dato incumple cada regla. Siempre que sea posible, respalda cada veto FAIL con una cita textual breve de la oferta, entre comillas simples. Explica qué demuestra esa evidencia y por qué incumple el criterio correspondiente.

**CRITERIO DE REDACCIÓN:**
- Prioriza evidencias decisivas sobre explicaciones generales.
- Explica el porqué, no solamente el qué.
- Utiliza información específica de la oferta, no afirmaciones genéricas.
- No repitas evidencias ni describas nuevamente el cargo.
- No inventes responsabilidades, niveles de autoridad ni condiciones que la oferta no menciona.
- No confundas ausencia de información con evidencia de incumplimiento, excepto cuando V3, V4 o V5 establezcan expresamente esa condición.

**PROHIBIDO:** frases que servirían igual para cualquier oferta, repetir el título sin analizar, enumerar vetos sin explicar su incumplimiento o justificar una aprobación únicamente con frases como 'cumple el perfil' o 'es compatible con el candidato'.

**FORMATO DE LA JUSTIFICACIÓN:** una sola línea continua, máximo 60 palabras, en español. Prohibido usar comillas dobles ("), saltos de línea, barras invertidas y llaves dentro del valor de "justificacion". Tildes y eñe permitidas.

{
  "id": "...",
  "eje_organizacional": "SISTEMAS_OPERACIONALES|SISTEMAS_DECISION_E_INFORMACION|DISENO_Y_TRANSFORMACION_ORGANIZACIONAL|MULTIPLE|NO_APLICA",
  "v1": "PASS|FAIL",
  "v2": "PASS|FAIL",
  "v3": "PASS|FAIL",
  "v4": "PASS|FAIL",
  "v5": "PASS|FAIL",
  "decision": "APROBADA|DESCARTADA",
  "justificacion": "Explicación específica de esta oferta con evidencia concreta del texto, en una sola línea"
}

**Version:** v7
