---
name: verify
description: Run FSP Draft's verification gate (env, syntax, Django check, missing migrations, ruff, pytest, invariant scan for key leaks / contact gating / engine purity / global RNG / LLM-in-grading, diff) and report PASS/FAIL. Use after finishing a feature, fix or refactor, before every commit or PR, and whenever asked to "check", "verify" or "make sure it works".
---

# Verify

## Run

```bash
.venv/Scripts/python .claude/skills/verify/scripts/verify.py            # all phases
.venv/Scripts/python .claude/skills/verify/scripts/verify.py --only tests,invariants
.venv/Scripts/python .claude/skills/verify/scripts/verify.py --full     # force the DB suite
```

No `.venv`? Create it first (see `CLAUDE.md`). The script reports SKIP for missing tools, never PASS.

## Then

1. **FAIL:** fix it and re-run. Don't commit on FAIL. For env/import/migration failures, use the `build-error-resolver` agent.
2. **WARN:** read each hit. Fix real problems; for a known pre-existing issue outside your task, say so in the summary instead of fixing it silently (and add it to the owner's task file if it isn't there).
3. **Tests SKIP because Postgres is down:** say so explicitly. "Tests pass" means the suite ran, not that it was skipped. Start Postgres with `docker start fsp-postgres` when the change touches models, views or services.
4. **Review the diff yourself:** unintended files, debug leftovers, a test that no longer asserts anything.
5. For non-trivial changes, run the matching review agent(s) in parallel: `django-reviewer` (apps/config), `ml-engine-reviewer` (families/engine/matching/validation), `invariant-auditor` (before merge to main or a demo).

## Report format

Paste the script's table, then one line per remaining WARN/SKIP with the reason. Finish with `READY` or `NOT READY` and what blocks it.

## What the invariant scan covers (and doesn't)

It greps for answer-key fields in serializers, `__all__` serializers, `candidate_contacts` access outside the gated service, Django/ORM imports and global RNG in engine packages, LLM clients on the scoring path, bare `timezone.now()` in assessment, `print()` and hard-coded secrets. It is a lead generator: a PASS does not prove an invariant holds. The `invariant-auditor` agent traces the paths.
