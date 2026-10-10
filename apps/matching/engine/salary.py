"""Gross <-> net monthly salary under the Russian progressive NDFL scale (ML-4).

Scale for tax residents' employment income from 2025 (п. 1 ст. 224 НК РФ), annual base:
    13 % up to 2.4 M ₽, 15 % up to 5 M, 18 % up to 20 M, 20 % up to 50 M, 22 % above.
Each rate applies only to the part of the income above the previous threshold.
Sources (checked 2026-10-10):
  https://www.nalog.gov.ru/rn26/news/activities_fts/16653428/   (FNS, 02.10.2026)
  https://www.consultant.ru/law/podborki/progressivnaya_shkala_ndfl/
Assumptions: a steady monthly salary (annual base = 12 × monthly), one employer, no regional
coefficients or northern allowances (those use the separate 13/15 % scale of п. 1.2) and no
deductions. Good enough to compare an offer with an expectation on the same footing; it is
not payroll accounting. Results are rounded to whole rubles.
"""
from __future__ import annotations

# (upper bound of the annual bracket in ₽, rate); None = no upper bound
BRACKETS: tuple[tuple[float | None, float], ...] = (
    (2_400_000, 0.13),
    (5_000_000, 0.15),
    (20_000_000, 0.18),
    (50_000_000, 0.20),
    (None, 0.22),
)


def annual_tax(gross_annual: float) -> float:
    """NDFL on an annual gross base, marginal brackets."""
    if gross_annual < 0:
        raise ValueError("income must be >= 0")
    tax, lower = 0.0, 0.0
    for upper, rate in BRACKETS:
        top = gross_annual if upper is None else min(gross_annual, upper)
        if top > lower:
            tax += (top - lower) * rate
        if upper is None or gross_annual <= upper:
            break
        lower = upper
    return tax


def _gross_from_net_annual(net_annual: float) -> float:
    """Inverse of g − tax(g): walk the brackets in net terms (net is strictly increasing in gross)."""
    if net_annual < 0:
        raise ValueError("income must be >= 0")
    lower_g = 0.0
    for upper, rate in BRACKETS:
        lower_n = lower_g - annual_tax(lower_g)
        if upper is None:
            return lower_g + (net_annual - lower_n) / (1 - rate)
        upper_n = upper - annual_tax(upper)
        if net_annual <= upper_n:
            return lower_g + (net_annual - lower_n) / (1 - rate)
        lower_g = upper
    raise AssertionError("unreachable")


def to_gross(amount: int, salary_type: str) -> int:
    """Monthly amount as gross."""
    if salary_type == "gross":
        return int(amount)
    if salary_type == "net":
        return round(_gross_from_net_annual(12 * amount) / 12)
    raise ValueError(f"unknown salary type: {salary_type!r}")


def to_net(amount: int, salary_type: str) -> int:
    """Monthly amount as net (after NDFL)."""
    if salary_type == "net":
        return int(amount)
    if salary_type == "gross":
        annual = 12 * amount
        return round((annual - annual_tax(annual)) / 12)
    raise ValueError(f"unknown salary type: {salary_type!r}")
