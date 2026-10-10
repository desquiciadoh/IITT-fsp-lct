"""Assessment app models: ItemFamily, AssessmentSession, AssessmentItem, LeagueMembership."""

import uuid

from core.enums import (
    AssessmentKind,
    AssessmentMode,
    AssessmentStatus,
    Grade,
    GradeDecision,
    ItemFamilyStatus,
    ItemFormat,
    LeagueStatus,
    Specialization,
)
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models


class ItemFamily(models.Model):
    """Parametric question family for leak-proof assessment.

    Each family is a template with a generator and oracle. Instances are
    created with unique seeds, so every candidate sees different questions
    but difficulty is calibrated via IRT parameters (a, b, c).

    INVARIANT: The answer key is NEVER serialized to the client.
    """

    id = models.CharField(primary_key=True, max_length=100)
    version = models.IntegerField(default=1)
    specs = ArrayField(
        models.CharField(max_length=20, choices=Specialization.choices),
        help_text="Which specializations this family applies to",
    )
    topic = models.CharField(max_length=100)
    skills = ArrayField(
        models.CharField(max_length=100),
        default=list,
        blank=True,
    )
    format = models.CharField(max_length=30, choices=ItemFormat.choices)

    # IRT parameters (3PL model)
    a = models.FloatField(help_text="Discrimination parameter")
    b = models.FloatField(help_text="Difficulty parameter")
    c = models.FloatField(
        default=0.25,
        help_text="Guessing parameter (1/num_options for MCQ, 0 for typed)",
    )
    time_limit_s = models.IntegerField(default=120)

    status = models.CharField(
        max_length=20,
        choices=ItemFamilyStatus.choices,
        default=ItemFamilyStatus.ACTIVE,
    )
    exposures = models.IntegerField(
        default=0,
        help_text="Number of times served to candidates",
    )

    class Meta:
        db_table = "item_families"

    def __str__(self) -> str:
        return f"{self.id} (a={self.a}, b={self.b})"


