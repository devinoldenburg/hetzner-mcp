"""Custom error types for hetzner-mcp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class HetznerMCPError(Exception):
    """Base error type for the project."""

    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


class SpecLoadError(HetznerMCPError):
    """Raised when OpenAPI specs cannot be loaded or parsed."""


class ValidationError(HetznerMCPError):
    """Raised for invalid tool arguments."""


class OperationNotFoundError(HetznerMCPError):
    """Raised when a requested operation does not exist."""
