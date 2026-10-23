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

Version 1 is complete (decisions D54–D56, 2026-10-19): Phases 0–6 — Module 1 (Opportunity Discovery), Module 2 (Offer Preparation), Module 3 (Initial Evaluation) and the transversal orchestrator — run the full loop end-to-end, both manually and automatically: a system timer fires a complete run 10 minutes after the computer powers on and repeats it every 3 hours while the machine is on (decision D54); first scheduled run: discovery → preparation (47 prepared + 1 duplicate) → evaluation → 7 approved / 39 justified discards, 0 chain errors. Phases 7–8 (deep processing, results management) are deferred to future versions (D55). Post-V1 hardening closed 2026-10-22 (decisions D60–D64): the search matrix runs a single Colombia sweep, live progress is visible from any terminal (`scripts/estado_corrida.py`), manual runs narrate themselves, a minute-level watchdog alerts on stalled batches and closes dead runs (D60–D63), and four operator commands manage the cycle by hand — pause, resume, stop-now and zero-wipe (D64). 744 tests; the post-reset scheduled-tanda verification is pending (tracker).

## Running the pipeline

Prerequisites: Python virtual environment at `.venv/`, the Ollama desktop app running locally (models `gemma4:31b-cloud` and `gpt-oss:120b-cloud` available through its proxy), and LinkedIn credentials in `.env` (see `config/.env.template`).

```bash
# 1. Preflight check: config, database writability, lock state, local model
.venv/bin/python scripts/preflight.py --ia

# 2. Full run (discovery -> preparation -> evaluation; manual runs narrate)
.venv/bin/python -m modules.orchestrator

# 3. Watch the current/latest batch live from any terminal
.venv/bin/python scripts/estado_corrida.py

# 4. Diagnose any past run (stages, offers by state, errors, catalogs)
.venv/bin/python scripts/reporte_corrida.py
```

Notes:
- `preflight.py --db` expects an explicit database path as an argument; omit it to check the default `data/job_search.db`.
- Logs default to INFO; set `LOG_LEVEL=DEBUG` in `.env` for verbose output.
- All persistent data lives in `data/job_search.db`; backups are stored under `data/backup/`.

## Scheduled automation

A user-level system timer fires the full pipeline automatically (decision D54): first run 10 minutes after the computer powers on, then every 3 hours counted from each run, stopping at shutdown. No fixed times — the day's drag run recovers overnight postings because the capture window is the last 24 hours and repeats are resolved by the dedup rules.

Every batch reports its verdict to the desktop (decision D57): a notification with the true counts on success, the failing module + motive on failure, and a benign "another run was in progress" notice on skip — all read from the official trace, and every verdict also lands in the batch's journal line, so nothing is lost if the machine was unattended.

```bash
# Install and activate (installing past the 10-min mark fires the drag run immediately)
bash scripts/instalar_programador.sh

# Next automated run / log of the automated runs
systemctl --user list-timers busqueda-empleo.timer
journalctl --user -u busqueda-empleo.service -b

# Remove the scheduler (manual runs remain available)
bash scripts/instalar_programador.sh --desinstalar
```

Notes:
- A scheduled run is skipped cleanly if another one is still in progress (the global lock resolves manual/automatic collisions); a failing preflight aborts the run leaving evidence in the journal; a stalled run is killed at 45 minutes so the next scheduled run stays healthy.
- Each tanda reuses the persistent LinkedIn session; if the account challenges (verification/new login), the tanda ends gracefully and the next manual run re-enables everything from the visible window.
- A minute-level watchdog (decisions D63): if the batch freezes without signals with a fresh chair it alerts desktop-side once per offense — "examínela" — without touching anything; runs whose processes provably died (own silence past the threshold, expired chair) are closed as `abortada: proceso desaparecido` with the official termination evidence; if the batch unit itself dies without its own verdict notification, an `OnFailure` desktop alert fires (deduplicated against the batch's own verdict in the journal). All of it is installed/removed together with the scheduler above.
- While a batch runs, any terminal can watch it live: `.venv/bin/python scripts/estado_corrida.py` (read-only).
- Four one-line commands manage the scheduled cycle by hand (decision D64), all idempotent, each with a desktop confirmation and a journal line:

```bash
# Pause upcoming automatic batches: the clock turns off (nothing fires, not even
# after a reboot) until resumed; a batch already running finishes normally
bash scripts/pausar_tandas.sh

# Resume the automatic cadence: re-arms the clock, reports the next firing,
# and repairs the watchdog system if anything went loose
bash scripts/reanudar_tandas.sh

# Stop the batch running right now (scheduled or manual) and close it at once
# as: aborted · vanished process · operator order
bash scripts/detener_tanda.sh

# Zero-out sweep: kills any leftover (batch processes incl. its browser), closes
# every open run, releases any chair, and verifies "nothing running"; it never
# disables the clock (that is pausar) and never deletes historical data
bash scripts/limpiar_tandas.sh
```

Notes for the commands: `detener` only touches the live batch it finds (leftover rows from older batches belong to the watchdog or to `limpiar`); `--db` lets any copy be operated for rehearsal; repeated invocations are always safe (they never double-act).

## LinkedIn session (persistent login)

Module 1 keeps its LinkedIn session in `data/browser_profile/` (set via `browser.profile_path` in `config/config.yaml`, a folder owned by the system — never your personal browser profile). Log in once manually in the visible window (up to 5 minutes, including any verification LinkedIn asks for); later runs reuse the session and enter directly. Module 2 always works as a guest and never uses this session.

**Reverting to fully automatic login:** empty `browser.profile_path` in `config/config.yaml` (leave it as `""`). Effect: entry goes back to the ephemeral mode (throwaway window per run), typing the `.env` credentials and waiting ~30 s for the main page; if LinkedIn asks for extra verification, the run ends with `criterio_no_cumplido`/`autenticacion_rechazada` instead of waiting. The `data/browser_profile/` folder can be deleted (it is git-ignored). No migrations or code changes needed.

## Technology Stack

Python 3.12, Playwright, BeautifulSoup4, Pydantic v2, Loguru, RapidFuzz, Tenacity, httpx, SQLite, Ollama (Gemma 4 31B cloud for evaluation/processing routes; GPT-OSS 120B cloud for location classification).
