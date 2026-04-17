from __future__ import annotations

from hetzner_mcp.registry import OperationRegistry


def test_registry_operation_counts() -> None:
    registry = OperationRegistry.load(refresh_specs=False)
    counts = registry.counts_by_domain()

    assert counts["cloud"] == 189
    assert counts["storage"] == 32
    assert registry.operation_count == 221


def test_known_operation_ids_exist() -> None:
    registry = OperationRegistry.load(refresh_specs=False)

    assert registry.get("create_server").path == "/servers"
    assert registry.get("get_action").path == "/actions/{id}"
    assert registry.get("create_storage_box").path == "/storage_boxes"
    assert registry.get("get_storage_boxes_action").path == "/storage_boxes/actions/{id}"
