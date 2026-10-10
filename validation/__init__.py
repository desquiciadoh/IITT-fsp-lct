"""Validation suite (ML-5..ML-8): synthetic world, assessment simulation, matching benchmark, report.

Imports the production engines; never Django. Run from the repo root: python -m validation.run
"""
import sys
from pathlib import Path

_APPS = str(Path(__file__).resolve().parents[1] / "apps")
if _APPS not in sys.path:          # the engines are top-level packages under apps/ (CLAUDE.md)
    sys.path.insert(0, _APPS)
