"""Matching app models: Company, Position, Shortlist."""

import uuid

from core.enums import Grade, PositionStatus, SalaryType, Specialization, TrustLevel, WorkFormat
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from pgvector.django import HnswIndex, VectorField


class Company(models.Model):
    """Employer company profile.

    Trust levels are determined by domain verification and other checks.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    inn = models.CharField(
        max_length=12,
        blank=True,
        default="",
        help_text="Russian INN (tax ID)",
    )
    website = models.URLField(blank=True, default="")
    email_domain = models.CharField(max_length=255, blank=True, default="")
    business_domain = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")
    trust_level = models.CharField(
        max_length=20,
        choices=TrustLevel.choices,
        default=TrustLevel.NONE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "companies"
        verbose_name_plural = "companies"

    def __str__(self) -> str:
        return self.name


class CompanyMember(models.Model):
    """Links users to companies (employer role)."""

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="members",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company_memberships",
    )

    class Meta:
        db_table = "company_members"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                name="uq_company_member_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.company_id}"


class Position(models.Model):
    """A hiring need (private) or published vacancy.

    INVARIANT: salary_min > 0 AND salary_max >= salary_min, enforced
    by a DB CHECK constraint. salary_type (gross/net) is mandatory.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="positions",
    )
    title = models.CharField(max_length=255)
    specialization = models.CharField(max_length=20, choices=Specialization.choices)
    grades = ArrayField(
        models.CharField(max_length=20, choices=Grade.choices),
        help_text="Acceptable grades for this position",
    )
    must_skills = ArrayField(
        models.CharField(max_length=100),
        default=list,
        blank=True,
        help_text="Required skills (weight=2 in matching)",
    )
    nice_skills = ArrayField(
        models.CharField(max_length=100),
        default=list,
        blank=True,
        help_text="Nice-to-have skills (weight=1 in matching)",
    )
    work_formats = ArrayField(
        models.CharField(max_length=20, choices=WorkFormat.choices),
        default=list,
        blank=True,
    )
    location = models.CharField(max_length=255, blank=True, default="")

    # Salary range (RUB/month) — MANDATORY with CHECK constraint
    salary_min = models.PositiveIntegerField(
        help_text="Minimum salary in RUB/month. Must be > 0.",
    )
    salary_max = models.PositiveIntegerField(
        help_text="Maximum salary in RUB/month. Must be >= salary_min.",
    )
    salary_type = models.CharField(
        max_length=10,
        choices=SalaryType.choices,
        help_text="Gross or net — mandatory for salary transparency",
    )

    team_context = models.TextField(blank=True, default="")
    description = models.TextField(blank=True, default="")
    allow_adjacent = models.BooleanField(
        default=False,
        help_text="Allow candidates from adjacent grades",
    )
    weights = models.JSONField(
        default=dict,
        blank=True,
        help_text="Custom matching weight overrides",
    )
    is_public = models.BooleanField(
        default=False,
        help_text="True = published vacancy, False = private hiring need",
    )
    status = models.CharField(
        max_length=20,
        choices=PositionStatus.choices,
        default=PositionStatus.OPEN,
    )
    embedding = VectorField(
        dimensions=1024,
        null=True,
        blank=True,
        help_text="1024-dim dense embedding (USER-bge-m3) for semantic matching",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "positions"
        indexes = [
            HnswIndex(
                name="position_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(salary_min__gt=0),
                name="chk_position_salary_min_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(salary_max__gte=models.F("salary_min")),
                name="chk_position_salary_max_gte_min",
            ),
            models.CheckConstraint(
                condition=models.Q(salary_type__in=["gross", "net"]),
                name="chk_position_salary_type_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} @ {self.company}"


class Shortlist(models.Model):
    """An employer's shortlisted candidate for a position.

    Shortlists survive filter changes — they're explicit selections.
    """

    position = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="shortlisted",
    )
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shortlisted_in",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shortlists"
        constraints = [
            models.UniqueConstraint(
                fields=["position", "candidate"],
                name="uq_shortlist_position_candidate",
            ),
        ]

    def __str__(self) -> str:
        return f"Shortlist: {self.candidate_id} for {self.position_id}"
