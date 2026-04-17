"""Runtime configuration loading for hetzner-mcp."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .http_client import RuntimeConfig


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
    """Load runtime config from environment variables."""
    timeout_seconds = _float_from_env("HETZNER_TIMEOUT_SECONDS", default=30.0)
    max_retries = _int_from_env("HETZNER_MAX_RETRIES", default=3)
    backoff_base = _float_from_env("HETZNER_BACKOFF_BASE_SECONDS", default=0.5)

    return RuntimeConfig(
        token_default=os.environ.get("HETZNER_TOKEN"),
        token_cloud=os.environ.get("HETZNER_CLOUD_TOKEN"),
        token_storage=os.environ.get("HETZNER_STORAGE_TOKEN"),
        cloud_base_url=os.environ.get("HETZNER_CLOUD_BASE_URL", "https://api.hetzner.cloud/v1"),
        storage_base_url=os.environ.get("HETZNER_STORAGE_BASE_URL", "https://api.hetzner.com/v1"),
        timeout_seconds=timeout_seconds,
        max_retries=max(0, max_retries),
        backoff_base_seconds=max(0.05, backoff_base),
        user_agent=os.environ.get("HETZNER_MCP_USER_AGENT", "hetzner-mcp/0.1.1"),
    )


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


def _int_from_env(name: str, *, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_from_env(name: str, *, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default
