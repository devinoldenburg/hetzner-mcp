from __future__ import annotations

from typing import Any

import hetzner_mcp.capabilities as capabilities
from hetzner_mcp.models import HttpResult


class _FakeClient:
    def __init__(self, _: object) -> None:
        pass

    def execute(
        self,
        *,
        operation: Any,
        path_params: dict[str, Any],
        query_params: dict[str, Any],
        body: object | None,
    ) -> HttpResult:
        _ = (path_params, query_params, body)
        status = _status_for(domain=str(operation.api_domain), method=str(operation.method))
        return HttpResult(
            ok=200 <= status < 300,
            status_code=status,
            headers={},
            data=None,
            raw_text="",
            request_url="https://example.invalid",
            retries=0,
        )


def _status_for(*, domain: str, method: str) -> int:
    if domain == "cloud" and method == "GET":
        return 200
    if domain == "cloud" and method == "POST":
        return 422
    if domain == "storage" and method == "GET":
        return 401
    if domain == "storage" and method == "POST":
        return 401
    return 0


def test_detect_api_key_capabilities_maps_probe_statuses_to_capability_levels(
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(capabilities, "HetznerHttpClient", _FakeClient)

    detected = capabilities.detect_api_key_capabilities(
        token="abc123",
        cloud_base_url="https://api.hetzner.cloud/v1",
        storage_base_url="https://api.hetzner.com/v1",
        timeout_seconds=30.0,
        user_agent="hetzner-mcp/test",
    )

    assert len(detected) == 2
    assert detected[0].api_domain == "cloud"
    assert detected[0].level == "read+write"
    assert detected[1].api_domain == "storage"
    assert detected[1].level == "no-access"
