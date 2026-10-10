"""ML-3: 3PL IRT, EAP, grade policy, topic evidence and the CAT loop.

Golden values come from an independent pure-Python reference below (math only, no numpy, no
import from the engine) or are derived by hand in the comments.
"""
from __future__ import annotations

import json
import math
import random
from collections import Counter

import pytest
from assessment.engine import irt
from assessment.engine.cat import CatState, IrtCatEngine, item_level
from assessment.engine.content import load_content
from assessment.engine.policy import decide
from assessment.engine.topics import topic_levels
from assessment.families.base import FamilyMeta
from assessment.families.registry import make_rng

C = load_content()

# ── independent reference implementation ───────────────────────────────────

REF_GRID = [-4.0 + 8.0 * k / 60 for k in range(61)]


def ref_p(theta, a, b, c):
    return c + (1 - c) / (1 + math.exp(-a * (theta - b)))


def ref_post(items, resp, mean=0.0, sd=1.0):
    logs = []
    for t in REF_GRID:
        lp = -0.5 * ((t - mean) / sd) ** 2
        for (a, b, c), u in zip(items, resp, strict=True):
            p = min(max(ref_p(t, a, b, c), 1e-9), 1 - 1e-9)
            lp += math.log(p if u else 1 - p)
        logs.append(lp)
    m = max(logs)
    w = [math.exp(x - m) for x in logs]
    s = sum(w)
    return [x / s for x in w]


def ref_eap(items, resp, mean=0.0, sd=1.0):
    post = ref_post(items, resp, mean, sd)
    th = sum(t * p for t, p in zip(REF_GRID, post, strict=True))
    se = math.sqrt(sum((t - th) ** 2 * p for t, p in zip(REF_GRID, post, strict=True)))
    return th, se


def ref_tail(post, cut):
    h = 8.0 / 60
    total = 0.0
    for t, p in zip(REF_GRID, post, strict=True):
        hi = t + h / 2                       # upper edge of the bin centred on t
        total += p * min(1.0, max(0.0, (hi - cut) / h))
    return total


ITEMS6 = [(1.2, b, 0.25) for b in (-1.0, -0.5, 0.0, 0.5, 1.0, 1.5)]


# ── IRT ────────────────────────────────────────────────────────────────────

def test_p_and_information_by_hand():
    # θ = b: P = c + (1 − c)/2 = 0.625; I = a²·(Q/P)·((P − c)/(1 − c))² = 1.44·0.6·0.25 = 0.216
    assert float(irt.p_3pl(0.0, 1.2, 0.0, 0.25)) == pytest.approx(0.625)
    assert float(irt.information(0.0, 1.2, 0.0, 0.25)) == pytest.approx(0.216)
    # c = 0: I(b) = a²/4
    assert float(irt.information(0.7, 2.0, 0.7, 0.0)) == pytest.approx(1.0)


def test_information_peaks_slightly_above_b_when_c_positive():
    a, b, c = 1.5, 0.0, 0.25
    peak = b + math.log((1 + math.sqrt(1 + 8 * c)) / 2) / a          # closed form, ≈ 0.209
    xs = [peak - 0.01, peak, peak + 0.01]
    vals = [float(irt.information(x, a, b, c)) for x in xs]
    assert vals[1] > vals[0] and vals[1] > vals[2]


@pytest.mark.parametrize("resp", [[True] * 6, [False] * 6, [True, False] * 3, [False, True] * 3,
                                  [True, True, True, False, False, False]])
def test_eap_matches_independent_reference(resp):
    th, se = irt.eap(ITEMS6, resp)
    rth, rse = ref_eap(ITEMS6, resp)
    assert th == pytest.approx(rth, abs=1e-9) and se == pytest.approx(rse, abs=1e-9)


def test_eap_with_typed_items_and_a_single_item():
    items = [(1.0, 0.3, 0.0), (1.6, -0.2, 0.0), (0.8, 1.1, 1 / 6)]
    for resp in ([True, False, True], [False, False, True]):
        assert irt.eap(items, resp) == pytest.approx(ref_eap(items, resp), abs=1e-9)
    assert irt.eap(items[:1], [True]) == pytest.approx(ref_eap(items[:1], [True]), abs=1e-9)


