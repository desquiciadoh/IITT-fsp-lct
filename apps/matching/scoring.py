"""Deterministic matching and explainable scoring service.

INVARIANTS:
1. Every candidate match includes transparent, evidence-based ReasonChips.
2. FSP achievements provide a boost (up to +15), but NEVER decide grade.
3. Candidates are identified to employers ONLY by public_id.
"""
from typing import Any
from profiles.models import CandidateProfile
from matching.models import Position
from core.enums import EvidenceSource, GradeDecision, LeagueStatus


def calculate_match_score(candidate_profile: CandidateProfile, position: Position) -> dict[str, Any]:
    """Calculate match score (0-100) and structured ReasonChips for a candidate-position pair."""
    reasons = []
    components = {}

    # 1. Stack fit (35 points)
    candidate_skills = {cs.skill.name.lower(): cs for cs in candidate_profile.skills.select_related('skill').all()}
    must_skills = [s.lower() for s in (position.must_skills or [])]
    nice_skills = [s.lower() for s in (position.nice_skills or [])]

    gaps = []
    must_matches = 0
    for s in must_skills:
        if s in candidate_skills:
            must_matches += 1
            cs = candidate_skills[s]
            reasons.append({
                'kind': 'plus',
                'text': f"Владеет {cs.skill.name}",
                'source': cs.source,
            })
        else:
            reasons.append({
                'kind': 'minus',
                'text': f"Отсутствует {s} (обязательный)",
            })
            gaps.append(f"Отсутствует обязательный навык {s}")

    skill_score = (must_matches / len(must_skills) * 35) if must_skills else 25
    components['skill'] = round(skill_score, 1)

    # 2. Grade & Verification Fit (25 points)
    league = candidate_profile.user.league_memberships.filter(specialization=position.specialization).first()
    grade_score = 0
    if league:
        if league.grade in (position.grades or []):
            if league.status == LeagueStatus.CONFIRMED:
                grade_score = 25
                reasons.append({
                    'kind': 'plus',
                    'text': f"Грейд {league.grade.upper()} подтвержден адаптивным тестом",
                    'source': EvidenceSource.TEST,
                })
            else:
                grade_score = 15
                reasons.append({
                    'kind': 'info',
                    'text': f"Грейд {league.grade.upper()} заявлен, но не подтвержден тестом",
                    'source': EvidenceSource.DECLARED,
                })
        else:
            grade_score = 5
            reasons.append({
                'kind': 'minus',
                'text': f"Грейд ({league.grade}) не совпадает с требованиями вакансии",
            })
            gaps.append(f"Грейд ({league.grade}) не совпадает с требованиями вакансии")
    else:
        grade_score = 5
        gaps.append("Грейд не подтвержден тестом")

    components['grade'] = grade_score

    # 3. Profile strength & IRT Rating (15 points)
    rating_val = league.rating if (league and league.rating) else 1000
    strength_score = min(15, max(0, (rating_val - 800) / 40))
    components['strength'] = round(strength_score, 1)

    # 4. FSP Achievements Boost (15 points)
    fsp_score = 0
    fsp_results = list(candidate_profile.user.fsp_results.all())
    fsp_link = getattr(candidate_profile.user, 'fsp_link', None)
    if fsp_results or fsp_link:
        fsp_score = min(15, len(fsp_results) * 3 + (5 if fsp_link and fsp_link.sports_rank else 0))
        rank_str = f" (разряд {fsp_link.sports_rank.upper()})" if fsp_link and fsp_link.sports_rank else ""
        reasons.append({
            'kind': 'plus',
            'text': f"Достижения в турнирах ФСП: {len(fsp_results)} соревнований{rank_str}",
            'source': EvidenceSource.FSP,
        })
    components['fsp'] = fsp_score

    # 5. Salary range fit (10 points)
    salary_score = 10
    cand_min = candidate_profile.salary_min or 0
    cand_max = candidate_profile.salary_max or cand_min
    pos_min = position.salary_min
    pos_max = position.salary_max

    if cand_min > 0:
        if cand_min <= pos_max and cand_max >= pos_min:
            reasons.append({
                'kind': 'plus',
                'text': f"Зарплатные ожидания ({cand_min}–{cand_max} ₽) попадают в вилку вакансии",
            })
            salary_score = 10
        elif cand_min > pos_max:
            reasons.append({
                'kind': 'minus',
                'text': f"Ожидания кандидата выше бюджета вакансии",
            })
            gaps.append("Ожидания кандидата выше бюджета вакансии")
            salary_score = 2
        else:
            salary_score = 8
    components['salary'] = salary_score

    total_score = min(100, sum(components.values()))

    components_list = [
        {'key': 'skill', 'value': round(skill_score, 1), 'weight': 0.35, 'contribution': round(skill_score, 1)},
        {'key': 'grade', 'value': float(grade_score), 'weight': 0.25, 'contribution': float(grade_score)},
        {'key': 'strength', 'value': round(strength_score, 1), 'weight': 0.15, 'contribution': round(strength_score, 1)},
        {'key': 'fsp', 'value': float(fsp_score), 'weight': 0.15, 'contribution': float(fsp_score)},
        {'key': 'salary', 'value': float(salary_score), 'weight': 0.10, 'contribution': float(salary_score)},
    ]

    return {
        'total_score': round(total_score, 1),
        'components': components_list,
        'components_dict': components,
        'reasons': reasons,
        'gaps': gaps,
    }
