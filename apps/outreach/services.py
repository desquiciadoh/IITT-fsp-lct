"""Outreach service: Offer state machine with optimistic locking."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from core.enums import ContactGrantSource, OfferStatus
from core.errors import (
    CandidateNotReachable,
    ContactNotGranted,
    InvalidTransition,
    OfferExpired,
    VersionConflict,
)
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from identity.models import AuditLog
from profiles.models import CandidateContact

from outreach.events import publish_domain_event
from outreach.models import ContactGrant, Offer, OfferEvent

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


class OfferService:
    """Manages the offer lifecycle with state machine and optimistic locking.

    Key invariants:
    1. Status changes only through valid transitions
    2. Optimistic locking via version field — concurrent updates get 409
    3. ContactGrant auto-created on acceptance
    4. All transitions logged as OfferEvents and AuditLog entries
    """

    @staticmethod
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
            OfferExpired: If the offer was past expires_at; the expiry is persisted first (409)
            InvalidTransition: If the state machine doesn't allow this transition
        """
        # The expiry must commit (or be released into the caller's transaction)
        # before OfferExpired propagates, so it is raised outside this block.
        with transaction.atomic():
            offer = Offer.objects.select_for_update().filter(id=offer_id).first()
            if offer is None:
                from django.http import Http404
                raise Http404('Offer not found')

            if offer.version != expected_version:
                raise VersionConflict()

            now = timezone.now()
            expired = (
                offer.expires_at is not None
                and now > offer.expires_at
                and offer.can_transition_to(OfferStatus.EXPIRED)
            )
            if not expired:
                return OfferService._apply_transition(
                    offer, new_status, actor_id, decline_reason, decline_comment,
                )
            OfferService._expire_locked(offer, actor_id, now)
        raise OfferExpired()

    @staticmethod
    def _expire_locked(offer: Offer, actor_id: uuid.UUID | None, now) -> None:
        """Mark a locked sent/viewed offer EXPIRED with event, audit and domain event."""
        from_status = offer.status
        offer.status = OfferStatus.EXPIRED
        offer.version = F('version') + 1
        offer.updated_at = now
        offer.save()
        offer.refresh_from_db()
        OfferEvent.objects.create(
            offer=offer,
            from_status=from_status,
            to_status=OfferStatus.EXPIRED,
            actor_id=actor_id,
        )
        AuditLog.objects.create(
            actor_id=actor_id,
            action='offer_expired',
            target_type='Offer',
            target_id=str(offer.id),
            meta={
                'new_status': OfferStatus.EXPIRED,
                'version': offer.version,
                'lazy': True,
            },
        )
        publish_domain_event('offer.updated', {
            'offer_id': str(offer.id),
            'status': OfferStatus.EXPIRED,
            'candidate_id': str(offer.candidate_id),
            'company_id': str(offer.company_id),
            'version': offer.version,
        })

    @staticmethod
    def _apply_transition(
        offer: Offer,
        new_status: str,
        actor_id: uuid.UUID,
        decline_reason: str,
        decline_comment: str,
    ) -> Offer:
        """Apply a normal state-machine transition to a locked offer."""
        offer_id = offer.id
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

        publish_domain_event('offer.updated', {
            'offer_id': str(offer.id),
            'status': new_status,
            'candidate_id': str(offer.candidate_id),
            'company_id': str(offer.company_id),
            'version': offer.version,
        })

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
        from matching.models import Company, Position
        from matching.scoring import calculate_match_score
        from profiles.models import CandidateProfile
        from profiles.selectors import is_candidate_visible_to_company

        # Verify candidate exists
        try:
            profile = CandidateProfile.objects.select_related('user').get(user_id=candidate_id)
        except CandidateProfile.DoesNotExist:
            raise CandidateNotReachable()

        company = Company.objects.filter(id=company_id).first()
        if not company or not is_candidate_visible_to_company(profile, company):
            raise CandidateNotReachable()

        # Compute why_you and match_snapshot server-side from scorer, ignoring client input
        if position_id:
            pos = Position.objects.filter(id=position_id, company_id=company_id).first()
            if pos:
                score_data = calculate_match_score(profile, pos)
                why_you = score_data.get('reasons', [])
                match_snapshot = score_data.get('components', {})
            else:
                why_you = []
                match_snapshot = {}
        else:
            why_you = []
            match_snapshot = {}

        expires_at = timezone.now() + timedelta(days=expires_in_days)

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
            why_you=why_you,
            match_snapshot=match_snapshot,
            expires_at=expires_at,
        )

        OfferEvent.objects.create(
            offer=offer,
            from_status='',
            to_status=OfferStatus.SENT,
            actor_id=created_by_id,
        )

        publish_domain_event('offer.created', {
            'offer_id': str(offer.id),
            'candidate_id': str(offer.candidate_id),
            'company_id': str(offer.company_id),
            'title': offer.title,
            'status': offer.status,
        })

        return offer

    @staticmethod
    def expire_offers() -> int:
        """Find all active offers past expires_at and mark them as expired."""
        now = timezone.now()
        expired_offers = Offer.objects.filter(
            status__in=[OfferStatus.SENT, OfferStatus.VIEWED],
            expires_at__lt=now,
        )
        count = 0
        for offer in expired_offers:
            with transaction.atomic():
                offer_locked = Offer.objects.select_for_update().filter(id=offer.id).first()
                if offer_locked and offer_locked.can_transition_to(OfferStatus.EXPIRED):
                    from_status = offer_locked.status
                    offer_locked.status = OfferStatus.EXPIRED
                    offer_locked.version = F('version') + 1
                    offer_locked.updated_at = now
                    offer_locked.save()
                    offer_locked.refresh_from_db()
                    OfferEvent.objects.create(
                        offer=offer_locked,
                        from_status=from_status,
                        to_status=OfferStatus.EXPIRED,
                        actor_id=None,
                    )
                    publish_domain_event('offer.updated', {
                        'offer_id': str(offer_locked.id),
                        'status': OfferStatus.EXPIRED,
                        'candidate_id': str(offer_locked.candidate_id),
                        'company_id': str(offer_locked.company_id),
                        'version': offer_locked.version,
                    })
                    count += 1
        return count
