"""FSP Draft verification gate: env, syntax, Django checks, migrations, lint, tests, invariants, diff.

Usage (from repo root):
    .venv/Scripts/python .claude/skills/verify/scripts/verify.py [--only PHASE,...] [--full] [--strict]

--only    comma-separated phases: env,syntax,django,migrations,lint,tests,invariants,diff
--full    run the whole pytest suite even if Postgres looks unreachable
--strict  treat WARN as failure (non-zero exit)

Exit code 1 if any phase FAILs. Missing tools are reported as SKIP, never as PASS.
"""
from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PY = sys.executable
CODE_DIRS = ["apps", "config", "tests"]
ENGINE_DIRS = ["apps/assessment/families", "apps/assessment/engine", "apps/matching/engine", "validation"]

results: list[tuple[str, str, str]] = []  # (phase, status, detail)


def record(phase: str, status: str, detail: str = "") -> None:
    results.append((phase, status, detail))


def run(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
    except FileNotFoundError as e:
        return 127, str(e)
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s: {' '.join(cmd)}"
    return p.returncode, (p.stdout + p.stderr).strip()


def has_module(name: str) -> bool:
    code, _ = run([PY, "-c", f"import {name}"], timeout=60)
    return code == 0


def tail(text: str, n: int = 25) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n:])


def py_files(dirs: list[str]) -> list[Path]:
    out: list[Path] = []
    for d in dirs:
        base = ROOT / d
        if base.is_dir():
            out += [p for p in base.rglob("*.py") if "migrations" not in p.parts]
    return out


# ── phases ──────────────────────────────────────────────────────────────────

def phase_env() -> None:
    ver = sys.version.split()[0]
    venv = ".venv" in PY.replace("\\", "/")
    missing = [m for m in ("django", "rest_framework", "pytest", "pytest_django") if not has_module(m)]
    if missing:
        record("env", "FAIL", f"python {ver} at {PY}; missing: {', '.join(missing)}. "
                              "Fix: py -3.13 -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt")
    else:
        record("env", "PASS" if venv else "WARN", f"python {ver}" + ("" if venv else " (not the project .venv)"))


def phase_syntax() -> None:
    bad = []
    for f in py_files(CODE_DIRS):
        try:
            compile(f.read_text(encoding="utf-8"), str(f), "exec")
        except SyntaxError as e:
            bad.append(f"{f.relative_to(ROOT)}:{e.lineno}: {e.msg}")
    record("syntax", "FAIL" if bad else "PASS", "\n".join(bad))


def phase_django() -> None:
    if not has_module("django"):
        record("django check", "SKIP", "django not installed")
        return
    code, out = run([PY, "manage.py", "check"])
    record("django check", "PASS" if code == 0 else "FAIL", "" if code == 0 else tail(out))


def phase_migrations() -> None:
    if not has_module("django"):
        record("migrations", "SKIP", "django not installed")
        return
    code, out = run([PY, "manage.py", "makemigrations", "--check", "--dry-run"])
    if code == 0:
        record("migrations", "PASS")
    else:
        record("migrations", "FAIL", "model changes without migrations:\n" + tail(out))


def phase_lint() -> None:
    if not has_module("ruff"):
        record("lint", "SKIP", "ruff not installed (.venv/Scripts/python -m pip install ruff)")
        return
    # Bug classes only: syntax, undefined names, redefinitions, broken comparisons, bare except, mutable defaults.
    # Style (unused imports etc.) is left to `ruff check` on the files you touched.
    code, out = run([PY, "-m", "ruff", "check", "--select", "E9,F63,F7,F82,F811,E722,B006",
                     "--no-cache", "--output-format", "concise", *[d for d in CODE_DIRS if (ROOT / d).exists()]])
    if code == 0:
        record("lint", "PASS")
    else:
        n = len([l for l in out.splitlines() if re.match(r".+:\d+:\d+:", l)])
        record("lint", "WARN", f"{n} issue(s):\n" + tail(out, 30))


def postgres_up() -> bool:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def phase_tests(full: bool) -> None:
    if not has_module("pytest_django"):
        record("tests", "SKIP", "pytest-django not installed")
        return
    if (ROOT / "tests/ml").is_dir():
        code, out = run([PY, "-m", "pytest", "tests/ml", "-q", "-p", "no:cacheprovider"])
        record("tests (ml, no DB)", "PASS" if code == 0 else "FAIL", tail(out, 15 if code else 1))
    if full or postgres_up():
        code, out = run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
        if code != 0 and re.search(r"OperationalError: connection (failed|to server)", out):
            record("tests (full)", "SKIP", "Postgres port is open but the connection was rejected (wrong credentials, "
                   "or another local PostgreSQL service on that port). Point POSTGRES_PORT/POSTGRES_PASSWORD "
                   "at the project DB, see CLAUDE.md")
        elif code == 5:
            record("tests (full)", "WARN", "no tests collected")
        else:
            record("tests (full)", "PASS" if code == 0 else "FAIL", tail(out, 25 if code else 1))
    else:
        record("tests (full)", "SKIP", "Postgres not reachable on POSTGRES_HOST:POSTGRES_PORT "
                                       "(docker start fsp-postgres) - run with --full to force")


def grep(pattern: str, files: list[Path], flags: int = 0) -> list[str]:
    rx = re.compile(pattern, flags)
    hits = []
    for f in files:
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if rx.search(line) and not line.lstrip().startswith("#"):
                    hits.append(f"{f.relative_to(ROOT).as_posix()}:{i}: {line.strip()[:120]}")
        except (UnicodeDecodeError, OSError):
            continue
    return hits


