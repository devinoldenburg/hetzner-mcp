from __future__ import annotations

import json
from pathlib import Path

import hetzner_mcp.install as install


def _set_temp_home(monkeypatch: object, tmp_path: Path) -> None:
    monkeypatch.setattr(install.Path, "home", classmethod(lambda cls: tmp_path))


def test_install_writes_opencode_global_jsonc_config(tmp_path: Path, monkeypatch: object) -> None:
    _set_temp_home(monkeypatch, tmp_path)
    monkeypatch.setattr(install.platform, "system", lambda: "Darwin")

    results = install.install_all(command="hetzner-mcp-server")
    opencode = next(item for item in results if item.client == "OpenCode")

    assert opencode.path == tmp_path / ".config" / "opencode" / "opencode.jsonc"
    assert opencode.message in {"configured", "already configured"}

    payload = json.loads(opencode.path.read_text(encoding="utf-8"))
    assert payload["mcp"]["hetzner-mcp"]["type"] == "local"
    assert payload["mcp"]["hetzner-mcp"]["command"] == ["hetzner-mcp-server"]
    assert payload["mcp"]["hetzner-mcp"]["enabled"] is True

    assert not (tmp_path / ".opencode" / "mcp.json").exists()


def test_load_json_supports_jsonc_comments_and_trailing_commas(tmp_path: Path) -> None:
    path = tmp_path / "opencode.jsonc"
    path.write_text(
        """
        {
          // global opencode config
          "mcp": {
            "hetzner-mcp": {
              "type": "local", // inline comment
              "command": ["hetzner-mcp-server",],
              "enabled": true,
            },
          },
          "url": "https://example.com",
        }
        """,
        encoding="utf-8",
    )

    payload = install._load_json(path)

    assert payload["mcp"]["hetzner-mcp"]["command"] == ["hetzner-mcp-server"]
    assert payload["mcp"]["hetzner-mcp"]["enabled"] is True
    assert payload["url"] == "https://example.com"
