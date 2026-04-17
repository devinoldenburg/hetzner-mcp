#!/usr/bin/env python3
"""Fetch and cache Hetzner OpenAPI specs used by the server."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hetzner_mcp.registry import OperationRegistry


def main() -> int:
    registry = OperationRegistry.load(refresh_specs=True)
    print(
        json.dumps(
            {
                "operation_count": registry.operation_count,
                "counts_by_domain": registry.counts_by_domain(),
                "counts_by_tag": registry.counts_by_tag(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
