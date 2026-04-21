"""Runtime configuration loading for hetzner-mcp."""

from __future__ import annotations

import json
import os
import urllib.parse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .errors import ValidationError
from .http_client import RuntimeConfig
from .models import ApiDomain

HETZNER_MCP_CONFIG_PATH_ENV = "HETZNER_MCP_CONFIG_PATH"
HETZNER_PROJECT_ENV = "HETZNER_PROJECT"
HETZNER_ALLOW_CUSTOM_BASE_URLS_ENV = "HETZNER_ALLOW_CUSTOM_BASE_URLS"

TOKEN_DEFAULT_KEY = "token_default"
TOKEN_CLOUD_KEY = "token_cloud"
TOKEN_STORAGE_KEY = "token_storage"
CLOUD_BASE_URL_KEY = "cloud_base_url"
STORAGE_BASE_URL_KEY = "storage_base_url"
TIMEOUT_SECONDS_KEY = "timeout_seconds"
MAX_RETRIES_KEY = "max_retries"
BACKOFF_BASE_SECONDS_KEY = "backoff_base_seconds"
USER_AGENT_KEY = "user_agent"

PROJECTS_KEY = "projects"
ACTIVE_PROJECT_KEY = "active_project"
PROJECT_DESCRIPTION_KEY = "description"

DEFAULT_CLOUD_BASE_URL = "https://api.hetzner.cloud/v1"
DEFAULT_STORAGE_BASE_URL = "https://api.hetzner.com/v1"

_DEFAULT_BASE_URLS: dict[ApiDomain, str] = {
    "cloud": DEFAULT_CLOUD_BASE_URL,
    "storage": DEFAULT_STORAGE_BASE_URL,
}

RUNTIME_SETTING_KEYS: tuple[str, ...] = (
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

ALLOWED_STORED_CONFIG_KEYS: tuple[str, ...] = (
    *RUNTIME_SETTING_KEYS,
    PROJECTS_KEY,
    ACTIVE_PROJECT_KEY,
)

ALLOWED_PROJECT_VALUE_KEYS: tuple[str, ...] = (
    *RUNTIME_SETTING_KEYS,
    PROJECT_DESCRIPTION_KEY,
)

_STRING_RUNTIME_KEYS = {
    TOKEN_DEFAULT_KEY,
    TOKEN_CLOUD_KEY,
    TOKEN_STORAGE_KEY,
    CLOUD_BASE_URL_KEY,
    STORAGE_BASE_URL_KEY,
    USER_AGENT_KEY,
}
_FLOAT_RUNTIME_KEYS = {
    TIMEOUT_SECONDS_KEY,
    BACKOFF_BASE_SECONDS_KEY,
}
_INT_RUNTIME_KEYS = {
    MAX_RETRIES_KEY,
}


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
    return _load_runtime_config(project_override=None, stored=None)


def _load_runtime_config(
    *,
    project_override: str | None,
    stored: Mapping[str, Any] | None,
) -> RuntimeConfig:
    stored_config = _ensure_stored(stored)
    selection = get_project_selection(stored_config, project_override=project_override)
    selected_project = selection["name"]
    project_values: dict[str, Any] = {}
    projects = list_projects(stored_config)
    if isinstance(selected_project, str) and selected_project in projects:
        project_values = projects[selected_project]

    effective_store = _effective_store(stored_config, project_values)

    timeout_seconds = _float_from_env_or_store(
        "HETZNER_TIMEOUT_SECONDS",
        TIMEOUT_SECONDS_KEY,
        effective_store,
        default=30.0,
    )
    max_retries = _int_from_env_or_store(
        "HETZNER_MAX_RETRIES",
        MAX_RETRIES_KEY,
        effective_store,
        default=3,
    )
    backoff_base = _float_from_env_or_store(
        "HETZNER_BACKOFF_BASE_SECONDS",
        BACKOFF_BASE_SECONDS_KEY,
        effective_store,
        default=0.5,
    )

    cloud_base_url = validate_base_url(
        _string_from_env_or_store(
            "HETZNER_CLOUD_BASE_URL",
            CLOUD_BASE_URL_KEY,
            effective_store,
            default=DEFAULT_CLOUD_BASE_URL,
        ),
        api_domain="cloud",
    )
    storage_base_url = validate_base_url(
        _string_from_env_or_store(
            "HETZNER_STORAGE_BASE_URL",
            STORAGE_BASE_URL_KEY,
            effective_store,
            default=DEFAULT_STORAGE_BASE_URL,
        ),
        api_domain="storage",
    )

    return RuntimeConfig(
        token_default=_optional_string_from_env_or_store(
            "HETZNER_TOKEN", TOKEN_DEFAULT_KEY, effective_store
        ),
        token_cloud=_optional_string_from_env_or_store(
            "HETZNER_CLOUD_TOKEN", TOKEN_CLOUD_KEY, effective_store
        ),
        token_storage=_optional_string_from_env_or_store(
            "HETZNER_STORAGE_TOKEN", TOKEN_STORAGE_KEY, effective_store
        ),
        cloud_base_url=cloud_base_url,
        storage_base_url=storage_base_url,
        timeout_seconds=timeout_seconds,
        max_retries=max(0, max_retries),
        backoff_base_seconds=max(0.05, backoff_base),
        user_agent=_string_from_env_or_store(
            "HETZNER_MCP_USER_AGENT",
            USER_AGENT_KEY,
            effective_store,
            default=f"hetzner-mcp/{__version__}",
        ),
    )


def load_runtime_config_for_project(
    project_override: str | None,
    *,
    stored: Mapping[str, Any] | None = None,
) -> RuntimeConfig:
    """Load runtime config for one session-scoped project override."""
    return _load_runtime_config(project_override=project_override, stored=stored)


def allow_custom_base_urls() -> bool:
    """Return whether custom HTTPS base URLs are explicitly allowed."""
    raw = os.environ.get(HETZNER_ALLOW_CUSTOM_BASE_URLS_ENV, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def validate_base_url(
    value: str,
    *,
    api_domain: ApiDomain,
    allow_custom: bool | None = None,
) -> str:
    """Validate one configured API base URL before tokens are ever attached to it."""
    parsed = urllib.parse.urlparse(value)
    label = f"{api_domain} base URL"

    if parsed.scheme != "https":
        raise ValidationError(
            code="invalid_base_url",
            message=f"{label} must use https",
            details={"api_domain": api_domain, "value": value},
        )
    if not parsed.netloc:
        raise ValidationError(
            code="invalid_base_url",
            message=f"{label} must include a hostname",
            details={"api_domain": api_domain, "value": value},
        )
    if parsed.username is not None or parsed.password is not None:
        raise ValidationError(
            code="invalid_base_url",
            message=f"{label} must not include embedded credentials",
            details={"api_domain": api_domain, "value": value},
        )
    if parsed.query or parsed.fragment:
        raise ValidationError(
            code="invalid_base_url",
            message=f"{label} must not include query strings or fragments",
            details={"api_domain": api_domain, "value": value},
        )

    normalized_path = parsed.path.rstrip("/") or ""
    normalized = urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, normalized_path, "", "", "")
    )

    custom_allowed = allow_custom_base_urls() if allow_custom is None else allow_custom
    if custom_allowed:
        return normalized

    expected = urllib.parse.urlparse(_DEFAULT_BASE_URLS[api_domain])
    expected_path = expected.path.rstrip("/") or ""
    expected_port = expected.port
    actual_port = parsed.port

    if (
        parsed.hostname != expected.hostname
        or actual_port != expected_port
        or normalized_path != expected_path
    ):
        raise ValidationError(
            code="custom_base_url_disabled",
            message=(
                f"{label} must use the official Hetzner endpoint {_DEFAULT_BASE_URLS[api_domain]}. "
                f"Set {HETZNER_ALLOW_CUSTOM_BASE_URLS_ENV}=true to opt into custom HTTPS base URLs."
            ),
            details={
                "api_domain": api_domain,
                "value": value,
                "expected": _DEFAULT_BASE_URLS[api_domain],
            },
        )

    return normalized


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
    return _sanitize_stored_payload(raw)


