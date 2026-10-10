"""ML-1: live families have parameter-dependent keys, independent oracles, and the harness gates them."""
from __future__ import annotations

import dataclasses
import os
import random
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from assessment.engine import FAMILIES_REGISTRY
from assessment.families import verify as harness
from assessment.families.base import Instance, fingerprint_of
from assessment.families.frontend.js_event_loop import simulate
from assessment.families.kit import choice_options, is_number_correct, norm_text
from assessment.families.registry import all_families, make_rng
from assessment.families.shared.complexity import iteration_counts, measure_class

ROOT = Path(__file__).resolve().parents[2]

FAMILIES = all_families()
SKILLS = harness._skills_catalog()
# The empirical complexity oracle runs code for many n; a smaller sample keeps tests/ml fast.
# The full 1000-instance run is `python -m assessment.families.verify` (and validation.run).
SAMPLE = {"sh.algo.complexity.v2": 150}


@pytest.mark.parametrize("fid", sorted(FAMILIES))
def test_family_passes_harness(fid):
    rep = harness.verify_family(FAMILIES[fid], n=SAMPLE.get(fid, 400), skills=SKILLS)
    assert rep.errors == [], rep.errors


# ── the harness rejects broken families ────────────────────────────────────

class _Good:
    """A small valid family: a + b with random operands, four options."""

    meta = dataclasses.replace(FAMILIES["be.sql.group_having.v2"].meta, id="t.test.add.v1", version=1)

    def params(self, rng):
        return {"a": rng.randint(1, 10_000), "b": rng.randint(1, 10_000)}

    def generate(self, rng):
        p = self.params(rng)
        s = p["a"] + p["b"]
        below = rng.randrange(4)                                   # the answer's rank is uniform
        lows = rng.sample(range(s - 9, s), below)
        highs = rng.sample(range(s + 1, s + 10), 3 - below)
        opts, key = choice_options(rng, str(s), [str(x) for x in lows + highs])
        return Instance(stem_md=f"{p['a']} + {p['b']} = ?", input="choice", key=key,
                        fingerprint=fingerprint_of(p), options=opts)

    def is_correct(self, key, answer):
        return answer.get("option_id") == key

    def oracle(self, inst):
        a, b = (int(x) for x in inst.stem_md.split(" = ")[0].split(" + "))
        return next(o["id"] for o in inst.options if o["text_md"] == str(a + b))


class _ConstantKey(_Good):
    def params(self, rng):
        rng.random()
        return {"a": 2, "b": 2} if rng.random() < 0.97 else super().params(rng)


class _WrongOracle(_Good):
    def oracle(self, inst):
        return inst.options[0]["id"]


class _DuplicateOptions(_Good):
    def generate(self, rng):
        inst = super().generate(rng)
        inst.options[1]["text_md"] = inst.options[0]["text_md"]
        return inst


class _SeedInFingerprint(_Good):
    def params(self, rng):
        return {"a": rng.randint(1, 3), "b": rng.randint(1, 3)}

    def generate(self, rng):
        inst = super().generate(rng)
        inst.fingerprint = fingerprint_of({"salt": rng.getrandbits(64)})
        return inst


class _FingerprintMissesParams(_Good):
    def generate(self, rng):
        inst = super().generate(rng)
        inst.fingerprint = fingerprint_of({"a": inst.stem_md.split(" + ")[0]})
        return inst


class _CorrectAlwaysFirst(_Good):
    def generate(self, rng):
        inst = super().generate(rng)
        inst.options.sort(key=lambda o: o["id"] != inst.key)
        return inst


class _Nondeterministic(_Good):
    _calls = 0

    def generate(self, rng):
        inst = super().generate(rng)
        type(self)._calls += 1
        inst.stem_md += " " * (self._calls % 2)
        return inst


class _TinySpace(_Good):
    def params(self, rng):
        return {"a": rng.randint(1, 5), "b": rng.randint(1, 5)}


class _NoneOracle(_Good):
    def oracle(self, inst):
        return None


class _EchoOracle(_Good):
    def oracle(self, inst):
        return inst.key            # the harness hands the oracle a copy without the key


class _AnswerNotOffered(_Good):
    """The keyed option shows a wrong number and the true sum is not among the options."""

    def generate(self, rng):
        inst = super().generate(rng)
        for o in inst.options:
            if o["id"] == inst.key:
                o["text_md"] = str(int(o["text_md"]) + 100)
        return inst


