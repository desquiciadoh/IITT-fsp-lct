# Validation suite (`validation/`)

Owner: ML (ML-5, ML-7, ML-8, ML-14). Everything here imports the production engines and never Django.

```bash
python -m validation.synth --seed 2026     # the synthetic world: seed_data/full/*.jsonl + validation/data/truth.jsonl
python -m validation.run                    # the full suite (about 3 minutes; the target is < 10)
python -m validation.run --fast             # smoke run (about 20 s)
```

`validation.run` writes:

- `out/report.json`: the `ValidationReport` (TASKS.md §1.4). It is schema-validated before it is written. `git_sha` is the commit that was measured, with `-dirty` when the tree differed. There is no fallback SHA.
- `out/details.json`: everything the fixed schema has no room for. That covers the §5.3 target table (PASS/MISS), standard errors, base rates, the per-family bank statistics, the leak-attack details and the calibration recovery.
- `out/charts/*.svg`: the confusion matrix, the test information function, the leak attack and the matching comparison.

A run that misses targets still exits 0. Misses are results, and the table prints them.

## Method

**Synthetic world (`synth.py`, ML-7).** There are 1,500 candidates with latent θ ~ N(0, 1) and per-skill proficiency. Exposure to a skill grows with θ. Declared skills show omissions and inflation. Every tested candidate takes a session on the production `IrtCatEngine`. The answers use *true* item parameters, which are the authored ones perturbed once (a × U(0.8, 1.2), b + N(0, 0.2)), so the engine is never graded against its own assumptions. An item's effective ability is θ + 1.0·(share of its skills the person has − the share expected at θ). This term is zero-mean given θ, so a test verifies skills the person actually has. Personas (heroes) are demo scripts: their sessions are honest draws, and `tests/ml/test_synth.py` checks that each story holds on ≥ 85 % of 60 sessions.

**Assessment (`sim_assessment.py`).**

- 10,000 simulees, unidimensional answers, a claim of θ + N(0, 0.35).
- Accuracy is the result grade against the band of the true θ. QWK uses quadratic weights.
- Retest: 2,500 simulees take a second independent session with the same claim.
- Exposure is the share of a spec's sessions that served a family; the report gives the maximum over specs.
- Collision rate and generator errors come from the verify harness at 1,000 instances per family. Concept families have few questions by design and are reported apart.
- **Leak attack:** 300 cheaters per share claim one band above their true grade. In the static-bank arm a leaked item is always answered right. In the parametric arm the cheater holds 20 leaked instances per leaked family and is right only when a fresh instance repeats one of those questions; otherwise they answer honestly. The honest and cheating runs share each session id (common random numbers). The leaked sets are nested prefixes of a permutation, averaged over two permutations.
- **Calibration recovery:** the ML-11 recalibration runs on simulated responses (θ̂ with SE 0.35, likelihood integrated over the posterior of θ) at 200, 600 and 2,000 responses per family.

**Matching (`bench_matching.py`).**

- 60 positions. Every system ranks the same pool: the specialisation after the production hard filters.
- The relevance oracle reads only the hidden truth: 0.65 × skill fit + 0.35 × grade fit, with relevance 3/2/1 at 0.70/0.50/0.30. These numbers were fixed before any system was scored and were never tuned.
- Systems:
  - keyword (declared skills);
  - BM25 (CV text);
  - an embedding baseline (USER-bge-m3 when installed, otherwise the lexical hash backend, named `hashed_ngram`);
  - `ours_no_verified` (the production scorer on declared information only);
  - `ours` (the production scorer, the position's preset, embeddings off as in production).
- Metrics: nDCG@10 with gains 2^rel − 1 against the ideal ranking of the same pool; P@10 (relevance ≥ 2, divided by 10); R@50; MRR. Non-FSP parity is the top-10 exposure rate of relevant non-FSP candidates over that of relevant FSP candidates. Latency covers the filter plus `score_pool`.

## Results (seed 2026)

The numbers and the PASS/MISS table are in `out/report.json` and `out/details.json`; ML.md §4 (ML-8) quotes the last committed run. What they mean:

**Met.**
- 0 generator errors and a parametric collision rate ≤ 0.1 %.
- Adjacent accuracy ≈ 99 %.
- Parity ≥ 0.8.
- Scoring p95 ≈ 50 ms for a 180-candidate pool.
- The leak attack separates the arms clearly: a static bank inflates θ by about +0.9 at 50 % leaked, with about 69 % of cheaters over-graded.

**Missed, and why.**
- **Exact accuracy (~63 %), retest (~55 % same grade, r ≈ 0.76), median length 20.**
  - The bank's discriminations (a ≈ 1.0–1.4) cannot reach SE ≤ 0.30 within 20 items.
  - About two thirds of sessions stop at the cap, and grade bands are only 1 θ wide, so neighbouring bands are confused (adjacent accuracy is 99 %).
  - More discriminating families (ML-13) and calibration on real responses are the levers. Moving the cut scores is not.
- **Max family exposure ≈ 1.0.** With 20–27 families per spec and 20-item sessions, every session sees most families. Every exposure is still a unique instance; the ≥ 40 families per spec of ML-13 lower this.
- **Parametric leak Δθ ≈ +0.15 at 50 %.** It comes entirely from the concept families (isolation anomalies, HTTP methods and status codes, vulnerability classes, operation costs). Twenty leaked instances answer 64–100 % of their fresh instances. ML-13 retires them by this rule.
- **Ranking.**
  - On the same pool, keyword overlap on declared skills beats our scorer: nDCG@10 0.68 vs 0.54.
  - The ablation is negative: declared-only 0.60 vs full 0.54.
  - Two reasons, both reported rather than tuned away:
    1. In this world declared skills are a strong signal (generated from proficiency with 85 % recall).
    2. Our score also weighs things the competence oracle ignores (salary affordability, freshness, strength).
  - Fitting weights or the world to this oracle would be tuning on the evaluation set.
- **Calibration recovery.** At 200 responses per family the recalibrated a is worse than the authored prior (RMSE 0.18 vs 0.13). b improves from about 600 responses, and both a and b reach RMSE ≈ 0.07 at 2,000. The monitor reports estimates from 200 responses on, but recalibrated parameters should be applied only from about 600 responses for b and 2,000 for a (BE.md §2.4).

## Integrity

- No module here imports Django or the ORM.
- `truth.jsonl` is read only by `bench_matching.relevance`.
- Runs are deterministic from the seed, apart from `generated_at` and timing.
- `tests/ml/test_validation.py` pins hand-computed goldens for QWK, nDCG, P@10, R@50, MRR and the oracle. It also checks that the SHA has no fallback and that misses are reported.