def test_eap_without_data_is_the_prior():
    th, se = irt.eap([], [])
    assert th == pytest.approx(0.0, abs=1e-12)
    assert se == pytest.approx(ref_eap([], [])[1], abs=1e-12) and 0.99 < se < 1.0


def test_eap_is_monotone_in_correct_answers():
    thetas = [irt.eap(ITEMS6, [i < k for i in range(6)])[0] for k in range(7)]
    assert thetas == sorted(thetas) and thetas[0] < -0.8 and thetas[-1] > 0.8


def test_extreme_items_do_not_overflow():
    items = [(3.0, -3.5, 0.0), (3.0, 3.5, 0.0)] * 10
    th, se = irt.eap(items, [False, True] * 10)       # wildly inconsistent responses
    assert math.isfinite(th) and math.isfinite(se)


def test_tail_probability_matches_reference_and_moves_continuously():
    post = irt.posterior(ITEMS6, [True, True, True, True, False, False])
    rpost = ref_post(ITEMS6, [True, True, True, True, False, False])
    for cut in (-2.0, -1.0, 0.0, 0.05, 1.0, 1.0667):
        assert irt.prob_at_least(post, cut) == pytest.approx(ref_tail(rpost, cut), abs=1e-9)
    assert irt.prob_at_least(post, -10) == pytest.approx(1.0) and irt.prob_at_least(post, 10) == 0.0
    ps = [irt.prob_at_least(post, x / 100) for x in range(-100, 101)]
    assert all(b <= a + 1e-12 for a, b in zip(ps, ps[1:], strict=False))


# ── policy ─────────────────────────────────────────────────────────────────

def _post(resp, items=ITEMS6):
    return irt.posterior(items, resp)


def test_rating_and_ci_formula():
    d = decide(_post([True] * 4 + [False] * 2), "middle", True, C)
    assert d.rating == round(1000 + 200 * d.theta) and d.rating_ci == round(1.96 * 200 * d.se)


def test_confirmed_iff_theta_at_least_claimed_cut_and_complete():
    post = _post([True] * 5 + [False])
    th = irt.moments(post)[0]
    assert 0.0 < th < 1.0                                       # middle band
    assert decide(post, "middle", True, C).decision == "confirmed"
    assert decide(post, "senior", True, C).decision == "unconfirmed"
    assert decide(post, "middle", False, C).decision == "unconfirmed"          # incomplete (D8)
    assert decide(post, "middle", True, C).result_grade == "middle"


def test_promotion_needs_p_at_least_0_9_of_next_cut():
    strong = [(1.5, b, 0.25) for b in (0.5, 1.0, 1.5, 2.0, 2.5)] * 4
    post = irt.posterior(strong, [True] * 20)
    assert irt.prob_at_least(post, 1.0) >= 0.9
    assert decide(post, "middle", True, C).promotion_unlocked
    assert not decide(post, "middle", False, C).promotion_unlocked
    weak = _post([True] * 5 + [False])
    assert irt.prob_at_least(weak, 1.0) < 0.9 and not decide(weak, "middle", True, C).promotion_unlocked
    assert not decide(post, "senior", True, C).promotion_unlocked          # no grade above senior


def test_fallback_is_highest_lower_grade_with_p_at_least_0_8():
    post = _post([True, True, True, False, False, False])
    p = {g.id: irt.prob_at_least(post, g.theta_cut) for g in C.grades}
    d = decide(post, "senior", True, C)
    assert d.decision == "unconfirmed"
    expected = next((g for g in ("middle", "junior", "intern") if p[g] >= 0.8), None)
    assert d.fallback_grade == expected and expected is not None
    assert decide(post, "senior", False, C).fallback_grade is None          # abandoned: no fallback
    assert decide(_post([False] * 6), "intern", True, C).fallback_grade is None


# ── topic evidence ─────────────────────────────────────────────────────────

def _entry(topic, a, b, c, correct, seq=1):
    return {"family_id": f"f{seq}", "seq": seq, "a": a, "b": b, "c": c, "topic": topic,
            "correct": correct, "late": False}