class _BiggestIsRight(_Good):
    """Distractors are always smaller than the answer: 'pick the largest' always wins."""

    def generate(self, rng):
        p = self.params(rng)
        s = p["a"] + p["b"]
        opts, key = choice_options(rng, str(s), [str(s - 1), str(s - 2), str(s - 3)])
        return Instance(stem_md=f"{p['a']} + {p['b']} = ?", input="choice", key=key,
                        fingerprint=fingerprint_of(p), options=opts)


class _AnswerNearFixedValue(_Good):
    """The answer is always close to 50 while distractors are spread out: a per-value leak."""

    def generate(self, rng):
        p = {"a": rng.randint(20, 30), "b": rng.randint(20, 30)}
        s = p["a"] + p["b"]
        others = rng.sample([x for x in range(1, 200) if abs(x - s) > 15], 3)
        opts, key = choice_options(rng, str(s), [str(x) for x in others])
        return Instance(stem_md=f"{p['a']} + {p['b']} = ?", input="choice", key=key,
                        fingerprint=fingerprint_of(p), options=opts)


class _TypedGood:
    meta = dataclasses.replace(_Good.meta, id="t.test.typed.v1", version=1, c=0.0, format="numeric_scenario")

    def generate(self, rng):
        p = {"a": rng.randint(10, 10_000), "b": rng.randint(10, 10_000)}
        return Instance(stem_md=f"{p['a']} * {p['b']} = ?", input="number", key=str(p["a"] * p["b"]),
                        fingerprint=fingerprint_of(p))

    def is_correct(self, key, answer):
        return is_number_correct(key, answer)

    def oracle(self, inst):
        a, b = (int(x) for x in inst.stem_md.split(" = ")[0].split(" * "))
        return str(a * b)


class _TypedTooLenient(_TypedGood):
    def is_correct(self, key, answer):
        return is_number_correct(key, answer, tol=abs(float(key)) * 0.2)


class _TypedKeyInStem(_TypedGood):
    """A text answer (a word made of hex letters) that the stem gives away."""

    meta = dataclasses.replace(_TypedGood.meta, id="t.test.typedtext.v1")

    def generate(self, rng):
        p = {"x": rng.getrandbits(48)}
        word = f"{p['x']:012x}"
        return Instance(stem_md=f"Перепишите слово {word} (подсказка: {word})", input="text", key=word,
                        fingerprint=fingerprint_of(p))

    def is_correct(self, key, answer):
        return isinstance(answer.get("value"), str) and answer["value"].strip() == key

    def oracle(self, inst):
        return inst.stem_md.split()[2]


class _TypedModalAnswer(_TypedGood):
    """A typed item whose answer is 42 a fifth of the time: c = 0 would understate guessing."""

    def generate(self, rng):
        inst = super().generate(rng)
        if rng.random() < 0.2:
            a = rng.randint(1, 10_000)
            inst = Instance(stem_md=f"{a} * 0 + 42 = ?", input="number", key="42", fingerprint=fingerprint_of({"a": a}))
        return inst

    def oracle(self, inst):
        if " * 0 + 42" in inst.stem_md:
            return "42"
        return super().oracle(inst)


class _DistractorNumbersNotInItem(_Good):
    """The answer reuses the stem's operands ("a b"), distractors are numbers that never occur in
    it: a candidate who only checks which numbers appear in the item gets it right."""

    def generate(self, rng):
        p = self.params(rng)
        others = [f"{rng.randint(1, 10_000)} {rng.randint(1, 10_000)}" for _ in range(3)]
        opts, key = choice_options(rng, f"{p['a']} {p['b']}", others)
        return Instance(stem_md=f"{p['a']} + {p['b']} = ? (запишите слагаемые)", input="choice", key=key,
                        fingerprint=fingerprint_of(p), options=opts)

    def oracle(self, inst):
        a, b = inst.stem_md.split(" = ")[0].split(" + ")
        return next(o["id"] for o in inst.options if o["text_md"] == f"{a} {b}")


