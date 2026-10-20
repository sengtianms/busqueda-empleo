# MVP Execution Plan — Job Search Automation
Working document: exact MVP build order, step by step, based on approved documents (DOC-00 to DOC-13, Annexes 5A, 5B, 5C, 9A).

> **Scope note (decision D55, 2026-10-19):** Version 1 ships Phases 0–6 only — Modules 1–3 plus the transversal orchestrator and the scheduled automation (decision D54). Phases 7–8 are deferred to future versions, and Phase 9 is adapted: the orchestrator entry point (`python -m modules.orchestrator`) replaces the five-module `run_mvp.py`, and its end-to-end verification is the V1 battery.

## Phase 0. Startup Preparation
- Confirm MVP scope against DOC-01, DOC-08, DOC-09 (LinkedIn only source).
- Work rules: one task at a time; no advancing without approval.
- Acceptance criteria per step: code written, passes lint+typecheck+tests, reviewed and approved.
- Testing strategy:
  - Unit (pytest): business logic/rules/transformations; fixtures in `tests/fixtures/`.
  - Integration: Playwright + real selectors (tagged `integration`).
  - LLM: prompts tested with local Ollama; mockable responses in unit tests.
  - Data layer: temporary `.db` files (SQLite).

## Phase 1. Common System Foundation (Infrastructure)
**Completed**
- Directory structure per DOC-07 (full root: `docs/`, `config/`, `modules/`, `shared/`, `data/`, `logs/`, `temp/`, `scripts/`, `tests/`, `prompts/`); migrated `Initial Documentation/` to `docs/`; `.gitkeep` in empty dirs.
- 1.2a Version control: `git init`, `.gitignore`, `.gitkeep` verification, first commit (base structure + migrated docs), GitHub remote published.

**Pending (execution order)**
1. venv + `requirements.txt` — init `venv`, full stack (DOC-11), install deps, `playwright install chromium`. Validate: correct venv, pip from venv, all packages installed, playwright install clean.
2. `config.yaml` + `.env.template` — functional parameters in `config/config.yaml` + `config/.env.template`.
3. `pyproject.toml` — configure Black, Ruff, mypy.
4. `shared/config.py` — unified loading of `config.yaml` + `.env`.
5. `shared/errors.py` — exception hierarchy by category (ER-RED, ER-NAV, ER-LLM, etc., DOC-06); attributes: code, severity (SV-1..SV-5), source_module, offer_id, timestamp.
6. `shared/logging_setup.py` — Loguru: standard format, rotation, `logs/` directory.
7. `shared/retry.py` — Tenacity wrapper, policies per DOC-06.
8. `shared/models.py` — Pydantic v2: `Offer`, `Evaluation`, `Result`, `Company`, etc. (DOC-13); sequential string IDs, ISO 8601 `fecha_creacion`/`fecha_ultima_edicion`.
9. `shared/persistence.py` — SQLite via sqlite3: read, write, update, find by ID, generate sequential IDs; path from config.
10. `tests/conftest.py` + `tests/fixtures/` — basic fixtures (test config, mock logger, temp persistence); `.gitkeep` in fixtures dir.

**Final validation**
- `ruff check .` no errors
- `mypy .` no errors
- `python -c "import shared.config, shared.errors, shared.logging_setup, shared.retry, shared.models, shared.persistence"` all importable
- `pytest tests/` all pass

## Phase 2. Shared Services (Cross-cutting Layer)
**Optimized Execution Order**
Phase 3 (prompts) can begin immediately after Task 2 (`ia_service.py`). Tasks 3–6 do not block Phase 3.

| Order | Task | Depends on | Blocks Phase 3? |
|---|---|---|---|
| 1 | Add `Profile` model to `shared/models.py` + `profile` section in `config.yaml` | Nothing | No |
| 2 | `shared/ia_service.py` (Ollama + prompt loader) | Task 1 (weak) | Yes |
| 3 | `shared/decision_engine.py` (rules + scoring) | Task 1 (strong) | No |
| 4 | `shared/state_machine.py` (states + transitions) | Nothing (independent) | No |
| 5 | Unit tests (ia_service, decision_engine, persistence, state_machine) | Tasks 2-4 | No |
| 6 | Final validation (ruff → mypy → pytest) | Task 5 | No |

### Task 1 — `Profile` model + config section
Files: modify `shared/models.py` and `config/config.yaml`.
Objective: Pydantic `Profile` model representing user's professional profile, required for decision engine; values loaded from new `profile` section in `config.yaml`.

