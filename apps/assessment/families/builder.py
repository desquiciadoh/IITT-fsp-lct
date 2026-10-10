"""Base classes for the three family shapes used in ML-6/ML-13. Pure; subclasses supply content.

TypedNumberFamily      the candidate types a number (input "number", c = 0). The generator
                       solves the drawn parameters one way; `oracle_value` recomputes from what
                       the candidate sees another way (sqlite, executing the code, a simulator).
ClassificationFamily   a fixed set of option labels on every item and an answer class drawn
                       uniformly, then a scenario of that class. Nothing in the options points
                       at the answer (the complexity lesson in ML-1); `classify` is a rule-based
                       oracle over the rendered text.
RedrawChoiceFamily     choice items whose distractors are the answers of independent redraws
                       of the same generator (the answer's own distribution: no value, rank or
                       size leaks, ML-1 SQL lesson), plus one misconception on a share of items.

All randomness comes from the rng given to `generate`; fingerprints hash the parameters.
"""
from __future__ import annotations

import contextlib
import io
import math
import random
from typing import Any

from .base import FamilyMeta, Instance, fingerprint_of
from .kit import (
    choice_options,
    is_choice_correct,
    is_number_correct,
    norm_text,
    option_key_for_text,
)


def fmt_number(value: float, decimals: int) -> str:
    """Canonical key text: an integer, or exactly `decimals` digits after the point."""
    if decimals == 0:
        return str(int(round(value)))
    return f"{round(value, decimals):.{decimals}f}"


def decimals_hint(decimals: int) -> str:
    if decimals == 0:
        return "Ответ — целое число."
    return f"Ответ округлите до {decimals} знак{'а' if decimals in (2, 3, 4) else 'ов'} после запятой."


class TypedNumberFamily:
    meta: FamilyMeta
    DECIMALS = 0

    # subclasses implement draw, solve, render, oracle_value
    def draw(self, rng: random.Random) -> dict:
        raise NotImplementedError

    def solve(self, p: dict) -> float:
        raise NotImplementedError

    def render(self, p: dict) -> tuple[str, dict[str, str] | None]:
        raise NotImplementedError

    def oracle_value(self, inst: Instance) -> float:
        raise NotImplementedError

    @property
    def tolerance(self) -> float:
        return 0.0 if self.DECIMALS == 0 else 0.5 * 10 ** -self.DECIMALS + 1e-9

    def generate(self, rng: random.Random) -> Instance:
        p = self.draw(rng)
        stem, code = self.render(p)
        key = fmt_number(self.solve(p), self.DECIMALS)
        return Instance(stem_md=f"{stem}\n\n{decimals_hint(self.DECIMALS)}", input="number", key=key,
                        fingerprint=fingerprint_of(p), code=code)

    def is_correct(self, key, answer: dict) -> bool:
        return is_number_correct(key, answer, self.tolerance)

    def oracle(self, inst: Instance):
        """The independent value, two digits finer than the key; the harness accepts it when
        is_correct(key, value) holds, i.e. within the answer's own rounding."""
        value = self.oracle_value(inst)
        if value is None or not math.isfinite(value):
            return None
        return fmt_number(value, self.DECIMALS + 2)


class ClassificationFamily:
    meta: FamilyMeta
    LABELS: tuple[str, ...] = ()
    STEM = ""

    def draw(self, rng: random.Random, label: str) -> dict:
        raise NotImplementedError

    def render(self, p: dict) -> tuple[str, dict[str, str] | None]:
        raise NotImplementedError

    def classify(self, inst: Instance) -> str | None:
        raise NotImplementedError

    def generate(self, rng: random.Random) -> Instance:
        label = self.LABELS[rng.randrange(len(self.LABELS))]
        p = self.draw(rng, label)
        p["label"] = label
        stem, code = self.render(p)
        others = [x for x in self.LABELS if x != label]
        options, key = choice_options(rng, label, others, k=len(self.LABELS))
        return Instance(stem_md=stem, input="choice", key=key, fingerprint=fingerprint_of(p), code=code,
                        options=options)

    def is_correct(self, key, answer: dict) -> bool:
        return is_choice_correct(key, answer)

    def oracle(self, inst: Instance):
        label = self.classify(inst)
        return option_key_for_text(inst.options, label) if label is not None else None


class RedrawChoiceFamily:
    meta: FamilyMeta
    MISCONCEPTION_SHARE = 0.15
    K = 4

    def draw(self, rng: random.Random) -> dict:
        raise NotImplementedError

    def answer(self, p: dict) -> str:
        raise NotImplementedError

    def misconceptions(self, p: dict) -> list[str]:
        return []

    def render(self, p: dict) -> tuple[str, dict[str, str] | None]:
        raise NotImplementedError

    def oracle_answer(self, inst: Instance) -> str | None:
        raise NotImplementedError

    def generate(self, rng: random.Random) -> Instance:
        p = self.draw(rng)
        correct = self.answer(p)
        seen = {norm_text(correct)}
        values = []
        wrong = sorted({m for m in self.misconceptions(p) if norm_text(m) not in seen})
        if wrong and rng.random() < self.MISCONCEPTION_SHARE:
            values.append(wrong[rng.randrange(len(wrong))])
            seen.add(norm_text(values[-1]))
        attempts = 0
        while len(values) < self.K - 1:
            attempts += 1
            if attempts > 500:
                raise ValueError("could not draw distinct distractor answers")
            v = self.answer(self.draw(rng))
            if norm_text(v) not in seen:
                seen.add(norm_text(v))
                values.append(v)
        stem, code = self.render(p)
        options, key = choice_options(rng, correct, values, k=self.K)
        return Instance(stem_md=stem, input="choice", key=key, fingerprint=fingerprint_of(p), code=code,
                        options=options)

    def is_correct(self, key, answer: dict) -> bool:
        return is_choice_correct(key, answer)

    def oracle(self, inst: Instance):
        text = self.oracle_answer(inst)
        return option_key_for_text(inst.options, text) if text is not None else None


# ── oracle helpers ─────────────────────────────────────────────────────────

SAFE_BUILTINS = {name: getattr(__builtins__, name) if not isinstance(__builtins__, dict) else __builtins__[name]
                 for name in ("print", "range", "len", "sum", "min", "max", "list", "dict", "set", "tuple",
                              "sorted", "enumerate", "zip", "abs", "str", "int", "float", "round",
                              "isinstance", "reversed", "any", "all", "map", "filter", "divmod", "bool")}


ALLOWED_IMPORTS = frozenset({"heapq", "math", "bisect", "collections", "functools", "itertools", "statistics"})


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name not in ALLOWED_IMPORTS or level:
        raise ImportError(f"import of {name!r} is not allowed in item code")
    return __import__(name, globals, locals, fromlist, level)


def run_python(code: str) -> str:
    """stdout of a generated program (verify harness and tests only; never user input)."""
    out = io.StringIO()
    ns: dict[str, Any] = {"__builtins__": {**SAFE_BUILTINS, "__import__": _guarded_import}}
    with contextlib.redirect_stdout(out):
        exec(compile(code, "<item>", "exec"), ns)  # noqa: S102 - the family's own generated code
    return out.getvalue().strip()
