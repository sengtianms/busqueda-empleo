# Session History
Chronological record of OpenCode sessions (newest first, one entry per session, ID-identified). Sessions 1–5 detail preserved in git.
Unless noted, decisions from previous sessions remain in effect.

## Sessions index
| № | Date | Session ID | Summary |
|---|---|---|---|
| 45 | 22/10/2026 | `ses_f4af1b961ffe5t8xNspW5U761x` | Four operator commands for the batch lifecycle shipped and live-verified (decision D64 in log v1.43): pause turns the scheduler clock off surviving reboots while a running batch finishes normally (exercised for real — the imminent firing was cancelled by operator choice), resume re-arms the clock with a next-firing report and watchdog repair, stop cuts the running batch and closes it instantly with truthful operator authorship on the official closure, and a zero-wipe closes everything and releases chairs while never disabling the clock nor deleting data; two real-world lessons baked in: commands never cut their own ancestor chain, and a failed unit needs stop plus a failure-mark reset; 744 tests; cycle left paused by operator choice — hot verification awaits resume |
| 44 | 22/10/2026 | `ses_f4af1b961ffe5t8xNspW5U761x` | Time-real batch visibility shipped in three reviewer-approved lotes and closed documentally in the same session (decisions D60–D63 in log v1.42): read-only live board from any terminal, manual-run narration voice with trace ticks excluded from closure metrics, minute-level silent-death watchdog with user-authorized ghost-run closures plus an OnFailure desktop fallback; a failed live smoke forced a per-row death-proof redesign protecting the running batch's own rows; matrix cut to a single Colombia sweep; README command corruption repaired; 730 tests; live scheduled-tanda verification still pending |
| 43 | 22/10/2026 | `ses_f4af1b961ffe5t8xNspW5U761x` | Browser anti-stall resilience built on the crash autopsy of a 1,000-offer batch (renewal every ~30 heavy pages with the same session memory, unbounded resurrection resuming the search at the exact page where death struck, honest stop only for a broken environment or an expired manual-entry window, per-operation time ceiling with a watchdog that forces the browser process tree down, chair always returned on every exit path); a live probe caught and fixed a silent no-kill defect in the enforcer; multi-geo groundwork rides along — deterministic region navigation after the platform killed the plain location parameter (world anchor verified live), 72-set source matrix, totals reader repair; live verification awaits the next scheduled tanda on the wiped database (693 tests) |
| 42 | 20/10/2026 | `ses_f4af1b961ffe5t8xNspW5U761x` | Evaluation prompt v6 registered officially (user text verbatim, reorganized for model legibility); production database purged at user request and a fresh full run through the official scheduled path verified end-to-end on the clean database (64 discovered → 64 prepared + 5 duplicates → 1 approved / 58 justified discards, 0 chain errors) with the desktop verdict popup delivered; the save's single commit also carries the parallel door-rotation hardening built against the morning hang (652 tests) |
| 41 | 19/10/2026 | `ses_f4af1b961ffe5t8xNspW5U761x` | Version 1 closed officially: scope cut to Modules 1–3 + orchestrator + scheduled automation (OS-level timer with post-boot drag run and 3-hour cadence, wrapper with preflight gate, installer tooling, versioned units), first live automatic run verified end-to-end; evaluation v5 strict behavior confirmed by the user and calibration audit closed with no findings; verdict notifications added afterward — desktop popups driven by the official trace with skip-vs-error distinction, live-verified against the morning chain (643 tests) |
| 40 | 19/10/2026 | `ses_f4af1b961ffe5t8xNspW5U761x` | Measured health audit from the primary records concluded no structural refactor was justified (run telemetry: five green runs, full pipeline ~2.5 min per 27 offers); evaluation prompt v5 work unified into main by fast-forward merge with full battery, push, and work-branch deletion (single-branch state restored); post-10k id-ordering limitation closed with a shared numeric key over candidate loads, run tiebreaks and duplicate originals, zero data migration, seven regression tests; both closing reviewers green; evaluation calibration audit (3 approvals → 0 on the same offers after the v5 rebuild) left pending by user choice |
| 39 | 17/10/2026 | `ses_f4af1b961ffe5t8xNspW5U761x` | Phase 6 completed (Module 3 built, verified on a solo run and on a full clean-DB orchestrated run); three OpenRouter alternate doors programmed with per-offer rotation and live-verified; evaluator justifications upgraded to evidence-backed explanations after the sample review; minor documentation polish (test counts, full-run registration, database counts, README index) |
| 38 | 15/10/2026 | `ses_f4af1b961ffe5t8xNspW5U761x` | Module 3 sheet built node by node (4 nodes, veto design, closure motives and metrics, prompt v2, separate flow-diagram image); 5-point pre-build gate recorded ahead of Phase 6; docs-only alignment batch applied across settings, data model, tables reference, decision record, plan, tracker and transversal sheet (D48); plan/tracker verified against the sheet and sub-phase build strategy confirmed; Previo Fase 6 built alone on approval (new result field and states, run counters, settings validator, preflight check, live DB migrated with backup); module nodes not started |
| 37 | 08/09/2026 | `ses_f7ef9f510ffe2YkCmvje0FKH6S` | Entry unblocked after OS reinstall with a persistent session (one manual login, later runs automatic); window fixed to a normal size with content following resizes; guest completion path proven still anonymous from real evidence; polish batch with shared settings readers plus decision record and operations docs; full runs green with zero errors |
| 36 | 25/08/2026 | `ses_fc6fa3931ffe4thZKiecpyCuhK` | Enrichment era closed (built as D39, measured as bottleneck, reverted as D40); three clean-run verifications mapped end-to-end; data-fidelity batch landed keeping every character in company keys, verbatim offer descriptions and a raw card company column (D41); full ops/performance program shipped: run-report and preflight CLIs, schema auto-init, jittered pacing, unified event emitter, persistence split into a package and card parser extracted (D42); live DB migrated twice with backups; final dogfooded verification preflight→run→reporte; second half: self-service run instructions proven by the user's first fully manual corridor on a wiped database, ERR-08 cluster traced to one all-caps department string, deterministic Colombian-department fast path added (D43) and local model swapped to gpt-oss:120b-cloud with a confidence-oriented prompt rewrite (D44); phase 5 formally closed by registering the orphaned handover-session changes as a consolidated decision (D45) and aligning data model, tables reference, README operations guide and both module sheets; final stretch: development branch merged into main and retired (single-branch state), third full wipe, user's fastest real run yet (123 offers under six minutes) exposed a location name-variant duplicate that was fixed generically with similarity-based catalog fusion (D46) |
| 35 | 25/08/2026 | `ses_fc9cdf2e5ffeMja2ZpSownJ82R` | First real orchestrated sequential runs M1→M2 validated end-to-end on an emptied database (twice); traspaso fixes confirmed; capture bug with pipe-in-title fixed using real card evidence; deterministic AI sampling (temperature 0) both routes; tests isolated from the production database; operating contract gains the functional-communication instruction (525 tests) |
| 34 | 21/08/2026 | `ses_fdafc2fd0ffexoEFYn60IjcuYQ` | Sub-fases 5.1–5.6 implementadas: fundamentos D33, nodos INICIO + decisión de candidatas, nodo Preparación de ofertas (captura httpx invitado, catálogos empresa/ubicación con IA PRM-006), Verificación de duplicidad + decisión de bucle (RapidFuzz dos etapas), Finalizar Proceso + orquestador del flujo del módulo (métricas por eventos, ruteo de terminaciones, fila de corrida registrada antes del bloqueo) y Orquestador transversal de corrida programada (lanza módulos en serie, resultados derivados desde la BD); D35–D38 registradas |
| 33 | 21/08/2026 | `ses_fdba95353ffezwVG7roiPKaX2c` | Phase 5 build plan defined from the two technical sheets: 7 sub-phases approved and written into MVP Execution Plan + tracker replacing the obsolete generic task list; docs-reviewer findings corrected |
| 32 | 20/08/2026 | `ses_fe33fd2dfffeQS3bPEmnaiJW1h` | Phase 5 documentation: Module 2 (Preparation) + transversal orchestrator technical sheets created and aligned across project docs (decision log, DOC-13A, database-tables, Appendix 5A, ficha M1, plan, guide, README); tracker 4.26 |
| 31 | 19/08/2026 | `ses_fe539fd2ffferuSLgK6EE88f5b` | Table rename D32: `ofertas` → `ofertas_descubiertas` everywhere (schema, secuencia_ids, nodes, tests, docs); idempotent migration first in `init_db`; live DB migrated in place, no backup; prefix OFE, indexes and function names unchanged; 331 tests |
| 30 | 18/08/2026 | `ses_fea037d3dffeR12tTJoQEt4IFq` | Multi-search Q&A in Module 1: `sets_de_filtros` natively supports several queries per run (search → capture → register per set, dedup by external id); contiguous-index rule documented in `config.yaml` (option A, config-only) — no code changes |
| 29 | 18/08/2026 | `ses_feb0c7a29ffe0jOcMvPYiDv5wa` | Schema cleanup + no-empty-field rule (D31): `eventos.id_oferta`, `ofertas.identificador_origen` and the `fuentes` table/FNT prefix removed; N/A/N/R placeholders enforced at the persistence boundary, `fecha_ultima_verificacion` exempted; live DB migrated 9→8 tables with backup (329 tests) |
| 28 | 17/08/2026 | `ses_fef46d693ffeeJzOMWNCGCQb5s` | Success-event traceability + observability (D30): `ingreso_exitoso`/`consulta_exitosa` emitted by the entry/search nodes aligning the ficha contracts, `duracion_s` in capture evidence, INFO logs default, `total_sucesos` semantics documented; verified fresh run COR-0001 98 offers 0 errors (327 tests) |
| 27 | 17/08/2026 | `ses_fef46d693ffeeJzOMWNCGCQb5s` | Card field extraction (D28) then user-requested revert (D29): only publication date kept, raw company/location columns dropped from `ofertas`, DB reset without run, verification COR-0001 99 offers 0 errors (322 tests) |
| 26 | 17/08/2026 | `ses_fef46d693ffeeJzOMWNCGCQb5s` | SDUi filter fix (D27): new LinkedIn UI drops `f_WT`/`location` — remote-only via `f_SAL`, canonical date buckets, DOM chip verification + UI click fallback, config without modality (318 tests) |
| 25 | 14/08/2026 | `ses_ffd4eef78ffeLdakkTRbtGuLdu` | Filter evidence debate + functional E2E & production-mode tests (COR-2068..2071) + D26: search entry straight to `/jobs/search-results` with `wait_until="commit"` — one search load + direct pagination, verified by COR-2140 (308 tests) |
| 24 | 14/08/2026 | `ses_ffd4eef78ffeLdakkTRbtGuLdu` | Lote D (D25): P4 items 13–18 — `EstadoCorrida` aligned to D4 + `Corrida` closure fields validated, value checks replacing dead `hasattr`, `marcar_cambio_de_fuente`, orchestrator `_ejecutar_nodo` + Protocol, single credential resolution, `logging.logs_path` (307 tests) |
| 23 | 14/08/2026 | `ses_ffd4eef78ffeLdakkTRbtGuLdu` | Lote C (D24): P3 duplication unifications — `ahora()`/`FORMATO_TIMESTAMP`/`TIPOS_ACCESO` in shared utilidades, `escribir_evento_seguro`, `_enviar`, merged capture policies, unified `_revisar_estado`, `_resultado_fallo` (302 tests) |
| 22 | 14/08/2026 | `ses_ffd4eef78ffeLdakkTRbtGuLdu` | Lote A (D22): Playwright leak fix (resources tracked in context, public closure reused by orchestrator), batch persistence in one connection derogating ficha NOTA 4.4, SQL closure metrics, RETURNING ids · Lote B (D23): unified retry helper replacing the 3 node loops + test-only variant, dead `escribir_lote` removed, Pydantic validation on writes (300 tests) |
| 21 | 14/08/2026 | `ses_0002228fbffeOK2V1m5PaeYAiK` | Filter investigation + observability hardening (D18–D21): LinkedIn `f_TPR`/`f_WT` verified working (UI labels cosmetic), search evidence URL+total, `fecha_publicacion` format validation, robust login fallback (282 tests) |
| 20 | 12/08/2026 | `ses_00927e803ffeXTR04EkYYKzmTV` | Project-wide review lots executed: Lote 1 quick-win cleanup (fast suite, dead state/fixtures, D14), Lote 2 Spanish catalog completed (D15), Lote 3 persistence performance (single-connection upsert + indexes, D16), Lote 4 test quality + last cleanups (vestigial node retired, contract session close, config + integration tests, D17) |
| 19 | 11/08/2026 | `ses_00f57a514ffeUyBVloqdH07g2W` | Spanish naming catalog (D7/D8): English→Spanish rename in code, config, tests; DB migrated with backup; docs aligned (decision log v1.1, DOC-13A v1.5, ficha, plan, tracker 4.7) |
| 18 | 11/08/2026 | `ses_011dd31a8ffe0sUJfx0l66OpUJ` | Documentation depuration: only primary docs kept, all non-primary deleted physically; docs-reviewer optimized (single skill, git-diff scope, primary-only checks, conditional output) |
| 17 | 10/08/2026 | `ses_0133020ecffeN4R4bi4Y7MXDAF` | LinkedIn 2026 SSR login fixed (direct login, `voyager` criterion, multi-variant parsing) + `sesiones` schema migration + closure-metrics success event (240 tests) |
| 16 | 10/08/2026 | `ses_0133020ecffeN4R4bi4Y7MXDAF` | Sub-fase 4.5: terminal closure node + full-flow orchestrator implemented, validated, and audited CONFORME (229 tests) |
| 15 | 09/08/2026 | `ses_01823c05affeFQbFrKubp332mC` | Skills inventory reviewed; review-against-documentation fully rewritten; /save authorized full commit of worktree |
| 14 | 09/08/2026 | `ses_01bcc78adffemcqFEiZxT52Eli` | Sub-fase 4.4: capture/registration nodes implemented, audited, and post-audit fixes applied (FK-free schema, name columns, upsert tests) |
| 13 | 08/08/2026 | `ses_01be77680ffeuyoKct4Qrfx1GG` | Repo sync to `fase-4`; new `/save` section with general git commit and push guidance |
| 12 | 08/08/2026 | `ses_01c089ce2ffe9MvQT4F1pC0MJN` | Sub-fase 4.2 deep audit + post-audit fixes (credentials mapping, playwright lifecycle) |

## Session 45 — 22/10/2026
`ses_f4af1b961ffe5t8xNspW5U761x` · `ajuste-final-v1`

