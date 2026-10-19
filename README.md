# Job Search Automation

Automated system for discovery, evaluation, and processing of job opportunities, with LinkedIn as the primary source.

## Documentation

All official documentation is located in `docs/`:

| Document | Purpose |
|----------|---------|
| [Ficha técnica — Descubrimiento (M1)](docs/diagrams/Ficha%20técnica%20-%20Diagrama%20de%20flujo%20(Descubrimiento%20de%20oportunidades).md) | Module 1 (Opportunity Discovery) — node-level spec, as-built (D22, D25, D28, D29, D30, D31, D32). |
| [Ficha técnica — Preparación de ofertas (M2)](docs/diagrams/Ficha%20técnica%20-%20Diagrama%20de%20flujo%20(Preparación%20de%20ofertas).md) | Module 2 (Offer Preparation, Phase 5) — node-level spec, authoritative construction base (D33, 2026-08-20). |
| [Ficha técnica — Orquestador transversal](docs/diagrams/Ficha%20técnica%20-%20Diagrama%20de%20flujo%20(Orquestador%20transversal).md) | Transversal orchestrator (modules 1 → 2) — authoritative construction base (D34, 2026-08-20). |
| [DOC-13A](docs/project-design/Document%2013A%20-%20Detailed%20Data%20Model%20Design.md) | Detailed data model (entities, attributes, catalogs, ERD) — v1.19. |
| [Appendix 5A](docs/project-design/DOC-Appendix%205A%20-%20Official%20Prefix%20Catalog.md) | Official prefix catalog (IDs, codes) — FNT retired (D31); module scope generalized (D33/D34). |
| [Decision log](docs/history/decision%20log.md) | Approved decisions and deviations — D1 through D52. |
| [MVP Execution Plan](docs/plans/MVP%20Execution%20Plan.md) | Build order and acceptance criteria |
| [tracker.md](docs/history/tracker.md) | Current status of each phase and task |
| [Database tables](docs/reports/database-tables.md) | As-built reference of `job_search.db` (tables, columns, writers) |
| [Adding a new source](docs/adding-a-new-source.md) | Step-by-step guide to integrate a new platform (config, adapter, registry, tests) |
| [Plan funcional fase 5](docs/plans/Plan%20funcional%20fase%205.md) | Phase 5 functional plan — Module 2 + transversal orchestrator (decisions, gaps, optimizations). |

## Status

Phases 0–6 complete: Module 1 (Opportunity Discovery), Module 2 (Offer Preparation), Module 3 (Initial Evaluation) and the transversal orchestrator are implemented, tested (624 tests) and running in production use — the pipeline discovers, prepares and evaluates offers end-to-end (latest full run: 65 offers → 65 prepared + 4 duplicates → 14 approved + 47 discarded, 0 errors; the v5 prompt with evidence-backed justifications and persisted main deliverable applies to subsequent runs). Phases 7–9 (Processing, Management, MVP integration) pending.

## Running the pipeline

Prerequisites: Python virtual environment at `.venv/`, the Ollama desktop app running locally (models `gemma4:31b-cloud` and `gpt-oss:120b-cloud` available through its proxy), and LinkedIn credentials in `.env` (see `config/.env.template`).

```bash
# 1. Preflight check: config, database writability, lock state, local model
.venv/bin/python scripts/preflight.py --ia

# 2. Full scheduled run (discovery -> preparation)
.venv/bin/python -m modules.orchestrator

# 3. Diagnose any past run (stages, offers by state, errors, catalogs)
.venv/bin/python scripts/reporte_corrida.py
```

Notes:
- `preflight.py --db` expects an explicit database path as an argument; omit it to check the default `data/job_search.db`.
- Logs default to INFO; set `LOG_LEVEL=DEBUG` in `.env` for verbose output.
- All persistent data lives in `data/job_search.db`; backups are stored under `data/backup/`.

## LinkedIn session (persistent login)

Module 1 keeps its LinkedIn session in `data/browser_profile/` (set via `browser.profile_path` in `config/config.yaml`, a folder owned by the system — never your personal browser profile). Log in once manually in the visible window (up to 5 minutes, including any verification LinkedIn asks for); later runs reuse the session and enter directly. Module 2 always works as a guest and never uses this session.

**Reverting to fully automatic login:** empty `browser.profile_path` in `config/config.yaml` (leave it as `""`). Effect: entry goes back to the ephemeral mode (throwaway window per run), typing the `.env` credentials and waiting ~30 s for the main page; if LinkedIn asks for extra verification, the run ends with `criterio_no_cumplido`/`autenticacion_rechazada` instead of waiting. The `data/browser_profile/` folder can be deleted (it is git-ignored). No migrations or code changes needed.

## Technology Stack

Python 3.12, Playwright, BeautifulSoup4, Pydantic v2, Loguru, RapidFuzz, Tenacity, httpx, SQLite, Ollama (Gemma 4 31B cloud for evaluation/processing routes; GPT-OSS 120B cloud for location classification).
