# ML.md: Machine Learning & Psychometrics Tasks (owner: ML engineer)

> **Audience:** the ML engineer and their AI coding agent.
> **Scope:** everything that decides *numbers*: parametric item families and oracles, the CAT/IRT engine and grade policy, the matching scorer, Profile Strength and FSP boost, league percentiles, embeddings, the synthetic world, and the validation suite (`make validate` → `report.json`).
> **Date:** 2026-10-08. Related files: [BE.md](BE.md) (backend wiring), [AI.md](AI.md) (LLM and taxonomy), [FE1.md](FE1.md), [FE2.md](FE2.md).

---

## 0. Ownership Rules

| You own | You do **not** own |
|---|---|
| `apps/assessment/families/`: item families, registry, HMAC rng, `verify` harness | Django models, migrations, views, serializers, URLs, Celery tasks (BE) |
| `apps/assessment/engine/`: CAT, 3PL EAP, grade policy, topic evidence, blueprints | Persisting `CatState`, serving items, deadlines, cooldowns, endpoints (BE) |
| `apps/matching/engine/`: features, weights and presets, reasons, gaps, strength, FSP boost, percentiles, gross↔net, relaxations (P1), acceptance likelihood (P1) | SQL prefilters, ORM loading into DTOs, pagination, facets (BE) |
| `content/specializations.yaml`, `content/grades.yaml`, `content/blueprints.yaml` | `content/skills.yaml` and `normalize_skill()` (AI) |
| `validation/`: synthetic world, assessment simulation, matching benchmark, report | LLM parsing, the "why" sentence (AI) |
| `seed_data/full/` content and schema | Loading it into the DB (`seed --mode=full`, BE) |
| Docs: `docs/BACKEND.md` §4 and §5; methodology sections (docs 02–04) | UI (FE1, FE2) |

**Hard invariants (from TK and ARCHITECTURE; never break them):**
1. **An LLM never decides a grade.** Grades come only from IRT scoring over oracle-computed keys.
2. **The answer key never leaves the server.** `Instance.view()` must not contain the key or anything derived from it.
3. **FSP achievements affect Strength and ranking only, never the grade.**
4. **Everything is deterministic and reproducible** from a seed. The same inputs give the same outputs, including tie-breaks.
5. **Engine packages are pure.** They must not import Django, the ORM or `core.enums`; use string constants. One unit test asserts your constants equal the values in `core.enums`. Validation scripts must import the exact production engine code.

---

## 1. Current State (audit of merge `3cf4044`)

The backend MVP has placeholder ML logic. All of it is yours to replace.

**ML-F1 🔴 Answer keys are constant, so the "leak-proof" claim is false** **[verified on 200 seeds]**.
- `apps/assessment/engine.py:68-74` (`be.sql.group_having.v1`): department counts are always `threshold+1, threshold, threshold−1`, so the correct answer is **always "2 отдела(ов)"**. Salaries and department names are decoration.
- `fe.js.event_loop.v1` (`:163-167`): the answer is always the pattern `1, <v>, 3, 2`.
- `be.algo.complexity.v1`: 4 variants, 2 possible answers.
- `fingerprint` includes the seed, so it can never collide and collision statistics are meaningless. It must hash the *drawn parameters* only.
- `oracle()` is declared but never implemented, and there is no verify harness.

**ML-F2 🔴 Grading is not IRT.**
- `score_assessment()` (`engine.py:207-243`) computes `theta = avg_b + (pct − 0.5)·2` and `se = max(0.2, 1/√n)`. The `a` and `c` parameters are ignored.
- It always returns `decision=CONFIRMED` **[verified]**; the view ignores that value and recomputes the decision itself.
- Cut scores are `−1.0 / −0.2 / 0.6 / 1.5` (`:199-204`), while ARCHITECTURE §2.5 says `−1 / 0 / +1` separate Intern | Junior | Middle | Senior. Decide which is right, put it in `content/grades.yaml`, and document it.

**ML-F3 🔴 There is no CAT.**
- Each session gets the first 3 registry families (`assessment/views.py:122-131`), with no adaptivity and no stop rule.
- Frontend candidates receive backend items. `ml_data` has **no** families at all.
- The seed is `sha256("secret:session:family:seq")`, but the spec says HMAC (you provide `make_rng`).

**ML-F4 🟠 The matching scorer is far from spec** (`apps/matching/scoring.py`).
- `nice_skills` are ignored, and the evidence source (test / FSP / declared) doesn't change the weight.
- Skills are matched by lower-cased display **name**, not by skill id or aliases.
- The "strength" component is a linear function of `rating`, not Profile Strength.
- FSP gets `3 × count + 5 if rank`. There's no gross/net normalization, no semantic or freshness feature, and `Position.weights` and presets are ignored.
- Some components emit no reason chip: no league gives 5 points silently; unknown salary expectations give a silent 10/10.
- `components` is a dict without weight or contribution, and there are no `gaps`.
- It receives ORM objects and lazily queries them (an N+1 that BE will remove once you take DTOs).
- Weights are 35/25/15/15/10 rather than the spec's 35/20/15/15/10/5.

**ML-F5 🟠 Strength, FSP boost and percentiles.**
- At finalize, `strength = 50 + 25θ` (`assessment/views.py:282,292`).
- FSP sync adds `+5` per result **cumulatively** on every call (`fsp_sync/views.py:103-108`). BE is fixing idempotency and storage (BE.md B10); you own the formula.
- `percentile` is never computed anywhere.
- The seed hardcodes inconsistent values (Anna: rating 1250, strength 95), so the synthetic world must produce values consistent with your formulas.

**ML-F6 🟡 Not started:** embeddings and pgvector, the synthetic world, the validation suite and report, girth calibration, and the leak monitor.

---

## 2. Target Layout

