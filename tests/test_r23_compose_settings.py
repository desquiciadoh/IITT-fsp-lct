from pathlib import Path

import yaml


def test_gitattributes_forces_lf_for_sh_scripts():
    root = Path(__file__).resolve().parent.parent
    gitattributes_path = root / ".gitattributes"
    assert gitattributes_path.exists(), ".gitattributes file must exist"
    content = gitattributes_path.read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in content


def test_docker_entrypoint_does_not_mask_seed_failure():
    root = Path(__file__).resolve().parent.parent
    entrypoint_path = root / "docker-entrypoint.sh"
    content = entrypoint_path.read_text(encoding="utf-8")
    assert "python manage.py seed || true" not in content
    assert "python manage.py seed" in content


def test_docker_compose_shares_backend_env_across_services():
    root = Path(__file__).resolve().parent.parent
    compose_path = root / "docker-compose.yml"
    content = compose_path.read_text(encoding="utf-8")

    assert "x-backend-env: &backend-env" in content
    data = yaml.safe_load(content)

    services = data.get("services", {})
    for svc_name in ["api", "worker", "worker-llm", "beat"]:
        assert svc_name in services, f"Service {svc_name} must exist in docker-compose.yml"
        env = services[svc_name].get("environment", {})
        # Must have ALLOWED_HOSTS in environment
        assert "ALLOWED_HOSTS" in env, f"{svc_name} must have ALLOWED_HOSTS configured"
        assert "SESSION_COOKIE_SECURE" in env, (
            f"{svc_name} must have SESSION_COOKIE_SECURE configured"
        )
        assert "CSRF_COOKIE_SECURE" in env, f"{svc_name} must have CSRF_COOKIE_SECURE configured"
        assert "SECURE_SSL_REDIRECT" in env, f"{svc_name} must have SECURE_SSL_REDIRECT configured"


def test_settings_cookie_and_security_env_support():
    import importlib
    import os

    import config.settings as app_settings

    # Test with env overrides
    orig_env = os.environ.copy()
    try:
        os.environ["DEBUG"] = "False"
        os.environ["SECRET_KEY"] = "test-secret"
        os.environ["ITEM_SEED_SECRET"] = "test-seed"
        os.environ["ALLOWED_HOSTS"] = "localhost"
        os.environ["SESSION_COOKIE_SECURE"] = "False"
        os.environ["CSRF_COOKIE_SECURE"] = "False"
        os.environ["SECURE_SSL_REDIRECT"] = "False"
        os.environ["SECURE_HSTS_SECONDS"] = "3600"
        os.environ["SECURE_PROXY_SSL_HEADER"] = "HTTP_X_FORWARDED_PROTO,https"

        reloaded = importlib.reload(app_settings)
        assert reloaded.SESSION_COOKIE_SECURE is False
        assert reloaded.CSRF_COOKIE_SECURE is False
        assert reloaded.SECURE_SSL_REDIRECT is False
        assert reloaded.SECURE_HSTS_SECONDS == 3600
        assert reloaded.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    finally:
        os.environ.clear()
        os.environ.update(orig_env)
        importlib.reload(app_settings)
