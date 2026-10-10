"""Tests for immutability invariants: AuditLog and OfferEvent cannot be updated or deleted."""

import pytest
from core.enums import OfferStatus, SalaryType, UserRole
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from identity.models import AuditLog
from matching.models import Company
from outreach.models import Offer, OfferEvent

User = get_user_model()


@pytest.mark.django_db
class TestAuditLogImmutability:
    def test_audit_log_cannot_be_updated(self):
        user = User.objects.create_user(email="audit_user@example.com", password="pwd")
        log = AuditLog.objects.create(
            actor=user,
            action="test_action",
            target_type="test",
            target_id="123",
            meta={"key": "val"},
        )

        log.action = "modified_action"
        with pytest.raises(PermissionDenied, match="immutable and cannot be updated"):
            log.save()

    def test_audit_log_cannot_be_deleted(self):
        user = User.objects.create_user(email="audit_user_del@example.com", password="pwd")
        log = AuditLog.objects.create(
            actor=user,
            action="test_action",
            target_type="test",
            target_id="123",
        )

        with pytest.raises(PermissionDenied, match="immutable and cannot be deleted"):
            log.delete()

    def test_audit_log_queryset_cannot_be_updated_or_deleted(self):
        user = User.objects.create_user(email="audit_qs@example.com", password="pwd")
        AuditLog.objects.create(actor=user, action="action_qs", target_type="t", target_id="1")

        with pytest.raises(PermissionDenied, match="immutable and cannot be updated"):
            AuditLog.objects.filter(actor=user).update(action="hacked")

        with pytest.raises(PermissionDenied, match="immutable and cannot be deleted"):
            AuditLog.objects.filter(actor=user).delete()


@pytest.mark.django_db
class TestOfferEventImmutability:
    def test_offer_event_cannot_be_updated(self):
        employer = User.objects.create_user(
            email="emp_event@example.com", password="pwd", role=UserRole.EMPLOYER
        )
        candidate = User.objects.create_user(
            email="cand_event@example.com", password="pwd", role=UserRole.CANDIDATE
        )
        company = Company.objects.create(name="Event Corp", contact_email="event@corp.com")
        offer = Offer.objects.create(
            candidate=candidate,
            company=company,
            created_by=employer,
            title="Dev",
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.GROSS,
        )
        event = OfferEvent.objects.create(
            offer=offer,
            from_status=OfferStatus.SENT,
            to_status=OfferStatus.VIEWED,
            actor=candidate,
        )

        event.to_status = OfferStatus.ACCEPTED
        with pytest.raises(PermissionDenied, match="immutable and cannot be updated"):
            event.save()

    def test_offer_event_cannot_be_deleted(self):
        employer = User.objects.create_user(
            email="emp_del@example.com", password="pwd", role=UserRole.EMPLOYER
        )
        candidate = User.objects.create_user(
            email="cand_del@example.com", password="pwd", role=UserRole.CANDIDATE
        )
        company = Company.objects.create(name="Del Corp", contact_email="del@corp.com")
        offer = Offer.objects.create(
            candidate=candidate,
            company=company,
            created_by=employer,
            title="Dev",
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.GROSS,
        )
        event = OfferEvent.objects.create(
            offer=offer,
            from_status=OfferStatus.SENT,
            to_status=OfferStatus.VIEWED,
            actor=candidate,
        )

        with pytest.raises(PermissionDenied, match="immutable and cannot be deleted"):
            event.delete()

    def test_offer_event_queryset_cannot_be_updated_or_deleted(self):
        employer = User.objects.create_user(
            email="emp_qs@example.com", password="pwd", role=UserRole.EMPLOYER
        )
        candidate = User.objects.create_user(
            email="cand_qs@example.com", password="pwd", role=UserRole.CANDIDATE
        )
        company = Company.objects.create(name="QS Corp", contact_email="qs@corp.com")
        offer = Offer.objects.create(
            candidate=candidate,
            company=company,
            created_by=employer,
            title="Dev",
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.GROSS,
        )
        OfferEvent.objects.create(
            offer=offer,
            from_status=OfferStatus.SENT,
            to_status=OfferStatus.VIEWED,
            actor=candidate,
        )

        with pytest.raises(PermissionDenied, match="immutable and cannot be updated"):
            OfferEvent.objects.filter(offer=offer).update(to_status=OfferStatus.ACCEPTED)

        with pytest.raises(PermissionDenied, match="immutable and cannot be deleted"):
            OfferEvent.objects.filter(offer=offer).delete()
