"""Schema validation and normalization for LLM output payloads (AI-R3).

Validates and normalizes dictionaries from LLM responses, cache, or rule engines into
type-safe, sanitized ResumeDraft and JdDraft instances with enum mapping,
bounds checking, salary sanitization, and string length caps.
"""
from __future__ import annotations

import re
from typing import Any

from .base import LlmSchemaError
from .types import JdDraft, ResumeDraft

_SPEC_MAP = {
    "backend": "backend",
    "бэкенд": "backend",
    "бэкендер": "backend",
    "back-end": "backend",
    "frontend": "frontend",
    "фронтенд": "frontend",
    "front-end": "frontend",
    "back end": "backend",
    "бекенд": "backend",
    "бэк": "backend",
    "front end": "frontend",
    "фронт": "frontend",
    "фронтэнд": "frontend",
    "ml_data": "ml_data",
    "ml": "ml_data",
    "ml/data": "ml_data",
    "data": "ml_data",
    "data science": "ml_data",
    "data scientist": "ml_data",
    "data engineer": "ml_data",
    "ml engineer": "ml_data",
    "ml-инженер": "ml_data",
    "дата саентист": "ml_data",
    "машинное обучение": "ml_data",
    "machine learning": "ml_data",
    "ai": "ml_data",
}

_GRADE_MAP = {
    "intern": "intern",
    "trainee": "intern",
    "стажер": "intern",
    "стажёр": "intern",
    "junior": "junior",
    "junior+": "junior",
    "джуниор": "junior",
    "джун": "junior",
    "младший": "junior",
    "middle": "middle",
    "middle+": "middle",
    "мидл": "middle",
    "миддл": "middle",
    "senior": "senior",
    "senior+": "senior",
    "сеньор": "senior",
    "сениор": "senior",
    "ведущий": "senior",
    "старший": "senior",
    "lead": "senior",
    "team lead": "senior",
    "тимлид": "senior",
}

_FORMAT_MAP = {
    "remote": "remote",
    "удаленка": "remote",
    "удалёнка": "remote",
    "удаленно": "remote",
    "удалённо": "remote",
    "дистанционно": "remote",
    "hybrid": "hybrid",
    "гибрид": "hybrid",
    "гибридный": "hybrid",
    "office": "office",
    "офис": "office",
    "в офисе": "office",
}

_SALARY_TYPE_MAP = {
    "net": "net",
    "на руки": "net",
    "чистыми": "net",
    "после вычета": "net",
    "после налогов": "net",
    "gross": "gross",
    "до вычета": "gross",
    "до налогов": "gross",
    "грязными": "gross",
    "с учетом ндфл": "gross",
    "с учётом ндфл": "gross",
}


def _enum_key(val: Any) -> str:
    """'  Middle+ ' -> 'middle+', 'Back-End.' -> 'back-end'."""
    if val is None or isinstance(val, (bool, dict, list)):
        return ""
    return re.sub(r"\s+", " ", str(val)).strip().strip(".,;:!").lower()


def _clean_str(val: Any, max_len: int = 100) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    return s[:max_len]


def _clean_list_str(vals: Any, max_item_len: int = 60, max_items: int = 60) -> list[str]:
    if not isinstance(vals, (list, tuple)):
        return []
    res: list[str] = []
    seen: set[str] = set()
    for v in vals:
        s = _clean_str(v, max_item_len)
        if s and s.lower() not in seen:
            seen.add(s.lower())
            res.append(s)
            if len(res) >= max_items:
                break
    return res


def _clean_enum_list(vals: Any, mapping: dict[str, str]) -> list[str]:
    if not isinstance(vals, (list, tuple)):
        return []
    res: list[str] = []
    seen: set[str] = set()
    for v in vals:
        if not v:
            continue
        mapped = mapping.get(_enum_key(v))
        if mapped and mapped not in seen:
            seen.add(mapped)
            res.append(mapped)
    return res


_SALARY_STR_RE = re.compile(
    r"^\D*?(\d[\d\s\xa0]*(?:[.,]\d+)?)\s*(k|к|тыс\.?|тысяч[а-я]*|млн|mln)?(?![a-zа-яё])",
    re.IGNORECASE,
)


def _clean_salary_num(val: Any) -> int | None:
    """250000, "250 000", "250k", "150 тыс", "1,5 млн" -> RUB; out of (0, 10 000 000] -> None."""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        num = int(val)
    else:
        m = _SALARY_STR_RE.match(str(val).strip())
        if not m:
            return None
        number = float(re.sub(r"[\s\xa0]", "", m.group(1)).replace(",", "."))
        suffix = (m.group(2) or "").lower()
        scale = 1_000_000 if suffix in ("млн", "mln") else 1000 if suffix else 1
        num = int(number * scale)
    return num if 0 < num <= 10_000_000 else None


