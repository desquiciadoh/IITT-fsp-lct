# CLAUDE.md: FSP Draft

Claude Code working notes. `AGENTS.md` (shared with other agents) is loaded as well; this file adds how to run things and how to work here. Product rules: `README.md` §1. Specs: `docs/ARCHITECTURE.md`. Tasks per owner: `BE.md`, `ML.md`, `AI.md`, `FE1.md`, `FE2.md`.

## Commands (Windows; Git Bash or PowerShell)

```bash
.venv/Scripts/python -m pytest tests/ml -q            # pure ML/engine tests, no DB
.venv/Scripts/python -m pytest -q                     # full suite, needs Postgres on :5432
.venv/Scripts/python manage.py check
.venv/Scripts/python manage.py makemigrations --check --dry-run
.venv/Scripts/python -m ruff check apps config tests
.venv/Scripts/python .claude/skills/verify/scripts/verify.py   # all gates + invariant scan
docker start fsp-postgres || docker run -d --name fsp-postgres -p 5432:5432 -e POSTGRES_DB=fsp_draft -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres pgvector/pgvector:pg17
```

- No `.venv` yet: `py -3.13 -m venv .venv` then `.venv/Scripts/python -m pip install -r requirements.txt ruff pytest-cov numpy`.
- Port 5432 taken by a native PostgreSQL service (the full suite fails with "connection rejected")? Run the container with `-p 5433:5432` and `export POSTGRES_PORT=5433` (PowerShell: `$env:POSTGRES_PORT=5433`).
- `apps/` is on `sys.path` (`config/settings.py`), so imports are `from assessment.models import ...`, not `apps.assessment`.
- WeasyPrint needs GTK on Windows. If PDF import fails locally, that is the environment, not the code.

## Layout

`apps/{core,identity,profiles,assessment,matching,outreach,fsp_sync}` is a Django modular monolith. `core/services.py` holds contact gating, `core/errors.py` returns RFC 7807 problem+json, `outreach/services.py` runs the offer state machine. Pure engines (target, see `ML.md` §2) live in `apps/assessment/{families,engine}/` and `apps/matching/engine/`. Tests are in `tests/`; pure ML tests go in `tests/ml/`.

## Invariants (a change that breaks one is a bug, even when tests pass)

1. An LLM never decides a grade or a score. Grading is deterministic IRT over oracle-computed keys.
2. Answer keys and their fingerprints never leave the server: not in a serializer, `Instance.view()`, a log, or an error body.
3. Contacts are read only through `core/services.py` after an accepted offer creates a `ContactGrant`. Denials return 403 and write `AuditLog`.
4. FSP results change Strength and ranking, never the grade. Unconfirmed profiles stay visible, ranked ×0.75.
5. `salary_min > 0`, `salary_max >= salary_min`, and `salary_type` are required, checked in both the DB and DRF.
6. Engine packages import no Django, ORM, or `core.enums`. They are deterministic from a seed: no global `random`, and no iteration over an unsorted `set`/`dict` of strings when the order affects output.
7. Every match score carries human-readable reason chips; the contributions sum to the score.

## How to work here

- **Ownership:** the user owns ML (`ML.md`). Don't edit Django models, views, or migrations for ML work; write a request into `BE.md` §2 instead. Keep cross-file IDs stable (`ML-3`, `G7`, `B12`).
- **Loop:** plan → failing test → minimal code → `verify` skill → review agent → commit. Small PRs (< ~400 lines) titled with the task ID.
- **Tests:** fixed seeds and golden values for every formula; behaviour over implementation; API tests check 401/403 boundaries.
- **Review agents** (`.claude/agents/`): `django-reviewer` for Django/DRF diffs, `ml-engine-reviewer` for families/CAT/IRT/matching math, `invariant-auditor` before any merge or demo, `silent-failure-hunter` for error paths, `build-error-resolver` for env/install/migration breakage. Run independent reviewers in parallel.
- **Skills:** `verify`, `tdd`, `irt-cat` (formulas and validation metrics), `item-family` (authoring a parametric family), `django-drf` (patterns for this repo).
- `.agents/` is the ECC install for Google Antigravity (team tooling). Claude Code does not load it; don't edit it. Its long references are copied under `.claude/skills/*/references/` where useful.
