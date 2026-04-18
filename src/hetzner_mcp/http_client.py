"""HTTP client for executing Hetzner API operations."""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .models import ApiDomain, HttpResult, OperationSpec


@dataclass(slots=True)
class RuntimeConfig:
    """Runtime settings and credentials for API calls."""

    token_default: str | None
    token_cloud: str | None
    token_storage: str | None
    cloud_base_url: str = "https://api.hetzner.cloud/v1"
    storage_base_url: str = "https://api.hetzner.com/v1"
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_base_seconds: float = 0.5
    user_agent: str = "hetzner-mcp/0.1.5"

    def token_for(self, api_domain: ApiDomain) -> str | None:
        if api_domain == "cloud":
            return self.token_cloud or self.token_default
        return self.token_storage or self.token_default

    def base_url_for(self, api_domain: ApiDomain) -> str:
        return self.cloud_base_url if api_domain == "cloud" else self.storage_base_url


class HetznerHttpClient:
    """Transport wrapper with retry and JSON parsing behavior."""

    RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    def execute(
        self,
        *,
        operation: OperationSpec,
        path_params: dict[str, Any],
        query_params: dict[str, Any],
        body: Any | None,
    ) -> HttpResult:
        token = self.config.token_for(operation.api_domain)
        if not token:
            return HttpResult(
                ok=False,
                status_code=0,
                headers={},
                data={
                    "error": {
                        "code": "missing_token",
                        "message": (
                            "No API token configured. Set HETZNER_TOKEN (or "
                            "HETZNER_CLOUD_TOKEN/HETZNER_STORAGE_TOKEN)."
                        ),
                    }
                },
                raw_text="",
                request_url="",
                retries=0,
            )

        request_url = self._build_url(
            operation=operation,
            path_params=path_params,
            query_params=query_params,
        )

        payload: bytes | None = None
        headers: dict[str, str] = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": self.config.user_agent,
        }
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        attempts = 0
        while True:
            attempts += 1
            status_code, response_headers, raw_text, data = self._perform_request(
                url=request_url,
                method=operation.method,
                headers=headers,
                body=payload,
            )

            should_retry = (
                status_code in self.RETRY_STATUS_CODES and attempts <= self.config.max_retries
            )
            if should_retry:
                self._sleep_backoff(attempt=attempts)
                continue

            return HttpResult(
                ok=200 <= status_code < 300,
                status_code=status_code,
                headers=response_headers,
                data=data,
                raw_text=raw_text,
                request_url=request_url,
                retries=max(0, attempts - 1),
            )

    def _build_url(
        self,
        *,
        operation: OperationSpec,
        path_params: dict[str, Any],
        query_params: dict[str, Any],
    ) -> str:
        path = operation.path
        for parameter in operation.parameters:
            if parameter.location != "path":
                continue
            value = path_params[parameter.name]
            encoded = urllib.parse.quote(str(value), safe="")
            path = path.replace("{" + parameter.name + "}", encoded)

        base = self.config.base_url_for(operation.api_domain).rstrip("/")
        url = f"{base}{path}"

        query_items: list[tuple[str, str]] = []
        for key, value in query_params.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                for item in value:
                    query_items.append((key, _stringify_query(item)))
            else:
                query_items.append((key, _stringify_query(value)))

        if query_items:
            return f"{url}?{urllib.parse.urlencode(query_items, doseq=True)}"
        return url

    def _perform_request(
        self,
        *,
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> tuple[int, dict[str, str], str, Any]:
        request = urllib.request.Request(url=url, data=body, method=method, headers=headers)

        response_headers: dict[str, str] = {}
        raw_text = ""
        status_code = 0
        data: Any = None

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                status_code = int(response.getcode())
                response_headers = {k: v for k, v in response.headers.items()}
                raw_bytes = response.read()
                raw_text = raw_bytes.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status_code = int(exc.code)
            response_headers = {k: v for k, v in exc.headers.items()} if exc.headers else {}
            raw_text = exc.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            status_code = 0
            raw_text = str(exc.reason)

        if raw_text:
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                data = None
        return status_code, response_headers, raw_text, data

    def _sleep_backoff(self, *, attempt: int) -> None:
        backoff = self.config.backoff_base_seconds * (2 ** (attempt - 1))
        jitter = random.uniform(0.0, 0.2)
        time.sleep(min(backoff + jitter, 5.0))


def _stringify_query(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
