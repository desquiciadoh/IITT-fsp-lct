"""Match features (ML-4; ARCHITECTURE §2.6). Each returns a value in 0..1 and Russian reason chips.

SkillFit    Σ w·evidence / Σ w over the need's skills, must w = 2, nice w = 1.
            evidence(skill) = max(direct, 0.5 · best direct evidence of a related skill)
            direct: test 1.0 × topic level (strong 1.0 / moderate 0.75 / limited 0.4, from the
            candidate's CatResult topics that cover the skill; level if no topic), FSP or
            micro-task 0.8 × level, declared 0.4 × level.
            A need without skills gives 0.5 (no information either way).
GradeFit    exact grade: confirmed 1.0, unconfirmed 0.6; adjacent grade (only if allowed):
            0.5, × 0.6 if unconfirmed (0.3); otherwise 0.
SalaryFit   both ranges in gross (salary.to_gross, NDFL scale). Expectation [cmin, cmax], budget max B:
            cmax <= B                -> 1.0
            cmin <= B < cmax         -> 0.5 + 0.5 · (B − cmin)/(cmax − cmin)
            cmin > B                 -> 0.5 · max(0, 1 − (cmin − B)/(0.25 · B))  (0 at 25 % over budget)
            no expectation           -> 0.5
SemanticFit cosine of the need and profile embeddings mapped linearly from [0.2, 0.8] to [0, 1];
            0.5 while embeddings are off (ML-9).
Freshness   0.5^(days since last activity / 30).
"""
from __future__ import annotations

import datetime
import functools
import math

from .salary import to_gross
from .strength import freshness
from .types import GRADES, CandidateCtx, NeedCtx, Reason

MUST_W, NICE_W = 2.0, 1.0
SOURCE_BASE = {"test": 1.0, "fsp": 0.8, "microtask": 0.8, "declared": 0.4}
TOPIC_SCALE = {"strong": 1.0, "moderate": 0.75, "limited": 0.4}
RELATED_FACTOR = 0.5
UNCONFIRMED_GRADE = 0.6
ADJACENT_GRADE = 0.5
OVER_BUDGET_ZERO = 0.25
SEMANTIC_LO, SEMANTIC_HI = 0.2, 0.8
NEUTRAL = 0.5

SOURCE_RU = {"test": "подтверждён тестом", "fsp": "подтверждён ФСП", "microtask": "подтверждён микрозадачей",
             "declared": "заявлен"}
GRADE_RU = {"intern": "Intern", "junior": "Junior", "middle": "Middle", "senior": "Senior"}


# ── taxonomy (AI-owned skills.yaml, ML-owned topics) ───────────────────────

@functools.lru_cache(maxsize=1)
def _skill_names() -> dict[str, str]:
    from taxonomy.loader import load_skills
    return {sid: e.name for sid, e in load_skills().items()}


@functools.lru_cache(maxsize=1)
def _related() -> dict[str, tuple[str, ...]]:
    """Undirected related-skill graph from skills.yaml (sorted for determinism)."""
    from taxonomy.loader import load_skills
    graph: dict[str, set[str]] = {}
    for sid, e in load_skills().items():
        for r in e.related:
            graph.setdefault(sid, set()).add(r)
            graph.setdefault(r, set()).add(sid)
    return {k: tuple(sorted(v)) for k, v in graph.items()}


@functools.lru_cache(maxsize=1)
def _skill_topics() -> dict[str, tuple[str, ...]]:
    from assessment.engine.content import load_content
    out: dict[str, list[str]] = {}
    for t in load_content().topics.values():
        for s in t.skills:
            out.setdefault(s, []).append(t.id)
    return {k: tuple(sorted(v)) for k, v in out.items()}


def skill_name(skill_id: str) -> str:
    return _skill_names().get(skill_id, skill_id)


# ── SkillFit ───────────────────────────────────────────────────────────────

def direct_evidence(c: CandidateCtx, skill_id: str) -> tuple[float, str | None]:
    """Best direct evidence for a skill and its source (0, None if the candidate has none)."""
    best, best_src = 0.0, None
    for e in sorted(c.skills, key=lambda e: (e.skill_id, e.source, e.level)):
        if e.skill_id != skill_id or e.source not in SOURCE_BASE:
            continue
        level = min(1.0, max(0.0, float(e.level)))
        if e.source == "test":
            topic_levels = [c.topic_levels[t] for t in _skill_topics().get(skill_id, ()) if t in c.topic_levels]
            if topic_levels:
                level = max(TOPIC_SCALE.get(lv, 0.0) for lv in topic_levels)
        value = SOURCE_BASE[e.source] * level
        if value > best:
            best, best_src = value, e.source
    return best, best_src


