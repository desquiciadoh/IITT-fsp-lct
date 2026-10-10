"""Live smoke test against GigaChat (AI-4). Never runs in CI.

Run with a real key:  GIGACHAT_AUTH_KEY=... pytest -m live tests/ai
Paste the output (no CV text) into the PR.
"""
import os
from pathlib import Path

import pytest
from llm_gateway import GatewayConfig, get_gateway, parse_jd

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.getenv("GIGACHAT_AUTH_KEY"), reason="GIGACHAT_AUTH_KEY is not set"),
]

JD_DIR = Path(__file__).resolve().parent / "fixtures" / "jd"


def test_live_parse_jd_end_to_end():
    config = GatewayConfig(
        provider="gigachat",
        auth_key=os.environ["GIGACHAT_AUTH_KEY"],
        scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
        model=os.getenv("GIGACHAT_MODEL", "GigaChat-2"),
        ca_bundle=os.getenv("GIGACHAT_CA_BUNDLE") or None,
        timeout_s=float(os.getenv("LLM_TIMEOUT_S", "10")),
    )
    result = parse_jd((JD_DIR / "jd_backend_must_nice.txt").read_text(encoding="utf-8"), gateway=get_gateway(config))

    print(f"source={result.source} reason={result.fallback_reason} spec={result.draft['specialization']} "
          f"must={result.draft['must_skills']} salary={result.draft['salary_min']}-{result.draft['salary_max']}")
    assert result.source == "llm", result.fallback_reason
    assert result.draft["specialization"] == "backend"
