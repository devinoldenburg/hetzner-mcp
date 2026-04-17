"""Core data models for Hetzner operation registry and HTTP interactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ApiDomain = Literal["cloud", "storage"]
ParameterLocation = Literal["path", "query", "header", "cookie"]


@dataclass(slots=True, frozen=True)
class ParameterSpec:
    """Single API parameter definition."""

    name: str
    location: ParameterLocation
    required: bool
    schema: dict[str, Any]
    description: str | None = None


@dataclass(slots=True, frozen=True)
class RequestBodySpec:
    """JSON request body definition."""

    required: bool
    schema: dict[str, Any] | None
    description: str | None = None


@dataclass(slots=True, frozen=True)
class OperationSpec:
    """Normalized operation description generated from OpenAPI specs."""

    operation_id: str
    api_domain: ApiDomain
    method: str
    path: str
    tags: tuple[str, ...]
    summary: str | None
    description: str | None
    parameters: tuple[ParameterSpec, ...] = field(default_factory=tuple)
    request_body: RequestBodySpec | None = None

    @property
    def primary_tag(self) -> str:
        return self.tags[0] if self.tags else "Untagged"

    @property
    def display_summary(self) -> str:
        if self.summary:
            return self.summary
        if self.description:
            return self.description.splitlines()[0]
        return f"{self.method} {self.path}"

    @property
    def docs_text(self) -> str:
        """Best available endpoint docs text from OpenAPI content."""
        if self.description:
            return self.description
        if self.summary:
            return self.summary
        return f"{self.method} {self.path}"


@dataclass(slots=True, frozen=True)
class CategorySpec:
    """Category/tag-level API documentation group."""

    category_id: str
    api_domain: ApiDomain
    name: str
    slug: str
    description: str | None
    operation_ids: tuple[str, ...]

    @property
    def tool_name(self) -> str:
        return f"category_guide_{self.api_domain}_{self.slug}"


@dataclass(slots=True, frozen=True)
class HttpResult:
    """Represents one HTTP call result."""

    ok: bool
    status_code: int
    headers: dict[str, str]
    data: Any
    raw_text: str
    request_url: str
    retries: int = 0


@dataclass(slots=True, frozen=True)
class BuiltRequest:
    """Prepared request arguments for transport execution."""

    path_params: dict[str, Any]
    query_params: dict[str, Any]
    body: Any | None