`Profile` model (add to `shared/models.py`):
```python
class Profile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tecnologias: dict[str, int] = Field(default_factory=dict)
    anos_experiencia: int = 0
    idiomas: dict[str, str] = Field(default_factory=dict)
    ubicaciones_preferidas: list[str] = Field(default_factory=list)
    modalidades_preferidas: list[str] = Field(default_factory=list)
    salario_minimo: float | None = None
    seniority: str = ""
    empresas_objetivo: list[str] = Field(default_factory=list)
    empresas_excluidas: list[str] = Field(default_factory=list)
    educacion_nivel: str = ""
```

`profile` section (add to `config/config.yaml`):
```yaml
profile:
  tecnologias: {}
  anos_experiencia: 0
  seniority: ""
  idiomas: {}
  ubicaciones_preferidas: []
  modalidades_preferidas: []
  salario_minimo: null
  empresas_objetivo: []
  empresas_excluidas: []
  educacion_nivel: ""
```
Rationale: Based on DOC-10 (technologies, experience, languages, job preferences) and criteria CE-001 through CE-012 from DOC-03. `Profile` is a value model (not persistent entity), consistent with DOC-13/13A.

### Task 2 — `shared/ia_service.py`
File: `shared/ia_service.py`
Objective: AI service with multi-provider support (SRV-002 per DOC-12), routing requests to local or cloud models depending on purpose.

| Component | Description |
|---|---|
| `load_prompt(prompt_id: str) -> str` | Load `prompts/{category}/{prompt_id}.md`; `ConfigError` if missing |
| `render_prompt(template: str, context: dict) -> str` | Replace `{{ variable }}` with context values |
| `_route_provider(purpose: str) -> str` | Determine provider from `config.yaml` → `ai_routing` |
| `_send_local(prompt: str) -> str` | httpx POST to local Ollama (`http://{host}:{port}/api/generate`) |
| `_send_cloud(prompt: str) -> str` | httpx POST to Ollama Cloud with API Key and endpoint from config |
| `_validate_response(raw_response: str) -> dict` | JSON parsing, minimum expected structure validation |
| `analyze(prompt_id: str, context: dict, purpose: str = "evaluation") -> dict` | Orchestrate: load → render → route → send → validate → return dict |

Error handling: `LLMError` with codes ER-LLM-001 (connection), ER-LLM-002 (timeout), ER-LLM-003 (invalid response), ER-LLM-004 (unexpected format).
Retries: `retry_decorator` from `shared/retry.py` with policy from `config.yaml` → `retries` (global block).
Routing: `config.yaml` → `ai_routing`. Official default (decision 2026-07-30): evaluation → cloud, processing → cloud; local available as fallback.
Prompt loader: searches `prompts/{category}/{prompt_id}.md`; supports subdirectories; each interaction logged with Loguru.

### Task 3 — `shared/decision_engine.py`
File: `shared/decision_engine.py`
Objective: Rule-based evaluation engine (SRV-001 per DOC-12).

| Component | Description |
|---|---|
| `load_profile() -> Profile` | Build `Profile` from `profile` section of `config.yaml` |
| `evaluate(offer: ProcessedOffer, profile: Profile) -> Evaluation` | Evaluate offer vs profile compatibility using weighted criteria |
| `_calculate_score(offer, profile, weights) -> float` | Calculate 0-100 score applying configured weights |
| `_classify(score: float) -> EvaluationResult` | Thresholds from config: ≥80 → HIGH, ≥50 → MEDIUM, <50 → LOW |
| `_decide(result: EvaluationResult) -> EvaluationDecision` | HIGH/MEDIUM → CONTINUE, LOW → DISCARD |
| `_justify(offer, profile, partial_scores) -> str` | Generate text with score breakdown |

Evaluated criteria (weights from `config.yaml` → `evaluation.weights`):

| Criterion | Configurable weight | Matching |
|---|---|---|
| Experience | 0.30 | `profile.anos_experiencia` vs offer |
| Technology | 0.25 | RapidFuzz between `profile.tecnologias` and `offer.tecnologias` |
| Location | 0.15 | RapidFuzz between `profile.ubicaciones_preferidas` and offer |
| Modality | 0.10 | Exact match against `profile.modalidades_preferidas` |
| Languages | 0.10 | Level match between `profile.idiomas` and `offer.idiomas` |
| Seniority | 0.10 | Match between `profile.seniority` and offer |

Business rules:
- Companies in `profile.empresas_excluidas` → automatic discard (score = 0).
- `profile.salario_minimo` not met → penalized score.
- Justification includes per-criterion breakdown.

