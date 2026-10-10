"""Matching domain services for talent search and candidate pools.

INVARIANTS:
1. SQL hard filters (specialization, grade adjacency, work formats, salary max)
   are applied before fetching candidates into Python.
2. Candidates are retrieved in batched queries with select_related / prefetch_related,
   converted to DTO dicts, and scored without issuing per-candidate DB queries.
3. Facet counts and search pagination are executed at the database level.
"""

from typing import Any

from assessment.models import LeagueMembership
from django.db.models import Count
from fsp_sync.models import FSPResult
from profiles.models import CandidateProfile, CandidateSkill
from profiles.selectors import visible_candidates_for

from matching.models import Company, Position, Shortlist
from matching.scoring import calculate_match_score
from matching.selectors import (
    compute_pool_facets,
    filter_candidate_profiles,
    filter_position_candidates_sql,
)
from matching.serializers import TalentShortSerializer


def candidate_to_dto(profile: CandidateProfile) -> dict[str, Any]:
    """Convert a prefetched CandidateProfile into a CandidateDTO dict for the scorer."""
    user = profile.user
    skills = [
        {
            "id": cs.skill_id,
            "name": cs.skill.name,
            "source": cs.source,
            "level": cs.level,
        }
        for cs in profile.skills.all()
    ]
    leagues = [
        {
            "specialization": lm.specialization,
            "grade": lm.grade,
            "status": lm.status,
            "rating": lm.rating,
            "percentile": lm.percentile,
            "strength": lm.strength,
        }
        for lm in user.league_memberships.all()
    ]
    fsp_link = getattr(user, "fsp_link", None)
    fsp_results = list(user.fsp_results.all())

    return {
        "user_id": profile.user_id,
        "public_id": profile.public_id,
        "full_name": profile.full_name,
        "blind_mode": profile.blind_mode,
        "city": profile.city,
        "work_formats": profile.work_formats or [],
        "specialization": profile.specialization,
        "claimed_grade": profile.claimed_grade,
        "salary_min": profile.salary_min or 0,
        "salary_max": profile.salary_max or (profile.salary_min or 0),
        "salary_type": profile.salary_type,
        "last_active_at": profile.last_active_at,
        "skills": skills,
        "league_memberships": leagues,
        "fsp_link": {
            "sports_rank": fsp_link.sports_rank if fsp_link else None,
        }
        if fsp_link
        else None,
        "fsp_results_count": len(fsp_results),
        "profile": profile,
    }


def fetch_candidate_dtos(filtered_qs) -> list[dict[str, Any]]:
    """Fetch candidate DTOs using fast values queries without instantiating thousands of models."""
    profile_rows = list(
        filtered_qs.order_by().values(
            "user_id",
            "public_id",
            "full_name",
            "blind_mode",
            "city",
            "work_formats",
            "specialization",
            "claimed_grade",
            "salary_min",
            "salary_max",
            "salary_type",
            "last_active_at",
            "user__fsp_link__sports_rank",
        )
    )
    if not profile_rows:
        return []

    user_ids = [r["user_id"] for r in profile_rows]

    # Batch skills via subquery on user_ids
    user_id_subquery = filtered_qs.order_by().values("user_id")
    skills_by_user: dict[int, list[dict[str, Any]]] = {}
    for row in (
        CandidateSkill.objects.filter(candidate_id__in=user_id_subquery)
        .order_by()
        .values("candidate_id", "skill_id", "skill__name", "source", "level")
    ):
        skills_by_user.setdefault(row["candidate_id"], []).append(
            {
                "id": row["skill_id"],
                "name": row["skill__name"],
                "source": row["source"],
                "level": row["level"],
            }
        )

    # Batch leagues via subquery on user_ids
    leagues_by_user: dict[int, list[dict[str, Any]]] = {}
    for row in (
        LeagueMembership.objects.filter(candidate_id__in=user_id_subquery)
        .order_by()
        .values(
            "candidate_id",
            "specialization",
            "grade",
            "status",
            "rating",
            "percentile",
            "strength",
        )
    ):
        leagues_by_user.setdefault(row["candidate_id"], []).append(
            {
                "specialization": row["specialization"],
                "grade": row["grade"],
                "status": row["status"],
                "rating": row["rating"],
                "percentile": row["percentile"],
                "strength": row["strength"],
            }
        )

    # Batch FSP results count via subquery on user_ids
    fsp_counts: dict[int, int] = {}
    for row in (
        FSPResult.objects.filter(candidate_id__in=user_id_subquery)
        .order_by()
        .values("candidate_id")
        .annotate(cnt=Count("id"))
    ):
        fsp_counts[row["candidate_id"]] = row["cnt"]

    dtos = []
    for r in profile_rows:
        uid = r["user_id"]
        sports_rank = r["user__fsp_link__sports_rank"]
        dtos.append(
            {
                "user_id": uid,
                "public_id": r["public_id"],
                "full_name": r["full_name"],
                "blind_mode": r["blind_mode"],
                "city": r["city"],
                "work_formats": r["work_formats"] or [],
                "specialization": r["specialization"],
                "claimed_grade": r["claimed_grade"],
                "salary_min": r["salary_min"] or 0,
                "salary_max": r["salary_max"] or (r["salary_min"] or 0),
                "salary_type": r["salary_type"],
                "last_active_at": r["last_active_at"],
                "skills": skills_by_user.get(uid, []),
                "league_memberships": leagues_by_user.get(uid, []),
                "fsp_link": {"sports_rank": sports_rank} if sports_rank is not None else None,
                "fsp_results_count": fsp_counts.get(uid, 0),
            }
        )
    return dtos


