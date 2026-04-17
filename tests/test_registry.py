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


def test_category_registry_contains_expected_categories() -> None:
    registry = OperationRegistry.load(refresh_specs=False)

    cloud_servers = registry.get_category("cloud:servers")
    storage_boxes = registry.get_category("storage:storage_boxes")

    assert cloud_servers.name == "Servers"
    assert cloud_servers.tool_name == "category_guide_cloud_servers"
    assert "create_server" in cloud_servers.operation_ids

    assert storage_boxes.name == "Storage Boxes"
    assert storage_boxes.tool_name == "category_guide_storage_storage_boxes"
    assert "create_storage_box" in storage_boxes.operation_ids
