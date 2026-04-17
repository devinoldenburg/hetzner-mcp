"""Uninstall helper for MCP client config entries."""

from __future__ import annotations

from .install import uninstall_all


def main() -> int:
    results = uninstall_all()
    for result in results:
        marker = "✓" if result.message in {"removed", "not configured", "missing"} else "!"
        print(f"{marker} {result.client}: {result.message} ({result.path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
