from __future__ import annotations

import pytest

from hetzner_mcp.errors import ValidationError
from hetzner_mcp.models import OperationSpec, ParameterSpec, RequestBodySpec
from hetzner_mcp.request_builder import build_request


def _sample_operation() -> OperationSpec:
    return OperationSpec(
        operation_id="sample",
        api_domain="cloud",
        method="POST",
        path="/servers/{id}",
        tags=("Servers",),
        summary="Sample",
        description=None,
        parameters=(
            ParameterSpec(
                name="id",
                location="path",
                required=True,
                schema={"type": "integer"},
            ),
            ParameterSpec(
                name="dry_run",
                location="query",
                required=False,
                schema={"type": "boolean"},
            ),
        ),
        request_body=RequestBodySpec(required=True, schema={"type": "object"}),
    )


def test_build_request_success() -> None:
    built = build_request(
        _sample_operation(),
        {
            "path": {"id": 123},
            "query": {"dry_run": True},
            "body": {"name": "example"},
        },
    )

    assert built.path_params == {"id": 123}
    assert built.query_params == {"dry_run": True}
    assert built.body == {"name": "example"}


def test_build_request_missing_required_path() -> None:
    with pytest.raises(ValidationError) as exc_info:
        build_request(_sample_operation(), {"body": {"name": "x"}})
    assert exc_info.value.code == "missing_path_param"


def test_build_request_missing_required_body() -> None:
    with pytest.raises(ValidationError) as exc_info:
        build_request(_sample_operation(), {"path": {"id": 123}})
    assert exc_info.value.code == "missing_body"


def test_build_request_disallow_unexpected_body() -> None:
    operation = OperationSpec(
        operation_id="no_body",
        api_domain="cloud",
        method="GET",
        path="/servers",
        tags=("Servers",),
        summary=None,
        description=None,
        parameters=(),
        request_body=None,
    )

    with pytest.raises(ValidationError) as exc_info:
        build_request(operation, {"body": {"x": 1}})
    assert exc_info.value.code == "unexpected_body"


def test_build_request_rejects_unknown_query_parameters() -> None:
    with pytest.raises(ValidationError) as exc_info:
        build_request(
            _sample_operation(),
            {
                "path": {"id": 123},
                "query": {"surprise": True},
                "body": {"name": "example"},
            },
        )
    assert exc_info.value.code == "unknown_query_param"


def test_build_request_rejects_wrong_path_type() -> None:
    with pytest.raises(ValidationError) as exc_info:
        build_request(_sample_operation(), {"path": {"id": "123"}, "body": {"name": "x"}})
    assert exc_info.value.code == "invalid_type"


def test_build_request_rejects_unknown_top_level_arguments() -> None:
    with pytest.raises(ValidationError) as exc_info:
        build_request(
            _sample_operation(),
            {
                "path": {"id": 123},
                "body": {"name": "x"},
                "surprise": "value",
            },
        )
    assert exc_info.value.code == "unknown_argument"


def test_build_request_validates_body_required_properties() -> None:
    operation = OperationSpec(
        operation_id="typed_body",
        api_domain="cloud",
        method="POST",
        path="/servers",
        tags=("Servers",),
        summary="Typed body",
        description=None,
        parameters=(),
        request_body=RequestBodySpec(
            required=True,
            schema={
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "minLength": 3},
                    "labels": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "additionalProperties": False,
            },
        ),
    )

    with pytest.raises(ValidationError) as exc_info:
        build_request(operation, {"body": {"labels": {"env": "prod"}}})
    assert exc_info.value.code == "missing_required_property"


def test_build_request_rejects_body_extra_properties() -> None:
    operation = OperationSpec(
        operation_id="strict_body",
        api_domain="cloud",
        method="POST",
        path="/servers",
        tags=("Servers",),
        summary="Strict body",
        description=None,
        parameters=(),
        request_body=RequestBodySpec(
            required=True,
            schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "additionalProperties": False,
            },
        ),
    )

    with pytest.raises(ValidationError) as exc_info:
        build_request(operation, {"body": {"name": "ok", "token": "secret"}})
    assert exc_info.value.code == "unknown_property"
