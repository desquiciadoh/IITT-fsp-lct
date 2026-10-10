"""Verify harness for item families (ML-1):  python -m assessment.families.verify --n 1000

For every family it generates n instances from fixed HMAC seeds and checks:
  render      view() is JSON, only stem_md/input/code/options, a known input kind and code language
  options     choice: >= 3 options, unique opaque ids, texts distinct after normalisation,
              c == 1/len(options); typed: no options, c == 0
  oracle      the independent oracle agrees with the key
  one-correct exactly one option is accepted by is_correct(); typed: the key is accepted, a near miss is not
  determinism the same seed renders the same instance (view, key, fingerprint)
  fingerprint the fingerprint hashes the semantic parameters (decorative names and ids left out):
              same content -> same fingerprint (no seed in it), same fingerprint -> same answer
              (no semantic parameter left out)
  semantic    typed builder families: an answer never changes when the non-SEMANTIC (decorative)
              fields are taken from another draw
  collisions  duplicate fingerprints <= 0.1 %; the concept families in CONCEPT_FAMILIES have a few
              questions by design (label x template), are exempt, and need >= 2 distinct questions
              per label; their rate is reported
  entropy     answer-text entropy > 1 bit (no constant keys)
  modal       typed families: no single typed answer (tolerance-aware) is right on more than 10 % of
              items, by a one-sided 95 % upper bound (c = 0 must hold)
  item numbers typed families: typing the first / last / largest / smallest / most frequent number of
              the stem and code is right on at most 10 % of items
  position    the correct option's position is not predictable (chi-square, choice families)
  guessing    no option-only strategy (longest, most similar, value rank, frequent answer for an
              option set, value correct most often before, closest to the typical answer, order
              closest to the others, numbers absent from / shared with the item, as many numbers
              as most options) beats c by more than max(0.05, 4 standard errors)
  meta        id/version/specs/format/a/b/c/time limit, skills exist in content/skills.yaml

Exit code 0 only when every family passes. Pure: no Django.
"""
from __future__ import annotations

import argparse
import copy
import dataclasses
import difflib
import json
import math
import re
import sys
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .base import INPUT_KINDS, ITEM_FORMATS, SPECS, Instance, ItemFamily
from .builder import TypedNumberFamily
from .kit import norm_text
from .registry import all_families, make_rng

VERIFY_SECRET = b"fsp-draft-verify-harness"
CODE_LANGS = ("python", "javascript", "typescript", "sql", "css", "html", "http")
MAX_COLLISION_RATE = 0.001
MIN_ENTROPY_BITS = 1.0
MAX_MODAL_SHARE = 0.10   # typed items have c = 0; one answer right this often would be a free guess
TYPED_EXACT = 1e-6       # a typed oracle must reproduce the exact key, not just a tolerated rounding
SWAP_CHECKS = 50

# Concept families: the question is a label and a scenario template, so a handful of questions repeat
# by design. They are exempt from the collision gate (their rate is reported) and must show at least
# two distinct questions per label. Anything else, including new classification families, is gated.
CONCEPT_FAMILIES = {
    "be.db.isolation_anomaly.v1": "anomaly x order of the two transactions",
    "be.http.status_code.v1": "status code x scenario template",
    "be.http.method.v1": "method x scenario template",
    "be.sec.vuln_class.v1": "vulnerability x handler template",
    "sh.ds.op_cost.v1": "complexity class x operation",
    "ml.models.fit_diagnosis.v1": "fit class x the two scores",
    "sh.code.find_bug.v1": "task x constant x buggy line",
    "fe.sec.xss_sink.v1": "unsafe line x three safe lines",
    "fe.ts.assignability.v1": "failing line x property set",
    "fe.web.cache_control.v1": "directive x age x validator",
}
MIN_N = 100            # below this the position and guessing statistics are too noisy to gate on
CONTENT_DIR = Path(__file__).resolve().parents[3] / "content"


@dataclass
class FamilyReport:
    family_id: str
    n: int
    errors: list[str] = field(default_factory=list)
    collision_rate: float = 0.0
    collision_gated: bool = True
    distinct_questions: int = 0
    modal_share: float = 0.0
    entropy_bits: float = 0.0
    distinct_answers: int = 0
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_json(self) -> dict:
        return {"family_id": self.family_id, "n": self.n, "ok": self.ok, "errors": self.errors,
                "collision_rate": self.collision_rate, "collision_gated": self.collision_gated,
                "distinct_questions": self.distinct_questions,
                "modal_share": round(self.modal_share, 4), "entropy_bits": round(self.entropy_bits, 4),
                "distinct_answers": self.distinct_answers, "seconds": round(self.seconds, 3)}