@pytest.mark.parametrize("cls, expected", [
    (_ConstantKey, "entropy"),
    (_WrongOracle, "oracle"),
    (_DuplicateOptions, "options: duplicate texts"),
    (_SeedInFingerprint, "same content, different fingerprint"),
    (_FingerprintMissesParams, "same fingerprint, different answer"),
    (_TypedModalAnswer, "modal: the answer '42.0'"),
    (_DistractorNumbersNotInItem, "guessing: 'fewest numbers absent from the item'"),
    (_CorrectAlwaysFirst, "position"),
    (_Nondeterministic, "determinism"),
    (_TinySpace, "collisions"),
    (_NoneOracle, "oracle: no unique option"),
    (_EchoOracle, "oracle"),
    (_AnswerNotOffered, "oracle"),
    (_BiggestIsRight, "guessing: 'value rank 4 of 4'"),
    (_AnswerNearFixedValue, "guessing: 'closest to the typical answer'"),
    (_TypedTooLenient, "near miss"),
    (_TypedKeyInStem, "leak: the typed answer"),
])
def test_harness_rejects_broken_family(cls, expected):
    rep = harness.verify_family(cls(), n=300, skills=SKILLS)
    assert not rep.ok
    assert any(expected in e for e in rep.errors), rep.errors


@pytest.mark.parametrize("cls", [_Good, _TypedGood])
def test_harness_accepts_the_reference_families(cls):
    rep = harness.verify_family(cls(), n=300, skills=SKILLS)
    assert rep.errors == []


def test_guess_margin_shrinks_with_sample_size():
    assert harness.guess_margin(0.25, 1000) == pytest.approx(4 * (0.25 * 0.75 / 1000) ** 0.5)   # 0.0548
    assert harness.guess_margin(0.25, 300) == pytest.approx(0.1)
    assert harness.guess_margin(0.25, 100_000) == 0.05                                           # floor


def test_event_loop_distractors_respect_what_a_junior_knows():
    """Distractors keep sync logs first in program order (only the 'program order' misconception
    breaks it), so knowing just that rule must not find the answer (ML-1 re-review: 59 %)."""
    fam = FAMILIES["fe.js.event_loop.v2"]
    bad = total = 0
    knows_sync = 0.0
    for i in range(600):
        inst = fam.generate(make_rng(b"junior", "s", fam.meta.id, i))
        sync = [ln.split("'")[1] for ln in inst.code["text"].splitlines() if ln.startswith("console.log")]
        ok = [o["text_md"].split(", ")[: len(sync)] == sync for o in inst.options]
        for o, good in zip(inst.options, ok, strict=True):
            if o["id"] != inst.key:
                total += 1
                bad += not good
        keep = [o["id"] for o, good in zip(inst.options, ok, strict=True) if good]
        knows_sync += (inst.key in keep) / len(keep)
    assert bad / total <= 0.2
    assert knows_sync / 600 <= 0.35


def test_harness_refuses_too_small_samples():
    with pytest.raises(ValueError):
        harness.verify_family(_Good(), n=0)
    assert harness.guessing_checks([(["1", "2", "3", "4"], 0)] * 5, 0.25)  # too few -> an error, not a pass

def test_harness_rejects_unknown_skill_and_bad_meta():
    bad = _Good()
    bad.meta = dataclasses.replace(bad.meta, skills=("no_such_skill",), c=0.5, time_limit_s=5)
    errs = harness.check_meta(bad, SKILLS)
    assert any("skills" in e for e in errs) and any("c=" in e for e in errs) and any("time_limit" in e for e in errs)


def test_cli_exit_codes(capsys):
    assert harness.main(["--n", "100", "--family", "be.sql.group_having.v2"]) == 0
    assert "1/1 families pass" in capsys.readouterr().out
    with pytest.raises(SystemExit) as unknown:
        harness.main(["--n", "100", "--family", "be.sql.group_having.v2", "--family", "be.sql.typo.v2"])
    assert "be.sql.typo.v2" in str(unknown.value.code)
    for small in ("0", "-5", "30"):
        with pytest.raises(SystemExit) as exc:
            harness.main(["--n", small])
        assert exc.value.code != 0

# ── keys depend on the drawn parameters (ML-F1 regression) ─────────────────

@pytest.mark.parametrize("fid", sorted(FAMILIES))
def test_answers_vary_with_parameters(fid):
    answers = Counter()
    for i in range(120):
        inst = FAMILIES[fid].generate(make_rng(b"k", "s", fid, i))
        answers[norm_text(harness.answer_text(inst))] += 1
    assert len(answers) >= 3 and answers.most_common(1)[0][1] / 120 < 0.6


