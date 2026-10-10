"""Django system checks for FSP Draft."""

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security)
def check_demo_mode_security(app_configs, **kwargs):
    """Warn if DEMO_MODE is enabled when DEBUG is False.

    In DEMO_MODE, the mock IdP allows any user to authenticate as any FSP
    participant, which must never be enabled on a production instance.
    """
    warnings = []
    demo_mode = getattr(settings, "DEMO_MODE", False)
    debug = getattr(settings, "DEBUG", False)

    if demo_mode and not debug:
        warnings.append(
            Warning(
                "DEMO_MODE is enabled while DEBUG is False. In DEMO_MODE, the mock IdP "
                "permits unverified logins as any FSP participant; demo hosts must never hold real users.",
                hint="Set DEMO_MODE=False in production or ensure DEBUG=True for demo/staging environments.",
                id="fsp.W001",
            )
        )
    return warnings