def attach_verified_topics(profiles: list[CandidateProfile]) -> None:
    """Batch-fetch verified assessment topics for profiles in a single query."""
    if not profiles:
        return
    candidate_ids = [p.user_id for p in profiles]
    from assessment.models import AssessmentItem
    from core.enums import AssessmentStatus

    items = (
        AssessmentItem.objects.filter(
            assessment__candidate_id__in=candidate_ids,
            assessment__status=AssessmentStatus.FINISHED,
            correct=True,
        )
        .values("assessment__candidate_id", "family__topic")
        .distinct()
    )
    topics_map: dict[Any, list[str]] = {}
    for it in items:
        cid = it["assessment__candidate_id"]
        topic = it["family__topic"]
        if topic:
            topics_map.setdefault(cid, []).append(topic)

    for p in profiles:
        p._verified_topics = topics_map.get(p.user_id, [])


def get_position_pool(
    position: Position,
    company: Company,
    query_params: dict[str, Any],
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """Retrieve and score candidates in the position pool."""
    # 1. Base visible candidates for company
    candidates_qs = visible_candidates_for(company)

    # 2. SQL-level facet counts across all visible candidates for this company
    facets = compute_pool_facets(candidates_qs)

    # 3. Apply position SQL hard filters (specialization, grade adjacency, work formats, salary max)
    filtered_qs = filter_position_candidates_sql(candidates_qs, position)

    # 4. Apply additional query param filters (grades, skills, fsp, etc.)
    filtered_qs = filter_candidate_profiles(filtered_qs, query_params)

    # 5. Fetch lightweight DTO dicts for scoring
    dtos = fetch_candidate_dtos(filtered_qs)

    # 6. Shortlist IDs for this position
    shortlisted_user_ids = set(
        Shortlist.objects.filter(position=position).values_list("candidate_id", flat=True)
    )

    # 7. Score candidates with pure DTOs (zero DB queries)
    scored_items = []
    for dto in dtos:
        score_data = calculate_match_score(dto, position)
        scored_items.append(
            {
                "user_id": dto["user_id"],
                "score": score_data["total_score"],
                "components": score_data["components"],
                "reasons": score_data["reasons"],
                "gaps": score_data.get("gaps", []),
                "shortlisted": dto["user_id"] in shortlisted_user_ids,
            }
        )

    # 8. Sort by total score descending
    scored_items.sort(key=lambda x: x["score"], reverse=True)

    # 9. Paginate
    total = len(scored_items)
    pages = max(1, (total + size - 1) // size) if total > 0 else 1
    start = (page - 1) * size
    end = start + size
    page_items = scored_items[start:end]

    # 10. Fetch and hydrate full models ONLY for the requested page
    page_user_ids = [item["user_id"] for item in page_items]
    if page_user_ids:
        page_profiles_qs = (
            CandidateProfile.objects.filter(user_id__in=page_user_ids)
            .select_related("user", "user__fsp_link")
            .prefetch_related(
                "skills__skill",
                "user__league_memberships",
                "user__fsp_results",
            )
        )
        profiles_by_id = {p.user_id: p for p in page_profiles_qs}
        page_profiles = [profiles_by_id[uid] for uid in page_user_ids if uid in profiles_by_id]
        attach_verified_topics(page_profiles)

        items = [
            {
                "talent": TalentShortSerializer(profiles_by_id[item["user_id"]]).data,
                "score": item["score"],
                "components": item["components"],
                "reasons": item["reasons"],
                "gaps": item["gaps"],
                "shortlisted": item["shortlisted"],
            }
            for item in page_items
            if item["user_id"] in profiles_by_id
        ]
    else:
        items = []

    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": pages,
        "facets": facets,
        "relaxations": [],
    }


def search_talent(
    company: Company,
    query_params: dict[str, Any],
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """Execute general talent search with SQL facets and pagination."""
    # 1. Base visible candidates for company
    candidates_qs = visible_candidates_for(company)

    # 2. SQL facets
    facets = compute_pool_facets(candidates_qs)

    # 3. Apply query param filters
    filtered_qs = filter_candidate_profiles(candidates_qs, query_params)

    # 4. SQL pagination
    total = filtered_qs.count()
    pages = max(1, (total + size - 1) // size) if total > 0 else 1
    start = (page - 1) * size
    end = start + size

    paged_qs = filtered_qs.select_related(
        "user",
        "user__fsp_link",
    ).prefetch_related(
        "skills__skill",
        "user__league_memberships",
        "user__fsp_results",
    )[start:end]

    paged_candidates = list(paged_qs)
    attach_verified_topics(paged_candidates)

    items = [TalentShortSerializer(c).data for c in paged_candidates]

    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": pages,
        "facets": facets,
    }
