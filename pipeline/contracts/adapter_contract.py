from __future__ import annotations
import hashlib
from pathlib import Path
import json
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SourceArtifact:
    """Immutable acquisition facts supplied to a source adapter."""
    source_url: str
    retrieved_at_utc: str
    sha256: str
    byte_size: int
    publication_date: str | None = None
    effective_date: str | None = None
    code_version: str = "unknown"
    config_version: str = "unknown"
    rights_caveat: str | None = None
    privacy_caveat: str | None = None
    coverage: str | None = None


class SourceAdapter(Protocol):
    """Minimal boundary between acquisition evidence and private staging."""
    source_id: str
    adapter_version: str

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]: ...


def assert_manifest(manifest: dict, raw: bytes, schema_version: str) -> None:
    """Assert safety invariants shared by adapter tests; not a release gate."""
    assert manifest["checksum_sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["byte_size"] == len(raw)
    assert manifest["schema_version"] == schema_version
    assert manifest["input_rows"] == manifest["normalized_rows"] + manifest["quarantined_rows"]
    assert manifest["release_state"] == "not-created"


def read_jsonl(path: Path) -> list[dict]:
    """Read deterministic staging records for test and review tooling."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
