"""Pure CAT/IRT engine (ML.md §2, §3): no Django, no ORM, no core.enums.

`FAMILIES_REGISTRY` and `score_assessment` re-export the legacy API that BE's services
still import; they go away once BE swaps in `CatEngine` (BE.md N2).
"""
from .legacy import FAMILIES_REGISTRY, score_assessment

__all__ = ["FAMILIES_REGISTRY", "score_assessment"]