```text
apps/assessment/families/          # pure, no Django
  base.py          FamilyMeta, Instance, ItemFamily protocol
  registry.py      all_families(), active_metas(spec), make_rng()
  verify.py        python -m assessment.families.verify  (1,000 instances per family)
  shared/ backend/ frontend/ ml_data/   one module per family (+ optional YAML meta)
apps/assessment/engine/            # pure, no Django
  irt.py           p_3pl, item information, EAP (61-point quadrature, N(0,1) prior)
  cat.py           CatEngine, CatState (JSON round-trip), selection, stopping
  policy.py        grade decision, promotion, fallback, cut scores loaded from content/grades.yaml
  topics.py        topic evidence (strong / moderate / limited)
  blueprint.py     blueprint_for(spec, skills) for JD screening (used by AI's parse_jd)
apps/matching/engine/              # pure, no Django
  types.py         CandidateCtx, NeedCtx, Weights, Component, Reason, Scored, ...
  features.py      skill_fit, grade_fit, salary_fit, semantic_fit, freshness
  score.py         passes_hard_filters, score_pool, presets
  strength.py      fsp_boost, strength, percentiles
  salary.py        to_gross / to_net (NDFL scale)
  relax.py         relaxations, acceptance_likelihood   (P1)
content/specializations.yaml  grades.yaml  blueprints.yaml
validation/
  synth.py  sim_assessment.py  bench_matching.py  report.py  run.py   # python -m validation.run
  data/truth.jsonl (hidden truth; never loaded into the app)
  out/report.json  out/report.fixture.json  out/charts/
seed_data/full/*.jsonl + seed_data/README.md (schema)
tests/ml/          pure unit tests (fixed seeds, no DB)
```

**Imports:** apps are importable as top-level packages today (`config/settings.py` puts `apps/` on `sys.path`), so `from assessment.engine.cat import ...` works. BE may move to `apps.<name>` imports (BE.md A9). Keep imports inside your packages **relative** so a move is cheap.

**Tests without a database:** pytest-django is configured, but tests not marked `django_db` never touch Postgres. Run `pytest tests/ml -q`.

**Dependencies:** add `numpy` (and `scipy` only if needed) in your first PR. Add `girth` (P1, calibration) and `sentence-transformers` (P1, CPU torch) when you start those tasks. BE reviews `requirements.txt` changes.

---

## 3. The Contract (you publish it; BE wires it)

**Publish this first, as stubs that return final shapes.** BE (and through BE, the FE API shape) depend on it. Changing a signature later means one PR touching both sides. The copies of these shapes in BE.md §2.1 summarize this section; this section is authoritative.

