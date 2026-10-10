"""Selectors and filter utilities for talent matching and pool searches."""

from typing import Any

from core.enums import Grade, LeagueStatus
from django.db.models import Count, Q

GRADE_ORDER = [Grade.INTERN, Grade.JUNIOR, Grade.MIDDLE, Grade.SENIOR]


def get_effective_grades(grades: list[str], allow_adjacent: bool = False) -> list[str]:
    """Return effective acceptable grades for matching.

    If allow_adjacent is True, expands each grade in `grades` to include
    its immediate neighbours in Grade order (intern <-> junior <-> middle <-> senior).
    """
    if not grades:
        return []

    normalized_grades = [g.strip().lower() for g in grades if g]
    if not allow_adjacent:
        return list(dict.fromkeys(normalized_grades))

    effective = set()
    for g in normalized_grades:
        effective.add(g)
        if g in GRADE_ORDER:
            idx = GRADE_ORDER.index(g)
            if idx > 0:
                effective.add(GRADE_ORDER[idx - 1])
            if idx < len(GRADE_ORDER) - 1:
                effective.add(GRADE_ORDER[idx + 1])

    # Return in GRADE_ORDER for determinism
    return [g for g in GRADE_ORDER if g in effective]


def filter_position_candidates_sql(queryset, position):
    """Apply SQL hard filters for a position to candidate profiles.

    Hard filters (BE.md N1):
    1. Specialization: matches position specialization (profile or league membership)
    2. Grade adjacency: matches effective grades (profile or league membership)
    3. Work formats: candidate formats overlap position formats, or candidate has open formats
    4. Salary max: candidate salary_min <= position salary_max, or candidate has no salary_min set
    """
    qs = queryset

    # 1. Specialization
    if position.specialization:
        qs = qs.filter(
            Q(specialization=position.specialization)
            | Q(user__league_memberships__specialization=position.specialization)
        )

    # 2. Grade adjacency
    effective_grades = get_effective_grades(position.grades or [], position.allow_adjacent)
    if effective_grades:
        qs = qs.filter(
            Q(claimed_grade__in=effective_grades)
            | Q(
                user__league_memberships__grade__in=effective_grades,
                user__league_memberships__specialization=position.specialization,
            )
        )

    # 3. Work formats
    if position.work_formats:
        qs = qs.filter(
            Q(work_formats__overlap=position.work_formats) | Q(work_formats=[])
        )

    # 4. Salary max
    if position.salary_max:
        qs = qs.filter(
            Q(salary_min__isnull=True)
            | Q(salary_min=0)
            | Q(salary_min__lte=position.salary_max)
        )

    return qs.distinct()


def filter_candidate_profiles(queryset, query_params: dict[str, Any]):
    """Apply query param filters to a CandidateProfile queryset."""
    qs = queryset

    # 1. Grades filter (e.g. grades=junior,middle)
    grades_param = query_params.get("grades")
    if grades_param:
        grades = [g.strip().lower() for g in grades_param.split(",") if g.strip()]
        if grades:
            qs = qs.filter(
                Q(claimed_grade__in=grades) | Q(user__league_memberships__grade__in=grades)
            ).distinct()

    # 2. Skills filter (e.g. skills=python,django)
    skills_param = query_params.get("skills")
    if skills_param:
        skills = [s.strip().lower() for s in skills_param.split(",") if s.strip()]
        if skills:
            for skill_item in skills:
                qs = qs.filter(
                    Q(skills__skill__id=skill_item) | Q(skills__skill__name__iexact=skill_item)
                ).distinct()

    # 3. FSP filter (fsp=true / 1)
    fsp_param = query_params.get("fsp")
    if fsp_param in ("true", "1", True):
        qs = qs.filter(
            Q(user__fsp_link__isnull=False) | Q(user__fsp_results__isnull=False)
        ).distinct()
    elif fsp_param in ("false", "0", False):
        qs = qs.filter(
            user__fsp_link__isnull=True,
            user__fsp_results__isnull=True,
        ).distinct()

    # 4. Work formats filter (formats=remote,hybrid)
    formats_param = query_params.get("formats")
    if formats_param:
        formats = [f.strip().lower() for f in formats_param.split(",") if f.strip()]
        if formats:
            format_q = Q()
            for fmt in formats:
                format_q |= Q(work_formats__contains=[fmt])
            qs = qs.filter(format_q)

    # 5. Salary max filter (salary_max=200000)
    salary_max_param = query_params.get("salary_max")
    if salary_max_param is not None and salary_max_param != "":
        try:
            sal_max = int(salary_max_param)
            qs = qs.filter(salary_min__isnull=False, salary_min__lte=sal_max)
        except (ValueError, TypeError):
            pass

    # 6. Confirmed only (confirmed_only=true / 1)
    confirmed_param = query_params.get("confirmed_only")
    if confirmed_param in ("true", "1", True):
        qs = qs.filter(user__league_memberships__status=LeagueStatus.CONFIRMED).distinct()

    # 7. Preset
    preset = query_params.get("preset")
    if preset == "fsp_stars":
        qs = qs.filter(user__fsp_results__isnull=False).distinct()
    elif preset == "confirmed":
        qs = qs.filter(user__league_memberships__status=LeagueStatus.CONFIRMED).distinct()

    return qs


