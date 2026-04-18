"""Loading and resolving Hetzner OpenAPI specs."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import SpecLoadError

CLOUD_SPEC_URL = "https://docs.hetzner.cloud/cloud.spec.json"
STORAGE_SPEC_URL = "https://docs.hetzner.cloud/hetzner.spec.json"

_CACHE_DIR = Path.home() / ".cache" / "hetzner-mcp"
_CLOUD_CACHE = _CACHE_DIR / "cloud.spec.json"
_STORAGE_CACHE = _CACHE_DIR / "hetzner.spec.json"


@dataclass(slots=True, frozen=True)
class LoadedSpecs:
    """Container for both Hetzner OpenAPI specs."""

    cloud: dict[str, Any]
    storage: dict[str, Any]


def load_specs(*, refresh: bool = False, timeout_seconds: float = 20.0) -> LoadedSpecs:
    """Load cloud and storage specs from cache and/or network.

    Behavior:
    - If refresh is False and cache exists, use cache first.
    - Otherwise fetch network and cache.
    - If fetch fails and cache exists, fall back to cache.
    """

    cloud = _load_single_spec(
        url=CLOUD_SPEC_URL,
        cache_path=_CLOUD_CACHE,
        refresh=refresh,
        timeout_seconds=timeout_seconds,
    )
    storage = _load_single_spec(
        url=STORAGE_SPEC_URL,
        cache_path=_STORAGE_CACHE,
        refresh=refresh,
        timeout_seconds=timeout_seconds,
    )

    _validate_spec_root(cloud, expected_server_prefix="https://api.hetzner.cloud")
    _validate_spec_root(storage, expected_server_prefix="https://api.hetzner.com")

    return LoadedSpecs(cloud=cloud, storage=storage)


def _load_single_spec(
    *,
    url: str,
    cache_path: Path,
    refresh: bool,
    timeout_seconds: float,
) -> dict[str, Any]:
    if not refresh and cache_path.exists():
        return _read_json_file(cache_path)

    try:
        spec = _fetch_json(url=url, timeout_seconds=timeout_seconds)
    except SpecLoadError:
        if cache_path.exists():
            return _read_json_file(cache_path)
        raise

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return spec


def _fetch_json(*, url: str, timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": "application/json", "User-Agent": _user_agent()},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_bytes = response.read()
    except urllib.error.HTTPError as exc:
        raise SpecLoadError(
            code="spec_http_error",
            message=f"Failed to fetch spec from {url} ({exc.code})",
            details={"url": url, "status_code": exc.code},
        ) from exc
    except urllib.error.URLError as exc:
        raise SpecLoadError(
            code="spec_network_error",
            message=f"Failed to fetch spec from {url}: {exc.reason}",
            details={"url": url},
        ) from exc

    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SpecLoadError(
            code="spec_json_error",
            message=f"Spec payload from {url} is not valid JSON",
            details={"url": url},
        ) from exc

    if not isinstance(payload, dict):
        raise SpecLoadError(
            code="spec_shape_error",
            message=f"Spec payload from {url} is not an object",
            details={"url": url},
        )

    return payload


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecLoadError(
            code="spec_cache_error",
            message=f"Could not read cached spec file: {path}",
            details={"path": str(path)},
        ) from exc

    if not isinstance(payload, dict):
        raise SpecLoadError(
            code="spec_cache_shape_error",
            message=f"Cached spec file is not a JSON object: {path}",
            details={"path": str(path)},
        )
    return payload


def _validate_spec_root(spec: dict[str, Any], *, expected_server_prefix: str) -> None:
    if "openapi" not in spec:
        raise SpecLoadError(
            code="spec_missing_openapi",
            message="OpenAPI version field missing in spec",
        )

    if not isinstance(spec.get("paths"), dict) or not spec["paths"]:
        raise SpecLoadError(
            code="spec_missing_paths",
            message="Spec paths are missing or empty",
        )

    servers = spec.get("servers", [])
    if not isinstance(servers, list) or not servers:
        raise SpecLoadError(
            code="spec_missing_servers",
            message="Spec servers are missing",
        )

    first_url = str(servers[0].get("url", ""))
    if not first_url.startswith(expected_server_prefix):
        raise SpecLoadError(
            code="spec_server_mismatch",
            message="Spec server URL does not match expected API domain",
            details={
                "expected_prefix": expected_server_prefix,
                "actual": first_url,
            },
        )


def resolve_refs(value: Any, *, spec: dict[str, Any], _stack: tuple[str, ...] = ()) -> Any:
    """Resolve local OpenAPI references recursively.

    Supports object-level `$ref` and `allOf` composition.
    """
    if isinstance(value, list):
        return [resolve_refs(item, spec=spec, _stack=_stack) for item in value]

    if not isinstance(value, dict):
        return value

    if "$ref" in value:
        ref = value["$ref"]
        if not isinstance(ref, str):
            return deepcopy(value)
        if not ref.startswith("#/"):
            raise SpecLoadError(
                code="spec_external_ref_unsupported",
                message=f"Only local refs are supported, got: {ref}",
            )
        if ref in _stack:
            raise SpecLoadError(
                code="spec_ref_cycle",
                message=f"Detected cyclic $ref resolution at {ref}",
            )

        target = _resolve_local_ref(ref=ref, spec=spec)
        merged = deepcopy(target)
        for key, current in value.items():
            if key == "$ref":
                continue
            if key == "required" and isinstance(current, list):
                existing_required = merged.get("required", [])
                if isinstance(existing_required, list):
                    merged["required"] = sorted(set(str(x) for x in existing_required + current))
                else:
                    merged["required"] = current
            else:
                merged[key] = current
        return resolve_refs(merged, spec=spec, _stack=(*_stack, ref))

    if "allOf" in value and isinstance(value["allOf"], list):
        combined: dict[str, Any] = {}
        properties: dict[str, Any] = {}
        required: list[str] = []

        for part in value["allOf"]:
            resolved_part = resolve_refs(part, spec=spec, _stack=_stack)
            if not isinstance(resolved_part, dict):
                continue
            for key, sub_value in resolved_part.items():
                if key == "properties" and isinstance(sub_value, dict):
                    properties.update(sub_value)
                elif key == "required" and isinstance(sub_value, list):
                    required.extend(str(x) for x in sub_value)
                elif key == "allOf":
                    continue
                else:
                    combined[key] = sub_value

        if properties:
            combined["properties"] = properties
        if required:
            combined["required"] = sorted(set(required))

        for key, sub_value in value.items():
            if key == "allOf":
                continue
            combined[key] = resolve_refs(sub_value, spec=spec, _stack=_stack)
        return combined

    return {
        key: resolve_refs(sub_value, spec=spec, _stack=_stack) for key, sub_value in value.items()
    }


def _resolve_local_ref(*, ref: str, spec: dict[str, Any]) -> Any:
    path_parts = ref[2:].split("/")
    current: Any = spec
    for raw_part in path_parts:
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise SpecLoadError(
                code="spec_ref_not_found",
                message=f"Reference not found: {ref}",
            )
        current = current[part]
    return current


def _user_agent() -> str:
    version = os.environ.get("HETZNER_MCP_VERSION", "0.1.6")
    return f"hetzner-mcp/{version}"
