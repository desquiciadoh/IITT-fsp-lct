"""FSP Sync app models: FSPLink, FSPResult.

Stores verified sports programming achievements from the FSP registry.
These affect ranking (Profile Strength) but NEVER determine grades.
"""
import uuid

from core.enums import Discipline, PlacementTier, SportsRank, SyncStatus
from django.conf import settings
from django.db import models


class FSPLink(models.Model):
    """Link between a candidate and their FSP participant ID.

    INVARIANT: Each participant_id maps to exactly one candidate (unique).
    Attempting to link an already-linked FSP ID returns 409 fsp_id_already_linked.
    """

    candidate = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='fsp_link',
    )
    participant_id = models.CharField(
        max_length=50,
        unique=True,
        help_text='FSP participant ID (e.g., FSP-000123)',
    )
    sports_rank = models.CharField(
        max_length=10,
        choices=SportsRank.choices,
        blank=True,
        default='',
    )
    rank_awarded_at = models.DateField(null=True, blank=True)

    sync_status = models.CharField(
        max_length=20,
        choices=SyncStatus.choices,
        default=SyncStatus.PENDING,
    )
    last_sync_at = models.DateTimeField(null=True, blank=True)
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fsp_links'

    def __str__(self) -> str:
        return f'{self.participant_id} ({self.sync_status})'


class FSPResult(models.Model):
    """A verified competition result from the FSP registry.

    Results are synced from the mock FSP registry and stored with
    a source_hash for integrity verification. They contribute to
    Profile Strength but NEVER change a candidate's grade.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='fsp_results',
    )
    event_id = models.CharField(max_length=100)
    event_name = models.CharField(max_length=255)
    discipline = models.CharField(max_length=20, choices=Discipline.choices)
    date = models.DateField()
    stage = models.CharField(max_length=50, blank=True, default='')
    format = models.CharField(
        max_length=20,
        choices=[('individual', 'Individual'), ('team', 'Team')],
        default='individual',
    )
    team_size = models.IntegerField(null=True, blank=True)
    placement = models.IntegerField()
    tier = models.CharField(max_length=20, choices=PlacementTier.choices)
    participants_total = models.IntegerField()
    source_hash = models.CharField(
        max_length=64,
        blank=True,
        default='',
        help_text='SHA-256 hash of source data for integrity verification',
    )

    class Meta:
        db_table = 'fsp_results'
        constraints = [
            models.UniqueConstraint(
                fields=['candidate', 'event_id'],
                name='uq_fsp_result_candidate_event',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.event_name}: #{self.placement} ({self.tier})'
