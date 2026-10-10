"""Tests for R2: secrets configuration and system checks."""

import inspect

from core.checks import check_demo_mode_security
from django.core.checks import Warning as CheckWarning
from django.test import SimpleTestCase, override_settings


class SystemChecksTestCase(SimpleTestCase):
    @override_settings(DEMO_MODE=True, DEBUG=False)
    def test_demo_mode_and_not_debug_warns(self):
        warnings = check_demo_mode_security(None)
        assert len(warnings) == 1
        assert isinstance(warnings[0], CheckWarning)
        assert warnings[0].id == "fsp.W001"
        assert "DEMO_MODE" in warnings[0].msg

    @override_settings(DEMO_MODE=False, DEBUG=False)
    def test_no_demo_mode_no_warning(self):
        warnings = check_demo_mode_security(None)
        assert len(warnings) == 0

    @override_settings(DEMO_MODE=True, DEBUG=True)
    def test_demo_mode_with_debug_no_warning(self):
        warnings = check_demo_mode_security(None)
        assert len(warnings) == 0


class SecretsConfigurationTestCase(SimpleTestCase):
    def test_assessment_services_uses_settings_item_seed_secret(self):
        from assessment import services

        source = inspect.getsource(services.AssessmentService.start_assessment)
        # Fallback string 'item-seed-secret-dev' should not be present in start_assessment
        assert "getattr(settings, 'ITEM_SEED_SECRET', 'item-seed-secret-dev')" not in source
        assert "settings.ITEM_SEED_SECRET" in source
