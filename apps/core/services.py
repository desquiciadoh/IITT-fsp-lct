"""Core services module.

Architecture rule: 'core' is a leaf module and must not import models from domain apps.
ContactAccessService and ContactInfo have moved to 'outreach.services'.
"""

import warnings


def __getattr__(name: str):
    if name in ("ContactAccessService", "ContactInfo"):
        warnings.warn(
            f"Importing {name} from core.services is deprecated. Use outreach.services instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        import outreach.services as outreach_services

        return getattr(outreach_services, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
