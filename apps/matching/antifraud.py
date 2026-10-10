"""Anti-fraud module for FSP Draft (Task BE-19).

Features:
- Weekly outreach credits (5 credits/week per position, refunded on accept)
- Salary sanity checks (max/min <= 2.0 ratio, positive bounds)
- Corporate domain verification and trust level computation
- Russian INN checksum validation (10-digit legal entities and 12-digit sole proprietorships)
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import TYPE_CHECKING

from core.enums import TrustLevel
from core.errors import NoCredits, SalaryInvalid
from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    import uuid

    from matching.models import Position

logger = logging.getLogger(__name__)

# Common public/free email providers (not corporate domains)
PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "mail.ru",
    "inbox.ru",
    "bk.ru",
    "list.ru",
    "internet.ru",
    "yandex.ru",
    "yandex.com",
    "ya.ru",
    "narod.ru",
    "rambler.ru",
    "lenta.ru",
    "autorambler.ru",
    "myrambler.ru",
    "ro.ru",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "msn.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "proton.me",
    "protonmail.com",
    "zoho.com",
    "gmx.com",
    "aol.com",
}


def validate_inn(inn: str) -> bool:
    """Validate Russian INN checksum.

    10 digits: Legal entities (ЮЛ)
    12 digits: Sole proprietorships / Individuals (ИП / ФЛ)
    """
    if not inn or not isinstance(inn, str):
        return False

    inn = inn.strip()
    if not inn.isdigit():
        return False

    length = len(inn)
    if length == 10:
        # Legal entities (10 digits)
        weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        checksum = (sum(int(inn[i]) * weights[i] for i in range(9)) % 11) % 10
        return checksum == int(inn[9])
    elif length == 12:
        # Individuals / Sole proprietorships (12 digits)
        weights_11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        checksum_11 = (sum(int(inn[i]) * weights_11[i] for i in range(10)) % 11) % 10
        weights_12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        checksum_12 = (sum(int(inn[i]) * weights_12[i] for i in range(11)) % 11) % 10
        return checksum_11 == int(inn[10]) and checksum_12 == int(inn[11])

    return False


def extract_domain(email_or_domain: str) -> str:
    """Extract clean domain from email or domain string."""
    if not email_or_domain:
        return ""
    val = email_or_domain.strip().lower()
    if "@" in val:
        val = val.split("@", 1)[1]
    # Remove protocol if user passed a URL
    val = re.sub(r"^https?://", "", val)
    val = val.split("/")[0].split(":")[0]
    return val


def is_corporate_domain(email_or_domain: str) -> bool:
    """Return True if email or domain belongs to a corporate domain (not public webmail)."""
    domain = extract_domain(email_or_domain)
    if not domain or "." not in domain:
        return False
    return domain not in PUBLIC_EMAIL_DOMAINS


def compute_company_trust_level(inn: str, email_or_domain: str) -> str:
    """Compute company trust level based on INN and corporate email domain.

    - VERIFIED: valid INN and corporate domain
    - DOMAIN: corporate domain present, but INN absent or unverified
    - NONE: public email domain or neither verified
    """
    has_valid_inn = validate_inn(inn)
    has_corp_domain = is_corporate_domain(email_or_domain)

    if has_valid_inn and has_corp_domain:
        return TrustLevel.VERIFIED
    elif has_corp_domain:
        return TrustLevel.DOMAIN
    return TrustLevel.NONE


def validate_salary_ratio(salary_min: int | None, salary_max: int | None) -> None:
    """Enforce salary sanity checks:

    1. salary_min > 0
    2. salary_max >= salary_min
    3. salary_max / salary_min <= 2.0 (salary spread ratio)
    """
    if salary_min is None or salary_max is None:
        return

    if salary_min <= 0:
        raise SalaryInvalid("salary_min must be greater than 0")

    if salary_max < salary_min:
        raise SalaryInvalid("salary_max must be greater than or equal to salary_min")

    if salary_max > 2 * salary_min:
        raise SalaryInvalid("salary_max / salary_min ratio cannot exceed 2.0")


def get_current_credit_week(dt=None):
    """Return Monday date for the given datetime or current time."""
    now_dt = dt or timezone.now()
    d = now_dt.date()
    return d - timedelta(days=d.weekday())


def consume_position_credit(position: Position, now=None) -> None:
    """Check and consume a weekly outreach credit for the given position.

    Enforces 5 credits/week limit (Task BE-19).
    Raises NoCredits if limit is reached.
    """
    from matching.models import PositionCredit

    week_date = get_current_credit_week(now)
    with transaction.atomic():
        credit, _ = PositionCredit.objects.select_for_update().get_or_create(
            position=position,
            week=week_date,
            defaults={"used": 0, "refunded": 0},
        )
        active_used = credit.used - credit.refunded
        if active_used >= 5:
            raise NoCredits(
                f"Weekly outreach credit limit reached for position {position.id} (5 credits/week)"
            )
        credit.used += 1
        credit.save(update_fields=["used"])


def refund_position_credit(position_id: uuid.UUID, created_at=None) -> None:
    """Refund a credit when an offer is accepted (Task BE-19)."""
    from matching.models import PositionCredit

    week_date = get_current_credit_week(created_at)
    credit = PositionCredit.objects.filter(
        position_id=position_id,
        week=week_date,
    ).first()

    if not credit:
        credit = (
            PositionCredit.objects.filter(position_id=position_id)
            .order_by("-week")
            .first()
        )

    if credit:
        credit.refunded += 1
        credit.save(update_fields=["refunded"])
        logger.info(
            "Refunded 1 credit for position=%s week=%s (refunded=%d)",
            position_id,
            credit.week,
            credit.refunded,
        )


def get_remaining_position_credits(position: Position, now=None) -> int:
    """Return remaining weekly outreach credits for the given position (out of 5)."""
    from matching.models import PositionCredit

    week_date = get_current_credit_week(now)
    credit = PositionCredit.objects.filter(
        position=position,
        week=week_date,
    ).first()
    if not credit:
        return 5
    active_used = max(0, credit.used - credit.refunded)
    return max(0, 5 - active_used)

