from __future__ import annotations

from pathlib import Path

from hetzner_mcp.config import (
    ACTIVE_PROJECT_KEY,
    HETZNER_PROJECT_ENV,
    PROJECTS_KEY,
    TOKEN_CLOUD_KEY,
    TOKEN_DEFAULT_KEY,
    TOKEN_STORAGE_KEY,
    config_file_path,
    get_project_selection,
    load_runtime_config,
    load_stored_config,
    project_profiles,
    save_stored_config,
    set_active_project,
    unset_stored_config_keys,
    upsert_project,
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
        HETZNER_PROJECT_ENV,
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


def test_runtime_config_uses_active_project_profile(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("HETZNER_MCP_CONFIG_PATH", str(tmp_path / "cfg.json"))
    _clear_runtime_env(monkeypatch)

    save_stored_config(
        {
            TOKEN_DEFAULT_KEY: "global-token",
            PROJECTS_KEY: {
                "staging": {
                    TOKEN_DEFAULT_KEY: "staging-token",
                    TOKEN_CLOUD_KEY: "staging-cloud-token",
                }
            },
            ACTIVE_PROJECT_KEY: "staging",
        }
    )

    cfg = load_runtime_config()
    assert cfg.token_default == "staging-token"
    assert cfg.token_cloud == "staging-cloud-token"


def test_env_selected_project_overrides_active_project(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("HETZNER_MCP_CONFIG_PATH", str(tmp_path / "cfg.json"))
    _clear_runtime_env(monkeypatch)

    save_stored_config(
        {
            PROJECTS_KEY: {
                "prod": {TOKEN_DEFAULT_KEY: "prod-token"},
                "dev": {TOKEN_DEFAULT_KEY: "dev-token"},
            },
            ACTIVE_PROJECT_KEY: "prod",
        }
    )
    monkeypatch.setenv(HETZNER_PROJECT_ENV, "dev")

    cfg = load_runtime_config()
    assert cfg.token_default == "dev-token"


def test_project_profile_helpers_create_and_select_profiles(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv("HETZNER_MCP_CONFIG_PATH", str(tmp_path / "cfg.json"))
    _clear_runtime_env(monkeypatch)

    upsert_project(
        name="prod",
        values={
            TOKEN_DEFAULT_KEY: "prod-token",
            TOKEN_STORAGE_KEY: "prod-storage",
            "description": "Production Hetzner project",
        },
        activate=True,
    )

    profiles = project_profiles()
    assert len(profiles) == 1
    assert profiles[0]["name"] == "prod"
    assert profiles[0]["has_default_token"] is True
    assert profiles[0]["has_storage_token"] is True
    assert profiles[0]["is_active"] is True

    selection = get_project_selection()
    assert selection["name"] == "prod"
    assert selection["exists"] is True

    set_active_project(None)
    selection = get_project_selection()
    assert selection["name"] is None
