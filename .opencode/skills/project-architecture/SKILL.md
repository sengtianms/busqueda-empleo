---
name: project-architecture
description: Use this skill whenever implementing, modifying, reviewing, or refactoring code — including database structure, data migrations and backups — to ensure every change complies with the project's official architecture and design decisions.
---

# Purpose

This skill ensures that every implementation remains fully aligned with the project's approved architecture.

The project's architecture is the single source of truth for system organization, module responsibilities, dependencies, data flow, and implementation boundaries.

This skill prevents architectural drift during development.

---

# When to Use

Use this skill whenever:

- Implementing new functionality.
- Modifying existing functionality.
- Creating new modules.
- Refactoring code.
- Reviewing architecture compliance.
- Making design decisions.
- Integrating multiple modules.
- Changing the database structure, existing data, backups or retention rules.

Do not use this skill for debugging or code style reviews.

---

# Architecture Validation Workflow

Follow these steps before making architectural decisions.

## 1. Understand the requested change

Identify:

- Business objective.
- Scope.
- Modules involved.
- Expected behavior.

Never modify architecture without understanding the complete request.

---

## 2. Identify affected modules

Determine:

- Which module owns the responsibility.
- Which modules interact with it.
- Which interfaces are affected.

Never assign responsibilities to the wrong module.

---

## 3. Respect module boundaries

Every module must have a single responsibility.

Never:

- Duplicate responsibilities.
- Create circular dependencies.
- Couple unrelated modules.
- Bypass defined workflows.

---

## 4. Preserve the approved data flow

Follow the official processing flow.

Never:

- Skip processing stages.
- Merge independent stages.
- Reorder the workflow without approval.
- Introduce hidden execution paths.

---

## 5. Respect the technology stack

Use only the approved technologies.

Never replace or introduce technologies without explicit approval.

---

## 6. Minimize architectural impact

Prefer extending the existing architecture instead of redesigning it.

Architectural changes require explicit approval.

---

## 7. Validate consistency

Before finishing, verify:

- Module responsibilities remain clear.
- Dependencies remain correct.
- Naming remains consistent.
- Public interfaces remain compatible.
- Existing workflows remain intact.

---

# Data and Persistence Protection

Applies to any task that changes the database structure, existing data,
backups, or the persistence contract.

## Before the change

1. Locate the authoritative definition in DOC-13A, Appendix 5A and the
   decision log. Never invent a table, column, state, prefix or rule.
2. Take a verified backup of the live database and record its path.
   The backup must pass an integrity check before proceeding.
3. Design the change as an idempotent migration: running it twice must be
   harmless, and it must execute automatically at startup.
4. Preserve existing rows and traceability. Historical records are never
   deleted or rewritten silently. Transformations keep the original value
   where the rules require it.
5. Define the before/after evidence: row counts, distinct counts and
   key samples.
6. State the rollback path and what would be lost if it is used.
7. Stop and request approval for any destructive or irreversible change.

## After the change

1. Run the integrity check on the live database and on retained backups.
2. Compare before/after counts and confirm the expected result.
3. Confirm the migration runs cleanly on a copy and on the live database.
4. Confirm the no-empty-field rule and its documented exceptions.
5. Report the backup path, the evidence and any deviation.

## Never

- Modify the live database without a verified backup or explicit authorization.
- Delete or rename columns used by traceability without a registered decision.
- Let a functional module access the database directly.
- Store credentials, tokens or personal data in the repository or database.
- Treat a successful script run as proof: the data itself must be verified.

---

# Mandatory Rules

Always:

- Treat the approved architecture as authoritative.
- Respect module ownership.
- Keep responsibilities isolated.
- Preserve loose coupling.
- Prefer consistency over novelty.
- Keep the system modular.

Never:

- Redesign the architecture.
- Introduce undocumented patterns.
- Create unnecessary abstractions.
- Duplicate logic between modules.
- Break module boundaries.
- Add hidden dependencies.
- Modify architectural decisions without approval.

---

# Expected Output

Every architectural review or implementation must include:

## Architecture Assessment

Overall compliance with the approved architecture.

## Affected Modules

List all impacted modules.

## Dependency Impact

Describe any dependency changes.

## Architectural Risks

Identify any risks introduced by the implementation.

## Compliance Status

State whether the implementation fully complies with the approved architecture.

If any architectural conflict exists, stop and request user approval before proceeding.