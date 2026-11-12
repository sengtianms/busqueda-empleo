---
description: Updates the current session's entry in session history.md
---

Update (or create) the current session's entry in `docs/history/session history.md`.

## Rules

- Runs **only** on user invocation (`/save`). The agent must never execute or anticipate it autonomously.
- History is managed by session number, newest first. Session number = last existing + 1 (consolidated Sessions 1–5 counts as one).
- One entry per OpenCode session (one conversation), not per calendar day.
- Get current session ID:
  ```
  sqlite3 ~/.local/share/opencode/opencode.db "SELECT id, substr(title,1,60), datetime(time_updated, 'unixepoch', 'localtime') FROM session ORDER BY time_updated DESC LIMIT 1;"
  ```
- Date format: `DD/MM/YYYY`.
- Fields: **Topics**, **Decisions**, **Status**.
- Topics: keyword-style lists, one bullet per line, written for a new developer. No commit hashes, file paths, or rule numbers.
- Decisions and Status: current session only; no repetition of prior sessions. A single line (e.g. "Decisions from previous sessions remain in effect") suffices for continuity.
- Content is inferred from the conversation just held.
- If something is unclear, ask before writing.
- After updating history, also update `docs/history/tracker.md` if any task changed status during the session.

## Git commit

After documentation is updated and consistent, record everything in a **single commit**:

1. **Scope**: every file modified or created during the session (tracked changes and new files). Nothing left uncommitted.
2. **Exclusions**: only those in `.gitignore` (secrets, `.env`, `data/*.db`, `temp/`, `logs/`). Note: `.env.template` is versioned — keep it.
3. **Verify**: `git status` and `git diff` must match session output. If any non-ignored file is unexpected, stop and ask the user.
4. **Stage**: `git add -A`, then review `git diff --cached` before committing.
5. **Commit format**: English, conventional, imperative mood, subject ≤ 72 chars: `<type>(<scope>): <short summary>` (e.g. `docs(commands): ...`).
6. **Push**: `git push origin <current-branch>`. If push fails (remote diverged), stop and report; never force-push.
7. **Report**: commit hash, push result, confirm clean worktree.

Merges and any branch push beyond this commit remain governed by Version Control rules in AGENTS.md; never performed here.
