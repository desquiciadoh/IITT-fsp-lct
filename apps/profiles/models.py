"""Profiles app models: CandidateProfile, CandidateContact, Skill, CandidateSkill."""

import uuid

from core.enums import (
    EvidenceSource,
    Grade,
    SalaryType,
    Specialization,
    WorkFormat,
)
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models


def generate_public_id(max_retries: int = 10) -> str:
    """Generate a public ID in the format C-XXXXXXXX (8 hex uppercase chars).

    Retries on collision if the database table is available.
    """
    for _ in range(max_retries):
        pid = f"C-{uuid.uuid4().hex[:8].upper()}"
        try:
            if not CandidateProfile.objects.filter(public_id=pid).exists():
                return pid
        except Exception:
            return pid
    return f"C-{uuid.uuid4().hex[:8].upper()}"


class CandidateProfile(models.Model):
    """Public-facing candidate profile.

    Employers see candidates only by `public_id` (e.g. C-7F3A2B),
    never by the internal user PK.

    INVARIANT: Contacts are in a separate table and are NEVER included
    in employer-facing serializers. Access is gated by ContactGrant.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="candidate_profile",
    )
    public_id = models.CharField(
        max_length=10,
        unique=True,
        default=generate_public_id,
        db_index=True,
    )
    full_name = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    timezone = models.CharField(max_length=50, blank=True, default="")

    specialization = models.CharField(
        max_length=20,
        choices=Specialization.choices,
        blank=True,
        default="",
    )
    claimed_grade = models.CharField(
        max_length=20,
        choices=Grade.choices,
        blank=True,
        default="",
    )
    years_experience = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )
    roles = ArrayField(
        models.CharField(max_length=100),
        default=list,
        blank=True,
    )
    work_formats = ArrayField(
        models.CharField(max_length=20, choices=WorkFormat.choices),
        default=list,
        blank=True,
    )

    # Salary expectations (RUB/month)
    salary_min = models.PositiveIntegerField(null=True, blank=True)
    salary_max = models.PositiveIntegerField(null=True, blank=True)
    salary_type = models.CharField(
        max_length=10,
        choices=SalaryType.choices,
        blank=True,
        default="",
    )
    salary_floor = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Private minimum salary; offers below trigger a warning",
    )

    # Visibility controls
    open_to_offers = models.BooleanField(default=True)
    blind_mode = models.BooleanField(
        default=False,
        help_text="Hide name and photo until offer acceptance",
    )
    blocked_company_ids = ArrayField(
        models.UUIDField(),
        default=list,
        blank=True,
        help_text="Companies hidden from seeing this profile",
    )

    about = models.TextField(blank=True, default="")
    experience_text = models.TextField(blank=True, default="")
    completeness = models.SmallIntegerField(default=0, help_text="Profile completeness 0-100")

    last_active_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "candidate_profiles"

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = generate_public_id()
        elif (
            self._state.adding
            and CandidateProfile.objects.filter(public_id=self.public_id).exists()
        ):
            self.public_id = generate_public_id()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.public_id} ({self.full_name})"


class CandidateContact(models.Model):
    """Candidate contact details — stored separately for gating.

    INVARIANT: This table is NEVER queried directly by employer-facing views.
    Access is only through the ContactAccess service, which requires an
    active ContactGrant and logs every access to AuditLog.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="candidate_contacts",
    )
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    telegram = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        db_table = "candidate_contacts"

    def __str__(self) -> str:
        return f"Contacts for {self.user_id}"


class Skill(models.Model):
    """Normalized skill from the taxonomy.

    Synced from content/skills.yaml. Provides aliases for fuzzy matching
    and topic grouping for assessment blueprints.
    """

    id = models.CharField(primary_key=True, max_length=100)
    name = models.CharField(max_length=200)
    aliases = ArrayField(
        models.CharField(max_length=200),
        default=list,
        blank=True,
    )
    topic = models.CharField(max_length=100, blank=True, default="")
    related = ArrayField(
        models.CharField(max_length=100),
        default=list,
        blank=True,
    )

    class Meta:
        db_table = "skills"

    def __str__(self) -> str:
        return self.name


class CandidateSkill(models.Model):
    """A skill linked to a candidate with evidence source and level.

    The same skill can appear multiple times with different sources
    (e.g., declared + verified by test).
    """

    candidate = models.ForeignKey(
        CandidateProfile,
        on_delete=models.CASCADE,
        related_name="skills",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="candidate_skills",
    )
    source = models.CharField(
        max_length=20,
        choices=EvidenceSource.choices,
    )
    level = models.FloatField(
        default=0.0,
        help_text="Skill level 0.0-1.0",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "candidate_skills"
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "skill", "source"],
                name="uq_candidate_skill_source",
            ),
        ]
        indexes = [
            models.Index(fields=["skill"], name="idx_candidate_skills_skill"),
        ]

    def __str__(self) -> str:
        return f"{self.candidate_id} / {self.skill_id} ({self.source})"