def entropy_bits(values: Iterable[str]) -> float:
    counts = Counter(values)
    total = sum(counts.values())
    return -sum(c / total * math.log2(c / total) for c in counts.values()) if total else 0.0


def content_of(inst: Instance) -> str:
    """What makes two items the same question: stem, code and the correct answer's text.

    Distractor texts and option order are left out: they can be drawn independently of the
    parameters (redraw families), and a leaked question/answer pair is reusable whatever the
    distractors are. This is also what the collision rate counts.
    """
    return json.dumps([inst.stem_md, inst.input, inst.code, answer_text(inst)], ensure_ascii=False,
                      sort_keys=True)


def _skills_catalog() -> set[str]:
    import yaml
    path = CONTENT_DIR / "skills.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    ids = {str(x["id"]).strip().lower() for x in data if isinstance(x, dict) and "id" in x}
    if not ids:
        raise RuntimeError(f"no skill ids in {path}")
    return ids


def check_meta(fam: ItemFamily, skills: set[str] | None) -> list[str]:
    m, errs = fam.meta, []
    if not m.id or m.id.count(".") < 2 or not m.id.endswith(f".v{m.version}"):
        errs.append(f"meta: id {m.id!r} must look like 'area.topic.name.v{m.version}'")
    if not m.specs or any(s not in SPECS for s in m.specs) or len(set(m.specs)) != len(m.specs):
        errs.append(f"meta: bad specs {m.specs}")
    if m.format not in ITEM_FORMATS:
        errs.append(f"meta: bad format {m.format!r}")
    if not 0.3 <= m.a <= 3.0:
        errs.append(f"meta: a={m.a} outside [0.3, 3]")
    if not -3.0 <= m.b <= 3.0:
        errs.append(f"meta: b={m.b} outside [-3, 3]")
    if not 0.0 <= m.c < 0.5:
        errs.append(f"meta: c={m.c} outside [0, 0.5)")
    if not 30 <= m.time_limit_s <= 300:
        errs.append(f"meta: time_limit_s={m.time_limit_s} outside [30, 300]")
    from ..engine.content import load_content  # lazy: engine imports families.base
    topics = load_content().topics
    if m.topic not in topics:
        errs.append(f"meta: topic {m.topic!r} not in content/specializations.yaml")
    elif not set(m.specs) <= set(topics[m.topic].specs):
        errs.append(f"meta: specs {m.specs} not all served by topic {m.topic} ({topics[m.topic].specs})")
    if skills is not None:
        unknown = sorted(s for s in m.skills if s not in skills)
        if unknown or not m.skills:
            errs.append(f"meta: skills not in content/skills.yaml: {unknown or 'none given'}")
    return errs


