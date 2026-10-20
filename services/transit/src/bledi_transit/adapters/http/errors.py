from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from bledi_transit.application.errors import AppError

log = logging.getLogger("bledi.http")

STATUS = {"not_found": 404, "invalid_request": 400, "unavailable": 503}
PUBLIC_CODES = {"not_found", "invalid_request", "unavailable"}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        detail = exc.detail if exc.code in PUBLIC_CODES else "invalid request"
        return JSONResponse({"detail": detail}, status_code=STATUS[exc.code])

    @app.exception_handler(Exception)
    async def internal(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s", request.url.path, exc_info=exc)
        return JSONResponse({"error": "internal"}, status_code=500)