class AssessmentSession(models.Model):
    """An adaptive test session for a candidate.

    Tracks the CAT engine state (θ estimate, items served, etc.) in
    a JSONB `state` field. Grade decisions are deterministic — no LLM
    involvement in the grading path.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assessments",
    )
    specialization = models.CharField(max_length=20, choices=Specialization.choices)
    claimed_grade = models.CharField(max_length=20, choices=Grade.choices)
    kind = models.CharField(
        max_length=20,
        choices=AssessmentKind.choices,
        default=AssessmentKind.INITIAL,
    )
    mode = models.CharField(
        max_length=20,
        choices=AssessmentMode.choices,
        default=AssessmentMode.FULL,
    )
    status = models.CharField(
        max_length=20,
        choices=AssessmentStatus.choices,
        default=AssessmentStatus.IN_PROGRESS,
    )

    # CAT engine state (serialized CatState)
    state = models.JSONField(
        default=dict,
        blank=True,
        help_text="Serialized CAT engine state for session resumption",
    )

    # Results (populated on finish)
    theta = models.FloatField(
        null=True,
        blank=True,
        help_text="θ estimate (EAP) on the IRT scale",
    )
    se = models.FloatField(
        null=True,
        blank=True,
        help_text="Standard error of θ",
    )
    rating = models.IntegerField(
        null=True,
        blank=True,
        help_text="Sport-style rating: 1000 + 200θ",
    )
    result_grade = models.CharField(
        max_length=20,
        choices=Grade.choices,
        blank=True,
        default="",
    )
    decision = models.CharField(
        max_length=20,
        choices=GradeDecision.choices,
        blank=True,
        default="",
    )
    promotion_unlocked = models.BooleanField(default=False)
    counts_as_attempt = models.BooleanField(
        default=True,
        help_text="False for fallback tests — failing does not burn a retake",
    )

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "assessments"
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "specialization"],
                condition=models.Q(status=AssessmentStatus.IN_PROGRESS),
                name="uq_one_in_progress_assessment_per_spec",
            ),
        ]
        indexes = [
            models.Index(
                fields=["candidate", "-started_at"],
                name="idx_assessments_candidate_date",
            ),
        ]

    @property
    def public_id(self) -> str:
        """Public identifier for employer-facing payloads (A-XXXXXXXX)."""
        return f"A-{self.id.hex[:8].upper()}"

    def __str__(self) -> str:
        return f"Assessment {self.id} ({self.specialization}/{self.claimed_grade})"


class AssessmentItem(models.Model):
    """A single item served during an assessment session.

    INVARIANT: The `key` field contains the correct answer and MUST NEVER
    be included in any API response. It is used only by the server-side
    grading logic. Tests verify this invariant (see tests/test_assessment_security.py).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.ForeignKey(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name="items",
    )
    seq = models.IntegerField(help_text="Item sequence number within the assessment")
    family = models.ForeignKey(
        ItemFamily,
        on_delete=models.PROTECT,
        related_name="assessment_items",
    )
    seed = models.CharField(
        max_length=64,
        help_text="HMAC-derived seed for reproducible instance generation",
    )

    # The rendered question (sent to the client)
    view = models.JSONField(
        help_text="Rendered item view (stem, code, options) — safe for client",
    )
    # The correct answer (NEVER sent to the client)
    key = models.JSONField(
        help_text="Correct answer — server-side only, NEVER serialized to API",
    )
    fingerprint = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Hash of drawn parameters for collision detection",
    )

    # Candidate response
    answer = models.JSONField(null=True, blank=True)
    correct = models.BooleanField(null=True, blank=True)
    integrity = models.JSONField(
        null=True,
        blank=True,
        help_text="Integrity signals: focus_loss, paste counts",
    )

    served_at = models.DateTimeField(auto_now_add=True)
    deadline_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Item-level deadline; set when the item becomes current, NULL until served",
    )
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "assessment_items"
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "seq"],
                name="uq_assessment_item_seq",
            ),
        ]

    def __str__(self) -> str:
        return f"Item {self.seq} of {self.assessment_id}"


class LeagueMembership(models.Model):
    """A candidate's membership in a specialization×grade League.

    Profile Strength and percentile are computed deterministically from
    θ, FSP achievements, and activity — never by an LLM.

    INVARIANT: Grade is set ONLY by the assessment engine. FSP achievements
    affect `strength` (ranking within the League) but NEVER change `grade`.
    """

    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="league_memberships",
    )
    specialization = models.CharField(max_length=20, choices=Specialization.choices)
    grade = models.CharField(max_length=20, choices=Grade.choices)
    status = models.CharField(
        max_length=20,
        choices=LeagueStatus.choices,
        default=LeagueStatus.PENDING,
    )

    theta = models.FloatField(null=True, blank=True)
    se = models.FloatField(null=True, blank=True)
    rating = models.IntegerField(null=True, blank=True)
    percentile = models.FloatField(null=True, blank=True)
    strength = models.FloatField(
        default=0.0,
        help_text="Profile Strength 0-100 for ranking within the League",
    )
    base_strength = models.FloatField(
        default=0.0,
        help_text="Base strength computed from IRT theta (0-100)",
    )
    fsp_boost = models.FloatField(
        default=0.0,
        help_text="Current FSP boost applied to strength (0-15)",
    )

    confirmed_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Cooldown: earliest retake allowed",
    )
    next_promotion_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Cooldown: earliest promotion attempt allowed",
    )

    class Meta:
        db_table = "league_memberships"
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "specialization"],
                name="uq_league_candidate_spec",
            ),
        ]
        indexes = [
            models.Index(
                fields=["specialization", "grade", "status"],
                name="idx_league_spec_grade_status",
            ),
        ]
        ordering = [
            models.OrderBy(models.F("confirmed_at"), descending=True, nulls_last=True),
            "-id",
        ]

    def __str__(self) -> str:
        return f"{self.candidate_id}: {self.specialization}/{self.grade} ({self.status})"
