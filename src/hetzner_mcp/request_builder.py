"""Build typed request fragments from operation definitions and tool arguments."""

from __future__ import annotations

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
