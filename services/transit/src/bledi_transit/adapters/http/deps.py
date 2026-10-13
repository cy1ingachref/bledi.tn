"""Use cases built by the composition root, handed to route handlers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from bledi_transit.application.catalog import Catalog
from bledi_transit.application.ports import Geocoder
from bledi_transit.application.routing.router import Router


@dataclass(frozen=True)
class Services:
    catalog: Catalog
    router: Router
    geocoder: Geocoder


def _services(request: Request) -> Services:
    return request.app.state.services


def _catalog(request: Request) -> Catalog:
    return _services(request).catalog


def _router(request: Request) -> Router:
    return _services(request).router


def _geocoder(request: Request) -> Geocoder:
    return _services(request).geocoder


CatalogDep = Annotated[Catalog, Depends(_catalog)]
RouterDep = Annotated[Router, Depends(_router)]
GeocoderDep = Annotated[Geocoder, Depends(_geocoder)]