def test_legacy_registry_serves_fixed_families_with_varying_keys():
    assert sorted(FAMILIES_REGISTRY) == ["be.sql.group_having.v2", "fe.js.event_loop.v2", "sh.algo.complexity.v2"]
    for fam in FAMILIES_REGISTRY.values():
        insts = [fam.generate(f"seed-{i}") for i in range(60)]
        assert fam.generate("seed-1").key == insts[1].key                       # deterministic
        assert len({i.key for i in insts}) > 30                                    # ids are opaque
        texts = {next(o["text_md"] for o in i.options if o["id"] == i.key) for i in insts}
        assert len(texts) >= 3                                                    # not constant
        assert all(set(i.options[0]) == {"id", "text_md"} for i in insts)


# ── oracles: hand-derived golden cases ─────────────────────────────────────

def test_sql_oracle_on_hand_built_instance():
    fam = FAMILIES["be.sql.group_having.v2"]
    # Sales: 150k, 90k, 200k; Legal: 120k; Ops: 100k, 110k.  WHERE salary >= 100000 drops 90k.
    # After WHERE: Sales 2, Legal 1, Ops 2; HAVING COUNT(*) >= 2 keeps Sales and Ops: cnt 2 + 2 = 4.
    script = ("CREATE TABLE employees (id INTEGER PRIMARY KEY, department TEXT, salary INTEGER);\n"
              "INSERT INTO employees (department, salary) VALUES\n"
              "  ('Sales', 150000),\n  ('Sales', 90000),\n  ('Legal', 120000),\n  ('Ops', 100000),\n"
              "  ('Sales', 200000),\n  ('Ops', 110000);\n\n"
              "SELECT department, COUNT(*) AS cnt\nFROM employees\nWHERE salary >= 100000\n"
              "GROUP BY department\nHAVING COUNT(*) >= 2;")
    opts = [{"id": "oa", "text_md": "3"}, {"id": "ob", "text_md": "2"}, {"id": "oc", "text_md": "5"},
            {"id": "od", "text_md": "4"}]
    inst = Instance(stem_md="?", input="choice", key=None, fingerprint="0" * 64,
                    code={"lang": "sql", "text": script}, options=opts)
    assert fam.oracle(inst) == "od"


def test_event_loop_simulator_hand_case():
    code = ("setTimeout(() => console.log('A'), 20);\n"
            "console.log('B');\n"
            "queueMicrotask(() => console.log('C'));\n"
            "setTimeout(() => console.log('D'), 0);\n"
            "Promise.resolve().then(() => console.log('E'));\n"
            "console.log('F');")
    # sync B F, microtasks C E (FIFO), timers by delay: D (0 -> 1 ms) then A (20 ms)
    assert simulate(code) == ["B", "F", "C", "E", "D", "A"]


@pytest.mark.parametrize("code, label", [
    ("def f(n):\n    s = 0\n    for i in range(n):\n        s += i\n    return s", "O(n)"),
    ("def f(n):\n    s = 0\n    for i in range(n):\n        for j in range(n):\n            s += 1\n    return s",
     "O(n^2)"),
    ("def f(n):\n    i = n\n    while i > 1:\n        i //= 2\n    return i", "O(log n)"),
    ("def f(n):\n    i = 1\n    while i * i <= n:\n        i += 1\n    return i", "O(√n)"),
    ("def f(n):\n    s = 0\n    for i in range(n):\n        j = 1\n        while j < n:\n            j *= 2\n"
     "            s += 1\n    return s", "O(n log n)"),
    ("def f(n):\n    s = 0\n    i = 1\n    while i < n:\n        for j in range(i):\n            s += 1\n"
     "        i *= 2\n    return s", "O(n)"),
])
def test_complexity_oracle_measures_textbook_shapes(code, label):
    assert measure_class(code) == label


@pytest.mark.parametrize("code", [
    "def f(n):\n    s = 0\n    for j in range(5):\n        s += j\n    return s",               # Θ(1)
    "def f(n):\n    l = [0]\n    for i in range(n):\n        if i in l:\n            l += [i]\n    return l",
    "def f(n):\n    return sum(i for i in range(n))",
    "def f(n):\n    if n < 2:\n        return 1\n    return f(n - 1) + 1",
    "def f(n):\n    s = 0\n    for i in range(n):\n        try:\n            s += i\n        except Exception:\n"
    "            pass\n    return s",
    "def f(n):\n    if n < 100000:\n        return 0\n    for i in range(n):\n        pass\n    return n",
])
def test_complexity_oracle_refuses_what_it_cannot_measure(code):
    with pytest.raises(ValueError):
        measure_class(code)