def compute_pool_facets(queryset) -> dict[str, Any]:
    """Compute facet counts over a candidate queryset using pure SQL."""
    if isinstance(queryset, list):
        profiles = queryset
        grade_counts: dict[str, int] = {}
        format_counts: dict[str, int] = {}
        fsp_count = 0
        confirmed_count = 0

        for p in profiles:
            grade = p.claimed_grade or "unknown"
            grade_counts[grade] = grade_counts.get(grade, 0) + 1
            for fmt in p.work_formats or []:
                format_counts[fmt] = format_counts.get(fmt, 0) + 1
            has_fsp = hasattr(p.user, "fsp_link") or getattr(p.user, "fsp_results", None)
            if has_fsp:
                fsp_count += 1
            is_confirmed = any(
                lm.status == LeagueStatus.CONFIRMED
                for lm in getattr(p.user, "league_memberships", []).all()
            ) if hasattr(p.user, "league_memberships") else False
            if is_confirmed:
                confirmed_count += 1

        return {
            "grades": grade_counts,
            "formats": format_counts,
            "fsp_count": fsp_count,
            "fsp_total": fsp_count,
            "confirmed_count": confirmed_count,
        }

    # 1. SQL-level grade counts
    grade_rows = (
        queryset.values("claimed_grade")
        .annotate(count=Count("pk", distinct=True))
        .order_by()
    )
    grade_counts = {}
    for row in grade_rows:
        grade = row.get("claimed_grade")
        if grade:
            grade_counts[grade] = row["count"]

    # 2. SQL-level aggregate format counts, FSP, and confirmed without multi-table Cartesian joins
    from assessment.models import LeagueMembership
    from fsp_sync.models import FSPLink, FSPResult
    from django.db.models import Exists, OuterRef

    fsp_exists = Exists(FSPLink.objects.filter(candidate_id=OuterRef("user_id"))) | Exists(
        FSPResult.objects.filter(candidate_id=OuterRef("user_id"))
    )
    confirmed_exists = Exists(
        LeagueMembership.objects.filter(
            candidate_id=OuterRef("user_id"),
            status=LeagueStatus.CONFIRMED,
        )
    )

    agg = queryset.annotate(
        _has_fsp=fsp_exists,
        _has_confirmed=confirmed_exists,
    ).aggregate(
        remote=Count("pk", filter=Q(work_formats__contains=["remote"])),
        hybrid=Count("pk", filter=Q(work_formats__contains=["hybrid"])),
        office=Count("pk", filter=Q(work_formats__contains=["office"])),
        fsp=Count("pk", filter=Q(_has_fsp=True)),
        confirmed=Count("pk", filter=Q(_has_confirmed=True)),
    )

    format_counts = {}
    for fmt in ("remote", "hybrid", "office"):
        cnt = agg.get(fmt, 0)
        if cnt > 0:
            format_counts[fmt] = cnt

    fsp_count = agg.get("fsp", 0)
    confirmed_count = agg.get("confirmed", 0)

    return {
        "grades": grade_counts,
        "formats": format_counts,
        "fsp_count": fsp_count,
        "fsp_total": fsp_count,
        "confirmed_count": confirmed_count,
    }