def validate_resume_payload(d: dict[str, Any], *, require_data: bool = True) -> ResumeDraft:
    """Validate and normalize a raw dict into a validated ResumeDraft.

    require_data=False is for the rules output: an empty draft is a valid answer there.
    """
    if not isinstance(d, dict):
        raise LlmSchemaError("Payload is not a dictionary", reason="schema")

    specialization = _SPEC_MAP.get(_enum_key(d.get("specialization")))
    claimed_grade = _GRADE_MAP.get(_enum_key(d.get("claimed_grade")))

    years_raw = d.get("years_experience")
    years_exp: float | None = None
    if years_raw is not None and not isinstance(years_raw, bool):
        try:
            y = float(str(years_raw).replace(",", "."))
            if 0.0 <= y <= 50.0:
                years_exp = round(y, 1)
        except ValueError:
            pass

    roles = _clean_list_str(d.get("roles"), max_item_len=100, max_items=5)
    skills_raw = _clean_list_str(d.get("skills_raw"), max_item_len=60, max_items=60)
    work_formats = _clean_enum_list(d.get("work_formats"), _FORMAT_MAP)

    sal_min = _clean_salary_num(d.get("salary_min"))
    sal_max = _clean_salary_num(d.get("salary_max"))
    if sal_min is not None and sal_max is not None and sal_max < sal_min:
        sal_min, sal_max = sal_max, sal_min

    salary_type = _SALARY_TYPE_MAP.get(_enum_key(d.get("salary_type")))

    city = _clean_str(d.get("city"), max_len=100)
    about = _clean_str(d.get("about"), max_len=500)
    experience_text = _clean_str(d.get("experience_text"), max_len=4000)

    # Sanity check: must have at least one usable piece of information
    has_data = any([
        specialization, claimed_grade, years_exp is not None, roles,
        skills_raw, work_formats, sal_min, sal_max, city, about, experience_text
    ])
    if require_data and not has_data:
        raise LlmSchemaError("Payload has no usable fields", reason="schema")

    return ResumeDraft(
        specialization=specialization,
        claimed_grade=claimed_grade,
        years_experience=years_exp,
        roles=roles,
        skills_raw=skills_raw,
        work_formats=work_formats,
        salary_min=sal_min,
        salary_max=sal_max,
        salary_type=salary_type,
        city=city,
        about=about,
        experience_text=experience_text,
    )


def validate_jd_payload(d: dict[str, Any], *, require_data: bool = True) -> JdDraft:
    """Validate and normalize a raw dict into a validated JdDraft."""
    if not isinstance(d, dict):
        raise LlmSchemaError("Payload is not a dictionary", reason="schema")

    title = _clean_str(d.get("title"), max_len=200)

    specialization = _SPEC_MAP.get(_enum_key(d.get("specialization")))

    grades = _clean_enum_list(d.get("grades"), _GRADE_MAP)
    must_skills = _clean_list_str(d.get("must_skills_raw"), max_item_len=60, max_items=60)
    nice_skills = _clean_list_str(d.get("nice_skills_raw"), max_item_len=60, max_items=60)
    # Deduplicate nice skills if they are already in must skills
    must_lowered = {s.lower() for s in must_skills}
    nice_skills = [s for s in nice_skills if s.lower() not in must_lowered]

    work_formats = _clean_enum_list(d.get("work_formats"), _FORMAT_MAP)
    location = _clean_str(d.get("location"), max_len=100)

    sal_min = _clean_salary_num(d.get("salary_min"))
    sal_max = _clean_salary_num(d.get("salary_max"))
    if sal_min is not None and sal_max is not None and sal_max < sal_min:
        sal_min, sal_max = sal_max, sal_min

    salary_type = _SALARY_TYPE_MAP.get(_enum_key(d.get("salary_type")))

    team_context = _clean_str(d.get("team_context"), max_len=1000)
    description = _clean_str(d.get("description"), max_len=4000)

    has_data = any([
        title, specialization, grades, must_skills, nice_skills,
        work_formats, location, sal_min, sal_max, description
    ])
    if require_data and not has_data:
        raise LlmSchemaError("Payload has no usable fields", reason="schema")

    return JdDraft(
        title=title,
        specialization=specialization,
        grades=grades,
        must_skills_raw=must_skills,
        nice_skills_raw=nice_skills,
        work_formats=work_formats,
        location=location,
        salary_min=sal_min,
        salary_max=sal_max,
        salary_type=salary_type,
        team_context=team_context,
        description=description,
    )
