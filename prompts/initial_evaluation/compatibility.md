**Objetivo**

Tu única función es aplicar 5 reglas de VETO basadas en la naturaleza del rol y su viabilidad.
No analices ajuste profundo.
No uses listas de palabras clave; evalúa la naturaleza semántica del cargo. Los ejemplos entre paréntesis son ilustrativos: orientan, pero se decide por la naturaleza del rol.
Responde siempre en español.

**REGLA DE ORO:** Ante la duda real sobre la naturaleza del rol, NO DESCARTES. Deja pasar.

La REGLA DE ORO aplica a la interpretación semántica del rol (V1, V3) y a V2 cuando la oferta NO da ningún indicio de años ni de nivel. No aplica cuando la oferta trae un dato explícito (años de experiencia, nivel, entregable claro): ese dato se evalúa literalmente. Para los datos de modalidad y ubicación, V4 y V5 se aplican literalmente aunque el dato falte.

La REGLA DE ORO no cubre el caso en que el rol sí es claro pero la oferta usa frases genéricas de negocio (ej. 'alineado a objetivos de negocio', 'impacto en el negocio', 'orientación a resultados'). Esas frases aparecen en casi cualquier rol y no crean ambigüedad.

**Variables**

- {{titulo}}
- {{descripcion_original}}
- {{modalidad}}
- {{ubicacion}}

**V1 Foco Organizacional (prueba del entregable y del beneficiario final)**

Evalúa el propósito del rol y lo que produce día a día, no el vocabulario ni las herramientas que usa.

**Paso 1.** Identifica el entregable principal: qué produce esta persona en su trabajo diario y cuál es la competencia central que la oferta exige para producirlo. Escríbelo en el campo entregable_principal ANTES de decidir V1.

**Paso 2.** Clasifica el entregable:
- **Mecanismo organizacional:** un proceso, un plan, un criterio de priorización, un modelo de gobierno, un control operacional, un rediseño estructural, un sistema de planeación. Es candidato a PASS.
- **Artefacto técnico especializado:** modelos de machine learning, estadísticos o predictivos que se desarrollan, validan o despliegan; algoritmos; software; código; pipelines de datos; infraestructura; plataformas; observabilidad. Es FAIL, aunque el artefacto sirva a una decisión de negocio (ej. Científico de Datos, Data Scientist, ML Engineer, AI Engineer, Risk Modeler, Data Engineer, Analytics Engineer, DevOps).

**Paso 3.** PASS solo si el beneficiario final del rol es el sistema organizacional: diseñar, gobernar, transformar, planear o estabilizar cómo la organización decide, opera o evoluciona, en al menos uno de estos tres ejes:
1. Sistemas operacionales (procesos, cadena de suministro, capacidad, servicio, mejora continua, calidad).
2. Sistemas de decisión e información (planeación, analítica para el negocio, gobierno de datos, criterios de priorización, control operacional).
3. Diseño y transformación organizacional (arquitectura de negocio, rediseño estructural, gobierno operacional, escalabilidad, gestión del cambio sistémico).

**Reglas de aplicación:**
- Que un modelo, un análisis o un dashboard apoye decisiones del negocio no equivale a diseñar el sistema de decisión. El eje 2 solo se cumple si el rol además define o lidera criterios, reglas, mecanismos de priorización o gobierno de decisión.
- Roles mixtos: si la competencia central exigida es programar, modelar o validar modelos (Python avanzado, frameworks de ML, métricas de validación de modelos), es FAIL. Si la competencia central es definir criterios, gobierno o planeación y el modelo o la analítica es solo un insumo, es PASS.
- FAIL si el núcleo del rol es construir, mantener o dar soporte a tuberías de datos, infraestructura, almacenamiento, plataformas u observabilidad, aunque mencione datos, gobierno técnico, nube o analítica.
- FAIL también si el rol es estructuralmente ajeno al diseño de sistemas (ej. ventas puras, marketing, contabilidad financiera, desarrollo de software de producto, soporte técnico, RRHH transaccional).

**V2 Nivel y Alcance (Seniority Real)**

PASS si el rol implica un nivel Senior/Lead/Manager con autonomía de diseño, liderazgo de equipos, o gobierno de sistemas.
FAIL si el rol es de entrada/asistencia (Junior, Trainee, Pasante, Auxiliar).
FAIL si la oferta indica un mínimo de años de experiencia menor a 5 (incluye rangos como 3 a 5 o 4 a 6) Y el rol es de ejecución individual, reporte, modelado o soporte, sin liderazgo de equipos ni diseño estructural explícito en la descripción. Las frases 'autonomía', 'proactividad', 'trabajo multifuncional' o 'trabajar en tribus' no son liderazgo.
Si la oferta no menciona años ni nivel, aplica la REGLA DE ORO y evalúa por el alcance descrito.

**V3 Calidad Mínima**

PASS si la descripción permite identificar responsabilidades o un problema a resolver.
FAIL si es spam, genérica, vacía o incomprensible. Sin descripción o con marca de no reportada → FAIL (excepción a la REGLA DE ORO).

**V4 Claridad de Modalidad**

PASS si la oferta especifica la modalidad (remoto, híbrido, presencial, teletrabajo).
PASS si modalidad no está especificada o es N/R, pero la ubicación esta dentro de Colombia
FAIL si modalidad no está especificada o es N/R, y ubicacion es distinta de Colombia o no está especificada.

**V5 Viabilidad Geográfica y Migratoria (Base: Colombia)**

