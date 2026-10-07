"""Identity app models: User, Identity, Consent, AuditLog."""
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.postgres.fields import ArrayField
from django.db import models

from core.enums import UserRole, ConsentType, IdentityProvider


class UserManager(BaseUserManager):
    """Custom user manager that uses email as the unique identifier."""

    def create_user(
        self,
        email: str,
        password: str | None = None,
        role: str = UserRole.CANDIDATE,
        **extra_fields,
    ):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, role=role, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', UserRole.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom User model using email as the unique identifier.

    Supports demo mode with per-user clock offset for time-travel testing.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.CANDIDATE,
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)
    is_demo = models.BooleanField(default=False)
    clock_offset_days = models.IntegerField(
        default=0,
        help_text='Time offset in days for demo time-travel. Non-zero only in DEMO_MODE.',
    )
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'users'

    def __str__(self) -> str:
        return f'{self.email} ({self.role})'

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None


class Identity(models.Model):
    """External identity provider link (local or FSP ID).

    Ensures one-to-one mapping for FSP ID: each `subject` is unique
    per provider, preventing duplicate FSP ID links.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='identities',
    )
    provider = models.CharField(
        max_length=20,
        choices=IdentityProvider.choices,
    )
    subject = models.CharField(
        max_length=255,
        help_text='External subject ID (email for local, participant_id for FSP)',
    )

    class Meta:
        db_table = 'identities'
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'subject'],
                name='uq_identity_provider_subject',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.provider}:{self.subject}'


class Consent(models.Model):
    """Versioned, append-only consent records for 152-FZ compliance.

    The latest consent row for each (user, type) pair determines
    whether consent is currently granted.
    """

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='consents',
    )
    type = models.CharField(max_length=20, choices=ConsentType.choices)
    granted = models.BooleanField()
    version = models.CharField(max_length=20, help_text='Consent document version')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'consents'
        ordering = ['-created_at']

    def __str__(self) -> str:
        status = 'granted' if self.granted else 'revoked'
        return f'{self.user_id} {self.type} {status} v{self.version}'


class AuditLog(models.Model):
    """Immutable audit trail for security-sensitive actions.

    Every contact access, consent change, and offer state transition
    is recorded here for compliance and forensics.
    """

    id = models.BigAutoField(primary_key=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='+',
    )
    action = models.CharField(max_length=100, db_index=True)
    target_type = models.CharField(max_length=100, blank=True, default='')
    target_id = models.CharField(max_length=255, blank=True, default='')
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'audit_log'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.action} by {self.actor_id} at {self.created_at}'
