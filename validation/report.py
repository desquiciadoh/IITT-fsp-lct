"""ValidationReport assembly (ML-8; TASKS.md §1.4). Pure: no Django.

`build_report` validates the dict against validation.schema before anything is written. The git
SHA is read from the repository; there is no fallback value: a report that cannot name the code
it measured is not written. If the working tree has changes outside validation/out, the SHA gets a
"-dirty" suffix, so a committed report.json says whether it is reproducible from that commit.
"""
from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path
from typing import Any

from validation.schema import validate_report

ROOT = Path(__file__).resolve().parents[1]


def git_sha(root: Path = ROOT) -> str:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True,
                              timeout=30).stdout.strip()
    sha = git("rev-parse", "HEAD")
    if not sha:
        raise RuntimeError("git rev-parse HEAD returned nothing")
    dirty = git("status", "--porcelain", "--", ".", ":(exclude)validation/out")
    return f"{sha}-dirty" if dirty else sha


def build_report(assessment: dict[str, Any], matching: dict[str, Any], sha: str,
                 generated_at: str | None = None) -> dict[str, Any]:
    report = {"generated_at": generated_at or datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "git_sha": sha, "synthetic_fixture": False, "assessment": assessment, "matching": matching}
    errors = validate_report(report)
    if errors:
        raise ValueError(f"ValidationReport does not match the schema: {errors}")
    return report


def write_json(data: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
