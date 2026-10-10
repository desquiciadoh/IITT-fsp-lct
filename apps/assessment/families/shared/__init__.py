"""Shared (all specializations) item families (one module per family group)."""
from .code_trace import FAMILIES as _code_trace
from .complexity import FAMILY as _complexity
from .ds_bugs import FAMILIES as _ds_bugs

FAMILIES = [_complexity, *_code_trace, *_ds_bugs]
