"""Dynamic MCP server exposing all Hetzner Cloud + Storage operations."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass
from typing import Any

import mcp.server.stdio
from mcp import types
from mcp.server import Server

from .config import load_runtime_config
from .errors import HetznerMCPError, ValidationError
from .http_client import HetznerHttpClient
from .models import OperationSpec
from .registry import OperationRegistry
from .request_builder import build_request

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    # Keep stdout clean for JSON-RPC frames.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.WARNING, handlers=[handler])


@dataclass(slots=True)
class HetznerMCPApplication:
    """Application service that powers tool listing and tool calls."""

    registry: OperationRegistry
    client: HetznerHttpClient

    def list_tools(self) -> list[types.Tool]:
        """Build helper + dynamic operation tools."""
        tools = [
            types.Tool(
                name="list_api_operations",
                description="List available Hetzner API operations with filters.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "api_domain": {"type": "string", "enum": ["cloud", "storage"]},
                        "tag": {"type": "string"},
                        "method": {
                            "type": "string",
                            "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                        },
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
                    },
                    "additionalProperties": False,
                },
            ),
            types.Tool(
                name="get_api_operation_details",
                description="Get full details and input schema for one operation.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "operation_id": {"type": "string"},
                    },
                    "required": ["operation_id"],
                    "additionalProperties": False,
                },
            ),
            types.Tool(
                name="search_api_operations",
                description="Search operations by keyword over id/path/summary/tags.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            ),
            types.Tool(
                name="wait_for_action",
                description=(
                    "Poll a Hetzner action until terminal status. "
                    "Use api_domain=cloud for /actions/{id} or api_domain=storage for "
                    "/storage_boxes/actions/{id}."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "api_domain": {"type": "string", "enum": ["cloud", "storage"]},
                        "action_id": {
                            "oneOf": [{"type": "integer"}, {"type": "string"}],
                            "description": "Hetzner action id",
                        },
                        "poll_interval_seconds": {
                            "type": "number",
                            "minimum": 0.2,
                            "default": 2,
                        },
                        "timeout_seconds": {
                            "type": "number",
                            "minimum": 1,
                            "default": 300,
                        },
                    },
                    "required": ["api_domain", "action_id"],
                    "additionalProperties": False,
                },
            ),
        ]

        for operation in self.registry.all_operations():
            tools.append(
                types.Tool(
                    name=operation.operation_id,
                    description=(
                        f"[{operation.api_domain}] {operation.method} {operation.path} - "
                        f"{operation.display_summary}"
                    ),
                    inputSchema=_operation_input_schema(operation),
                )
            )
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any] | None) -> types.CallToolResult:
        """Handle helper tools and dynamic operation tools."""
        try:
            if name == "list_api_operations":
                payload = self._helper_list_operations(arguments)
                return _success_result(payload)
            if name == "get_api_operation_details":
                payload = self._helper_get_operation_details(arguments)
                return _success_result(payload)
            if name == "search_api_operations":
                payload = self._helper_search_operations(arguments)
                return _success_result(payload)
            if name == "wait_for_action":
                payload = await self._helper_wait_for_action(arguments)
                return _success_result(payload)

            operation = self.registry.get(name)
            return await self._execute_operation(operation=operation, arguments=arguments)
        except HetznerMCPError as exc:
            return _error_result(exc.to_dict())
        except Exception as exc:  # pragma: no cover
            logger.exception("Unhandled error while processing tool call")
            return _error_result(
                {
                    "code": "internal_error",
                    "message": str(exc),
                }
            )

    def _helper_list_operations(self, arguments: dict[str, Any] | None) -> dict[str, Any]:
        args = arguments or {}
        if not isinstance(args, dict):
            raise ValidationError(code="invalid_arguments", message="Arguments must be an object")

        api_domain = args.get("api_domain")
        if api_domain is not None and api_domain not in {"cloud", "storage"}:
            raise ValidationError(
                code="invalid_api_domain", message="api_domain must be cloud or storage"
            )

        tag = _optional_string(args.get("tag"))
        method = _optional_string(args.get("method"))
        query = _optional_string(args.get("query"))
        limit = _optional_int(args.get("limit"), default=100)

        operations = self.registry.list_filtered(
            api_domain=api_domain,
            tag=tag,
            method=method,
            query=query,
            limit=limit,
        )
        return {
            "total": len(operations),
            "counts_by_domain": self.registry.counts_by_domain(),
            "counts_by_tag": self.registry.counts_by_tag(),
            "operations": [_operation_summary(op) for op in operations],
        }

    def _helper_get_operation_details(self, arguments: dict[str, Any] | None) -> dict[str, Any]:
        args = arguments or {}
        if not isinstance(args, dict):
            raise ValidationError(code="invalid_arguments", message="Arguments must be an object")
        operation_id = args.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            raise ValidationError(
                code="missing_operation_id",
                message="operation_id is required",
            )
        operation = self.registry.get(operation_id)
        return {
            **_operation_summary(operation),
            "description": operation.description,
            "input_schema": _operation_input_schema(operation),
            "parameters": [
                {
                    "name": p.name,
                    "in": p.location,
                    "required": p.required,
                    "description": p.description,
                    "schema": p.schema,
                }
                for p in operation.parameters
            ],
            "request_body": (
                {
                    "required": operation.request_body.required,
                    "description": operation.request_body.description,
                    "schema": operation.request_body.schema,
                }
                if operation.request_body
                else None
            ),
        }

    def _helper_search_operations(self, arguments: dict[str, Any] | None) -> dict[str, Any]:
        args = arguments or {}
        if not isinstance(args, dict):
            raise ValidationError(code="invalid_arguments", message="Arguments must be an object")
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValidationError(code="missing_query", message="query is required")
        limit = _optional_int(args.get("limit"), default=50)

        operations = self.registry.list_filtered(query=query, limit=limit)
        return {
            "query": query,
            "total": len(operations),
            "operations": [_operation_summary(op) for op in operations],
        }

    async def _helper_wait_for_action(self, arguments: dict[str, Any] | None) -> dict[str, Any]:
        args = arguments or {}
        if not isinstance(args, dict):
            raise ValidationError(code="invalid_arguments", message="Arguments must be an object")

        api_domain = args.get("api_domain")
        if api_domain not in {"cloud", "storage"}:
            raise ValidationError(
                code="invalid_api_domain", message="api_domain must be cloud or storage"
            )

        action_id = args.get("action_id")
        if action_id is None:
            raise ValidationError(code="missing_action_id", message="action_id is required")

        poll_interval = float(args.get("poll_interval_seconds", 2))
        timeout_seconds = float(args.get("timeout_seconds", 300))
        deadline = time.monotonic() + timeout_seconds

        operation_id = "get_action" if api_domain == "cloud" else "get_storage_boxes_action"
        operation = self.registry.get(operation_id)
        action_status: str | None = None
        history: list[dict[str, Any]] = []

        while time.monotonic() < deadline:
            step_result = await self._execute_operation(
                operation=operation,
                arguments={
                    "path": {"id": action_id},
                },
            )
            structured = step_result.structuredContent or {}
            history.append(structured)

            if step_result.isError:
                return {
                    "finished": True,
                    "success": False,
                    "reason": "poll_error",
                    "last_result": structured,
                    "history_count": len(history),
                }

            payload = structured.get("response")
            if isinstance(payload, dict):
                action_obj = payload.get("action")
                if isinstance(action_obj, dict):
                    status = action_obj.get("status")
                    if isinstance(status, str):
                        action_status = status
                    if action_status in {"success", "error", "failed"}:
                        return {
                            "finished": True,
                            "success": action_status == "success",
                            "status": action_status,
                            "action": action_obj,
                            "history_count": len(history),
                        }

            await asyncio.sleep(max(0.2, poll_interval))

        return {
            "finished": False,
            "success": False,
            "reason": "timeout",
            "status": action_status,
            "history_count": len(history),
            "timeout_seconds": timeout_seconds,
        }

    async def _execute_operation(
        self,
        *,
        operation: OperationSpec,
        arguments: dict[str, Any] | None,
    ) -> types.CallToolResult:
        request = build_request(operation, arguments)

        result = await asyncio.to_thread(
            self.client.execute,
            operation=operation,
            path_params=request.path_params,
            query_params=request.query_params,
            body=request.body,
        )

        payload = {
            "operation": _operation_summary(operation),
            "request": {
                "url": result.request_url,
                "method": operation.method,
                "retries": result.retries,
                "path": request.path_params,
                "query": request.query_params,
                "body": request.body,
            },
            "status_code": result.status_code,
            "headers": result.headers,
            "response": result.data if result.data is not None else result.raw_text,
        }

        if result.ok:
            return _success_result(payload)

        error_payload = _normalize_api_error(
            result_data=result.data, status_code=result.status_code
        )
        return _error_result(
            {
                **error_payload,
                "context": payload,
            }
        )


def _operation_input_schema(operation: OperationSpec) -> dict[str, Any]:
    path_parameters = [p for p in operation.parameters if p.location == "path"]
    query_parameters = [p for p in operation.parameters if p.location == "query"]

    properties: dict[str, Any] = {}
    required: list[str] = []

    if path_parameters:
        path_props: dict[str, Any] = {}
        path_required: list[str] = []
        for parameter in path_parameters:
            path_props[parameter.name] = _schema_from_parameter(parameter)
            if parameter.required:
                path_required.append(parameter.name)
        path_schema: dict[str, Any] = {
            "type": "object",
            "properties": path_props,
            "additionalProperties": False,
        }
        if path_required:
            path_schema["required"] = path_required
        properties["path"] = path_schema
        required.append("path")

    if query_parameters:
        query_props: dict[str, Any] = {}
        query_required: list[str] = []
        for parameter in query_parameters:
            query_props[parameter.name] = _schema_from_parameter(parameter)
            if parameter.required:
                query_required.append(parameter.name)
        query_schema: dict[str, Any] = {
            "type": "object",
            "properties": query_props,
            "additionalProperties": True,
        }
        if query_required:
            query_schema["required"] = query_required
        properties["query"] = query_schema

    if operation.request_body is not None:
        if operation.request_body.schema is not None:
            properties["body"] = operation.request_body.schema
        else:
            properties["body"] = {"type": "object", "additionalProperties": True}
        if operation.request_body.required:
            required.append("body")

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = sorted(set(required))
    return schema


def _schema_from_parameter(parameter: Any) -> dict[str, Any]:
    schema = parameter.schema if isinstance(parameter.schema, dict) else {"type": "string"}
    output = dict(schema)
    if parameter.description and "description" not in output:
        output["description"] = parameter.description
    return output


def _operation_summary(operation: OperationSpec) -> dict[str, Any]:
    return {
        "operation_id": operation.operation_id,
        "api_domain": operation.api_domain,
        "method": operation.method,
        "path": operation.path,
        "tag": operation.primary_tag,
        "summary": operation.display_summary,
    }


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _optional_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def _normalize_api_error(*, result_data: Any, status_code: int) -> dict[str, Any]:
    if isinstance(result_data, dict):
        error_obj = result_data.get("error")
        if isinstance(error_obj, dict):
            return {
                "code": str(error_obj.get("code", "api_error")),
                "message": str(error_obj.get("message", "Hetzner API request failed")),
                "details": error_obj.get("details"),
                "status_code": status_code,
            }

    if status_code == 0:
        return {
            "code": "network_error",
            "message": "Network request failed before receiving an HTTP response",
            "status_code": status_code,
        }

    return {
        "code": "api_error",
        "message": f"Hetzner API request failed with status {status_code}",
        "status_code": status_code,
    }


def _success_result(payload: dict[str, Any]) -> types.CallToolResult:
    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=json.dumps(payload, indent=2),
            )
        ],
        structuredContent=payload,
        isError=False,
    )


def _error_result(payload: dict[str, Any]) -> types.CallToolResult:
    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=json.dumps({"error": payload}, indent=2),
            )
        ],
        structuredContent={"error": payload},
        isError=True,
    )


def create_server(*, refresh_specs: bool = False) -> Server[Any]:
    """Create and configure the dynamic MCP server instance."""
    config = load_runtime_config()
    registry = OperationRegistry.load(refresh_specs=refresh_specs)
    app = HetznerMCPApplication(registry=registry, client=HetznerHttpClient(config=config))

    server: Server[Any] = Server(
        name="hetzner-mcp",
        version="0.1.0",
        instructions=(
            "Hetzner MCP server with full Cloud + Storage API coverage. "
            "Use list_api_operations/search_api_operations to discover operations, "
            "then call operation tools directly by operationId."
        ),
    )

    @server.list_tools()  # type: ignore[untyped-decorator,no-untyped-call]
    async def _list_tools() -> list[types.Tool]:
        return app.list_tools()

    @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        return await app.call_tool(name=name, arguments=arguments)

    return server


async def run_server(*, refresh_specs: bool = False) -> None:
    """Run the MCP server over stdio transport."""
    server = create_server(refresh_specs=refresh_specs)
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Entry point for console script."""
    _configure_logging()
    refresh_specs = bool(int(sys.argv[1])) if len(sys.argv) > 1 and sys.argv[1].isdigit() else False
    asyncio.run(run_server(refresh_specs=refresh_specs))


if __name__ == "__main__":
    main()
