#!/usr/bin/env python3
"""Verify that expected Hetzner operation counts are fully loaded."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

EXPECTED_CLOUD = 189
EXPECTED_STORAGE = 32
EXPECTED_TOTAL = 221


def main() -> int:
    from hetzner_mcp.registry import OperationRegistry

    registry = OperationRegistry.load(refresh_specs=False)
    counts = registry.counts_by_domain()

    cloud = counts["cloud"]
    storage = counts["storage"]
    total = registry.operation_count
    categories = len(registry.all_categories())

    print(f"cloud={cloud} storage={storage} total={total} categories={categories}")

    if cloud != EXPECTED_CLOUD or storage != EXPECTED_STORAGE or total != EXPECTED_TOTAL:
        print("Coverage verification failed")
        return 1

    print("Coverage verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
