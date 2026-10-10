"""Helpers shared by family modules: option building, answer normalisation, typed-answer checks."""
from __future__ import annotations

import random
import unicodedata
from collections.abc import Sequence

from .base import option_id

# Characters a typed number may contain that mean nothing (spaces) or a plain ASCII sign.
NUMBER_CHARS = {" ": "", "\u00a0": "", "\u202f": "", "\u2212": "-"}


def norm_text(s: str) -> str:
    """Canonical form for comparing answers: NFKC, case, whitespace, decimal comma, numeric value."""
    s = unicodedata.normalize("NFKC", str(s)).strip().lower().replace(",", ".")
    s = " ".join(s.split())
    try:
        f = float(s)
    except ValueError:
        return s
    return repr(f) if f == f and f not in (float("inf"), float("-inf")) else s


def choice_options(rng: random.Random, correct: str, distractors: Sequence[str],
                   k: int = 4) -> tuple[list[dict[str, str]], str]:
    """k shuffled options with opaque ids: the correct text plus the first k-1 distinct distractors.

    Distractors are given in priority order (most plausible misconception first). Raises if fewer
    than k-1 distinct distractors remain after normalisation, so a family can never ship a
    question with a duplicate or a missing option.
    """
    seen = {norm_text(correct)}
    picked: list[str] = []
    for d in distractors:
        key = norm_text(d)
        if key not in seen:
            seen.add(key)
            picked.append(d)
        if len(picked) == k - 1:
            break
    if len(picked) < k - 1:
        raise ValueError(f"need {k - 1} distinct distractors, got {len(picked)}")
    texts = [correct, *picked]
    ids: list[str] = []
    while len(ids) < k:
        oid = option_id(rng)
        if oid not in ids:
            ids.append(oid)
    order = list(range(k))
    rng.shuffle(order)
    options = [{"id": ids[j], "text_md": texts[order[j]]} for j in range(k)]
    key = options[order.index(0)]["id"]
    return options, key


def option_key_for_text(options: Sequence[dict[str, str]], text: str) -> str | None:
    """The id of the option whose text is exactly `text` up to whitespace (oracles use this).

    Stricter than norm_text on purpose: a rendering bug in case or decimal separator must make
    the oracle disagree, not be normalised away.
    """
    target = " ".join(str(text).split())
    hits = [o["id"] for o in options if " ".join(o["text_md"].split()) == target]
    return hits[0] if len(hits) == 1 else None


def is_choice_correct(key: str, answer: dict) -> bool:
    oid = answer.get("option_id") if isinstance(answer, dict) else None
    return isinstance(oid, str) and oid == key


def is_number_correct(key: str, answer: dict, tol: float = 0.0) -> bool:
    """Typed numeric answer: decimal comma or point, spaces ignored; |answer − key| <= tol."""
    raw = answer.get("value") if isinstance(answer, dict) else None
    if not isinstance(raw, str):
        return False
    raw = "".join(NUMBER_CHARS.get(ch, ch) for ch in raw.strip()).replace(",", ".")
    if not raw or len(raw) > 32:
        return False
    try:
        got = float(raw)
    except ValueError:
        return False
    if got != got:  # NaN
        return False
    return abs(got - float(key)) <= tol + 1e-9