def _check_instance(fam: ItemFamily, inst: Instance) -> list[str]:
    m, errs = fam.meta, []
    view = inst.view()
    try:
        blob = json.dumps(view, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        return [f"render: view() is not JSON ({type(e).__name__})"]
    if set(view) != {"stem_md", "input", "code", "options"}:
        errs.append(f"render: view keys {sorted(view)}")
    if inst.fingerprint and inst.fingerprint in blob:
        errs.append("leak: fingerprint appears in view()")
    if not isinstance(inst.stem_md, str) or not inst.stem_md.strip():
        errs.append("render: empty stem")
    if inst.input not in INPUT_KINDS:
        errs.append(f"render: input {inst.input!r}")
    if inst.code is not None and (set(inst.code) != {"lang", "text"} or inst.code["lang"] not in CODE_LANGS
                                  or not inst.code["text"].strip()):
        errs.append(f"render: bad code block (lang={(inst.code or {}).get('lang')!r})")
    if len(inst.fingerprint) != 64:
        errs.append("fingerprint: not a sha256 hex digest")

    try:
        # The oracle sees what the candidate sees: a copy with the key removed.
        oracle_key = fam.oracle(dataclasses.replace(copy.deepcopy(inst), key=None))
    except Exception as e:  # the harness reports any oracle crash as a family error
        errs.append(f"oracle: raised {type(e).__name__}: {e}")
    else:
        answer = {"option_id": oracle_key} if inst.input == "choice" else {"value": oracle_key}
        if oracle_key is None:
            errs.append("oracle: no unique option matches the oracle's answer")
        elif inst.input == "number":
            try:
                gap = abs(float(str(oracle_key).replace(",", ".")) - float(str(inst.key).replace(",", ".")))
            except ValueError:
                gap = math.inf
            if gap > TYPED_EXACT:
                errs.append("oracle: disagrees with the key")
        elif not (oracle_key == inst.key or (inst.input != "choice" and isinstance(oracle_key, str)
                                             and fam.is_correct(inst.key, answer))):
            errs.append("oracle: disagrees with the key")

    if inst.input == "choice":
        opts = inst.options or []
        ids = [o.get("id") for o in opts]
        if len(opts) < 3:
            errs.append(f"options: only {len(opts)}")
        if len(set(ids)) != len(ids) or not all(isinstance(i, str) and i for i in ids):
            errs.append("options: ids not unique")
        texts = [norm_text(o.get("text_md", "")) for o in opts]
        if len(set(texts)) != len(texts):
            errs.append(f"options: duplicate texts {[o.get('text_md') for o in opts]}")
        if opts and abs(m.c - 1 / len(opts)) > 1e-9:
            errs.append(f"meta: c={m.c} but {len(opts)} options")
        accepted = [i for i in ids if fam.is_correct(inst.key, {"option_id": i})]
        if len(accepted) != 1:
            errs.append(f"one-correct: {len(accepted)} options accepted")
        if fam.is_correct(inst.key, {"option_id": "o-not-an-option"}) or fam.is_correct(inst.key, {}):
            errs.append("is_correct: accepts a missing or unknown option")
    else:
        if inst.options:
            errs.append("options: typed item carries options")
        if m.c != 0:
            errs.append(f"meta: typed item with c={m.c}")
        if not fam.is_correct(inst.key, {"value": str(inst.key)}):
            errs.append(f"is_correct: rejects its own key {inst.key!r}")
        if fam.is_correct(inst.key, {"value": ""}) or fam.is_correct(inst.key, {}):
            errs.append("is_correct: accepts an empty answer")
        if fam.is_correct(inst.key, {"value": near_miss(inst.key)}):
            errs.append("is_correct: accepts a near miss")
        # Text keys only: a numeric answer may legitimately equal an input (a median is a value
        # of the sample), so its presence in the stem is not a leak.
        if _as_number(str(inst.key)) is None and len(str(inst.key)) > 3 and str(inst.key) in blob:
            errs.append("leak: the typed answer appears in view()")
    return errs


def _upper_bound(p: float, n: int) -> float:
    """One-sided 95 % upper bound of a share (normal approximation)."""
    return p + 1.645 * math.sqrt(max(p * (1 - p), 1e-12) / n)


def _best_single_answer(fam: ItemFamily, typed) -> tuple[str, float]:
    """The single typed answer accepted on most items, tolerance-aware (a rounded value also covers
    its neighbours), over the 30 most frequent keys as candidates."""
    candidates = [k for k, _ in Counter(str(k) for k, _ in typed).most_common(30)]
    best, share = "", 0.0
    for cand in candidates:
        hits = sum(1 for key, _ in typed if fam.is_correct(key, {"value": cand}))
        if hits / len(typed) > share:
            best, share = cand, hits / len(typed)
    return best, share


def _typed_guess_checks(fam: ItemFamily, typed) -> list[str]:
    """c = 0 must hold: no fixed answer and no number read off the item is right too often."""
    errs, n = [], len(typed)
    best, share = _best_single_answer(fam, typed)
    if _upper_bound(share, n) > MAX_MODAL_SHARE:
        errs.append(f"modal: the answer {best!r} is right on {share:.1%} of items "
                    f"(95 % bound {_upper_bound(share, n):.1%} > {MAX_MODAL_SHARE:.0%}, c = 0)")
    strategies = {
        "first number in the item": lambda xs: xs[0] if xs else None,
        "last number in the item": lambda xs: xs[-1] if xs else None,
        "largest number in the item": lambda xs: max(xs, key=float) if xs else None,
        "smallest number in the item": lambda xs: min(xs, key=float) if xs else None,
        "most frequent number in the item": lambda xs: Counter(xs).most_common(1)[0][0] if xs else None,
    }
    for name, pick in strategies.items():
        hits = sum(1 for key, xs in typed if (g := pick(xs)) is not None and fam.is_correct(key, {"value": g}))
        if hits / n > MAX_MODAL_SHARE:
            errs.append(f"guessing: '{name}' is right on {hits / n:.0%} of typed items > {MAX_MODAL_SHARE:.0%}")
    return errs


def _semantic_swap_check(fam: ItemFamily) -> list[str]:
    """A typed builder family's answer must not depend on fields left out of SEMANTIC: take the
    decorative fields from another draw and the answer must stay the same."""
    if not isinstance(fam, TypedNumberFamily) or fam.SEMANTIC is None:
        return []
    keep = set(fam.SEMANTIC)
    for i in range(SWAP_CHECKS):
        a = fam.draw(make_rng(VERIFY_SECRET, "swap-a", fam.meta.id, i))
        b = fam.draw(make_rng(VERIFY_SECRET, "swap-b", fam.meta.id, i))
        mixed = {k: (a[k] if k in keep else b.get(k, a[k])) for k in a}
        try:
            same = abs(fam.solve(mixed) - fam.solve(a)) <= TYPED_EXACT
        except Exception as e:  # solve needed a decorative field: that field is semantic
            return [f"semantic: solve() fails when decorative fields change ({type(e).__name__}: {e})"]
        if not same:
            return ["semantic: the answer changes with a field left out of SEMANTIC"]
    return []


def near_miss(key) -> str:
    """A wrong answer close to the key: the number moved by max(1, 5 %), or the text plus a char."""
    try:
        f = float(str(key).replace(",", "."))
    except ValueError:
        return f"{key}x"
    return repr(f + max(1.0, abs(f) * 0.05))


def answer_text(inst: Instance) -> str:
    if inst.input == "choice" and inst.options:
        return next((o["text_md"] for o in inst.options if o["id"] == inst.key), "")
    return str(inst.key)


def verify_family(fam: ItemFamily, n: int = 1000, skills: set[str] | None = None) -> FamilyReport:
    if n < MIN_N:
        raise ValueError(f"verify needs n >= {MIN_N} instances per family, got {n}")
    fid = fam.meta.id
    rep = FamilyReport(family_id=fid, n=n)
    t0 = time.perf_counter()
    rep.errors += check_meta(fam, skills if skills is not None else _skills_catalog())
    fps: list[str] = []
    answers: list[str] = []
    by_content: dict[str, str] = {}
    by_fp: dict[str, str] = {}
    contexts: list[str] = []
    typed: list[tuple[object, list[str]]] = []          # (key, numbers in stem and code)
    positions: Counter[int] = Counter()
    option_counts: Counter[int] = Counter()
    choice_records: list[tuple[list[str], int]] = []
    seen_errors: Counter[str] = Counter()
    checked = 0
    for i in range(n):
        try:
            inst = fam.generate(make_rng(VERIFY_SECRET, "verify", fid, i))
            again = fam.generate(make_rng(VERIFY_SECRET, "verify", fid, i))
        except Exception as e:  # report, keep going
            seen_errors[f"generate: raised {type(e).__name__}: {e}"] += 1
            continue
        try:
            if (inst.view(), inst.key, inst.fingerprint) != (again.view(), again.key, again.fingerprint):
                seen_errors["determinism: same seed rendered a different instance"] += 1
            for err in _check_instance(fam, inst):
                seen_errors[err] += 1
            content = content_of(inst)
            if by_content.setdefault(content, inst.fingerprint) != inst.fingerprint:
                seen_errors["fingerprint: same content, different fingerprint (seed in fingerprint?)"] += 1
            answer = norm_text(answer_text(inst))
            if by_fp.setdefault(inst.fingerprint, answer) != answer:
                seen_errors["fingerprint: same fingerprint, different answer (semantic parameter missing)"] += 1
            fps.append(inst.fingerprint)
            answers.append(norm_text(answer_text(inst)))
            ids = [o["id"] for o in inst.options or []]
            if inst.input == "choice" and inst.key in ids:
                option_counts[len(ids)] += 1
                positions[ids.index(inst.key)] += 1
                choice_records.append(([o["text_md"] for o in inst.options], ids.index(inst.key)))
                contexts.append(f"{inst.stem_md}\n{(inst.code or {}).get('text', '')}")
            elif inst.input == "number":
                typed.append((inst.key, _NUM_TOKEN.findall(f"{inst.stem_md}\n{(inst.code or {}).get('text', '')}")))
            checked += 1
        except Exception as e:  # a check crashed on this instance: report it, keep the run
            seen_errors[f"check: raised {type(e).__name__}: {e}"] += 1
    for err, count in sorted(seen_errors.items()):
        rep.errors.append(f"{err}  [x{count}]")
    if checked < n:
        rep.errors.append(f"coverage: only {checked} of {n} instances were fully checked")
    if fps:
        duplicates = len(fps) - len(set(fps))
        rep.collision_rate = duplicates / len(fps)
        # 0.1 % of the sample, but never less than one duplicate: below n = 1000 a single
        # coincidence would otherwise fail a family whose rate is fine (ARCHITECTURE §5.3 is per 1000).
        rep.distinct_questions = len(set(fps))
        rep.collision_gated = fid not in CONCEPT_FAMILIES
        if rep.collision_gated and duplicates > max(1, int(MAX_COLLISION_RATE * len(fps))):
            rep.errors.append(f"collisions: {rep.collision_rate:.2%} > {MAX_COLLISION_RATE:.1%}")
        labels = len(getattr(fam, "LABELS", ())) or 1
        if not rep.collision_gated and rep.distinct_questions < 2 * labels:
            rep.errors.append(f"concept: only {rep.distinct_questions} distinct questions for {labels} labels "
                              f"(need >= {2 * labels})")
    if typed:
        rep.errors += _typed_guess_checks(fam, typed)
        rep.modal_share = _best_single_answer(fam, typed)[1]
    rep.errors += _semantic_swap_check(fam)
    rep.entropy_bits = entropy_bits(answers)
    rep.distinct_answers = len(set(answers))
    if rep.entropy_bits <= MIN_ENTROPY_BITS:
        rep.errors.append(f"entropy: answer text {rep.entropy_bits:.2f} bits <= {MIN_ENTROPY_BITS}")
    if len(option_counts) > 1:
        rep.errors.append(f"options: the number of options varies {dict(option_counts)} (c is fixed per family)")
    if option_counts:
        rep.errors += _position_check(positions, max(option_counts))
        rep.errors += guessing_checks(choice_records, fam.meta.c, contexts)
    rep.seconds = time.perf_counter() - t0
    return rep


# ── can the answer be guessed from the options alone? ──────────────────────
# Each strategy below looks only at the option texts (what a test-wise candidate sees without
# solving the item). A family fails if any strategy beats the guessing rate c by more than
# guess_margin(c, n), i.e. if the 3PL's fixed c understates how often an ignorant candidate
# is right. The margin is max(0.05, 4 standard errors of a chance-level accuracy): about
# c + 0.055 at n = 1000 and c + 0.10 at n = 300. With ~12 strategies the false-alarm rate of
# a leak-free family stays below 1e-3, and leaks of +0.05 are caught at n = 1000.

MIN_GUESS_SAMPLES = 100
MIN_GUESS_EFFECT = 0.05
GUESS_SE_FACTOR = 4.0
MIN_GROUP = 10
SMOOTHING = 2.0           # pseudo-observations at the chance rate for per-value learning


def guess_margin(c: float, n: int) -> float:
    return max(MIN_GUESS_EFFECT, GUESS_SE_FACTOR * math.sqrt(c * (1 - c) / n))


def _pick_accuracy(records, score) -> float:
    """Accuracy of picking the option with the highest score (ties share credit)."""
    total = 0.0
    for texts, correct in records:
        scores = [score(texts, i) for i in range(len(texts))]
        best = max(scores)
        winners = [i for i, s in enumerate(scores) if s == best]
        total += (correct in winners) / len(winners)
    return total / len(records)


def _as_number(text: str) -> float | None:
    try:
        return float(norm_text(text))
    except ValueError:
        return None


def _as_sequence(text: str) -> tuple[str, ...] | None:
    parts = tuple(p.strip() for p in text.split(","))
    return parts if len(parts) >= 3 and all(parts) else None


def _kendall(a: tuple[str, ...], b: tuple[str, ...]) -> int:
    pos = {x: i for i, x in enumerate(b)}
    seq = [pos.get(x, -1) for x in a]
    return sum(1 for i in range(len(seq)) for j in range(i + 1, len(seq)) if seq[i] > seq[j])


_NUM_TOKEN = re.compile(r"-?\d+(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    return set(_NUM_TOKEN.findall(text))


def guessing_strategies(records: list[tuple[list[str], int]],
                        contexts: list[str] | None = None) -> dict[str, float]:
    """Accuracy of each option-only strategy over the sample. `contexts` (stem + code per record)
    enables the item-consistency strategies: a candidate who does not solve the item can still
    drop options whose numbers never occur in it, or whose length differs from the others."""
    out: dict[str, float] = {}
    out["longest option"] = _pick_accuracy(records, lambda t, i: len(t[i]))
    out["shortest option"] = _pick_accuracy(records, lambda t, i: -len(t[i]))

    def similarity(t, i):
        return sum(difflib.SequenceMatcher(None, t[i], t[j]).ratio() for j in range(len(t)) if j != i)
    out["most similar to the others"] = _pick_accuracy(records, similarity)
    out["least similar to the others"] = _pick_accuracy(records, lambda t, i: -similarity(t, i))

    # The most frequent answer among items that show the same set of options. Learned on one
    # half of the sample and scored on the other (2-fold), because the in-sample mode of small
    # groups overfits: 10 uniform answers out of 4 already give a ~45 % "mode".
    folds: list[dict[frozenset, Counter]] = [{}, {}]
    for idx, (texts, correct) in enumerate(records):
        key = frozenset(norm_text(x) for x in texts)
        folds[idx % 2].setdefault(key, Counter())[norm_text(texts[correct])] += 1
    # Scored over every held-out item: a set seen often enough in the other half gets its mode,
    # any other item a blind guess (1/k). That is the advantage a candidate who memorised past
    # option sets actually has, not the (much higher) rate on the few sets that repeat.
    hits = 0.0
    for train, test in ((folds[0], folds[1]), (folds[1], folds[0])):
        for key, answers in test.items():
            n_test = sum(answers.values())
            learned = train.get(key)
            if not learned or sum(learned.values()) < MIN_GROUP:
                hits += n_test / len(key)
                continue
            top = max(learned.values())
            modes = [a for a, v in learned.items() if v == top]
            hits += sum(answers[a] for a in modes) / len(modes)
    out["most frequent answer for this option set"] = hits / len(records)

    numeric = [r for r in records if all(_as_number(x) is not None for x in r[0])]
    if len(numeric) >= MIN_GUESS_SAMPLES:
        k = len(numeric[0][0])
        for rank in range(k):
            def by_rank(t, i, rank=rank):
                order = sorted(range(len(t)), key=lambda j: _as_number(t[j]))
                return 1 if order.index(i) == rank else 0
            out[f"value rank {rank + 1} of {k}"] = _pick_accuracy(numeric, by_rank)

    out.update(_per_value_strategies(records))

    if contexts is not None and len(contexts) == len(records):
        out["fewest numbers absent from the item"] = _pick_accuracy_ctx(
            records, contexts, lambda t, i, ctx: -len(_numbers(t[i]) - _numbers(ctx)))
        out["most numbers shared with the item"] = _pick_accuracy_ctx(
            records, contexts, lambda t, i, ctx: len(_numbers(t[i]) & _numbers(ctx)))

    def same_count(t, i):
        size = len(_NUM_TOKEN.findall(t[i]))
        return sum(1 for j in range(len(t)) if j != i and len(_NUM_TOKEN.findall(t[j])) == size)
    out["as many numbers as most options"] = _pick_accuracy(records, same_count)

    seqs = [r for r in records if all(_as_sequence(x) for x in r[0])]
    if len(seqs) >= MIN_GUESS_SAMPLES:
        def central(t, i):
            return -sum(_kendall(_as_sequence(t[i]), _as_sequence(t[j])) for j in range(len(t)) if j != i)
        out["order closest to the others"] = _pick_accuracy(seqs, central)
    return out


def _pick_accuracy_ctx(records, contexts, score) -> float:
    total = 0.0
    for (texts, correct), ctx in zip(records, contexts, strict=True):
        scores = [score(texts, i, ctx) for i in range(len(texts))]
        best = max(scores)
        winners = [i for i, s in enumerate(scores) if s == best]
        total += (correct in winners) / len(winners)
    return total / len(records)


def _per_value_strategies(records) -> dict[str, float]:
    """Strategies that learn from single option values, 2-fold cross-validated.

    - 'value correct most often before': per normalised option text, the smoothed rate at which
      it was the answer when shown in the other half; pick the option with the highest rate.
    - 'closest to the typical answer' (numeric options): pick the value closest to the median
      answer of the other half.
    """
    out: dict[str, float] = {}
    halves = [records[0::2], records[1::2]]
    hits_rate = hits_median = 0.0
    numeric_all = all(all(_as_number(x) is not None for x in t) for t, _ in records)
    for train, test in ((halves[0], halves[1]), (halves[1], halves[0])):
        shown: Counter[str] = Counter()
        right: Counter[str] = Counter()
        for texts, correct in train:
            for i, x in enumerate(texts):
                shown[norm_text(x)] += 1
                right[norm_text(x)] += i == correct
        k = len(train[0][0]) if train else 4

        def rate(t, i, shown=shown, right=right, k=k):
            key = norm_text(t[i])
            return (right[key] + SMOOTHING / k) / (shown[key] + SMOOTHING)
        hits_rate += _pick_accuracy(test, rate) * len(test)
        if numeric_all and train:
            answers = sorted(_as_number(t[c]) for t, c in train)
            median = answers[len(answers) // 2]
            hits_median += _pick_accuracy(test, lambda t, i, m=median: -abs(_as_number(t[i]) - m)) * len(test)
    out["value correct most often before"] = hits_rate / len(records)
    if numeric_all:
        out["closest to the typical answer"] = hits_median / len(records)
    return out


def guessing_checks(records: list[tuple[list[str], int]], c: float,
                    contexts: list[str] | None = None) -> list[str]:
    if len(records) < MIN_GUESS_SAMPLES:
        return [f"guessing: only {len(records)} choice instances, need {MIN_GUESS_SAMPLES}"]
    margin = guess_margin(c, len(records))
    errs = []
    for name, acc in guessing_strategies(records, contexts).items():
        if acc > c + margin:
            errs.append(f"guessing: '{name}' is right {acc:.0%} of the time without reading the item "
                        f"(c = {c:.2f}, limit {c + margin:.0%})")
    return errs


# chi-square critical values at alpha = 0.001 by degrees of freedom
_CHI2_999 = {1: 10.83, 2: 13.82, 3: 16.27, 4: 18.47, 5: 20.52, 6: 22.46, 7: 24.32, 8: 26.12, 9: 27.88}


def _position_check(positions: Counter[int], k: int) -> list[str]:
    """Chi-square goodness of fit of the correct option's position against uniform (df = k-1, alpha 0.001)."""
    total = sum(positions.values())
    if k - 1 not in _CHI2_999:
        return [f"position: no critical value for {k} options"]
    expected = total / k
    chi2 = sum((positions.get(p, 0) - expected) ** 2 / expected for p in range(k))
    crit = _CHI2_999[k - 1]
    if chi2 > crit:
        return [f"position: correct option position is predictable (chi2={chi2:.1f} > {crit})"]
    return []


def verify_all(n: int = 1000, only: list[str] | None = None) -> list[FamilyReport]:
    fams = all_families()
    skills = _skills_catalog()
    missing = sorted(set(only or ()) - set(fams))
    if missing:
        raise SystemExit(f"unknown family ids: {missing}")
    ids = [f for f in fams if not only or f in only]
    return [verify_family(fams[f], n, skills) for f in ids]


def _out(line: str) -> None:
    sys.stdout.write(line + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--family", action="append", help="only this family id (repeatable)")
    ap.add_argument("--json", help="also write the reports to this file")
    args = ap.parse_args(argv)
    if args.n < MIN_N:
        ap.error(f"--n must be >= {MIN_N}")
    reports = verify_all(args.n, args.family)
    width = max((len(r.family_id) for r in reports), default=10)
    for r in reports:
        status = "PASS" if r.ok else "FAIL"
        _out(f"{r.family_id:<{width}}  {status}  collisions={r.collision_rate:.3%}  "
             f"entropy={r.entropy_bits:.2f}b  answers={r.distinct_answers}  {r.seconds:.1f}s")
        for e in r.errors:
            _out(f"    - {e}")
    if args.json:
        Path(args.json).write_text(json.dumps([r.to_json() for r in reports], indent=2, ensure_ascii=False),
                                   encoding="utf-8")
    failed = [r.family_id for r in reports if not r.ok]
    _out(f"\n{len(reports) - len(failed)}/{len(reports)} families pass")
    return 1 if failed or not reports else 0


if __name__ == "__main__":
    sys.exit(main())
