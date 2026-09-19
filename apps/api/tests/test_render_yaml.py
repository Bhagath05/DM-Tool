"""Regression: deployment config must let the worker's production fail-closed
guard activate.

`validate_worker_secrets` (aicmo/config.py) only runs when `api_env ==
"production"`. If the worker service doesn't declare `API_ENV`, it resolves to
`development` and the guard is a silent no-op — the exact gap the audit found.
"""

from __future__ import annotations

from pathlib import Path


def _render_yaml_text() -> str:
    # apps/api/tests/test_render_yaml.py -> repo root is parents[3].
    return (Path(__file__).resolve().parents[3] / "render.yaml").read_text()


def test_worker_service_declares_api_env():
    text = _render_yaml_text()
    assert "name: dm-tool-worker" in text
    worker_section = text.split("name: dm-tool-worker", 1)[1]
    assert "API_ENV" in worker_section, (
        "dm-tool-worker must declare API_ENV so validate_worker_secrets "
        "activates in production (without it the guard is a no-op)."
    )


def test_api_service_still_declares_auth_env():
    text = _render_yaml_text()
    api_section = (
        text.split("name: dm-tool-api", 1)[1].split("name: dm-tool-worker", 1)[0]
    )
    assert "API_ENV" in api_section
    # First-party auth needs no AUTH_MODE / CLERK_* env — the render config must
    # not reintroduce them.
    assert "AUTH_MODE" not in api_section
    assert "CLERK" not in api_section