```python
# ── apps/assessment/families/base.py ──
from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Any, Literal, Protocol

Spec = Literal["backend", "frontend", "ml_data"]
Grade = Literal["intern", "junior", "middle", "senior"]          # ordered
ItemFormat = Literal["code_output", "find_bug", "sql_result", "complexity",
                     "numeric_scenario", "concept_mcq"]
InputKind = Literal["choice", "number", "text"]

@dataclass(frozen=True)
class FamilyMeta:
    id: str                    # "be.sql.group_having.v2"
    version: int
    specs: tuple[Spec, ...]    # shared families list every spec
    topic: str                 # must exist in content/specializations.yaml
    skills: tuple[str, ...]    # skill ids from content/skills.yaml (AI-owned); CI checks references
    format: ItemFormat
    a: float                   # discrimination
    b: float                   # difficulty (expert prior → recalibrated)
    c: float                   # 1/len(options) for choice, 0 for typed answers
    time_limit_s: int

@dataclass
class Instance:
    stem_md: str
    input: InputKind
    key: Any                                  # SERVER-SIDE ONLY → AssessmentItem.key
    fingerprint: str                          # sha256 of the drawn SEMANTIC parameters (never the seed; names/ids excluded, D14)
    code: dict[str, str] | None = None        # {"lang": "python"|"javascript"|"sql", "text": ...}
    options: list[dict[str, str]] | None = None   # [{"id": opaque, "text_md": ...}], shuffled, distinct

    def view(self) -> dict: ...               # stem_md, input, code, options. NEVER key/fingerprint

class ItemFamily(Protocol):
    meta: FamilyMeta
    def generate(self, rng: random.Random) -> Instance: ...
    def is_correct(self, key: Any, answer: dict) -> bool: ...   # answer: {"option_id": str} | {"value": str}
    def oracle(self, inst: Instance) -> Any: ...                # independent recomputation; verify harness only

# ── apps/assessment/families/registry.py ──
def all_families() -> dict[str, ItemFamily]: ...
def active_metas(spec: Spec) -> list[FamilyMeta]: ...           # BE syncs these into ItemFamily rows
def make_rng(secret: bytes, session_id: str, purpose: str, n: int) -> random.Random:
    """HMAC-SHA256(secret, f"{session_id}|{purpose}|{n}") → int seed.
    purpose = family_id for item generation, "select" for randomesque selection."""

# ── apps/assessment/engine/cat.py ──
Mode = Literal["full", "express"]
Kind = Literal["initial", "fallback", "promotion", "screening"]

@dataclass
class CatState:
    spec: Spec; claimed: Grade; mode: Mode; kind: Kind
    administered: list[dict]   # [{family_id, seq, a, b, c, topic, correct: bool|None, late: bool}]
    theta: float; se: float
    min_items: int; max_items: int
    seen: list[str] = []                        # family ids from earlier attempts (D2)
    blueprint: list[tuple[str, float]] | None = None   # screening quotas (D2)
    stop_reason: str | None = None              # set when a stop rule ends the test (D8)
    def to_json(self) -> dict: ...              # BE stores it in AssessmentSession.state (JSONB); "v": 1
    @classmethod
    def from_json(cls, d: dict) -> "CatState": ...

@dataclass(frozen=True)
class CatResult:
    theta: float; se: float
    rating: int                     # round(1000 + 200·θ)
    rating_ci: int                  # round(1.96 · 200 · SE)
    result_grade: Grade
    decision: Literal["confirmed", "unconfirmed"]
    promotion_unlocked: bool        # P(θ ≥ next cut) ≥ 0.9
    fallback_grade: Grade | None    # highest lower grade with P(θ ≥ cut) ≥ 0.8, else None
    topics: list[tuple[str, Literal["strong", "moderate", "limited"]]]
    evidence: list[tuple[int, Grade, bool]]     # (seq, item level, correct)
    complete: bool = False          # a stop rule ended the test; False -> never confirmed (D8)
    stop_reason: str | None = None  # express | max_items | se | ci | pool_exhausted | None

class CatEngine(Protocol):
    def start(self, spec: Spec, claimed: Grade, mode: Mode, kind: Kind,
              pool: list[FamilyMeta], seen: set[str],
              blueprint: list[tuple[str, float]] | None = None) -> CatState: ...
    def next_family(self, state: CatState, pool: list[FamilyMeta],
                    rng: random.Random) -> FamilyMeta | None: ...      # None → stop
    def record(self, state: CatState, family_id: str, correct: bool,
               late: bool = False) -> CatState: ...                     # late ⇒ scored as incorrect
    def result(self, state: CatState) -> CatResult: ...                 # pure: never mutates state

def item_level(meta: FamilyMeta) -> Grade: ...       # difficulty band of b → ItemView.level

# ── apps/assessment/engine/blueprint.py ──
def blueprint_for(spec: Spec, skill_ids: list[str]) -> list[tuple[str, float]]: ...   # (topic, weight), Σ=1

# ── apps/matching/engine/types.py ──
Source = Literal["test", "fsp", "microtask", "declared"]

@dataclass(frozen=True)
class SkillEvidence: skill_id: str; source: Source; level: float          # level 0..1

@dataclass(frozen=True)
class FspResultCtx:
    tier: Literal["winner", "prize_winner", "finalist", "participant"]
    date: "datetime.date"; discipline: str; participants_total: int; team_size: int | None

@dataclass(frozen=True)
class CandidateCtx:
    public_id: str
    specialization: Spec | None
    league_grade: Grade | None
    league_status: Literal["pending", "confirmed", "unconfirmed"] | None
    theta: float | None; se: float | None; rating: int | None; percentile: float | None
    strength: float | None                      # precomputed by strength(), stored by BE
    skills: tuple[SkillEvidence, ...]
    topic_levels: dict[str, str]                # from CatResult.topics
    fsp_rank: Literal["cat3", "cat2", "cat1", "kms", "ms"] | None
    fsp_results: tuple[FspResultCtx, ...]
    salary_min: int | None; salary_max: int | None; salary_type: Literal["gross", "net"] | None
    work_formats: tuple[str, ...]; city: str; timezone: str
    last_active_at: "datetime.datetime | None"
    embedding: tuple[float, ...] | None         # P1

@dataclass(frozen=True)
class NeedCtx:
    position_id: str; specialization: Spec
    grades: tuple[Grade, ...]; allow_adjacent: bool
    must_skills: tuple[str, ...]; nice_skills: tuple[str, ...]   # skill ids (normalized at save time)
    work_formats: tuple[str, ...]; location: str
    salary_min: int; salary_max: int; salary_type: Literal["gross", "net"]
    embedding: tuple[float, ...] | None

@dataclass(frozen=True)
class Weights:
    skill: float = 35; strength: float = 20; grade: float = 15
    salary: float = 15; semantic: float = 10; freshness: float = 5

@dataclass(frozen=True)
class Component:
    key: Literal["skill", "strength", "grade", "salary", "semantic", "freshness"]
    value: float          # 0..1
    weight: float
    contribution: float   # value · weight; Σ contribution == Scored.score

@dataclass(frozen=True)
class Reason:
    kind: Literal["plus", "minus", "info"]
    text: str             # Russian, user-facing (e.g. "SQL подтверждён тестом")
    source: Source | None

@dataclass(frozen=True)
class Scored:
    public_id: str; score: float                 # 0..100
    components: tuple[Component, ...]; reasons: tuple[Reason, ...]; gaps: tuple[str, ...]

# ── apps/matching/engine/score.py ──
def passes_hard_filters(need: NeedCtx, c: CandidateCtx) -> bool: ...   # reference; BE mirrors indexed parts in SQL
def preset(name: Literal["balanced", "skills", "budget"]) -> Weights: ...
def score_pool(need: NeedCtx, pool: "Sequence[CandidateCtx]", weights: Weights,
               now: "datetime.datetime") -> list[Scored]: ...         # sorted desc; tie-break by public_id

# ── apps/matching/engine/strength.py ──
@dataclass(frozen=True)
class StrengthBreakdown: base: float; fsp_boost: float; total: float; percentile: float

def fsp_boost(rank: str | None, results: "Sequence[FspResultCtx]", now: "datetime.datetime") -> float: ...  # 0..15, pure
def percentiles(thetas: "Sequence[float]") -> list[float]: ...           # same order as input, 0..100
def strength(c: CandidateCtx, league_thetas: "Sequence[float]", now: "datetime.datetime") -> StrengthBreakdown: ...

# ── apps/matching/engine/salary.py ──
def to_gross(amount: int, salary_type: Literal["gross", "net"]) -> int: ...
def to_net(amount: int, salary_type: Literal["gross", "net"]) -> int: ...

# ── apps/matching/engine/relax.py (P1) ──
@dataclass(frozen=True)
class Relaxation: change: str; delta: int     # "убрать Kubernetes из обязательных" → +23 candidates
def relaxations(need: NeedCtx, pool: "Sequence[CandidateCtx]", weights: Weights) -> list[Relaxation]: ...
def acceptance_likelihood(need: NeedCtx, offer_salary_max: int, c: CandidateCtx) -> Literal["low", "medium", "high"]: ...
```

**How BE uses it:**
- **Start:** BE calls `start()`, then `next_family()`, then `generate(make_rng(...))`. It stores `view()` and `key`, and serves the view.
- **Answer:** BE calls `is_correct()`, then `record()`, then `next_family()`. When that returns `None`, BE calls `result()` and persists it.
- **League update:** BE calls `strength()` and `percentiles()` for the league and emits `league.updated`.
- **Pool:** BE runs the SQL prefilter, loads `CandidateCtx` in one batch, calls `score_pool()`, and paginates.

---

## 4. Task Checklist

IDs in parentheses refer to `docs/TASKS.md`. Acceptance targets come from ARCHITECTURE §5.3.

### P0: in this order

- [x] **ML-0 · Publish the contract with stubs** (F-07, MK3/MK4).
  - Create the packages from §2 with the §3 types.
  - `StubCatEngine`: serves 8 items, θ = (correct − 4)/2, decision against the claimed cut.
  - Stub `score_pool`: move the current `scoring.py` formula onto the DTOs, return the final shapes, and add a chip for every component.
  - Stub `fsp_boost`: `min(15, 5·n)`. `percentiles` can be real immediately.
  - *Done:* BE can replace `engine.py`/`scoring.py` calls with no API shape change, and `tests/ml` is green.
  - **Done (branch `ml/ML-0-contract`):** packages from §2 exist. `assessment/engine.py` became the package `engine/`, and `engine/legacy.py` re-exports `FAMILIES_REGISTRY`/`score_assessment` for BE until N2. `tests/ml/test_contract.py` has 58 tests: an AST purity scan that resolves relative imports, an AST check for global RNG, enum constants against `core.enums`, an HMAC golden for `make_rng` pinned to a literal, a lossless `CatState` JSON round trip with `"v": 1`, the stub engine, presets, Σ contributions = score, and hand-computed mid-rank percentiles. Contract additions with defaults (decisions D1–D4 in §8): `CatState.seen`, `CatState.blueprint` + `start(..., blueprint=None)`, `CandidateCtx.microtask_dates`, weights rescaled to Σ = 100. The full suite passes on Postgres.
- [x] **ML-1 · Fix the 3 live families and build the harness** (AI-02; fixes ML-F1).
  - Make every key depend on the drawn parameters.
    - **SQL:** randomize the count of matching departments (0..N) and the table data, and compute the answer with an in-memory `sqlite3` oracle.
    - **JS event loop:** randomize the sequence of `log`/`setTimeout`/`Promise.then`/`queueMicrotask`, and compute order with a small simulator; CI runs the real Node oracle.
    - **Complexity:** more loop shapes.
  - Fingerprint the parameters, not the seed.
  - `python -m assessment.families.verify --n 1000` checks: the oracle agrees with the key, exactly one option is correct, options are distinct, rendering works, the collision rate is ≤ 0.1%, and **answer-text entropy > 1 bit** (no constant keys).
  - *Done:* the 3 families pass; a deliberately broken family fails.
  - **Done (branch `ml/ML-1-families-harness`):** `be.sql.group_having.v2` (sqlite3 oracle; distractors are answers of independent redraws plus a misconception on 15 % of items), `fe.js.event_loop.v2` (simulator oracle, checked by real Node on 200 instances; distractors are misconceptions or structured orders, and the answer's centrality rank is uniform), `sh.algo.complexity.v2` (17 shapes, ≥ 2 per class; six fixed Θ options; AST-instrumented iteration-count oracle with an allow-list and fit-quality gates). `verify --n 1000`: 3/3 pass, 0 collisions. The harness gates **guessing from the options alone** (D6). Two review rounds measured option-only leaks of 58–69 % and a junior-knowledge leak of 59 %; the families were rebuilt, and every strategy is now at chance + ≤ 0.02. The oracle gets a key-less copy, None or an echo fails, `n ≥ 100` is enforced, and unknown ids are rejected. `tests/ml/test_families.py` covers 15 deliberately broken families (each rejected for the stated reason), hand-derived oracle goldens, a junior-knowledge test for the event loop, and cross-`PYTHONHASHSEED` determinism. The legacy registry serves the v2 families (ML-F1 closed for BE's current path).
- [x] **ML-2 · Content files.**
  - `content/specializations.yaml`: topics per spec.
  - `content/grades.yaml`: id, Russian descriptor, θ cut, rating cut. Resolve the cut-score mismatch (ML-F2).
  - `content/blueprints.yaml`: topic quotas per spec.
  - BE serves these via `GET /api/taxonomy`, and FE shows the grade descriptors.
  - **Done (branch `ml/ML-2-content`):** `content/grades.yaml` (cuts −1/0/+1 plus the intern floor −2, rating cuts 600/800/1000/1200, start θ, Russian descriptors; D7), `content/specializations.yaml` (24 topics with specs and skill ids, all in `skills.yaml`), `content/blueprints.yaml` (weights per spec, Σ = 1). `assessment.engine.content.load_content()` validates them: order, monotone cuts, rating = 1000 + 200θ, topics in their spec, sums, missing topics. 9 malformed-file tests. `blueprint_for` is real, with hand-computed goldens, and `parse_jd` returns it end to end. The verify harness checks that each family's topic exists and serves its specs. `item_level`/`band_of` read the cuts from the file. BE request in BE.md §2.4 (taxonomy).
- [x] **ML-3 · CAT/IRT engine** (AI-03; fixes ML-F2, ML-F3).
  - Fixed-c 3PL with EAP (61-point quadrature, N(0,1) prior) and Fisher information.
  - **First item** targets the claimed grade's cut. Scoring always uses the neutral prior, so claiming high never inflates θ.
  - **Selection:** max information under blueprint quotas, randomesque top-5 using `rng`, preferring unseen families.
  - **Stopping:** at ≥10 items when SE ≤ 0.30 or the 95% CI clears the cut; hard cap 20. Express mode stops at 8 items.
  - **Policy:** confirmed if θ ≥ cut(claimed); promotion if P ≥ 0.9; fallback grade if P ≥ 0.8; topic evidence; rating = 1000 + 200θ.
  - *Done:* tests cover all-correct, all-wrong, alternating and seed reproducibility; `CatState` round-trips through JSON; it replaces the stub with no API change.
  - **Done (branch `ml/ML-3-cat-engine`):** `engine/irt.py` (3PL, Fisher information, 61-point EAP with neutral N(0,1) prior in log space, tail probability from the same grid with bin fractions), `engine/policy.py` (cuts from `grades.yaml`, confirm / promotion P ≥ 0.9 / fallback P ≥ 0.8, rating 1000 + 200θ), `engine/topics.py` (observed vs expected score at the reference cut, D9), `engine/cat.py` (`IrtCatEngine`: first item at `start_theta`, max information under blueprint quotas ⌊w(n+1)⌋+1, randomesque top 5 through `rng`, unseen families preferred, stop rules 10/20/SE 0.30/95 % CI/express 8, `stop_reason`, completeness D8). The stub is gone; the signatures are unchanged. `tests/ml/test_cat.py` has 31 tests: EAP, information and tail probability against an independent pure-Python reference (1e-9); hand-derived policy and topic goldens; all-correct, all-wrong and alternating runs; neutral prior (claiming high never raises θ̂); first-item targeting; exposure spread of the first item (≤ 30 % from top 5); quota invariants at every step over 20 sessions; seed reproducibility with a JSON round trip after every call; late or pending items scored wrong; pool exhaustion; screening blueprints. BE wiring request in BE.md §2.4 (N2). Accuracy, retest, length and exposure on simulees are measured in ML-8.
- [x] **ML-4 · Matching scorer & strength** (AI-05; fixes ML-F4, ML-F5).
  - **Hard-filter reference:** spec, grades (+adjacent), formats.
  - **Features:**
    - SkillFit = Σ w·evidence / Σ w, with must w=2 and nice w=1. Evidence: test 1.0 (scaled by topic level), FSP or micro-task 0.8, declared 0.4, related skill 0.5 × evidence.
    - GradeFit: exact and confirmed 1.0, exact and unconfirmed 0.6, adjacent 0.5.
    - SalaryFit: overlap of the ranges after gross↔net normalization with the NDFL scale (verify the current 2025+ progressive brackets).
    - SemanticFit: 0.5 while embeddings are off (MK8).
    - Freshness.
  - **Presets:** balanced, skills, budget.
  - **Explanations:** every component yields a chip; `gaps` lists missing must-haves; Russian texts.
  - **Strength:** 0.85·Base + FSP Boost, where Base = 0.75·θ-percentile + 0.15·activity + 0.10·freshness. FSP Boost = 12·(1 − e^(−R/2)) + rank bonus (cat1 +1, KMS +2, MS +3), with placement weights 1.0/0.7/0.4/0.15 and participation capped at 0.6.
  - **Fairness:** unconfirmed candidates are ranked ×0.75, and no FSP means a boost of 0.
  - *Done:* golden tests on hand-ranked fixtures pass; `fsp_boost` is idempotent; Σ contributions equals the score.
  - **Done (branch `ml/ML-4-matching`):** `matching/engine/features.py` (SkillFit by skill id with must = 2 / nice = 1, test × topic level, FSP or micro-task 0.8, declared 0.4, related 0.5×; GradeFit exact 1 / adjacent 0.5 (D13); SalaryFit = mean affordability over the expectation, on gross; SemanticFit 0.5 while off; Freshness 30-day half-life), `score.py` (weights rescaled to 100, unconfirmed ×0.75 through the effective weights, a Russian chip for every component, `gaps` = display names of must-haves without direct evidence, presets balanced / skills / budget), `strength.py` (Strength = min(100, 0.85·Base + Boost), Base = 0.75·pct + 15·activity + 10·freshness, FSP Boost = 12(1 − e^−R/2) + rank bonus; idempotent on duplicates, ignores future dates), `salary.py` (2025+ NDFL scale 13/15/18/20/22 % at 2.4/5/20/50 M, marginal; verified on nalog.gov.ru 02.10.2026 and consultant.ru; source cited in the module), and `verified_skills()` in `assessment/engine/topics.py`. `tests/ml/test_matching.py` has 40 tests: the FNS example (3 M ₽ → 402 000 ₽ tax), bracket edges and a round trip; hand-derived goldens for boost, Strength, every feature and a full score (83.3 → 62.475 when unconfirmed); a hand-ranked pool whose Strength values are computed by `strength()` over one league, including cross-property checks (an unconfirmed candidate with verified must-haves beats a confirmed one with none, a strong non-FSP beats a weak FSP medallist, FSP moves a score by ≤ 3 points); a fresh-interpreter check that the engines load no Django; a hand-ranked pool where each pair differs in one property; presets moving the order as named; determinism. D10 in §8. BE requests in BE.md §2.4.
- [x] **ML-5 · Report schema and fixture early** (AI-10 part 1, MK9).
  - `validation/out/report.fixture.json` with `"synthetic_fixture": true`, exactly matching `ValidationReport` in `TASKS.md` §1.4.
  - *Done:* BE serves it at `GET /api/lab/report`, and FE2 renders the Lab with a red FIXTURE banner.
  - **Done (branch `ml/ML-5-report-schema`):** `validation/schema.py` (`validate_report`: exact key sets, types, ranges, a 4×4 confusion matrix, equal-length TIF arrays) and `validation/out/report.fixture.json` (`synthetic_fixture: true`, neutral placeholder values with `simulees: 0`, so no number can be mistaken for a result). `tests/ml/test_report_schema.py` parses the TypeScript `ValidationReport` out of `docs/TASKS.md` and asserts that its key set equals the schema's. The fixture validates, and 10 malformed variants are rejected. ML-8 writes `report.json` through the same validator.
