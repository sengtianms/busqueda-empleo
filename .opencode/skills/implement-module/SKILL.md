---
name: implement-module
description: Use this skill when implementing any new module, class, service, component, or backlog task in this project. Follow the official implementation workflow before writing or modifying code.
---

# Purpose

This skill defines the mandatory implementation workflow for every development task in this project. Its purpose is to ensure consistency, traceability, and strict compliance with the project's approved architecture, documentation, and implementation standards.

---

# When to Use

Use this skill whenever you are asked to:

- Implement a backlog task.
- Create a new module.
- Create or modify a class.
- Create or modify a service.
- Create or modify a component.
- Add new functionality.
- Refactor existing code as part of an approved task.

Do **not** use this skill for:

- Code reviews.
- Debugging.
- Documentation writing.
- Planning or architecture design.

---

# Implementation Workflow

Follow every step in the exact order.

## 1. Understand the Task

Carefully read the complete request.

Identify:

- Objective.
- Expected outcome.
- Scope.
- Constraints.

Never begin implementation before fully understanding the task.

---

## 2. Identify Dependencies

Determine:

- Which modules are involved.
- Which files will be created or modified.
- Which existing components are affected.

Never modify files outside the task scope.

---

## 3. Validate Available Information

Verify that all required information is available before writing code.

If any requirement is:

- Missing,
- Ambiguous,
- Contradictory,
- Undefined,

Stop immediately.

Explain what information is missing and request clarification.

**Never make assumptions.**

---

## 4. Respect the Project Architecture

Always follow:

- Approved architecture.
- Official project structure.
- Existing design decisions.
- Naming conventions.
- Coding standards.
- Existing interfaces and contracts.

If the task changes the database structure, existing data, backups or
retention rules, apply the Data and Persistence Protection section of the
`project-architecture` skill before writing any code.

Never redesign or restructure the project unless explicitly instructed.

---

## 5. Implement Only the Requested Scope

Implement only the functionality explicitly requested.

Do not:

- Add extra features.
- Improve unrelated code.
- Refactor unrelated modules.
- Introduce new dependencies.
- Modify project structure.
- Change business rules.

---

## 6. Keep Changes Isolated

Limit modifications to the minimum number of files required.

Avoid side effects.

Preserve backward compatibility whenever possible.

---

## 7. Validate the Implementation

Before considering the task complete, verify:

- No syntax errors.
- Correct imports.
- Type consistency.
- Proper exception handling.
- Logging consistency.
- Integration with existing components.
- Compliance with project standards.

---

## 8. Summarize the Work

After implementation, provide:

- Files created.
- Files modified.
- Brief implementation summary.
- Potential risks.
- Known limitations.

---

# Mandatory Rules

Always:

- Follow the approved project documentation.
- Respect the official architecture.
- Respect the project implementation plan.
- Keep code clean, readable, and maintainable.
- Prefer simple and consistent solutions.
- Maintain compatibility with the existing system.
- Keep changes minimal and focused.
- Stop and request clarification whenever an implementation decision is not explicitly documented.

Never:

- Assume requirements.
- Invent missing information.
- Change the architecture.
- Change the technology stack.
- Rename public APIs without approval.
- Modify unrelated modules.
- Delete existing functionality without authorization.
- Introduce undocumented behavior.
- Continue automatically to the next backlog task.

---

# Expected Output

Every completed implementation must include:

## Completed

Brief summary of what was implemented.

## Files Created

List every new file.

## Files Modified

List every modified file.

## Validation

Summarize the verification performed before completion.

## Risks

List any known risks or limitations.

## Pending

List any remaining items that require user approval.

Wait for explicit user approval before starting the next implementation task.