def save_stored_config(payload: Mapping[str, Any]) -> Path:
    """Persist local config file and tighten file permissions when possible."""
    out = _sanitize_stored_payload(payload)

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


def list_projects(stored: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Return configured project profiles keyed by project name."""
    config = _ensure_stored(stored)
    raw = config.get(PROJECTS_KEY)
    if not isinstance(raw, dict):
        return {}

    out: dict[str, dict[str, Any]] = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not isinstance(value, dict):
            continue
        clean_name = _normalize_project_name(name)
        if clean_name is None:
            continue
        out[clean_name] = _sanitize_project_values(value)
    return out


def project_profiles(stored: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return user-facing profile metadata for each configured project."""
    config = _ensure_stored(stored)
    projects = list_projects(config)
    selection = get_project_selection(config)
    active_name = selection["name"] if selection["exists"] else None

    out: list[dict[str, Any]] = []
    for name in sorted(projects.keys()):
        values = projects[name]
        out.append(
            {
                "name": name,
                "description": _optional_string(values.get(PROJECT_DESCRIPTION_KEY)),
                "has_default_token": bool(_optional_string(values.get(TOKEN_DEFAULT_KEY))),
                "has_cloud_token": bool(_optional_string(values.get(TOKEN_CLOUD_KEY))),
                "has_storage_token": bool(_optional_string(values.get(TOKEN_STORAGE_KEY))),
                "is_active": active_name == name,
            }
        )
    return out


def get_project_selection(
    stored: Mapping[str, Any] | None = None,
    *,
    project_override: str | None = None,
) -> dict[str, Any]:
    """Return selected project routing details for runtime and agent guidance."""
    config = _ensure_stored(stored)
    projects = list_projects(config)

    selected = _optional_string(os.environ.get(HETZNER_PROJECT_ENV))
    source = "env" if selected else "unset"
    if selected is None:
        selected = _normalize_project_name(project_override)
        if selected is not None:
            source = "session"
    if selected is None:
        selected = _optional_string(config.get(ACTIVE_PROJECT_KEY))
        if selected is not None:
            source = "file"

    exists = bool(selected and selected in projects)
    description: str | None = None
    if selected and exists:
        description = _optional_string(projects[selected].get(PROJECT_DESCRIPTION_KEY))

    if selected is None:
        message = "No project profile selected. Using global tokens/config values."
    elif exists:
        description_suffix = f" ({description})" if description else ""
        selection_scope = "Session override" if source == "session" else "Active project"
        message = (
            f"{selection_scope} '{selected}'{description_suffix}. API calls use this project's "
            "credentials unless overridden by environment variables."
        )
    elif source == "env":
        message = (
            f"HETZNER_PROJECT='{selected}' does not match any configured project profile. "
            "Falling back to global tokens/config values."
        )
    elif source == "session":
        message = (
            f"Session override project '{selected}' was not found. "
            "Falling back to global tokens/config values."
        )
    else:
        message = (
            f"Configured active project '{selected}' was not found. "
            "Falling back to global tokens/config values."
        )

    return {
        "name": selected,
        "source": source,
        "exists": exists,
        "description": description,
        "available_projects": sorted(projects.keys()),
        "message": message,
    }


def upsert_project(
    name: str,
    values: Mapping[str, Any],
    *,
    activate: bool = False,
) -> Path:
    """Create or update one project profile."""
    project_name = _normalize_project_name(name)
    if project_name is None:
        raise ValueError("Project name is required")

    sanitized_values = _sanitize_project_values(values)
    if not sanitized_values:
        raise ValueError("At least one project value must be provided")

    current = load_stored_config()
    projects = list_projects(current)
    existing = projects.get(project_name, {})
    merged = dict(existing)
    merged.update(sanitized_values)
    projects[project_name] = merged

    current[PROJECTS_KEY] = projects
    if activate:
        current[ACTIVE_PROJECT_KEY] = project_name
    return save_stored_config(current)


def remove_project(name: str) -> Path:
    """Delete one project profile and clear active selection if needed."""
    project_name = _normalize_project_name(name)
    if project_name is None:
        raise ValueError("Project name is required")

    current = load_stored_config()
    projects = list_projects(current)
    projects.pop(project_name, None)

    if projects:
        current[PROJECTS_KEY] = projects
    else:
        current.pop(PROJECTS_KEY, None)

    active = _normalize_project_name(current.get(ACTIVE_PROJECT_KEY))
    if active == project_name:
        current.pop(ACTIVE_PROJECT_KEY, None)

    return save_stored_config(current)


def set_active_project(name: str | None) -> Path:
    """Set or clear active project selection in local config."""
    current = load_stored_config()
    normalized = _normalize_project_name(name)
    if normalized is None:
        current.pop(ACTIVE_PROJECT_KEY, None)
    else:
        current[ACTIVE_PROJECT_KEY] = normalized
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


def _ensure_stored(stored: Mapping[str, Any] | None) -> dict[str, Any]:
    if stored is None:
        return load_stored_config()
    return _sanitize_stored_payload(stored)


def _effective_store(
    stored: Mapping[str, Any],
    project_values: Mapping[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key in RUNTIME_SETTING_KEYS:
        if key in stored:
            merged[key] = stored[key]
    for key in RUNTIME_SETTING_KEYS:
        if key in project_values:
            merged[key] = project_values[key]
    return merged


def _sanitize_stored_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}

    for key, value in payload.items():
        if key in RUNTIME_SETTING_KEYS:
            sanitized = _sanitize_runtime_value(key, value)
            if sanitized is not None:
                out[key] = sanitized
            continue

        if key == ACTIVE_PROJECT_KEY:
            active = _normalize_project_name(value)
            if active is not None:
                out[key] = active
            continue

        if key == PROJECTS_KEY:
            projects = _sanitize_projects(value)
            if projects:
                out[key] = projects
            continue

    return out


def _sanitize_projects(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}

    out: dict[str, dict[str, Any]] = {}
    for name, raw_project in value.items():
        if not isinstance(raw_project, dict):
            continue
        project_name = _normalize_project_name(name)
        if project_name is None:
            continue

        sanitized = _sanitize_project_values(raw_project)
        if sanitized:
            out[project_name] = sanitized
    return out


def _sanitize_project_values(values: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in values.items():
        if key in RUNTIME_SETTING_KEYS:
            sanitized = _sanitize_runtime_value(key, value)
            if sanitized is not None:
                out[key] = sanitized
            continue

        if key == PROJECT_DESCRIPTION_KEY:
            description = _optional_string(value)
            if description is not None:
                out[key] = description
            continue
    return out


def _sanitize_runtime_value(key: str, value: Any) -> Any | None:
    if key in _STRING_RUNTIME_KEYS:
        return _optional_string(value)
    if key in _INT_RUNTIME_KEYS:
        return _int_or_none(value)
    if key in _FLOAT_RUNTIME_KEYS:
        return _float_or_none(value)
    return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _normalize_project_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


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