def phase_invariants() -> None:
    app_files = py_files(["apps"])
    serializers = [f for f in app_files if f.name == "serializers.py" or "serializers" in f.parts]
    engine_files = py_files(ENGINE_DIRS)

    # 1. Answer key must never be a serializer field.
    key_hits = grep(r"""['"](key|fingerprint)['"]""", serializers)
    key_hits = [h for h in key_hits if "fields" in h or "Field(" in h or "source=" in h]
    record("inv: answer key not serialized", "FAIL" if key_hits else "PASS", "\n".join(key_hits))

    # 2. No '__all__' / exclude serializers (silently exposes new columns).
    all_hits = grep(r"fields\s*=\s*['\"]__all__['\"]|^\s*exclude\s*=", serializers)
    record("inv: explicit serializer fields", "WARN" if all_hits else "PASS", "\n".join(all_hits))

    # 3. Contacts only through ContactAccessService (outreach/services.py) (owner edits in profiles are allowed; review the rest).
    allowed = {"apps/core/services.py", "apps/outreach/services.py", "apps/profiles/models.py", "apps/profiles/serializers.py",
               "apps/profiles/views.py", "apps/core/management/commands/seed.py",
               # reviewed 2026-10-09: candidate self-view; employer path goes through ContactAccessService
               "apps/outreach/serializers.py"}
    contact_hits = [h for h in grep(r"candidate_contacts|CandidateContact", app_files)
                    if h.split(":")[0] not in allowed and "/migrations/" not in h]
    record("inv: contact access via ContactAccessService", "WARN" if contact_hits else "PASS",
           ("review each path for ContactGrant gating:\n" + "\n".join(contact_hits)) if contact_hits else "")

    # 4. Engine purity: no Django/ORM/core imports.
    if engine_files:
        impure = grep(r"^\s*(from|import)\s+(django|rest_framework|core|identity|profiles|outreach|fsp_sync)\b|"
                      r"\.objects\.", engine_files)
        record("inv: engines import no Django", "FAIL" if impure else "PASS", "\n".join(impure))

        # 5. Determinism: no global randomness in engines.
        glob_rand = grep(r"(?<![\w.])random\.(random|choice|choices|randint|randrange|shuffle|sample|uniform|gauss|seed)\(|"
                         r"np\.random\.(rand|randn|randint|choice|shuffle|normal|uniform|seed)\(", engine_files)
        record("inv: no global RNG in engines", "FAIL" if glob_rand else "PASS", "\n".join(glob_rand))

    else:
        record("inv: engine purity/determinism", "SKIP", "no engine packages yet (" + ", ".join(ENGINE_DIRS) + ")")

    # 6. No LLM client imported or called on the grading/scoring path.
    scoring_files = py_files(["apps/assessment", "apps/matching", "validation"])
    llm = grep(r"^\s*(from|import)\s+\S*(llm_gateway|gigachat|openai|anthropic|langchain)|"
               r"\b(llm_gateway|gigachat|openai|anthropic)\.\w+\(", scoring_files, re.I)
    record("inv: no LLM in grading/scoring", "FAIL" if llm else "PASS", "\n".join(llm))

    # 8. Cooldown/deadline logic should use the demo-aware clock.
    now_hits = [h for h in grep(r"timezone\.now\(\)", py_files(["apps/assessment"]))
                if "def get_current_time_for_user" not in h and "now = timezone.now()" not in h]
    record("inv: demo-aware clock in assessment", "WARN" if now_hits else "PASS",
           ("bare timezone.now() in assessment (check cooldown/deadline paths):\n" + "\n".join(now_hits)) if now_hits else "")

    # 9. Hygiene.
    prints = grep(r"^\s*print\(", [f for f in app_files if "management" not in f.parts])
    record("hygiene: no print() in apps", "WARN" if prints else "PASS", "\n".join(prints))
    secrets = grep(r"""(api[_-]?key|secret|password|token)\s*=\s*['"][A-Za-z0-9_\-]{16,}['"]""",
                   py_files(["apps", "config"]), re.I)
    record("hygiene: no hard-coded secrets", "WARN" if secrets else "PASS", "\n".join(secrets))


def phase_diff() -> None:
    code, out = run(["git", "status", "--short"])
    _, stat = run(["git", "diff", "--stat", "HEAD"])
    record("diff", "INFO", (out or "(clean)") + ("\n" + tail(stat, 3) if stat else ""))


PHASES = ["env", "syntax", "django", "migrations", "lint", "tests", "invariants", "diff"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(PHASES))
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    only = [p.strip() for p in args.only.split(",") if p.strip()]
    os.chdir(ROOT)

    for p in only:
        if p == "tests":
            phase_tests(args.full)
        elif p in PHASES:
            globals()[f"phase_{p}"]()
        else:
            print(f"unknown phase: {p}", file=sys.stderr)
            return 2

    width = max(len(r[0]) for r in results)
    print("VERIFICATION REPORT\n" + "=" * 19)
    for phase, status, _ in results:
        print(f"{phase.ljust(width)}  {status}")
    details = [(p, s, d) for p, s, d in results if d and s != "PASS"]
    for phase, status, detail in details:
        print(f"\n--- {phase} [{status}]\n{detail}")

    failed = any(s == "FAIL" for _, s, _ in results)
    warned = any(s == "WARN" for _, s, _ in results)
    verdict = "NOT READY" if failed or (args.strict and warned) else "READY"
    print(f"\nOverall: {verdict}" + (" (with warnings)" if warned and verdict == "READY" else ""))
    return 1 if verdict == "NOT READY" else 0


if __name__ == "__main__":
    sys.exit(main())
