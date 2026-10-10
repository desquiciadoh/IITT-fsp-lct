"""Topic evidence (ML-3): strong / moderate / limited per topic of a finished session.

A topic is compared with the standard of the reference grade, the grade the session supports
(the claimed grade if confirmed, otherwise the result grade). On the topic's own items:

    E = Σ P_i(cut)                  expected score of a borderline candidate at cut(reference)
    O = Σ u_i                       observed score
    z = (O − E) / √(Σ P_i(1 − P_i)) standardised difference

    strong    z ≥ +0.5   (and at least two items: one answer is not strong evidence)
    limited   z ≤ −1.0
    moderate  otherwise

So "strong SQL" for a confirmed Middle means "on the SQL items you did clearly better than a
borderline Middle would". A posterior-based θ_T was tried first and rejected: with 2–3 items
its prior dominated, and 0/3 correct could still read "strong". Matching scales verified-by-
test skill evidence by these labels (TOPIC_SCALE).
"""
from __future__ import annotations

import math

from .content import Content
from .irt import p_3pl

STRONG_Z = 0.5
LIMITED_Z = -1.0
TOPIC_SCALE = {"strong": 1.0, "moderate": 0.75, "limited": 0.4}


def verified_skills(topics: list[tuple[str, str]], administered: list[dict],
                    skills_by_family: dict[str, tuple[str, ...]]) -> list[str]:
    """Skill ids a finished session verifies: the skills of the answered families whose topic
    came out strong or moderate. BE stores them as CandidateSkill(source="test"); matching then
    scales the evidence by the topic level. Narrower than the topic's skill list on purpose:
    a SQL aggregation item verifies `sql`, not every database in the topic."""
    good = {t for t, level in topics if level in ("strong", "moderate")}
    out: set[str] = set()
    for x in administered:
        if x["correct"] is not None and x["topic"] in good:
            out.update(skills_by_family.get(x["family_id"], ()))
    return sorted(out)


def topic_levels(administered: list[dict], reference_grade: str,
                 content: Content) -> list[tuple[str, str]]:
    """[(topic, level)] sorted by topic id, for answered entries of a session."""
    cut = content.grade(reference_grade).theta_cut
    by_topic: dict[str, list[dict]] = {}
    for x in administered:
        if x["correct"] is not None:
            by_topic.setdefault(x["topic"], []).append(x)
    out = []
    for topic in sorted(by_topic):
        items = by_topic[topic]
        ps = [float(p_3pl(cut, float(x["a"]), float(x["b"]), float(x["c"]))) for x in items]
        expected = sum(ps)
        observed = sum(1 for x in items if x["correct"])
        z = (observed - expected) / math.sqrt(max(sum(p * (1 - p) for p in ps), 1e-9))
        if z >= STRONG_Z and len(items) > 1:
            level = "strong"
        elif z <= LIMITED_Z:
            level = "limited"
        else:
            level = "moderate"
        out.append((topic, level))
    return out