El candidato reside en Colombia.
PASS si el rol es 100% remoto (permitiendo trabajar desde Colombia para empresas de cualquier país).
PASS si la modalidad es presencial, híbrida o remota dentro de Colombia.
PASS si modalidad no está especificada o es N/R ubicacion está dentro de Colombia.
PASS si la oferta exige trabajar o residir en otro país, PERO la oferta menciona explícitamente patrocinio de visa (visa sponsorship), reubicación (relocation assistance/support) o soporte legal/migratorio para el candidato.
FAIL si la oferta exige trabajar o residir en otro país y no hay mención de patrocinio de visa, reubicación o soporte migratorio.
FAIL si la oferta solo considera candidatos que residan en un lugar fuera de Colombia, sin ofrecer reubicación o patrocinio de visa.

**DECISIÓN**

Si v1, v2, v3, v4 y v5 son PASS -> APROBADA.
Si alguno es FAIL -> DESCARTADA.

**EJEMPLOS DE CALIBRACIÓN (orientan el criterio; no son una lista de cargos)**

**Ejemplo 1.**

**Cargo:** Científico de Datos en una fintech.
**Descripción:** desarrollar modelos de riesgo con machine learning y grafos para el ciclo de crédito, Python avanzado, validación de modelos con KS y AUC, 4 a 6 años de experiencia, híbrido en Medellín.
{"entregable_principal": "Modelos de riesgo de crédito con ML y grafos llevados a producción", "v1": "FAIL", "v2": "FAIL", "v3": "PASS", "v4": "PASS", "v5": "PASS", "decision": "DESCARTADA", "justificacion": "V1: el entregable es un artefacto técnico, 'desarrollar modelos de riesgo robustos' con ML y grafos, y la competencia central es programar y validar modelos. V2: pide '4 a 6 años' como especialista individual, sin liderazgo de equipos ni diseño estructural."}

**Ejemplo 2.**

**Cargo:** Supply Chain Planning Manager.
**Descripción:** liderar un equipo de 6 planeadores, definir el proceso S&OP y los criterios de priorización de abastecimiento, gobernar los KPIs de servicio, 8 años de experiencia, presencial en Bogotá.
{"entregable_principal": "Proceso S&OP y criterios de priorización de abastecimiento con gobierno de KPIs", "v1": "PASS", "v2": "PASS", "v3": "PASS", "v4": "PASS", "v5": "PASS", "decision": "APROBADA", "justificacion": "Eje de sistemas operacionales y de decisión: el rol debe 'definir el proceso S&OP y los criterios de priorización de abastecimiento' y liderar 6 personas. Viable por modalidad presencial en Bogotá, dentro de Colombia."}

**Ejemplo 3.**

**Cargo:** Head of Decision Analytics.
**Descripción:** definir cómo la compañía prioriza inversiones y capacidad, establecer el gobierno de métricas y las reglas de decisión entre áreas, liderar un equipo de analítica que provee los insumos, 10 años de experiencia, remoto desde Colombia.
{"entregable_principal": "Reglas de decisión, gobierno de métricas y priorización de inversión entre áreas", "v1": "PASS", "v2": "PASS", "v3": "PASS", "v4": "PASS", "v5": "PASS", "decision": "APROBADA", "justificacion": "Eje de sistemas de decisión e información: el rol debe 'establecer el gobierno de métricas y las reglas de decisión entre áreas', y la analítica es solo insumo. Lidera equipo con 10 años de experiencia. Viable por modalidad remota desde Colombia."}

**SALIDA**

Devuelve exclusivamente este JSON, sin markdown, sin texto adicional. El primer carácter de tu respuesta debe ser `{`.
La decisión debe ser coherente: APROBADA solo si v1, v2, v3, v4 y v5 son PASS.
El campo entregable_principal va primero, se redacta antes de decidir V1 y debe describir lo que el rol produce día a día. Una sola línea, máximo 20 palabras, sin comillas dobles.
**REGLA CRÍTICA PARA JUSTIFICACIÓN (contenido):** el texto debe explicar ESTA oferta, no una genérica. Redacta según el caso:
- Si APROBADA: nombra el eje del foco organizacional que cumple (sistemas operacionales / sistemas de decisión e información / diseño y transformación organizacional), aporta una evidencia concreta de la descripción (una responsabilidad, requisito o frase del cargo, entre comillas simples) y confirma la viabilidad con el dato de modalidad/ubicación.
- Si DESCARTADA: nombra TODOS los vetos que la descartan (V1–V5) y el dato exacto de la oferta que activa cada uno (la responsabilidad, requisito o frase que lo demuestra).
**PROHIBIDO:** frases que servirían igual para cualquier oferta (ej. 'rol compatible con el perfil'), repetir el título sin analizar, o justificaciones sin evidencia de la descripción.
**FORMATO DE LA JUSTIFICACIÓN:** una sola línea continua, máximo 60 palabras, en español. Prohibido usar comillas dobles ("), saltos de línea, barras invertidas y llaves dentro del valor de "justificacion". Tildes y eñe permitidas.
{
  "entregable_principal": "Qué produce el rol día a día, en una línea",
  "v1": "PASS|FAIL",
  "v2": "PASS|FAIL",
  "v3": "PASS|FAIL",
  "v4": "PASS|FAIL",
  "v5": "PASS|FAIL",
  "decision": "APROBADA|DESCARTADA",
  "justificacion": "Explicación específica de esta oferta con evidencia concreta del texto, en una sola línea"
}

**Version:** v5
