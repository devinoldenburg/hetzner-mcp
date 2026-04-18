"""Installer helpers for MCP client configuration."""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True, frozen=True)
class InstallResult:
    """Result for one target MCP client."""

    client: str
    path: Path
    updated: bool
    message: str


def install_all(*, command: str = "hetzner-mcp-server") -> list[InstallResult]:
    """Install config for all supported clients."""
    results: list[InstallResult] = []
    for target in _targets_for_platform():
        results.append(_install_target(target=target, command=command))
    return results


def status_all() -> list[InstallResult]:
    """Check current status for all targets without modifying files."""
    results: list[InstallResult] = []
    for target in _targets_for_platform():
        if not target.path.exists():
            results.append(
                InstallResult(
                    client=target.client,
                    path=target.path,
                    updated=False,
                    message="missing",
                )
            )
            continue

        config = _load_json(target.path)
        section = config.get(target.root_key, {}) if isinstance(config, dict) else {}
        if isinstance(section, dict) and target.server_key in section:
            results.append(
                InstallResult(
                    client=target.client,
                    path=target.path,
                    updated=False,
                    message="configured",
                )
            )
        else:
            results.append(
                InstallResult(
                    client=target.client,
                    path=target.path,
                    updated=False,
                    message="not configured",
                )
            )
    return results


def uninstall_all() -> list[InstallResult]:
    """Remove hetzner-mcp entries from all supported clients."""
    results: list[InstallResult] = []
    for target in _targets_for_platform():
        if not target.path.exists():
            results.append(
                InstallResult(
                    client=target.client,
                    path=target.path,
                    updated=False,
                    message="missing",
                )
            )
            continue

        config = _load_json(target.path)
        if not isinstance(config, dict):
            results.append(
                InstallResult(
                    client=target.client,
                    path=target.path,
                    updated=False,
                    message="invalid json",
                )
            )
            continue

        section = config.get(target.root_key)
        if not isinstance(section, dict) or target.server_key not in section:
            results.append(
                InstallResult(
                    client=target.client,
                    path=target.path,
                    updated=False,
                    message="not configured",
                )
            )
            continue

        section.pop(target.server_key, None)
        _write_json(target.path, config)
        results.append(
            InstallResult(
                client=target.client,
                path=target.path,
                updated=True,
                message="removed",
            )
        )
    return results


@dataclass(slots=True, frozen=True)
class _ClientTarget:
    client: str
    path: Path
    root_key: str
    server_key: str
    opencode_format: bool = False


def _install_target(*, target: _ClientTarget, command: str) -> InstallResult:
    config = _load_json(target.path)
    if not isinstance(config, dict):
        config = {}

    root = config.get(target.root_key)
    if not isinstance(root, dict):
        root = {}
        config[target.root_key] = root

    server_value = _server_value_for_target(target=target, command=command)

    was_equal = root.get(target.server_key) == server_value
    root[target.server_key] = server_value
    _write_json(target.path, config)

    return InstallResult(
        client=target.client,
        path=target.path,
        updated=not was_equal,
        message="configured" if not was_equal else "already configured",
    )


def _load_json(path: Path) -> dict[str, Any] | Any:
    if not path.exists():
        return {}

    try:
        raw = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".jsonc":
            raw = _jsonc_to_json(raw)
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _jsonc_to_json(raw: str) -> str:
    return _strip_trailing_commas(_strip_jsonc_comments(raw))


def _strip_jsonc_comments(raw: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    in_line_comment = False
    in_block_comment = False
    index = 0
    length = len(raw)

    while index < length:
        char = raw[index]
        next_char = raw[index + 1] if index + 1 < length else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                out.append(char)
            index += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
                continue
            if char == "\n":
                out.append(char)
            index += 1
            continue

        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            out.append(char)
            index += 1
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            index += 2
            continue

        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue

        out.append(char)
        index += 1

    return "".join(out)


def _strip_trailing_commas(raw: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    index = 0
    length = len(raw)

    while index < length:
        char = raw[index]

        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            out.append(char)
            index += 1
            continue

        if char == ",":
            lookahead = index + 1
            while lookahead < length and raw[lookahead] in {" ", "\t", "\r", "\n"}:
                lookahead += 1
            if lookahead < length and raw[lookahead] in {"]", "}"}:
                index += 1
                continue

        out.append(char)
        index += 1

    return "".join(out)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _server_value_for_target(*, target: _ClientTarget, command: str) -> dict[str, Any]:
    if target.opencode_format:
        return {
            "type": "local",
            "command": [command],
            "enabled": True,
        }

    return {
        "command": command,
        "args": [],
    }


def _opencode_global_config_path(home: Path) -> Path:
    return home / ".config" / "opencode" / "opencode.jsonc"


def _targets_for_platform() -> list[_ClientTarget]:
    home = Path.home()
    targets: list[_ClientTarget] = [
        _ClientTarget(
            client="Cursor",
            path=home / ".cursor" / "mcp.json",
            root_key="mcpServers",
            server_key="hetzner-mcp",
        ),
        _ClientTarget(
            client="Claude Code",
            path=home / ".claude" / "mcp.json",
            root_key="mcpServers",
            server_key="hetzner-mcp",
        ),
        _ClientTarget(
            client="Windsurf",
            path=home / ".codeium" / "windsurf" / "mcp_config.json",
            root_key="mcp_servers",
            server_key="hetzner_mcp",
        ),
        _ClientTarget(
            client="OpenCode",
            path=_opencode_global_config_path(home),
            root_key="mcp",
            server_key="hetzner-mcp",
            opencode_format=True,
        ),
        _ClientTarget(
            client="Cline",
            path=home
            / ".config"
            / "Code"
            / "User"
            / "globalStorage"
            / "saoudrizwan.claude-dev"
            / "settings"
            / "cline_mcp_settings.json",
            root_key="mcpServers",
            server_key="hetzner-mcp",
        ),
    ]

    system = platform.system().lower()
    if system == "darwin":
        targets.append(
            _ClientTarget(
                client="Claude Desktop",
                path=home
                / "Library"
                / "Application Support"
                / "Claude"
                / "claude_desktop_config.json",
                root_key="mcpServers",
                server_key="hetzner-mcp",
            )
        )
    elif system == "linux":
        targets.append(
            _ClientTarget(
                client="Claude Desktop",
                path=home / ".config" / "Claude" / "claude_desktop_config.json",
                root_key="mcpServers",
                server_key="hetzner-mcp",
            )
        )

    return targets


def main() -> int:
    results = install_all()
    for result in results:
        marker = "✓" if result.message in {"configured", "already configured"} else "!"
        print(f"{marker} {result.client}: {result.message} ({result.path})")
    print("Restart your MCP client after installation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
