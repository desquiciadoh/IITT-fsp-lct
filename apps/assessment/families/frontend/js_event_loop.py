"""fe.js.event_loop.v2: output order of sync logs, microtasks and timers.

A random sequence of 4-6 statements mixes `console.log`, `setTimeout` (0/5/20 ms),
`Promise.resolve().then` and `queueMicrotask`, so the order is a function of the draw. The
generator ranks statements by queue (sync < microtask < timer by delay); the oracle parses
the code the candidate sees and runs a small event-loop simulator. tests/ml also runs a
sample through real Node.js when it is installed.

Difficulty prior b = 0.2 (lower middle): the micro/macrotask order is a standard frontend
interview question, but mixed delays and queueMicrotask trip up juniors. Distractors are
the usual wrong models: program order, timers before microtasks, async in program order,
queueMicrotask treated as a timer, microtasks run as a stack; when a short script makes
several of them coincide, random orders that keep the sync logs first fill the gap (never
near-copies of the answer, which made the answer the 'centre' of the options).
"""
from __future__ import annotations

import random
import re

from ..base import FamilyMeta, Instance, fingerprint_of
from ..kit import choice_options, is_choice_correct, option_key_for_text

META = FamilyMeta(id="fe.js.event_loop.v2", version=2, specs=("frontend",),
                  topic="js.event_loop", skills=("javascript",), format="code_output",
                  a=1.4, b=0.2, c=0.25, time_limit_s=90)

KINDS = ("sync", "timeout", "promise", "microtask")
DELAYS = (0, 5, 20)
LABELS = "ABCDEFGHJK"


def _line(kind: str, label: str, delay: int) -> str:
    log = f"console.log('{label}')"
    if kind == "sync":
        return f"{log};"
    if kind == "timeout":
        return f"setTimeout(() => {log}, {delay});"
    if kind == "promise":
        return f"Promise.resolve().then(() => {log});"
    return f"queueMicrotask(() => {log});"


def _discordant(a, b) -> int:
    """Kendall distance: pairs of letters that two orders put the other way round."""
    pos = {x: i for i, x in enumerate(b)}
    s = [pos[x] for x in a]
    return sum(1 for i in range(len(s)) for j in range(i + 1, len(s)) if s[i] > s[j])


def _centrality_rank(options: list[list[str]]) -> int | None:
    """How many options are strictly closer to all the others than options[0]; None on a tie."""
    totals = [sum(_discordant(o, p) for p in options if p is not o) for o in options]
    if totals.count(totals[0]) > 1:
        return None
    return sum(1 for t in totals[1:] if t < totals[0])


def _pick_distractors(rng: random.Random, correct, wrong_models, fillers) -> list[list[str]]:
    """Three wrong orders such that the answer's centrality rank among the four is uniform.

    Distractors built from misconceptions each change one aspect of the true order, so the
    true order tends to be the one closest to all others: a test-wise candidate picks it
    without reading the code (ML-1 review). We draw the rank the answer must have (0 = most
    central .. 3 = least), then sample triples, misconceptions preferred, until one fits.
    """
    pool: list[list[str]] = []
    for order in wrong_models + fillers:
        if order != correct and order not in pool:
            pool.append(order)
    wrong = [o for o in pool if o in wrong_models]
    target = rng.randrange(4)
    fallback = None
    for attempt in range(400):
        source = wrong if attempt < 100 and len(wrong) >= 3 else pool
        if len(source) < 3:
            source = pool
        if len(source) < 3:
            break
        triple = rng.sample(source, 3)
        rank = _centrality_rank([correct, *triple])
        if rank == target:
            return triple
        if fallback is None and rank is not None:
            fallback = triple
    if fallback is None:
        if len(pool) < 3:
            raise ValueError("fewer than three distinct wrong orders")
        fallback = pool[:3]
    return fallback


def _fmt(labels) -> str:
    return ", ".join(labels)


