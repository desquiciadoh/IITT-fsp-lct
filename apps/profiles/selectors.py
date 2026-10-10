"""Profiles app selectors for clean data retrieval and privacy boundaries."""
from core.enums import ConsentType, LeagueStatus
from django.db.models import OuterRef, Subquery
from identity.models import Consent

from profiles.models import CandidateProfile


def visible_candidates_for(company):
    """Return queryset of CandidateProfiles visible to the specified company.

    Privacy and visibility invariant (BE.md B4, B5; TASKS §1.3):
    1. open_to_offers is True
    2. Candidate email is verified (email_verified_at is not null)
    3. Latest PUBLICATION consent is granted (revoked consent hides candidate)
    4. League status is not PENDING (candidate must have at least one assessed/confirmed league)
    5. Company is not in candidate's blocked_company_ids
    """
    latest_pub = Consent.objects.filter(
        user_id=OuterRef('user_id'),
        type=ConsentType.PUBLICATION,
    ).order_by('-created_at').values('granted')[:1]

    # Query profiles matching requirements 1-3
    qs = CandidateProfile.objects.filter(
        open_to_offers=True,
        user__email_verified_at__isnull=False,
    ).annotate(
        pub_granted=Subquery(latest_pub),
    ).filter(
        pub_granted=True,
    )

    # Exclude candidates whose league status is only PENDING
    # If they have a membership, at least one must be non-pending
    qs = qs.exclude(
        user__league_memberships__status=LeagueStatus.PENDING,
        user__league_memberships__confirmed_at__isnull=True,
    )

    # Filter out candidates who blocked this company
    # Note: blocked_company_ids is ArrayField of UUIDs or strings
    company_id_str = str(company.id)
    company_id = company.id

    visible_ids = [
        c.user_id for c in qs
        if not (
            c.blocked_company_ids
            and (company_id in c.blocked_company_ids or company_id_str in [str(x) for x in c.blocked_company_ids])
        )
    ]
    return CandidateProfile.objects.filter(user_id__in=visible_ids)


def is_candidate_visible_to_company(candidate_profile, company) -> bool:
    """Check if a single candidate profile is visible to the given company."""
    if not candidate_profile.open_to_offers:
        return False
    if not candidate_profile.user.email_verified_at:
        return False

    latest_pub = candidate_profile.user.consents.filter(
        type=ConsentType.PUBLICATION,
    ).order_by('-created_at').first()
    if not latest_pub or not latest_pub.granted:
        return False

    # Check blocked companies
    company_id_str = str(company.id)
    company_id = company.id
    if candidate_profile.blocked_company_ids:
        blocked_strs = [str(x) for x in candidate_profile.blocked_company_ids]
        if company_id in candidate_profile.blocked_company_ids or company_id_str in blocked_strs:
            return False

    # Check league status is not pending
    has_pending_only = candidate_profile.user.league_memberships.filter(
        status=LeagueStatus.PENDING,
        confirmed_at__isnull=True,
    ).exists() and not candidate_profile.user.league_memberships.exclude(
        status=LeagueStatus.PENDING,
    ).exists()
    if has_pending_only:
        return False

    return True
