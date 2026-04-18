"""API token capability probes for CLI auth flows."""

from __future__ import annotations

from dataclasses import dataclass

from .http_client import HetznerHttpClient, RuntimeConfig
from .models import ApiDomain, HttpResult, OperationSpec

_ACCESS_DENIED_STATUS_CODES = frozenset({401, 403})
_WRITE_VALIDATION_STATUS_CODES = frozenset({400, 405, 409, 415, 422})
_READ_PROBE_PATHS: dict[ApiDomain, str] = {
    "cloud": "/servers",
    "storage": "/storage_boxes",
}


@dataclass(slots=True, frozen=True)
class DomainCapability:
    """Detected capabilities for one API domain."""

    api_domain: ApiDomain
    read_access: bool | None
    write_access: bool | None
    read_status_code: int
    write_status_code: int

    @property
    def level(self) -> str:
        if self.read_access is True and self.write_access is True:
            return "read+write"
        if self.read_access is True and self.write_access is False:
            return "read-only"
        if self.read_access is False and self.write_access is False:
            return "no-access"
        if self.read_access is False and self.write_access is True:
            return "write-only"
        if self.read_access is True and self.write_access is None:
            return "read (write unknown)"
        if self.read_access is None and self.write_access is False:
            return "no-write (read unknown)"
        return "unknown"


def detect_api_key_capabilities(
    *,
    token: str,
    cloud_base_url: str,
    storage_base_url: str,
    timeout_seconds: float,
    user_agent: str,
    domains: tuple[ApiDomain, ...] = ("cloud", "storage"),
) -> list[DomainCapability]:
    """Probe token read/write capabilities using safe representative endpoints."""
    clean_token = token.strip()
    if not clean_token:
        return []

    requested_domains = _normalized_domains(domains)
    if not requested_domains:
        return []

    probe_timeout_seconds = min(max(timeout_seconds, 1.0), 2.0)
    client = HetznerHttpClient(
        RuntimeConfig(
            token_default=clean_token,
            token_cloud=None,
            token_storage=None,
            cloud_base_url=cloud_base_url,
            storage_base_url=storage_base_url,
            timeout_seconds=probe_timeout_seconds,
            max_retries=0,
            backoff_base_seconds=0.1,
            user_agent=user_agent,
        )
    )

    results: list[DomainCapability] = []
    for domain in requested_domains:
        read_result = _execute_probe(client=client, api_domain=domain, method="GET", body=None)
        write_result = _execute_probe(client=client, api_domain=domain, method="POST", body={})
        results.append(
            DomainCapability(
                api_domain=domain,
                read_access=_read_access_from_status(read_result.status_code),
                write_access=_write_access_from_status(write_result.status_code),
                read_status_code=read_result.status_code,
                write_status_code=write_result.status_code,
            )
        )

    return results


def _normalized_domains(domains: tuple[ApiDomain, ...]) -> tuple[ApiDomain, ...]:
    unique: list[ApiDomain] = []
    for domain in domains:
        if domain not in {"cloud", "storage"}:
            continue
        if domain in unique:
            continue
        unique.append(domain)
    return tuple(unique)


def _execute_probe(
    *,
    client: HetznerHttpClient,
    api_domain: ApiDomain,
    method: str,
    body: object | None,
) -> HttpResult:
    operation = OperationSpec(
        operation_id=f"probe_{api_domain}_{method.lower()}",
        api_domain=api_domain,
        method=method,
        path=_READ_PROBE_PATHS[api_domain],
        tags=(),
        summary=None,
        description=None,
    )
    return client.execute(
        operation=operation,
        path_params={},
        query_params={},
        body=body,
    )


def _read_access_from_status(status_code: int) -> bool | None:
    if 200 <= status_code < 300:
        return True
    if status_code in _ACCESS_DENIED_STATUS_CODES:
        return False
    if status_code == 0:
        return None
    return None


def _write_access_from_status(status_code: int) -> bool | None:
    if status_code in _ACCESS_DENIED_STATUS_CODES:
        return False
    if 200 <= status_code < 300:
        return True
    if status_code in _WRITE_VALIDATION_STATUS_CODES:
        return True
    if status_code == 0:
        return None
    return None