def skill_fit(need: NeedCtx, c: CandidateCtx) -> tuple[float, list[Reason], list[str]]:
    weighted = [(s, MUST_W, True) for s in need.must_skills] + \
               [(s, NICE_W, False) for s in need.nice_skills if s not in need.must_skills]
    if not weighted:
        return NEUTRAL, [Reason("info", "В вакансии не указаны навыки", None)], []
    reasons: list[Reason] = []
    gaps: list[str] = []
    total = got = 0.0
    hit_must = 0
    for skill, w, must in weighted:
        name = skill_name(skill)
        ev, src = direct_evidence(c, skill)
        rel_ev, rel_skill = 0.0, None
        for r in _related().get(skill, ()):
            r_ev, _ = direct_evidence(c, r)
            if RELATED_FACTOR * r_ev > rel_ev:
                rel_ev, rel_skill = RELATED_FACTOR * r_ev, r
        value = max(ev, rel_ev)
        total += w
        got += w * value
        if ev > 0:
            hit_must += must
            kind = "plus" if src in ("test", "fsp", "microtask") else "info"
            reasons.append(Reason(kind, f"{name} {SOURCE_RU[src]}", src))
        elif must:
            gaps.append(name)                            # no direct evidence of a must-have
            if rel_skill is None:
                reasons.append(Reason("minus", f"Нет обязательного навыка: {name}", None))
        if rel_ev > ev:
            reasons.append(Reason("info", f"{name}: засчитан смежный навык {skill_name(rel_skill)}", None))
    n_must = len(need.must_skills)
    if n_must:
        reasons.insert(0, Reason("info", f"Обязательные навыки: {hit_must} из {n_must}", None))
    return got / total, reasons, gaps


# ── GradeFit ───────────────────────────────────────────────────────────────

def _adjacent(a: str, b: str) -> bool:
    return abs(GRADES.index(a) - GRADES.index(b)) == 1


def grade_fit(need: NeedCtx, c: CandidateCtx) -> tuple[float, list[Reason]]:
    g = c.league_grade
    confirmed = c.league_status == "confirmed"
    if g is None:
        return 0.0, [Reason("minus", "Нет результата квалификации", None)]
    name = GRADE_RU[g]
    if g in need.grades:
        if confirmed:
            return 1.0, [Reason("plus", f"Грейд {name} подтверждён тестом", "test")]
        return UNCONFIRMED_GRADE, [Reason("info", f"Грейд {name} не подтверждён тестом", "declared")]
    if need.allow_adjacent and any(_adjacent(g, x) for x in need.grades):
        value = ADJACENT_GRADE * (1.0 if confirmed else UNCONFIRMED_GRADE)
        status = "подтверждён" if confirmed else "не подтверждён"
        return value, [Reason("info", f"Соседний грейд {name} ({status})", "test" if confirmed else "declared")]
    return 0.0, [Reason("minus", f"Грейд {name} не подходит вакансии", None)]


# ── SalaryFit ──────────────────────────────────────────────────────────────

def _rub(x: int) -> str:
    return f"{x:,}".replace(",", " ") + " ₽"


def salary_fit(need: NeedCtx, c: CandidateCtx) -> tuple[float, list[Reason]]:
    if not c.salary_min or not c.salary_type:
        return NEUTRAL, [Reason("info", "Зарплатные ожидания не указаны", None)]
    cmin = to_gross(c.salary_min, c.salary_type)
    cmax = to_gross(c.salary_max, c.salary_type) if c.salary_max else cmin
    cmax = max(cmax, cmin)
    budget = to_gross(need.salary_max, need.salary_type)
    shown = f"{_rub(cmin)}–{_rub(cmax)} gross" if cmax > cmin else f"{_rub(cmin)} gross"
    if cmax <= budget:
        return 1.0, [Reason("plus", f"Ожидания {shown} в пределах вилки", "declared")]
    if cmin <= budget:
        value = 0.5 + 0.5 * (budget - cmin) / (cmax - cmin)
        return value, [Reason("info", f"Ожидания {shown} частично в вилке", "declared")]
    over = (cmin - budget) / budget
    value = 0.5 * max(0.0, 1.0 - over / OVER_BUDGET_ZERO)
    return value, [Reason("minus", f"Ожидания выше бюджета на {math.ceil(over * 100)} %", "declared")]


# ── SemanticFit, Freshness ─────────────────────────────────────────────────

def cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("embeddings differ in dimension")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def semantic_fit(need: NeedCtx, c: CandidateCtx) -> tuple[float, list[Reason]]:
    if need.embedding is None or c.embedding is None:
        return NEUTRAL, [Reason("info", "Смысловое сходство не рассчитано", None)]
    cos = cosine(need.embedding, c.embedding)
    value = min(1.0, max(0.0, (cos - SEMANTIC_LO) / (SEMANTIC_HI - SEMANTIC_LO)))
    kind = "plus" if value >= 0.66 else "info" if value >= 0.33 else "minus"
    words = {"plus": "высокое", "info": "среднее", "minus": "низкое"}[kind]
    return value, [Reason(kind, f"Опыт и описание вакансии: {words} смысловое сходство", "declared")]


def freshness_fit(c: CandidateCtx, now: datetime.datetime) -> tuple[float, list[Reason]]:
    if c.last_active_at is None:
        return 0.0, [Reason("info", "Нет данных об активности", None)]
    value = freshness(c.last_active_at, now)
    days = max(0, int((now - c.last_active_at).total_seconds() // 86400))
    text = "Активен сегодня" if days == 0 else f"Был активен {days} дн. назад"
    return value, [Reason("info" if days > 30 else "plus", text, None)]
