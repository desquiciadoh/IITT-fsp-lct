"""Selectors and filter utilities for talent matching and pool searches."""
from typing import Any

from core.enums import LeagueStatus
from django.db.models import Q


def filter_candidate_profiles(queryset, query_params: dict[str, Any]):
    """Apply query param filters to a CandidateProfile queryset."""
    qs = queryset

    # 1. Grades filter (e.g. grades=junior,middle)
    grades_param = query_params.get('grades')
    if grades_param:
        grades = [g.strip().lower() for g in grades_param.split(',') if g.strip()]
        if grades:
            qs = qs.filter(
                Q(claimed_grade__in=grades) |
                Q(user__league_memberships__grade__in=grades)
            ).distinct()

    # 2. Skills filter (e.g. skills=python,django)
    skills_param = query_params.get('skills')
    if skills_param:
        skills = [s.strip().lower() for s in skills_param.split(',') if s.strip()]
        if skills:
            for skill_item in skills:
                qs = qs.filter(
                    Q(skills__skill__id=skill_item) |
                    Q(skills__skill__name__iexact=skill_item)
                ).distinct()

    # 3. FSP filter (fsp=true / 1)
    fsp_param = query_params.get('fsp')
    if fsp_param in ('true', '1', True):
        qs = qs.filter(
            Q(user__fsp_link__isnull=False) |
            Q(user__fsp_results__isnull=False)
        ).distinct()
    elif fsp_param in ('false', '0', False):
        qs = qs.filter(
            user__fsp_link__isnull=True,
            user__fsp_results__isnull=True,
        ).distinct()

    # 4. Work formats filter (formats=remote,hybrid)
    formats_param = query_params.get('formats')
    if formats_param:
        formats = [f.strip().lower() for f in formats_param.split(',') if f.strip()]
        if formats:
            format_q = Q()
            for fmt in formats:
                format_q |= Q(work_formats__contains=[fmt])
            qs = qs.filter(format_q)

    # 5. Salary max filter (salary_max=200000)
    salary_max_param = query_params.get('salary_max')
    if salary_max_param is not None and salary_max_param != '':
        try:
            sal_max = int(salary_max_param)
            qs = qs.filter(salary_min__isnull=False, salary_min__lte=sal_max)
        except (ValueError, TypeError):
            pass

    # 6. Confirmed only (confirmed_only=true / 1)
    confirmed_param = query_params.get('confirmed_only')
    if confirmed_param in ('true', '1', True):
        qs = qs.filter(
            user__league_memberships__status=LeagueStatus.CONFIRMED
        ).distinct()

    # 7. Preset
    preset = query_params.get('preset')
    if preset == 'fsp_stars':
        qs = qs.filter(user__fsp_results__isnull=False).distinct()
    elif preset == 'confirmed':
        qs = qs.filter(user__league_memberships__status=LeagueStatus.CONFIRMED).distinct()

    return qs


def compute_pool_facets(queryset) -> dict[str, Any]:
    """Compute facet counts over a candidate queryset."""
    if hasattr(queryset, 'prefetch_related'):
        profiles = list(queryset.prefetch_related('user__league_memberships', 'user__fsp_results'))
    else:
        profiles = list(queryset)

    grade_counts: dict[str, int] = {}
    format_counts: dict[str, int] = {}
    fsp_count = 0
    confirmed_count = 0

    for p in profiles:
        grade = p.claimed_grade or 'unknown'
        grade_counts[grade] = grade_counts.get(grade, 0) + 1

        for fmt in (p.work_formats or []):
            format_counts[fmt] = format_counts.get(fmt, 0) + 1

        has_fsp = hasattr(p.user, 'fsp_link') or p.user.fsp_results.exists()
        if has_fsp:
            fsp_count += 1

        is_confirmed = any(
            lm.status == LeagueStatus.CONFIRMED
            for lm in p.user.league_memberships.all()
        )
        if is_confirmed:
            confirmed_count += 1

    return {
        'grades': grade_counts,
        'formats': format_counts,
        'fsp_count': fsp_count,
        'fsp_total': fsp_count,
        'confirmed_count': confirmed_count,
    }
