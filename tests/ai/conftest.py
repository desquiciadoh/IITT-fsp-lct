"""Pytest configuration for AI/LLM Gateway tests."""
import sys
from pathlib import Path

# Ensure apps/ and repo root are on sys.path per AI.md §2 and AI-R14
root_dir = Path(__file__).resolve().parent.parent.parent
apps_dir = root_dir / "apps"
if str(apps_dir) not in sys.path:
    sys.path.insert(0, str(apps_dir))
if str(root_dir) not in sys.path:
    sys.path.insert(1, str(root_dir))
