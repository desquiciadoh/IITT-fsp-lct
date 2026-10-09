"""PostToolUse hook: after Claude edits a .py file, fail fast on syntax errors and undefined names.

Reads the hook JSON from stdin. Exit 2 sends stderr back to Claude so it fixes the file right away;
exit 0 otherwise (including when the file isn't Python or ruff isn't installed).
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    path = (data.get("tool_input") or {}).get("file_path") or ""
    if not path.endswith(".py") or not os.path.isfile(path):
        return 0

    try:
        compile(Path(path).read_text(encoding="utf-8"), path, "exec")
    except SyntaxError as e:
        print(f"SyntaxError in {path}:{e.lineno}: {e.msg}", file=sys.stderr)
        return 2

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).resolve().parents[2]))
    venv_py = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not venv_py.exists():
        return 0
    try:
        r = subprocess.run([str(venv_py), "-m", "ruff", "check", "--select", "E9,F821,F822,F823",
                            "--output-format", "concise", "--no-cache", path],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if r.returncode == 1 and r.stdout.strip():
        print("ruff (undefined names / syntax):\n" + r.stdout.strip(), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