**Topics**
- Four operator commands designed from user answers on two open questions: pause means the scheduler clock turning off system-wide (nothing fires, not even after a reboot, while a batch already running finishes normally), and stopping the current batch means cutting it AND closing it honestly at once rather than leaving an orphaned trace
- Single command engine in Spanish with four one-line operators, all idempotent, each with a desktop confirmation plus a journal line; a copy-database flag for safe rehearsals and an adjustable grace window between the soft and the forced stop signal
- Stop identifies the live cluster with the same board anchors as the viewer (batch + module in course), kills manual-run processes from soft to forced plus the capture browser it can leave loose, and closes those runs instantly through the watchdog's closure machinery with truthful authorship written into the closure evidence; old leftover rows stay untouched for the watchdog or the wipe
- Wipe is the zero guarantee: stops every leftover, closes EVERY open run with the official form, releases any remaining chair including owners unknown to the trace (explicit operator order overrides the watchdog's anonymous-chair caution), re-verifies processes and open rows, announces "everything at zero" or names what is pending, and never disables the clock nor deletes data
- Resume re-arms the clock, reports when it will next fire, and repairs the batch system through the official installer if the watchdog went loose; pause never touches the trace, resume repair counts as a real action for its desktop notice
- Live smoke caught a real defect on day one: a command whose own text mentioned the process patterns got match-killed together with its terminal — the entire ancestor chain of the command is now untouchable, proven by a dedicated contract test
- Second live lesson: a scheduler unit marked failed stays marked after a plain stop; clearing it needs stop plus a failure-mark reset, now part of both stop and wipe
- Day's real events inspected read-only before touching anything: the pending live-verification tanda fired at 16:36 and was hand-stopped two minutes in (unit left failed, trace already wiped clean — nothing to close); with the next firing minutes away, the operator chose the new pause command for real, which cancelled it with popup and journal; resume deliberately left for the operator's hand when the hot verification gets scheduled
- Documentary closure by the standard gates: formal decision registered (decision log v1.43), README commands block and status refresh, tracker gains the commands section, operating contract gains a status clause and the new test count; code reviewer green after two robustness minors (repair acting counts as an action; an unreadable trace no longer claims "zero"), docs reviewer green after a status refresh and a spacing fix

**Decisions**
- D64: the four operator commands — pause/resume/wipe never touch the trace's truth (closures reuse the watchdog's official form under operator authorship; the wipe releases unknown chairs only by explicit order and never touches the clock or data), the commands' ancestor chain is never a kill target, and a failed unit is despejada with stop + failure-mark reset
- Decisions from previous sessions remain in effect

**Status**
- Operator commands ✅ built, tested and live-verified: pause exercised for real (imminent firing cancelled), stop and wipe verified end-to-end against database copies with dummy processes including the failed-unit despeje, resume covered by tests and reserved for the operator's hand — both closing reviewers CONFORME after fixes
- Ruff 0 · mypy 0 (strict, 106 files) · pytest 744 passing
- Live scheduled-tanda verification ⏳ still pending (tracker); the cycle is left PAUSED by operator choice — resuming arms the clock and reports the next firing, which completes that verification
- Branch: `ajuste-final-v1` · session work committed by this save · no merge to `main`

## Session 44 — 22/10/2026
`ses_f4af1b961ffe5t8xNspW5U761x` · `ajuste-final-v1`

