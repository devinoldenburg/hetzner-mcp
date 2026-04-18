"""Dynamic MCP server exposing all Hetzner Cloud + Storage operations."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import mcp.server.stdio
from mcp import types
from mcp.server import Server

from .config import get_project_selection, load_runtime_config, project_profiles, set_active_project
from .errors import HetznerMCPError, ValidationError
from .http_client import HetznerHttpClient
from .models import CategorySpec, OperationSpec
from .registry import OperationRegistry
from .request_builder import build_request

logger = logging.getLogger(__name__)

GUIDE_PREFIX = "guide_"
CATEGORY_GUIDE_PREFIX = "category_guide_"
DOCS_TO_EXEC_MAX_INTERACTIONS = 40
EXECUTION_RELEVANCE_MAX_INTERACTIONS = 120


@dataclass(slots=True)
class OperationUsageState:
    """Usage-tracking state for one operation within one session."""

    last_docs_event: int | None = None
    last_execute_event: int | None = None
    execute_count: int = 0


@dataclass(slots=True)
class SessionUsageState:
    """Per-session usage tracking for docs-first policy."""

    event_counter: int = 0
    operations: dict[str, OperationUsageState] = field(default_factory=dict)


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
    session_usage: dict[str, SessionUsageState] = field(default_factory=dict)

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
                name="list_api_categories",
                description=(
                    "List API documentation categories (resource groups/tags) with detailed "
                    "descriptions and operation coverage."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "api_domain": {"type": "string", "enum": ["cloud", "storage"]},
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
                    },
                    "additionalProperties": False,
                },
            ),
            types.Tool(
                name="get_api_category_details",
                description=(
                    "Get full category documentation including what it is for and all endpoints "
                    "inside it."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "category_id": {
                            "type": "string",
                            "description": "Format: <api_domain>:<slug>, example cloud:servers",
                        }
                    },
                    "required": ["category_id"],
                    "additionalProperties": False,
                },
            ),
            types.Tool(
                name="list_api_projects",
                description=(
                    "List configured API project profiles, active selection, and guidance so "
                    "agents can pick the right credentials context."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            types.Tool(
                name="set_active_api_project",
                description=(
                    "Set the active API project profile for this server runtime and persisted "
                    "local config."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Configured project profile name",
                        }
                    },
                    "required": ["project"],
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
                        f"{operation.display_summary}. "
                        f"Docs: {_docs_excerpt(operation.docs_text, max_chars=180)}"
                    ),
                    inputSchema=_operation_input_schema(operation),
                )
            )
            tools.append(
                types.Tool(
                    name=f"{GUIDE_PREFIX}{operation.operation_id}",
                    description=(
                        f"Detailed endpoint guide for {operation.operation_id}: purpose, usage, "
                        "arguments, and docs text."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                )
            )

        for category in self.registry.all_categories():
            tools.append(
                types.Tool(
                    name=category.tool_name,
                    description=(
                        f"Detailed category guide for {category.name} ({category.api_domain}): "
                        "what this category is for and all endpoint capabilities."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                )
            )
        return tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        *,
        session_key: str | None = None,
    ) -> types.CallToolResult:
        """Handle helper tools and dynamic operation tools."""
        normalized_session = self._normalize_session_key(session_key)
        event_id = self._next_session_event(normalized_session)

        try:
            if name == "list_api_operations":
                payload = self._helper_list_operations(arguments)
                return _success_result(payload)
            if name == "get_api_operation_details":
                payload = self._helper_get_operation_details(arguments)
                operation_id = payload.get("operation_id")
                if isinstance(operation_id, str):
                    payload["docs_policy"] = self._mark_docs_seen(
                        session_key=normalized_session,
                        operation_id=operation_id,
                        event_id=event_id,
                    )
                return _success_result(payload)
            if name == "search_api_operations":
                payload = self._helper_search_operations(arguments)
                return _success_result(payload)
            if name == "list_api_categories":
                payload = self._helper_list_categories(arguments)
                return _success_result(payload)
            if name == "get_api_category_details":
                payload = self._helper_get_category_details(arguments)
                return _success_result(payload)
            if name == "list_api_projects":
                payload = self._helper_list_projects(arguments)
                return _success_result(payload)
            if name == "set_active_api_project":
                payload = self._helper_set_active_project(arguments)
                return _success_result(payload)
            if name == "wait_for_action":
                payload = await self._helper_wait_for_action(arguments)
                return _success_result(payload)

            if name.startswith(GUIDE_PREFIX):
                operation_id = name[len(GUIDE_PREFIX) :]
                operation = self.registry.get(operation_id)
                payload = self._build_operation_guide(operation)
                payload["docs_policy"] = self._mark_docs_seen(
                    session_key=normalized_session,
                    operation_id=operation.operation_id,
                    event_id=event_id,
                )
                return _success_result(payload)

            if name.startswith(CATEGORY_GUIDE_PREFIX):
                category = self.registry.get_category_by_tool_name(name)
                return _success_result(self._build_category_guide(category))

            operation = self.registry.get(name)
            self._assert_operation_unlocked(
                session_key=normalized_session,
                operation_id=operation.operation_id,
                event_id=event_id,
            )
            result = await self._execute_operation(operation=operation, arguments=arguments)
            if not result.isError:
                self._mark_operation_executed(
                    session_key=normalized_session,
                    operation_id=operation.operation_id,
                    event_id=event_id,
                )
            return result
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
            "operations": [
                {
                    **_operation_summary(op),
                    "endpoint_guide_tool": f"{GUIDE_PREFIX}{op.operation_id}",
                }
                for op in operations
            ],
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
        category_tool_name: str | None = None
        try:
            category = self.registry.get_category(
                f"{operation.api_domain}:{_slug_from_tag(operation.primary_tag)}"
            )
            category_tool_name = category.tool_name
        except HetznerMCPError:
            category_tool_name = None
        return {
            **_operation_summary(operation),
            "description": operation.description,
            "docs_text": operation.docs_text,
            "input_schema": _operation_input_schema(operation),
            "endpoint_guide_tool": f"{GUIDE_PREFIX}{operation.operation_id}",
            "category_guide_tool": category_tool_name,
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
            "operations": [
                {
                    **_operation_summary(op),
                    "endpoint_guide_tool": f"{GUIDE_PREFIX}{op.operation_id}",
                }
                for op in operations
            ],
        }

    def _helper_list_categories(self, arguments: dict[str, Any] | None) -> dict[str, Any]:
        args = arguments or {}
        if not isinstance(args, dict):
            raise ValidationError(code="invalid_arguments", message="Arguments must be an object")

        api_domain = args.get("api_domain")
        if api_domain is not None and api_domain not in {"cloud", "storage"}:
            raise ValidationError(
                code="invalid_api_domain", message="api_domain must be cloud or storage"
            )

        query = _optional_string(args.get("query"))
        limit = _optional_int(args.get("limit"), default=100)

        categories = self.registry.all_categories()
        if api_domain:
            categories = [category for category in categories if category.api_domain == api_domain]
        if query:
            query_lower = query.lower()
            categories = [
                category
                for category in categories
                if query_lower in category.name.lower()
                or query_lower in category.slug.lower()
                or query_lower in (category.description or "").lower()
            ]

        categories = categories[: max(limit, 1)]
        return {
            "total": len(categories),
            "categories": [
                {
                    "category_id": category.category_id,
                    "api_domain": category.api_domain,
                    "name": category.name,
                    "slug": category.slug,
                    "operation_count": len(category.operation_ids),
                    "description": category.description,
                    "description_excerpt": _docs_excerpt(category.description or ""),
                    "category_guide_tool": category.tool_name,
                }
                for category in categories
            ],
        }

    def _helper_get_category_details(self, arguments: dict[str, Any] | None) -> dict[str, Any]:
        args = arguments or {}
        if not isinstance(args, dict):
            raise ValidationError(code="invalid_arguments", message="Arguments must be an object")

        category_id = args.get("category_id")
        if not isinstance(category_id, str) or not category_id:
            raise ValidationError(code="missing_category_id", message="category_id is required")

        category = self.registry.get_category(category_id)
        return self._build_category_guide(category)

    def _helper_list_projects(self, arguments: dict[str, Any] | None) -> dict[str, Any]:
        args = arguments or {}
        if not isinstance(args, dict):
            raise ValidationError(code="invalid_arguments", message="Arguments must be an object")

        profiles = project_profiles()
        selection = get_project_selection()
        agent_message = _project_agent_message_for_server(selection=selection, profiles=profiles)
        return {
            "active_project": {
                "name": selection.get("name"),
                "source": selection.get("source"),
                "exists": selection.get("exists"),
            },
            "available_projects": [profile["name"] for profile in profiles],
            "projects": profiles,
            "message_for_agent": agent_message,
            "selection_message": selection.get("message"),
        }

    def _helper_set_active_project(self, arguments: dict[str, Any] | None) -> dict[str, Any]:
        args = arguments or {}
        if not isinstance(args, dict):
            raise ValidationError(code="invalid_arguments", message="Arguments must be an object")

        project = args.get("project")
        if not isinstance(project, str) or not project.strip():
            raise ValidationError(code="missing_project", message="project is required")

        profiles = project_profiles()
        available = {profile["name"] for profile in profiles}
        if project not in available:
            raise ValidationError(
                code="unknown_project",
                message=f"Unknown project '{project}'. Call list_api_projects first.",
                details={"available_projects": sorted(available)},
            )

        set_active_project(project)
        self.client.config = load_runtime_config()

        payload = self._helper_list_projects({})
        payload["updated"] = True
        payload["message"] = (
            f"Active project switched to '{project}'. New API calls now use this project's "
            "credentials unless overridden by environment variables."
        )
        return payload

    def _build_operation_guide(self, operation: OperationSpec) -> dict[str, Any]:
        path_parameters = [
            parameter for parameter in operation.parameters if parameter.location == "path"
        ]
        query_parameters = [
            parameter for parameter in operation.parameters if parameter.location == "query"
        ]

        return {
            "operation": _operation_summary(operation),
            "purpose": operation.display_summary,
            "what_it_is_for": _derive_operation_purpose(operation),
            "docs_text": operation.docs_text,
            "required_path_parameters": [
                parameter.name for parameter in path_parameters if parameter.required
            ],
            "path_parameters": [_parameter_doc(parameter) for parameter in path_parameters],
            "query_parameters": [_parameter_doc(parameter) for parameter in query_parameters],
            "request_body": (
                {
                    "required": operation.request_body.required,
                    "description": operation.request_body.description,
                    "schema": operation.request_body.schema,
                    "example": _example_body(operation.request_body.schema),
                }
                if operation.request_body
                else None
            ),
            "example_tool_arguments": _example_tool_arguments(operation),
            "execute_tool": operation.operation_id,
        }

    def _build_category_guide(self, category: CategorySpec) -> dict[str, Any]:
        operations = self.registry.operations_for_category(category.category_id)
        return {
            "category": {
                "category_id": category.category_id,
                "api_domain": category.api_domain,
                "name": category.name,
                "slug": category.slug,
                "description": category.description,
                "description_excerpt": _docs_excerpt(category.description or ""),
                "operation_count": len(operations),
                "category_guide_tool": category.tool_name,
            },
            "what_it_is_for": _derive_category_purpose(category),
            "operations": [
                {
                    **_operation_summary(operation),
                    "docs_excerpt": _docs_excerpt(operation.docs_text),
                    "execute_tool": operation.operation_id,
                    "endpoint_guide_tool": f"{GUIDE_PREFIX}{operation.operation_id}",
                }
                for operation in operations
            ],
        }

    def _mark_docs_seen(
        self, *, session_key: str, operation_id: str, event_id: int
    ) -> dict[str, Any]:
        operation_state = self._get_or_create_operation_state(session_key, operation_id)
        operation_state.last_docs_event = event_id

        return {
            "required": True,
            "policy": "context_usage",
            "operation_id": operation_id,
            "session_scope": session_key,
            "granted_at_event": event_id,
            "docs_to_execute_max_interactions": DOCS_TO_EXEC_MAX_INTERACTIONS,
            "execution_relevance_max_interactions": EXECUTION_RELEVANCE_MAX_INTERACTIONS,
            "message": (
                "Endpoint docs acknowledged. Execution is allowed while context remains fresh "
                "based on interaction distance, not wall-clock time."
            ),
        }

    def _mark_operation_executed(
        self, *, session_key: str, operation_id: str, event_id: int
    ) -> None:
        operation_state = self._get_or_create_operation_state(session_key, operation_id)
        operation_state.last_execute_event = event_id
        operation_state.execute_count += 1

    def _assert_operation_unlocked(
        self,
        *,
        session_key: str,
        operation_id: str,
        event_id: int,
    ) -> None:
        operation_state = self._get_or_create_operation_state(session_key, operation_id)
        guide_tool = f"{GUIDE_PREFIX}{operation_id}"

        if operation_state.execute_count > 0 and operation_state.last_execute_event is not None:
            gap_since_execute = event_id - operation_state.last_execute_event
            if gap_since_execute <= EXECUTION_RELEVANCE_MAX_INTERACTIONS:
                return

        if operation_state.last_docs_event is not None:
            gap_since_docs = event_id - operation_state.last_docs_event
            if gap_since_docs <= DOCS_TO_EXEC_MAX_INTERACTIONS:
                return

        raise ValidationError(
            code="docs_required",
            message=(
                "Docs-first policy: call the endpoint guide tool before executing this endpoint. "
                f"Required guide tool: {guide_tool}. "
                "Unlock factor is interaction distance (context freshness), not time."
            ),
            details={
                "operation_id": operation_id,
                "session_scope": session_key,
                "docs_to_execute_max_interactions": DOCS_TO_EXEC_MAX_INTERACTIONS,
                "execution_relevance_max_interactions": EXECUTION_RELEVANCE_MAX_INTERACTIONS,
                "last_docs_event": operation_state.last_docs_event,
                "last_execute_event": operation_state.last_execute_event,
                "execute_count": operation_state.execute_count,
                "current_event": event_id,
                "required_guide_tool": guide_tool,
            },
        )

    def _next_session_event(self, session_key: str) -> int:
        session_state = self.session_usage.setdefault(session_key, SessionUsageState())
        session_state.event_counter += 1
        return session_state.event_counter

    def _get_or_create_operation_state(
        self,
        session_key: str,
        operation_id: str,
    ) -> OperationUsageState:
        session_state = self.session_usage.setdefault(session_key, SessionUsageState())
        return session_state.operations.setdefault(operation_id, OperationUsageState())

    def _normalize_session_key(self, session_key: str | None) -> str:
        return session_key or "global"

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
        "docs_excerpt": _docs_excerpt(operation.docs_text),
    }


def _parameter_doc(parameter: Any) -> dict[str, Any]:
    return {
        "name": parameter.name,
        "in": parameter.location,
        "required": parameter.required,
        "description": parameter.description,
        "schema": parameter.schema,
        "example": _example_value(parameter.schema),
    }


def _derive_operation_purpose(operation: OperationSpec) -> str:
    action = {
        "GET": "read or inspect",
        "POST": "create or trigger",
        "PUT": "replace or update",
        "PATCH": "partially update",
        "DELETE": "remove",
    }.get(operation.method, "operate on")
    return (
        f"Use this endpoint to {action} resources in category '{operation.primary_tag}'. "
        f"It targets {operation.path} on the {operation.api_domain} API."
    )


def _derive_category_purpose(category: CategorySpec) -> str:
    if category.description:
        return category.description
    return (
        f"This category groups related endpoints for '{category.name}' on the "
        f"{category.api_domain} API."
    )


def _example_tool_arguments(operation: OperationSpec) -> dict[str, Any]:
    path_parameters = [
        parameter for parameter in operation.parameters if parameter.location == "path"
    ]
    query_parameters = [
        parameter for parameter in operation.parameters if parameter.location == "query"
    ]

    out: dict[str, Any] = {}
    if path_parameters:
        out["path"] = {
            parameter.name: _example_value(parameter.schema) for parameter in path_parameters
        }
    if query_parameters:
        out["query"] = {
            parameter.name: _example_value(parameter.schema)
            for parameter in query_parameters
            if parameter.required
        }
    if operation.request_body is not None:
        out["body"] = _example_body(operation.request_body.schema)
    return out


def _example_body(schema: dict[str, Any] | None) -> Any:
    if not isinstance(schema, dict):
        return {"example": "value"}

    schema_type = schema.get("type")
    if schema_type == "object":
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            result: dict[str, Any] = {}
            required = schema.get("required", [])
            required_keys = [str(item) for item in required] if isinstance(required, list) else []
            selected_keys = required_keys or list(properties.keys())[:3]
            for key in selected_keys:
                sub_schema = properties.get(key, {"type": "string"})
                if isinstance(sub_schema, dict):
                    result[key] = _example_value(sub_schema)
                else:
                    result[key] = "example"
            return result
        return {}
    if schema_type == "array":
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            return [_example_value(item_schema)]
        return ["example"]
    return _example_value(schema)


def _example_value(schema: dict[str, Any]) -> Any:
    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]
    schema_type = schema.get("type")
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1.0
    if schema_type == "boolean":
        return True
    if schema_type == "array":
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            return [_example_value(item_schema)]
        return ["example"]
    if schema_type == "object":
        return _example_body(schema)
    return "example"


def _docs_excerpt(text: str, *, max_chars: int = 220) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rstrip() + "..."


def _slug_from_tag(tag: str) -> str:
    lowered = tag.strip().lower()
    replaced = re.sub(r"[^a-z0-9]+", "_", lowered)
    normalized = re.sub(r"_+", "_", replaced).strip("_")
    return normalized or "untagged"


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


def _project_agent_message_for_server(
    *,
    selection: dict[str, Any],
    profiles: list[dict[str, Any]],
) -> str:
    if not profiles:
        return (
            "No project profiles configured. Configure one via CLI: "
            "hetzner-mcp project add <name> --token <token>."
        )

    selected = selection.get("name")
    exists = bool(selection.get("exists"))
    source = selection.get("source")

    if exists and isinstance(selected, str):
        for profile in profiles:
            if profile.get("name") == selected:
                description = profile.get("description") or "no description"
                return (
                    f"Active project is '{selected}' ({description}). "
                    "Use set_active_api_project to switch when your task targets a different "
                    "environment."
                )

    if isinstance(selected, str) and source == "env":
        return (
            f"Project env selection '{selected}' does not match configured profiles. "
            "Resolve by setting HETZNER_PROJECT to a valid name or clearing it."
        )

    names = ", ".join(str(profile.get("name")) for profile in profiles)
    return (
        "Project profiles exist but no valid active project is selected. "
        f"Available: {names}. Use set_active_api_project first."
    )


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


def _session_key_from_server(server: Server[Any]) -> str:
    """Create a stable in-process session key from current MCP request context."""
    try:
        ctx = server.request_context
    except LookupError:
        return "global"

    session_obj = ctx.session
    session_id = str(id(session_obj))

    client_name = "unknown"
    client_version = "unknown"
    try:
        client_params = session_obj.client_params
        if client_params is not None:
            client_info = getattr(client_params, "clientInfo", None)
            if client_info is not None:
                client_name = str(getattr(client_info, "name", "unknown"))
                client_version = str(getattr(client_info, "version", "unknown"))
    except Exception:
        client_name = "unknown"
        client_version = "unknown"

    return f"session:{session_id}:{client_name}:{client_version}"


def create_server(*, refresh_specs: bool = False) -> Server[Any]:
    """Create and configure the dynamic MCP server instance."""
    config = load_runtime_config()
    registry = OperationRegistry.load(refresh_specs=refresh_specs)
    app = HetznerMCPApplication(registry=registry, client=HetznerHttpClient(config=config))

    server: Server[Any] = Server(
        name="hetzner-mcp",
        version="0.1.5",
        instructions=(
            "Hetzner MCP server with full Cloud + Storage API coverage. "
            "Use list_api_operations/search_api_operations to discover operations, "
            "then call operation tools directly by operationId. "
            "For multi-project setups, call list_api_projects first to see which credentials "
            "profile maps to which environment, and use set_active_api_project when needed. "
            "Docs-first policy is enforced: for each endpoint, call guide_<operationId> "
            "first to unlock execution based on context freshness (interaction distance). "
            "Use guide_<operationId> and category_guide_<domain>_<slug> tools for detailed "
            "docs-based explanations."
        ),
    )

    @server.list_tools()  # type: ignore[untyped-decorator,no-untyped-call]
    async def _list_tools() -> list[types.Tool]:
        return app.list_tools()

    @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        session_key = _session_key_from_server(server)
        return await app.call_tool(name=name, arguments=arguments, session_key=session_key)

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
