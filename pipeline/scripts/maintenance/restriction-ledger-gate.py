"""Fail-closed contract for replaying an external current-restriction ledger.

This module deliberately does not select a ledger operator, retention policy,
or production activation mechanism. It verifies a supplied, already-authorized
ledger snapshot before a restored database may be served.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


class RestrictionLedgerError(ValueError):
    """The ledger is missing, malformed, stale, or not fully applied."""


def ledger_digest(ledger: dict[str, Any]) -> str:
    """Hash only the versioned, row-free control-plane projection."""
    payload = {
        "schema_version": ledger.get("schema_version"),
        "revision": ledger.get("revision"),
        "active_restrictions": ledger.get("active_restrictions"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_ledger(path: str | Path) -> dict[str, Any]:
    ledger_path = Path(path)
    if not ledger_path.is_file():
        raise RestrictionLedgerError("restriction ledger is unavailable")
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RestrictionLedgerError("restriction ledger cannot be read") from exc
    if not isinstance(ledger, dict) or ledger.get("schema_version") != 1:
        raise RestrictionLedgerError("restriction ledger schema is unsupported")
    if not isinstance(ledger.get("revision"), str) or not ledger["revision"]:
        raise RestrictionLedgerError("restriction ledger revision is missing")
    if not isinstance(ledger.get("ledger_sha256"), str) or ledger["ledger_sha256"] != ledger_digest(ledger):
        raise RestrictionLedgerError("restriction ledger digest is invalid")
    restrictions = ledger.get("active_restrictions")
    if not isinstance(restrictions, list) or any(
        not isinstance(item, dict)
        or item.get("action") != "suppress"
        for item in restrictions
    ):
        raise RestrictionLedgerError("restriction ledger restrictions are invalid")
    return ledger


def verify_replayed_restrictions(snapshot: dict[str, Any], ledger: dict[str, Any]) -> None:
    """Fail closed unless the restored DB reports every current restriction.

    Comparison uses opaque source/record keys only; restricted payloads are not
    copied into errors. The service must remain stopped when this raises.
    """
    if snapshot.get("ledger_revision") != ledger["revision"]:
        raise RestrictionLedgerError("restored restriction revision is not current")
    if snapshot.get("ledger_sha256") != ledger["ledger_sha256"]:
        raise RestrictionLedgerError("restored restriction digest is not current")
    applied = snapshot.get("active_restrictions")
    expected = ledger["active_restrictions"]
    if not isinstance(applied, list):
        raise RestrictionLedgerError("restored restriction state is unavailable")

    def key(item: dict[str, Any]) -> tuple[str, str, str]:
        values = tuple(item.get(field) for field in ("source_id", "source_record_key", "scope", "action"))
        if any(not isinstance(value, str) or not value for value in values):
            raise RestrictionLedgerError("restriction reference is incomplete")
        if values[3] != "suppress":
            raise RestrictionLedgerError("restriction action is unsupported")
        return values

    expected_keys = {key(item) for item in expected}
    applied_keys = {key(item) for item in applied}
    if len(expected_keys) != len(expected) or len(applied_keys) != len(applied):
        raise RestrictionLedgerError("restriction references are duplicated")
    if expected_keys != applied_keys:
        raise RestrictionLedgerError("restored restrictions do not match current ledger")


def pre_service_gate(ledger_path: str | Path, restored_snapshot: dict[str, Any]) -> None:
    """Verify a restored snapshot before a local/test service may start."""
    verify_replayed_restrictions(restored_snapshot, load_ledger(ledger_path))


def verify_v1_v2_crosswalk(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic mappings; never guess when a key is ambiguous."""
    mapped: dict[str, str] = {}
    unresolved: list[dict[str, str]] = []
    for row in rows:
        v1_id, v2_id = row.get("v1_id"), row.get("v2_id")
        if not isinstance(v1_id, str) or not isinstance(v2_id, str) or not v1_id or not v2_id:
            unresolved.append({"reason": "missing_identifier"})
            continue
        prior = mapped.get(v1_id)
        if prior is not None and prior != v2_id:
            mapped.pop(v1_id)
            unresolved.append({"v1_id": v1_id, "reason": "ambiguous_mapping"})
            continue
        mapped[v1_id] = v2_id
    return {"mapped": mapped, "unresolved": unresolved}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--snapshot", required=True)
    args = parser.parse_args()
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    pre_service_gate(args.ledger, snapshot)
    print("PASS: current restriction ledger verified before service start")
