"""CLI for hetzner-mcp operations."""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
from typing import Any

from .config import load_runtime_config, redacted_view
from .install import install_all, status_all
from .registry import OperationRegistry
from .server import run_server
from .uninstall import main as uninstall_main


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "server":
        asyncio.run(run_server(refresh_specs=args.refresh_specs))
        return 0

    if args.command == "install":
        results = install_all()
        for result in results:
            print(f"- {result.client}: {result.message} ({result.path})")
        print("Restart your MCP client after install.")
        return 0

    if args.command == "status":
        return _status()

    if args.command == "diagnose":
        return _diagnose(as_json=args.json)

    if args.command == "repair":
        results = install_all()
        for result in results:
            print(f"- {result.client}: {result.message} ({result.path})")
        print("Repair complete. Restart your MCP client.")
        return 0

    if args.command == "uninstall":
        return uninstall_main()

    parser.print_help()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hetzner-mcp",
        description="Hetzner MCP installer and diagnostic CLI",
    )
    sub = parser.add_subparsers(dest="command")

    install = sub.add_parser("install", help="Configure supported MCP clients")
    install.set_defaults(command="install")

    status = sub.add_parser("status", help="Show current installation and registry status")
    status.set_defaults(command="status")

    diagnose = sub.add_parser("diagnose", help="Print diagnostic information")
    diagnose.add_argument("--json", action="store_true", help="Output as JSON")
    diagnose.set_defaults(command="diagnose")

    repair = sub.add_parser("repair", help="Re-apply client configuration entries")
    repair.set_defaults(command="repair")

    uninstall = sub.add_parser("uninstall", help="Remove config from supported MCP clients")
    uninstall.set_defaults(command="uninstall")

    server = sub.add_parser("server", help="Run stdio MCP server")
    server.add_argument(
        "--refresh-specs",
        action="store_true",
        help="Refetch Hetzner OpenAPI specs before startup",
    )
    server.set_defaults(command="server")

    return parser


def _status() -> int:
    cfg = load_runtime_config()
    redacted = redacted_view(cfg)

    print("Config")
    print(f"- default token: {'yes' if redacted.has_default_token else 'no'}")
    print(f"- cloud token:   {'yes' if redacted.has_cloud_token else 'no'}")
    print(f"- storage token: {'yes' if redacted.has_storage_token else 'no'}")
    print(f"- cloud base:    {redacted.cloud_base_url}")
    print(f"- storage base:  {redacted.storage_base_url}")
    print(f"- timeout:       {redacted.timeout_seconds}s")
    print(f"- max retries:   {redacted.max_retries}")

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


def _diagnose(*, as_json: bool) -> int:
    data: dict[str, Any] = {
        "python": {
            "version": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
        },
        "config": redacted_view(load_runtime_config()).__dict__,
        "clients": [result.__dict__ for result in status_all()],
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


if __name__ == "__main__":
    raise SystemExit(main())