### Task 4 — `shared/state_machine.py`
File: `shared/state_machine.py`
Objective: State machine for offer lifecycle (official EST catalog, DOC-01 §13: EST-001 to EST-007).

| Component | Description |
|---|---|
| `VALID_TRANSITIONS: dict[OfferState, list[OfferState]]` | Map of allowed transitions |
| `transition(current_state: OfferState, target_state: OfferState) -> OfferState` | Validate and execute transition; `InternalError` (ER-INT-010) if invalid |
| `possible_transitions(state: OfferState) -> list[OfferState]` | Return valid destinations from a state |

Defined transitions:
- DISCOVERED → PREPARED
- PREPARED → EVALUATED
- EVALUATED → ACCEPTED | DISCARDED
- ACCEPTED → PROCESSED
- DISCARDED → FINALIZED
- PROCESSED → FINALIZED

Validations: transition matrix per DOC-01 §13 — only defined transitions, no skipping stages, no going back.

### Task 5 — Unit tests
| File | Content |
|---|---|
| `tests/test_ia_service.py` | Tests with httpx mock (simulated Ollama response), prompt loading, error if prompt missing |
| `tests/test_decision_engine.py` | Tests with `example_processed_offer` fixture + new `example_profile`; verify scores and classifications (fixture retired in Lote 1 cleanup 2026-08-12 — tests build models inline; criterion met at the time) |
| `tests/test_persistence.py` | CRUD tests with `temp_db_file`: generate_id, read_table, write_row, find_by_id, update |
| `tests/test_state_machine.py` | Tests for valid and invalid transitions |

Additional fixture in `conftest.py`: `example_profile() -> Profile`

### Task 6 — Final validation
- `ruff check .`
- `mypy .`
- `pytest tests/ -v`
Criteria: 0 ruff errors, 0 mypy errors, all tests green.

## Phase 3. Initial Prompts
- Create `prompts/initial_evaluation/` — analyze offer/profile compatibility.
- Create `prompts/processing/` — strategic extraction + input generation.
- Each prompt: file with identifier (PRM-XXX), instructions section, `{{ }}` variables, expected output format.
- Test each prompt manually with Ollama + real offer; adjust and approve version 1.

## Phase 4. Module 1 — Opportunity Discovery
Build strategy: functional sub-phases grouping nodes by testable unit, per canonical spec in `docs/diagrams/Ficha técnica - Diagrama de flujo (Descubrimiento de oportunidades).md` (technical sheet + flow diagram = authoritative source). Each sub-phase has full work cycle (analysis → plan → implementation → validation → close, per AGENTS.md) and approval before next. Six decision nodes act as contract validators of immediate predecessor (five after D17 retired the "¿Quedan ofertas por capturar…?" decision in Lote 4 — see as-built notes in the ficha and decision log v1.6). Nodes implemented in flow order; decision nodes grouped with preceding process node (pure in-memory evaluations requiring contract input).

| Sub-phase | Nodes included | Type |
|---|---|---|
| 4.1 — Startup and source control | INICIO (v1.3) + ¿Existe al menos una fuente configurada? (v1.0) + ¿Quedan fuentes por procesar? (v1.0) + Seleccionar la siguiente fuente pendiente (v1.0) | 1 process + 2 decisions + 1 process |
| 4.2 — Platform entry | Entrar a la fuente seleccionada (v1.1) + ¿El ingreso fue exitoso? (v1.0) | 1 process + 1 decision |
| 4.3 — Filter search | Aplicar los filtros básicos (v1.1) + ¿Se encontraron ofertas? (v1.1) | 1 process + 1 decision |
| 4.4 — Capture and registration | Capturar ofertas (v1.0) + Registrar ofertas en "Ofertas Totales" (v1.0) + ¿Quedan ofertas por capturar? (v1.0) + ¿Quedan sets de filtros por aplicar? (v1.0) | 2 processes + 2 decisions |
| 4.5 — Closure and orchestrator | Finalizar Proceso (spec draft) + orquestador del flujo completo (conectar todos los nodos) | 1 terminal + 1 integration |

> **As-built 2026-08-12 (D17, Lote 4):** el nodo "¿Quedan ofertas por capturar? (v1.0)" se retiró del flujo (decisión constante desde la captura por listado D11); la fila 4.4 queda como 2 processes + 1 decision y el flujo total tiene 12 nodos (5 decisiones). Las versiones de la tabla (v1.0/v1.1) son las originales de construcción; las vigentes están en la ficha técnica (as-built).