def test_topic_levels_by_hand():
    # Middle (cut 0), items a=1.3 b=0.3 c=0.25: P(0) = 0.25 + 0.75/(1 + e^0.39) = 0.5529,
    # Var = P(1 − P) = 0.2472. Two items: E = 1.1058, sd = sqrt(0.4944) = 0.7031.
    #   2/2: z = (2 − 1.1058)/0.7031 = +1.27 -> strong; 1/2: z = −0.15 -> moderate; 0/2: z = −1.57 -> limited
    # One item answered correctly: z = (1 − 0.5529)/0.4972 = +0.90, capped at moderate.
    def adm(topic_resp):
        out, seq = [], 0
        for topic, resp in topic_resp.items():
            for u in resp:
                seq += 1
                out.append(_entry(topic, 1.3, 0.3, 0.25, u, seq))
        return out
    got = dict(topic_levels(adm({"a": [True, True], "b": [True, False], "c": [False, False], "d": [True]}),
                            "middle", C))
    assert got == {"a": "strong", "b": "moderate", "c": "limited", "d": "moderate"}
    # Senior (cut 1): P(1) = 0.25 + 0.75/(1 + e^−0.91) = 0.7848; 1/2: z = (1 − 1.5696)/0.5809 = −0.98
    assert dict(topic_levels(adm({"x": [True, False]}), "senior", C)) == {"x": "moderate"}
    # Junior (cut −1): P = 0.3670; 0/2: z = −0.734/0.6815 = −1.08 -> limited
    assert dict(topic_levels(adm({"x": [False, False]}), "junior", C)) == {"x": "limited"}
    assert topic_levels([_entry("p", 1, 0, 0, None)], "middle", C) == []        # pending ignored


# ── the CAT loop ───────────────────────────────────────────────────────────

def _pool(spec="backend", per_topic=6, seed=0):
    rng = random.Random(seed)
    metas = []
    for topic in C.topics_for(spec):
        for k in range(per_topic):
            metas.append(FamilyMeta(id=f"t.{topic}.{k}.v1", version=1, specs=(spec,), topic=topic,
                                    skills=("sql",), format="concept_mcq", a=round(rng.uniform(0.8, 2.0), 2),
                                    b=round(rng.uniform(-2.5, 2.5), 2), c=0.25, time_limit_s=90))
    return metas


def _run(engine, spec, claimed, mode, answer, session="s1", pool=None, seen=(), roundtrip=True):
    pool = pool if pool is not None else _pool(spec)
    state = engine.start(spec, claimed, mode, "initial", pool, set(seen))
    order = []
    while True:
        meta = engine.next_family(state, pool, make_rng(b"k", session, "select", len(state.administered) + 1))
        if roundtrip:
            state = CatState.from_json(json.loads(json.dumps(state.to_json())))
        if meta is None:
            break
        order.append(meta.id)
        state = engine.record(state, meta.id, answer(meta, len(order)))
    return state, order, engine.result(state)


def test_all_correct_all_wrong_alternating():
    eng = IrtCatEngine()
    st, order, res = _run(eng, "backend", "middle", "full", lambda m, k: True)
    best = res.theta
    assert res.decision == "confirmed" and res.theta > 1.0 and res.result_grade == "senior"
    assert 10 <= len(order) <= 20 and st.stop_reason in ("se", "ci", "max_items")
    assert res.promotion_unlocked
    st, order, res = _run(eng, "backend", "middle", "full", lambda m, k: False)
    assert res.decision == "unconfirmed" and res.theta < -1.0 and res.fallback_grade in (None, "intern")
    worst = res.theta
    st, order, res = _run(eng, "backend", "middle", "full", lambda m, k: k % 2 == 1)
    assert worst < res.theta < best and len(order) >= 10
    assert [e[0] for e in res.evidence] == list(range(1, len(order) + 1))
    assert all(e[1] == item_level(next(m for m in _pool() if m.id == fid)) for e, fid in zip(res.evidence, order,
                                                                                              strict=True))


def test_express_stops_at_eight_and_full_never_before_ten():
    eng = IrtCatEngine()
    st, order, _ = _run(eng, "frontend", "junior", "express", lambda m, k: True)
    assert len(order) == 8 and st.stop_reason == "express"
    for answer in (lambda m, k: True, lambda m, k: False, lambda m, k: m.b < 0.3):
        st, order, _ = _run(eng, "frontend", "junior", "full", answer)
        assert 10 <= len(order) <= 20


