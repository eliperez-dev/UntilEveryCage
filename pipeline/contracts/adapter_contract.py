from __future__ import annotations
import hashlib
from pathlib import Path
import json


def assert_manifest(manifest: dict, raw: bytes, schema_version: str) -> None:
    assert manifest["checksum_sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["byte_size"] == len(raw)
    assert manifest["schema_version"] == schema_version
    assert manifest["input_rows"] == manifest["normalized_rows"] + manifest["quarantined_rows"]
    assert manifest["release_state"] == "not-created"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
