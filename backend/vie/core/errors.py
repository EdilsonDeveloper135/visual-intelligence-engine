"""Uniform API errors: {"code", "message", "details"}. Messages are safe to show to the user."""

from __future__ import annotations

from typing import Any


class VieError(Exception):
    status_code = 400

    def __init__(self, code: str, message: str, details: Any = None, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        if status_code is not None:
            self.status_code = status_code

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


class NotFound(VieError):
    status_code = 404


class Conflict(VieError):
    status_code = 409


class Forbidden(VieError):
    status_code = 403


class Unauthorized(VieError):
    status_code = 401


class TooLarge(VieError):
    status_code = 413


class Unprocessable(VieError):
    status_code = 422


class ServiceUnavailable(VieError):
    status_code = 503
