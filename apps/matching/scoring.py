"""Deterministic matching and explainable scoring service.

INVARIANTS:
1. Every candidate match includes transparent, evidence-based ReasonChips.
2. FSP achievements provide a boost (up to +15), but NEVER decide grade.
3. Candidates are identified to employers ONLY by public_id.
"""

from typing import Any

from core.enums import EvidenceSource, LeagueStatus

from matching.models import Position


def calculate_match_score(
    candidate_profile: Any, position: Position, detailed: bool = True
) -> dict[str, Any]:
    """Calculate match score (0-100) and structured ReasonChips for a candidate-position pair.

    Accepts either a CandidateProfile model instance or a CandidateDTO dictionary.
    """
    reasons = [] if detailed else None
    components = {}

    is_dto = isinstance(candidate_profile, dict)

    # 1. Stack fit (35 points)
    if is_dto:
        candidate_skills = {
            s["name"].lower(): s for s in candidate_profile.get("skills", [])
        }
    else:
        if (
            hasattr(candidate_profile, "_prefetched_objects_cache")
            and "skills" in candidate_profile._prefetched_objects_cache
        ):
            candidate_skills = {
                cs.skill.name.lower(): cs for cs in candidate_profile.skills.all()
            }
        else:
            candidate_skills = {
                cs.skill.name.lower(): cs
                for cs in candidate_profile.skills.select_related("skill").all()
            }

    must_skills = getattr(position, "_cached_must_skills", None)
    if must_skills is None:
        must_skills = [s.lower() for s in (position.must_skills or [])]
        try:
            position._cached_must_skills = must_skills
        except Exception:
            pass

    gaps = [] if detailed else None
    must_matches = 0
    for s in must_skills:
        if s in candidate_skills:
            must_matches += 1
            if detailed:
                cs = candidate_skills[s]
                source = cs.get("source") if isinstance(cs, dict) else cs.source
                skill_name = cs.get("name") if isinstance(cs, dict) else cs.skill.name
                reasons.append(
                    {
                        "kind": "plus",
                        "text": f"Владеет {skill_name}",
                        "source": source,
                    }
                )
        elif detailed:
            reasons.append(
                {
                    "kind": "minus",
                    "text": f"Отсутствует {s} (обязательный)",
                }
            )
            gaps.append(f"Отсутствует обязательный навык {s}")

    skill_score = (must_matches / len(must_skills) * 35) if must_skills else 25
    components["skill"] = round(skill_score, 1)

    # 2. Grade & Verification Fit (25 points)
    if is_dto:
        memberships = candidate_profile.get("league_memberships", [])
        matching_lms = [
            lm for lm in memberships if lm.get("specialization") == position.specialization
        ]
        league = matching_lms[0] if matching_lms else None
        league_grade = league.get("grade") if league else None
        league_status = league.get("status") if league else None
        league_rating = league.get("rating") if league else None
    else:
        user = candidate_profile.user
        if (
            hasattr(user, "_prefetched_objects_cache")
            and "league_memberships" in user._prefetched_objects_cache
        ):
            memberships = list(user.league_memberships.all())
            matching_lms = [
                lm for lm in memberships if lm.specialization == position.specialization
            ]
            league = matching_lms[0] if matching_lms else None
        else:
            league = user.league_memberships.filter(
                specialization=position.specialization
            ).first()
        league_grade = league.grade if league else None
        league_status = league.status if league else None
        league_rating = league.rating if league else None

    grade_score = 0
    if league:
        if league_grade in (position.grades or []):
            if league_status == LeagueStatus.CONFIRMED:
                grade_score = 25
                if detailed:
                    reasons.append(
                        {
                            "kind": "plus",
                            "text": f"Грейд {league_grade.upper()} подтвержден адаптивным тестом",
                            "source": EvidenceSource.TEST,
                        }
                    )
            else:
                grade_score = 15
                if detailed:
                    reasons.append(
                        {
                            "kind": "info",
                            "text": f"Грейд {league_grade.upper()} заявлен, но не подтвержден тестом",
                            "source": EvidenceSource.DECLARED,
                        }
                    )
        else:
            grade_score = 5
            if detailed:
                reasons.append(
                    {
                        "kind": "minus",
                        "text": f"Грейд ({league_grade}) не совпадает с требованиями вакансии",
                    }
                )
                gaps.append(f"Грейд ({league_grade}) не совпадает с требованиями вакансии")
    else:
        grade_score = 5
        if detailed:
            gaps.append("Грейд не подтвержден тестом")

    components["grade"] = grade_score

    # 3. Profile strength & IRT Rating (15 points)
    rating_val = league_rating if league_rating else 1000
    strength_score = min(15, max(0, (rating_val - 800) / 40))
    components["strength"] = round(strength_score, 1)

    # 4. FSP Achievements Boost (15 points)
    fsp_score = 0
    if is_dto:
        fsp_results_count = candidate_profile.get("fsp_results_count", 0)
        fsp_link = candidate_profile.get("fsp_link")
        sports_rank = fsp_link.get("sports_rank") if fsp_link else None
    else:
        fsp_results = list(candidate_profile.user.fsp_results.all())
        fsp_results_count = len(fsp_results)
        fsp_link = getattr(candidate_profile.user, "fsp_link", None)
        sports_rank = fsp_link.sports_rank if fsp_link else None

    if fsp_results_count > 0 or fsp_link:
        fsp_score = min(15, fsp_results_count * 3 + (5 if sports_rank else 0))
        if detailed:
            rank_str = f" (разряд {sports_rank.upper()})" if sports_rank else ""
            reasons.append(
                {
                    "kind": "plus",
                    "text": f"Достижения в турнирах ФСП: {fsp_results_count} соревнований{rank_str}",
                    "source": EvidenceSource.FSP,
                }
            )
    components["fsp"] = fsp_score

    # 5. Salary range fit (10 points)
    salary_score = 10
    if is_dto:
        cand_min = candidate_profile.get("salary_min") or 0
        cand_max = candidate_profile.get("salary_max") or cand_min
    else:
        cand_min = candidate_profile.salary_min or 0
        cand_max = candidate_profile.salary_max or cand_min

    pos_min = position.salary_min
    pos_max = position.salary_max

    if cand_min > 0:
        if cand_min <= pos_max and cand_max >= pos_min:
            if detailed:
                reasons.append(
                    {
                        "kind": "plus",
                        "text": f"Зарплатные ожидания ({cand_min}–{cand_max} ₽) попадают в вилку вакансии",
                    }
                )
            salary_score = 10
        elif cand_min > pos_max:
            if detailed:
                reasons.append(
                    {
                        "kind": "minus",
                        "text": "Ожидания кандидата выше бюджета вакансии",
                    }
                )
                gaps.append("Ожидания кандидата выше бюджета вакансии")
            salary_score = 2
        else:
            salary_score = 8
    components["salary"] = salary_score

    total_score = min(100, sum(components.values()))

    if not detailed:
        return {
            "total_score": round(total_score, 1),
            "components": [],
            "components_dict": components,
            "reasons": [],
            "gaps": [],
        }

    components_list = [
        {
            "key": "skill",
            "value": round(skill_score, 1),
            "weight": 0.35,
            "contribution": round(skill_score, 1),
        },
        {
            "key": "grade",
            "value": float(grade_score),
            "weight": 0.25,
            "contribution": float(grade_score),
        },
        {
            "key": "strength",
            "value": round(strength_score, 1),
            "weight": 0.15,
            "contribution": round(strength_score, 1),
        },
        {"key": "fsp", "value": float(fsp_score), "weight": 0.15, "contribution": float(fsp_score)},
        {
            "key": "salary",
            "value": float(salary_score),
            "weight": 0.10,
            "contribution": float(salary_score),
        },
    ]

    return {
        "total_score": round(total_score, 1),
        "components": components_list,
        "components_dict": components,
        "reasons": reasons,
        "gaps": gaps,
    }
