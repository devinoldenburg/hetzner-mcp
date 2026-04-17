"""Operation registry construction for Hetzner APIs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .errors import OperationNotFoundError, SpecLoadError
from .models import ApiDomain, CategorySpec, OperationSpec, ParameterSpec, RequestBodySpec
from .specs import LoadedSpecs, load_specs, resolve_refs

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


@dataclass(slots=True)
class OperationRegistry:
    """In-memory index of all operations and summary metadata."""

    operations: dict[str, OperationSpec]
    categories: dict[str, CategorySpec]
    loaded_from_cache: bool = False

    @classmethod
    def load(cls, *, refresh_specs: bool = False) -> OperationRegistry:
        specs = load_specs(refresh=refresh_specs)
        operations, categories = _build_registry(specs)
        return cls(operations=operations, categories=categories)

    @property
    def operation_count(self) -> int:
        return len(self.operations)

    def get(self, operation_id: str) -> OperationSpec:
        try:
            return self.operations[operation_id]
        except KeyError as exc:
            raise OperationNotFoundError(
                code="operation_not_found",
                message=f"Unknown operation: {operation_id}",
            ) from exc

    def all_operations(self) -> list[OperationSpec]:
        return sorted(self.operations.values(), key=lambda op: op.operation_id)

    def all_categories(self) -> list[CategorySpec]:
        return sorted(self.categories.values(), key=lambda cat: cat.category_id)

    def get_category(self, category_id: str) -> CategorySpec:
        try:
            return self.categories[category_id]
        except KeyError as exc:
            raise OperationNotFoundError(
                code="category_not_found",
                message=f"Unknown API category: {category_id}",
            ) from exc

    def get_category_by_tool_name(self, tool_name: str) -> CategorySpec:
        for category in self.categories.values():
            if category.tool_name == tool_name:
                return category
        raise OperationNotFoundError(
            code="category_not_found",
            message=f"Unknown API category tool: {tool_name}",
        )

    def operations_for_category(self, category_id: str) -> list[OperationSpec]:
        category = self.get_category(category_id)
        return [self.operations[operation_id] for operation_id in category.operation_ids]

    def list_filtered(
        self,
        *,
        api_domain: ApiDomain | None = None,
        tag: str | None = None,
        method: str | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> list[OperationSpec]:
        method_normalized = method.upper() if method else None
        query_normalized = query.lower().strip() if query else None

        results: list[OperationSpec] = []
        for operation in self.all_operations():
            if api_domain and operation.api_domain != api_domain:
                continue
            if tag and operation.primary_tag.lower() != tag.lower():
                continue
            if method_normalized and operation.method.upper() != method_normalized:
                continue
            if query_normalized:
                haystack = " ".join(
                    [
                        operation.operation_id,
                        operation.path,
                        operation.display_summary,
                        " ".join(operation.tags),
                    ]
                ).lower()
                if query_normalized not in haystack:
                    continue
            results.append(operation)
            if len(results) >= max(limit, 1):
                break
        return results

    def counts_by_tag(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for operation in self.operations.values():
            tag = operation.primary_tag
            counts[tag] = counts.get(tag, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: item[0].lower()))

    def counts_by_domain(self) -> dict[str, int]:
        out = {"cloud": 0, "storage": 0}
        for operation in self.operations.values():
            out[operation.api_domain] += 1
        return out


def _build_registry(specs: LoadedSpecs) -> tuple[dict[str, OperationSpec], dict[str, CategorySpec]]:
    operations: dict[str, OperationSpec] = {}
    categories: dict[str, CategorySpec] = {}
    sources: tuple[tuple[ApiDomain, dict[str, Any]], ...] = (
        ("cloud", specs.cloud),
        ("storage", specs.storage),
    )
    for api_domain, spec in sources:
        parsed = _parse_spec_operations(spec=spec, api_domain=api_domain)
        for operation in parsed:
            if operation.operation_id in operations:
                raise SpecLoadError(
                    code="duplicate_operation_id",
                    message=f"Duplicate operationId detected: {operation.operation_id}",
                )
            operations[operation.operation_id] = operation
        parsed_categories = _parse_spec_categories(
            spec=spec, api_domain=api_domain, operations=parsed
        )
        for category in parsed_categories:
            if category.category_id in categories:
                raise SpecLoadError(
                    code="duplicate_category_id",
                    message=f"Duplicate category id detected: {category.category_id}",
                )
            categories[category.category_id] = category
    return operations, categories


def _parse_spec_operations(*, spec: dict[str, Any], api_domain: ApiDomain) -> list[OperationSpec]:
    operations: list[OperationSpec] = []

    for path, path_item_raw in spec.get("paths", {}).items():
        path_item = resolve_refs(path_item_raw, spec=spec)
        if not isinstance(path_item, dict):
            continue

        path_parameters = path_item.get("parameters", [])
        for method in HTTP_METHODS:
            operation_raw = path_item.get(method)
            if operation_raw is None:
                continue
            operation_obj = resolve_refs(operation_raw, spec=spec)
            if not isinstance(operation_obj, dict):
                continue

            operation_id = operation_obj.get("operationId")
            if not isinstance(operation_id, str) or not operation_id:
                operation_id = _fallback_operation_id(method=method, path=path)

            tags_raw = operation_obj.get("tags", [])
            tags = tuple(str(tag) for tag in tags_raw) if isinstance(tags_raw, list) else ()

            parameters = _extract_parameters(
                spec=spec,
                path_parameters=path_parameters,
                operation_parameters=operation_obj.get("parameters", []),
            )

            request_body = _extract_request_body(spec=spec, operation_obj=operation_obj)

            operation = OperationSpec(
                operation_id=operation_id,
                api_domain=api_domain,
                method=method.upper(),
                path=path,
                tags=tags,
                summary=_string_or_none(operation_obj.get("summary")),
                description=_string_or_none(operation_obj.get("description")),
                parameters=tuple(parameters),
                request_body=request_body,
            )
            operations.append(operation)

    return sorted(operations, key=lambda op: op.operation_id)


def _extract_parameters(
    *,
    spec: dict[str, Any],
    path_parameters: Any,
    operation_parameters: Any,
) -> list[ParameterSpec]:
    merged_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for source in (path_parameters, operation_parameters):
        if not isinstance(source, list):
            continue
        for raw_parameter in source:
            resolved = resolve_refs(raw_parameter, spec=spec)
            if not isinstance(resolved, dict):
                continue
            name = resolved.get("name")
            location = resolved.get("in")
            if not isinstance(name, str) or not isinstance(location, str):
                continue
            merged_by_key[(name, location)] = resolved

    output: list[ParameterSpec] = []
    for (name, location), parameter in sorted(merged_by_key.items(), key=lambda item: item[0]):
        schema_raw = parameter.get("schema", {"type": "string"})
        schema = resolve_refs(schema_raw, spec=spec)
        if not isinstance(schema, dict):
            schema = {"type": "string"}

        normalized_location = (
            location if location in {"path", "query", "header", "cookie"} else "query"
        )
        output.append(
            ParameterSpec(
                name=name,
                location=normalized_location,  # type: ignore[arg-type]
                required=bool(parameter.get("required", False) or normalized_location == "path"),
                schema=schema,
                description=_string_or_none(parameter.get("description")),
            )
        )
    return output


def _extract_request_body(
    *, spec: dict[str, Any], operation_obj: dict[str, Any]
) -> RequestBodySpec | None:
    raw_request_body = operation_obj.get("requestBody")
    if raw_request_body is None:
        return None
    resolved = resolve_refs(raw_request_body, spec=spec)
    if not isinstance(resolved, dict):
        return None

    content = resolved.get("content", {})
    if not isinstance(content, dict):
        return None

    body_schema: dict[str, Any] | None = None
    if "application/json" in content and isinstance(content["application/json"], dict):
        schema_candidate = content["application/json"].get("schema")
        if schema_candidate is not None:
            schema_resolved = resolve_refs(schema_candidate, spec=spec)
            if isinstance(schema_resolved, dict):
                body_schema = schema_resolved

    return RequestBodySpec(
        required=bool(resolved.get("required", False)),
        schema=body_schema,
        description=_string_or_none(resolved.get("description")),
    )


def _fallback_operation_id(*, method: str, path: str) -> str:
    normalized = (
        path.strip("/").replace("/", "_").replace("{", "").replace("}", "").replace("-", "_")
    )
    return f"{method}_{normalized}"


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _parse_spec_categories(
    *,
    spec: dict[str, Any],
    api_domain: ApiDomain,
    operations: list[OperationSpec],
) -> list[CategorySpec]:
    """Build category docs from OpenAPI tags and operation assignments."""
    operations_by_tag: dict[str, list[OperationSpec]] = {}
    for operation in operations:
        operations_by_tag.setdefault(operation.primary_tag, []).append(operation)

    tag_descriptions: dict[str, str | None] = {}
    spec_tags = spec.get("tags", [])
    if isinstance(spec_tags, list):
        for item in spec_tags:
            resolved = resolve_refs(item, spec=spec)
            if not isinstance(resolved, dict):
                continue
            tag_name = resolved.get("name")
            if not isinstance(tag_name, str) or not tag_name:
                continue
            tag_descriptions[tag_name] = _string_or_none(resolved.get("description"))

    categories: list[CategorySpec] = []
    for tag_name, tagged_operations in sorted(
        operations_by_tag.items(), key=lambda x: x[0].lower()
    ):
        slug = _slugify(tag_name)
        category_id = f"{api_domain}:{slug}"
        categories.append(
            CategorySpec(
                category_id=category_id,
                api_domain=api_domain,
                name=tag_name,
                slug=slug,
                description=tag_descriptions.get(tag_name),
                operation_ids=tuple(sorted(op.operation_id for op in tagged_operations)),
            )
        )

    return categories


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    replaced = re.sub(r"[^a-z0-9]+", "_", lowered)
    normalized = re.sub(r"_+", "_", replaced).strip("_")
    return normalized or "untagged"