**Topics**
- Live batch board closure: tanda anchoring hardened, batch launched inside a 900-second identification window kept separate from the frozen threshold, missing/uninitialized database renders a plain-language panel creating nothing, both evidence-separator styles accepted, per-module remaining-time estimated from the run's own pace; 17 tests, reviewer verdict green
- Manual runs narrate themselves in their terminal (module announcement, search-set launch, capture page progress) through a small inviolable speaker; automatic scheduled batches stay silent because the wrapper marks the process chain; the board consumes brand-new trace ticks to name the module and track set/page progress
- Narration ticks recorded in the official trace but explicitly subtracted from every closure metric, keeping verdicts and totals byte-identical to tick-free runs; verified once by reviewers across all three closure formulas
- User explicitly authorized closing dead leftover runs and a desktop alert on batch death; a watcher asking once per minute reviews lack of life: catching a stalled batch only alerts (nothing touched); runs whose own silence proves death are closed with the official closure form and a desktop notice of what was closed
- Failed smoke taught the closure rule: a proof measured per run (each run's own signals) replaced the global measure, and the live batch's own rows gained protection through the board's anchors — stale seat closes the whole chain, inherited seats freed in passing, unknown seat owners untouched
- First Lote-3 review caught a leaked contract: a failed row update used to release that run's seat and announce it as closed; fixed to order row-first-chair-later with honesty enforced and covered by a dedicated test
- If the scheduler's batch unit dies unable to report (kill/OOM), a fallback desktop alert fires with journal-based dedup so it never repeats the wrapper's own verdict; installer manages the two extra watcher pieces together with the scheduler
- Documentary closure executed in-session by user order while the live verification remains pending: formal decision records D60–D63 (decision log v1.42), README status/scheduled/running blocks (including repairing a corrupt run-command line), operating contract status refresh, search-matrix cut to a single Colombia sweep aligned in the platform adapter comment; docs review green after two minor text corrections

**Decisions**
- D60: search matrix reduced to a single Colombia sweep (geography by official region code only; other region anchors + remote modality removed; two-digit totals repair already validated live)
- D61: read-only live board contract (anchoring, safe missing-database behavior, own-pace estimates)
- D62: manual narration voice + three trace ticks recorded as successes yet subtracted from metrics (zero-tick semantics identical to before)
- D63: minute-level watchdog, user-authorized ghost-run closures with per-row ownership proof, once-per-offense desktop alerts, and OnFailure fallback with journal dedup
- Decisions from previous sessions remain in effect

**Status**
- Three visibility lotes ✅ closed (board · narration/ticks · watcher) with reviewer CONFORME ×3 and documentary closure ✅ (docs review green after fixes)
- Ruff 0 · mypy 0 (strict, 104 files) · pytest 730 passing
- Live scheduled-tanda verification ⏳ pending on the wiped database (validates the whole feature hot; tracker row) — after it, nothing left open for this task
- Branch: `ajuste-final-v1` · session work uncommitted until this save · no merge to `main`

## Session 43 — 22/10/2026
`ses_f4af1b961ffe5t8xNspW5U761x` · `ajuste-final-v1`

**Topics**
- Crash autopsy context at the session's start: a Saturday-afternoon automatic batch collapsed when one search set ballooned to 946 offers across 38 heavy pages (process killed itself mid-run; the launcher stayed alive but mute with the batch seat held); the stage was reset on the user's instruction — scheduled service stopped, only the automation's browser processes removed, the database wiped to zero rows with no backup, official id counters restarted
- Iron rule set with the user before building: nothing of a batch travels to the next batch — every batch finishes its own work integral
- Anti-stall resilience ("browser vest") built on five approved mechanisms, described functionally to the user: preventive channel renewal every ~30 heavy page-loads with the same session memory and no interruption; resurrection on browser death — wreck discarded, fresh channel with session memory, search resumes at the exact page where it died, unbounded while there is progress (each fetched page forgives the counter); no-surrender — the only honest stops are the expired manual-entry window and a broken environment (consecutive deaths with zero progress), and both close the batch with a verdict
- Hard time ceiling on every supervised browser operation (watchdog thread with absolute deadlines): silence beyond the ceiling forces the browser process tree down, so a wedged call can no longer hang the batch the way it did during the autopsy
- Capture contract extended additively: a capture can be cut to page/offer budgets and restarted exactly where the previous one stopped; the per-search state now reports the exact resume position and whether more pages remain; the single-chunk happy path preserves the prior result objects verbatim so existing consumers and tests keep their identity guarantees
- Channel lifecycle centralized in a discovery-side navigation module (open / kill / re-open with re-entrance reusing session memory; the session's logical session id survives reconstructions); the entrance node delegates channel helpers keeping its patchable private names; the search node re-attempts its set after a death; the capture node runs the chunked loop with the classic conditional retry kept inside each chunk
- Configuration gained a discovery settings block (renewal threshold, consecutive-death cap) validated at the start node and carried by the run context; the renewal event is an official success event so close-metrics stay faithful
- Live probe against a real channel caught a fatal hidden flaw: the process enforcer's search pattern was parsed as the killer's own option and never killed anything — silently; fixed with the end-of-options separator and re-proven live end-to-end (browser dies, the blocked operation wakes with the death signal, detection recognizes it, zero automation processes left)
- Multi-geo groundwork rides in the same commit: deterministic region-code navigation after the platform stopped honoring the plain location parameter (world anchor verified live against the Colombia anchor), the source matrix grown to 72 filter sets across the four geographic sweeps, the double-digit totals reader repaired, preflight database self-check fixed
- 41 tests added across the session (geography groundwork + resilience): death-signal detection direct and by cause chain, enforcer patterns, reopening paths (success, aperture failure, re-entrance failure, unmet criterion), renewal switching, watchdog firing decisions, adapter resume/budgets, nodes' resurrection and abort behavior

**Decisions**
- No new decision rows yet: the geography groundwork and the resilience batch are registered formally after the live verification (planned immediately after the next scheduled tanda); the work already carries the reserved decision markers in code and tests
- Decisions from previous sessions remain in effect

**Status**
- Resilience vest ✅ built and battery-verified (ruff 0 · mypy 0 · pytest 693) · multi-geo groundwork ✅ built, riding this save · live verification ⏳ pending on the next scheduled tanda (17:51 clock slot, full chain on the wiped database with a verdict expected)
- Documentary closure ⬜ pending after that verification: decision registrations, module sheet as-built, operating-contract status refresh
- Session history + all session changes committed in this save; on the user's request right after, the session work was consolidated by fast-forward merge into `ajuste-final-v1` and the work branch removed locally and remotely (battery re-verified on the destination branch); the consolidation rides a small follow-up docs commit
- Branch: `ajuste-final-v1` · no merge to `main` (merging awaits explicit user authorization)

## Session 42 — 20/10/2026
`ses_f4af1b961ffe5t8xNspW5U761x` · `ajuste-final-v1`

**Topics**
- Evaluation prompt v6 into force: the user's text accepted verbatim and reorganized for model legibility — candidate profile with explicit seek/avoid lists, golden rule tightened against generic and aspirational phrases, V1 application rules with a wider artifact catalog, V2 defined by real leadership/design authority, V3 discarding requirements-only descriptions, six calibration examples; response contract, validator and provider doors untouched
- Prompt-only change verified on its consumption path: placeholders survive the substituting renderer exactly; no code or settings adjust, the new text activates by itself on the next evaluation
- Production database purged at user request with no backup taken: every table's records wiped to zero, structure preserved, official id counters restarted from the beginning
- Fresh full run through the official scheduled path on the clean database (~8 min): discovery captured 64 new offers over the 24-hour window, preparation prepared all 64 with 5 duplicates resolved and the opening LinkedIn temporary walls self-recovered by its retries, initial evaluation returned 1 approved / 58 justified discards, 0 chain errors — nothing left pending classification
- v6 behavior visible in the verdicts: the accepted offer is a decision/information-systems management role justified with quoted description evidence; sampled discards each name the veto controls that applied (individual-execution technical roles failed on the two main controls even with Senior titles)
- Desktop verdict popup verified again in production with the clean-run counts
- Pending-change inventory requested by the user before gating the save: the single commit also carries the parallel door-rotation hardening answering today's hung batch (per-door wait cap with immediate rotation, fallen doors remembered for the rest of the run, honest stop when every provider fails)

**Decisions**
- D58 (2026-10-19): evaluation prompt v6 — user-authored text verbatim, structured into titled sections/lists; candidate profile + tightened golden rule + real-seniority criteria; output contract unchanged (decision log v1.40)
- Decisions from previous sessions remain in effect

**Status**
- Prompt v6 registered ✅ (tracker 6.5) · door-rotation hardening ✅ (tracker 6.6, parallel work carried in this commit); 652 tests passing · ruff 0 · mypy 0
- Database running clean: it holds only the verification run's 64 offers, three green module rows and the complete trace, ready for the user's own review of v6 verdicts
- Session history and all pending branch changes committed in this /save (single commit + push)
- Branch: `ajuste-final-v1` · no merge (merging to `main` awaits explicit user authorization)

## Session 41 — 19/10/2026
`ses_f4af1b961ffe5t8xNspW5U761x` · `ajuste-final-v1`

**Topics**
- Version 1 closed: official scope = discover → prepare → initial evaluation chained automatically; deep-processing and results-management phases deferred to future versions; the existing orchestrator entry replaces the old five-module launcher in the plan
- Scheduled automation deployed at the OS level: drag run 10 minutes after power-on, repeats every 3 hours while the machine is on, no fixed clock times; overnight gaps covered by the 24-hour capture window and dedup
- Wrapper hardening: preflight gate before launching per the orchestrator's own entry criteria, venv guard, timeout cap, versioned system units installed in the user session, installer/uninstaller tooling, README scheduled-automation section
- First live automatic run verified end-to-end (~5 min): 48 declared, 47 prepared + 1 duplicate resolved, 7 approved / 39 justified discards, 0 chain errors; one transient offer failure self-recovered on the second pass — nothing left pending
- Evaluation strictness settled with the user: the strict rebuild's all-discard outcome on the earlier sample reflects their profile and intent, calibration audit closed with no findings
- Verdict notifications: every scheduled batch (or a failed start) now posts a desktop popup — success counts / failure motive / benign "another batch in progress" notice — always mirrored into the batch's journal line; same channel as the user's other desktop automations, zero new dependencies
- Notifier reads its verdict from the official trace (batch hour and counts from the run rows and the scheduled batch's own summary marker); a same-second module closure nearly misattributed the batch during live verification — marker-based identification plus a regression test fixed it
- Preflight "another batch already running" counted as a benign skip, not an error; delivery stays best-effort and never alters the run's result
- 12 notifier tests mirroring the house fixtures; battery green (lint/type-check clean, 643 passing); closing reviewers approved, 6 minor hardening suggestions applied
- Docs closed with user approval: decision record rows for the scheduled automation, the scope cut and the evaluator confirmation; scope notes and deferred tags in the MVP plan; README status/sections; operating-contract status; tracker scope section + notification row

**Decisions**
- D54 (2026-10-19): scheduled automation — user-level OS timer (10-minute post-boot drag run + 3-hour cadence), versioned units, wrapper + installer tooling (decision log v1.38)
- D55 (2026-10-19): Version-1 scope cut — Modules 1–3 + orchestrator + scheduling official; Phases 7–8 deferred to future versions; Phase 9 adapted to the three-module chain
- D56 (2026-10-19): evaluation v5 strict behavior confirmed as desired; calibration audit closed with no findings — never reopened absent an explicit user request
- D57 (2026-10-19): batch verdict notifications — desktop popup + journal verdict line read from the official trace, scheduled batch identified by its summary marker (same-second module closure case), preflight lock → benign skip, best-effort delivery (decision log v1.39)
- Decisions from previous sessions remain in effect

**Status**
- Version 1 ✅ (tracker scope section) · verdict notifications ✅ (tracker row); 643 tests passing · ruff 0 · mypy 0
- Scheduled automation live; the next automatic batch fires ~3 h after the previous activation, now with its notification
- Session history + all session changes committed in this /save; single commit + push
- Branch: `ajuste-final-v1` · no merge (merge to `main` awaits explicit user authorization)
- Next: Phase 7 (Module 4 — Deep Processing) is the V2 starting point, deferred until the user requests it

## Session 40 — 19/10/2026
`ses_f4af1b961ffe5t8xNspW5U761x` · `main`

**Topics**
- Full-context recovery from the four primary records, then a measured health audit of the built machinery (telemetry of the five latest runs, file sizes, test surface) concluding there is no structural refactor to justify — only two small evidence-backed items
- Health numbers verified live: last five runs with zero errors, full pipeline at ~2.5 min per 27 offers, style/type checks clean; the big cleanups from prior sessions confirmed as still paying off
- Evaluation prompt v5 work unified into the main line by fast-forward merge with the full battery re-run, push to GitHub, and deletion of the completed work branch — single-branch state restored
- Post-10k identifier-ordering limitation closed: a shared numeric key now governs candidate ordering, run tiebreaks and duplicate-original selection; identifiers, stored values and the database untouched, zero data migration
- Seven regression tests added (ten-thousand-boundary FIFO tie, run tiebreak, duplicate-index collision, numeric eligibility, key cases), all failing under the old text rule
- Closing reviews green on both axes (code and documents); one one-line docstring clarification applied from the code review
- Evaluation calibration audit left pending by user choice: the same 27 offers scored 3 approvals before the v5 rebuild and 0 in today's re-evaluation, to be ruled on separately

**Decisions**
- D53: numeric sequential-order rule for official ids — shared number-after-dash key ordering candidate loads (oldest first) and closed-run tiebreaks (latest first); duplicate-original rules compare numerically (business rules unchanged, comparator only); physical insertion order rejected as the key (fragile after VACUUM); no schema, id-format or data migration
- Decisions from previous sessions remain in effect

**Status**
- Phase 6 complete ✅ (now unified into the main line); Phases 7–9 pending ⬜
- Evaluation calibration audit ⬜ pending user decision (may gate Phase 7 planning)
- ruff 0 · mypy 0 · pytest 631 passing
- Active branch: `main` (single-branch state; work branch deleted after merge)

## Session 39 — 17/10/2026
`ses_f4af1b961ffe5t8xNspW5U761x` · `fase-6`

**Topics**
- Module 3 built node by node on approval: start with candidate decision, five-veto evaluation through routed AI with retries and door rotation, closure with event-based metrics, and the module flow orchestrator
- Prompt hardened against false positives (beneficiary test, structural exclusion of data-plumbing roles) with noise-section hygiene for the AI input only; legacy scoring engine retired
- Module verified live twice: solo evaluation run, then a full clean-database orchestrated run (65 offers → 14 approved + 47 discarded, zero errors)
- Landing-page key table converted into three usable OpenRouter keys in the private env file; three alternate doors programmed with per-offer rotation and one live call verified
- Two time-dependent lock tests fixed to use the real clock instead of a hardcoded morning timestamp
- Sample review of approved offers found explanations contentless; evaluator prompt upgraded to two-to-three-sentence evidence-backed explanations with a 60-word cap, validated live on nine real offers (same outcomes, self-contained explanations)
- User removed their three personal profile documents from the repo root; nothing private entered the version control
- Minor documentation polish: per-node test counts, full-run registration in the tracker, database counts table refreshed to the current database, README status and index aligned

**Decisions**
- D49: Module 3 build (four-node evaluation flow, five routed vetoes, prompt v3 + input hygiene, legacy scoring retirement, solo run verification, transversal third enabled after Preparation)
- D50: three OpenRouter alternate doors active (same Gemma 4 31B family, per-offer rotation on verified door failure, keys only in the private env file, responding door recorded in evidence)
- D51: evaluation justification upgraded — prompt v4 requires evidence-backed per-offer explanations (axis + quoted description evidence + viability, or veto + triggering data; template phrases prohibited), word cap 20→60 synchronized in prompt and validator
- Decisions from previous sessions remain in effect

**Status**
- Phase 6 complete ✅; Phases 7–9 pending ⬜
- ruff ✓ · mypy ✓ · pytest 617 passing; active branch `fase-6`

## Session 38 — 15/10/2026
`ses_f4af1b961ffe5t8xNspW5U761x` · `fase-6`

**Topics**
- Module 3 technical sheet designed node by node with the four-point process (organize node dropped, four nodes kept)
- Separate flow-diagram image produced and reviewed with the user
- Pre-build prerequisite plan defined in five points and recorded ahead of Phase 6
- Full project-document review for Module 3 alignment, document by document
- Docs-only alignment batch applied (new evaluation settings, veto result storage, new states and events, closure metrics, plan and tracker replaced by the sheet-based plan, transversal third after solo run)
- Plan and tracker verified against the sheet; sub-phase build strategy confirmed for construction
- Previo Fase 6 built alone per approved plan (result field, two new states, two run counters, shared settings validator, preflight check, live database migrated with backup, legacy scoring kept)
- Full verification green with previous behavior unchanged; tracker and test-count updates deferred to user approval

**Decisions**
- D48: Module 3 docs alignment before build (legacy scoring kept deprecated until the build retires the old engine; physical migrations, transversal third and scoring retirement deferred to construction)
- Decisions from previous sessions remain in effect

**Status**
- Previo Fase 6 built and verified, pending user approval; Phase 6 nodes not started
- pytest 580 passing (563 prior + 17 new); active branch `fase-6`

## Session 37 — 08/09/2026
`ses_f7ef9f510ffe2YkCmvje0FKH6S` · `fase-6`

**Topics**
- Verification run requested by the user; entry blocked by unknown-device challenge after OS reinstall and full reinstallation
- Browser review: bundled test browser confirmed as the correct application in both modes; entry window fixed to a normal size with content following resizes (then un-maximized per user taste)
- Persistent entry session: single manual login with up-to-five-minute guided wait, later runs fully automatic; valid-session shortcut with detached-form guard; ephemeral automatic mode kept as one-setting reversal
- Guest completion path proven still anonymous from production evidence (wall retries) and code inspection; console-only retry messages and volume effect explained
- Polish batch: shared settings readers, config-driven window and manual wait, single content fetch, tidied imports, new decision record and operations-guide notes

**Decisions**
- D47: persistent entry session plus normal window, session-aware entry, one-setting reversal, polish batch with shared readers; no schema changes
- Decisions from previous sessions remain in effect

**Status**
- Entry, window, session, polish and docs ✅ complete; three real runs green with zero errors (77+2 and 80 offers)
- ruff 0 · mypy 0 · pytest 563 passing across 83 files
- Active branch: `fase-6`; database wiped without backup per user instruction, then re-run by the user (80 offers, 0 errors)

## Session 36 — 25/08/2026
`ses_fc6fa3931ffe4thZKiecpyCuhK` · `fase-5`

**Topics**
- Production database wiped without backup and fully orchestrated sequential runs executed on it; complete run mapping found zero defects (traceability, catalog linking, duplicate handling, canonical modality and the pipe-in-title regression all verified)
- Guest-access experiment on real LinkedIn company pages (31 visits, no login): website/sector/size/description plus headquarters/type/founded/specialties are readable; about one second per page; transient throttle walls clear after roughly 45 seconds; a two-second pause between visits yielded 10/10 successes
- User-approved design change: enrichment ran inside offer preparation right when each company registered, replacing the deferred closure-time placeholder; bilingual label extraction, wall detection by status/body-size with one cooldown retry, autocuración of still-empty companies, catalog extended with four extra columns, live database migrated with backup
- First full run with enrichment active measured on a clean database: ~27.5 minutes total of which ~96% were profile visits; 29 wall blocks drove ~19 minutes of fixed inline waits and still left 25 of 57 companies pending; every block showed the same throttle signature (tiny stub page), zero login screens
- Optimization discussion: shorter waits, patience budgets and decoupled enrichment all rejected — user verdict that doing it later equals never doing it, so the real question was whether the columns are worth filling at all
- Enrichment reverted end to end: preparation stops visiting profiles entirely; reader module, its suite and fixtures deleted; catalog reduced to identity fields via guarded column drops; configuration keys and their validations removed; company data model aligned to the minimal shape
- Documentation re-marked across the decision log (superseding entry), data model attributes, table matrix with counts refreshed from the live database, module sheet as-built notes, tracker row and operating contract status
- Second reviewer round: code approved without major findings; three documentation minors fixed (version-row ordering, stale counts snapshot, orphan model fields); legacy persistence tests re-seeded without dropped columns
- Post-revert verification cycle repeated on a fully emptied database: run mapped end-to-end with zero defects; user clarification that throttling (code 999 stub pages) is neither an error page nor a login wall
- Data-fidelity batch requested by the user: company-name normalization keeps EVERY character (accents/ñ/punctuation/&/dots/parentheses), offer descriptions preserve visible structure (paragraphs/list bullets/line breaks) for future preparations only, and a raw card `empresa` column mirrors `ubicacion` written by Module 1 at registration
- Implementation details: dedicated name-key helper separate from the strict normalizer (locations/duplicate titles untouched) with idempotent key recomputation migration; structural extractor distinguishes injected breaks from source indentation via internal marker; card classifier now returns company+location+modality in one pass; capture path writes the new column end-to-end
- Reviewer round caught a blocker (display column lost between capture and persistence — fixed plus integration test) and a major (source-indentation artifacts breaking sentences — fixed with the marker approach); documentation minors corrected including stale counts and an orphan model field
- Tables dropped entirely (not just emptied): exposed that no component creates the schema (clean ERR-02 abort) and a shell-timeout killed one background attempt leaving a partial locked state — cleaned and relaunched in foreground successfully
- Full-project review delivered measured proposals (pause equals 66% of preparation; eight duplicated event wrappers with inconsistent evidence bounding; persistence at 1,249 lines and adapter at 939 ahead of Phase 6); user approved the complete program
- Operations & performance batch shipped: read-only run-report CLI and preflight CLI (config/database/lock/optional model checks with exit-code gate), schema auto-initialization at the three flow entries, uniform-random inter-offer pause (base lowered, jitter key, validation), single shared event emitter replacing the wrappers with universal bounded evidence, persistence split into a five-module package re-exporting its exact prior API with zero external edits, card parser extracted to its own pure module
- Final dogfooded verification: preflight green → orchestrated run completed with zero errors → reporte CLI printed the full diagnosis in seconds
- Self-service operating instructions delivered (preflight gate, single orchestrator command, run report CLI); user executed their first fully manual corridor on a wiped database — 129 offers captured, 117 prepared, 12 duplicates, zero errors
- Speed review measured on real run data: human-like pacing is the floor by design and parallel fetching was rejected as a bot-signature risk; steady-state daily runs are inherently incremental so the cold-start volume seen that day is exceptional — no worthwhile optimization without damaging protections
- Location warning cluster (32 notices) diagnosed to a single recurring all-caps department string leaving 16 offers pending: root cause was the never-invent rule colliding with unusual formatting — not model size or missing knowledge; both models answered perfectly when asked conversationally
- Deterministic Colombian-department fast path added before the AI call (32 departments plus capital district under strict normalized keys, optional country suffix stripped; city-bearing texts keep the richer AI tuple after tests caught a first-cut regression); successes cached like any other
- Americas expansion scoped with the user: future search-country switches will gate the fast path per configured country and regional catalogs will be added only under measured evidence — nothing built yet by explicit instruction
- Head-to-head model experiments through the exact production request shape: equal geographic knowledge on both models, the bigger-model route roughly three times faster per answer, occasional off-format answers observed and tolerated by the existing design
- Local model swapped to the 120b cloud route and instructions rewritten around confident recognition with four worked examples (domestic caps department, foreign caps division, city+region, country-only) while keeping the strict JSON contract and never-invent guarantee; adversarial battery passed before any file was touched
- Phase-5 gap review showed only the documentation-closure point remained; much of it had already been absorbed by recent decision closures, so the real delta was small and purely documentary
- Documentation closure batch: the five orphaned handover-session changes plus test-suite database isolation registered as one consolidated decision entry; data model aligned to the location-column rename with its writer moved to Module 1 card capture (version bump); README refreshed with a true project status and a new self-service operations guide (preflight, single run command, run diagnosis) matching verified commands and prerequisites
- Database-tables reference got live row counts and its writers matrix corrected — reviewer rounds caught stale attributions still crediting Module 2 for card-written columns, the superseded literal total formula, two step-table rows in the preparation sheet and an outdated catalog justification; all fixed and re-verified clean
- Deferred empty-fields item for companies declared obsolete outright (those columns no longer exist after the enrichment revert)
- Phase formally marked complete in tracker and operating contract; next milestone is Phase 6 (offer evaluation)
- Development branch merged into main under explicit user authorization after verifying zero divergence (fast-forward, identical tree hashes) with the full battery re-run on main; branch deleted locally and remotely — project now lives on a single main line
- Third full database wipe without backup; the user's own run on the consolidated code base was the fastest yet (123 offers in under six minutes, zero blocking errors)
- One real-world defect surfaced: a metro-area name variant classified slightly differently created a second catalog row for Bogotá beside the canonical one — exact-tuple dedup cannot merge name variants, a generic international class of problem
- Location-alias fusion implemented: catalog row resolution happens in a single read per unseen tuple (country-filtered scan serving exact match first, then similarity fusion via RapidFuzz requiring zero component conflicts plus one real coincidence); missing values never fuse alone, country-only tuples never fuse, other-country rows unreachable, every fusion logged
- New optional configuration threshold (0–100, default 90) validated like its siblings; setting it to zero disables only the fuzzy path while exact matching keeps working
- Deterministic full-tuple aliases introduced ahead of the department cheat-sheet ("Bogotá D.C." variants resolve complete triples without touching the AI — safe now because no information is lost)
- Live data healed without backup per user instruction: affected offer re-pointed to the canonical row, duplicate removed, catalog back to ten rows
- Cache regression test caught an early double-read design; resolver restructured into one scan before closing; a tracker editing slip that briefly replaced a prior history row was self-caught and restored within the same session

**Decisions**
- D39 (superseded within this session): enrichment at preparation step 2 replacing the Finalizar stub; autocuración; no cap with the depth key redefined as an emergency brake; new inter-visit pause key; four extra company fields with the not-reported marker; log-only traceability
- D40: enrichment reverted after being measured as a bottleneck (~96% of a full run) with no downstream consumer — catalog keeps only id/name/normalized-name/profile link plus audit dates via an idempotent column-drop migration; future company attributes must be obtained selectively and off the offer critical path
- D41: data-fidelity batch — name-key rule keeps every character (lowercase + single spaces) with recomputation migration; descriptions stored with visible structure going forward (no re-capture of existing rows, user choice); new offers.empresa display column from the SDUi card's first usable candidate (no historical backfill, upsert never overwrites, catalog link stays empresa_id)
- D42: operations & performance batch — run-report and preflight CLIs; schema auto-init only when absent (normal runs skip migrations); jittered pacing via optional validated key (0 disables); unified event emitter with universally bounded evidence; persistence package preserving the public API verbatim; card parser extraction; inert legacy mapping entry and missing version row cleanup
- D43: deterministic Colombian-department pre-classification before the AI — fast-path table under strict normalized keys with optional country-suffix stripping, hits cached as successes, city-bearing texts deliberately left to the AI so the city component survives; prompt gains an all-caps observation (v2); legacy pending rows self-heal via lot b without HTTP
- D44: local classification model swapped to gpt-oss:120b-cloud (supersedes D35's model choice; routing mechanism unchanged) and PRM-006 promoted to v3 — confident-recognition guidance replaces the fear-based N/A rule, stricter output-contract phrasing (first character must be a brace), four worked examples serving the Americas expansion; fast path stays untouched as a zero-cost accelerator
- D45: session-35 follow-ups formalized during phase-5 closure — card-capture traspaso to Module 1, location column rename with data-model alignment, union-DISTINCT unique-offer total superseding the literal sum, pipe-in-title capture fix, config-driven deterministic AI sampling (temperature zero), autouse test-suite database isolation; no new code — official record of already-verified changes
- D46: location-alias fusion — catalog resolution exact-or-fuzzy in one country-filtered read per unseen tuple (RapidFuzz merge needing zero conflicts plus one real coincidence; sentinels never fuse alone; country-only and other-country excluded; fusions logged); optional validated threshold defaulting to 90 with 0 disabling only the fuzzy path; deterministic full-tuple aliases for known name variants consulted before the department table; live-data healing without backup
- Decisions from previous sessions remain in effect

**Status**
- Enrichment implemented ✅ (5.8) and reverted ✅ (5.9); data-fidelity batch closed ✅ (5.10); operations & performance program closed ✅ (5.11); department fast path closed ✅ (5.12); local model swap + instructions rewrite closed ✅ (5.13); phase-5 documentation closure closed ✅ (5.7 punto 2); location-alias fusion closed ✅ (5.14)
- **Phase 5 COMPLETE** — next: Phase 6 (Evaluation) planning
- ruff 0 · mypy 0 · pytest 552 passing across 83 files
- Single-branch state: `fase-5` merged into `main` (fast-forward) and deleted locally/remotely under explicit user authorization; six commits pushed during this session (enrichment feature; revert+history; data-fidelity+operations batches; location fast path + model swap; phase-5 documentation closure; alias fusion)

## Session 35 — 25/08/2026
`ses_fc9cdf2e5ffeMja2ZpSownJ82R` · `fase-5`

**Topics**
- First real orchestrated sequential run M1→M2 executed end-to-end through the official entry point: scheduled run closed completed with zero errors, 72 offers discovered and prepared, 4 duplicates detected
- Post-run database verification exposed modality pollution (63/72 offers stored raw guest-page text instead of canonical values); root causes traced to a header-dump fallback bug and raw-text canonization in preparation
- Corrections plan (A–F) approved and implemented in one task; a prior unreviewed commit attempting the same transfer was declared void by the user — card patterns reconstructed from documented evidence plus fixture DOM inspection
- Card-based capture added to the discovery adapter: SDUi paragraph classification extracts raw location and canonical modality (remoto/hibrido/presencial, N/R when absent), handling hybrid suffixes, noise segments and remoto-only segments; classic variant reads location via its own selector scoped inside the link element
- Capture node persists both columns; preparation stripped of all page-based location/modality extraction and column writes — classifies only the stored row text via PRM-006 and links catalog ids; guard test ensures module 2 never overwrites module 1-owned fields
- Column renamed `ubicacion_nombre` → `ubicacion`; idempotent migration ordered right after schema creation and before the Spanish rebuild so legacy populated values survive; regression test asserts survival across double init; live DB migrated with backup (72 rows preserved)
- Closure metric corrected: total offers counts each physical offer once via DISTINCT union over both success codes (literal sum had reported 76 for 72 physical); persistence counting helper extended to accept list filters (SQL IN)
- New official orchestrator entry point enabling direct module invocation
- Reviewer subagents unavailable all session due to provider rate limits/endpoint failures — task closed without external review under explicit user authorization
- Clean-run verification executed twice on an emptied database (no backup, user instruction): the first exposed follow-up findings, the second proved every fix end-to-end with zero errors and full catalog linking
- Root-cause investigation of the offer whose location had stored the company name: guest-page check confirmed LinkedIn DOES report a location; real card markup then inspected through a logged-in browser session
- Cause found: job titles containing a vertical bar broke the title-block filter (first pipe-segment truncated), shifting candidates so the company was read as the location; only that one card affected
- Title filter corrected to recognize multi-part title blocks by individual title segments, guarded so single-part candidates are never discarded; regression fixture built from the REAL captured card plus parametrized pipe-position cases and an anti-false-positive guard test
- Second clean run: the previously broken offer now stores Colombia/remoto; modality 100% canonical across all offers; every offer linked to company and location catalogs with zero unclassified-location warnings
- Location misclassification investigated (Pereira stored under the wrong department): four identical AI calls produced three different answers — sampling randomness because requests omitted model options and Ollama defaults to temperature 0.8
- Deterministic sampling added: configurable sampling options read from configuration for BOTH local and cloud AI routes; repeated identical calls now return identical correct answers (verified 3/3)
- Wrong catalog row corrected manually (Pereira → Risaralda)
- New defect discovered: running the test suite wrote junk rows into the production database (orphan sessions/events from node tests lacking isolation)
- Global automatic test isolation adopted: every test now runs against its own temporary database; verified identical production-database counts before/after a full suite run; junk rows cleaned
- Operating contract updated with the user's standing instruction: functional, jargon-free communication unless technical detail is expressly requested

**Decisions**
- Ownership transfer approved: location/modality capture belongs to Module 1 cards; Module 2 consumes stored text only (partially supersedes D29; ficha updates deferred)
- Empty-from-source convention: adapter writes `N/R` when the source card lacks data ("source did not report"); model defaults stay `N/A`
- `total_ofertas` semantics changed to physical-count DISTINCT union over {oferta_preparada, oferta_duplicada} (supersedes the literal preparadas+duplicadas formula; decision log entry pending)
- All official documentation updates (decision log, fichas as-built, DOC-13A, database-tables.md, AGENTS.md) deliberately deferred to the documentation-closure task
- User voided the initial "card without location" hypothesis with link evidence: real DOM showed the location present; the cause was the embedded bar in the job title
- Deterministic sampling approved for classification-type AI calls on both routes (temperature 0 via configuration)
- Company catalog empty-fields correction explicitly deferred again by user ("not yet")
- Test isolation adopted globally (automatic per-test temporary database) instead of per-test opt-in
- Prior unreviewed commit attempting this transfer declared void — not recovered nor referenced
- All official documentation updates (decision log, fichas as-built, DOC-13A, database-tables.md, AGENTS.md) deliberately deferred to the documentation-closure task

**Status**
- Sub-phase 5.7 punto 1 ✅ complete: traspaso validated with two clean orchestrated runs (74 offers, 0 errors, full catalog linking, union metric correct) plus three follow-up fixes (pipe-in-title capture, deterministic AI sampling both routes, test-suite database isolation)
- ruff 0 · mypy 0 · pytest 525 passing; production database verified untouched by the suite
- Sub-phase 5.7 punto 2 ⬜ pending: Phase 5 documentation closure (decision log entries for traspaso/union/rename/pipe-fix/sampling, as-built ficha notes M1/M2/orchestrator + entry point, DOC-13A, database-tables.md writers matrix, AGENTS.md status); empresas empty-fields fix deferred by user
- Single commit + push on `fase-5`; no merge

## Session 34 — 21/08/2026
`ses_fdafc2fd0ffexoEFYn60IjcuYQ` · `fase-5`

**Topics**
- Sub-phase 5.1 foundations implemented: all 11 consolidated D33 dependencies (schema to the M2 state, models, state machine, shared utility, config, location prompt)
- Migration chain: new guarded idempotent `_migrate_preparacion_d33` after D31; `_migrar_espanol_total` rebuild applies additions + 8-state CHECK on legacy DBs
- Anti-loss guards symmetric with D31: d31 no longer drops `eventos.id_oferta`, d29 no longer drops `ubicacion_nombre` (both re-added by D33; regression tests with double init)
- Prompt PRM-006 created (template C.9) and manually tested against the routed model: 3/3 valid JSON
- Live DB migrated via `init_db()` with backup; 136 offers preserved; second init no-op
- Sub-phase 5.2 implemented: Module 2 INICIO + candidate decision in a new preparation package mirroring discovery (context, lock, FIFO candidates, `sin_pendientes` motive slots for the closure node)
- FIFO candidate read added to the persistence layer; shared global lock reused across modules without touching Module 1 code
- Docs review caught config key drift in the retries validation (seconds-suffixed keys); fixed and regression-guarded against the official config
- Sub-phase 5.3 implemented: Preparación de ofertas node — two lots per pass (H1), guest httpx capture with browser headers, authwall multi-signal detection with session renewal, configurable retries/pauses/session lifetime
- Catalogs populated without SQL in the module: company upsert by normalized name; location classification via PRM-006 with Pydantic validation, per-text success-only cache, remote → N/R without row
- Reviewers: docs approved; code review MAJOR resolved as D36 plus four minors applied (ERR-07 warning parity, shared evidence truncation helper, sentinel guard for lot b, coverage tests)
- Sub-phase 5.4 implemented: Verificación de duplicidad node — 100% local RapidFuzz two-stage matching (exact index O(1) + fuzzy title/description thresholds same-company only), marker written on every evaluated offer, duplicates point to the oldest original
- Loop decision node ¿Quedan ofertas en 'descubierta'? — module's only I/O decision; bounded passes with revision_pendientes event always at close
- Code review found and fixed during build: validators returning empty string vs is-not-None checks, generic SQLite exceptions not wrapped as retryable flow codes, mutual intra-lot duplicate marking (smaller-id rule)
- Reviewers applied: anti-chain guard (ids marked this pass stop being candidates), context counters synced, public event helper reused by the decision node, transient-retry success test
- Sub-phase 5.5 implemented: Finalizar Proceso node — metrics from events with DISTINCT offer ids per success code, success events counted before the termination event, official motive/state table with concurrence as a success event
- Motive resolution priority: explicit from the orchestrator > pre-fixed on the context > derived from metrics plus had-candidates flag; failed metric queries degrade to default abort motive when nothing is pre-fixed
- Module orchestrator: INICIO routing closes every registered run (post-registration failures close as abort; contention route closes without touching the foreign lock), loop until the loop node signals finalize, structured database/config failures close as critical error while unexpected exceptions close as abort
- Run row now registered right after the database probe and before the lock attempt, making every termination closable including the contention route; single shared start timestamp for row and context
- Company enrichment stays a gate-only stub that logs when configured depth is positive (deferred H2)
- Build-time bug fixed: infinite loop from reading a non-existent decision field on the loop-node result (its signal is its state)
- Reviewers applied: mandatory closure step order restored (resources before lock release), orchestration coverage test for post-registration INICIO failure, negative enrichment-stub case, timestamp consistency pin
- Sub-phase 5.6 implemented: transversal scheduled-run node that validates a new orchestrator config section, registers its own run row with a single retry, launches each configured module's public flow in strict order and derives every module result from the database inside the execution window
- Module results attributed one-to-one by excluding already-derived runs (a silent second module never inherits the first one's run); pre-window runs ignored; missing closed run reported as not-started in evidence
- Summary events per module plus final summary event; module exceptions are recorded as failures without stopping the scheduled run; partial summary also recorded when the orchestrator itself aborts
- Scheduled run closes completed with success/failure metrics counted by event code; own unexpected failures close as aborted critical error after emitting the partial summary
- New additive read helper in the shared persistence layer returns the latest closed run since a timestamp with id exclusions and deterministic tiebreak
- Config section for the orchestrator: serie-only mode (parallel rejected at validation), module list discovery+preparation, default pause five seconds between modules
- Code review found and fixed during build: single-retry semantics were dead because database failures carry no retryable code (unconditional one-retry wrapper added, mirroring Finalizar Proceso), missing partial-summary rule on the abort path, exclusion ids initially filtered against the wrong column

**Decisions**
- P1 approved (5.4): offers without an extracted company are excluded from duplicate matching on both sides (only the verification marker)
- P2 approved (5.4): the loop node writes its pending-revision event only when it runs; a zero-candidates start short-circuits to Finalizar with the sin_pendientes motive
- Approved technical latitude (5.4): token-sort/partial-ratio fuzzers with inclusive thresholds, oldest-id tie-breaks and smaller-id-only matching, invalid thresholds abort as ERR-03, error_bd added as retryable flow code
- P1 approved: company enrichment implemented as gate-only stub (no network) — full enrichment deferred to future work
- P2-A approved and applied to already-implemented code: run registration moved before the lock attempt in INICIO so every registered run is closable; registration failure reports as ERR-05
- Approved technical latitude: motive priority explicit > context-prefixed > derived; degraded metrics keep an explicit/pre-fixed motive otherwise default aborto; INICIO routing by presence of run id; critical codes set {ERR-01, ERR-03, ERR-09} → error_critico, unexpected exceptions → aborto; event type map with concurrencia as suceso
- Ficha deviations left as as-built notes for phase documentation closure: single-retry semantics on steps 2/5 (mirror M1), DISTINCT metrics formula (D36 supersedes literal counting), registration at step 3b instead of step 6
- D38 approved: Spanish identifier exception extended to the transversal orchestrator package (ficha-mandated Spanish public names), same scope and limits as D37 (decision log v1.23)
- Approved defaults for the orchestrator config section: serie-only mode with parallel explicitly rejected, pause of five seconds between modules
- D36: `total_preparadas` at Finalizar Proceso counts DISTINCT offer ids via `contar_distintos` — lot (b) keeps re-emitting the success event for per-step traceability (user choice A); implementation lands in 5.5 (decision log v1.21)
- D37: Spanish identifier exception extended to `modules/preparation/` (node files/tests/run_context), same scope and limits as `modules/discovery/` (decision log v1.22)
- D35: `ai_routing.preparacion: "local"` with `ai_local.model: "gpt-oss:20b-cloud"` (Ollama-hosted via local proxy) — user choice avoiding cloud quota limits and undersized models; per-purpose model selection in `ia_service` deferred until a second local purpose exists (decision log v1.20)
- Config defaults approved for `preparacion:`: pausa 2 s, limite_vida_sesion 50, umbrales 90/85, max_pasadas 2, profundidad 0, retries block mirroring global
- Decisions from previous sessions remain in effect

**Status**
- Sub-fases 5.1 ✅ 5.2 ✅ 5.3 ✅ 5.4 ✅ 5.5 ✅ 5.6 ✅ (tracker); sub-fase 5.7 pending to close Phase 5
- Ruff 0 · mypy 0 · pytest 512 passing (+33 in 5.5, +18 in 5.6)
- Known limitation documented: lexicographic id ordering breaks past 10k offers per prefix (pre-existing, affects FIFO and duplicate original selection)
- Single commit + push on `fase-5`; no merge
- Next: sub-fase 5.7 — corrida real secuencial 1→2 + notas as-built y cierre documental de la fase

## Session 33 — 21/08/2026
`ses_fdba95353ffezwVG7roiPKaX2c` · `fase-5`

**Topics**
- Full project analysis requested: built vs remaining by phase, evaluation of what exists
- Phase 5 construction plan designed from the two technical sheets: 7 functional sub-phases (foundations → module nodes → transversal orchestrator → real sequential run + documentation closure), mirroring the proven Module 1 strategy with one difference — consolidated schema/shared dependencies go first as their own sub-phase
- MVP Execution Plan and tracker Phase 5 sections rewritten; obsolete generic task list replaced by the sheet-based plan
- Reviewer: docs-reviewer on the doc changes — 3 minor findings corrected (loop decision is the only decision with I/O, official node count preserved, unbacked backup claim replaced by case-by-case precedent)

**Decisions**
- Phase 5 build plan approved: foundations-first ordering; location-classification prompt built in foundations with manual test before integration; default company-catalog enrichment depth 0; generic Phase 5 content superseded
- Live DB backup for foundation migrations decided case-by-case at sub-phase start (project precedent) — no blanket rule
- Decisions from previous sessions remain in effect

**Status**
- Phase 5 build plan defined ✅ (tracker rows 5.1–5.7 pending); implementation not started
- Docs-only session: ruff/mypy/pytest n/a; suite unchanged (331 tests)
- Single commit + push on `fase-5`; no merge
- Next: sub-phase 5.1 — Foundations (schema, models, config, prompt)

## Session 32 — 20/08/2026
`ses_fe33fd2dfffeQS3bPEmnaiJW1h` · `fase-5`

**Topics**
- Phase 5 plan formally closed: 5 macro decisions + corrections + 7 gap mitigations + 6 optimizations approved as the M2 construction base
- Two technical sheets created as authoritative construction bases: Module 2 (Preparation) with 6 nodes + 11 consolidated schema migrations; transversal orchestrator with the scheduled-run node + 7 RNs
- Module 2 design: company capture via fresh-guest httpx session with browser fallback (offer pages capturable without login); deep catalog enrichment decoupled from the critical path as the last step of Finalizar (configurable depth); two-stage duplicate detection (exact title+company, then fuzzy description with RapidFuzz); in-memory caches for companies and locations; metrics by events (offer id_corrida never overwritten); `sin_pendientes` as a new run state for "nothing to do"; `fecha_ultima_verificacion` re-used as the verification marker with dual semantics (M1 dedup hit + M2 verification)
- Transversal orchestrator design: launches modules in pipeline order, never touches the global lock, result derived from the database (last run closed in the window since T0), module failure does not stop the scheduled run, dedicated row in `corridas` for the scheduled run, summary events with `campo=valor` evidence format, config-driven module list
- 11 consolidated migrations: `duplicada` state + `id_duplicidad`/`ubicacion_nombre`/`modalidad` on offers; `total_preparadas`/`total_duplicadas` + `sin_pendientes` on runs; `id_oferta` re-added on events; `ubicaciones` restructured to (city, region, country) tuple dedup with N/A components and no row for remote
- Documentation alignment: decision log v1.19 (D33, D34); DOC-13A v1.11 (entities, dictionary, version history); database-tables.md (writers per module, schema, events catalog); Appendix 5A (FNT retired, OFE → `ofertas_descubiertas`, module scope generalized); ficha M1 as-built note on the dual semantics of the verification marker; plan fase 5 with pointers to the two fichas; guide for new sources updated to reference the transversal orchestrator and the M2 ficha; README.md with explicit rows for the two new fichas
- Reviewer: docs-reviewer approval + 5 minor corrections (evidence format, exclusion-table clarification, run-state vocabulary precision, dual-semantics note, dual dependencia with shared utilities); all applied
- No code changes this session — documentation only, implementation pending approval

**Decisions**
- D33 (2026-08-20): Module 2 (Preparation) technical sheet approved — macro decisions D1–D5 (terminal `duplicada` state, `id_duplicidad` to original, module own run + new closure metrics, decoupled company capture and enrichment, two-stage duplicate verification); corrections; H1–H7; 6 optimizations; 11 consolidated schema migrations (decision log v1.19)
- D34 (2026-08-20): transversal orchestrator technical sheet approved — dedicated layer, scheduled-run row in `corridas`, module result derived from the database, module failure does not stop the run, `orquestador:` config section, no migrations
- Decisions from previous sessions remain in effect

**Status**
- Phase 5 plan closed ✅ (tracker 4.26); documentation aligned across 7 files (decision log, DOC-13A, database-tables, Appendix 5A, ficha M1, plan fase 5, adding-a-new-source) + README; the two new fichas remain as authoritative construction bases
- No code changes: ruff/mypy/pytest not executed; suite unchanged (331 tests)
- Single commit + push on `fase-5`; no merge
- Next: Module 2 implementation (cards task TBD: shared utilities, `modules/preparation/` structure, `modules/orchestrator/` skeleton, real sequential 1→2 run); MVP Execution Plan and tracker pending alignment
| 11 | 08/08/2026 | `ses_01c312689ffewPDBUxLcQIRb5L` | Sub-fase 4.3: Filter search + generic register implemented and validated (171 tests) |
| 10 | 08/08/2026 | `ses_01d9bc3d2ffe0OwXiVc3Mw8NWO` | Sub-fase 4.2: Ingreso flow implemented (3 nodes) and validated (152 tests) |
| 9 | 08/08/2026 | `ses_01ebcd885ffe7UB5IsfCrylV90` | Sub-fase 4.1: INICIO node implemented and validated (123 tests), reviewer fixes applied, branch `fase-4` created |
| 8 | 07/08/2026 | `ses_021c087e1ffePrh0h4O4Zzb4BY` | Module 1 preparation: discovery scaffold (run context + LinkedIn adapter), full validation passed, build ready |
| 7 | 07/08/2026 | `ses_0234a5a0effeWIUu0hsOpfvx3L` | Module 1 (Discovery): build strategy decided node-by-node; MVP Plan Phase 4 redefined as 13-node plan |
| 6 | 01/08/2026 | `ses_041587944ffe8Ve6EeplEa9Huo` | Session History restructured; custom sub-agents created |
| 1–5 | 23–30/07/2026 | — | Project foundation, Phases 0–3, SQLite migration, prompts retested |

## Session 31 — 19/08/2026
`ses_fe539fd2ffferuSLgK6EE88f5b` · `fase-5`

**Topics**
- Table rename D32 (user request): physical table `ofertas` → `ofertas_descubiertas` to disambiguate as later modules add their own offer tables; applied to schema, `secuencia_ids`, queries, discovery nodes, tests and docs
- Idempotent migration `_migrate_ofertas_descubiertas` runs first in `init_db` (before the schema creation loop, so `CREATE TABLE IF NOT EXISTS` never creates an empty duplicate); `secuencia_ids` row updated so the OFE sequence continues without collisions
- Scope limits honored: prefix `OFE`/`ultimo_numero`, index names (`idx_ofertas_id_externo`, `idx_ofertas_id_corrida`) and function names unchanged; prior decision references (D1/D4/D7/D8/D15/D16/D17/D29/D31/PMD-021) updated to the current naming, original wording preserved in git
- Live DB migrated in place via `init_db()`, no backup (user instruction; reversible rename + idempotent migration); verified 8 tables, 62 offers, `ofertas_descubiertas|OFE|62`, second run no-op
- Bugs found and fixed during tests: `secuencia_ids` UPDATE guarded by table existence (legacy fixtures), f-string prefix restored in `_upsert_ofertas_en`
- Reviewers executed: code-reviewer approved; docs-reviewer minor findings F-001/F-003 applied, F-002 pre-existing (missing v1.11 version row) left documented
- Docs updated: decision log v1.18 (D32), DOC-13A v1.10, ficha técnica as-built note, database-tables.md, AGENTS.md, tracker 4.25

**Decisions**
- D32 (user-approved): rename `ofertas` → `ofertas_descubiertas` with OFE prefix, indexes and function names unchanged; no backup of the live DB; prior decision references updated to the current naming
- Decisions from previous sessions remain in effect

**Status**
- 331 tests passing (2 new: rename + secuencia preserved, idempotency); ruff/mypy clean
- Live DB migrated and verified; all docs updated; reviewer findings closed
- Branch: `fase-5` · no merge
- Next: Phase 5 (Module 2 — Preparation), task 1: `modules/preparation/` structure (pending)

## Session 30 — 18/08/2026
`ses_fea037d3dffeR12tTJoQEt4IFq` · `fase-4`

**Topics**
- Q&A: how to search more job queries on LinkedIn — answered from the code: `sets_de_filtros` is a list, the orchestrator loops each set inside the same run (set N: search → capture → register → next set), per-source set iterator with reset on source change, dedup by `id_externo` across sets, per-set traceability via `indice_set`
- Rule explained: `indice_set` must be consecutive from 0 — a gap (0 and 2) aborts the run with ERR-01 "Set ausente"; a duplicate index is silently ignored; `max_ofertas_por_corrida` caps the whole run, not per set
- Option A implemented (document-only, user-approved): contiguous-index rule commented above `sets_de_filtros` in `config.yaml`; no code changes, config load verified (1 set, index 0)
- Second search set ("Operaciones manager") NOT added — pending user keywords/config

**Decisions**
- Option A approved: rule documented in config comments; no validation code (options B/C deferred)
- Decisions from previous sessions remain in effect

**Status**
- Config comment ✅ · no code changes (ruff/mypy/pytest n/a; suite remains 329)
- Session history committed in this /save; single commit + push
- Branch: `fase-4` · no merge
- Next: Phase 5 (Module 2 — Preparation), task 1: `modules/preparation/` structure (pending)

## Session 29 — 18/08/2026
`ses_feb0c7a29ffe0jOcMvPYiDv5wa` · `fase-4`

**Topics**
- D31 (user request, 4 points): schema cleanup + no-empty-field rule
- `eventos.id_oferta` dropped (reserved, never written; event-offer traceability out of Module 1 scope); `ofertas.identificador_origen` dropped (dead duplicate of the dedup key); `fuentes` table + `FNT` prefix removed (never populated — sources are config-driven, concept stays)
- `fecha_ultima_verificacion` untouched — exempted by explicit user instruction
- Fundamental rule established: no empty fields — `N/A`/`N/R` placeholders, never `''`/NULL; enforced at the persistence boundary (event fields: fuente/sesion/set index/evidence; offer fields: description/date/observations/company/location), schema `DEFAULT 'N/A'`
- `empresa_id`/`ubicacion_id` NULL → `'N/A'` (supersedes D4/D29 on those columns); `id_externo` excluded (would collide in dedup)
- `contar_distintos` treats `N/A` as empty — the termination event no longer inflates the closure metric `fuentes_procesadas` (behavior verified: still 1 for the historical run)
- Idempotent in-place migration (drop table + sequence row, guarded column drops, per-column backfill); live DB migrated 9→8 tables with backup, 62 offers preserved, zero empties in normalized columns
- 2 new tests (event/offer normalization to `N/A`) + extended coverage (`contar_distintos`, legacy-schema migration asserts the drops) → 329 passing
- Docs aligned: decision log v1.17 (D31), DOC-13A v1.9 (+ new §2.17 data management rules), database-tables.md (8 tables), ficha as-built note, tracker 4.24, AGENTS.md data rule
- Reviewers: code-reviewer approved (3 minors — migration docstring precision, test row-order robustness); docs-reviewer approved (no findings)

**Decisions**
- D31 (2026-08-18): schema cleanup + no-empty-field rule — dropped `id_oferta`/`identificador_origen`/`fuentes`, `N/A` placeholders at the persistence boundary for events and offers, `fecha_ultima_verificacion` exempted, `contar_distintos` excludes `N/A` (decision log v1.17)
- Decisions from previous sessions remain in effect

**Status**
- D31 ✅ (tracker 4.24); 329 tests passing · ruff 0 · mypy 0
- Live DB migrated 9→8 tables (backup preserved); 62 offers intact, trace normalized
- Session history + all session changes committed in this /save; single commit + push
- Branch: `fase-4` · no merge
- Next: Phase 5 (Module 2 — Preparation), task 1: `modules/preparation/` structure (pending)

## Session 28 — 17/08/2026
`ses_fef46d693ffeeJzOMWNCGCQb5s` · `fase-4`

**Topics**
- D30 (user-approved scope H+I+C+F): success-event traceability, capture duration, INFO logs, `total_sucesos` semantics
- Entry node writes `ingreso_exitoso` on success (suceso; evidence `sesion=<id>`, never credentials); search node writes `consulta_exitosa` only on success-with-offers (evidence `set=<indice> | total=<total_declarado>`); success-with-zero-offers and failures still typed by the register node — one event per search result, no duplicates (aligns the existing ficha contracts)
- Capture evidence `captura_completada` now includes `duracion_s=<N>` (monotonic elapsed of the capture block with retries); `total_sucesos` semantics documented (success events prior to closure; termination event written after counting, never counted — no behavior change)
- Default log level INFO in config; `LOG_LEVEL=DEBUG` override documented in `.env.template`; logging fallback default aligned to INFO (reviewer minor)
- 5 new tests (event written/not written in entry and search, `duracion_s` in evidence) + integration test asserting the 2 new codes, `duracion_s` and `total_sucesos == 4` → 327 passing
- Live verification run on clean DB (run numbered COR-0001 — id sequences reset with the DB): 98 offers, 0 errors; complete trace `ingreso_exitoso` → `consulta_exitosa` → `captura_completada` (`duracion_s=39`) → `ofertas_registradas`, `total_sucesos=4`; dates 98/98, raw text in `observaciones` 98/98, `empresa_id`/`ubicacion_id` NULL 98/98
- DB cleaned to 0 rows after verification (user decision) + VACUUM; backups preserved (pre-run state and post-run evidence)
- Docs aligned: decision log v1.16 (D30), ficha as-built note, DOC-13A v1.8, tracker 4.23, AGENTS.md (327)
- Reviewers: code-reviewer approved (3 minors — fallback INFO fixed, DOC-13A version row order fixed, dead guard nit accepted); docs-reviewer approved (2 format minors fixed: DOC-13A row order, tracker docs column)

**Decisions**
- D30 (2026-08-17): success-event traceability — `ingreso_exitoso`/`consulta_exitosa` emitted by the nodes aligning the ficha contracts (one event per search result; zero-offers/failures via the register node); `duracion_s` in `captura_completada` evidence; default log level INFO with `LOG_LEVEL=DEBUG` override; `total_sucesos` semantics documented as success events prior to closure (decision log v1.16)
- Decisions from previous sessions remain in effect

**Status**
- D30 ✅ (tracker 4.23); 327 tests passing · ruff 0 · mypy 0
- Production: fresh run COR-0001 — 98 offers, 0 errors, trace complete, `total_sucesos=4`
- Live DB clean (0 rows in traceability tables); backups preserved
- Session history + all session changes committed in this /save; single commit + push
- Branch: `fase-4` · no merge
- Next: Phase 5 (Module 2 — Preparation), task 1: `modules/preparation/` structure (pending)

## Session 27 — 17/08/2026
`ses_fef46d693ffeeJzOMWNCGCQb5s` · `fase-4`

**Topics**
- D28: SDUi card field extraction — hashed CSS classes per page, `<p>` text classification with fixed UI noise exclusion (Exp 9: 3 real pages / 75 unique cards, 75/75); company/location/relative date captured from the card
- D28: `fecha_publicacion` persisted as approximate absolute timestamp from "Publicado hace N <unidad>" (±1 h, month = 30 days) + raw text kept in `observaciones` (approved RN-03 deviation); declared total only from visible DOM text (excludes script/style/comments); production COR-0001 on clean DB: 89 offers, 0 errors, 89/89 populated (323 tests)
- User rejected the company/location outcome: raw strings in `ofertas` are not useful — the offer's relation to the catalogs must be their ids; populating catalogs out of scope
- D29: adapter reverted to enlace/título/fecha relativa + visible total (`_fecha_relativa_sdui`); classic company/location selectors removed; `empresa_nombre`/`ubicacion_nombre` columns dropped from `ofertas` (schema + live DB via idempotent `ALTER TABLE DROP COLUMN` migration); `empresa_id`/`ubicacion_id` stay NULL (D4), catalogs unpopulated (PMD-021); Offer model untouched (322 tests: 1 removed, 3 reduced)
- Live DB reset without run (user-specified) with backup; pytest runs re-polluted the DB (integration tests write the real DB with synthetic ids) → caught by docs-reviewer → final cleanup to 0 rows
- Docs aligned: decision log v1.15 (D29), DOC-13A v1.7, ficha (RN-03 + as-built notes + NOTA 4.4 inline marker), tracker 4.22, AGENTS.md (322), database-tables.md
- Verification run COR-0001: 99 offers, 0 errors, completed; `fecha_publicacion` 99/99 + raw `observaciones` 99/99; `empresa_id`/`ubicacion_id` 99/99 NULL; dropped columns absent from schema

**Decisions**
- D28 (2026-08-17): card field extraction — company/location/date via `<p>` classification, date as approximate absolute timestamp + raw text in `observaciones`, total visible-only (decision log v1.14; company/location part superseded by D29)
- D29 (2026-08-17): user-ordered revert — adapter keeps enlace/título/fecha relativa + visible total; `empresa_nombre`/`ubicacion_nombre` dropped from `ofertas` (idempotent migration); `empresa_id`/`ubicacion_id` NULL in MVP; catalogs not populated (out of scope) (decision log v1.15)
- Decisions from previous sessions remain in effect

**Status**
- D28 ✅ (tracker 4.21; company/location superseded by D29) · D29 ✅ (tracker 4.22); 322 tests passing · ruff 0 · mypy 0
- Production: COR-0001 — 99 offers, 0 errors, date 99/99, ids NULL 99/99, completed
- Live DB clean (0 rows in traceability tables); backup preserved
- Session history + all session changes committed in this /save; single commit + push
- Branch: `fase-4` · no merge
- Next: Phase 5 (Module 2 — Preparation), task 1: `modules/preparation/` structure (pending)

## Session 26 — 17/08/2026
`ses_fef46d693ffeeJzOMWNCGCQb5s` · `fase-4`

**Topics**
- DB reset: all records deleted without backup + VACUUM (sequences restarted); verification run COR-0001: 75 offers, 0 errors, 41 s, completed
- Filter bug: COR-0001 captured non-remote/stale offers — LinkedIn's new SDUi UI (`/jobs/search-results`) drops `f_WT` and `location` from the URL and honors only canonical date buckets; the old total span is gone (plain text "N resultados")
- Empirical investigation (Exp 1–7, authenticated browser): remote filter = `f_SAL=f_SA_id_225001:272001` (internal taxonomy id); 5 h window (`r18000`) not representable (rewritten to `r86400`); DOM selectors for chip verification documented; new-UI module URL pattern
- Decision D27 implemented: remote-only via `f_SAL` (presencial/híbrido → `filtros_no_aplicables`), canonical date buckets only (`r86400`/`r604800`/`r2592000`; config `r86400`; any other `r<N>` → `filtros_no_aplicables`), post-load DOM chip verification (remote radio `aria-checked='true'`, date via `label[for]` + sibling checkbox) + best-effort UI click fallback for missing filters + re-verification + `filtros_no_aplicables` on failure (never silent capture), total from "N resultados", pagination from the applied `page.url`; 10 new tests (308→318)
- Exp 8 (user-requested, before implementation): híbrido/presencial NOT representable in the new UI (taxonomy only contains the remoto segment; id stable across 2 searches × 2 sessions) — D27 validated empirically
- Live debug COR-0275 → root cause: real DOM uses `<input>` + `<label for>` SIBLINGS (not nested) and the date pill selector matched 2 elements (strict-mode); selectors corrected with verified evidence → COR-0344 OK (remote-only: 72 listed, 27 registered, 0 errors)
- Config default changed: `modalidad` removed from the filter set (captures all modalities); commented D27 instructions in `config.yaml` to re-enable remote → COR-0481 OK (no `f_SAL`, 89 listed, 17 new, 0 errors)
- Reviewers: code-reviewer (1 major fixed — non-canonical `r<N>` now hard-fails; minors deferred as future improvements), docs-reviewer twice, final close check CONFORME
- `temp/` investigation scripts cleaned (gitignored) → global `mypy .` clean (51 files)

**Decisions**
- D27 (2026-08-17): new SDUi UI filters — remote-only `f_SAL=f_SA_id_225001:272001`, canonical date buckets only, DOM chip verification + UI click fallback + `filtros_no_aplicables` on failure, total from plain text, pagination from applied URL; supersedes D18/D20/D26 (documented in decision log v1.13)
- Default config: no modality filter (all modalities captured); remote reactivable by uncommenting (documented in `config.yaml`, ficha note g)
- Decisions from previous sessions remain in effect

**Status**
- D27 ✅ (tracker 4.20); 318 tests passing · ruff 0 · mypy 0 (global, `temp/` cleaned)
- Production: COR-0344 (remote-only) + COR-0481 (all modalities) — 0 errors, verification passed without fallback
- Session history + all session changes committed in this /save; single commit + push
- Branch: `fase-4` · no merge
- Next: Phase 5 (Module 2 — Preparation), task 1: `modules/preparation/` structure (pending)

## Session 25 — 14/08/2026
`ses_ffd4eef78ffeLdakkTRbtGuLdu` · `fase-4`

**Topics**
- Functional E2E test of Module 1 approved and run (2 real runs): COR-2068 (107 offers captured, full capture flow) + COR-2069 (108 captured, 1 new — dedup by `id_externo` verified live); DB: 110 offers, 110 distinct links, lock empty; backup `job_search.db.bak_20260814_203224`
- "Modo producción" instrumented test (temporary script outside the repo observing `Page.goto`): COR-2070 (evidence of ALL navigated URLs; one transitory ERR-07, 0 offers) + COR-2071 pure production (107 captured, 0 new, 0 errors, completed); backup `..._modo_produccion`
- User's manual LinkedIn evidence analyzed (clean search vs panel filters vs 24h window): `origin`/`referralSearchId`/`f_SAL` are UI/session artifacts — the user has no selectable salary filter; LinkedIn injects `f_SAL` when rebuilding panel state; the "18 ofertas" label vs the real set (~105-107) is LinkedIn's cosmetic total (D18 confirmed in practice); module URLs are canonical and reproducible, immune to account-session filters
- The 3 pre-capture loads explained: 2 identical `/jobs/search` loads = transient post-login failure + D23 retry; 3rd+ = capture pagination (`search-results?start=N`) — LinkedIn serves max 25 cards per page, the real set cannot load "at once"
- Decision D26 approved and implemented: `apply_filters` navigates straight to `/jobs/search-results` (SDUi list) with `wait_until="commit"` — one search load + direct pagination; tests updated (`URL_RESULTADOS`, FakePage records `wait_until`, new reuse test: apply_filters + capture_batch = 1 goto), 308 tests, ruff/mypy clean
- Production verification COR-2140: login → 1× search-results (25 real offers) → start=25/50/75/100/105, no retries, 0 errors, completed (dedup: 0 new)
- Reviewers: code-reviewer approved (1 minor fixed: line >100 chars), docs-reviewer approved (D26 registered, ficha as-built, tracker/AGENTS updated)
- Docs applied with user approval: D26 + decision log v1.12, tracker 4.19, ficha técnica as-built note, AGENTS.md (status + 308)

**Decisions**
- D26: search entry straight to the `/jobs/search-results` SDUi list with `wait_until="commit"` — removes the transient post-login `fuente_inalcanzable` retry duplication and the unreliable-total `/jobs/search` intermediate; one search load + direct pagination (verified by COR-2140)
- Decisions from previous sessions remain in effect

**Status**
- Functional E2E ✅ (COR-2068/2069) · modo producción ✅ (COR-2070/2071) · D26 ✅ (tracker 4.19); 308 tests passing · ruff 0 · mypy 0
- Discovery behavior confirmed against real evidence: only configured filters applied, results reproducible, real set captured in full (105-107 offers)
- Docs: decision log v1.12 (D26), tracker 4.19, ficha as-built note, AGENTS.md updated
- Branch: `fase-4` · no merge
- Next: Phase 5 (Module 2 — Preparation), task 1: `modules/preparation/` structure (pending)

## Session 24 — 14/08/2026
`ses_ffd4eef78ffeLdakkTRbtGuLdu` · `fase-4`

**Topics**
- Improvement plan shown again to the user (recovered from the local OpenCode DB); Lote D (P4 items 13–18) approved as the last lot with all recommendations, one pass
- Lote D (P4): `EstadoCorrida` reduced to the D4 vocabulary (`en_ejecucion`/`completada`/`sin_fuentes`/`abortada`; `error`/`concurrencia` removed — test-only); `Corrida` extended with the 6 closure fields + `extra="forbid"`; `actualizar_corrida` now validates with the model before writing (D23 deferral closed); `registrar_corrida` callers unaffected
- Value validation replacing dead `hasattr` checks (ingreso/busqueda; ERR-02 contract preserved); `RunContext.marcar_cambio_de_fuente` public + idempotent (busqueda no longer mutates privates; 2 new tests)
- Orchestrator: `_ejecutar_nodo` helper + structural `_ResultadoNodo` Protocol (estado/descripcion/decision), 11 call sites unified; `ResultadoRegistro` gained `decision: str = ""`; flow order/motivos verified identical
- Credentials resolved once via `_resolver_credenciales` (was 1 read per attempt; `_obtener_credenciales` deleted); inline imports (`json`/`loguru`) moved to top of ia_service; `logging.logs_path: "logs"` in config with fallback in `_logs_path`
- Reviewers: code-reviewer approved (3 nits non-blocking), docs-reviewer compliant — enum now matches D4 exactly; F-001/F-002 drift corrected via as-built notes (ficha states, DOC-13A attributes + state domain), F-003 kept
- Docs applied with user approval: D25 + decision log v1.11, tracker 4.18, AGENTS.md (status + 307), ficha técnica as-built note, DOC-13A §2.14/§5.5.14

**Decisions**
- D25: Lote D — 6 items (13–18); `_resolver_credenciales` `None` double meaning disambiguated by caller; `marcar_cambio_de_fuente` placement in RunContext approved despite module docstring wording
- Decisions from previous sessions remain in effect

**Status**
- Lote A ✅ (tracker 4.15) · Lote B ✅ (4.16) · Lote C ✅ (4.17) · Lote D ✅ (tracker 4.18); 307 tests passing · ruff 0 · mypy 0
- P4 improvement plan fully closed; Phase 4 complete & recorded as-built
- Session history + all session changes committed in this /save; single commit + push
- Branch: `fase-4` · no merge
- Next: Phase 5 (Module 2 — Preparation), task 1: `modules/preparation/` structure (pending)

## Session 23 — 14/08/2026
`ses_ffd4eef78ffeLdakkTRbtGuLdu` · `fase-4`

**Topics**
- Improvement plan recovered from the local OpenCode DB (not in the repo): priorities P0–P4 with lotes A ✅ / B ✅ / C ✅ / D pending; plan presented and Lote C approved by the user
- Lote C (P3): 6 duplication unifications, pure refactor with zero contract change
- `ahora()` + `FORMATO_TIMESTAMP` + `TIPOS_ACCESO` as public helpers in shared utilidades, replacing 7 duplicated implementations (persistence `_now`, run_context/inicio/finalizar/control_fuentes/captura/registro `_ahora`); shadowed locals renamed to `marca` in persistence
- `escribir_evento_seguro` in persistence replacing the 5 node wrappers (inicio, captura, control_fuentes, registro, finalizar); RN-04 preserved (failure logged, never aborts); 25 test patches retargeted to the node-imported name (patches against the persistence source would not intercept) + write-fail test re-patched at the real call site + 2 new helper tests
- `_enviar` in ia_service unifying `_send_local`/`_send_cloud` (thin `@retry_decorator()` wrappers kept public; LLM-001..003 intact)
- Capture policies merged via `{**global, **por_fuente}` (identical defaults); adapter status check unified in `_revisar_estado`; failure `SearchResult` built once via `_resultado_fallo` in busqueda
- Discarded scope documented (structural source validation INICIO↔RunContext, `_es_obsoleto` mirror) + cosmetic message changes (capture empty-page evidence, LLM-003 local capitalization, unified failure log)
- Reviewers: code-reviewer approved (P3 cosmetic only), docs-reviewer 0 contract violations; F-003 pre-existing drift documented per recommendation (termination event written in a single attempt; retry NOT implemented)
- Docs applied with user approval: D24 + decision log v1.10, tracker 4.17, AGENTS.md (status + 302 + `shared/utilidades.py` in the Spanish exception list), ficha técnica as-built note

**Decisions**
- D24: Lote C — 6 duplication unifications (items 7–12 of the P3 plan); discarded scope; observable cosmetic changes; F-003 termination-event retry drift documented (not implemented)
- Decisions from previous sessions remain in effect

**Status**
- Lote A ✅ (tracker 4.15) · Lote B ✅ (tracker 4.16) · Lote C ✅ (tracker 4.17); 302 tests passing · ruff 0 · mypy 0
- Lote D (P4 consistency/robustness, incl. EstadoCorrida P4-13) pending planning
- Session history + all session changes committed in this /save; single commit + push
- Branch: `fase-4` · no merge
- Next: Phase 5 (Module 2 — Preparation), task 1: `modules/preparation/` structure (pending)

## Session 22 — 14/08/2026
`ses_ffd4eef78ffeLdakkTRbtGuLdu` · `fase-4`

**Topics**
- Lote A plan presented and approved by the user (P0 leak fix + P1 performance improvements), including the 3 design decisions (whole-lot retry, public resource closure reused by the orchestrator, wrapper on the batch core)
- Playwright resource leak fixed: context now carries the browser and Playwright instance, assigned on successful platform entry and cleared on definitive failure/reset; the closure node exposes a public resource-closing function (page → browser → instance, idempotent) reused by the orchestrator when switching sources — the previous browser context is no longer leaked
- Batch persistence: whole lot upserted in one connection (dedup by external id incl. intra-lot duplicates, per-row failures logged with run/external ids and non-aborting); single-offer call became a thin wrapper that raises a descriptive persistence error on invalid rows (was a misleading index error)
- Retry policy: 2 attempts of the whole lot, only on connection/transaction exceptions; per-row failures are data errors and are not retried
- Generated ids captured via RETURNING without an extra select
- Closure metrics computed by SQL counts (empty column values excluded) replacing full-table reads into Python
- 10 new tests (batch upsert, empty lot, invalid single row, SQL counts with/without filters, resource assignment/reset, metrics with real DB, session closed on source switch); bugs fixed during implementation: mocked tuple unpacking, intra-batch dedup, call-args introspection, missing pytest import
- Reviewers: code findings all fixed (descriptive error on invalid row, traceability in failure log, 2 missing tests); docs finding resolved: batch persistence derogates the ficha per-offer note, now registered as an approved decision
- Docs applied with user approval: new decision entry, ficha as-built notes (capture node + global, rules/validations/step updated), tracker sub-phase 4.15, AGENTS.md test count 292
- Lote B: unified retry helper `ejecutar_con_reintento` (config-driven backoff, `al_fallo_final`/`al_error_interno`/`al_reintento` callbacks, dispatch by `codigo_motivo` only) replacing the 3 duplicated node loops and the test-only `retry_conditional`; ingreso reuses the Playwright instance between attempts, closes page/browser via callback, stops the instance only on definitive failure
- `escribir_lote` deleted (no production callers); Pydantic validation before writes: `EventoAlmacen`/`Corrida` in persistence, `AuditoriaSesion` in the session audit (non-aborting); `registro.py` passes `fuente_id=""` (None rejected); `max_attempts=0` keeps ERR-09 in captura; `actualizar_corrida` NOT validated (deferred to Lote D, P4-13)
- Tests: 5 retry tests migrated + 8 new (callbacks receive exc/intentos, backoff exponential + `max_wait` cap asserted, both `max_attempts=0` routes); patches moved to `shared.retry.*`; 2 batch tests removed; 2 validation tests added; reviewer P2 fixed (`code` fallback removed from dispatch — non-flow exceptions fall to error interno like the old except branches)
- Docs applied with user approval: decision log D23 + v1.9 (v1.8 row repaired), tracker 4.16, AGENTS.md status + test count 300, database-tables.md mention of `escribir_lote` removed

**Decisions**
- D22: batch persistence and retry in one connection (derogates ficha NOTA 4.4 "persistencia por oferta"); SQL closure metrics; RETURNING ids; Playwright resources tracked in context with public closure reused by the orchestrator on source switch
- D23: unified retry helper `ejecutar_con_reintento` (replaces `retry_conditional` + 3 node loops); `escribir_lote` deleted; Pydantic validation on writes; notes F-004 (ficha per-node retryable codes vs global union, pre-existing) and F-005 (ERR-09 edge restored) documented
- Decisions from previous sessions remain in effect

**Status**
- Lote A ✅ (tracker 4.15) · Lote B ✅ (tracker 4.16); 300 tests passing · ruff 0 · mypy 0
- Lotes C (P3 duplication unifications) and D (P4 consistency/robustness, incl. EstadoCorrida P4-13) pending planning
- Session history + all session changes committed in this /save; single commit + push
- Branch: `fase-4` · no merge
- Next: Phase 5 (Module 2 — Preparation), task 1: `modules/preparation/` structure (pending)

## Session 21 — 14/08/2026
`ses_0002228fbffeOK2V1m5PaeYAiK` · `fase-4`

**Topics**
- Session resumed with the LinkedIn filter investigation (user report: "Últimas 24 horas" label with 5 h config); user authorized executing the 4 pending items left open: clean temp artifacts, document the finding, observability hardening, robust login fallback
- Empirical filter test conclusions: `f_TPR` windows (r18000=11, r43200=17, r86400=58, none=368) and `f_WT=2` (19→11 offers) DO filter correctly; LinkedIn labels any `r<N>` window as "Últimas 24 horas" and job cards embed hardcoded accessible text — cosmetic platform limitation; config `r18000` (5 h) kept unchanged
- Observability: successful search results now carry `evidencia_acotada` with the applied URL + declared total (persisted by the generic event node) and `apply_filters` logs INFO "Busqueda aplicada"
- Validation: `fecha_publicacion` format enforced as `r<N>` in the adapter, malformed values → official `filtros_no_aplicables` (adapter-level per filter-applicability rules, not a UI-bucket catalog which would reject working values)
- Login fallback hardened: fallback submit click is best-effort (5 s, swallowed) followed by the 30 s detached wait — slow form detach no longer turns a real successful login into a false rejection
- Fixed own shadowing bug caught by the new evidence test (loop variable reused the URL parameter); renamed to `enlace_oferta`
- 4 new adapter tests (slow-detach login, malformed date rejected, `r<N>` accepted with exact URL, evidence url+total); temp artifacts deleted
- Docs: decision log v1.7 (D18–D21), tracker sub-fase 4.14, AGENTS.md status + 282 tests; both reviewers approved, one doc attribution fixed (D20 test count)

**Decisions**
- D18: LinkedIn labels `f_TPR` windows with the nearest UI bucket; the filter itself works — label is cosmetic, config `r18000` confirmed and kept
- D19: successful `SearchResult` carries the applied search URL + declared total as evidence (events + logs become diagnosable)
- D20: `fecha_publicacion` format validation `r<N>` in the adapter (not a UI-bucket catalog); malformed values → `filtros_no_aplicables`
- D21: login fallback tolerant to slow form detach (best-effort click + 30 s detached wait)
- Decisions from previous sessions remain in effect

**Status**
- 4 pending items ✅ (tracker 4.14); filter investigation closed, observability + validation + login hardening done
- Ruff 0 · mypy 0 · pytest 282/282 (278 + 4 new)
- Session history + all session changes committed in this /save; single commit + push
- Branch: `fase-4` · no merge
- Next: Phase 5 (Module 2 — Preparation), task 1: `modules/preparation/` structure (pending)

## Session 20 — 12/08/2026
`ses_00927e803ffeXTR04EkYYKzmTV` · `fase-4`

**Topics**
- Project-wide review lots, approved and executed one by one with plan + impact first: Lote 1 (quick wins), Lote 2 (Spanish catalog), Lote 3 (persistence performance), Lote 4 (test quality + last cleanups)
- Lote 1: test suite made ~10× faster by neutralizing retry sleeps; write-only run-context state removed; dead fixtures deleted; closure node queries metrics once; dead params/fields removed
- Lote 2: every persistence function renamed to Spanish with English aliases dropped (catalog D7/D8 complete); known inert column default documented, not migrated
- Lote 3: offer upsert rewritten to a single connection (was up to 3 per offer); 3 non-unique lookup indexes created idempotently in DB init (dedup + closure metrics)
- Lote 4: vestigial decision node retired from code, orchestrator, tests and ficha (constant answer since list-based capture) — flow now 12 nodes
- Lote 4: session close delegated to the documented adapter contract instead of direct page close; tests verify the contract
- Lote 4: dedicated config tests added (configuration layer was untested); full-flow integration tests added running real nodes with only adapter/config/Chromium launch simulated
- Docs updated per lot: decision log through v1.6 (D14–D17), tracker 4.10–4.13, ficha as-built notes, MVP plan as-built annotations, AGENTS.md test counts

**Decisions**
- D14: Lote 1 quick-win cleanup — write-only context state removed, dead params/fixtures, single metrics query, fast suite
- D15: Spanish catalog completed for persistence function names; known inert column default documented, not migrated
- D16: persistence performance — single-connection offer upsert, 3 non-unique indexes in DB init
- D17: Lote 4 — vestigial "¿Quedan ofertas…?" node retired (option a: code + ficha re-edited), session close via `close_session` contract, config + integration tests added
- Review findings D3/D4 (private-coupling and weak assertions) not executed by recommendation
- Decisions from previous sessions remain in effect

**Status**
- Lotes 1–4 ✅ (tracker 4.10–4.13); all executed review findings A1–C2 and E1/E2 closed
- Ruff 0 · mypy 0 · pytest 278/278 (~3.3 s)
- Lote 3 committed + pushed; Lote 4 + session history committed in this /save
- Branch: `fase-4` · single commit + push, no merge

## Session 19 — 11/08/2026
`ses_00f57a514ffeUyBVloqdH07g2W` · `fase-4`

**Topics**
- Spanish naming catalog (D7/D8): word-boundary English→Spanish rename of persistence fields, config keys, and discovery identifiers across models, persistence, state machine, retry, decision engine, config, discovery nodes/adapters/orchestrator/run context, and tests
- Exceptions: error-context attributes keep English names; `linkedin`→`perfil_linkedin` and `size`→`tamano` applied manually only (unsafe for blind replacement)
- DB migrated with total Spanish migration: per-table rebuild with explicit column map, estado CASE translation, sesiones id backfill, idempotent; backup preserved, 7 offers intact
- Offer states in Spanish (`descubierta`…`finalizada`) including DB CHECK constraint; timeout codes renamed to `tiempo_agotado_*`
- Docs aligned: D7/D8 registered (decision log v1.1), data model DOC-13A v1.5 with Actual-name annotations, module ficha as-built note, MVP plan profile YAML and criteria table, tracker 4.7, AGENTS status
- Docs-reviewer approved; 4 minor findings fixed (annotations, plan YAML, errors.py exception list, C5 header)

**Decisions**
- D7: Spanish naming catalog applied mechanically (word boundary) to code, config, and tests, with documented exceptions
- D8: offer states and timeout codes use Spanish vocabulary, superseding the C5 `discovered` value
- DB migrated via total Spanish migration (idempotent, explicit mapping, CASE), backup kept
- Decisions from previous sessions remain in effect

**Status**
- Spanish naming migration D7/D8 ✅ (code + DB + docs)
- Ruff 0 · mypy 0 · pytest 243/243
- Branch: `fase-4` · /save single commit + push, no merge

## Session 18 — 11/08/2026
`ses_011dd31a8ffe0sUJfx0l66OpUJ` · `fase-4`

**Topics**
- Documentation authority clarified: only primary docs are consultable when building (module ficha, decision log, data model, prefix catalog, plan, tracker, AGENTS.md)
- Docs-reviewer inefficiency diagnosed: two heavy skills loaded, full-implementation inspection, checks against retired docs, inflated output template
- Physical deletion of all non-primary documentation: design docs and retired docs removed from the repo (history preserved in git)
- Authority model simplified in AGENTS.md: single consultable category; generic close gate against primary docs replaces the DOC-01 sync gate
- Docs-reviewer optimized: one lightweight skill, git-diff scoped inspection, primary-docs-only checks, CONFORME output in ≤5 lines when no findings
- Review skill streamlined: precedence = primary docs, 3-step workflow, conditional report template
- README links updated to living documents only
- Functional inputs (requirements, decision model, data flow, error catalog, user profile) removed: future module fichas will be rebuilt from module-1 ficha + decision log + data model
- Workflow audit (checks, implementation, documentation, closure skills): read/update scope verified aligned with primary docs only; project-documentation skill adjusted to forbid consulting deleted docs and over-reading

**Decisions**
- Only primary documentation remains consultable; all non-primary docs deleted physically, never to be consulted again
- Future module fichas (2–5) are built from module-1 ficha + decision log + data model, without prior functional inputs
- Closure documentation review limited to changed files and primary documents, with conditional output
- Documentation consultation across all workflow skills scoped to primary documents only, minimum required by the task

**Status**
- Documentation depuration + reviewer optimization + workflow alignment ✅ (no code changes: ruff/mypy/pytest n/a)
- Branch: `fase-4` · /save single commit + push, no merge

## Session 17 — 10/08/2026
`ses_0133020ecffeN4R4bi4Y7MXDAF` · `fase-4`

**Topics**
- Deep-debug of LinkedIn 2026 login: page renders two copies of the form — invisible SSR residual (`autocomplete="username"`, 0×0) vs real React one (`autocomplete="username webauthn"`, visible); exact-attribute CSS selector matched only the residual → 30s fill timeout; authwall/modal hypothesis was a false lead
- Direct login: authenticated sources go straight to the Spanish login URL (search URL no longer visited first); selectors `[autocomplete^='username']:visible` + Enter submit with click fallback; form-detach wait; entry criterion verified by HTML polling tolerant to in-flight navigation
- Entry criterion switched from `global-nav` to `voyager` (feed no longer renders `global-nav`; SSR shell arrives first, `voyager` ~3.5s later)
- Multi-variant listing/detail parsing: per-page exclusive CSS variants (2026 job-card → generic anchor → classic base-search-card), href dedup, title/description fallbacks; new fixtures + adapter tests
- Two pre-existing findings fixed: session-audit insert (generic writer requires `id` column; schema migrated idempotently with id=session_id) and closure metrics (happy path wrote no events, so finalize counts showed 0/0)
- Capture success now writes `ofertas_registradas` success event; functional run COR-1957: session audit persisted, events traceable, closure `total_sucesos=2 | fuentes_procesadas=1`
- Re-visit dedup verified: re-seen offers become UPDATEs, so run-level `total_ofertas` counts only newly registered offers (7/7 of COR-1839 duplicated in COR-1957 → 0 new by design)
- Tests: 240 passing (persistence migration, `write_row` on sesiones, register-success event tests added)

**Decisions**
- LinkedIn 2026 login selectors: prefix match + `:visible`, Enter submit with click fallback — never exact-attribute match on username
- Entry success for authenticated sources: HTML polling for `voyager` on the feed, tolerant to navigation; direct login URL instead of visiting search first
- Parsing variants resolved per page by exclusivity (one variant per page, selectors never mixed)
- `sesiones` schema aligned with the generic writer (`id` PK + creation dates); migration copies legacy rows with id=session_id; session audit passes the explicit id
- Happy-path capture writes `ofertas_registradas` so closure metrics reflect the run; degraded/partial lote events unchanged
- Run `total_ofertas` counts only newly registered offers by design (upsert dedup); no semantic change

**Status**
- Login SSR fix + multi-variant parsing + both pre-existing findings ✅ (validated on real DB via COR-1957)
- Ruff 0 · mypy 0 (46 files) · pytest 240/240
- Branch: `fase-4` · /save single commit + push, no merge

## Session 16 — 10/08/2026
`ses_0133020ecffeN4R4bi4Y7MXDAF` · `fase-4`

**Topics**
- Sub-fase 4.5 implemented: terminal node Finalizar Proceso + orchestrator connecting the 13 nodes + module entry point (python -m)
- Persistence additions only (no other files touched): `actualizar_corrida`, `liberar_bloqueo` alias, 6 closure columns on `corridas`, idempotent migration
- Closure semantics: state mapping by motivo, metrics query with zero fallback, single-retry on update, best-effort event/resource-close/lock-release
- Custom Playwright closing (page/browser/instance attributes) without touching existing adapters
- Orchestrator loops: sources × filter sets, session close between sources, abort with motivo on any node error; INICIO non-ok exits without Finalizar
- Unit tests: 17 node + 13 orchestrator (mocks, temp DB end-to-end, order-of-calls tracking); full suite 229
- Read-only audit by user request: CONFORME with minor findings (metric query duplicated on close, user-specified deviations vs ficha pending D4 documentation)
- Reviewer sub-agents: code-reviewer returned empty twice; docs-reviewer flagged ficha deviations later confirmed as user-specified

**Decisions**
- Estado vocabulary defined by user: completada/sin_fuentes/abortada (reconciles the session 9 pending item; deviations vs ficha/doc to be documented as D4 in a later session)
- Termination event: tipo suceso only on completada, error otherwise; INICIO non-ok (error/concurrencia) prints and returns without Finalizar — both per user spec
- Documentation updates (tracker/ficha/DOC-13A) deferred by user during implementation; /save applies only session history + tracker status
- No commit was made during implementation; /save authorizes the single closing commit and push on `fase-4`

**Status**
- Sub-fase 4.5 ✅: closure node + orchestrator implemented and audited CONFORME
- Ruff 0, mypy 0 (44 files), pytest 229/229
- Branch: `fase-4` · committed & pushed via /save, no merge
`ses_01823c05affeFQbFrKubp332mC` · `fase-4`

**Topics**
- Skills inventory: project skills (implementation, docs, debugging, review, testing) vs global skills (design, SEO, data validation)
- Reviewed review-against-documentation skill: purpose, workflow, review categories, output format
- Use scope of the skill: closure/verification stage via the documentation reviewer agent
- Full rewrite of the skill: applicability, required inputs, documentation precedence hierarchy, 7-step workflow, finding categories, severity levels, mandatory rules, review output template
- /save detection of unexpected worktree changes (report deletions, DOC edits) — user authorized committing everything

**Decisions**
- Review skill now defines documentation precedence order, structured findings/severity taxonomies, and a fixed review report template
- Restricting the skill to the docs-reviewer agent only: discussed, investigated, pending user confirmation (not applied)
- /save session: full worktree commit authorized by user

**Status**
- Session: skill rewritten ✅ · no code changes (ruff/mypy/pytest n/a)
- Skill-agent restriction: ⬜ pending decision
- Branch: `fase-4` · /save full commit authorized

## Session 14 — 09/08/2026
`ses_01bcc78adffemcqFEiZxT52Eli` · `fase-4`

**Topics**
- Context recovery: AGENTS.md, MVP Plan, tracker, session history
- Sub-fase 4.4 implementation: capture nodes (`capturar_ofertas`, `registrar_ofertas`, `quedan_ofertas_por_capturar`, `quedan_sets_por_aplicar`)
- `upsert_oferta` by `id_externo_url` + `timestamp_ultima_verificacion` (+ `read_table` filters + migration)
- First upsert commit reverted on request; reimplemented with full test coverage (22 node tests)
- Second audit: FK constraint failed on capture (empty `empresa_id`/`ubicacion_id` referencing missing catalogs)
- Post-audit fixes: FK-free `ofertas` schema, `empresa_nombre`/`ubicacion_nombre` columns, idempotent migration, 5 upsert integration tests
- Docs aligned: ficha técnica NOTA + RN-02/03, DOC-13 decision D4, DOC-13A v1.4, tracker 4.4 ✅, AGENTS.md update
- Fixed pre-existing migration bug on real DB (obsolete Spanish columns)

**Decisions**
- Dedup by `id_externo_url` stays in Module 1 (upsert); documented as approved deviation over 1.0 spec
- `empresa_id`/`ubicacion_id` stored NULL in MVP; raw adapter strings kept in `empresa_nombre`/`ubicacion_nombre`; `fuente_id` stores `source_id` with no FK constraint (decision D4 2026-08-09)
- Schema migrations copy only columns present in target schema (intersection) to survive legacy DBs

**Status**
- Sub-fase 4.4 ✅: capture/registration nodes validated with audit fixes
- Ruff 0, mypy 0 (39 files), pytest 199/199
- Branch: `fase-4` · committed, no merge

## Session 13 — 08/08/2026
`ses_01be77680ffeuyoKct4Qrfx1GG` · `fase-4`

**Topics**
- Context recovery and current status summary
- Remote sync of last commit on `fase-4`
- Investigation: no documented rules for commit/push from `/save`
- Drafted general, phase-independent git commit + push section for `/save` command
- Added section to `/save` command file and pushed to `fase-4`

**Decisions**
- Place general git commit + push guidance in `/save` command (not AGENTS.md/elsewhere), close to action it governs
- Keep merges and branch pushes out of `/save`; governed by AGENTS.md Version Control rules
- Section covers: scope verification, excluded files, explicit staging, review of staged diff, conventional English commit message ≤ 72 chars, single commit per closing, push of commit with no force-push

**Status**
- Branch: `fase-4` · `/save` section added, committed & pushed (no merge); no code changes (ruff/mypy/pytest n/a)

## Session 12 — 08/08/2026
`ses_01c089ce2ffe9MvQT4F1pC0MJN` · `fase-4`

**Topics**
- Context recovery: AGENTS.md, MVP Plan, tracker, session history
- Deep audit of Sub-fase 4.2 across 11 verification sections (structure, resource lifecycle, credentials, session_id, retries, decision node, event registration, tests, cleanliness, suite, commit/tracker)
- Critical finding: credential key mismatch between node and adapter (refs vs canonical keys)
- Minor finding: playwright `finally` guard depended on shared context state (multi-source leak risk)
- Post-audit fixes implemented and validated

**Decisions**
- Credential mapping convention (MVP): `credenciales_referencia[0] → username`, `[1] → password`
- Adapter consumes canonical keys; node performs mapping (Option A over changing adapter)
- Playwright lifecycle tracked by local `playwright_activo` flag instead of context state, preventing multi-source leaks
- On success, local flag reset so `finally` does not close session intended for subsequent nodes

**Status**
- Sub-fase 4.2 post-audit fixes applied and validated
- Ruff 0, mypy 0 (37 files), pytest 172/172
- Branch: `fase-4` · committed, no merge

## Session 11 — 08/08/2026
`ses_01c312689ffewPDBUxLcQIRb5L` · `fase-4`

**Topics**
- Sub-fase 4.3 complete: search nodes ("Aplicar filtros básicos", "¿Se encontraron ofertas?", "Registrar suceso/error")
- Set iteration (indices) with reset and marking as processed when source changes
- Adapter search with filters
- Conditional retries (source unavailable / timeouts) and retry counts
- Search_result contract fixing (`exito` vs `ok` literal)
- Generic event node that reads search_result or entry_result, typed to suceso/error, via shared/persistence
- Event logging of failures/successes not aborted
- Discovery of errors in the reviewer and final tests

**Decisions**
- Search filters unsupported (`filtros_no_aplicables`) fail set completely instead of silently continuing without filters
- Success path of retries validated: successful retries count against actual attempts (`numero_de_intentos`)
- Event search scoped to current source (search_result of previous source inhibited)
- Logging of a write failure must still continue (registered node)
- Playwright mocked in node tests to avoid async/event-loop issues

**Status**
- Phase 4.3 ✅: Filter search + generic register nodes done and validated
- Ruff 0, mypy 0 (37 files), pytest 171/171
- Branch: `fase-4` · committed

## Session 10 — 08/08/2026
`ses_01d9bc5d2ffe0OwXiVc3MrXgBo` · `fase-4`

**Topics**
- Sub-fase 4.2 complete: "Entrar a la fuente", "¿Ingreso exitoso?" and "Registrar evento" nodes
- Integration with LinkedInAdapter (navigation, auth, success criteria)
- Conditional retry logic for source unavailability and timeouts
- session_id generation (SES-NNNN) and handle_sesion management (Playwright page)
- Event logging for both successes and failures in persistence layer
- Validation of entry result consistency

**Decisions**
- Browser instance created per attempt to ensure clean state
- Playwright instance started manually to prevent page closure on successful node exit

**Status**
- Phase 4.2 ✅: Platform entry nodes done and validated
- Ruff 0, mypy clean (logic), pytest 152/152
- Branch: `fase-4`

## Session 9 — 08/08/2026
`ses_01ebcd885ffe7UB5IsfCrylV90` · `fase-4`

**Topics**
- Sub-fase 4.1 complete: INICIO node + 3 control nodes (existence, iteration, selection) of Discovery flow (technical sheet v1.0/v1.3)
- Branch `fase-4` created from `main`; Phase 4 work restricted to it, no merge without authorization
- `run_context.py`: `permitir_vacio` parameter; new context fields (`fuente_corriente`, `posicion_fuente_corriente`, `motivo_terminacion`, `timestamp_terminacion`)
- `shared/persistence.py`: atomic lock acquisition (`BEGIN IMMEDIATE`), `forzar` overwrite with CAS, `probe_write`, `write_corrida`, `write_evento`, public `umbral_obsolescencia_minutos`
- `control_fuentes.py`: 3 nodes, pure context evaluation, ERR-01..03 local codes, termination reasons fixed on context (sin_fuentes/corrida_completada), traceability run_id+source_id
- Reviewer cycle: blockers resolved, minors fixed (iterador range validation, run_id empty → Loguru-only, atomic mutation docs)
- Validation: 136 tests passing, ruff 0, mypy 0

**Decisions**
- INICIO validates `source_id`/`nombre` required to discard with ERR-12 instead of aborting with ERR-10
- `acquire_lock` rework: `BEGIN IMMEDIATE` for atomic first acquisition; CAS (`UPDATE ... WHERE run_id`) for `forzar` branch
- Authorities exception in AGENTS.md: `modules/discovery/` uses Spanish identifiers for domain concepts (consistent with `run_context.py` precedent)
- `corridas.estado` 5 values vs DOC-13A termination-reason reconciliation pending before Finalizar Proceso node (documented, not resolved)

**Status**
- Phase 4.1 ✅: INICIO + 3 control nodes done and validated
- Ruff 0, mypy 0 (31 files), pytest 136/136
- Branch: `fase-4`

## Session 8 — 07/08/2026
`ses_021c087e1ffePrh0h4O4Zzb4BY` · `modulo-1`

**Topics**
- Context recovery: preparation plan phases 1–5 completed and committed, phase 6 scaffolded (run context + LinkedIn adapter)
- Fase 6 of preparation plan: discovery scaffold with 4 methods, 8 new conftest fixtures, 20 new tests, HTML fixtures
- Code-review fixes from reviewers: entry criterion enforced as mandatory in validated config and base URL derived from source URL
- Documentation correction: `credenciales_no_disponibles` registered in official `codigo_motivo` catalog as non-retryable config error, outside retry groups A/B
- Fase 7 validation finished: full checklist vs docs + suite green (102/102), verdict "READY TO BUILD PHASE 4"
- Git state verified: working tree clean at session start, all phase work already committed and pushed
- Session history updated (this entry)

**Decisions**
- `credenciales_no_disponibles` → ER-CFG, non-retryable, belongs neither to retry Group A nor B (occurs before channel opens, deterministic at step 2 of "Entrar a la fuente")
- Node construction of Phase 4 starts only after explicit user confirmation
- Reviewer minor findings stay documented as-is pending future authorization (adapter error class outside BaseError hierarchy)

**Status**
- Phases 0–3 ✅; Module 1 preparation plan phases 1–7 ✅ (validation verdict "ready to build"); Phase 4 node construction ⬜ pending approval
- Ruff 0, mypy 0 (27 files), pytest 102/102
- Branch: `modulo-1`

## Session 7 — 07/08/2026
`ses_0234a5a0effeWIUu0hsOpfvx3L` · `modulo-1`

**Topics**
- Context recovery: AGENTS.md, MVP Plan, tracker, session history
- Analysis of Module 1 flow diagram + technical sheet (13 canonical node specs)
- Build strategy discussion: node-by-node vs. vertical-phase A-E approach
- Chosen node-by-node build for Phase 4 (13 nodes, flow order, one validated node per step)
- MVP Execution Plan Phase 4 rewritten: generic 8-step plan replaced by 13-node build plan
- Gaps identified vs. current infra: rework risk contained via per-node work cycle

**Decisions**
- Phase 4 (Module 1) built node-by-node, strictly in flow order, each node through its own full work cycle (analysis → plan → implementation → validation → close)
- The 6 decision nodes act as contract validators of their immediate predecessor
- Closed/open gap decisions pending user approval before execution (no implementation done)

**Status**
- Phases 0–3 ✅, Phase 4 ⬜ (plan redefined as 13 nodes; no implementation yet)
- No code changes this session → Ruff/mypy/pytest n/a
- Branch: `modulo-1`

## Session 6 — 01/08/2026
`ses_041587944ffe8Ve6EeplEa9Huo` · `modulo-1`

**Topics**
- Session identification via OpenCode local database
- Session History restructured: managed by session number, newest first
- Past sessions (1–5) consolidated into a single entry; detail preserved in git
- 5 custom sub-agents created: docs-reviewer, code-reviewer, docs-updater, test-writer, playwright-debugger

**Decisions**
- Session History managed by session number, newest first
- Sessions 1–5 consolidated; old format remains recoverable in git
- One entry per OpenCode session (not per calendar day)
- Sub-agents have a single specific function; reviewers are read-only; they support project construction, not the product automation

**Status**
- Phases 0–3 ✅, Phase 4 ⬜
- Ruff 0, mypy 0, pytest 48/48
- Branch: `modulo-1`

## Sessions 1–5 — 23–30/07/2026 (consolidated)

**Topics**
- Project foundation: repository, directory structure, config, git + GitHub, MVP plan (9 phases)
- Phases 0–3 completed: shared services, profile model, AI service, decision engine, state machine, 5 prompts (PRM-001..005)
- Persistence migrated from Excel to SQLite (7 tables + ID sequences)
- Code fully translated to English; data layer kept in Spanish
- Architecture review: 7 offer states, cloud-primary AI strategy, MVP persistence scope, data dictionary + ERD
- Prompts retested end-to-end against `gemma4:31b-cloud`; mandatory Spanish output enforced
- Branch `modulo-1` created for Phase 4 (Opportunity Discovery)

**Decisions still in effect**
- LinkedIn is the only source for the MVP
- SQLite persistence; data layer (models, persistence, DB) in Spanish
- Cloud-primary AI strategy with configurable local fallback
- Offer lifecycle unified to 7 states
- Prompts must always instruct Spanish output (generated content is stored data)

**Status (end of 30/07/2026)**
- Phases 0–3 ✅, Phase 4 ⬜
- Ruff 0, mypy 0, pytest 48/48
- Branch: `modulo-1`