## Phase 5. Module 2 — Offer Preparation + Transversal Orchestrator
Build strategy: functional sub-phases grouping nodes by testable unit, per canonical specs in `docs/diagrams/Ficha técnica - Diagrama de flujo (Preparación de ofertas).md` and `docs/diagrams/Ficha técnica - Diagrama de flujo (Orquestador transversal).md` (technical sheets = authoritative construction bases; macro decisions D33/D34, decision log v1.19). Each sub-phase has full work cycle (analysis → plan → implementation → validation → close, per AGENTS.md) and approval before next. Nodes implemented in flow order; decision nodes grouped with preceding process node (the candidate decision is a pure in-memory evaluation; the loop decision — the module's only decision with I/O per its ficha RN-05 — is grouped by flow cohesion). Difference vs Phase 4: the 11 consolidated schema/shared dependencies (ficha M2, "Dependencias de esquema") go first as their own sub-phase — D33 consolidated them to apply coherently (one idempotent migration set) instead of interleaving migrations across node tasks.

| Sub-phase | Content included | Type |
|---|---|---|
| 5.1 — Foundations: schema, models, config, prompt | The 11 consolidated dependencies: idempotent migrations (`duplicada` in `estado` CHECK, `id_duplicidad`, `ubicacion_nombre`+`modalidad` columns, `total_preparadas`/`total_duplicadas` on `corridas`, `eventos.id_oferta` re-added, `ubicaciones` restructured to `(ciudad, region, pais)`); models (`OfferState.DUPLICADA`, `EstadoCorrida.SIN_PENDIENTES`, `Corrida`/`EventoAlmacen` extended, `Location` without `modalidad`); state-machine transition `preparada → duplicada`; `normalizar_texto` utility; config section `preparacion:` (default `profundidad_catalogo_empresa: 0`) + `ai_routing.preparacion`; location-classification prompt `prompts/preparacion/ubicacion.md` manually tested against the routed model before integration. Live DB migration via the idempotent migrations in `init_db()`; backup decided case-by-case at sub-phase start (project precedent D31/D32) | Schema + shared foundations |
| 5.2 — Startup and candidate decision | INICIO (module own run, execution context, shared global lock, FIFO candidate load, `hubo_candidatas`) + ¿Quedan ofertas por preparar en esta corrida? (`sin_pendientes` controlled termination) | 1 process + 1 decision |
| 5.3 — Offer preparation | Preparación de ofertas: guest httpx session with browser fallback, page capture `/jobs/view/N`, company upsert (no AI), location classification with AI + caches, offer update, per-offer events with `id_oferta`, two lots per pass (H1), configurable pauses/session lifetime/retries | 1 process |
| 5.4 — Duplicate verification and loop decision | Verificación de duplicidad (two-stage RapidFuzz: exact index O(1) + fuzzy with thresholds, marker `fecha_ultima_verificacion`, event `oferta_duplicada`) + ¿Quedan ofertas en 'descubierta'? (loop with `max_pasadas`, event `revision_pendientes`) | 1 process + 1 decision |
| 5.5 — Closure and module orchestrator | Finalizar Proceso (metrics by events, official motive/state table incl. `sin_pendientes`, lock release conditional to ownership, best-effort resource close, decoupled company enrichment as step 6 gated by `profundidad_catalogo_empresa`) + module flow orchestrator (`ejecutar_flujo`, connects all 6 nodes) | 1 terminal + 1 integration |
| 5.6 — Transversal orchestrator | `modules/orchestrator/`: scheduled-run node `ejecutar_corrida_programada()` (dedicated row in `corridas`, module result derived from the DB via `leer_ultima_corrida_cerrada`, module failure does not stop the run), declarative module registry, config section `orquestador:`, integration tests — built at Module 2 closure per its own ficha | 1 transversal node |
| 5.7 — Real sequential run 1→2 and documentation closure | Production run validating M1→M2 chained through BD coordination + summary events (`modulo_ejecutado` × N, `corrida_programada`); as-built notes on deviations, database-tables writers per module, README, AGENTS.md status/test count; code-reviewer + docs-reviewer | E2E verification + doc closure |

## Phase 6. Module 3 — Initial Evaluation

> Build strategy (as Phases 4–5): functional sub-phases grouping nodes by testable unit, per canonical spec in `docs/diagrams/Ficha técnica - Diagrama de flujo (Evaluación inicial de ofertas).md` (technical sheet = authoritative construction base; decision D48). Pre-build gate: `docs/history/tracker.md` "Previo Fase 6" (5 points). Legacy scoring (`evaluation.weights`, `decision_engine.py` High/Medium/Low, "optional LLM") is retired by this design — evaluation is 5 veto controls by the routed AI (prompt `compatibility.md` v5 since D52 with deliverable-first V1 and persisted `entregable_principal`; v5 keeps D51's evidence-backed justification and 60-word cap, and discards must name every triggering veto), no score.

| Sub-phase | Content | Nodes |
|---|---|---|
| 6.1 — Startup and candidate decision | INICIO (module own run, execution context, full `evaluacion:` validation, shared global lock M1/M2/M3, FIFO `preparada` load, `hubo_candidatas`, no AI probe) + ¿Hay ofertas por procesar? (`sin_pendientes` controlled termination) | 1 process + 1 decision |
| 6.2 — Initial evaluation | Evaluación inicial: batch (evaluate all, then close), 4 fields as-is, 5 vetoes via routed AI + ordered alternate doors (one attempt per door with immediate rotation and run-scoped door memory; 2 attempts only for invalid answers — D59), immediate per-offer persistence (`aceptada_ei`/`descartada_ei` via `evaluada` + `resultado_evaluacion_inicial` with `entregable_principal` + event with `id_oferta`), V3-FAIL empty-description exception, persistent failure → pending in `preparada`, quota exhaustion → orderly close | 1 process |
| 6.3 — Closure and module orchestrator | Finalizar Proceso (metrics by events with DISTINCT `id_oferta`, official motive/state table incl. `sin_pendientes`/`corrida_completada`/`cupo_agotado`, best-effort close, ownership-safe lock release) + module flow orchestrator (`ejecutar_flujo`, mirror of Preparation) | 1 terminal + 1 integration |
| 6.4 — Solo real run, transversal third, doc closure | Solo real verification run of the module; on pass, transversal joins third after Preparation (`orquestador.modulos`, result read from DB as the others); physical migrations (`resultado_evaluacion_inicial`, `total_aprobadas`/`total_descartadas`, states) land with the build; legacy scoring keys + old engine retired; as-built notes, database-tables writers per module, README, AGENTS.md status/test count; code-reviewer + docs-reviewer | E2E verification + doc closure |

## Phase 7. Module 4 — Deep Processing (deferred to post-V1 versions — decision D55)
- Create `modules/processing/`.
- Load accepted offers from evaluation.
- Invoke LLM with `prompts/processing/`: vacancy diagnosis; strategic extraction (key requirements, culture, differentiators); application design (strengths to highlight, gaps to mitigate); input generation (draft cover letter, interview prep).
- Validate result consistency (Pydantic).
- Save products in persistence + `data/output/`; log full history.
- Error handling: ER-LLM, ER-INT.
- Tests: real prompts + real offer → inspect quality; mock responses → validate parsing/structures.

## Phase 8. Module 5 — Results Management (deferred to post-V1 versions — decision D55)
- Create `modules/management/`.
- Implement: full per-offer history, state management, tracking.
- Reports: offer summary (processed, discarded, pending); export to compatible format (`data/output/`).
- Validate complete traceability (each decision → justification → log).
- Error handling: ER-DB, ER-DAT.
- Tests: unit (queries, filters, export); integration (real data → generated report).

## Phase 9. MVP Integration (adapted to the V1 scope — decision D55)

> Adapted for V1: the orchestrator entry point already chains the three active modules and D54's timer fires it automatically; `run_mvp.py` is superseded. Remaining V1 content: the real verification battery (2026-10-19 scheduled run COR-0006→0009) and final approval.
- Create `scripts/run_mvp.py` — orchestrator running all 5 phases in sequence.
- Test full end-to-end flow with small set of real offers.
- Verify: logs, errors, states, persistence, generated files.
- Fix broken dependencies and adjust sequence.
- Run pytest regression (lint → typecheck → tests).
- Review coverage: any DOC-01 functionality unimplemented? any inconsistent documentation?
- Final MVP approval.

## Validation Criteria per Step
Each numbered step completes when:
- Code written and placed per DOC-07.
- `ruff check .` passes with no errors.
- `mypy .` passes with no errors.
- `pytest tests/` passes (relevant tests exist and green).
- Result reviewed and approved before next step.

## References
| Document | Purpose |
|---|---|
| DOC-01 | Functional requirements |
| DOC-03 | Decision model |
| DOC-04 | Data flow |
| DOC-05 | Project standards |
| DOC-06 | Error handling |
| DOC-07 | Folder architecture |
| DOC-08 | Scope and objectives |
| DOC-09 | Source research (LinkedIn) |
| DOC-11 | Technology stack |
| DOC-12 | General system architecture |
| DOC-13 | Data model |
| Annex 5A | Prefix catalog |
| Annex 5B | Official technical standards |
| Annex 9A | LinkedIn strategic decisions |
