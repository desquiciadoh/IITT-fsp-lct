"""Tests for R3: admin leak prevention and read-only admins."""

from assessment.models import AssessmentItem, AssessmentSession, LeagueMembership
from django.contrib import admin
from django.test import RequestFactory, SimpleTestCase
from identity.models import AuditLog
from outreach.models import ContactGrant, OfferEvent
from profiles.models import CandidateContact


class MockUser:
    is_active = True
    is_staff = True
    is_superuser = True

    def has_perm(self, perm):
        return True


class AdminSecurityTestCase(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get("/admin/")
        self.request.user = MockUser()

    def test_candidate_contact_not_registered(self):
        assert CandidateContact not in admin.site._registry

    def test_assessment_item_admin_excludes_secrets_and_is_not_editable(self):
        model_admin = admin.site._registry[AssessmentItem]
        exclude = model_admin.exclude or ()
        for secret_field in ("key", "fingerprint", "seed"):
            assert secret_field in exclude
            assert secret_field not in (model_admin.readonly_fields or ())

        assert model_admin.has_add_permission(self.request) is False
        assert model_admin.has_change_permission(self.request) is False

    def test_read_only_admins(self):
        read_only_models = [
            AssessmentSession,
            LeagueMembership,
            AuditLog,
            OfferEvent,
            ContactGrant,
        ]
        for model in read_only_models:
            model_admin = admin.site._registry[model]
            assert model_admin.has_add_permission(self.request) is False, f"{model} allows add"
            assert model_admin.has_change_permission(self.request) is False, (
                f"{model} allows change"
            )