class JsEventLoop:
    meta = META

    def generate(self, rng: random.Random) -> Instance:
        while True:
            n = rng.randint(4, 6)
            kinds = [rng.choice(KINDS) for _ in range(n)]
            if "sync" in kinds and "timeout" in kinds and ({"promise", "microtask"} & set(kinds)):
                break
        labels = rng.sample(LABELS, n)
        delays = [rng.choice(DELAYS) if k == "timeout" else 0 for k in kinds]
        stmts = list(zip(kinds, labels, delays, strict=True))
        params = {"stmts": stmts}

        rank = {"sync": 0, "promise": 1, "microtask": 1, "timeout": 2}
        idx = range(n)
        correct = [labels[i] for i in sorted(idx, key=lambda i: (rank[kinds[i]], delays[i], i))]
        program = list(labels)
        timers_first = [labels[i] for i in sorted(idx, key=lambda i: ({"sync": 0, "timeout": 1}.get(
            kinds[i], 2), delays[i], i))]
        async_in_order = [labels[i] for i in sorted(idx, key=lambda i: (kinds[i] != "sync", i))]
        qm_as_timer = [labels[i] for i in sorted(idx, key=lambda i: (
            {"sync": 0, "promise": 1}.get(kinds[i], 2), delays[i] if kinds[i] == "timeout" else 0, i))]
        micro = [i for i in idx if rank[kinds[i]] == 1]
        stack = [labels[i] for i in idx if kinds[i] == "sync"] + [labels[i] for i in reversed(micro)] + \
            [labels[i] for i in sorted((i for i in idx if kinds[i] == "timeout"), key=lambda i: (delays[i], i))]
        timers_by_order = [labels[i] for i in sorted(idx, key=lambda i: (rank[kinds[i]], i))]
        wrong_models = [program, timers_first, async_in_order, qm_as_timer, stack, timers_by_order]
        sync = [labels[i] for i in idx if kinds[i] == "sync"]
        rest = [x for x in correct if x not in sync]
        fillers = []
        for _ in range(24):
            perm = rest[:]
            rng.shuffle(perm)
            fillers.append(sync + perm)
        for _ in range(24):            # a short async tail has few sync-first orders
            perm = list(labels)
            rng.shuffle(perm)
            fillers.append(perm)
        distractors = [_fmt(x) for x in _pick_distractors(rng, correct, wrong_models, fillers)]
        options, key = choice_options(rng, _fmt(correct), distractors)
        code = "\n".join(_line(k, lab, d) for k, lab, d in stmts)
        return Instance(stem_md="В каком порядке буквы появятся в консоли после выполнения скрипта?",
                        input="choice", key=key, fingerprint=fingerprint_of(params),
                        code={"lang": "javascript", "text": code}, options=options)

    def is_correct(self, key, answer: dict) -> bool:
        return is_choice_correct(key, answer)

    def oracle(self, inst: Instance):
        return option_key_for_text(inst.options, _fmt(simulate(inst.code["text"])))


_PATTERNS = (
    ("sync", re.compile(r"^console\.log\('(\w)'\);$")),
    ("timeout", re.compile(r"^setTimeout\(\(\) => console\.log\('(\w)'\), (\d+)\);$")),
    ("micro", re.compile(r"^Promise\.resolve\(\)\.then\(\(\) => console\.log\('(\w)'\)\);$")),
    ("micro", re.compile(r"^queueMicrotask\(\(\) => console\.log\('(\w)'\)\);$")),
)


def _parse(line: str) -> tuple[str, re.Match]:
    for kind, pat in _PATTERNS:
        m = pat.match(line)
        if m:
            return kind, m
    raise ValueError(f"unsupported statement: {line}")


def simulate(code: str) -> list[str]:
    """Run the script's top-level statements through a minimal event loop.

    The script body is one macrotask: sync logs print at once, callbacks go to the microtask
    queue or to a timer heap keyed by (due time, creation order). After the body the microtask
    queue drains completely, then timers fire one by one, each followed by a microtask drain.
    """
    out: list[str] = []
    microtasks: list[str] = []
    timers: list[tuple[int, int, str]] = []
    for seq, line in enumerate(x.strip() for x in code.splitlines() if x.strip()):
        kind, m = _parse(line)
        if kind == "sync":
            out.append(m.group(1))
        elif kind == "micro":
            microtasks.append(m.group(1))
        else:
            # Node and browsers clamp 0 ms to 1 ms; only the relative order matters here.
            timers.append((max(1, int(m.group(2))), seq, m.group(1)))
    while microtasks:
        out.append(microtasks.pop(0))
    for _, _, label in sorted(timers):
        out.append(label)
        while microtasks:
            out.append(microtasks.pop(0))
    return out


FAMILY = JsEventLoop()
