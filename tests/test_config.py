from __future__ import annotations

from pathlib import Path

from hetzner_mcp.config import (
    TOKEN_DEFAULT_KEY,
    TOKEN_STORAGE_KEY,
    config_file_path,
    load_runtime_config,
    load_stored_config,
    save_stored_config,
    unset_stored_config_keys,
)


def _clear_runtime_env(monkeypatch: object) -> None:
    names = [
        "HETZNER_TOKEN",
        "HETZNER_CLOUD_TOKEN",
        "HETZNER_STORAGE_TOKEN",
        "HETZNER_CLOUD_BASE_URL",
        "HETZNER_STORAGE_BASE_URL",
        "HETZNER_TIMEOUT_SECONDS",
        "HETZNER_MAX_RETRIES",
        "HETZNER_BACKOFF_BASE_SECONDS",
        "HETZNER_MCP_USER_AGENT",
    ]
    for name in names:
        monkeypatch.delenv(name, raising=False)


def test_runtime_config_loads_values_from_local_config(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("HETZNER_MCP_CONFIG_PATH", str(tmp_path / "cfg.json"))
    _clear_runtime_env(monkeypatch)

    save_stored_config(
        {
            "token_default": "stored-token",
            "cloud_base_url": "https://example.cloud/v1",
            "storage_base_url": "https://example.storage/v1",
            "timeout_seconds": 42,
            "max_retries": 9,
            "backoff_base_seconds": 0.7,
            "user_agent": "hetzner-mcp/test",
        }
    )

    cfg = load_runtime_config()
    assert cfg.token_default == "stored-token"
    assert cfg.cloud_base_url == "https://example.cloud/v1"
    assert cfg.storage_base_url == "https://example.storage/v1"
    assert cfg.timeout_seconds == 42.0
    assert cfg.max_retries == 9
    assert cfg.backoff_base_seconds == 0.7
    assert cfg.user_agent == "hetzner-mcp/test"


def test_runtime_config_prefers_environment_over_local_config(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv("HETZNER_MCP_CONFIG_PATH", str(tmp_path / "cfg.json"))
    _clear_runtime_env(monkeypatch)

    save_stored_config({"token_default": "stored-token", "timeout_seconds": 10})
    monkeypatch.setenv("HETZNER_TOKEN", "env-token")
    monkeypatch.setenv("HETZNER_TIMEOUT_SECONDS", "15")

    cfg = load_runtime_config()
    assert cfg.token_default == "env-token"
    assert cfg.timeout_seconds == 15.0


def test_unset_stored_config_keys_removes_selected_keys(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv("HETZNER_MCP_CONFIG_PATH", str(tmp_path / "cfg.json"))
    _clear_runtime_env(monkeypatch)

    save_stored_config({TOKEN_DEFAULT_KEY: "a", TOKEN_STORAGE_KEY: "b", "max_retries": 3})
    unset_stored_config_keys([TOKEN_STORAGE_KEY])

    stored = load_stored_config()
    assert stored[TOKEN_DEFAULT_KEY] == "a"
    assert TOKEN_STORAGE_KEY not in stored
    assert stored["max_retries"] == 3
    assert config_file_path().exists()