- [x] **ML-6 · Family content to M1** (AI-04).
  - At least 15 families per spec (shared algorithm families count for every spec), mixing all 6 formats, with author priors for `b` (bookmark standard-setting, PD-07).
  - **Use the AI engineer's LLM-drafted families as input** (AI.md, AI-DRAFT); you review them, and the harness gates them.
  - *Done:* `verify` is green; a topic × grade-band coverage table is in the docs.
  - **Done (branch `ml/ML-6-content-m1`):** 48 families. Per spec: backend 25, frontend 20, ML & Data 27 (shared families count for all three), covering every blueprint topic. `verify --n 1000`: 46/46 pass. The coverage table and catalogue are generated into [docs/ml/item-bank.md](docs/ml/item-bank.md) by `python -m assessment.families.catalog`; a test keeps it current. Three builder bases (`families/builder.py`): typed numeric answers (c = 0), classification with a fixed option set, and redraw distractors. Oracles are independent of the generators: sqlite3 for SQL, executing the shown Python, simulators for event loops, schedules and asyncio, a selector-specificity counter, a structural TS checker, a line-repair find-the-bug oracle, numpy, and Fraction arithmetic. Every JS family is also checked against real Node; Node caught an operator-precedence bug in both Python models of `fe.js.coercion` before merge. Each family docstring justifies its `b` prior. Formats: backend and ML & Data use all 6; frontend uses 5 (no `sql_result`: no frontend topic is SQL, by design). **AI-DRAFT:** AI.md AI-8 (LLM-drafted families) has not been delivered, so there was nothing to review; when drafts arrive they go through the same harness and the item-family review checklist. **Known weakness:** the intern and senior bands are thin (frontend has 1 intern and 1 senior family), and concept families get their uniqueness from cosmetic context (ids, resource names) rather than from the reasoning. ML-8 measures what this costs.
  - **Review follow-up (branch `ml/ML-6-review-fixes`, D14):** the post-merge review blocked six redraw families whose distractors contradicted the code (shortcut accuracy 0.42–0.93), a process-wide `redirect_stdout` in `run_python` that gave wrong keys under threads, rounding-tie keys that rejected half-up answers, typed families where one answer was right on 13–55 % of items, contestable keys (heappush as Θ(log n), a 409 'unique code' scenario, epochs for k-NN), grammar slips, and fingerprints over decoration. Fixed: item-derived distractors with similarity-balanced subsets; a per-call `print`; exact keys with tie-safe tolerance; eight families redesigned with v2 ids (three now typed); isolation_anomaly b 1.1 → 0.4, littles_law 0.8 → 0.6 (worker variant dropped); semantic fingerprints. The harness gained the typed modal gate (≤ 10 %), item-consistency strategies and semantic fingerprint checks. `verify --n 1000`: 48/48 pass. Tests: thread safety, rounding ties, hint grammar, semantic fingerprints, balanced picks, and two new broken-family probes.
- [x] **ML-7 · Synthetic world** (AI-09).
  - Latent skills and θ per candidate.
  - Observables:
    - declared skills with inflation and omissions;
    - CAT results simulated through the real engine;
    - FSP history for ~35% (correlated with θ), in the ARCHITECTURE §2.8 registry contract format;
    - salaries by grade and city; formats.
  - 12 companies, 60 positions, CV texts, and the hero personas (Anna, Alex, Ivan…) injected.
  - Output to `seed_data/full/*.jsonl` with the schema in `seed_data/README.md`. The hidden truth goes to `validation/data/truth.jsonl`.
  - *Done:* deterministic per seed; BE's `seed --mode=full` loads it in < 60 s; BE's `fsp-id-mock` serves the FSP part.
  - **Done (branch `ml/ML-7-synthetic-world`):** `python -m validation.synth --seed 2026` runs in about 18 s. It writes `seed_data/full/{candidates,assessments,leagues,fsp_registry,companies,positions}.jsonl` and `manifest.json` (sha256 per file), with the schema in [seed_data/README.md](seed_data/README.md), and the hidden truth to `validation/data/truth.jsonl`. Contents: 1,500 candidates (latent θ ~ N(0,1), per-skill proficiency, inflation), 1,397 qualified through the production `IrtCatEngine` on perturbed item parameters (`validation/simulate.py`, shared with ML-8), 483 with FSP history (32 %) correlated with θ in the §2.8 contract, 12 fictional companies (`.example` domains, no real brands) and 60 positions with JD texts. Strength comes from `strength()`, and the heroes are the README personas plus Ivan. `tests/ml/test_synth.py`: same seed gives a byte-identical world, no truth fields in public rows, schema and invariant 5 checks, percentiles reproduce the formula, the FSP contract, FSP correlates with θ, inflation and omissions are present, and the hero stories hold in the shipped seed. BE request (N8) in BE.md §2.4. **Finding:** even a true θ = 2.0 senior fails the claim in about 15 % of seeds, because the bank has few hard items; ML-8 quantifies this.
- [ ] **ML-8 · Validation suite** (AI-10 part 2).
  - `sim_assessment.py` (10k simulees): exact and adjacent accuracy, QWK, retest same-grade and r, TIF, median length, maximum family exposure, collision rate, leak attack (10/30/50% leaked, static bank vs parametric), and girth recovery.
  - `bench_matching.py`: a relevance oracle (0–3) from the hidden truth; 5 systems (keyword, BM25, embeddings-only, ours without verified evidence, ours); nDCG@10, P@10, R@50, MRR, non-FSP parity, latency.
  - Charts; `python -m validation.run` in under 10 min.
  - *Done:* a real `report.json` with `git_sha` is committed at M2. **Report misses honestly.**

### P1

- [x] **ML-9 · Embeddings** (AI-11).
  - Use `deepvk/USER-bge-m3` on CPU, baked into the image.
  - Profiles and positions are embedded on seed and update; BE provides the pgvector field, the HNSW index and the trigger points.
  - SemanticFit goes live with `EMBEDDINGS=local`.
  - Pool p95 stays under 300 ms.
  - **Done:** `apps/matching/engine/embeddings.py` (pure engine: `embed_text`, `embed_batch`, `candidate_embedding_text`, `need_embedding_text`, CPU USER-bge-m3 support with deterministic L2-normalised pseudo-embedding fallback for test/offline environments), `docs/MODELS.md` register updated, `BE.md` N7 request updated. Tests in `tests/ml/test_embeddings.py` (9 tests, pool latency < 100 ms). SemanticFit in `features.py` fully operational when vectors are present.
- [x] **ML-10 · Counterfactual relaxations and acceptance likelihood** (AI-12, non-LLM part).
  - Top 3 relaxations by delta; low/medium/high likelihood from the salary ratio, format fit, status and responsiveness.
  - **Done:** `apps/matching/engine/relax.py` (`relaxations`: evaluation of must-skills, adjacent grades, work formats, salary budget; top 3 sorted by delta desc with deterministic tie-breaks; `acceptance_likelihood`: multi-factor scoring with salary interpolation, format conflict guard, responsiveness and league status). 10 unit tests in `tests/ml/test_relax.py`.
