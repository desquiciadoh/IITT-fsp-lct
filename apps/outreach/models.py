"""Outreach app models: Offer, OfferEvent, ContactGrant.

Implements the reverse-contact protocol: employers send salary-first
Draft Offers, contacts unlock only on candidate acceptance.
"""
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.enums import (
    ContactChannel,
    ContactGrantSource,
    DeclineReason,
    OfferStatus,
    SalaryType,
)


# Valid state transitions for the offer state machine
OFFER_TRANSITIONS: dict[str, list[str]] = {
    OfferStatus.SENT: [OfferStatus.VIEWED, OfferStatus.WITHDRAWN, OfferStatus.EXPIRED],
    OfferStatus.VIEWED: [
        OfferStatus.ACCEPTED,
        OfferStatus.DECLINED,
        OfferStatus.WITHDRAWN,
        OfferStatus.EXPIRED,
    ],
    OfferStatus.ACCEPTED: [OfferStatus.INTERVIEW, OfferStatus.CLOSED],
    OfferStatus.INTERVIEW: [OfferStatus.HIRED, OfferStatus.CLOSED],
    OfferStatus.DECLINED: [],  # Terminal
    OfferStatus.EXPIRED: [],   # Terminal
    OfferStatus.WITHDRAWN: [], # Terminal
    OfferStatus.HIRED: [],     # Terminal
    OfferStatus.CLOSED: [],    # Terminal
}


class Offer(models.Model):
    """A Draft Offer from an employer to a candidate.

    INVARIANTS:
    1. salary_min > 0 AND salary_max >= salary_min (DB CHECK)
    2. Status changes only through the state machine (OFFER_TRANSITIONS)
    3. Optimistic locking via `version` field — concurrent updates get 409
    4. Contact information is NEVER included; access requires ContactGrant
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        'matching.Company',
        on_delete=models.CASCADE,
        related_name='offers',
    )
    position = models.ForeignKey(
        'matching.Position',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='offers',
    )
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_offers',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_offers',
    )

    title = models.CharField(max_length=255)
    description = models.TextField()

    # Salary (RUB/month) — MANDATORY, enforced by CHECK constraint
    salary_min = models.PositiveIntegerField()
    salary_max = models.PositiveIntegerField()
    salary_type = models.CharField(max_length=10, choices=SalaryType.choices)
    currency = models.CharField(max_length=3, default='RUB')

    contact_channel = models.CharField(max_length=20, choices=ContactChannel.choices)
    contact_value = models.CharField(max_length=255)

    status = models.CharField(
        max_length=20,
        choices=OfferStatus.choices,
        default=OfferStatus.SENT,
    )
    decline_reason = models.CharField(
        max_length=20,
        choices=DeclineReason.choices,
        blank=True,
        default='',
    )
    decline_comment = models.TextField(blank=True, default='')

    # Matching context snapshot (frozen at offer creation)
    why_you = models.JSONField(
        default=list,
        blank=True,
        help_text='Reason chips explaining why the candidate was selected',
    )
    match_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text='Frozen match score components at offer creation time',
    )

    # Optimistic locking
    version = models.IntegerField(
        default=1,
        help_text='Incremented on every status change for optimistic locking',
    )

    expires_at = models.DateTimeField(
        help_text='Auto-expire after 14 days by default',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'offers'
        indexes = [
            models.Index(
                fields=['candidate', 'status'],
                name='idx_offers_candidate_status',
            ),
            models.Index(
                fields=['company', 'status'],
                name='idx_offers_company_status',
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(salary_min__gt=0),
                name='chk_offer_salary_min_positive',
            ),
            models.CheckConstraint(
                condition=models.Q(salary_max__gte=models.F('salary_min')),
                name='chk_offer_salary_max_gte_min',
            ),
        ]

    def __str__(self) -> str:
        return f'Offer {self.id}: {self.title} ({self.status})'

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=14)
        super().save(*args, **kwargs)

    def can_transition_to(self, new_status: str) -> bool:
        """Check if the state machine allows this transition."""
        return new_status in OFFER_TRANSITIONS.get(self.status, [])


class OfferEvent(models.Model):
    """Immutable event log for offer status changes."""

    id = models.BigAutoField(primary_key=True)
    offer = models.ForeignKey(
        Offer,
        on_delete=models.CASCADE,
        related_name='events',
    )
    from_status = models.CharField(max_length=20, choices=OfferStatus.choices)
    to_status = models.CharField(max_length=20, choices=OfferStatus.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'offer_events'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.offer_id}: {self.from_status} → {self.to_status}'


class ContactGrant(models.Model):
    """Grant giving an employer access to candidate contacts.

    INVARIANT: Created ONLY when an offer transitions to `accepted`.
    Checked by ContactAccess service before any contact data is returned.
    Every access is logged to AuditLog.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='contact_grants',
    )
    company = models.ForeignKey(
        'matching.Company',
        on_delete=models.CASCADE,
        related_name='contact_grants',
    )
    source = models.CharField(max_length=20, choices=ContactGrantSource.choices)
    source_id = models.UUIDField(help_text='ID of the offer or application that created this grant')
    granted_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Set when candidate revokes contact access',
    )

    class Meta:
        db_table = 'contact_grants'
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'source_id'],
                name='uq_contact_grant_source',
            ),
        ]

    def __str__(self) -> str:
        status = 'revoked' if self.revoked_at else 'active'
        return f'Grant {self.id} ({status})'

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None
