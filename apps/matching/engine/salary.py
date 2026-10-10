"""Gross <-> net monthly salary (ML.md §3). ML-0 stub: flat 13 % NDFL; ML-4 applies the progressive scale."""
from __future__ import annotations

FLAT_RATE = 0.13


def to_gross(amount: int, salary_type: str) -> int:
    if salary_type == "gross":
        return int(amount)
    if salary_type == "net":
        return round(amount / (1 - FLAT_RATE))
    raise ValueError(f"unknown salary type: {salary_type!r}")


def to_net(amount: int, salary_type: str) -> int:
    if salary_type == "net":
        return int(amount)
    if salary_type == "gross":
        return round(amount * (1 - FLAT_RATE))
    raise ValueError(f"unknown salary type: {salary_type!r}")