- [x] **ML-11 · Leak and drift monitor + calibration** (AI-13).
  - Observed vs expected correct rate per θ band, flags, retiring families with a < 0.6, and a girth recalibration job. BE schedules it in Celery beat and exposes `GET /lab/families`.
  - **Done:** `apps/assessment/engine/monitor.py` (`analyze_family`, `recalibrate_family`, `monitor_families`: observed vs expected 3PL rates across 4 θ bands with standardized residuals, anomaly detection for `leak_suspected`, `content_drift`, and `low_discrimination`, MAP recalibration of IRT parameters, status recommendation active/flagged/retired, and JSON export for `GET /lab/families`). Tests in `tests/ml/test_monitor.py` (6 tests).
- [ ] **ML-12 · Test Twins and screening blueprints** (AI-14). Turn a position into a blueprint and generate two instances of the same blueprint; FE2 renders them side by side.
- [ ] **ML-13 · Content to final** (AI-15). At least 40 families per spec, a promotion blueprint, and retirement of weak families.
- [ ] **ML-14 · Pilot and annotation analysis** (AI-16). Known grade vs result, retest, κ on 300 pairs, oracle-vs-human Spearman, all into the report.

---

## 5. Interfaces With Other Streams

| With | You give | You need |
|---|---|---|
| **BE** | The §3 contract, a stub first; `active_metas()` for `sync_families`; content YAMLs; `seed_data/full/`; report files | `ItemFamily` sync, `CatState` persistence, deadline enforcement, the `CandidateCtx` batch loader, `recompute_league()` trigger points, pgvector (P1), Celery beat for the drift monitor (P1) |
| **AI** | `blueprint_for()` for JD parsing; review of LLM-drafted families | `content/skills.yaml` ids (your `FamilyMeta.skills` reference them); drafted family candidates. The matching engine reads `taxonomy.loader.load_skills()` (names and `related`, used as an undirected graph). It must stay pure; `tests/ml/test_matching.py::test_engines_import_no_django_even_transitively` checks this in a fresh interpreter |
| **FE2** | `report.json` in the `ValidationReport` shape; `ItemView.level` / `max_items` semantics; `components`/`reasons`/`gaps` semantics | — |
| **FE1** | `CatResult` field semantics for the result screen (rating ± CI, topics, evidence, fallback, promotion) | — |

---

## 6. Docs You Own

- `docs/BACKEND.md` §4.1–§4.3 (item families, IRT, grade immutability) and §5 (scoring and ReasonChips). These sections currently describe 3PL EAP and nice-skill weights that don't exist; rewrite them to match the shipped engine and formulas.
- The methodology sections (docs 02–04: assessment, matching, validation), including the topic × grade coverage table and the standard-setting notes.
- An entry for `USER-bge-m3` in the model usage register (the AI engineer maintains the register).
- `seed_data/README.md` (schema) and `validation/README.md` (how to reproduce every number).

## 7. Working Agreements

- Unit tests use fixed seeds and run with **no DB** (`pytest tests/ml`). Every formula has a golden test.
- No LLM calls anywhere on the grading or scoring path.
- Small PRs (under ~400 lines), titled with the task ID (`ML-3 CAT engine`).
- If you need a model or endpoint change, write it into BE.md §2 as a request rather than editing Django code.

## 8. Decisions Log

Decisions taken while implementing this file. Each one is referenced from the task that introduced it.

