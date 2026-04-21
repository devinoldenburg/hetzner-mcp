"""Build typed request fragments from operation definitions and tool arguments."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import ValidationError
from .models import BuiltRequest, OperationSpec


def build_request(operation: OperationSpec, arguments: dict[str, Any] | None) -> BuiltRequest:
    """Build request data from operation + arguments.

    Expected input shape:
    {
      "path": { ... },
      "query": { ... },
      "body": { ... } | any
    }
    """
    args = arguments or {}

    if not isinstance(args, dict):
        raise ValidationError(
            code="invalid_arguments",
            message="Tool arguments must be an object",
        )

    unknown_argument_keys = sorted(key for key in args if key not in {"path", "query", "body"})
    if unknown_argument_keys:
        raise ValidationError(
            code="unknown_argument",
            message=(
                "Unsupported top-level tool arguments: "
                + ", ".join(str(key) for key in unknown_argument_keys)
            ),
            details={"unknown_arguments": unknown_argument_keys},
        )

    path_params = args.get("path", {})
    query_params = args.get("query", {})
    body = args.get("body", None)

    if path_params is None:
        path_params = {}
    if query_params is None:
        query_params = {}

    if not isinstance(path_params, dict):
        raise ValidationError(
            code="invalid_path_params",
            message="'path' must be an object",
        )
    if not isinstance(query_params, dict):
        raise ValidationError(
            code="invalid_query_params",
            message="'query' must be an object",
        )

    _validate_required_parameters(
        operation=operation, path_params=path_params, query_params=query_params
    )
    _validate_parameter_shapes(
        operation=operation,
        path_params=path_params,
        query_params=query_params,
    )
    _validate_body(operation=operation, body=body)

    return BuiltRequest(path_params=path_params, query_params=query_params, body=body)


def _validate_required_parameters(
    *,
    operation: OperationSpec,
    path_params: dict[str, Any],
    query_params: dict[str, Any],
) -> None:
    for parameter in operation.parameters:
        if not parameter.required:
            continue
        if parameter.location == "path":
            if parameter.name not in path_params:
                raise ValidationError(
                    code="missing_path_param",
                    message=f"Missing required path parameter: {parameter.name}",
                )
        elif parameter.location == "query":
            if parameter.name not in query_params:
                raise ValidationError(
                    code="missing_query_param",
                    message=f"Missing required query parameter: {parameter.name}",
                )


def _validate_body(*, operation: OperationSpec, body: Any) -> None:
    if operation.request_body is None:
        if body is not None:
            raise ValidationError(
                code="unexpected_body",
                message="This operation does not accept a JSON body",
            )
        return

    if operation.request_body.required and body is None:
        raise ValidationError(
            code="missing_body",
            message="This operation requires a JSON body in 'body'",
        )

    if operation.request_body.schema is not None and body is not None:
        _validate_schema(value=body, schema=operation.request_body.schema, location="body")


def _validate_parameter_shapes(
    *,
    operation: OperationSpec,
    path_params: dict[str, Any],
    query_params: dict[str, Any],
) -> None:
    allowed_path_names = {
        parameter.name for parameter in operation.parameters if parameter.location == "path"
    }
    allowed_query_names = {
        parameter.name for parameter in operation.parameters if parameter.location == "query"
    }
    for key in path_params:
        if key not in allowed_path_names:
            raise ValidationError(
                code="unknown_path_param",
                message=f"Unknown path parameter: {key}",
                details={"parameter": key},
            )
    for key in query_params:
        if key not in allowed_query_names:
            raise ValidationError(
                code="unknown_query_param",
                message=f"Unknown query parameter: {key}",
                details={"parameter": key},
            )

    for parameter in operation.parameters:
        if parameter.location == "path" and parameter.name in path_params:
            _validate_schema(
                value=path_params[parameter.name],
                schema=parameter.schema,
                location=f"path.{parameter.name}",
            )
        elif parameter.location == "query" and parameter.name in query_params:
            _validate_schema(
                value=query_params[parameter.name],
                schema=parameter.schema,
                location=f"query.{parameter.name}",
            )


def _validate_schema(*, value: Any, schema: Any, location: str) -> None:
    if not isinstance(schema, dict) or not schema:
        return

    if schema.get("nullable") is True and value is None:
        return

    one_of = schema.get("oneOf")
    if isinstance(one_of, list) and one_of:
        _validate_union(value=value, variants=one_of, location=location, keyword="oneOf")
        return

    any_of = schema.get("anyOf")
    if isinstance(any_of, list) and any_of:
        _validate_union(value=value, variants=any_of, location=location, keyword="anyOf")
        return

    schema_type = schema.get("type")
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values and value not in enum_values:
        raise ValidationError(
            code="invalid_enum_value",
            message=f"{location} must be one of {enum_values}",
            details={"location": location, "allowed": enum_values},
        )

    if isinstance(schema_type, list):
        matched = False
        errors: list[str] = []
        for candidate in schema_type:
            candidate_schema = dict(schema)
            candidate_schema["type"] = candidate
            try:
                _validate_schema(value=value, schema=candidate_schema, location=location)
                matched = True
                break
            except ValidationError as exc:
                errors.append(exc.message)
        if not matched:
            raise ValidationError(
                code="invalid_type",
                message=f"{location} does not match any allowed type",
                details={"location": location, "errors": errors},
            )
        return

    if schema_type == "object":
        _validate_object_schema(value=value, schema=schema, location=location)
        return
    if schema_type == "array":
        _validate_array_schema(value=value, schema=schema, location=location)
        return
    if schema_type == "string":
        _validate_string_schema(value=value, schema=schema, location=location)
        return
    if schema_type == "integer":
        _validate_number_schema(value=value, schema=schema, location=location, integer_only=True)
        return
    if schema_type == "number":
        _validate_number_schema(value=value, schema=schema, location=location, integer_only=False)
        return
    if schema_type == "boolean":
        if not isinstance(value, bool):
            raise ValidationError(
                code="invalid_type",
                message=f"{location} must be a boolean",
                details={"location": location},
            )


def _validate_union(*, value: Any, variants: list[Any], location: str, keyword: str) -> None:
    errors: list[str] = []
    matches = 0
    for variant in variants:
        try:
            _validate_schema(value=value, schema=variant, location=location)
            matches += 1
        except ValidationError as exc:
            errors.append(exc.message)

    if keyword == "oneOf" and matches == 1:
        return
    if keyword == "anyOf" and matches >= 1:
        return

    raise ValidationError(
        code="invalid_schema_variant",
        message=f"{location} does not satisfy {keyword}",
        details={"location": location, "errors": errors},
    )


def _validate_object_schema(*, value: Any, schema: dict[str, Any], location: str) -> None:
    if not isinstance(value, Mapping):
        raise ValidationError(
            code="invalid_type",
            message=f"{location} must be an object",
            details={"location": location},
        )

    properties = schema.get("properties")
    properties_map = properties if isinstance(properties, dict) else {}
    required = schema.get("required")
    required_names = [str(item) for item in required] if isinstance(required, list) else []
    for name in required_names:
        if name not in value:
            raise ValidationError(
                code="missing_required_property",
                message=f"{location}.{name} is required",
                details={"location": location, "property": name},
            )

    additional = schema.get("additionalProperties", True)
    if additional is False:
        unknown = [key for key in value if key not in properties_map]
        if unknown:
            unknown_names = ", ".join(sorted(str(key) for key in unknown))
            raise ValidationError(
                code="unknown_property",
                message=f"{location} contains unsupported properties: {unknown_names}",
                details={"location": location, "unknown": sorted(str(key) for key in unknown)},
            )

    for key, item in value.items():
        child_location = f"{location}.{key}"
        if key in properties_map and isinstance(properties_map[key], dict):
            _validate_schema(value=item, schema=properties_map[key], location=child_location)
        elif isinstance(additional, dict):
            _validate_schema(value=item, schema=additional, location=child_location)


def _validate_array_schema(*, value: Any, schema: dict[str, Any], location: str) -> None:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValidationError(
            code="invalid_type",
            message=f"{location} must be an array",
            details={"location": location},
        )

    items = list(value)
    min_items = schema.get("minItems")
    max_items = schema.get("maxItems")
    if isinstance(min_items, int) and len(items) < min_items:
        raise ValidationError(
            code="too_few_items",
            message=f"{location} must contain at least {min_items} items",
            details={"location": location, "min_items": min_items},
        )
    if isinstance(max_items, int) and len(items) > max_items:
        raise ValidationError(
            code="too_many_items",
            message=f"{location} must contain at most {max_items} items",
            details={"location": location, "max_items": max_items},
        )

    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(items):
            _validate_schema(value=item, schema=item_schema, location=f"{location}[{index}]")


def _validate_string_schema(*, value: Any, schema: dict[str, Any], location: str) -> None:
    if not isinstance(value, str):
        raise ValidationError(
            code="invalid_type",
            message=f"{location} must be a string",
            details={"location": location},
        )

    min_length = schema.get("minLength")
    max_length = schema.get("maxLength")
    pattern = schema.get("pattern")
    if isinstance(min_length, int) and len(value) < min_length:
        raise ValidationError(
            code="string_too_short",
            message=f"{location} must be at least {min_length} characters",
            details={"location": location, "min_length": min_length},
        )
    if isinstance(max_length, int) and len(value) > max_length:
        raise ValidationError(
            code="string_too_long",
            message=f"{location} must be at most {max_length} characters",
            details={"location": location, "max_length": max_length},
        )
    if isinstance(pattern, str):
        if re.fullmatch(pattern, value) is None:
            raise ValidationError(
                code="pattern_mismatch",
                message=f"{location} does not match required pattern",
                details={"location": location, "pattern": pattern},
            )


def _validate_number_schema(
    *, value: Any, schema: dict[str, Any], location: str, integer_only: bool
) -> None:
    if isinstance(value, bool):
        raise ValidationError(
            code="invalid_type",
            message=f"{location} must be a {'integer' if integer_only else 'number'}",
            details={"location": location},
        )
    if integer_only:
        if not isinstance(value, int):
            raise ValidationError(
                code="invalid_type",
                message=f"{location} must be an integer",
                details={"location": location},
            )
        numeric_value = float(value)
    else:
        if not isinstance(value, (int, float)):
            raise ValidationError(
                code="invalid_type",
                message=f"{location} must be a number",
                details={"location": location},
            )
        numeric_value = float(value)

    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    exclusive_minimum = schema.get("exclusiveMinimum")
    exclusive_maximum = schema.get("exclusiveMaximum")
    if isinstance(minimum, (int, float)) and numeric_value < float(minimum):
        raise ValidationError(
            code="number_too_small",
            message=f"{location} must be >= {minimum}",
            details={"location": location, "minimum": minimum},
        )
    if isinstance(maximum, (int, float)) and numeric_value > float(maximum):
        raise ValidationError(
            code="number_too_large",
            message=f"{location} must be <= {maximum}",
            details={"location": location, "maximum": maximum},
        )
    if isinstance(exclusive_minimum, (int, float)) and numeric_value <= float(exclusive_minimum):
        raise ValidationError(
            code="number_too_small",
            message=f"{location} must be > {exclusive_minimum}",
            details={"location": location, "exclusive_minimum": exclusive_minimum},
        )
    if isinstance(exclusive_maximum, (int, float)) and numeric_value >= float(exclusive_maximum):
        raise ValidationError(
            code="number_too_large",
            message=f"{location} must be < {exclusive_maximum}",
            details={"location": location, "exclusive_maximum": exclusive_maximum},
        )
