"""Base classes for the two family shapes used in ML-6. Pure; subclasses supply content.

TypedNumberFamily      the candidate types a number (input "number", c = 0). The generator
                       solves the drawn parameters one way; `oracle_value` recomputes from what
                       the candidate sees another way (sqlite, executing the code, a simulator).
                       The key keeps the exact value; an answer is right within half a unit of
                       the requested rounding, so both neighbours of a rounding tie count.
ClassificationFamily   a fixed set of option labels on every item and an answer class drawn
                       uniformly, then a scenario of that class. Nothing in the options points
                       at the answer; `classify` is a rule-based oracle over the rendered text.
(Choice items with distractors derived from the item's parameters were tried and dropped in the
ML-6 reviews: every derived set left an option-only shortcut, first similarity, then the sums of
the options. Code-reading items that ask "what does it print" are typed instead.)

Fingerprints hash the semantic parameters: `SEMANTIC` names the drawn fields that change the
question; decorative fields (names, request ids, contexts) are left out, so the collision rate
counts real repeats (ML.md §3: "sha256 of the drawn parameters").
"""
from __future__ import annotations

import functools
import io
import math
import random

from .base import FamilyMeta, Instance, fingerprint_of
from .kit import choice_options, is_choice_correct, is_number_correct, option_key_for_text


def exact_key(value: float, decimals: int) -> str:
    """Server-side key: the exact value (to 1e-9), not the rounded display, so a candidate who
    rounds half up and one who rounds half to even are both judged against the true value."""
    if decimals == 0:
        return str(int(round(value)))
    return repr(round(value, 9))


def decimals_hint(decimals: int) -> str:
    if decimals == 0:
        return "Ответ — целое число."
    return f"Ответ округлите до {decimals} знак{'а' if decimals == 1 else 'ов'} после запятой."


def semantic_fingerprint(family, p: dict) -> str:
    keys = getattr(family, "SEMANTIC", None)
    params = p if keys is None else {k: p[k] for k in sorted(set(keys) | ({"label"} & set(p)))}
    return fingerprint_of(params)


class TypedNumberFamily:
    meta: FamilyMeta
    DECIMALS = 0
    SEMANTIC: tuple[str, ...] | None = None

    # subclasses implement draw, solve, render, oracle_value
    def draw(self, rng: random.Random) -> dict:
        raise NotImplementedError

    def solve(self, p: dict) -> float:
        raise NotImplementedError

    def render(self, p: dict) -> tuple[str, dict[str, str] | None]:
        raise NotImplementedError

    def oracle_value(self, inst: Instance) -> float:
        raise NotImplementedError

    def hint(self, p: dict) -> str:
        return decimals_hint(self.DECIMALS)

    @property
    def tolerance(self) -> float:
        return 0.0 if self.DECIMALS == 0 else 0.5 * 10 ** -self.DECIMALS + 1e-9

    def generate(self, rng: random.Random) -> Instance:
        p = self.draw(rng)
        stem, code = self.render(p)
        key = exact_key(self.solve(p), self.DECIMALS)
        return Instance(stem_md=f"{stem}\n\n{self.hint(p)}", input="number", key=key,
                        fingerprint=semantic_fingerprint(self, p), code=code)

    def is_correct(self, key, answer: dict) -> bool:
        return is_number_correct(key, answer, self.tolerance)

    def oracle(self, inst: Instance):
        """The independent value at full precision; the harness accepts it when is_correct(key, value)."""
        value = self.oracle_value(inst)
        if value is None or not math.isfinite(value):
            return None
        return exact_key(value, self.DECIMALS)


class ClassificationFamily:
    meta: FamilyMeta
    LABELS: tuple[str, ...] = ()
    SEMANTIC: tuple[str, ...] | None = None

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
        return Instance(stem_md=stem, input="choice", key=key, fingerprint=semantic_fingerprint(self, p),
                        code=code, options=options)

    def is_correct(self, key, answer: dict) -> bool:
        return is_choice_correct(key, answer)

    def oracle(self, inst: Instance):
        label = self.classify(inst)
        return option_key_for_text(inst.options, label) if label is not None else None


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
    """stdout of a program the family itself generated (never user input).

    Used by oracles and, for find_bug, during generation, so it must be thread-safe: `print` is
    bound to a private buffer instead of swapping the process-wide sys.stdout. The restricted
    builtins keep accidents out; they are not a security sandbox (the code comes from templates).
    """
    out = io.StringIO()
    builtins = {**SAFE_BUILTINS, "print": functools.partial(print, file=out), "__import__": _guarded_import}
    exec(compile(code, "<item>", "exec"), {"__builtins__": builtins})  # noqa: S102 - generated code only
    return out.getvalue().strip()
