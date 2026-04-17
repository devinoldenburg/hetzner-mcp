from __future__ import annotations

import json
from pathlib import Path

import hetzner_mcp.cli as cli
from hetzner_mcp.install import InstallResult


class _FakeRegistry:
    operation_count = 221

    def counts_by_domain(self) -> dict[str, int]:
        return {"cloud": 189, "storage": 32}


def test_update_command_refreshes_specs_and_repairs_clients(
    monkeypatch: object, capsys: object
) -> None:
    calls: dict[str, bool] = {}

    class _FakeRegistryApi:
        @staticmethod
        def load(*, refresh_specs: bool) -> _FakeRegistry:
            calls["refresh_specs"] = refresh_specs
            return _FakeRegistry()

    def _fake_install_all() -> list[InstallResult]:
        return [
            InstallResult(
                client="Cursor",
                path=Path("/tmp/cursor-mcp.json"),
                updated=True,
                message="configured",
            )
        ]

    monkeypatch.setattr(cli, "OperationRegistry", _FakeRegistryApi)
    monkeypatch.setattr(cli, "install_all", _fake_install_all)

    exit_code = cli.main(["update"])
    captured = capsys.readouterr().out

    assert exit_code == 0
    assert calls["refresh_specs"] is True
    assert "specs: refreshed" in captured
    assert "client config" in captured
    assert "Update complete" in captured


def test_update_command_continues_when_refresh_fails(monkeypatch: object, capsys: object) -> None:
    class _FailRegistryApi:
        @staticmethod
        def load(*, refresh_specs: bool) -> _FakeRegistry:
            _ = refresh_specs
            raise RuntimeError("network down")

    def _fake_install_all() -> list[InstallResult]:
        return [
            InstallResult(
                client="Claude Code",
                path=Path("/tmp/claude-mcp.json"),
                updated=False,
                message="already configured",
            )
        ]

    monkeypatch.setattr(cli, "OperationRegistry", _FailRegistryApi)
    monkeypatch.setattr(cli, "install_all", _fake_install_all)

    exit_code = cli.main(["update"])
    captured = capsys.readouterr().out

    assert exit_code == 0
    assert "refresh failed" in captured
    assert "already configured" in captured
    assert "Update complete" in captured


def test_project_commands_manage_multiple_profiles(
    tmp_path: Path, monkeypatch: object, capsys: object
) -> None:
    monkeypatch.setenv("HETZNER_MCP_CONFIG_PATH", str(tmp_path / "cfg.json"))
    monkeypatch.delenv("HETZNER_PROJECT", raising=False)

    add_prod = cli.main(
        [
            "project",
            "add",
            "prod",
            "--description",
            "Production environment",
            "--token",
            "prod-token",
            "--activate",
        ]
    )
    assert add_prod == 0
    _ = capsys.readouterr()

    add_dev = cli.main(
        [
            "project",
            "add",
            "dev",
            "--description",
            "Development environment",
            "--token",
            "dev-token",
        ]
    )
    assert add_dev == 0
    _ = capsys.readouterr()

    list_exit = cli.main(["project", "list", "--json"])
    list_output = capsys.readouterr().out
    assert list_exit == 0
    payload = json.loads(list_output)
    assert payload["selection"]["name"] == "prod"
    assert payload["selection"]["exists"] is True
    assert len(payload["profiles"]) == 2

    use_exit = cli.main(["project", "use", "dev"])
    use_output = capsys.readouterr().out
    assert use_exit == 0
    assert "Active project set to 'dev'" in use_output

    show_exit = cli.main(["project", "show", "dev", "--json"])
    show_output = capsys.readouterr().out
    assert show_exit == 0
    show_payload = json.loads(show_output)
    assert show_payload["name"] == "dev"
    assert show_payload["is_active"] is True
