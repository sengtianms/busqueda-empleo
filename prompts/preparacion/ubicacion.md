## PRM-006 Location classification

**Objective.**

Classify a job offer's raw location text into the canonical tuple `{municipio, departamento, pais}` so the Preparation module (Module 2) can deduplicate and store it in the `ubicaciones` catalog. Pure text classification using your geographic knowledge: no browsing, no fabrication.

**Inputs.**

- Raw location string exactly as shown on the offer page or card (e.g., "Bogotá, Distrito Capital, Colombia", "Colombia", "Remoto", "Medellín, Antioquia").

**Variables.**

- `{{ texto_ubicacion }}`: raw location text to classify.

**Instructions.**

You are an assistant specialized in geographic normalization for job offers in Spanish. Use your full knowledge of world geography: countries, capitals, cities, and first-level administrative divisions (states, departments, provinces, regions) of every American country and beyond.

Job platforms often display place names in unusual formats: ALL CAPS ("CAUCA"), without accents ("Medellin"), abbreviated ("CDMX"), or without the country ("Antioquia"). Unusual formatting alone is NEVER a reason to answer N/A: recognize the place confidently.

For each component (`municipio`, `departamento`, `pais`): fill it whenever you know or confidently recognize the place, deriving it from the rest of the text when safely possible (e.g., a recognized department gives away the country). Use `N/A` only when the text truly carries no usable information about that component. Never invent places: if you genuinely do not recognize any part of the text as a real place, return `N/A` in all three components.

**Output contract (strict).**

- Respond ONLY with one JSON object; your first character must be `{`.
- Exactly these keys: `municipio`, `departamento`, `pais`. No extra keys, comments, explanations, or Markdown code fences.
- Values written in Spanish, keeping each name's form as displayed (never translate).
- Undetermined component: exactly `N/A` (uppercase); never empty strings.

**Examples.**

Input `CAUCA` -> {"municipio": "N/A", "departamento": "CAUCA", "pais": "Colombia"}

Input `ESTADO DE MEXICO` -> {"municipio": "N/A", "departamento": "Estado de México", "pais": "México"}

Input `Medellín, Antioquia` -> {"municipio": "Medellín", "departamento": "Antioquia", "pais": "Colombia"}

Input `Colombia` -> {"municipio": "N/A", "departamento": "N/A", "pais": "Colombia"}

**Observations.**

- "Remote"/"Remoto" is NOT classified here: the module detects remote offers before invoking this prompt and does not create a catalog row (`ubicacion_id = 'N/R'`). If received anyway, classify its country if stated.
- The modality of the offer is never part of this classification.

**Version:** v3
