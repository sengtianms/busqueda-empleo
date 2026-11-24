# Job Search Automation

Automated system for discovery, evaluation, and processing of job opportunities, with LinkedIn as the primary source.

## Documentation

All official documentation is located in `docs/`:

| Document | Purpose |
|----------|---------|
| [Ficha técnica — Descubrimiento (M1)](docs/diagrams/Ficha%20técnica%20-%20Diagrama%20de%20flujo%20(Descubrimiento%20de%20oportunidades).md) | Module 1 (Opportunity Discovery) — node-level spec, as-built v1.1 (D41, D47, D60–D62, D70, D71, D81). |
| [Ficha técnica — Preparación de ofertas (M2)](docs/diagrams/Ficha%20técnica%20-%20Diagrama%20de%20flujo%20(Preparación%20de%20ofertas).md) | Module 2 (Offer Preparation, Phase 5) — node-level spec, as-built v2.1 (D78, 2026-11-18). |
| [Ficha técnica — Orquestador transversal](docs/diagrams/Ficha%20técnica%20-%20Diagrama%20de%20flujo%20(Orquestador%20transversal).md) | Transversal orchestrator (modules 1 → 2 → 3) — as-built with the three-module chain (D34, D49, D76, D79). |
| [Ficha técnica — Evaluación inicial (M3)](docs/diagrams/Ficha%20técnica%20-%20Diagrama%20de%20flujo%20(Evaluación%20inicial%20de%20ofertas).md) | Module 3 (Initial Evaluation) — two AI-free processes: export and import (version 2.2, D76 built 2026-11-19, aligned to instruction v7 by D80 on 2026-11-20). |
| [DOC-13A](docs/project-design/Document%2013A%20-%20Detailed%20Data%20Model%20Design.md) | Detailed data model (entities, attributes, catalogs, ERD) — v1.27. |
| [Appendix 5A](docs/project-design/DOC-Appendix%205A%20-%20Official%20Prefix%20Catalog.md) | Official prefix catalog (IDs, codes) — FNT retired (D31); module scope generalized (D33/D34). |
| [Decision log](docs/history/decision%20log.md) | Approved decisions and deviations — D1 through D81. |
| [MVP Execution Plan](docs/plans/MVP%20Execution%20Plan.md) | Build order and acceptance criteria |
| [tracker.md](docs/history/tracker.md) | Current status of each phase and task |
| [Database tables](docs/reports/database-tables.md) | As-built reference of `job_search.db` (tables, columns, writers) |
| [Adding a new source](docs/adding-a-new-source.md) | Step-by-step guide to integrate a new platform (config, adapter, registry, tests) |
| [Plan funcional fase 5](docs/plans/Plan%20funcional%20fase%205.md) | Phase 5 functional plan — historical design record, superseded by the Module 2 sheet v2.1 and D78. |

## Status