def test_stop_rules_by_hand():
    eng = IrtCatEngine()
    st = eng.start("backend", "middle", "full", "initial", [], set())
    entry = {"family_id": "x", "seq": 1, "a": 1, "b": 0, "c": 0, "topic": "t", "correct": True, "late": False}
    st.administered = [dict(entry, seq=i + 1, family_id=f"x{i}") for i in range(9)]
    st.theta, st.se = 2.0, 0.2
    assert eng.stop_rule(st) is None                      # 9 < min_items even with a tiny SE
    st.administered.append(dict(entry, seq=10, family_id="x9"))
    assert eng.stop_rule(st) == "se"
    st.theta, st.se = 0.7, 0.35                           # CI [0.014, 1.386] is above cut 0
    assert eng.stop_rule(st) == "ci"
    st.theta, st.se = 0.5, 0.35                           # CI [-0.186, 1.186] straddles 0
    assert eng.stop_rule(st) is None
    st.administered += [dict(entry, seq=i + 1, family_id=f"x{i}") for i in range(10, 20)]
    assert eng.stop_rule(st) == "max_items"


def test_neutral_prior_claiming_high_never_inflates_theta():
    eng = IrtCatEngine()
    pool = _pool()
    for claimed_low, claimed_high in (("junior", "senior"), ("intern", "middle")):
        lo = eng.start("backend", claimed_low, "full", "initial", pool, set())
        hi = eng.start("backend", claimed_high, "full", "initial", pool, set())
        for st in (lo, hi):                               # identical answered items, any claim
            for m in pool[:12]:
                st.administered.append({"family_id": m.id, "seq": len(st.administered) + 1, "a": m.a, "b": m.b,
                                        "c": m.c, "topic": m.topic, "correct": m.b < 0.4, "late": False})
            st.stop_reason = "max_items"
        assert eng.result(lo).theta == eng.result(hi).theta


def test_first_item_targets_start_theta_of_the_claim():
    eng = IrtCatEngine()
    eng.TOP_K = 1                                      # no randomness: the most informative family
    pool = _pool()
    for claimed in ("intern", "junior", "middle", "senior"):
        st = eng.start("backend", claimed, "full", "initial", pool, set())
        first = eng.next_family(st, pool, random.Random(0))
        target = C.grade(claimed).start_theta
        weights = C.blueprints["backend"]
        best = max((m for m in pool if weights[m.topic] > 0),
                   key=lambda m: (float(irt.information(target, m.a, m.b, m.c)), [-ord(ch) for ch in m.id]))
        assert first.id == best.id


def test_randomesque_spreads_first_item_and_stays_in_top_five():
    eng = IrtCatEngine()
    pool = _pool()
    target = C.grade("middle").start_theta
    top5 = sorted(pool, key=lambda m: (-float(irt.information(target, m.a, m.b, m.c)), m.id))[:5]
    firsts = Counter()
    for s in range(300):
        st = eng.start("backend", "middle", "full", "initial", pool, set())
        firsts[eng.next_family(st, pool, make_rng(b"k", f"s{s}", "select", 1)).id] += 1
    assert set(firsts) == {m.id for m in top5}
    assert max(firsts.values()) / 300 < 0.3                # exposure of the best family ~ 1/5


def test_blueprint_quotas_hold_at_every_step():
    eng = IrtCatEngine()
    weights = C.blueprints["backend"]
    for seed in range(20):
        rng = random.Random(seed)
        st = eng.start("backend", "middle", "full", "initial", _pool(seed=seed), set())
        pool = _pool(seed=seed)
        while (m := eng.next_family(st, pool, random.Random(seed * 100 + len(st.administered)))) is not None:
            eng.record(st, m.id, rng.random() < 0.5)
            n = len(st.administered)
            counts = Counter(x["topic"] for x in st.administered)
            for topic, c in counts.items():
                assert c <= math.floor(weights[topic] * n) + 1, (seed, n, topic, c)


def test_unseen_families_are_preferred_and_none_repeats():
    eng = IrtCatEngine()
    pool = _pool()
    seen = {m.id for m in pool[::2]}
    st, order, _ = _run(eng, "backend", "middle", "full", lambda m, k: k % 3 != 0, seen=seen, pool=pool)
    assert len(order) == len(set(order))
    assert not set(order) & seen                           # enough unseen families in every topic


def test_same_seeds_same_test_and_json_roundtrip_changes_nothing():
    eng = IrtCatEngine()
    ans = lambda m, k: (m.b + k) % 2 < 1.1                 # noqa: E731
    a = _run(eng, "ml_data", "junior", "full", ans, session="abc", roundtrip=True)
    b = _run(eng, "ml_data", "junior", "full", ans, session="abc", roundtrip=False)
    assert a[1] == b[1] and a[2] == b[2]
    c = _run(eng, "ml_data", "junior", "full", ans, session="other")
    assert c[1] != a[1]


