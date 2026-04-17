"""Runtime configuration loading for hetzner-mcp."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .http_client import RuntimeConfig

HETZNER_MCP_CONFIG_PATH_ENV = "HETZNER_MCP_CONFIG_PATH"

TOKEN_DEFAULT_KEY = "token_default"
TOKEN_CLOUD_KEY = "token_cloud"
TOKEN_STORAGE_KEY = "token_storage"
CLOUD_BASE_URL_KEY = "cloud_base_url"
STORAGE_BASE_URL_KEY = "storage_base_url"
TIMEOUT_SECONDS_KEY = "timeout_seconds"
MAX_RETRIES_KEY = "max_retries"
BACKOFF_BASE_SECONDS_KEY = "backoff_base_seconds"
USER_AGENT_KEY = "user_agent"

ALLOWED_STORED_CONFIG_KEYS: tuple[str, ...] = (
    TOKEN_DEFAULT_KEY,
    TOKEN_CLOUD_KEY,
    TOKEN_STORAGE_KEY,
    CLOUD_BASE_URL_KEY,
    STORAGE_BASE_URL_KEY,
    TIMEOUT_SECONDS_KEY,
    MAX_RETRIES_KEY,
    BACKOFF_BASE_SECONDS_KEY,
    USER_AGENT_KEY,
)


@dataclass(slots=True, frozen=True)
class RedactedConfigView:
    """Safe-to-display config snapshot."""

    has_default_token: bool
    has_cloud_token: bool
    has_storage_token: bool
    cloud_base_url: str
    storage_base_url: str
    timeout_seconds: float
    max_retries: int


def load_runtime_config() -> RuntimeConfig:
    """Load runtime config from environment and local config file.

    Environment variables take precedence over local file values.
    """
    stored = load_stored_config()
    timeout_seconds = _float_from_env_or_store(
        "HETZNER_TIMEOUT_SECONDS",
        TIMEOUT_SECONDS_KEY,
        stored,
        default=30.0,
    )
    max_retries = _int_from_env_or_store(
        "HETZNER_MAX_RETRIES",
        MAX_RETRIES_KEY,
        stored,
        default=3,
    )
    backoff_base = _float_from_env_or_store(
        "HETZNER_BACKOFF_BASE_SECONDS",
        BACKOFF_BASE_SECONDS_KEY,
        stored,
        default=0.5,
    )

    return RuntimeConfig(
        token_default=_optional_string_from_env_or_store(
            "HETZNER_TOKEN", TOKEN_DEFAULT_KEY, stored
        ),
        token_cloud=_optional_string_from_env_or_store(
            "HETZNER_CLOUD_TOKEN", TOKEN_CLOUD_KEY, stored
        ),
        token_storage=_optional_string_from_env_or_store(
            "HETZNER_STORAGE_TOKEN", TOKEN_STORAGE_KEY, stored
        ),
        cloud_base_url=_string_from_env_or_store(
            "HETZNER_CLOUD_BASE_URL",
            CLOUD_BASE_URL_KEY,
            stored,
            default="https://api.hetzner.cloud/v1",
        ),
        storage_base_url=_string_from_env_or_store(
            "HETZNER_STORAGE_BASE_URL",
            STORAGE_BASE_URL_KEY,
            stored,
            default="https://api.hetzner.com/v1",
        ),
        timeout_seconds=timeout_seconds,
        max_retries=max(0, max_retries),
        backoff_base_seconds=max(0.05, backoff_base),
        user_agent=_string_from_env_or_store(
            "HETZNER_MCP_USER_AGENT",
            USER_AGENT_KEY,
            stored,
            default="hetzner-mcp/0.1.2",
        ),
    )


def config_file_path() -> Path:
    """Return the local persisted config path."""
    override = os.environ.get(HETZNER_MCP_CONFIG_PATH_ENV)
    if override:
        return Path(override).expanduser()

    appdata = os.environ.get("APPDATA")
    if os.name == "nt" and appdata:
        return Path(appdata) / "hetzner-mcp" / "config.json"

    return Path.home() / ".config" / "hetzner-mcp" / "config.json"


def load_stored_config() -> dict[str, Any]:
    """Load persisted local config file."""
    path = config_file_path()
    if not path.exists():
        return {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(raw, dict):
        return {}

    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key in ALLOWED_STORED_CONFIG_KEYS:
            out[key] = value
    return out


def save_stored_config(payload: Mapping[str, Any]) -> Path:
    """Persist local config file and tighten file permissions when possible."""
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key in ALLOWED_STORED_CONFIG_KEYS:
            out[key] = value

    path = config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    return path


def set_stored_config_values(updates: Mapping[str, Any]) -> Path:
    """Merge updates into the local persisted config."""
    current = load_stored_config()
    for key, value in updates.items():
        if key in ALLOWED_STORED_CONFIG_KEYS:
            current[key] = value
    return save_stored_config(current)


def unset_stored_config_keys(keys: Iterable[str]) -> Path:
    """Remove selected keys from local persisted config."""
    current = load_stored_config()
    for key in keys:
        current.pop(key, None)
    return save_stored_config(current)


def redacted_view(config: RuntimeConfig) -> RedactedConfigView:
    """Build a safe diagnostic view of config without secrets."""
    return RedactedConfigView(
        has_default_token=bool(config.token_default),
        has_cloud_token=bool(config.token_cloud),
        has_storage_token=bool(config.token_storage),
        cloud_base_url=config.cloud_base_url,
        storage_base_url=config.storage_base_url,
        timeout_seconds=config.timeout_seconds,
        max_retries=config.max_retries,
    )


def _optional_string_from_env_or_store(
    env_name: str,
    stored_key: str,
    stored: Mapping[str, Any],
) -> str | None:
    env_value = _optional_string(os.environ.get(env_name))
    if env_value is not None:
        return env_value
    return _optional_string(stored.get(stored_key))


def _string_from_env_or_store(
    env_name: str,
    stored_key: str,
    stored: Mapping[str, Any],
    *,
    default: str,
) -> str:
    value = _optional_string_from_env_or_store(env_name, stored_key, stored)
    if value is not None:
        return value
    return default


def _int_from_env_or_store(
    env_name: str,
    stored_key: str,
    stored: Mapping[str, Any],
    *,
    default: int,
) -> int:
    raw = os.environ.get(env_name)
    if raw is None:
        stored_value = stored.get(stored_key)
        return _int_from_any(stored_value, default=default)
    return _int_from_any(raw, default=default)


def _float_from_env_or_store(
    env_name: str,
    stored_key: str,
    stored: Mapping[str, Any],
    *,
    default: float,
) -> float:
    raw = os.environ.get(env_name)
    if raw is None:
        stored_value = stored.get(stored_key)
        return _float_from_any(stored_value, default=default)
    return _float_from_any(raw, default=default)


def _int_from_any(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _float_from_any(value: Any, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped
