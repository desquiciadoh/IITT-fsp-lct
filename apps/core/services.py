"""Contact access service — the gatekeeper for candidate contacts.

SECURITY INVARIANT: Candidate contacts (email, phone, telegram) are NEVER
returned to an employer without an active ContactGrant. Every access attempt
is logged to AuditLog, whether successful or not.

This service is the ONLY pathway to read candidate contacts for employer-facing
views. Direct queries to CandidateContact from employer views are forbidden.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.utils import timezone

from core.errors import ContactNotGranted
from identity.models import AuditLog
from outreach.models import ContactGrant
from profiles.models import CandidateContact

if TYPE_CHECKING:
    import uuid

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContactInfo:
    """Contact information returned to an authorized employer."""
    full_name: str
    email: str
    phone: str
    telegram: str


class ContactAccessService:
    """Gatekeeper for candidate contact data.

    Enforces the zero-leak invariant:
    1. Check for an active (non-revoked) ContactGrant
    2. Log the access attempt to AuditLog
    3. Return contacts only if grant exists, else raise ContactNotGranted
    """

    @staticmethod
    def get_contacts(
        company_id: uuid.UUID,
        candidate_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> ContactInfo:
        """Retrieve candidate contacts if an active grant exists.

        Args:
            company_id: The employer's company UUID
            candidate_id: The candidate's user UUID
            actor_id: The user performing the access (for audit)

        Returns:
            ContactInfo with the candidate's contact details

        Raises:
            ContactNotGranted: If no active grant exists (also logged)
        """
        grant = ContactGrant.objects.filter(
            company_id=company_id,
            candidate_id=candidate_id,
            revoked_at__isnull=True,
        ).first()

        if grant is None:
            # Log the failed access attempt
            AuditLog.objects.create(
                actor_id=actor_id,
                action='contact_access_denied',
                target_type='CandidateContact',
                target_id=str(candidate_id),
                meta={
                    'company_id': str(company_id),
                    'reason': 'no_active_grant',
                },
            )
            logger.warning(
                'Contact access denied: company=%s candidate=%s actor=%s',
                company_id, candidate_id, actor_id,
            )
            raise ContactNotGranted()

        # Log the successful access
        AuditLog.objects.create(
            actor_id=actor_id,
            action='contact_access_granted',
            target_type='CandidateContact',
            target_id=str(candidate_id),
            meta={
                'company_id': str(company_id),
                'grant_id': str(grant.id),
            },
        )

        try:
            contacts = CandidateContact.objects.get(user_id=candidate_id)
        except CandidateContact.DoesNotExist:
            return ContactInfo(full_name='', email='', phone='', telegram='')

        # Get full name from profile
        from profiles.models import CandidateProfile
        try:
            profile = CandidateProfile.objects.get(user_id=candidate_id)
            full_name = profile.full_name
        except CandidateProfile.DoesNotExist:
            full_name = ''

        return ContactInfo(
            full_name=full_name,
            email=contacts.email,
            phone=contacts.phone,
            telegram=contacts.telegram,
        )

    @staticmethod
    def has_active_grant(
        company_id: uuid.UUID,
        candidate_id: uuid.UUID,
    ) -> bool:
        """Check if an active contact grant exists without logging."""
        return ContactGrant.objects.filter(
            company_id=company_id,
            candidate_id=candidate_id,
            revoked_at__isnull=True,
        ).exists()

    @staticmethod
    def create_grant(
        candidate_id: uuid.UUID,
        company_id: uuid.UUID,
        source: str,
        source_id: uuid.UUID,
    ) -> ContactGrant:
        """Create a new contact grant (called when an offer is accepted)."""
        grant, created = ContactGrant.objects.get_or_create(
            source=source,
            source_id=source_id,
            defaults={
                'candidate_id': candidate_id,
                'company_id': company_id,
            },
        )
        if created:
            AuditLog.objects.create(
                actor_id=candidate_id,
                action='contact_grant_created',
                target_type='ContactGrant',
                target_id=str(grant.id),
                meta={
                    'company_id': str(company_id),
                    'source': source,
                    'source_id': str(source_id),
                },
            )
        return grant

    @staticmethod
    def revoke_grant(
        grant_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        """Revoke a contact grant (candidate-initiated)."""
        grant = ContactGrant.objects.filter(
            id=grant_id,
            revoked_at__isnull=True,
        ).first()
        if grant:
            grant.revoked_at = timezone.now()
            grant.save(update_fields=['revoked_at'])
            AuditLog.objects.create(
                actor_id=actor_id,
                action='contact_grant_revoked',
                target_type='ContactGrant',
                target_id=str(grant_id),
                meta={'company_id': str(grant.company_id)},
            )
