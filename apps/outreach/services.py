"""Outreach service: Offer state machine with optimistic locking."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.errors import InvalidTransition, VersionConflict, CandidateNotReachable
from core.services import ContactAccessService
from identity.models import AuditLog
from outreach.models import ContactGrant, Offer, OfferEvent, OFFER_TRANSITIONS
from core.enums import ContactGrantSource, OfferStatus

if TYPE_CHECKING:
    import uuid

logger = logging.getLogger(__name__)


class OfferService:
    """Manages the offer lifecycle with state machine and optimistic locking.

    Key invariants:
    1. Status changes only through valid transitions
    2. Optimistic locking via version field — concurrent updates get 409
    3. ContactGrant auto-created on acceptance
    4. All transitions logged as OfferEvents and AuditLog entries
    """

    @staticmethod
    @transaction.atomic
    def transition(
        offer_id: uuid.UUID,
        new_status: str,
        expected_version: int,
        actor_id: uuid.UUID,
        decline_reason: str = '',
        decline_comment: str = '',
    ) -> Offer:
        """Transition an offer to a new status with optimistic locking.

        Args:
            offer_id: The offer UUID
            new_status: Target status
            expected_version: Client's last known version (for conflict detection)
            actor_id: The user performing the action
            decline_reason: Required when declining
            decline_comment: Optional comment when declining

        Returns:
            The updated Offer

        Raises:
            VersionConflict: If the version doesn't match (409)
            InvalidTransition: If the state machine doesn't allow this transition
        """
        offer = Offer.objects.select_for_update().filter(id=offer_id).first()
        if offer is None:
            from django.http import Http404
            raise Http404('Offer not found')

        if offer.version != expected_version:
            raise VersionConflict()

        if not offer.can_transition_to(new_status):
            raise InvalidTransition(offer.status, new_status)

        from_status = offer.status
        offer.status = new_status
        offer.version = F('version') + 1
        offer.updated_at = timezone.now()
        if new_status == OfferStatus.DECLINED:
            offer.decline_reason = decline_reason
            offer.decline_comment = decline_comment
        offer.save()
        offer.refresh_from_db()

        # Record the event
        OfferEvent.objects.create(
            offer=offer,
            from_status=from_status if isinstance(from_status, str) else offer.status,
            to_status=new_status,
            actor_id=actor_id,
        )

        # Auto-create ContactGrant on acceptance
        if new_status == OfferStatus.ACCEPTED:
            ContactAccessService.create_grant(
                candidate_id=offer.candidate_id,
                company_id=offer.company_id,
                source=ContactGrantSource.OFFER,
                source_id=offer.id,
            )

        # Audit log
        AuditLog.objects.create(
            actor_id=actor_id,
            action=f'offer_{new_status}',
            target_type='Offer',
            target_id=str(offer_id),
            meta={
                'new_status': new_status,
                'version': offer.version,
            },
        )

        return offer

    @staticmethod
    @transaction.atomic
    def create_offer(
        company_id: uuid.UUID,
        candidate_id: uuid.UUID,
        created_by_id: uuid.UUID,
        title: str,
        description: str,
        salary_min: int,
        salary_max: int,
        salary_type: str,
        contact_channel: str,
        contact_value: str,
        position_id: uuid.UUID | None = None,
        why_you: list | None = None,
        match_snapshot: dict | None = None,
        expires_in_days: int = 14,
    ) -> Offer:
        """Create a new Draft Offer."""
        from profiles.models import CandidateProfile
        from identity.models import Consent

        # Verify candidate is reachable
        try:
            profile = CandidateProfile.objects.get(user_id=candidate_id)
        except CandidateProfile.DoesNotExist:
            raise CandidateNotReachable()

        if not profile.open_to_offers:
            raise CandidateNotReachable()

        # Check publication consent
        latest_consent = Consent.objects.filter(
            user_id=candidate_id,
            type='publication',
        ).order_by('-created_at').first()

        if not latest_consent or not latest_consent.granted:
            raise CandidateNotReachable()

        # Check company blocklist
        if company_id in (profile.blocked_company_ids or []):
            raise CandidateNotReachable()

        offer = Offer.objects.create(
            company_id=company_id,
            position_id=position_id,
            candidate_id=candidate_id,
            created_by_id=created_by_id,
            title=title,
            description=description,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_type=salary_type,
            contact_channel=contact_channel,
            contact_value=contact_value,
            why_you=why_you or [],
            match_snapshot=match_snapshot or {},
        )

        OfferEvent.objects.create(
            offer=offer,
            from_status='',
            to_status=OfferStatus.SENT,
            actor_id=created_by_id,
        )

        return offer