def test_late_answers_are_incorrect_and_pending_items_count_against():
    eng = IrtCatEngine()
    pool = _pool()
    st = eng.start("backend", "junior", "full", "initial", pool, set())
    m = eng.next_family(st, pool, random.Random(1))
    eng.record(st, m.id, True, late=True)
    assert st.administered[0]["correct"] is False
    m2 = eng.next_family(st, pool, random.Random(2))
    assert eng.next_family(st, pool, random.Random(3)) == m2         # retry re-serves the pending item
    res = eng.result(st)                                               # BE ended the session early
    assert [e[2] for e in res.evidence] == [False, False]
    assert res.decision == "unconfirmed" and res.fallback_grade is None     # incomplete (D8)
    with pytest.raises(ValueError):
        eng.record(st, "not-served", True)


def test_pool_exhaustion_stops_and_only_counts_after_min_items():
    eng = IrtCatEngine()
    small = _pool(per_topic=1)[:6]
    st, order, res = _run(eng, "backend", "intern", "full", lambda m, k: True, pool=small)
    assert len(order) == 6 and st.stop_reason == "pool_exhausted"
    assert res.decision == "unconfirmed"                                  # 6 < 10 answers
    st, order, res = _run(eng, "backend", "intern", "full", lambda m, k: True, pool=_pool(per_topic=1))
    assert res.decision == "confirmed" and len(order) >= 10


def test_screening_blueprint_restricts_topics_and_never_changes_scoring():
    eng = IrtCatEngine()
    pool = _pool()
    st = eng.start("backend", "middle", "full", "screening", pool, set(),
                   blueprint=[("sql.aggregation", 2.0), ("python.core", 2.0)])
    assert st.blueprint == [("python.core", 0.5), ("sql.aggregation", 0.5)]
    for k in range(10):
        m = eng.next_family(st, pool, random.Random(k))
        assert m.topic in ("sql.aggregation", "python.core")
        eng.record(st, m.id, k % 2 == 0)
    items = [(x["a"], x["b"], x["c"]) for x in st.administered]
    assert st.theta == pytest.approx(ref_eap(items, [x["correct"] for x in st.administered])[0], abs=1e-9)
    with pytest.raises(ValueError):
        eng.start("backend", "middle", "full", "screening", pool, set(), blueprint=[("x", 0.0)])


def test_start_validates_parameters():
    with pytest.raises(ValueError):
        IrtCatEngine().start("devops", "middle", "full", "initial", [], set())
    with pytest.raises(ValueError):
        IrtCatEngine().start("backend", "lead", "full", "initial", [], set())


def test_real_registry_runs_a_session_end_to_end():
    from assessment.families.registry import active_metas, all_families
    eng = IrtCatEngine()
    pool = active_metas("backend")
    fams = all_families()
    st = eng.start("backend", "junior", "express", "initial", pool, set())
    while (m := eng.next_family(st, pool, make_rng(b"k", "e2e", "select", len(st.administered) + 1))) is not None:
        inst = fams[m.id].generate(make_rng(b"k", "e2e", m.id, len(st.administered)))
        answer = {"option_id": inst.key} if inst.input == "choice" else {"value": str(inst.key)}
        eng.record(st, m.id, fams[m.id].is_correct(inst.key, answer))
    res = eng.result(st)
    assert res.evidence and all(e[2] for e in res.evidence)


def test_verified_skills_come_from_answered_families_in_good_topics():
    from assessment.engine.topics import verified_skills
    adm = [_entry("sql.aggregation", 1.2, 0.0, 0.25, True, 1), _entry("python.core", 1.2, 0.0, 0.25, False, 2),
           _entry("backend.http", 1.2, 0.0, 0.25, None, 3)]
    adm[0]["family_id"], adm[1]["family_id"], adm[2]["family_id"] = "f.sql", "f.py", "f.http"
    skills = {"f.sql": ("sql",), "f.py": ("python",), "f.http": ("rest_api",)}
    topics = [("python.core", "limited"), ("sql.aggregation", "strong")]
    assert verified_skills(topics, adm, skills) == ["sql"]