def test_complexity_oracle_keeps_five_points_for_cubic_code():
    code = ("def f(n):\n    s = 0\n    for i in range(n):\n        for j in range(n):\n"
            "            for k in range(n):\n                s += 1\n    return s")
    assert len(iteration_counts(code)) >= 5 and measure_class(code) == "O(n^3)"


def test_families_render_identically_under_different_hash_seeds():
    """Invariant 6: no iteration over unordered str sets/dicts affects the output."""
    script = (
        "import hashlib, json, sys\n"
        "sys.path.insert(0, 'apps')\n"
        "from assessment.families.registry import all_families, make_rng\n"
        "h = hashlib.sha256()\n"
        "for fid, fam in all_families().items():\n"
        "    for i in range(40):\n"
        "        inst = fam.generate(make_rng(b'k', 's', fid, i))\n"
        "        h.update(json.dumps([inst.view(), inst.key, inst.fingerprint], ensure_ascii=False).encode())\n"
        "print(h.hexdigest())\n")
    outs = set()
    for seed in ("0", "1", "4242"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        res = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env,
                             cwd=str(ROOT), timeout=300, check=True)
        outs.add(res.stdout.strip())
    assert len(outs) == 1

# ── real Node.js agrees with the event-loop key ───────────────────────────

@pytest.mark.skipif(shutil.which("node") is None and not os.environ.get("CI"),
                    reason="Node.js not installed (required in CI)")
def test_event_loop_keys_match_real_node(tmp_path):
    fam = FAMILIES["fe.js.event_loop.v2"]
    insts = [fam.generate(make_rng(b"node", "s", fam.meta.id, i)) for i in range(200)]
    # one Node process: each script runs in its own async context, outputs are collected in order
    wrapped = []
    for k, inst in enumerate(insts):
        body = inst.code["text"].replace("console.log(", f"__log({k}, ")
        wrapped.append(f"(() => {{\n{body}\n}})();")
    js = ("const __out = {};\nfunction __log(k, v) { (__out[k] = __out[k] || []).push(v); }\n"
          + "\n".join(wrapped) + "\nsetTimeout(() => console.log(JSON.stringify(__out)), 200);\n")
    script = tmp_path / "event_loop_check.js"
    script.write_text(js, encoding="utf-8")
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60, check=True)
    import json
    out = json.loads(res.stdout)
    for k, inst in enumerate(insts):
        key_text = next(o["text_md"] for o in inst.options if o["id"] == inst.key)
        assert ", ".join(out[str(k)]) == key_text, (inst.code["text"], out[str(k)])


# ── typed-answer helper ────────────────────────────────────────────────────

def test_is_number_correct_normalises_and_never_evals():
    assert is_number_correct("12.5", {"value": " 12,5 "})
    assert is_number_correct("1000", {"value": "1 000"})
    assert not is_number_correct("12.5", {"value": "12.6"})
    assert is_number_correct("12.5", {"value": "12.6"}, tol=0.1)
    for bad in ("", "nan", "__import__('os')", "1e999999", None, "12.5abc"):
        assert not is_number_correct("12.5", {"value": bad})
    assert not is_number_correct("12.5", {})


def test_choice_options_needs_enough_distinct_distractors():
    with pytest.raises(ValueError):
        choice_options(random.Random(0), "1", ["1", "1.0", "2"])


NODE_FAMILIES = sorted(fid for fid, fam in FAMILIES.items() if getattr(fam, "NODE_CHECK", False))


@pytest.mark.skipif(shutil.which("node") is None and not os.environ.get("CI"),
                    reason="Node.js not installed (required in CI)")
