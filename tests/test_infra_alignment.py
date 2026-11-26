"""Regression tests for compose/Dockerfile infrastructure alignment.

Covers fixes H2, L1 and L2 from bledi-fixes-handoff.md:
- the Rust routing service must not publish :8081 to the host;
- every Dockerfile HTTP healthcheck must probe the same path as compose;
- transit must not wait on the db service (it has no database dependency).

These are pure text assertions so they run without Docker in any environment.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMPOSE = REPO / "docker-compose.yml"
DOCKERFILES = {
    "transit": REPO / "services" / "transit" / "Dockerfile",
    "routing": REPO / "services" / "routing" / "Dockerfile",
    "accounts": REPO / "services" / "accounts" / "Dockerfile",
}


def _health_path(text: str, port: int) -> str | None:
    m = re.search(r'curl[^\n]*?-f[^\n]*?http://localhost:%d(/[^\s"]+)' % port, text)
    return m.group(1) if m else None


def test_routing_port_not_published():
    compose = COMPOSE.read_text(encoding="utf-8")
    routing_block = compose.split("  transit-routing:", 1)[1].split("  web:", 1)[0]
    assert 'ports:' not in routing_block, "transit-routing must not publish host ports"
    assert 'expose:' in routing_block and '"8081"' in routing_block


def test_compose_and_dockerfile_healthchecks_agree():
    compose = COMPOSE.read_text(encoding="utf-8")
    for service, port in (("transit", 8000), ("routing", 8081), ("accounts", 3000)):
        compose_path = _health_path(compose, port)
        dockerfile_path = _health_path(DOCKERFILES[service].read_text(encoding="utf-8"), port)
        assert compose_path is not None, f"{service}: compose healthcheck path missing"
        assert dockerfile_path == compose_path, (
            f"{service}: Dockerfile healthcheck {dockerfile_path!r} != compose {compose_path!r}"
        )


def test_transit_does_not_depend_on_db():
    compose = COMPOSE.read_text(encoding="utf-8")
    start = compose.index("\n  transit:\n")
    end = compose.find("\n  transit-routing:", start)
    transit_block = compose[start:end if end > 0 else None]
    assert "depends_on:" not in transit_block, "transit has no DB dependency"
