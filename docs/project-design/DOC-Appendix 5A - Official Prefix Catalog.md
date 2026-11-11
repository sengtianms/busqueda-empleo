# Appendix 5A – Official Prefix Catalog

Sole official reference for assigning, administering, and interpreting all prefixes in the job search automation project. No project document may define prefixes different from or incompatible with this catalog.

## A.1 Principles and administration

1. Each prefix is unique project-wide and represents a single concept.
2. No prefix may be reassigned to a different category.
3. Prefixes are stable for the entire project lifecycle.
4. Any incorporation, modification, or deletion requires prior update of this catalog and documented justification.

## A.2 Document prefixes

| Prefix | Document |
|--------|----------|
| DOC-00 | Project Glossary |
| DOC-01 | Functional Requirements |
| DOC-02 | Non-Functional Requirements |
| DOC-03 | Decision Model |
| DOC-04 | Data Flow |
| DOC-05 | Project Standards |

## A.3 Chapter prefixes

| Prefix | Meaning |
|--------|---------|
| PEP | Principles of project standards |
| CEG | General conventions |
| CNP | Naming conventions |
| CID | Identifier conventions |
| CED | State conventions |
| CFH | Date and time conventions |
| CFDT | Data format conventions |
| CJS | JSON structure conventions |
| CDO | Documentation conventions |
| CPR | Prompt conventions |
| CNA | File and document naming conventions |
| COC | Folder organization conventions |
| CVE | Versioning conventions |
| CLR | Log conventions |
| CAT | Audit and traceability conventions |
| CEM | Entity and data model conventions |
| CMC | Module and component conventions |
| CCS | System configuration conventions |
| RES | Standard restrictions |
| CAE | Acceptance criteria |

## A.4 Requirement prefixes

| Prefix | Meaning |
|--------|---------|
| RF | Functional Requirement |
| RNF | Non-Functional Requirement |

## A.5 Decision prefixes

| Prefix | Meaning |
|--------|---------|
| MD | Decision Model Rule |

## A.6 Data flow prefixes

| Prefix | Meaning |
|--------|---------|
| FD | Data Flow Rule |

## A.7 Process prefixes

| Prefix | Meaning |
|--------|---------|
| PRC | Process |
| ETP | Stage |
| SUB | Subprocess |

## A.8 Module prefixes

| Prefix | Meaning |
|--------|---------|
| MOD | Module |
| CMP | Component |
| SRV | Service |
| INT | Integration |

## A.9 Entity prefixes

| Prefix | Meaning |
|--------|---------|
| ENT | Entity |
| ATR | Attribute |
| REL | Relation |

## A.9b Persistent data ID prefixes

| Prefix | SQLite Table | Meaning |
|--------|-------------|---------|
| FNT | — (retired) | Job source — **retired** (D31, 2026-08-18): the `fuentes` table was dropped from the physical model; sources are config-driven via `config.yaml`; the FNT- prefix is no longer generated. |
| EMP | companies | Employer company (populated by Module 2, Nodo 2 — D33) |
| UBI | locations | Geographic location (populated by Module 2, Nodo 2 — D33; tuple dedup; no `modalidad` column) |
| OFE | ofertas_descubiertas | Raw job offer (Module 1 capture + Module 2 enrichment) |
| OFP | processed_offers | Processed and cleaned offer |
| EVL | evaluations | Compatibility evaluation |
| RSP | processing_results | Deep processing result |
| COR | corridas | Run of a module (Discovery — Module 1, Preparation — Module 2) or of the scheduled run (transversal orchestrator — D34) |
| SES | sesiones | Platform session of the Discovery module (Module 1) |
| EVT | eventos | Event (error or success) of any module or the transversal orchestrator |
| BLO | bloqueo | Concurrency lock record (single active run across the whole pipeline — D33) |
| LT | listas_busquedas | Search-list identity per config position (D71): `LT-0001..LT-0009` = `indice_set` 0..8; `texto` is the full keywords phrase. Deliberately NOT in `secuencia_ids` — the id derives from the config order, never from a counter. |
| DUP | duplicados_descubiertas | Duplicate encounter of the Discovery dedup (D71): one row per silent `id_externo` re-meet, with the encounter list, the origin list of the original row (unknown only for pre-D71 offers) and the run/link/timestamp. |

## A.10 Configuration prefixes

| Prefix | Meaning |
|--------|---------|
| CFG | Configuration |
| ENV | Environment variable |
| PAR | Parameter |

## A.11 Log prefixes

| Prefix | Meaning |
|--------|---------|
| LOG | Operational log |
| EVT | Event |
| ERR | Error |
| WRN | Warning |
| INF | Information |

## A.12 Prompt prefixes

| Prefix | Meaning |
|--------|---------|
| PRM | Prompt |
| SYS | System instruction |
| TMP | Prompt template |

## A.13 File prefixes

| Prefix | Meaning |
|--------|---------|
| DOC | Document |
| IMG | Image |
| CFG | Configuration |
| DB | Database |
| JSON | JSON file |
| LOG | Log file |
