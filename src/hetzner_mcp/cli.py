"""CLI for hetzner-mcp operations."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .capabilities import DomainCapability, detect_api_key_capabilities
from .config import (
    BACKOFF_BASE_SECONDS_KEY,
    CLOUD_BASE_URL_KEY,
    HETZNER_PROJECT_ENV,
    MAX_RETRIES_KEY,
    PROJECT_DESCRIPTION_KEY,
    STORAGE_BASE_URL_KEY,
    TIMEOUT_SECONDS_KEY,
    TOKEN_CLOUD_KEY,
    TOKEN_DEFAULT_KEY,
    TOKEN_STORAGE_KEY,
    USER_AGENT_KEY,
    config_file_path,
    get_project_selection,
    list_projects,
    load_runtime_config,
    load_stored_config,
    project_profiles,
    redacted_view,
    remove_project,
    save_stored_config,
    set_active_project,
    upsert_project,
    validate_base_url,
)
from .errors import ValidationError
from .install import install_all, status_all, uninstall_all
from .models import ApiDomain
from .registry import OperationRegistry
from .server import run_server


@dataclass(slots=True, frozen=True)
class ConfigKeySpec:
    """CLI metadata for one configurable key."""

    cli_key: str
    storage_key: str
    value_type: str
    description: str
    secret: bool = False


@dataclass(slots=True, frozen=True)
class TokenProbeRequest:
    """One token capability probe request from CLI input."""

    label: str
    token: str
    domains: tuple[ApiDomain, ...]


CONFIG_KEY_SPECS: tuple[ConfigKeySpec, ...] = (
    ConfigKeySpec(
        cli_key="token",
        storage_key=TOKEN_DEFAULT_KEY,
        value_type="string",
        description="Default Hetzner API token used for both domains",
        secret=True,
    ),
    ConfigKeySpec(
        cli_key="cloud-token",
        storage_key=TOKEN_CLOUD_KEY,
        value_type="string",
        description="Cloud API token override",
        secret=True,
    ),
    ConfigKeySpec(
        cli_key="storage-token",
        storage_key=TOKEN_STORAGE_KEY,
        value_type="string",
        description="Storage API token override",
        secret=True,
    ),
    ConfigKeySpec(
        cli_key="cloud-base-url",
        storage_key=CLOUD_BASE_URL_KEY,
        value_type="string",
        description="Cloud API base URL",
    ),
    ConfigKeySpec(
        cli_key="storage-base-url",
        storage_key=STORAGE_BASE_URL_KEY,
        value_type="string",
        description="Storage API base URL",
    ),
    ConfigKeySpec(
        cli_key="timeout-seconds",
        storage_key=TIMEOUT_SECONDS_KEY,
        value_type="float",
        description="HTTP timeout in seconds",
    ),
    ConfigKeySpec(
        cli_key="max-retries",
        storage_key=MAX_RETRIES_KEY,
        value_type="int",
        description="Maximum transient retry attempts",
    ),
    ConfigKeySpec(
        cli_key="backoff-base-seconds",
        storage_key=BACKOFF_BASE_SECONDS_KEY,
        value_type="float",
        description="Base retry backoff seconds",
    ),
    ConfigKeySpec(
        cli_key="user-agent",
        storage_key=USER_AGENT_KEY,
        value_type="string",
        description="HTTP User-Agent string",
    ),
)

CONFIG_KEY_MAP: dict[str, ConfigKeySpec] = {spec.cli_key: spec for spec in CONFIG_KEY_SPECS}
ALL_CONFIG_STORAGE_KEYS: tuple[str, ...] = tuple(spec.storage_key for spec in CONFIG_KEY_SPECS)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    handler = getattr(args, "_handler", None)
    if callable(handler):
        return int(handler(args))

    parser.print_help()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hetzner-mcp",
        description="Structured CLI for Hetzner MCP server, auth, and client integration",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"hetzner-mcp {__version__}",
    )

    sub = parser.add_subparsers(dest="command")

    status = sub.add_parser("status", help="Show effective config, registry, and client status")
    status.set_defaults(_handler=_cmd_status)

    doctor = sub.add_parser("doctor", help="Print detailed diagnostics")
    doctor.add_argument("--json", action="store_true", help="Output as JSON")
    doctor.set_defaults(_handler=_cmd_doctor)

    server = sub.add_parser("server", help="Run the MCP server")
    server.add_argument("action", nargs="?", choices=["run"], default="run")
    server.add_argument(
        "--refresh-specs",
        action="store_true",
        help="Refetch Hetzner OpenAPI specs before startup",
    )
    server.set_defaults(_handler=_cmd_server_run)

    update = sub.add_parser(
        "update",
        help="Refresh specs and re-apply client integration",
    )
    update.set_defaults(_handler=_cmd_update)

    client = sub.add_parser("client", help="Manage MCP client integration")
    client_sub = client.add_subparsers(dest="client_command")
    client_install = client_sub.add_parser("install", help="Configure supported MCP clients")
    client_install.set_defaults(_handler=_cmd_client_install)
    client_status = client_sub.add_parser("status", help="Show client config installation state")
    client_status.set_defaults(_handler=_cmd_client_status)
    client_repair = client_sub.add_parser("repair", help="Re-apply configuration entries")
    client_repair.set_defaults(_handler=_cmd_client_repair)
    client_uninstall = client_sub.add_parser("uninstall", help="Remove MCP config entries")
    client_uninstall.set_defaults(_handler=_cmd_client_uninstall)

    auth = sub.add_parser("auth", help="Manage API tokens directly from CLI")
    auth_sub = auth.add_subparsers(dest="auth_command")
    auth_set = auth_sub.add_parser(
        "set",
        help="Set or clear token values and auto-detect token capabilities",
    )
    auth_set.add_argument("token", nargs="?", help="Default token (same as --token)")
    auth_set.add_argument("--token", dest="default_token", help="Default token for both APIs")
    auth_set.add_argument("--cloud-token", help="Cloud API token override")
    auth_set.add_argument("--storage-token", help="Storage API token override")
    auth_set.add_argument("--clear-default", action="store_true", help="Clear stored default token")
    auth_set.add_argument("--clear-cloud", action="store_true", help="Clear stored cloud token")
    auth_set.add_argument("--clear-storage", action="store_true", help="Clear stored storage token")
    auth_set.set_defaults(_handler=_cmd_auth_set)

    auth_show = auth_sub.add_parser("show", help="Show token status and value sources")
    auth_show.add_argument("--json", action="store_true", help="Output as JSON")
    auth_show.set_defaults(_handler=_cmd_auth_show)

    auth_clear = auth_sub.add_parser("clear", help="Clear token values from local config")
    auth_clear.add_argument("--default", action="store_true", dest="clear_default")
    auth_clear.add_argument("--cloud", action="store_true", dest="clear_cloud")
    auth_clear.add_argument("--storage", action="store_true", dest="clear_storage")
    auth_clear.add_argument("--all", action="store_true", dest="clear_all")
    auth_clear.set_defaults(_handler=_cmd_auth_clear)

    project = sub.add_parser(
        "project",
        help="Manage multiple project profiles (multiple API key sets)",
    )
    project_sub = project.add_subparsers(dest="project_command")

    project_add = project_sub.add_parser(
        "add",
        help="Create/update one project profile and detect token capabilities",
    )
    project_add.add_argument("name", help="Project profile name")
    project_add.add_argument("--description", help="Human-friendly project description")
    project_add.add_argument("--token", help="Default token for this project")
    project_add.add_argument("--cloud-token", help="Cloud token override for this project")
    project_add.add_argument("--storage-token", help="Storage token override for this project")
    project_add.add_argument("--activate", action="store_true", help="Set as active project")
    project_add.set_defaults(_handler=_cmd_project_add)

    project_list = project_sub.add_parser(
        "list",
        help="List configured project profiles and active selection",
    )
    project_list.add_argument("--json", action="store_true", help="Output as JSON")
    project_list.set_defaults(_handler=_cmd_project_list)

    project_show = project_sub.add_parser("show", help="Show one project profile")
    project_show.add_argument("name", help="Project profile name")
    project_show.add_argument("--json", action="store_true", help="Output as JSON")
    project_show.set_defaults(_handler=_cmd_project_show)

    project_use = project_sub.add_parser(
        "use",
        help="Set active project profile used by runtime config",
    )
    project_use.add_argument("name", help="Project profile name")
    project_use.set_defaults(_handler=_cmd_project_use)

    project_remove = project_sub.add_parser("remove", help="Remove one project profile")
    project_remove.add_argument("name", help="Project profile name")
    project_remove.set_defaults(_handler=_cmd_project_remove)

    config = sub.add_parser("config", help="Manage persisted runtime config file")
    config_sub = config.add_subparsers(dest="config_command")

    config_show = config_sub.add_parser("show", help="Show stored and effective config")
    config_show.add_argument("--json", action="store_true", help="Output as JSON")
    config_show.set_defaults(_handler=_cmd_config_show)

    config_path = config_sub.add_parser("path", help="Print persisted config path")
    config_path.set_defaults(_handler=_cmd_config_path)

    config_get = config_sub.add_parser("get", help="Get one stored config value")
    config_get.add_argument("key", help=f"One of: {_available_config_keys()}")
    config_get.add_argument("--reveal", action="store_true", help="Show secret values")
    config_get.set_defaults(_handler=_cmd_config_get)

    config_set = config_sub.add_parser("set", help="Set one stored config value")
    config_set.add_argument("key", help=f"One of: {_available_config_keys()}")
    config_set.add_argument("value", help="Value to store")
    config_set.set_defaults(_handler=_cmd_config_set)

    config_unset = config_sub.add_parser("unset", help="Unset stored config keys")
    config_unset.add_argument("keys", nargs="*", help=f"One or more of: {_available_config_keys()}")
    config_unset.add_argument("--all", action="store_true", help="Unset every stored key")
    config_unset.set_defaults(_handler=_cmd_config_unset)

    config_edit = config_sub.add_parser("edit", help="Open persisted config in $EDITOR")
    config_edit.add_argument("--editor", help="Override editor command")
    config_edit.set_defaults(_handler=_cmd_config_edit)

    legacy_install = sub.add_parser("install", help="Alias for 'client install'")
    legacy_install.set_defaults(_handler=_cmd_client_install)

    legacy_repair = sub.add_parser("repair", help="Alias for 'client repair'")
    legacy_repair.set_defaults(_handler=_cmd_client_repair)

    legacy_uninstall = sub.add_parser("uninstall", help="Alias for 'client uninstall'")
    legacy_uninstall.set_defaults(_handler=_cmd_client_uninstall)

    legacy_diagnose = sub.add_parser("diagnose", help="Alias for 'doctor'")
    legacy_diagnose.add_argument("--json", action="store_true", help="Output as JSON")
    legacy_diagnose.set_defaults(_handler=_cmd_doctor)

    return parser


def _cmd_server_run(args: argparse.Namespace) -> int:
    asyncio.run(run_server(refresh_specs=bool(args.refresh_specs)))
    return 0


def _cmd_update(_: argparse.Namespace) -> int:
    print("Update")

    try:
        registry = OperationRegistry.load(refresh_specs=True)
    except Exception as exc:
        print(f"- specs: refresh failed ({exc}); continuing with cached specs")
    else:
        counts = registry.counts_by_domain()
        print(
            "- specs: refreshed "
            f"({registry.operation_count} total; "
            f"cloud={counts['cloud']}, storage={counts['storage']})"
        )

    print("- client config:")
    results = install_all()
    for result in results:
        print(f"  - {result.client}: {result.message} ({result.path})")

    print("Update complete. Restart your MCP client to pick up changes.")
    return 0


def _cmd_client_install(_: argparse.Namespace) -> int:
    results = install_all()
    for result in results:
        print(f"- {result.client}: {result.message} ({result.path})")
    print("Restart your MCP client after install.")
    return 0


def _cmd_client_repair(_: argparse.Namespace) -> int:
    results = install_all()
    for result in results:
        print(f"- {result.client}: {result.message} ({result.path})")
    print("Repair complete. Restart your MCP client.")
    return 0


def _cmd_client_status(_: argparse.Namespace) -> int:
    print("Client configuration")
    for result in status_all():
        print(f"- {result.client}: {result.message} ({result.path})")
    return 0


def _cmd_client_uninstall(_: argparse.Namespace) -> int:
    results = uninstall_all()
    for result in results:
        marker = "OK" if result.message in {"removed", "not configured", "missing"} else "WARN"
        print(f"- {result.client}: {marker} {result.message} ({result.path})")
    return 0


def _cmd_status(_: argparse.Namespace) -> int:
    cfg = load_runtime_config()
    redacted = redacted_view(cfg)
    stored = load_stored_config()
    config_path = config_file_path()
    selection = get_project_selection(stored)
    profiles = project_profiles(stored)
    default_source = _source_for_setting("HETZNER_TOKEN", TOKEN_DEFAULT_KEY, stored, default=False)
    cloud_source = _source_for_setting(
        "HETZNER_CLOUD_TOKEN", TOKEN_CLOUD_KEY, stored, default=False
    )
    storage_source = _source_for_setting(
        "HETZNER_STORAGE_TOKEN", TOKEN_STORAGE_KEY, stored, default=False
    )
    cloud_base_source = _source_for_setting(
        "HETZNER_CLOUD_BASE_URL", CLOUD_BASE_URL_KEY, stored, default=True
    )
    storage_base_source = _source_for_setting(
        "HETZNER_STORAGE_BASE_URL", STORAGE_BASE_URL_KEY, stored, default=True
    )
    timeout_source = _source_for_setting(
        "HETZNER_TIMEOUT_SECONDS", TIMEOUT_SECONDS_KEY, stored, default=True
    )
    retries_source = _source_for_setting(
        "HETZNER_MAX_RETRIES", MAX_RETRIES_KEY, stored, default=True
    )

    print("Runtime config")
    print(f"- config path:   {config_path} ({'exists' if config_path.exists() else 'missing'})")
    print(
        "- default token: "
        f"{'yes' if redacted.has_default_token else 'no'} "
        f"(source: {default_source})"
    )
    print(
        f"- cloud token:   {'yes' if redacted.has_cloud_token else 'no'} (source: {cloud_source})"
    )
    print(
        "- storage token: "
        f"{'yes' if redacted.has_storage_token else 'no'} "
        f"(source: {storage_source})"
    )
    print(f"- cloud base:    {redacted.cloud_base_url} (source: {cloud_base_source})")
    print(f"- storage base:  {redacted.storage_base_url} (source: {storage_base_source})")
    print(f"- timeout:       {redacted.timeout_seconds}s (source: {timeout_source})")
    print(f"- max retries:   {redacted.max_retries} (source: {retries_source})")

    print("\nProject routing")
    print(
        "- selected project: "
        f"{selection.get('name') or '<none>'} "
        f"(source: {selection.get('source')}, exists: {selection.get('exists')})"
    )
    if profiles:
        for profile in profiles:
            role = "active" if profile.get("is_active") else "available"
            description = profile.get("description") or "no description"
            token_flags = _project_token_flags(profile)
            print(f"- profile {profile['name']}: {description} ({role}; tokens: {token_flags})")
    else:
        print("- profiles: none")
    print(f"- agent message: {_project_agent_message(selection=selection, profiles=profiles)}")

    try:
        registry = OperationRegistry.load(refresh_specs=False)
        counts = registry.counts_by_domain()
        print("\nRegistry")
        print(f"- total operations: {registry.operation_count}")
        print(f"- total categories: {len(registry.all_categories())}")
        print(f"- cloud operations: {counts['cloud']}")
        print(f"- storage operations: {counts['storage']}")
    except Exception as exc:
        print("\nRegistry")
        print(f"- failed to load: {exc}")

    print("\nClient configuration")
    for result in status_all():
        print(f"- {result.client}: {result.message} ({result.path})")

    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    as_json = bool(args.json)
    stored = load_stored_config()
    selection = get_project_selection(stored)
    profiles = project_profiles(stored)
    data: dict[str, Any] = {
        "python": {
            "version": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
        },
        "config_path": str(config_file_path()),
        "stored_config": _redacted_stored_payload(stored),
        "project_selection": selection,
        "project_profiles": profiles,
        "project_message": _project_agent_message(selection=selection, profiles=profiles),
        "config": asdict(redacted_view(load_runtime_config())),
        "config_sources": {
            "token_default": _source_for_setting(
                "HETZNER_TOKEN", TOKEN_DEFAULT_KEY, stored, default=False
            ),
            "token_cloud": _source_for_setting(
                "HETZNER_CLOUD_TOKEN", TOKEN_CLOUD_KEY, stored, default=False
            ),
            "token_storage": _source_for_setting(
                "HETZNER_STORAGE_TOKEN", TOKEN_STORAGE_KEY, stored, default=False
            ),
            "cloud_base_url": _source_for_setting(
                "HETZNER_CLOUD_BASE_URL", CLOUD_BASE_URL_KEY, stored, default=True
            ),
            "storage_base_url": _source_for_setting(
                "HETZNER_STORAGE_BASE_URL", STORAGE_BASE_URL_KEY, stored, default=True
            ),
            "timeout_seconds": _source_for_setting(
                "HETZNER_TIMEOUT_SECONDS", TIMEOUT_SECONDS_KEY, stored, default=True
            ),
            "max_retries": _source_for_setting(
                "HETZNER_MAX_RETRIES", MAX_RETRIES_KEY, stored, default=True
            ),
        },
        "clients": [
            {
                "client": result.client,
                "path": str(result.path),
                "updated": result.updated,
                "message": result.message,
            }
            for result in status_all()
        ],
    }

    try:
        registry = OperationRegistry.load(refresh_specs=False)
        data["registry"] = {
            "operation_count": registry.operation_count,
            "category_count": len(registry.all_categories()),
            "counts_by_domain": registry.counts_by_domain(),
            "counts_by_tag": registry.counts_by_tag(),
        }
    except Exception as exc:
        data["registry"] = {
            "error": str(exc),
        }

    if as_json:
        print(json.dumps(data, indent=2))
    else:
        print("Diagnostics")
        print(json.dumps(data, indent=2))
    return 0


def _cmd_auth_set(args: argparse.Namespace) -> int:
    default_token = _optional_non_empty_string(args.default_token)
    positional_token = _optional_non_empty_string(args.token)
    effective_default_token = default_token or positional_token
    cloud_token = _optional_non_empty_string(args.cloud_token)
    storage_token = _optional_non_empty_string(args.storage_token)

    updates: dict[str, Any] = {}
    removals: list[str] = []
    probes: list[TokenProbeRequest] = []

    if effective_default_token is not None:
        updates[TOKEN_DEFAULT_KEY] = effective_default_token
        probes.append(
            TokenProbeRequest(
                label="default token",
                token=effective_default_token,
                domains=("cloud", "storage"),
            )
        )
    if cloud_token is not None:
        updates[TOKEN_CLOUD_KEY] = cloud_token
        probes.append(TokenProbeRequest(label="cloud token", token=cloud_token, domains=("cloud",)))
    if storage_token is not None:
        updates[TOKEN_STORAGE_KEY] = storage_token
        probes.append(
            TokenProbeRequest(
                label="storage token",
                token=storage_token,
                domains=("storage",),
            )
        )

    if bool(args.clear_default):
        removals.append(TOKEN_DEFAULT_KEY)
    if bool(args.clear_cloud):
        removals.append(TOKEN_CLOUD_KEY)
    if bool(args.clear_storage):
        removals.append(TOKEN_STORAGE_KEY)

    if not updates and not removals:
        print(
            "No token changes provided. Use --token/--cloud-token/--storage-token or clear flags."
        )
        return 2

    current = load_stored_config()
    for key, value in updates.items():
        current[key] = value
    for key in removals:
        current.pop(key, None)
    save_stored_config(current)

    print(f"Updated auth config in {config_file_path()}")
    _emit_token_capability_report(probes)
    return _cmd_auth_show(_namespace_with_json_false())


def _cmd_auth_show(args: argparse.Namespace) -> int:
    as_json = bool(args.json)
    stored = load_stored_config()
    selection = get_project_selection(stored)
    profiles = project_profiles(stored)
    effective = redacted_view(load_runtime_config())
    config_path = config_file_path()
    default_source = _source_for_setting("HETZNER_TOKEN", TOKEN_DEFAULT_KEY, stored, default=False)
    cloud_source = _source_for_setting(
        "HETZNER_CLOUD_TOKEN", TOKEN_CLOUD_KEY, stored, default=False
    )
    storage_source = _source_for_setting(
        "HETZNER_STORAGE_TOKEN", TOKEN_STORAGE_KEY, stored, default=False
    )

    payload = {
        "config_path": str(config_path),
        "stored_path_exists": config_path.exists(),
        "default_token": {
            "configured": effective.has_default_token,
            "source": default_source,
        },
        "cloud_token": {
            "configured": effective.has_cloud_token,
            "source": cloud_source,
        },
        "storage_token": {
            "configured": effective.has_storage_token,
            "source": storage_source,
        },
        "project_selection": selection,
        "message_for_agent": _project_agent_message(selection=selection, profiles=profiles),
    }

    if as_json:
        print(json.dumps(payload, indent=2))
        return 0

    print("Auth")
    print(f"- config path: {config_path} ({'exists' if config_path.exists() else 'missing'})")
    print(
        "- default token: "
        f"{'yes' if effective.has_default_token else 'no'} "
        f"(source: {default_source})"
    )
    print(
        f"- cloud token:   {'yes' if effective.has_cloud_token else 'no'} (source: {cloud_source})"
    )
    print(
        "- storage token: "
        f"{'yes' if effective.has_storage_token else 'no'} "
        f"(source: {storage_source})"
    )
    print(
        "- selected project: "
        f"{selection.get('name') or '<none>'} "
        f"(source: {selection.get('source')}, exists: {selection.get('exists')})"
    )
    print(f"- agent message: {_project_agent_message(selection=selection, profiles=profiles)}")
    return 0


def _cmd_auth_clear(args: argparse.Namespace) -> int:
    clear_default = bool(args.clear_default)
    clear_cloud = bool(args.clear_cloud)
    clear_storage = bool(args.clear_storage)
    clear_all = bool(args.clear_all)

    removals: list[str] = []
    if clear_all or not (clear_default or clear_cloud or clear_storage):
        removals = [TOKEN_DEFAULT_KEY, TOKEN_CLOUD_KEY, TOKEN_STORAGE_KEY]
    else:
        if clear_default:
            removals.append(TOKEN_DEFAULT_KEY)
        if clear_cloud:
            removals.append(TOKEN_CLOUD_KEY)
        if clear_storage:
            removals.append(TOKEN_STORAGE_KEY)

    current = load_stored_config()
    for key in removals:
        current.pop(key, None)
    save_stored_config(current)
    print(f"Cleared {', '.join(_to_cli_key(key) for key in removals)} in {config_file_path()}")
    return _cmd_auth_show(_namespace_with_json_false())


def _cmd_project_add(args: argparse.Namespace) -> int:
    name = _optional_non_empty_string(args.name)
    if name is None:
        print("Project name is required")
        return 2

    updates: dict[str, Any] = {}
    description = _optional_non_empty_string(args.description)
    if description is not None:
        updates[PROJECT_DESCRIPTION_KEY] = description

    probes: list[TokenProbeRequest] = []

    token = _optional_non_empty_string(args.token)
    if token is not None:
        updates[TOKEN_DEFAULT_KEY] = token
        probes.append(
            TokenProbeRequest(
                label=f"project '{name}' default token", token=token, domains=("cloud", "storage")
            )
        )

    cloud_token = _optional_non_empty_string(args.cloud_token)
    if cloud_token is not None:
        updates[TOKEN_CLOUD_KEY] = cloud_token
        probes.append(
            TokenProbeRequest(
                label=f"project '{name}' cloud token",
                token=cloud_token,
                domains=("cloud",),
            )
        )

    storage_token = _optional_non_empty_string(args.storage_token)
    if storage_token is not None:
        updates[TOKEN_STORAGE_KEY] = storage_token
        probes.append(
            TokenProbeRequest(
                label=f"project '{name}' storage token",
                token=storage_token,
                domains=("storage",),
            )
        )

    if not updates:
        print("No project values provided. Add token values and/or --description.")
        return 2

    try:
        upsert_project(name=name, values=updates, activate=bool(args.activate))
    except ValueError as exc:
        print(str(exc))
        return 2

    print(f"Saved project '{name}' in {config_file_path()}")
    if bool(args.activate):
        print(f"Active project set to '{name}'")
    _emit_token_capability_report(probes)
    return _cmd_project_list(_namespace_with_json_false())


def _cmd_project_list(args: argparse.Namespace) -> int:
    as_json = bool(args.json)
    stored = load_stored_config()
    profiles = project_profiles(stored)
    selection = get_project_selection(stored)

    payload = {
        "config_path": str(config_file_path()),
        "project_env_var": HETZNER_PROJECT_ENV,
        "selection": selection,
        "profiles": profiles,
        "message_for_agent": _project_agent_message(selection=selection, profiles=profiles),
    }

    if as_json:
        print(json.dumps(payload, indent=2))
        return 0

    print("Projects")
    print(f"- config path: {payload['config_path']}")
    selected = selection.get("name")
    source = selection.get("source")
    exists = selection.get("exists")
    print(f"- selected project: {selected or '<none>'} (source: {source}, exists: {exists})")
    if not profiles:
        print("- profiles: none")
    else:
        for profile in profiles:
            role = "active" if profile.get("is_active") else "available"
            description = profile.get("description") or "no description"
            token_flags = _project_token_flags(profile)
            print(f"- {profile['name']}: {description} ({role}; tokens: {token_flags})")
    print(f"- agent message: {payload['message_for_agent']}")
    return 0


def _cmd_project_show(args: argparse.Namespace) -> int:
    as_json = bool(args.json)
    name = _optional_non_empty_string(args.name)
    if name is None:
        print("Project name is required")
        return 2

    stored = load_stored_config()
    projects = list_projects(stored)
    project = projects.get(name)
    if project is None:
        print(f"Unknown project '{name}'.")
        return 2

    selection = get_project_selection(stored)
    payload = {
        "name": name,
        "description": project.get(PROJECT_DESCRIPTION_KEY),
        "has_default_token": bool(_optional_non_empty_string(project.get(TOKEN_DEFAULT_KEY))),
        "has_cloud_token": bool(_optional_non_empty_string(project.get(TOKEN_CLOUD_KEY))),
        "has_storage_token": bool(_optional_non_empty_string(project.get(TOKEN_STORAGE_KEY))),
        "is_active": bool(selection.get("exists") and selection.get("name") == name),
    }

    if as_json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Project {name}")
    print(f"- description: {payload['description'] or 'none'}")
    print(f"- active: {payload['is_active']}")
    print(f"- default token: {payload['has_default_token']}")
    print(f"- cloud token:   {payload['has_cloud_token']}")
    print(f"- storage token: {payload['has_storage_token']}")
    return 0


def _cmd_project_use(args: argparse.Namespace) -> int:
    name = _optional_non_empty_string(args.name)
    if name is None:
        print("Project name is required")
        return 2

    projects = list_projects(load_stored_config())
    if name not in projects:
        print(f"Unknown project '{name}'. Use 'hetzner-mcp project list' first.")
        return 2

    set_active_project(name)
    print(f"Active project set to '{name}'")
    return _cmd_project_list(_namespace_with_json_false())


def _cmd_project_remove(args: argparse.Namespace) -> int:
    name = _optional_non_empty_string(args.name)
    if name is None:
        print("Project name is required")
        return 2

    projects = list_projects(load_stored_config())
    if name not in projects:
        print(f"Project '{name}' is not configured.")
        return 2

    remove_project(name)
    print(f"Removed project '{name}'")
    return _cmd_project_list(_namespace_with_json_false())


def _cmd_config_show(args: argparse.Namespace) -> int:
    as_json = bool(args.json)
    stored = load_stored_config()
    selection = get_project_selection(stored)
    profiles = project_profiles(stored)
    effective = redacted_view(load_runtime_config())

    payload: dict[str, Any] = {
        "config_path": str(config_file_path()),
        "stored_path_exists": config_file_path().exists(),
        "stored": _redacted_stored_payload(stored),
        "project_selection": selection,
        "project_profiles": profiles,
        "effective": asdict(effective),
    }

    if as_json:
        print(json.dumps(payload, indent=2))
        return 0

    print("Stored config")
    print(
        f"- path: {payload['config_path']} "
        f"({'exists' if payload['stored_path_exists'] else 'missing'})"
    )
    if not payload["stored"]:
        print("- values: none")
    else:
        for key in sorted(payload["stored"].keys()):
            print(f"- {key}: {payload['stored'][key]}")

    print(
        "- selected project: "
        f"{selection.get('name') or '<none>'} "
        f"(source: {selection.get('source')}, exists: {selection.get('exists')})"
    )
    if profiles:
        for profile in profiles:
            role = "active" if profile.get("is_active") else "available"
            description = profile.get("description") or "no description"
            print(f"- project {profile['name']}: {description} ({role})")

    print("\nEffective runtime")
    print(f"- default token: {'yes' if effective.has_default_token else 'no'}")
    print(f"- cloud token:   {'yes' if effective.has_cloud_token else 'no'}")
    print(f"- storage token: {'yes' if effective.has_storage_token else 'no'}")
    print(f"- cloud base:    {effective.cloud_base_url}")
    print(f"- storage base:  {effective.storage_base_url}")
    print(f"- timeout:       {effective.timeout_seconds}s")
    print(f"- max retries:   {effective.max_retries}")
    return 0


def _cmd_config_path(_: argparse.Namespace) -> int:
    print(config_file_path())
    return 0


def _cmd_config_get(args: argparse.Namespace) -> int:
    spec = _resolve_config_key(str(args.key))
    stored = load_stored_config()
    if spec.storage_key not in stored:
        print("<unset>")
        return 0

    value = stored[spec.storage_key]
    if spec.secret and not bool(args.reveal):
        print("<redacted>")
    else:
        print(value)
    return 0


def _cmd_config_set(args: argparse.Namespace) -> int:
    spec = _resolve_config_key(str(args.key))
    parsed = _parse_config_value(spec, str(args.value))

    current = load_stored_config()
    current[spec.storage_key] = parsed
    save_stored_config(current)

    print(f"Set {spec.cli_key} in {config_file_path()}")
    return 0


def _cmd_config_unset(args: argparse.Namespace) -> int:
    clear_all = bool(args.all)
    keys_raw = [str(key) for key in list(args.keys)]

    if clear_all:
        removals = list(ALL_CONFIG_STORAGE_KEYS)
    else:
        if not keys_raw:
            print("No keys specified. Use 'config unset <key>' or '--all'.")
            return 2
        removals = [_resolve_config_key(key).storage_key for key in keys_raw]

    current = load_stored_config()
    for key in removals:
        current.pop(key, None)
    save_stored_config(current)

    print(f"Unset {', '.join(_to_cli_key(key) for key in removals)} in {config_file_path()}")
    return 0


def _cmd_config_edit(args: argparse.Namespace) -> int:
    path = config_file_path()
    if not path.exists():
        save_stored_config(load_stored_config())

    editor = _resolve_editor(_optional_non_empty_string(args.editor))
    command = [*editor, str(path)]
    try:
        result = subprocess.run(command, check=False)
    except FileNotFoundError:
        print(f"Editor command not found: {' '.join(editor)}")
        return 1

    if result.returncode != 0:
        print(f"Editor exited with status {result.returncode}")
        return result.returncode

    if not _is_valid_json_object(path):
        print("Config file is not valid JSON object. Fix it and run the command again.")
        return 1

    print(f"Updated config at {path}")
    return 0


def _available_config_keys() -> str:
    return ", ".join(spec.cli_key for spec in CONFIG_KEY_SPECS)


def _resolve_config_key(key: str) -> ConfigKeySpec:
    normalized = key.strip().lower().replace("_", "-")
    spec = CONFIG_KEY_MAP.get(normalized)
    if spec is None:
        raise SystemExit(f"Unknown key '{key}'. Use one of: {_available_config_keys()}")
    return spec


def _parse_config_value(spec: ConfigKeySpec, raw: str) -> Any:
    value = raw.strip()
    if spec.value_type == "string":
        if not value:
            raise SystemExit(f"{spec.cli_key} cannot be empty")
        if spec.storage_key == CLOUD_BASE_URL_KEY:
            try:
                return validate_base_url(value, api_domain="cloud")
            except ValidationError as exc:
                raise SystemExit(str(exc)) from exc
        if spec.storage_key == STORAGE_BASE_URL_KEY:
            try:
                return validate_base_url(value, api_domain="storage")
            except ValidationError as exc:
                raise SystemExit(str(exc)) from exc
        return value
    if spec.value_type == "int":
        try:
            return int(value)
        except ValueError as exc:
            raise SystemExit(f"{spec.cli_key} must be an integer") from exc
    if spec.value_type == "float":
        try:
            return float(value)
        except ValueError as exc:
            raise SystemExit(f"{spec.cli_key} must be a number") from exc
    raise SystemExit(f"Unsupported value type for {spec.cli_key}")


def _to_cli_key(storage_key: str) -> str:
    for spec in CONFIG_KEY_SPECS:
        if spec.storage_key == storage_key:
            return spec.cli_key
    return storage_key


def _redacted_stored_payload(stored: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for spec in CONFIG_KEY_SPECS:
        if spec.storage_key not in stored:
            continue
        out[spec.cli_key] = "<redacted>" if spec.secret else stored[spec.storage_key]

    selection = get_project_selection(stored)
    out["active_project"] = selection.get("name")

    projects = list_projects(stored)
    if projects:
        out["projects"] = {}
        for name, values in projects.items():
            out["projects"][name] = {
                "description": values.get(PROJECT_DESCRIPTION_KEY),
                "token": "<redacted>"
                if _optional_non_empty_string(values.get(TOKEN_DEFAULT_KEY))
                else None,
                "cloud-token": "<redacted>"
                if _optional_non_empty_string(values.get(TOKEN_CLOUD_KEY))
                else None,
                "storage-token": "<redacted>"
                if _optional_non_empty_string(values.get(TOKEN_STORAGE_KEY))
                else None,
            }
    return out


def _project_token_flags(profile: dict[str, Any]) -> str:
    has_default = bool(profile.get("has_default_token"))
    has_cloud = bool(profile.get("has_cloud_token"))
    has_storage = bool(profile.get("has_storage_token"))

    parts: list[str] = []
    if has_default:
        parts.append("default")
    if has_cloud:
        parts.append("cloud")
    if has_storage:
        parts.append("storage")
    if not parts:
        return "none"
    return ",".join(parts)


def _emit_token_capability_report(probes: list[TokenProbeRequest]) -> None:
    if not probes:
        return

    runtime = load_runtime_config()
    print("Token capabilities")
    for probe in probes:
        try:
            capabilities = detect_api_key_capabilities(
                token=probe.token,
                cloud_base_url=runtime.cloud_base_url,
                storage_base_url=runtime.storage_base_url,
                timeout_seconds=runtime.timeout_seconds,
                user_agent=runtime.user_agent,
                domains=probe.domains,
            )
        except Exception as exc:
            print(f"- {probe.label}: detection failed ({exc})")
            continue

        if not capabilities:
            print(f"- {probe.label}: unknown")
            continue

        formatted = ", ".join(_format_domain_capability(item) for item in capabilities)
        print(f"- {probe.label}: {formatted}")


def _format_domain_capability(capability: DomainCapability) -> str:
    return (
        f"{capability.api_domain}:{capability.level} "
        f"(GET {_status_label(capability.read_status_code)}, "
        f"POST {_status_label(capability.write_status_code)})"
    )


def _status_label(status_code: int) -> str:
    if status_code == 0:
        return "network-error"
    return str(status_code)


def _project_agent_message(*, selection: dict[str, Any], profiles: list[dict[str, Any]]) -> str:
    if not profiles:
        return (
            "No project profiles are configured yet. Add one with "
            "'hetzner-mcp project add <name> --token <token>'."
        )

    selected = selection.get("name")
    exists = bool(selection.get("exists"))
    source = selection.get("source")

    if exists and isinstance(selected, str):
        for profile in profiles:
            if profile.get("name") == selected:
                description = profile.get("description") or "no description"
                return (
                    f"Use project '{selected}' for {description}. "
                    "Switch project with 'hetzner-mcp project use <name>' or set "
                    f"{HETZNER_PROJECT_ENV}=<name> for one session. "
                    "MCP-side session switching is temporary unless persist=true is requested."
                )

    if isinstance(selected, str) and source == "env":
        return (
            f"{HETZNER_PROJECT_ENV} is set to '{selected}', but this profile does not exist. "
            "Unset it or choose an existing profile with 'hetzner-mcp project list'."
        )

    names = ", ".join(str(profile.get("name")) for profile in profiles)
    return (
        "Project profiles are configured but none is active. "
        f"Available: {names}. Use 'hetzner-mcp project use <name>' to select one."
    )


def _source_for_setting(
    env_name: str,
    stored_key: str,
    stored: dict[str, Any],
    *,
    default: bool,
) -> str:
    env_value = os.environ.get(env_name)
    if isinstance(env_value, str) and env_value.strip():
        return "env"

    if stored_key in stored:
        stored_value = stored[stored_key]
        if isinstance(stored_value, str):
            if stored_value.strip():
                return "file"
        elif isinstance(stored_value, (int, float)):
            return "file"

    return "default" if default else "unset"


def _resolve_editor(explicit: str | None) -> list[str]:
    if explicit:
        return shlex.split(explicit)

    visual = os.environ.get("VISUAL")
    if isinstance(visual, str) and visual.strip():
        return shlex.split(visual)

    editor = os.environ.get("EDITOR")
    if isinstance(editor, str) and editor.strip():
        return shlex.split(editor)

    if os.name == "nt":
        return ["notepad"]
    return ["vi"]


def _is_valid_json_object(path: Path) -> bool:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(raw, dict)


def _optional_non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _namespace_with_json_false() -> argparse.Namespace:
    return argparse.Namespace(json=False)


if __name__ == "__main__":
    raise SystemExit(main())
