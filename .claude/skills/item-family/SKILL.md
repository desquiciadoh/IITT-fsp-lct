---
name: item-family
description: Author or fix a parametric assessment item family for FSP Draft (generator + independent oracle + IRT priors) that passes the verify harness - unique instances, key depends on drawn parameters, exactly one correct option, no key leakage through view(). Use when adding, reviewing or repairing families in apps/assessment/families/ (ML-1, ML-6, ML-13) or reviewing LLM-drafted families from the AI stream.
---

# Authoring an item family

Contract: `ML.md` §3 (`FamilyMeta`, `Instance`, `ItemFamily`, `make_rng`). Spec: `docs/ARCHITECTURE.md` §2.5. The current `apps/assessment/engine.py` families are the **anti-example** (ML-F1): constant answers, seed in the fingerprint, no oracle.

## Rules

1. **The key is a function of drawn parameters.** Draw parameters first (tables, numbers, code shape), compute the key from them, and make sure several distinct answers occur over seeds (answer-text entropy > 1 bit).
2. **An independent oracle.** `oracle(inst)` recomputes the key by a different path than `generate`:
   - SQL: run the query on in-memory `sqlite3` with the generated rows;
   - JS event loop: a small microtask/macrotask simulator (CI may also run Node);
   - code output: `exec` the generated Python in a restricted namespace in the harness only;
   - complexity: a table of loop shapes → Big-O, reviewed by a human.
3. **Options:** exactly one correct; distinct after normalisation (strip, case, `0.50` vs `0.5`); plausible distractors that come from typical mistakes (off-by-one, `>` vs `>=`, `WHERE` vs `HAVING`, sync vs microtask order). Shuffle with `rng`. Option ids are opaque, drawn from `rng` (e.g. `f"o{rng.getrandbits(32):08x}"`), never positional letters that correlate with the key.
4. **`c`** = `1/len(options)` for choice items, 0 for typed answers. **`a`, `b`**: expert priors (bookmark standard-setting). `b` maps to a grade band via the cuts (intern < −1 ≤ junior < 0 ≤ middle < 1 ≤ senior).
5. **`fingerprint`** = `sha256(json.dumps(params, sort_keys=True, ensure_ascii=False))`, from parameters only, never the seed. Collisions must be ≤ 0.1% over 1,000 instances.
6. **`view()`** returns `stem_md`, `input`, `code`, `options` only. Don't put the answer in the stem, code comments or option metadata.
7. **Pure and deterministic:** no Django imports, no global `random`, only the passed `rng`. The same rng state gives an identical instance.
8. **Text:** stems and options are in Russian (the product UI), and code in the item's language. Markdown in `*_md` fields. `time_limit_s` is realistic (60–180 s).
9. **`is_correct(key, answer)`:** choice compares `answer["option_id"]`; typed answers normalise (trim, decimal comma vs point, case) and never `eval` user input.

## Skeleton

```python
# apps/assessment/families/backend/sql_group_having.py
from __future__ import annotations
import hashlib, json, random, sqlite3
from ..base import FamilyMeta, Instance

META = FamilyMeta(id="be.sql.group_having.v2", version=2, specs=("backend", "ml_data"),
                  topic="sql.aggregation", skills=("sql",), format="sql_result",
                  a=1.3, b=0.4, c=0.25, time_limit_s=120)

class SqlGroupHaving:
    meta = META

    def generate(self, rng: random.Random) -> Instance:
        params = {...}                                   # draw everything here
        key_value = self._compute(params)                # from params only
        options = self._options(key_value, params, rng)  # 4 distinct, 1 correct, shuffled, opaque ids
        key = next(o["id"] for o in options if o["_correct"])
        options = [{"id": o["id"], "text_md": o["text_md"]} for o in options]
        fp = hashlib.sha256(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return Instance(stem_md=..., input="choice", key=key, fingerprint=fp,
                        code={"lang": "sql", "text": ...}, options=options)

    def is_correct(self, key, answer: dict) -> bool:
        return answer.get("option_id") == key

    def oracle(self, inst: Instance):
        ...  # rebuild the table in sqlite3 from the instance, run the query, map the result to an option id
```

## Done when

- `python -m assessment.families.verify --n 1000` passes for the family: the oracle agrees with the key, exactly one correct option, distinct options, it renders, collisions ≤ 0.1%, entropy > 1 bit.
- A deliberately broken copy (constant key) fails the harness. Keep that as a test.
- `tests/ml/` has a parametrised seed test, and `"key"`/`"fingerprint"` values don't appear in `json.dumps(inst.view())`.
- The `ml-engine-reviewer` agent has no CRITICAL findings.

## Reviewing LLM-drafted families (from AI.md)

Treat the draft as untrusted input. Re-derive the key logic yourself, check that distractors are wrong for a stated reason, run the harness, and check that the topic and skills ids exist in `content/specializations.yaml` and `content/skills.yaml`. An LLM never sets `a`/`b` without a human decision.