@pytest.mark.parametrize("fid", NODE_FAMILIES)
def test_js_family_keys_match_real_node(fid, tmp_path):
    """The Python generator and oracle model JS semantics; real Node is the referee."""
    from assessment.families.frontend.js_core import node_answer
    fam = FAMILIES[fid]
    for i in range(30):
        inst = fam.generate(make_rng(b"node", "s", fid, i))
        script = tmp_path / f"item_{i}.js"
        script.write_text(inst.code["text"], encoding="utf-8")
        out = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=30, check=True).stdout
        got = node_answer(out)
        if inst.input == "choice":
            assert got == harness.answer_text(inst), (inst.code["text"], got)
        else:
            assert float(got) == pytest.approx(float(inst.key)), (inst.code["text"], got)


# ── builder: thread safety, rounding ties, semantic fingerprints, balanced distractors ──

def test_run_python_is_thread_safe_and_does_not_touch_stdout(capsys):
    """find_bug runs item code during generation; under threads the old redirect_stdout swapped
    sys.stdout for the whole process and produced wrong keys (ML-6 review)."""
    from concurrent.futures import ThreadPoolExecutor

    fam = FAMILIES["sh.code.find_bug.v1"]

    def key_of(i):
        inst = fam.generate(make_rng(b"threads", "s", fam.meta.id, i))
        return inst.fingerprint, inst.key, inst.view()

    serial = [key_of(i) for i in range(60)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        threaded = list(pool.map(key_of, range(60)))
    assert threaded == serial
    assert capsys.readouterr().out == ""


def test_rounding_tie_accepts_both_neighbours():
    """True value 0.3125 asked to 3 decimals: 0.312 (half to even) and 0.313 (half up) are both
    right; the key keeps the exact value instead of a rounded one."""
    from assessment.families.builder import TypedNumberFamily, exact_key

    class Tie(TypedNumberFamily):
        DECIMALS = 3

    fam = Tie()
    key = exact_key(0.3125, 3)
    assert key == "0.3125"
    for ok in ("0.312", "0.313", "0,313", "0.3125"):
        assert fam.is_correct(key, {"value": ok}), ok
    for bad in ("0.311", "0.314", "0.31"):
        assert not fam.is_correct(key, {"value": bad}), bad


def test_decimals_hint_grammar():
    from assessment.families.builder import decimals_hint
    assert decimals_hint(0) == "Ответ — целое число."
    assert decimals_hint(1) == "Ответ округлите до 1 знака после запятой."
    assert decimals_hint(2) == "Ответ округлите до 2 знаков после запятой."


def test_semantic_fingerprint_ignores_decorative_fields():
    from assessment.families.builder import semantic_fingerprint

    class Fam:
        SEMANTIC = ("x", "y")

    base = semantic_fingerprint(Fam(), {"x": 1, "y": [2, 3], "name": "users"})
    assert base == semantic_fingerprint(Fam(), {"x": 1, "y": [2, 3], "name": "orders"})
    assert base != semantic_fingerprint(Fam(), {"x": 1, "y": [3, 2], "name": "users"})
    # a classification label always counts, even when SEMANTIC omits it
    assert (semantic_fingerprint(Fam(), {"x": 1, "y": 2, "label": "A"})
            != semantic_fingerprint(Fam(), {"x": 1, "y": 2, "label": "B"}))


def test_balanced_pick_makes_the_answers_similarity_rank_uniform():
    """With distractors derived from the answer, the answer is the most similar option unless the
    subset is chosen; balanced_pick draws a target rank uniformly and uses a subset with it."""
    from assessment.families.builder import balanced_pick, similarity_rank

    rng = random.Random(7)
    ranks = Counter()
    for _ in range(800):
        vals = rng.sample(range(10, 99), 4)
        answer = str(vals)
        pool = [str(vals[::-1]), str(vals[1:] + vals[:1]), str(sorted(vals)), str([v + 1 for v in vals]),
                str(rng.sample(range(10, 99), 4)), str(rng.sample(range(10, 99), 4))]
        pool = list(dict.fromkeys(x for x in pool if x != answer))
        picked = balanced_pick(rng, answer, pool, 3)
        assert len(set(picked)) == 3 and set(picked) <= set(pool)
        ranks[min(similarity_rank(answer, picked), 3)] += 1
    total = sum(ranks.values())
    # Neither extreme may identify the answer: "most similar" (rank 0) and "least similar" (rank 3)
    # stay within the harness margin of chance. Unreachable middle ranks fall back to the nearest.
    assert ranks[0] / total <= 0.30 and ranks[3] / total <= 0.30, ranks
    assert ranks[0] / total >= 0.15, ranks     # the target rank is honoured, not just avoided
