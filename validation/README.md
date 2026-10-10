# Validation Suite & Methodology (`validation/`)

This directory houses the validation suite for **FSP Draft** (tasks `ML-8`, `AI-10 part 2`).
It runs Monte Carlo simulation of the psychometric assessment engine and benchmarks candidate matching systems against a latent ground-truth oracle.

---

## 1. Quick Start

Run the full validation suite:

```bash
# Full run: 10,000 simulees on the production CAT engine, 60 positions benchmark
python -m validation.run

# Fast run (for quick smoke testing): 500 simulees, 10 positions
python -m validation.run --fast

# Custom parameters
python -m validation.run --simulees 10000 --positions 60 --seed 2026
```

### Outputs
- `validation/out/report.json`: Production validation report in the `ValidationReport` schema format (`synthetic_fixture: false`). Served by the backend at `GET /api/lab/report`.
- `validation/out/report.fixture.json`: Fallback fixture used before validation runs (`synthetic_fixture: true`).
- `validation/out/charts/`: High-resolution vector SVG charts:
  - `confusion.svg`: 4×4 classification confusion matrix across grade bands (Intern, Junior, Middle, Senior).
  - `tif.svg`: Test Information Function curve across latent ability $\theta$, highlighting cut scores.
  - `leak_attack.svg`: Cheater ability inflation comparison ($\Delta\theta$) between a static bank and parametric families.
  - `matching.svg`: Retrieval accuracy ($nDCG@10$, $P@10$) across 5 search and ranking baselines.

---

## 2. Assessment Simulation (`sim_assessment.py`)

### Methodology
Simulates 10,000 examinees with true latent ability $\theta \sim \mathcal{N}(0, 1)$ across Backend (45%), Frontend (35%), and ML & Data (20%).
Responses are generated using the production `IrtCatEngine` with item parameters perturbed once per seed ($a \times \mathcal{U}(0.8, 1.2)$, $b + \mathcal{N}(0, 0.2)$) to reflect real-world calibration uncertainty.

### Metrics Computed
- **Exact Accuracy (`exact_acc`)**: Fraction of simulees whose evaluated grade matches their true latent grade band ($\theta < -1.0$: Intern, $-1.0 \le \theta < 0$: Junior, $0 \le \theta < 1$: Middle, $\theta \ge 1$: Senior).
- **Adjacent Accuracy (`adjacent_acc`)**: Fraction of decisions within at most $\pm 1$ grade band.
- **QWK (`qwk`)**: Quadratic Weighted Kappa measuring chance-corrected agreement with quadratic distance penalties.
- **Retest Reliability (`retest_same_grade`, `retest_r`)**: Same-grade consistency and Pearson correlation $r(\hat{\theta}_1, \hat{\theta}_2)$ between two independent sessions per simulee.
- **Test Information (`tif`)**: Fisher test information $I(\theta) = \sum_{j} I_j(\theta)$ averaged across sessions, validating peak information at grade cut boundaries.
- **Leak Attack (`leak_attack`)**: Simulates attackers with memorized answer keys for 10%, 30%, and 50% of the item bank. Compares score inflation ($\Delta\theta$) under a static question bank vs parametric families where parameters and distractors are redrawn.

---

## 3. Matching Benchmark (`bench_matching.py`)

### Methodology
Evaluates candidate retrieval against an objective, non-circular **relevance oracle (0–3)** derived from latent ground-truth parameters in `validation/data/truth.jsonl`.
Candidates and positions are drawn from the synthetic world (`seed_data/full/`).

### Evaluated Systems
1. `keyword`: Baseline matching keyword overlap of declared resume skills against job requirements.
2. `bm25`: Classic BM25 probabilistic text retrieval between position description and candidate CV text.
3. `embeddings_only`: Semantic cosine similarity between position and candidate profile vector representations.
4. `ours_no_verified`: Our production matching engine without verified assessment/FSP evidence (all skills unconfirmed).
5. `ours`: Full production matching engine integrating CAT verified skills, FSP tournament boost, Profile Strength, and salary normalization.

### Metrics
- **nDCG@10**: Normalized Discounted Cumulative Gain at rank 10.
- **P@10**: Precision at rank 10 (fraction of top-10 candidates with relevance $\ge 2$).
- **R@50**: Recall at rank 50 (coverage of relevant talent in the pool).
- **MRR**: Mean Reciprocal Rank of the first relevant candidate.
- **Non-FSP Parity (`non_fsp_parity`)**: Exposure ratio of non-FSP candidates in top-10 recommendations, ensuring tournament achievements do not monopolize candidate discovery.
- **Latency (`pool_p95_ms`)**: 95th percentile latency of candidate pool scoring.

---

## 4. Integrity and Purity Invariants

1. **Pure Engine**: All modules in `validation/` import pure engine code (`assessment.engine`, `assessment.families`, `matching.engine`). They never import Django ORM models.
2. **Deterministic**: Every simulation and benchmark run is deterministic and fully reproducible from `--seed 2026`.
3. **Strict Schema**: `report.json` is validated by `validation.schema.validate_report()` before saving.