| ID | Decision | Why |
|---|---|---|
| D1 | `CatEngine.next_family` appends a pending entry (`correct: None`) to `state.administered` and returns the same family if it is called again before `record`. `result()` scores any still-pending entry as incorrect (`late`). | `record()` only receives a family id, so the state must already know the item's a/b/c/topic. Retries are safe. A candidate who ends a session on a hard item can't skip it. |
| D2 | `CatState` serializes `"v": 1`. New fields are optional and read with `.get`, and `from_json` refuses a newer version. Optional fields: `seen` (family ids from earlier attempts), `blueprint` (screening quotas, passed to `start(..., blueprint=None)`, validated against the spec's topics, duplicates merged) and `stop_reason`. `CatResult` gained `complete` and `stop_reason` (with defaults). `result()` never mutates the state and applies the stop rules itself, so the call order doesn't matter. | BE stores the state in JSONB across deploys. A screening test (ML-12) needs its own topic quotas without a signature change. |
| D3 | `make_rng` seeds `random.Random` with the full 256-bit HMAC digest. It refuses an empty secret, and `n` is the item `seq` (generation) or the selection step (`"select"`). | With an empty secret, seeds could be computed from the session id. With `n = seq`, re-serving an item renders the same instance. |
| D4 | `score_pool` rescales any `Weights` to Σ = 100 (`Component.weight` is the effective weight), so the score stays in 0..100 and Σ contribution = score exactly (no rounding inside the engine). | Sliders and `Position.weights` can sum to anything. Rounding is left to the presentation layer. |
| D6 | **Option-only guessing gate.** The verify harness runs test-wise strategies that never read the item: longest or shortest option, most or least similar to the others, value rank (numeric options), the most frequent answer for a repeated option set (cross-validated, scored over all items), and the per-value correct rate and closeness to the typical answer (both cross-validated), and the order closest to the others (sequence options). A family fails if any strategy beats c by more than max(0.05, 4·√(c(1−c)/n)): c + 0.055 at n = 1000, under 1e-3 false alarms over all strategies. Families fix leaks by construction: distractors drawn from the answer's own distribution, a fixed option set with a uniform answer class, and distractor triples chosen for a uniform centrality rank. | The 3PL fixes c = 1/k. If options leak the answer, the real guessing rate is higher and θ̂ is inflated for guessers. No human reviews the content, so the gate must catch this. |
| D7 | **Cut scores (ML-F2):** −1 / 0 / +1 between intern, junior, middle and senior, as ARCHITECTURE §2.5 documents, not the code's −1.0/−0.2/0.6/1.5. Intern has a floor of −2 (rating 600): an intern claim is confirmed iff θ̂ ≥ −2. The first item targets `start_theta` (the claimed cut; −1.5 for intern). Item levels and result grades use only the three separating cuts. | The documented cuts are symmetric on the N(0,1) population scale (16/34/34/16 %), and no data backed the old numbers. Without a floor an intern claim could never fail, and the fallback "highest lower grade with P ≥ 0.8" would always offer intern with no evidence. The legacy `score_assessment` keeps its own numbers until BE swaps in `CatEngine` (its lifecycle tests pin them). |
| D8 | **Completeness.** A session may confirm a grade (or offer a fallback) only when a stop rule ended it (`stop_reason`). Running out of families counts only after `min_items` answers. A session BE ends early (finish, abandon, expiry) is scored, but `decision` is `unconfirmed` and `fallback_grade` is None. | θ̂ from 3 answers can sit above a cut by luck. BE's H6 already refuses instant fallback for abandoned sessions; the engine now says the same thing. |
| D9 | **Topic evidence** compares the topic's observed score with the expected score of a borderline candidate at the reference cut: z = (O − E)/√ΣP(1−P); strong if z ≥ 0.5 (and ≥ 2 items), limited if z ≤ −1. The reference is the claimed grade if confirmed, else the result grade. | A posterior θ_T with a leave-topic-out prior was tried first: with 2–3 items the prior dominated, and 0/3 correct could read "strong". |
| D10 | **Matching semantics.** (a) The ×0.75 for unconfirmed (any status other than `confirmed`) multiplies the effective weights, so Σ contribution = score still holds and a chip states it (see D13). (b) SalaryFit is asymmetric and continuous: affordability f(x) = 1 up to the budget max, falling linearly to 0 at 125 % of it; SalaryFit is the mean of f over the expectation range, or f of a single amount. The first version had a 1.0 → 0.5 cliff for 1 ₽ (ML-4 review). Expectations below the budget score 1, since the employer can afford them. (c) Related-skill evidence is max(direct, 0.5 × best related direct evidence), with the graph from AI's `skills.yaml` treated as undirected. (d) Activity uses accepted micro-task dates (`CandidateCtx.microtask_dates`, added with a default in ML-0, one entry per task, same-day tasks all count): 1 − exp(−Σ 0.5^(age/90)). (e) NDFL: steady monthly salary, one employer, no regional coefficients. | The spec gives the weights and evidence factors but not these shapes. Each choice is the simplest monotone rule that an employer can read from the chip. |
| D11 | **Confirmation uses the EAP under the N(0,1) prior, as specified, and the shrinkage is accepted and measured.** The ML-3 review simulated about +0.24 bias at the junior cut and −0.23 at the senior cut: a true θ = 1.2 senior is confirmed 44.5 % of the time on a synthetic 60-family pool. Under an N(0,1) population, deciding on the posterior is Bayes-optimal for overall accuracy, and the neutral prior is what keeps a high claim from inflating θ̂. The cost is that per-grade error is asymmetric for short tests. ML-8 reports P(confirm \| true θ) at each cut ± 0.2. If that curve is unacceptable, the lever is a flatter decision prior (`posterior(..., prior_sd=…)` already exists) together with longer tests, decided on simulation evidence and never tuned on the evaluation set. | The spec fixes the prior. Changing the decision estimator is a product decision about the trade-off between fairness to rare high performers and overall accuracy, so it should be made on the ML-8 numbers. |
| D12 | **Blueprint quotas are two-sided.** The ceiling is count < ⌊w(n+1)⌋+1, and the floor comes from Kingsbury–Zara with slack: only topics within 0.5 item of the largest deficit w(n+1) − count compete on information. Measured on 200 synthetic 20-item sessions: all 11 backend topics covered, and no topic more than one item below ⌊w·n⌋ at any step. | ARCHITECTURE: "the fixed category blueprint keeps grades comparable". A ceiling alone left topics uncovered (median 9 of 11). |
| D13 | **One penalty for an unconfirmed grade.** The whole score is ranked ×0.75 (invariant 4), and GradeFit is 1.0 for the exact grade whether or not it is confirmed; the chip says it is unconfirmed. This supersedes the spec's GradeFit 0.6 for unconfirmed. | With both penalties, an unconfirmed candidate with every must-have verified by test ranked below a confirmed candidate with **no** relevant skills (ML-4 review: 55.5 vs 55.6). A test now pins the opposite. |
| D5 | `percentiles` is the mid-rank: 100·(#below + ½·#equal)/N, with the candidate inside the league list. NaN raises. | Ties share a value, and a single member gets 50. |
| D14 | **ML-6 review: what an item is, and how it is keyed.** (a) The fingerprint hashes the family's `SEMANTIC` parameters; decorative fields (names, request ids, contexts, ETags) are left out, so the collision rate counts real repeats. The harness checks same content ⇒ same fingerprint and same fingerprint ⇒ same answer. Classification (concept) families have a handful of questions by design (label × template); they are exempt from the collision gate, and their rate is reported (e.g. op_cost 98 %, fit_diagnosis 75 %, find_bug 41 %). (b) Typed keys keep the exact value (to 1e-9), and an answer is right within half a unit of the requested rounding, so both neighbours of a rounding tie count. (c) Typed families: no single answer may be right on more than 10 % of items, because c = 0 must hold. (d) Choice distractors come from the item's own parameters (`alternatives`), and the subset is chosen so that the answer's similarity rank is uniform (`balanced_pick`). The harness adds item-consistency strategies (numbers absent from the item, numbers shared with it, the modal count of numbers). (e) A semantic change bumps the version and the id: `bm.sql.left_join_count.v2`, `bm.sql.not_in_null.v2`, `fe.react.effect_runs.v2`, `sh.code.binary_search_steps.v2`, `sh.code.recursion_calls.v2`, `bm.py.mutable_default.v2`, `ml.data.broadcast.v2` and `fe.js.coercion.v2`. The last three became typed: every set of derived distractors still left some option-only strategy above chance. | The ML-6 review measured option-only shortcuts at 0.42–0.93 on six redraw families, half-up answers rejected on rounding ties, and constant answers right on 13–55 % of typed items. |
