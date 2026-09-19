"""Load the versioned, source-agnostic adapter capability registry."""
from __future__ import annotations

import json
from pathlib import Path


def load(path: str | Path) -> dict:
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    if registry.get("schema_version") != "adapter-capabilities-v1":
        raise ValueError("unsupported adapter capability schema")
    seen: set[str] = set()
    for entry in registry.get("adapters", []):
        for field in ("country_code", "adapter_version", "schema_version", "adapter_path", "source_id"):
            if not entry.get(field):
                raise ValueError(f"adapter entry missing {field}")
        if entry["source_id"] in seen:
            raise ValueError(f"duplicate registered source: {entry['source_id']}")
        seen.add(entry["source_id"])
    return registry
