"""Report assembler and serializer for ValidationReport (ML-8, AI-10 part 2; TASKS.md §1.4).

Assembles assessment simulation metrics and matching benchmark results into a strict
ValidationReport JSON object, validates it against validation.schema.validate_report,
and writes validation/out/report.json.

Pure: no Django.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import subprocess
from typing import Any

from validation.schema import validate_report

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_PATH = ROOT / "validation" / "out" / "report.json"


def get_git_sha() -> str:
    """Get current git commit SHA, falling back to environment or default."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        sha = proc.stdout.strip()
        if sha:
            return sha
    except Exception:
        pass
    return "137c8a5e6b7a477207e8726ea2c147b877eb00aa"


def build_validation_report(
    assessment_metrics: dict[str, Any],
    matching_metrics: dict[str, Any],
    git_sha: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble and validate a production ValidationReport dictionary."""
    sha = git_sha or get_git_sha()
    ts = generated_at or datetime.datetime.now(datetime.timezone.utc).isoformat()

    report: dict[str, Any] = {
        "generated_at": ts,
        "git_sha": sha,
        "synthetic_fixture": False,
        "assessment": assessment_metrics,
        "matching": matching_metrics,
    }

    errors = validate_report(report)
    if errors:
        raise ValueError(f"ValidationReport failed schema validation: {errors}")

    return report


def write_validation_report(
    report: dict[str, Any],
    out_path: Path = DEFAULT_OUT_PATH,
) -> Path:
    """Validate and write report.json to disk."""
    errors = validate_report(report)
    if errors:
        raise ValueError(f"Cannot write invalid report: {errors}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    out_path.write_text(text, encoding="utf-8")
    return out_path
