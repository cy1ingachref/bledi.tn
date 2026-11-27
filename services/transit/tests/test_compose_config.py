"""PR5 regression guard: both services must trust the gateway's XFF header.

This fails if someone removes TRUST_PROXY_HEADERS from either service in
docker-compose.yml and reintroduces the all-users-one-bucket bug.
"""
from __future__ import annotations

from pathlib import Path

import yaml


def _repo_root() -> Path:
    # tests/ -> transit/ -> services/ -> repo root
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docker-compose.yml").is_file():
            return parent
    raise AssertionError("docker-compose.yml not found above " + str(here))


def _env_map(service: dict) -> dict[str, str]:
    """Normalise both `environment:` forms: mapping and `KEY=value` list."""
    env = service.get("environment") or {}
    if isinstance(env, dict):
        return {str(k): str(v) for k, v in env.items()}
    result: dict[str, str] = {}
    for item in env:
        key, sep, value = str(item).partition("=")
        if sep:
            result[key] = value
    return result


def load_compose() -> dict:
    with _repo_root().joinpath("docker-compose.yml").open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, dict) and "services" in data
    return data["services"]


def test_transit_trusts_proxy_headers():
    services = load_compose()
    assert "transit" in services
    env = _env_map(services["transit"])
    assert env.get("TRUST_PROXY_HEADERS") == "1"


def test_accounts_trusts_proxy_headers():
    services = load_compose()
    assert "accounts" in services
    env = _env_map(services["accounts"])
    assert env.get("TRUST_PROXY_HEADERS") == "1"


def test_environment_mapping_normaliser_handles_list_form():
    """Guard the guard: the KEY=value list form is read correctly too."""
    assert _env_map({"environment": ["A=1", "TRUST_PROXY_HEADERS=1", "BARE"]}) == {
        "A": "1",
        "TRUST_PROXY_HEADERS": "1",
    }
