from __future__ import annotations

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