Version 1 is complete (decisions D54–D56, 2026-10-19): Phases 0–6 — Module 1 (Opportunity Discovery), Module 2 (Offer Preparation), Module 3 (Initial Evaluation) and the transversal orchestrator — run the full loop end-to-end, both manually and automatically: a system timer fires a complete run 10 minutes after the computer powers on and repeats it every 3 hours while the machine is on (decision D54); first scheduled run: discovery → preparation (47 prepared + 1 duplicate) → evaluation → 7 approved / 39 justified discards, 0 chain errors. Phases 7–8 (deep processing, results management) are deferred to future versions (D55). Post-V1 hardening closed 2026-10-22 (decisions D60–D64): the search matrix runs a single Colombia sweep, live progress is visible from any terminal (`scripts/estado_corrida.py`), manual runs narrate themselves, a minute-level watchdog alerts on stalled batches and closes dead runs (D60–D63), and four operator commands manage the cycle by hand — pause, resume, stop-now and zero-wipe (D64). First operations batch closed 2026-10-23 (decision D65): the scheduled unit runs as `Type=exec` so the ordered stop is real and never fires the emergency alert, the board's remaining-time estimate counts completed search sets only, and the last batch is told apart from its last stage even when both close on the same second. The 06:32 scheduled batch closed the pending post-reset verification (238 offers, 0 chain errors, desktop verdict). Operations viewers slimmed 2026-10-24 (decision D66): the watchdog and the live board read only what each pass needs — the board fell 0.844 → 0.037 s and the watchdog 0.513 → 0.0045 s on a 103 MB synthetic bench, with identical output in the two compared scenarios. 765 tests; the ordered stop was confirmed live on 2026-10-24 (COR-0026/COR-0027: 0.59 s, unit `inactive`/`success`, no emergency alert; tracker). Session audits now store one row per search set, updating on reentry (D67). Watchdog passes now land every 2 minutes instead of every minute — same thresholds, detection rules, closures and alerts (D68). Evaluation redesigned 2026-11-15 (decision D76): Module 3 no longer calls any AI — the scheduled batch exports the prepared offers as chat-readable lots, the operator evaluates them at no cost, and a one-line manual command imports the results with strict validation (invalid lines are rejected and their offers stay pending). Built and closed on 2026-11-19 (branch `rediseno-evaluacion`): the batch exports lots, the one-line command `bash scripts/importar_evaluaciones.sh` imports the chat's answer with strict validation, the old AI route was retired and the preflight no longer checks models. Real export of 294 offers into 10 lots closed as `evaluacion_pendiente` with 0 errors; a real import on a copy applied 15 approvals and 15 justified discards with a clean closure. Module 1 keeps its LinkedIn session in a system-owned folder and can wait once for a manual login (D47), and its browser channel renews and resurrects during a batch so each run finishes intact (D81); both were verified in live batches. The locations catalogue gained an exact-tuple uniqueness guard (D82) and a one-line maintenance command to list, add, correct and fuse rows without SQL (D83), with a catalogue check in preflight. 1,014 tests; lint and types clean.

## Running the pipeline

Prerequisites: a Python virtual environment at `.venv/` and LinkedIn credentials in `.env` (see `config/.env.template`). The batch does **not** need Ollama: evaluation is AI-free, and the location classifier only falls back to an OpenRouter door (`OPENROUTER_API_KEY_1` in `.env`) when the deterministic municipality catalogue cannot resolve a text. Ollama remains optional for manual prompt testing and future processing work. The first login may be manual: Module 1 keeps a system-owned session in `data/browser_profile/` and waits up to five minutes for it.

```bash
# 1. Preflight check: config, work folder, database, locations catalogue, lock state
.venv/bin/python scripts/preflight.py

# 2. Full run (discovery -> preparation -> evaluation; manual runs narrate)
.venv/bin/python -m modules.orchestrator

# 3. Watch the current/latest batch live from any terminal
.venv/bin/python scripts/estado_corrida.py

# 4. Diagnose any past run (stages, offers by state, errors, catalogs)
.venv/bin/python scripts/reporte_corrida.py

# 5. Diagnose which search list brought each offer and its duplicates (read-only)
.venv/bin/python scripts/reporte_listas.py
```

Notes:
- `preflight.py --db` expects an explicit database path as an argument; omit it to check the default `data/job_search.db`.
- Logs default to INFO; set `LOG_LEVEL=DEBUG` in `.env` for verbose output.
- All persistent data lives in `data/job_search.db`; backups are stored under `data/backup/`.
- Evaluation runs in two processes (D76, built): the batch exports the prepared offers into `data/evaluacion_manual/lotes/` and closes as `evaluacion_pendiente` when lots are waiting (or `sin_pendientes` when there is nothing to export). Evaluate a lot in the chat, save its answer in `data/evaluacion_manual/resultados/` and run `bash scripts/importar_evaluaciones.sh`: it validates each line, applies the verdicts, shows the report and sends the desktop notice. Since D80 (instruction v7) each answer line carries `eje_organizacional` (five closed values, coherent with V1) instead of the former deliverable; invalid lines leave their offers pending, and a lot with missing answers is kept and named in the report.

## Catálogo de ubicaciones

El catálogo de municipios es dato del operador, no se recalcula en cada tanda. Se mantiene con una sola orden (D83), sin escribir consultas:

