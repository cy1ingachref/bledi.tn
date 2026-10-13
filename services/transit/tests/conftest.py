from __future__ import annotations

import pytest
from support import services

from bledi_transit.application.routing.router import Router


@pytest.fixture(scope="session")
def router() -> Router:
    return services().router
