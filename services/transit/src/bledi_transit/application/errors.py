from __future__ import annotations

from typing import Literal

ErrorCode = Literal["not_found", "invalid_request", "unavailable"]


class AppError(Exception):
    def __init__(self, code: ErrorCode, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
