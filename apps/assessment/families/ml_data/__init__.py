"""ML & Data item families (one module per family group)."""
from .models_dl import FAMILIES as _models_dl
from .stats_metrics import FAMILIES as _stats_metrics

FAMILIES = [*_stats_metrics, *_models_dl]
