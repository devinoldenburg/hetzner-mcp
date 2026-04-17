from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from hetzner_mcp.models import HttpResult
from hetzner_mcp.registry import OperationRegistry
from hetzner_mcp.server import HetznerMCPApplication


@dataclass
class _DummyClient:
    def execute(
        self,
        *,
        operation: Any,
        path_params: dict[str, Any],
        query_params: dict[str, Any],
        body: Any,
    ) -> HttpResult:
        return HttpResult(
            ok=True,
            status_code=200,
            headers={},
            data={
                "operation": operation.operation_id,
                "path_params": path_params,
                "query_params": query_params,
                "body": body,
            },
            raw_text="",
            request_url="https://example.invalid/request",
            retries=0,
        )


def _app() -> HetznerMCPApplication:
    registry = OperationRegistry.load(refresh_specs=False)
    return HetznerMCPApplication(registry=registry, client=_DummyClient())


def test_list_tools_includes_full_dynamic_set() -> None:
    app = _app()
    tools = app.list_tools()

    names = {tool.name for tool in tools}
    assert "list_api_operations" in names
    assert "get_api_operation_details" in names
    assert "search_api_operations" in names
    assert "list_api_categories" in names
    assert "get_api_category_details" in names
    assert "wait_for_action" in names
    assert "create_server" in names
    assert "create_storage_box" in names
    assert "guide_create_server" in names
    assert "guide_create_storage_box" in names

    category_count = len(app.registry.all_categories())
    helper_count = 6
    expected_tools = (app.registry.operation_count * 2) + category_count + helper_count
    assert len(tools) == expected_tools


def test_get_api_operation_details_helper() -> None:
    app = _app()
    result = asyncio.run(
        app.call_tool(
            name="get_api_operation_details",
            arguments={"operation_id": "create_server"},
        )
    )
    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["operation_id"] == "create_server"


def test_operation_call_routes_to_http_client() -> None:
    app = _app()
    result = asyncio.run(
        app.call_tool(
            name="get_action",
            arguments={"path": {"id": 123}},
        )
    )

    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["status_code"] == 200
    response = result.structuredContent["response"]
    assert response["operation"] == "get_action"
    assert response["path_params"] == {"id": 123}


def test_endpoint_guide_tool_returns_detailed_docs_payload() -> None:
    app = _app()
    result = asyncio.run(
        app.call_tool(
            name="guide_create_server",
            arguments={},
        )
    )

    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["operation"]["operation_id"] == "create_server"
    assert "what_it_is_for" in result.structuredContent
    assert result.structuredContent["execute_tool"] == "create_server"


def test_category_guide_tool_returns_category_docs_payload() -> None:
    app = _app()
    category = app.registry.get_category("cloud:servers")
    result = asyncio.run(
        app.call_tool(
            name=category.tool_name,
            arguments={},
        )
    )

    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["category"]["category_id"] == "cloud:servers"
    assert len(result.structuredContent["operations"]) >= 1