```bash
./scripts/catalogo_ubicaciones.sh listar bogota          # buscar; --todo para ver todo
./scripts/catalogo_ubicaciones.sh listar --origen sistema
./scripts/catalogo_ubicaciones.sh agregar --municipio "Puerto Nuevo" --departamento "Cundinamarca"
./scripts/catalogo_ubicaciones.sh corregir UBI-XXXX --municipio "Nombre correcto"
./scripts/catalogo_ubicaciones.sh fusionar UBI-XXXX UBI-YYYY   # equivocada -> correcta
```

- **Listar** muestra totales, origen, ofertas enlazadas y posibles variantes de escritura; es de solo lectura.
- **Agregar** crea municipios o filas de solo departamento con país Colombia y origen `operador`. Rechaza duplicados exactos, variantes, alias conocidos y departamentos repetidos.
- **Corregir** cambia el nombre sin cambiar el identificador: las ofertas ya enlazadas conservan su enlace y su texto original.
- **Fusionar** mueve las ofertas de la fila equivocada a la correcta y retira la primera en una sola operación. No hay borrado suelto.
- Las filas «no aplica» y «solo país» son estructurales y no se editan. Las filas creadas por el sistema conservan su origen aunque se corrijan.
- Las escrituras se niegan si hay una tanda activa. Añade `--db RUTA` a cualquier acción para ensayar sobre una copia; las escrituras reales quedan en `logs/catalogo_ubicaciones.log` y los ensayos, con marca `ENSAYO`, en `logs/catalogo_ubicaciones_ensayo.log`.
- El prevuelo comprueba el catálogo antes de cada tanda: falla si falta una fila estructural y avisa si detecta variantes.

## Scheduled automation

A user-level system timer fires the full pipeline automatically (decision D54): first run 10 minutes after the computer powers on, then every 3 hours counted from each run, stopping at shutdown. No fixed times — the day's drag run recovers overnight postings because the capture window is the last 24 hours and repeats are resolved by the dedup rules. Since D76 the automatic batch hands evaluation over as exported lots and closes as `evaluacion_pendiente`; importing the chat's answer is a manual step, so no run ever waits for a person (built and verified on 2026-11-19).

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
- A 2-minute watchdog (decisions D63 + D68): if the batch freezes without signals with a fresh chair it alerts desktop-side once per offense — "examínela" — without touching anything; runs whose processes provably died (own silence past the threshold, expired chair) are closed as `abortada: proceso desaparecido` with the official termination evidence; if the batch unit itself dies without its own verdict notification, an `OnFailure` desktop alert fires (deduplicated against the batch's own verdict in the journal). All of it is installed/removed together with the scheduler above.
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

To import the evaluations returned by the chat (one line, no arguments):

```bash
bash scripts/importar_evaluaciones.sh
```

It prints the report (applied, rejected, closed and kept lots, pending offers), sends the desktop notice and exits with a real status. `--db` lets you rehearse on a copy.

## LinkedIn session (persistent login)

Module 1 keeps its LinkedIn session in `data/browser_profile/` (set via `browser.profile_path` in `config/config.yaml`, a folder owned by the system — never your personal browser profile). Log in once manually in the visible window (up to 5 minutes, including any verification LinkedIn asks for); later runs reuse the session and enter directly. Module 2 always works as a guest and never uses this session.

**Reverting to fully automatic login:** empty `browser.profile_path` in `config/config.yaml` (leave it as `""`). Effect: entry goes back to the ephemeral mode (throwaway window per run), typing the `.env` credentials and waiting ~30 s for the main page; if LinkedIn asks for extra verification, the run ends with `criterio_no_cumplido`/`autenticacion_rechazada` instead of waiting. The `data/browser_profile/` folder can be deleted (it is git-ignored). No migrations or code changes needed.

## Technology Stack

Python 3.12, Playwright, BeautifulSoup4, Pydantic v2, Loguru, RapidFuzz, Tenacity, httpx, SQLite, Ollama (declared local route for Preparation; location classification currently uses the configured OpenRouter reserve because the principal door is off). Module 3 no longer uses any model: the operator evaluates in the chat.
