"""Profiles app selectors for clean data retrieval and privacy boundaries."""

from assessment.models import LeagueMembership
from core.enums import ConsentType, LeagueStatus
from django.db.models import Exists, OuterRef, Q, Subquery
from identity.models import Consent

from profiles.models import CandidateProfile


def visible_candidates_for(company):
    """Return queryset of CandidateProfiles visible to the specified company.

    Privacy and visibility invariant (BE.md R5, B4, B5; TASKS §1.3):
    1. The latest publication consent is granted
    2. open_to_offers is True
    3. Candidate email is verified (email_verified_at is not null)
    4. At least one non-pending league exists (Exists(...))
    5. Company is not in candidate's blocked_company_ids (~Q(blocked_company_ids__contains=[company.id]))
    6. Ordered deterministically with tiebreaker on user_id
    """
    latest_pub = (
        Consent.objects.filter(
            user_id=OuterRef("user_id"),
            type=ConsentType.PUBLICATION,
        )
        .order_by("-created_at", "-id")
        .values("granted")[:1]
    )

    non_pending_league = LeagueMembership.objects.filter(
        candidate_id=OuterRef("user_id"),
    ).exclude(
        status=LeagueStatus.PENDING,
    )

    return (
        CandidateProfile.objects.annotate(pub_granted=Subquery(latest_pub))
        .filter(
            pub_granted=True,
            open_to_offers=True,
            user__email_verified_at__isnull=False,
        )
        .filter(Exists(non_pending_league))
        .filter(~Q(blocked_company_ids__contains=[company.id]))
        .order_by("-last_active_at", "user_id")
    )


def is_candidate_visible_to_company(candidate_profile, company) -> bool:
    """Check if a single candidate profile is visible to the given company."""
    if not candidate_profile:
        return False
    return visible_candidates_for(company).filter(pk=candidate_profile.pk).exists()
