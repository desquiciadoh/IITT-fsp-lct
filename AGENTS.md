# ECC Project Engineering Standards: FSP Draft

This project operates under the **ECC (Engineering Context & Coordination)** methodology:
```text
plan -> test -> implement -> review -> verify -> remember -> improve
```

## Core Directives

1. **Architecture & Scope Compliance**
   - Refer to [TK.md](docs/TK.md), [QA.md](docs/QA.md), and [ARCHITECTURE.md](docs/ARCHITECTURE.md).
   - Current implementation stack: Django 5.x + Django REST Framework modular monolith, PostgreSQL + pgvector, Celery/Redis-compatible broker.
   - The React + TypeScript SPA, FastAPI migration, and Valkey deployment described in older planning material are not present in this checkout; treat the Django code and `requirements.txt` as authoritative until those components are implemented.
   - Grading & Scoring: Deterministic IRT scoring and parametric question families. LLMs never decide grades directly.
   - Reverse recruitment: Employers browse ranked Leagues and send salary-first Draft Offers; contacts remain gated until candidate acceptance. Contact gating strictly lives in `outreach/services.py` (`ContactAccessService`; `core/services.py` is a deprecated re-export shim). Denials return 403 and write `AuditLog`.

2. **ECC Workspace Rules & Quality Gates**
   - Coding guidelines and patterns are defined in `.agents/rules/`:
     - Python & Django/DRF: `python-coding-style.md`, `python-testing.md` (the FastAPI rule is retained only for future migration work)
     - React & TypeScript: `react-coding-style.md`, `react-patterns.md`, `typescript-coding-style.md`
     - Engineering discipline: `common-development-workflow.md`, `common-code-review.md`, `common-security.md`
   - Specialist agent roles and skills are located in `.agents/agents/` and `.agents/skills/`.

3. **Workflow Rules**
   - **TDD first**: Write and verify tests before and alongside business logic implementation.
   - **Explainability**: Every candidate-job match score must carry human-readable, evidence-based justifications.
   - **Zero Regression**: Run tests and lint checks after any code modification.