# ── review fixes (ML-3 review) ─────────────────────────────────────────────

def test_blueprint_quotas_are_floors_too():
    eng = IrtCatEngine()
    weights = C.blueprints["backend"]
    for seed in range(30):
        rng = random.Random(seed)
        pool = _pool(seed=seed)
        st = eng.start("backend", "middle", "full", "initial", pool, set())
        st.min_items = st.max_items = 20
        while (m := eng.next_family(st, pool, random.Random(seed * 1000 + len(st.administered)))) is not None:
            eng.record(st, m.id, rng.random() < 0.5)
            n = len(st.administered)
            counts = Counter(x["topic"] for x in st.administered)
            for topic, w in weights.items():
                assert counts.get(topic, 0) >= math.floor(w * n) - 1, (seed, n, topic)
        assert set(Counter(x["topic"] for x in st.administered)) == set(weights)   # all 11 topics


def test_result_does_not_depend_on_calling_next_family_first_and_never_mutates():
    eng = IrtCatEngine()
    pool = _pool()
    st = eng.start("backend", "junior", "full", "initial", pool, set())
    for k in range(40):
        if eng.stop_rule(st) is not None:
            break
        m = eng.next_family(st, pool, random.Random(k))
        eng.record(st, m.id, True)
    assert st.stop_reason is None                      # BE finalises without a last next_family
    snapshot = json.dumps(st.to_json(), sort_keys=True)
    early = eng.result(st)
    assert json.dumps(st.to_json(), sort_keys=True) == snapshot
    assert early.complete and early.decision == "confirmed" and early.stop_reason in ("se", "ci")
    assert eng.next_family(st, pool, random.Random(99)) is None
    assert eng.result(st) == early


def test_result_on_a_pending_item_leaves_it_pending_for_record():
    eng = IrtCatEngine()
    pool = _pool()
    st = eng.start("backend", "junior", "full", "initial", pool, set())
    m = eng.next_family(st, pool, random.Random(0))
    preview = eng.result(st)
    assert preview.evidence == [(1, item_level(m), False)] and not preview.complete
    eng.record(st, m.id, True)                          # still pending: no "not pending" error
    assert st.administered[0]["correct"] is True


def test_pending_family_retired_mid_session_is_finished_from_the_registry():
    from assessment.families.registry import active_metas
    eng = IrtCatEngine()
    pool = active_metas("backend")
    st = eng.start("backend", "junior", "full", "initial", pool, set())
    m = eng.next_family(st, pool, random.Random(0))
    smaller = [x for x in pool if x.id != m.id]         # e.g. the leak monitor retired it
    assert eng.next_family(st, smaller, random.Random(1)) == m
    eng.record(st, m.id, True)
    nxt = eng.next_family(st, smaller, random.Random(2))
    assert nxt is None or nxt.id != m.id


def test_screening_blueprint_is_validated_and_merged():
    eng = IrtCatEngine()
    with pytest.raises(ValueError, match="not a backend topic"):
        eng.start("backend", "middle", "full", "screening", [], set(), blueprint=[("web.react", 1.0)])
    with pytest.raises(ValueError):
        eng.start("backend", "middle", "full", "screening", [], set(), blueprint=[("sql.joins", -1.0)])
    st = eng.start("backend", "middle", "full", "screening", [], set(),
                   blueprint=[("sql.joins", 1.0), ("python.core", 1.0), ("sql.joins", 2.0)])
    assert st.blueprint == [("python.core", 0.25), ("sql.joins", 0.75)]


def test_single_item_topics_are_always_moderate():
    one_wrong_easy = [_entry("t", 1.4, -1.0, 0.25, False, 1)]
    one_right_hard = [_entry("t", 1.4, 2.0, 0.25, True, 1)]
    assert topic_levels(one_wrong_easy, "middle", C) == [("t", "moderate")]
    assert topic_levels(one_right_hard, "middle", C) == [("t", "moderate")]


def test_registry_is_big_enough_for_a_full_cat():
    """The N2 gate (BE.md ML-3 row): >= 20 active families per spec covering every blueprint topic."""
    from assessment.families.registry import active_metas
    for spec in ("backend", "frontend", "ml_data"):
        metas = active_metas(spec)
        assert len(metas) >= IrtCatEngine.FULL_MAX
        assert {m.topic for m in metas} == set(C.topics_for(spec))
