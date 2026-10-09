---
name: tdd
description: Test-first workflow for FSP Draft - red/green/refactor with pytest, pytest-django and factory-boy; pure DB-free tests with fixed seeds and golden values for ML engines; API boundary tests (401/403/409) and invariant tests for Django. Use when implementing a feature or fixing a bug, writing tests, or when a task says "TDD", "add tests" or "cover".
---

# TDD for FSP Draft

## Loop

1. **Red.** Write the smallest test that states the behaviour. Run it and see it fail for the right reason (an assertion, not an `ImportError`). A test that passes before the change proves nothing.
2. **Green.** Write the minimal code that passes. Run that test, then the touched module's tests.
3. **Refactor.** Clean up with tests green. Then run the `verify` skill.
4. **Bug fix:** first a regression test that reproduces the bug, named after it (`test_sql_family_key_not_constant`).

Commands:

```bash
.venv/Scripts/python -m pytest tests/ml -q                         # pure, fast
.venv/Scripts/python -m pytest tests/test_contact_gating.py -q -x  # one file, stop at first failure
.venv/Scripts/python -m pytest -q -k "offer and conflict"          # by name
.venv/Scripts/python -m pytest --cov=apps --cov-report=term-missing -q
```

## Pure engine tests (`tests/ml/`, no DB)

- No `db` fixture and no Django imports; import engines as `from assessment.engine.irt import ...` (`apps/` is on `sys.path`).
- **Fixed seeds** everywhere: `random.Random(42)`, `np.random.default_rng(42)`.
- **Golden values** for every formula, computed independently (by hand, or a numpy one-liner in the test docstring), compared with `pytest.approx(..., abs=1e-6)`.
- **Properties** worth a test each:
  - determinism: the same seed gives identical output, also through `CatState.to_json()` → `from_json()`;
  - monotonicity: more correct answers never lower θ̂; a higher θ never lowers P;
  - bounds: the rating CI shrinks as items are added; probabilities stay in [c, 1];
  - edge cases: all-correct, all-wrong, alternating, empty pool, one item, `c = 0`, extreme `b`;
  - secrecy: `"key"` and `"fingerprint"` are not in `inst.view()` and their values don't appear in `json.dumps(inst.view())`.
- A family test runs many seeds (`@pytest.mark.parametrize("seed", range(200))`) and checks that the oracle agrees with the key, there is exactly one correct option, and answers are not constant.
- Matching: hand-ranked golden fixtures (`assert [c.id for c in ranked] == ["C-A", "C-B", "C-C"]`), `sum(contributions) == pytest.approx(score)`, and every component has a chip.

## Django/API tests (`tests/`, need Postgres)

- Mark with `@pytest.mark.django_db`; reuse `conftest.py` fixtures (`api_client`, `candidate_user`, `employer_user`) and the fixture style in `tests/test_contact_gating.py`.
- Test through the API (`api_client.force_authenticate(user)` is fine unless the test is about auth itself) and assert status **and** body (problem+json `type`/code).
- Every endpoint gets its boundary: anonymous → 401, wrong role → 403, someone else's object → 403/404, stale `version` → 409.
- Every invariant you touch gets a test: contacts hidden before `accepted` and visible after; `key` absent from item responses; salary constraints rejected at the DRF and DB level; FSP sync doesn't change the grade; cooldown respects `clock_offset_days`.
- Assert side effects: `AuditLog` row written, `ContactGrant` created exactly once, no extra queries (`django_assert_max_num_queries`) on list endpoints.
- Mock only at boundaries (FSP registry HTTP, the LLM gateway, Celery `.delay`), never the code under test.

## Anti-patterns

- Asserting on implementation details (private helpers, call counts of internal functions).
- Tests that depend on order or on shared mutable state; `time.sleep`; real network.
- Assertions that can't fail (`assert result is not None` as the only check).
- Changing a test to make it pass without saying why the old expectation was wrong.

## More

Long references from ECC (generic, not project-specific): `references/ecc-django-tdd.md` (factories, DRF API tests, mocking) and `references/ecc-python-testing.md` (fixtures, parametrize, property-based tests). Read only the section you need.
