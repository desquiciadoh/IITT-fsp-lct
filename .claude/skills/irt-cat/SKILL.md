---
name: irt-cat
description: Psychometrics and ranking math for FSP Draft - 3PL IRT, Fisher information, EAP on a 61-point grid, CAT item selection with blueprint quotas and randomesque exposure control, stop rules, grade policy probabilities, rating scale, Monte Carlo validation, and ranking metrics (QWK, nDCG, MRR). Use when implementing or debugging apps/assessment/engine, apps/matching/engine or validation/, computing golden test values, or answering "why is θ/grade/score X".
---

# IRT / CAT / ranking reference

Spec sources, in priority order: `ML.md` §3 (contract) and §4 (ML-3, ML-4, ML-8), then `docs/ARCHITECTURE.md` §2.5, §2.6 and §2.12. If they disagree, `ML.md` wins; flag the conflict instead of picking silently.

A runnable reference implementation for golden values: `scripts/irt_reference.py` (numpy). Import its functions in a scratch script or run it to see sample outputs. Production code must not import it.

## Model

- **3PL, logistic metric (D = 1):** `P(θ) = c + (1 − c) / (1 + e^(−a(θ − b)))`. `c = 1/len(options)` for choice items, 0 for typed answers, and fixed (not estimated). If item `b` priors were set on a normal-ogive scale, use D = 1.702 everywhere; never mix.
- **Fisher information:** `I(θ) = a² · (Q/P) · ((P − c)/(1 − c))²`. With c > 0 it peaks at `b + ln((1 + √(1 + 8c))/2)/a`, slightly above b.
- **EAP:** grid of 61 points on [−4, 4], prior N(0,1) normalised on the grid. Sum log-likelihoods, add the log prior, subtract the max, exponentiate, normalise. θ̂ = posterior mean; SE = posterior SD. Clip P to [1e−9, 1 − 1e−9] before `log`. With no responses it returns (0, ≈1).
- **Neutral prior always.** The claimed grade picks only the first item (near cut(claimed)); it never shifts the prior, so claiming high can't inflate θ̂.
- **Late answers** are recorded as incorrect.

## CAT loop

1. **Start:** first item has b closest to cut(claimed), within blueprint quotas.
2. **Select:** filter the pool by unfulfilled blueprint quotas and not-yet-administered families. Prefer families unseen in earlier attempts. Score by `I(θ̂)`, sort by `(−info, family_id)` for deterministic ties, then pick uniformly from the top 5 with the passed `rng` (randomesque exposure control). Return `None` if the pool is empty.
3. **Stop** (check after each response): `n ≥ max_items (20)`; or `n ≥ min_items (10)` and (`SE ≤ 0.30` or the 95% CI `θ̂ ± 1.96·SE` lies wholly above or below the cut). Express mode: stop at 8.
4. **Result:**
   - `rating = round(1000 + 200θ̂)`, `rating_ci = round(1.96 · 200 · SE)`;
   - `confirmed` iff `θ̂ ≥ cut(claimed)`;
   - `promotion_unlocked` iff `P(θ ≥ cut(next grade) | data) ≥ 0.9`;
   - `fallback_grade` = the highest lower grade with `P(θ ≥ cut) ≥ 0.8`, else `None`;
   - compute P from the same posterior grid as θ̂, not a normal approximation, so the numbers agree;
   - cut scores are loaded from `content/grades.yaml` (ARCHITECTURE: −1 / 0 / +1 between intern|junior|middle|senior; the current code uses different values, see ML-F2).
5. **`item_level(meta)`:** the grade band that `b` falls into, using the same cuts.

Determinism checklist: all randomness from `rng` (`make_rng` = HMAC-SHA256(secret, `session_id|purpose|n`) → `random.Random(int.from_bytes(digest[:8], "big"))`); explicit tie-breaks; `sorted()` before iterating sets; `CatState` round-trips through JSON (floats as floats, not rounded strings).

## Matching and strength (ML-4)

- `SkillFit = Σ w·evidence / Σ w`. Must-have w = 2, nice-to-have w = 1. Evidence: test 1.0 (scaled by topic level), FSP or micro-task 0.8, declared 0.4, related skill 0.5 × its evidence.
- `GradeFit`: exact + confirmed 1.0, exact + unconfirmed 0.6, adjacent 0.5.
- `SalaryFit`: overlap of the ranges after gross↔net normalisation (NDFL brackets for 2025+; verify the current scale before coding it).
- `SemanticFit` = 0.5 while embeddings are off.
- Weights 35/20/15/15/10/5 (spec); presets balanced/skills/budget.
- The score is Σ weight·feature. Each component emits a Russian chip, and the contributions sum to the score. Unconfirmed ×0.75.
- **Strength** = 0.85·Base + FSP Boost, where Base = 0.75·θ-percentile + 0.15·activity + 0.10·freshness.
- **FSP Boost** = 12·(1 − e^(−R/2)) + rank bonus (cat1 +1, KMS +2, MS +3). Placement weights 1.0/0.7/0.4/0.15; participation capped at 0.6. No FSP ⇒ 0.

## Validation (ML-8)

- **Simulation:**
  - draw true θ per grade band;
  - simulate responses with `P(true θ)` from **perturbed** item parameters (a ×U(0.8,1.2), b +N(0,0.2)) while the engine uses the nominal ones;
  - run the real engine;
  - report exact/adjacent accuracy, a confusion matrix, QWK, retest r(θ̂₁, θ̂₂) and grade agreement, median length, max family exposure and the collision rate.
- **Leak attack:** a cheater knows 10/30/50% of (item, answer) pairs. With a static bank the leaked items are answered correctly; with parametric families a leaked answer doesn't match the new instance. Compare θ inflation and the false-promotion rate.
- **Ranking:**
  - nDCG@10 with gains `2^rel − 1` and discount `log2(i + 1)`; IDCG from **all** relevant candidates for the need, not just the returned list;
  - P@10 at rel ≥ 2; R@50; MRR at rel ≥ 2;
  - non-FSP exposure parity.
- **QWK:** weights `(i − j)²/(k − 1)²`, expected matrix from the marginals.
- Report misses honestly; fixture files carry `"synthetic_fixture": true`.

## Debugging "θ̂ looks wrong"

1. Recompute with `scripts/irt_reference.py` on the same `(a, b, c, correct)` list.
2. Common causes:
   - `c` applied to typed items;
   - `log(0)` without clipping;
   - prior centred on the claimed grade;
   - `late` treated as missing instead of incorrect;
   - SE taken from Fisher information (`1/√ΣI`) while the policy assumes posterior SD (pick one; the spec says EAP posterior SD);
   - grid not normalised;
   - a sign error in `a(θ − b)`.
