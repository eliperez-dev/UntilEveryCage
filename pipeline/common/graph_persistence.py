"""Private, append-only persistence for D4 graph handoffs.

This module is the database boundary after an adapter has produced a validated
private handoff.  It deliberately does not infer identity: source-native
facilities and organizations are stored as source-qualified projections,
uncertain links remain candidate edges, and evidence events use a separate
sink from facility candidates.

The importer is suitable only for a loopback disposable database.  Results are
aggregate-only so callers do not accidentally print private rows or payloads.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

import psycopg

from pipeline.contracts.graph_candidate_handoff import (
    CONTRACT_VERSION as GRAPH_CONTRACT_VERSION,
    canonical_json_bytes,
    validate_graph_candidate,
)
from pipeline.common.graph_edges import (
    EntityRef,
    SourceRef,
    build_connection_edge,
    connection_edge_key,
    persist_connection_edges,
    score_connection,
    validate_connection_edge,
)
from pipeline.common.graph_source_mapping import FACILITY_IDENTIFIERS


DISPOSABLE_MARKER = "uec-e2e-disposable-v1"
EVIDENCE_HANDOFF_VERSION = "us-aphis-observation-handoff-v1"
DEFAULT_BATCH_SIZE = 250
_FORBIDDEN_IDENTITY_KEYS = {
    "canonical_id", "global_id", "universal_id", "universal_identity",
    "global_identity", "master_id", "entity_id",
}
BatchCommitObserver = Callable[[int, int, int], None]
ConnectionEdgeBuilder = Callable[[dict[str, Any], dict[str, Any]], Iterable[dict[str, Any]]]


def _peak_rss_bytes() -> int | None:
    """Best-effort process RSS instrumentation without adding a dependency."""
    try:
        import psutil  # type: ignore
        return int(psutil.Process().memory_info().rss)
    except Exception:
        try:
            import resource  # type: ignore
            value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            return value * (1024 if os.name != "nt" else 1)
        except Exception:
            return None


def _native_matcher_endpoint(ref: EntityRef) -> EntityRef:
    """Restore the source adapter's declared facility identifier type.

    The matcher may use the generic field name ``establishment_id`` for
    blocking and candidate construction. Persisted graph endpoints must use
    the source-specific identifier type from the existing adapter registry.
    Only this exact generic facility shape is normalized; values, source IDs,
    organization endpoints, and already-native identifier types are unchanged.
    """
    if ref.entity_type != "facility" or ref.identifier_type != "establishment_id":
        return ref
    declared = FACILITY_IDENTIFIERS.get(ref.source_id)
    if declared is None:
        return ref
    return EntityRef(ref.entity_type, ref.source_id, declared[0], ref.source_identifier)

# These are evidence/event sources, not facility-master identity sources.  In
# particular, an APHIS observation must never be asserted to be an FSIS
# establishment merely because the two rows happen to share a name or number.
_APHIS_FSIS_SOURCES = frozenset({"us.aphis", "us.inspections"})
_FSIS_SOURCES = frozenset({"us.fsis"})


class GraphPersistenceError(ValueError):
    """A handoff or database target violated the private graph boundary."""


def require_disposable_graph_database(database_url: str, acknowledged: bool = False) -> None:
    """Reject shared, production-looking, and default-port database targets."""
    if not acknowledged:
        raise GraphPersistenceError("refusing graph import: pass --disposable-db explicitly")
    parsed = urlparse(database_url)
    if (parsed.hostname or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise GraphPersistenceError("refusing graph import: database host is not loopback")
    if parsed.port in (None, 5432):
        raise GraphPersistenceError("refusing graph import: database must use a non-default port")
    database = (parsed.path or "").lstrip("/").lower()
    if not database.startswith("uec"):
        raise GraphPersistenceError("refusing graph import: database name is not a UEC disposable database")


def require_private_graph_target(database_url: str, *, expected_database: str, purpose: str) -> None:
    """Validate an explicitly configured ordinary private graph target.

    This separate gate intentionally does not weaken or bypass the disposable
    graph importer. The caller must provide the expected database name and a
    purpose string from its private operator configuration.
    """
    if purpose != "private-graph-materialization-v1":
        raise GraphPersistenceError("refusing graph materialization: purpose is not authorized")
    normalized_database = expected_database.casefold()
    forbidden_name_tokens = ("prod", "production", "retained", "frozen", "reference", "v0_")
    if (not expected_database or not normalized_database.startswith("uec_")
            or any(token in normalized_database for token in forbidden_name_tokens)):
        raise GraphPersistenceError("refusing graph materialization: an approved private target name is required")
    parsed = urlparse(database_url)
    if (parsed.hostname or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise GraphPersistenceError("refusing graph materialization: database host is not loopback")
    database = (parsed.path or "").lstrip("/")
    if database != expected_database:
        raise GraphPersistenceError("refusing graph materialization: database does not match configured target")
    if not database.startswith("uec"):
        raise GraphPersistenceError("refusing graph materialization: target name is not UEC-scoped")


_PRIVATE_GRAPH_REQUIRED_PRIVILEGES = {
    "sources": {"SELECT", "INSERT"},
    "raw_artifacts": {"SELECT", "INSERT"},
    "source_records": {"SELECT", "INSERT"},
    "releases": {"SELECT"},
    "map_facilities_public_discovery_read_model": {"SELECT"},
    "facilities": {"SELECT", "INSERT"},
    "organizations": {"SELECT", "INSERT"},
    "source_entity_identifiers": {"SELECT", "INSERT"},
    "source_entity_crosswalks": {"SELECT", "INSERT"},
    "organization_relationship_observations": {"SELECT", "INSERT"},
    "graph_record_release_bindings": {"SELECT", "INSERT"},
    "claims": {"SELECT", "INSERT"},
    "claim_support": {"SELECT", "INSERT"},
    "graph_ingest_runs": {"SELECT", "INSERT", "UPDATE"},
    "graph_ingest_items": {"SELECT", "INSERT"},
    "graph_evidence_events": {"SELECT", "INSERT"},
    "graph_evidence_links": {"SELECT", "INSERT"},
    "graph_connection_edges": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "graph_edge_materialization_runs": {"SELECT", "INSERT", "UPDATE"},
    "graph_public_projection_builds": {"SELECT", "INSERT", "UPDATE"},
    "graph_public_projection_edges": {"SELECT", "INSERT"},
    "graph_public_projection_edge_supports": {"SELECT", "INSERT"},
    "graph_public_projection_endpoints": {"SELECT", "INSERT"},
    "graph_public_projection_anchors": {"SELECT", "INSERT"},
    "graph_public_projection_evidence_refs": {"SELECT", "INSERT"},
    "graph_source_name_assertions": {"SELECT", "INSERT"},
    "graph_public_projection_org_labels": {"SELECT", "INSERT"},
    "graph_public_projection_endpoint_anchors": {"SELECT", "INSERT"},
}
_PRIVATE_GRAPH_REQUIRED_READ_PRIVILEGES = {
    "graph_projection_generation": {"SELECT"},
    # The selected-release selectors directly test whether a candidate source
    # record participates in public facility membership; these two private
    # tables are needed to keep event references out of facility membership.
    "observations": {"SELECT"},
    "release_members": {"SELECT"},
    # The projection builder must verify the same public-release, manifest,
    # history, and suppression gates that make its output servable.
    "public_discovery_read_models": {"SELECT"},
    "release_manifests": {"SELECT"},
    "public_release_history": {"SELECT"},
    "public_suppression_generation": {"SELECT"},
    # Typed evidence and organization labels are projected only after these
    # exact selected-release review, metadata-clearance, and restriction checks.
    "publication_review_release_current": {"SELECT"},
    "source_rights_decisions": {"SELECT"},
    "graph_public_evidence_metadata_clearance_current": {"SELECT"},
    "public_access_restricted": {"SELECT"},
}
_PRIVATE_GRAPH_REQUIRED_FUNCTION_PRIVILEGES = {
    "uec.is_valid_italian_vat_identifier(text,text,text)": {"EXECUTE"},
}


def _validate_private_graph_writer(connection: Any, expected_database: str) -> None:
    row = connection.execute("SELECT current_database(), current_user").fetchone()
    if (not row or row[0] != expected_database or not str(row[1]).startswith("uec_graph_writer_")
            or row[1] in {"uec_api_runtime", "uec_release_operator"}):
        raise GraphPersistenceError("refusing graph materialization: database role is not a private writer")
    role_flags = connection.execute(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
        "FROM pg_roles WHERE rolname=current_user"
    ).fetchone()
    if not role_flags or any(role_flags):
        raise GraphPersistenceError("refusing graph materialization: privileged database roles are not allowed")
    privileges = connection.execute(
        "SELECT table_schema, table_name, privilege_type FROM information_schema.role_table_grants "
        "WHERE grantee=current_user"
    ).fetchall()
    grants_by_table: dict[str, set[str]] = {}
    for schema_name, table_name, privilege in privileges:
        if schema_name == "uec":
            grants_by_table.setdefault(table_name, set()).add(privilege)
    required_privileges = {**_PRIVATE_GRAPH_REQUIRED_PRIVILEGES,
                           **_PRIVATE_GRAPH_REQUIRED_READ_PRIVILEGES}
    if any(not grants_by_table.get(table, set()).issuperset(required)
           for table, required in required_privileges.items()):
        raise GraphPersistenceError("refusing graph materialization: private graph writer grants are incomplete")
    write_tables = {(item[0], item[1]) for item in privileges
                    if item[2] in {"INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"}}
    allowed_writes = {("uec", table) for table in _PRIVATE_GRAPH_REQUIRED_PRIVILEGES}
    if not write_tables.issubset(allowed_writes):
        raise GraphPersistenceError("refusing graph materialization: role has writes outside graph tables")
    for function, required in _PRIVATE_GRAPH_REQUIRED_FUNCTION_PRIVILEGES.items():
        for privilege in required:
            granted = connection.execute(
                "SELECT has_function_privilege(current_user,%s,%s)", (function, privilege)
            ).fetchone()
            if not granted or not granted[0]:
                raise GraphPersistenceError("refusing graph materialization: private graph writer function grants are incomplete")


def _verify_disposable_marker(connection: psycopg.Connection[Any]) -> None:
    row = connection.execute(
        "SELECT marker FROM uec.disposable_import_guard "
        "WHERE marker=%s AND database_name=current_database() AND role_name=current_user",
        (DISPOSABLE_MARKER,),
    ).fetchone()
    if row != (DISPOSABLE_MARKER,):
        raise GraphPersistenceError("refusing graph import: exact disposable database marker is missing")


def _private_manifest(manifest: dict[str, Any], *, evidence: bool = False) -> None:
    if not isinstance(manifest, dict):
        raise GraphPersistenceError("handoff manifest must be an object")
    if manifest.get("release_state") not in {None, "not-created"}:
        raise GraphPersistenceError("promoted or released handoffs cannot enter private graph storage")
    if manifest.get("publication_state") not in {None, "private-candidate"}:
        raise GraphPersistenceError("handoff is not a private candidate")
    if manifest.get("storage_state") not in {None, "private"}:
        raise GraphPersistenceError("handoff storage state is not private")
    if manifest.get("publication_status") not in {None, "not_eligible"}:
        raise GraphPersistenceError("handoff publication status is not not_eligible")
    if manifest.get("release_id") is not None:
        raise GraphPersistenceError("handoff must not name a release")
    if evidence and manifest.get("entity_scope") != "evidence_event":
        raise GraphPersistenceError("evidence handoff must declare entity_scope=evidence_event")


def _reject_global_identity(value: Any, path: str = "handoff") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() in _FORBIDDEN_IDENTITY_KEYS:
                raise GraphPersistenceError(f"{path} must not assert a universal identity ({key})")
            _reject_global_identity(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_global_identity(child, f"{path}[{index}]")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphPersistenceError(f"cannot read handoff records: {path}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise GraphPersistenceError("handoff records must be JSON objects")
    return rows


def _candidate_paths(root: Path) -> tuple[Path, ...]:
    """Return candidate payload paths in the same deterministic order used by the loader."""
    adapter_jsonl = root / "graph-candidates.jsonl"
    if adapter_jsonl.is_file():
        return (adapter_jsonl,)
    records_path = root / "records.jsonl"
    if records_path.is_file():
        return (records_path,)
    paths = tuple(sorted(root.glob("*/graph-candidate.json")))
    if not paths:
        raise GraphPersistenceError("graph candidate handoff records are missing")
    return paths


def _iter_candidate_payloads(root: Path) -> Iterable[dict[str, Any]]:
    """Decode either the JSONL handoff or the legacy one-file-per-candidate form."""
    for records_path in _candidate_paths(root):
        if records_path.name in {"records.jsonl", "graph-candidates.jsonl"}:
            try:
                handle = records_path.open(encoding="utf-8")
            except OSError as exc:
                raise GraphPersistenceError(f"cannot read handoff records: {records_path}") from exc
            with handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        candidate = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise GraphPersistenceError(f"malformed graph candidate: {records_path}") from exc
                    if not isinstance(candidate, dict):
                        raise GraphPersistenceError("handoff records must be JSON objects")
                    yield candidate
        else:
            try:
                candidate = json.loads(records_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise GraphPersistenceError(f"malformed graph candidate: {records_path}") from exc
            if not isinstance(candidate, dict):
                raise GraphPersistenceError("handoff records must be JSON objects")
            yield candidate


def _graph_candidate_root(path: str | Path) -> tuple[Path, dict[str, Any]]:
    """Resolve a candidate handoff without reading its rows."""
    root = Path(path)
    if root.is_file():
        root = root.parent
    if (root / "graph-candidates" / "manifest.json").is_file():
        candidate_root = root / "graph-candidates"
        _, parent_manifest = _manifest_for(root)
        _, graph_manifest = _manifest_for(candidate_root)
        manifest = {**parent_manifest, **graph_manifest}
    elif (root / "graph" / "graph-candidates-manifest.json").is_file():
        candidate_root = root / "graph"
        try:
            graph_manifest = json.loads((candidate_root / "graph-candidates-manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GraphPersistenceError("graph candidate handoff manifest is malformed") from exc
        parent_manifest = {}
        if (root / "manifest.json").is_file():
            _, parent_manifest = _manifest_for(root)
        manifest = {**parent_manifest, **graph_manifest}
    elif (root / "graph-candidates-manifest.json").is_file():
        candidate_root = root
        try:
            graph_manifest = json.loads((root / "graph-candidates-manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GraphPersistenceError("graph candidate handoff manifest is malformed") from exc
        parent_manifest = {}
        if (root.parent / "manifest.json").is_file():
            _, parent_manifest = _manifest_for(root.parent)
        manifest = {**parent_manifest, **graph_manifest}
    elif (root / "manifest.json").is_file():
        candidate_root = root
        _, manifest = _manifest_for(root)
    else:
        raise GraphPersistenceError("graph candidate handoff root is not recognizable")
    _private_manifest(manifest)
    if manifest.get("contract_version") not in {None, "private-graph-candidate-set-v1", "private-graph-candidate-batch-v1", GRAPH_CONTRACT_VERSION}:
        raise GraphPersistenceError("unsupported graph candidate handoff contract")
    if manifest.get("source_kind", "facility_master") == "evidence_event":
        raise GraphPersistenceError("evidence-event handoffs must use the evidence importer")
    return candidate_root, manifest


def inspect_graph_candidate_handoff(path: str | Path) -> tuple[dict[str, Any], str, int]:
    """Validate a handoff in a streaming pass and return its digest and count.

    The importer uses this pass before opening a database transaction, then
    streams the same files a second time.  This preserves the checksum gate
    without retaining all private rows in process memory.
    """
    candidate_root, manifest = _graph_candidate_root(path)
    source_id = manifest.get("source_id")
    digest = hashlib.sha256()
    count = 0
    for candidate in _iter_candidate_payloads(candidate_root):
        _reject_global_identity(candidate)
        try:
            validate_graph_candidate(candidate)
        except ValueError as exc:
            raise GraphPersistenceError(str(exc)) from exc
        if source_id and candidate.get("source_id") != source_id:
            raise GraphPersistenceError("candidate source_id does not match handoff manifest")
        source_id = source_id or candidate["source_id"]
        digest.update(canonical_json_bytes(candidate))
        count += 1
    if not source_id:
        raise GraphPersistenceError("graph handoff requires source_id")
    value = digest.hexdigest()
    expected = manifest.get("records_sha256") or manifest.get("sha256")
    if expected and expected != value:
        raise GraphPersistenceError("graph candidate handoff checksum mismatch")
    expected_count = manifest.get("candidate_count")
    if expected_count is not None and expected_count != count:
        raise GraphPersistenceError("graph candidate handoff count mismatch")
    return {**manifest, "source_id": source_id, "source_kind": "facility_master"}, value, count


def iter_graph_candidate_handoff(path: str | Path) -> tuple[dict[str, Any], Iterable[dict[str, Any]], str, int]:
    """Return a validated, bounded-memory candidate stream.

    ``inspect_graph_candidate_handoff`` performs validation and digesting before
    this iterator is consumed.  The iterator itself only holds one decoded row.
    """
    manifest, digest, count = inspect_graph_candidate_handoff(path)
    candidate_root, _ = _graph_candidate_root(path)

    def stream() -> Iterable[dict[str, Any]]:
        yield from _iter_candidate_payloads(candidate_root)

    return manifest, stream(), digest, count


def _manifest_for(root: Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise GraphPersistenceError(f"handoff manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GraphPersistenceError("handoff manifest is malformed JSON") from exc
    return manifest_path, manifest


def load_graph_candidate_handoff(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Load and validate a facility graph-candidate handoff.

    ``path`` may be the graph-candidates directory, a candidate-handoff root,
    or a single candidate directory.  The returned digest covers canonical
    candidate bytes, not filesystem paths.
    """
    manifest, digest, _ = inspect_graph_candidate_handoff(path)
    candidate_root, _ = _graph_candidate_root(path)
    candidates: list[dict[str, Any]] = []
    candidates.extend(_iter_candidate_payloads(candidate_root))
    return manifest, candidates, digest


def load_evidence_handoff(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    root = Path(path)
    if root.is_file():
        root = root.parent
    _, manifest = _manifest_for(root)
    _private_manifest(manifest, evidence=True)
    if manifest.get("contract_version") != EVIDENCE_HANDOFF_VERSION:
        raise GraphPersistenceError("unsupported evidence-event handoff contract")
    records_path = root / "records.jsonl"
    if not records_path.is_file():
        raise GraphPersistenceError("evidence handoff records.jsonl is missing")
    payload = records_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if manifest.get("normalized_sha256") != digest:
        raise GraphPersistenceError("evidence handoff checksum mismatch")
    rows = _read_jsonl(records_path)
    if len(rows) != int(manifest.get("normalized_rows", -1)):
        raise GraphPersistenceError("evidence handoff row count mismatch")
    source_id = manifest.get("source_id")
    if not source_id:
        raise GraphPersistenceError("evidence handoff requires source_id")
    for row in rows:
        _reject_global_identity(row)
        if row.get("source_id") != source_id:
            raise GraphPersistenceError("evidence row source_id does not match manifest")
        normalized = row.get("normalized")
        if not isinstance(normalized, dict):
            raise GraphPersistenceError("evidence row requires normalized object")
        key = row.get("source_record_key") or normalized.get("source_observation_key")
        if not isinstance(key, str) or not key.strip():
            raise GraphPersistenceError("evidence row requires source-native event key")
    return {**manifest, "source_id": source_id, "source_kind": "evidence_event"}, rows, digest


def _stable_uuid(*parts: object) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "uec:d4:graph:" + "|".join(str(part) for part in parts))


def _timestamp(manifest: dict[str, Any]) -> str:
    value = manifest.get("retrieved_at_utc") or manifest.get("observed_at")
    return str(value) if value else datetime.now(timezone.utc).isoformat()


def _observed_at(value: Any, manifest: dict[str, Any]) -> str:
    """Use the handoff timestamp when a source date is explicitly unknown."""
    if value:
        candidate = str(value)
        try:
            datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            return candidate
        except ValueError:
            pass
    return _timestamp(manifest)


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _country(manifest: dict[str, Any]) -> str:
    value = str(manifest.get("country_code") or "ZZ").upper()
    return value[:2] if len(value) >= 2 else "ZZ"


def _aphis_facility_identifier_aliases(normalized_values: Any) -> list[tuple[str, str]]:
    """Return exact APHIS certificate/customer aliases from retained source fields.

    APHIS Form 7023 registration numbers are certificate numbers only for the
    documented R/F/V/G registration formats. Keep the rule versioned and
    format-bound; never infer customer numbers from registration IDs.
    """
    native_ids = normalized_values.get("source_native_ids") if isinstance(normalized_values, dict) else None
    if not isinstance(native_ids, dict):
        native_ids = {}
    alias_types = {
        "certificate_number": "aphis_certificate_number",
        "customer_number": "aphis_customer_number",
        "customer_number_x": "aphis_customer_number_x",
        "customer_number_y": "aphis_customer_number_y",
    }
    aliases = list(dict.fromkeys(
        (identifier_type, value.strip())
        for name, identifier_type in alias_types.items()
        if isinstance((value := native_ids.get(name)), str) and value.strip()
    ))
    establishment_id = normalized_values.get("establishment_id") if isinstance(normalized_values, dict) else None
    registration_values = [native_ids.get("aphis_license_number")]
    if isinstance(establishment_id, str) and establishment_id.startswith("aphis-registration:"):
        registration_values.append(establishment_id.removeprefix("aphis-registration:"))
    for registration in registration_values:
        if not isinstance(registration, str):
            continue
        encoded = registration.encode("ascii", errors="ignore")
        valid_registration = (
            len(encoded) == 9 and len(registration) == 9
            and encoded[2:3] == b"-" and encoded[4:5] == b"-"
            and encoded[:2].isdigit() and encoded[5:].isdigit()
            and encoded[3:4] in {b"R", b"F", b"V", b"G"}
        )
        if valid_registration:
            aliases.append(("aphis_certificate_number", registration))
    return list(dict.fromkeys(aliases))


def _additional_facility_identifier_aliases(candidate: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Validate source-declared same-facility aliases without deriving IDs."""
    values = candidate.get("additional_source_identifiers", [])
    if values is None:
        return []
    if not isinstance(values, list):
        raise GraphPersistenceError("additional_source_identifiers must be a list")
    aliases: list[tuple[str, str, str]] = []
    for item in values:
        if not isinstance(item, dict):
            raise GraphPersistenceError("additional source identifier must be an object")
        identifier_type, value = item.get("identifier_type"), item.get("value")
        namespace = item.get("id_namespace", "source_scoped")
        identity_scope = item.get("identity_scope", "source_scoped")
        if (not isinstance(identifier_type, str) or not identifier_type.strip()
                or not isinstance(value, str) or not value.strip()
                or not isinstance(namespace, str) or not namespace.strip()
                or identity_scope != "source_scoped"):
            raise GraphPersistenceError("additional source identifiers must be non-empty and source-scoped")
        aliases.append((identifier_type, value, namespace))
    return list(dict.fromkeys(aliases))


def _persist_facility_identifier_aliases(connection: Any, *, source_id: str,
                                         source_record_id: uuid.UUID, facility_id: uuid.UUID,
                                         observed_at: Any,
                                         aliases: Iterable[tuple[str, str, str]]) -> int:
    """Append exact alias identifiers to the existing facility; never create a node."""
    inserted = 0
    for identifier_type, value, _namespace in dict.fromkeys(aliases):
        existing = connection.execute(
            """SELECT identifier_id FROM uec.source_entity_identifiers
               WHERE source_id=%s AND source_record_id=%s AND entity_type='facility'
                 AND facility_id=%s AND identifier_type=%s AND source_identifier=%s""",
            (source_id, source_record_id, facility_id, identifier_type, value),
        ).fetchone()
        if existing:
            continue
        connection.execute(
            """INSERT INTO uec.source_entity_identifiers
               (source_id,source_record_id,entity_type,facility_id,identifier_type,
                source_identifier,value_as_observed,observed_at)
               VALUES (%s,%s,'facility',%s,%s,%s,%s,%s)""",
            (source_id, source_record_id, facility_id, identifier_type, value, value, observed_at),
        )
        inserted += 1
    return inserted


def _ensure_source_artifact(connection: Any, manifest: dict[str, Any], digest: str) -> tuple[uuid.UUID, uuid.UUID]:
    source_id = manifest["source_id"]
    connection.execute(
        """INSERT INTO uec.sources(source_id,country_code,name,official_url,access_method)
           VALUES (%s,%s,%s,%s,'private-graph-handoff') ON CONFLICT (source_id) DO NOTHING""",
        (source_id, _country(manifest), source_id, manifest.get("source_url") or "https://example.invalid/private-handoff"),
    )
    artifact_sha = str(manifest.get("checksum_sha256") or manifest.get("source_artifact_sha256") or digest)
    if len(artifact_sha) != 64:
        artifact_sha = digest
    connection.execute(
        """INSERT INTO uec.raw_artifacts(storage_key,sha256,byte_size,media_type,retrieved_at)
           VALUES (%s,%s,%s,'application/jsonl',%s) ON CONFLICT (sha256) DO NOTHING""",
        (f"private-graph-handoff/{source_id}/{artifact_sha}", artifact_sha,
         int(manifest.get("byte_size") or 0), _timestamp(manifest)),
    )
    artifact_id = connection.execute("SELECT artifact_id FROM uec.raw_artifacts WHERE sha256=%s", (artifact_sha,)).fetchone()[0]
    return _stable_uuid("source", source_id), artifact_id


def _ensure_record(connection: Any, manifest: dict[str, Any], artifact_id: uuid.UUID,
                   source_record_key: str, source_values: dict[str, Any], digest: str,
                   graph_context: dict[str, Any] | None = None) -> uuid.UUID:
    source_id = manifest["source_id"]
    record_id = _stable_uuid("record", source_id, source_record_key, str(artifact_id))
    connection.execute(
        """INSERT INTO uec.source_records(source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at)
           VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (source_id,source_record_key,artifact_id) DO NOTHING""",
        (record_id, source_id, source_record_key, artifact_id,
         json.dumps({"source_values": source_values, **(graph_context or {}),
                     "handoff_sha256": digest}, ensure_ascii=False), _timestamp(manifest)),
    )
    row = connection.execute(
        "SELECT source_record_id FROM uec.source_records WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s",
        (source_id, source_record_key, artifact_id),
    ).fetchone()
    if not row:
        raise GraphPersistenceError("source record was not materialized")
    return row[0]


def _entity_maps(connection: Any, manifest: dict[str, Any], candidate: dict[str, Any],
                 record_id: uuid.UUID, artifact_id: uuid.UUID, *,
                 require_approved_facility: bool = False,
                 approved_facility_map: dict[tuple[str, str, uuid.UUID], set[uuid.UUID]] | None = None,
                 mapping_diagnostics: dict[str, int] | None = None) -> tuple[dict[str, uuid.UUID], dict[str, uuid.UUID]]:
    facilities: dict[str, uuid.UUID] = {}
    organizations: dict[str, uuid.UUID] = {}
    country = _country(manifest)
    source_id = manifest["source_id"]
    source_record_key = str(candidate.get("source_record_key") or "")
    if not source_record_key:
        raise GraphPersistenceError("candidate requires source_record_key")
    source_values = candidate.get("source_values") or {}
    for item in candidate.get("facilities", []):
        ref = item["local_ref"]
        identifier = item["source_identifier"]
        if require_approved_facility:
            facility_id, mapping_state = _approved_facility_for_source_record(
                connection, source_id, source_record_key, artifact_id,
                approved_facility_map=approved_facility_map,
            )
            if mapping_state != "mapped":
                # Preserve only a source-qualified private node when public
                # release lineage is absent or ambiguous. It cannot resolve
                # through the release projection and is never treated as a
                # canonical/public facility.
                facility_id = _stable_uuid("facility", source_id, identifier["identifier_type"], identifier["value"])
                if mapping_diagnostics is not None:
                    mapping_diagnostics[mapping_state] = mapping_diagnostics.get(mapping_state, 0) + 1
        else:
            facility_id = _stable_uuid("facility", source_id, identifier["identifier_type"], identifier["value"])
        name = source_values.get("name") or source_values.get("trading_name")
        connection.execute(
            """INSERT INTO uec.facilities(facility_id,canonical_name,country_code)
               VALUES (%s,%s,%s) ON CONFLICT (facility_id) DO NOTHING""",
            (facility_id, name, country),
        )
        existing = connection.execute(
            """SELECT identifier_id FROM uec.source_entity_identifiers
               WHERE source_id=%s AND source_record_id=%s AND entity_type='facility'
                 AND identifier_type=%s AND source_identifier=%s""",
            (source_id, record_id, identifier["identifier_type"], identifier["value"]),
        ).fetchone()
        identifier_id = existing[0] if existing else connection.execute(
            """INSERT INTO uec.source_entity_identifiers
               (source_id,source_record_id,entity_type,facility_id,identifier_type,source_identifier,value_as_observed,observed_at)
               VALUES (%s,%s,'facility',%s,%s,%s,%s,%s) RETURNING identifier_id""",
            (source_id, record_id, facility_id, identifier["identifier_type"], identifier["value"],
             identifier["value"], _timestamp(manifest)),
        ).fetchone()[0]
        facilities[ref] = identifier_id
    # Additional aliases are source assertions about this same facility. The
    # only adapter-derived aliases retained here remain APHIS's documented
    # certificate/customer identifier mappings; no facility node is created
    # from an alias and no namespace is equated with another.
    facility_aliases = _additional_facility_identifier_aliases(candidate)
    if source_id == "us.aphis":
        facility_aliases.extend(
            (identifier_type, value, "us.aphis")
            for identifier_type, value in
            _aphis_facility_identifier_aliases(candidate.get("normalized_values"))
        )
    facility_aliases = list(dict.fromkeys(facility_aliases))
    if facility_aliases:
        if len(facilities) != 1:
            raise GraphPersistenceError(
                "additional source identifiers require exactly one primary facility in the candidate"
            )
        _, primary_identifier_id = next(iter(facilities.items()))
        facility_id = _facility_id_for_identifier(connection, primary_identifier_id)
        _persist_facility_identifier_aliases(
            connection, source_id=source_id, source_record_id=record_id,
            facility_id=facility_id, observed_at=_timestamp(manifest),
            aliases=facility_aliases,
        )
    for item in candidate.get("organizations", []):
        ref = item["local_ref"]
        identifier = item["source_identifier"]
        same_record = connection.execute(
            "SELECT organization_id FROM uec.source_entity_identifiers WHERE source_id=%s "
            "AND source_record_id=%s AND entity_type='organization' AND identifier_type=%s AND source_identifier=%s",
            (source_id, record_id, identifier["identifier_type"], identifier["value"]),
        ).fetchall()
        if len(same_record) == 1:
            organization_id = same_record[0][0]
        else:
            organization_ids = connection.execute(
                "SELECT DISTINCT organization_id FROM uec.source_entity_identifiers WHERE source_id=%s "
                "AND entity_type='organization' AND identifier_type=%s AND source_identifier=%s",
                (source_id, identifier["identifier_type"], identifier["value"]),
            ).fetchall()
            if len(organization_ids) == 1:
                organization_id = organization_ids[0][0]
            else:
                # A persisted random UUID is stable across retries without
                # being a public-salt hash of a protected source identifier.
                organization_id = uuid.uuid4()
                if len(organization_ids) > 1 and mapping_diagnostics is not None:
                    mapping_diagnostics["ambiguous_private_organization_identifier"] = (
                        mapping_diagnostics.get("ambiguous_private_organization_identifier", 0) + 1
                    )
        name = source_values.get("operator_name") or source_values.get("organization_name")
        connection.execute(
            """INSERT INTO uec.organizations(organization_id,canonical_name,country_code)
               VALUES (%s,%s,%s) ON CONFLICT (organization_id) DO NOTHING""",
            (organization_id, name, country),
        )
        existing = connection.execute(
            """SELECT identifier_id FROM uec.source_entity_identifiers
               WHERE source_id=%s AND source_record_id=%s AND entity_type='organization'
                 AND identifier_type=%s AND source_identifier=%s""",
            (source_id, record_id, identifier["identifier_type"], identifier["value"]),
        ).fetchone()
        identifier_id = existing[0] if existing else connection.execute(
            """INSERT INTO uec.source_entity_identifiers
               (source_id,source_record_id,entity_type,organization_id,identifier_type,source_identifier,value_as_observed,observed_at)
               VALUES (%s,%s,'organization',%s,%s,%s,%s,%s) RETURNING identifier_id""",
            (source_id, record_id, organization_id, identifier["identifier_type"], identifier["value"],
             identifier["value"], _timestamp(manifest)),
        ).fetchone()[0]
        organizations[ref] = identifier_id
    # The handoff's name assertions are source-field assertions, not canonical
    # organization names. The v1 contract does not assign assertions to a local
    # organization ref, so persist them only where this record has one org node.
    assertions = candidate.get("name_assertions", [])
    if len(organizations) == 1:
        _, identifier_id = next(iter(organizations.items()))
        organization_id = _organization_id_for_identifier(connection, identifier_id)
        for assertion in assertions:
            if not isinstance(assertion, dict):
                continue
            value = assertion.get("value")
            source_field = assertion.get("source_field")
            role = assertion.get("role")
            if (not isinstance(value, str) or not value.strip()
                    or not isinstance(source_field, str) or not source_field.strip()
                    or role not in {"legal", "business", "trading", "dba", "operator", "brand"}):
                continue
            connection.execute(
                """INSERT INTO uec.graph_source_name_assertions
                   (source_id,source_record_id,organization_id,identifier_id,assertion_role,source_field,assertion_value)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (source_id, record_id, organization_id, identifier_id, role, source_field.strip(), value.strip()),
            )
    return facilities, organizations


def _candidate_has_backfillable_context(source_id: str, candidate: dict[str, Any]) -> bool:
    """Identify aliases/organization labels without touching the database."""
    aliases = _additional_facility_identifier_aliases(candidate)
    if source_id == "us.aphis":
        aliases.extend((kind, value, "us.aphis") for kind, value in
                       _aphis_facility_identifier_aliases(candidate.get("normalized_values")))
    return bool(aliases) or (
        len(candidate.get("organizations", [])) == 1
        and bool(candidate.get("name_assertions", []))
    )


def _backfill_existing_candidate_context(connection: Any, manifest: dict[str, Any],
                                         candidate: dict[str, Any], artifact_id: uuid.UUID) -> None:
    """Append newly-supported labels/aliases to exact existing record identifiers.

    A candidate can be replayed after persistence semantics are upgraded while
    its original ingest item hash remains unchanged. This deliberately does
    not update source_records/raw_fields, create entity nodes or identifiers,
    or revisit edge payloads: it only attaches source assertions and declared
    aliases to identifiers already bound to this source-record-artifact tuple.
    """
    source_id = str(manifest["source_id"])
    if not _candidate_has_backfillable_context(source_id, candidate):
        return
    source_record_key = candidate.get("source_record_key")
    if not isinstance(source_record_key, str) or not source_record_key:
        raise GraphPersistenceError("candidate requires source_record_key")
    record = connection.execute(
        """SELECT source_record_id FROM uec.source_records
           WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s""",
        (source_id, source_record_key, artifact_id),
    ).fetchone()
    if not record:
        return
    record_id = record[0]

    # Same-facility aliases may be appended only when the exact primary
    # facility identifier is already present for this record and artifact.
    facility_items = candidate.get("facilities", [])
    aliases = _additional_facility_identifier_aliases(candidate)
    if source_id == "us.aphis":
        aliases.extend((kind, value, "us.aphis") for kind, value in
                       _aphis_facility_identifier_aliases(candidate.get("normalized_values")))
    aliases = list(dict.fromkeys(aliases))
    if aliases and len(facility_items) == 1:
        identifier = facility_items[0].get("source_identifier", {})
        primary = connection.execute(
            """SELECT facility_id FROM uec.source_entity_identifiers
               WHERE source_id=%s AND source_record_id=%s AND entity_type='facility'
                 AND identifier_type=%s AND source_identifier=%s""",
            (source_id, record_id, identifier.get("identifier_type"), identifier.get("value")),
        ).fetchall()
        if len(primary) == 1 and primary[0][0] is not None:
            _persist_facility_identifier_aliases(
                connection, source_id=source_id, source_record_id=record_id,
                facility_id=primary[0][0], observed_at=_timestamp(manifest), aliases=aliases,
            )

    # Name assertions are intentionally attached only when one candidate org
    # maps to one pre-existing org identifier on this exact source record.
    org_items = candidate.get("organizations", [])
    assertions = candidate.get("name_assertions", [])
    if len(org_items) != 1 or not assertions:
        return
    identifier = org_items[0].get("source_identifier", {})
    organization_rows = connection.execute(
        """SELECT identifier_id,organization_id FROM uec.source_entity_identifiers
           WHERE source_id=%s AND source_record_id=%s AND entity_type='organization'
             AND identifier_type=%s AND source_identifier=%s""",
        (source_id, record_id, identifier.get("identifier_type"), identifier.get("value")),
    ).fetchall()
    if len(organization_rows) != 1 or organization_rows[0][1] is None:
        return
    identifier_id, organization_id = organization_rows[0]
    for assertion in assertions:
        if not isinstance(assertion, dict):
            continue
        value = assertion.get("value")
        source_field = assertion.get("source_field")
        role = assertion.get("role")
        if (not isinstance(value, str) or not value.strip()
                or not isinstance(source_field, str) or not source_field.strip()
                or role not in {"legal", "business", "trading", "dba", "operator", "brand"}):
            continue
        connection.execute(
            """INSERT INTO uec.graph_source_name_assertions
               (source_id,source_record_id,organization_id,identifier_id,assertion_role,source_field,assertion_value)
               VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (source_id, record_id, organization_id, identifier_id, role,
             source_field.strip(), value.strip()),
        )


def _facility_id_for_identifier(connection: Any, identifier_id: uuid.UUID) -> uuid.UUID:
    return connection.execute("SELECT facility_id FROM uec.source_entity_identifiers WHERE identifier_id=%s", (identifier_id,)).fetchone()[0]


def _organization_id_for_identifier(connection: Any, identifier_id: uuid.UUID) -> uuid.UUID:
    return connection.execute("SELECT organization_id FROM uec.source_entity_identifiers WHERE identifier_id=%s", (identifier_id,)).fetchone()[0]


def _approved_facility_for_source_record(connection: Any, source_id: str,
                                         source_record_key: str,
                                         artifact_id: uuid.UUID,
                                         approved_facility_map: dict[tuple[str, str, uuid.UUID], set[uuid.UUID]] | None = None
                                         ) -> tuple[uuid.UUID | None, str]:
    """Resolve a graph facility to current approved lineage without guessing."""
    if approved_facility_map is not None:
        facilities = approved_facility_map.get((source_id, source_record_key, artifact_id), set())
        if len(facilities) != 1:
            return None, "ambiguous_approved_release_mapping" if facilities else "no_eligible_public_record"
        return next(iter(facilities)), "mapped"
    rows = connection.execute(
        """SELECT DISTINCT p.facility_id
           FROM uec.map_facilities_public_discovery_read_model p
           JOIN (SELECT release_id FROM uec.releases
                 WHERE status='promoted' AND test_only IS NOT TRUE AND profile='official'
                 ORDER BY created_at DESC, release_id DESC LIMIT 1) r ON r.release_id=p.release_id
           JOIN uec.source_records source_record ON source_record.source_record_id=p.source_record_id
             AND source_record.source_id=%s AND source_record.source_record_key=%s
             AND source_record.artifact_id=%s
           ORDER BY p.facility_id""",
        (source_id, source_record_key, artifact_id),
    ).fetchall()
    if len(rows) != 1:
        return None, "ambiguous_approved_release_mapping" if rows else "no_eligible_public_record"
    return rows[0][0], "mapped"


def _load_approved_facility_map(connection: Any, source_id: str,
                                artifact_id: uuid.UUID) -> dict[tuple[str, str, uuid.UUID], set[uuid.UUID]]:
    """Load one promoted release's source-record lineage once for this import."""
    rows = connection.execute(
        """SELECT DISTINCT source_record.source_id, source_record.source_record_key,
                  source_record.artifact_id, p.facility_id
           FROM uec.map_facilities_public_discovery_read_model p
           JOIN (SELECT release_id FROM uec.releases
                 WHERE status='promoted' AND test_only IS NOT TRUE AND profile='official'
                 ORDER BY created_at DESC, release_id DESC LIMIT 1) r ON r.release_id=p.release_id
           JOIN uec.source_records source_record ON source_record.source_record_id=p.source_record_id
           WHERE source_record.source_id=%s AND source_record.artifact_id=%s
           ORDER BY source_record.source_id, source_record.source_record_key,
                    source_record.artifact_id, p.facility_id""",
        (source_id, artifact_id),
    ).fetchall()
    mappings: dict[tuple[str, str, uuid.UUID], set[uuid.UUID]] = {}
    for source_id, source_record_key, artifact_id, facility_id in rows:
        key = (str(source_id), str(source_record_key), artifact_id)
        mappings.setdefault(key, set()).add(facility_id)
    return mappings


def _load_run_source_record_ids(connection: Any, run_id: uuid.UUID,
                                artifact_id: uuid.UUID) -> dict[tuple[str, str, str], uuid.UUID]:
    rows = connection.execute(
        """SELECT DISTINCT record.source_id, record.source_record_key, artifact.sha256,
                  record.source_record_id
           FROM uec.graph_ingest_items item
           JOIN uec.source_records record
             ON record.source_id=item.source_id
            AND record.source_record_key=item.source_record_key
            AND record.artifact_id=%s
           JOIN uec.raw_artifacts artifact ON artifact.artifact_id=record.artifact_id
           WHERE item.ingest_run_id=%s AND item.status='inserted'
             AND item.item_kind='facility_candidate'
           ORDER BY record.source_id, record.source_record_key""",
        (artifact_id, run_id),
    ).fetchall()
    return {(str(source_id), str(key), str(sha).lower()): record_id
            for source_id, key, sha, record_id in rows}


def _load_run_source_record_ids_for_edge_batches(connection: Any, run_id: uuid.UUID,
                                                 artifact_id: uuid.UUID) -> dict[tuple[str, str], uuid.UUID]:
    """Load source IDs and close the implicit read transaction before edge batches."""
    result = _load_run_source_record_ids(connection, run_id, artifact_id)
    # The SELECT above opens a psycopg implicit transaction. Without this
    # boundary, the explicit edge-batch transactions below become savepoints.
    connection.commit()
    return result


_ITALY_CANONICAL_BINDING_CTES = """
WITH selected_release AS MATERIALIZED (
    SELECT release_id FROM uec.releases
    WHERE status='promoted' AND test_only IS NOT TRUE AND profile='official'
    ORDER BY created_at DESC, release_id DESC LIMIT 1
),
candidate_rows AS MATERIALIZED (
    SELECT DISTINCT item.item_sha256, candidate.source_record_id,
           NULLIF(btrim(candidate.raw_fields #>> '{source_values,num_identificativo_produzione_commercializzazione}'), '') AS recognition_number,
           NULLIF(btrim(candidate.raw_fields #>> '{source_values,codice_impianto_attivita}'), '') AS activity_code
    FROM uec.graph_ingest_items item
    JOIN uec.source_records candidate
      ON candidate.source_id=item.source_id
     AND candidate.source_record_key=item.source_record_key
     AND candidate.artifact_id=%s
    WHERE item.ingest_run_id=%s AND item.source_id=%s
      AND item.status='inserted' AND item.item_kind='facility_candidate'
),
candidate_pairs AS MATERIALIZED (
    SELECT recognition_number, activity_code,
           count(DISTINCT source_record_id) AS source_record_count,
           count(DISTINCT item_sha256) AS candidate_count,
           (array_agg(DISTINCT source_record_id))[1] AS private_record_id
    FROM candidate_rows
    WHERE recognition_number IS NOT NULL AND activity_code IS NOT NULL
    GROUP BY recognition_number, activity_code
),
approved_rows AS MATERIALIZED (
    SELECT record.source_record_id, model.facility_id,
           NULLIF(btrim(record.raw_fields #>> '{normalized,recognition_number}'), '') AS recognition_number,
           NULLIF(btrim(record.raw_fields #>> '{normalized,activity_code}'), '') AS activity_code
    FROM selected_release selected
    JOIN uec.map_facilities_public_discovery_read_model model
      ON model.release_id=selected.release_id
    JOIN uec.source_records record ON record.source_record_id=model.source_record_id
    WHERE record.source_id=%s AND record.artifact_id=%s
),
approved_pairs AS MATERIALIZED (
    SELECT recognition_number, activity_code,
           count(DISTINCT source_record_id) AS source_record_count,
           count(DISTINCT facility_id) AS facility_count,
           (array_agg(DISTINCT source_record_id))[1] AS canonical_record_id,
           (array_agg(DISTINCT facility_id))[1] AS facility_id
    FROM approved_rows
    WHERE recognition_number IS NOT NULL AND activity_code IS NOT NULL
    GROUP BY recognition_number, activity_code
),
unique_mappings AS MATERIALIZED (
    SELECT candidate.private_record_id, approved.canonical_record_id, approved.facility_id
    FROM candidate_pairs candidate
    JOIN approved_pairs approved USING (recognition_number, activity_code)
    WHERE candidate.source_record_count=1 AND candidate.candidate_count=1
      AND approved.source_record_count=1 AND approved.facility_count=1
)
"""


def _italy_binding_summary(connection: Any, run_id: uuid.UUID, source_id: str,
                           artifact_id: uuid.UUID) -> dict[str, int]:
    if source_id != "it.853-2004":
        raise GraphPersistenceError("canonical native binding is not configured for this source")
    # Parameter order follows the CTEs: private artifact/run/source, then
    # approved source/artifact. Only aggregate counts are returned.
    rows = connection.execute(
        _ITALY_CANONICAL_BINDING_CTES + """
        SELECT count(*) AS candidate_pair_groups,
               count(*) FILTER (WHERE candidate.source_record_count=1 AND candidate.candidate_count=1) AS unique_candidate_pairs,
               count(*) FILTER (WHERE candidate.source_record_count>1 OR candidate.candidate_count>1) AS ambiguous_candidate_pairs,
               count(*) FILTER (WHERE candidate.source_record_count=1 AND candidate.candidate_count=1
                                  AND approved.source_record_count=1 AND approved.facility_count=1) AS mapped_pairs,
               count(*) FILTER (WHERE candidate.source_record_count=1 AND candidate.candidate_count=1
                                  AND approved.recognition_number IS NULL) AS no_approved_pair,
               count(*) FILTER (WHERE candidate.source_record_count=1 AND candidate.candidate_count=1
                                  AND approved.recognition_number IS NOT NULL
                                  AND (approved.source_record_count<>1 OR approved.facility_count<>1)) AS ambiguous_approved_pair
        FROM candidate_pairs candidate
        LEFT JOIN approved_pairs approved USING (recognition_number, activity_code)
        """,
        (artifact_id, run_id, source_id, source_id, artifact_id),
    ).fetchone()
    return {str(name): int(value or 0) for name, value in zip(
        ("candidate_pair_groups", "unique_candidate_pairs", "ambiguous_candidate_pairs",
         "mapped_pairs", "no_approved_pair", "ambiguous_approved_pair"), rows)}


def _insert_italy_canonical_identifier_bindings(connection: Any, run_id: uuid.UUID,
                                                source_id: str, artifact_id: uuid.UUID) -> dict[str, int]:
    if source_id != "it.853-2004":
        raise GraphPersistenceError("canonical native binding is not configured for this source")
    cursor = connection.execute(
        _ITALY_CANONICAL_BINDING_CTES + """
        INSERT INTO uec.source_entity_identifiers
            (source_id,source_record_id,entity_type,facility_id,organization_id,
             identifier_type,source_identifier,value_as_observed,observed_at,
             review_state,storage_state,privacy_status,publication_status,release_id)
        SELECT private_identifier.source_id, mapping.canonical_record_id,
               private_identifier.entity_type,
               CASE WHEN private_identifier.entity_type='facility' THEN mapping.facility_id ELSE NULL END,
               private_identifier.organization_id,
               private_identifier.identifier_type, private_identifier.source_identifier,
               private_identifier.value_as_observed, private_identifier.observed_at,
               private_identifier.review_state, private_identifier.storage_state,
               private_identifier.privacy_status, private_identifier.publication_status,
               private_identifier.release_id
        FROM unique_mappings mapping
        JOIN uec.source_entity_identifiers private_identifier
          ON private_identifier.source_record_id=mapping.private_record_id
         AND private_identifier.source_id=%s
        WHERE NOT EXISTS (
            SELECT 1 FROM uec.source_entity_identifiers existing
            WHERE existing.source_record_id=mapping.canonical_record_id
              AND existing.source_id=private_identifier.source_id
              AND existing.entity_type=private_identifier.entity_type
              AND existing.identifier_type=private_identifier.identifier_type
              AND existing.source_identifier=private_identifier.source_identifier
              AND existing.facility_id IS NOT DISTINCT FROM
                  CASE WHEN private_identifier.entity_type='facility' THEN mapping.facility_id ELSE NULL END
              AND existing.organization_id IS NOT DISTINCT FROM private_identifier.organization_id
        )
        RETURNING identifier_id
        """,
        (artifact_id, run_id, source_id, source_id, artifact_id, source_id),
    )
    identifier_rows = int(cursor.rowcount)
    binding_cursor = connection.execute(
        _ITALY_CANONICAL_BINDING_CTES + """
        INSERT INTO uec.graph_record_release_bindings
            (release_id,private_source_record_id,canonical_source_record_id,
             facility_id,source_id,artifact_id,binding_method)
        SELECT selected.release_id, mapping.private_record_id,
               mapping.canonical_record_id, mapping.facility_id,
               %s, %s, 'it_recognition_activity_singleton_v1'
        FROM selected_release selected CROSS JOIN unique_mappings mapping
        ON CONFLICT DO NOTHING
        RETURNING private_source_record_id
        """,
        (artifact_id, run_id, source_id, source_id, artifact_id, source_id, artifact_id),
    )
    return {"identifier_rows": identifier_rows, "release_bindings": int(binding_cursor.rowcount)}


def _backfill_graph_edge_support_record_ids(connection: Any, run_id: uuid.UUID,
                                            source_id: str, artifact_id: uuid.UUID) -> int:
    """Attach exact source-record IDs to existing graph refs for this run.

    The key is retained for private provenance; the ID resolves its artifact
    version. Other-source refs are left untouched and must already carry IDs
    before they can pass the public release support gate.
    """
    cursor = connection.execute(
        """
        WITH run_records AS MATERIALIZED (
            SELECT DISTINCT record.source_id, record.source_record_key,
                   artifact.sha256 AS artifact_sha256, record.source_record_id
            FROM uec.graph_ingest_items item
            JOIN uec.source_records record
              ON record.source_id=item.source_id
             AND record.source_record_key=item.source_record_key
             AND record.artifact_id=%s
            JOIN uec.raw_artifacts artifact ON artifact.artifact_id=record.artifact_id
            WHERE item.ingest_run_id=%s AND item.source_id=%s
              AND item.status='inserted' AND item.item_kind='facility_candidate'
        ),
        edge_refs AS MATERIALIZED (
            SELECT edge.connection_edge_id, edge.connection_type,
                   jsonb_array_length(edge.supporting_source_refs) AS ref_count,
                   refs.ordinality, refs.value,
                   record.source_record_id AS resolved_record_id
            FROM uec.graph_connection_edges edge
            CROSS JOIN LATERAL jsonb_array_elements(edge.supporting_source_refs)
                WITH ORDINALITY AS refs(value, ordinality)
            LEFT JOIN run_records record
              ON record.source_id=refs.value->>'source_id'
             AND record.source_record_key=refs.value->>'source_record_key'
             AND record.artifact_sha256=lower(refs.value->>'artifact_sha256')
        WHERE (edge.from_source_id=%s OR edge.to_source_id=%s)
          AND edge.storage_state='private'
          AND edge.publication_status='not_eligible'
        ),
        rebuilt AS MATERIALIZED (
            SELECT connection_edge_id,
                   jsonb_agg(
                       value
                       || CASE WHEN value->>'source_id'=%s AND resolved_record_id IS NOT NULL
                                    AND NOT (value ? 'source_record_id')
                               THEN jsonb_build_object('source_record_id',resolved_record_id::text)
                               ELSE '{}'::jsonb END
                       || CASE WHEN connection_type='inferred' AND ref_count=2
                               THEN jsonb_build_object('role', CASE WHEN ordinality=1 THEN 'from' ELSE 'to' END)
                               ELSE '{}'::jsonb END
                       ORDER BY ordinality
                   ) AS supporting_source_refs,
                   bool_and(CASE WHEN value->>'source_id'=%s
                                 THEN (value ? 'source_record_id') OR resolved_record_id IS NOT NULL
                                 ELSE value ? 'source_record_id' END) AS all_refs_resolved
            FROM edge_refs
            GROUP BY connection_edge_id
        )
        UPDATE uec.graph_connection_edges edge
        SET supporting_source_refs=rebuilt.supporting_source_refs
        FROM rebuilt
        WHERE edge.connection_edge_id=rebuilt.connection_edge_id
          AND rebuilt.all_refs_resolved
          AND edge.supporting_source_refs IS DISTINCT FROM rebuilt.supporting_source_refs
        RETURNING edge.connection_edge_id
        """,
        (artifact_id, run_id, source_id, source_id, source_id, source_id, source_id),
    )
    return int(cursor.rowcount)


def _repair_inferred_native_endpoints(connection: Any, source_id: str,
                                     artifact_id: uuid.UUID) -> dict[str, int]:
    """Append native-key representations of normalized inferred edges.

    A repair is eligible only when both ordered support refs resolve through
    the exact current release binding and each canonical record has one
    same-facility native assertion whose documented D6 normalization equals
    the persisted endpoint. The old private edge is retained as history.
    """
    cursor = connection.execute(
        """
        WITH selected_release AS MATERIALIZED (
            SELECT release_id FROM uec.releases
            WHERE status='promoted' AND test_only IS NOT TRUE AND profile='official'
            ORDER BY created_at DESC, release_id DESC LIMIT 1
        ), edge_refs AS MATERIALIZED (
            SELECT edge.connection_edge_id, edge.edge_key, edge.relationship_type,
                   edge.connection_type, edge.confidence, edge.confidence_band,
                   edge.match_method, edge.supporting_source_refs,
                   edge.signal_explanation, edge.ruleset_version, edge.observed_at,
                   edge.computed_at, edge.conflicting, edge.suppressed,
                   edge.from_entity_type, edge.from_source_id, edge.from_identifier_type,
                   edge.from_source_identifier, edge.to_entity_type, edge.to_source_id,
                   edge.to_identifier_type, edge.to_source_identifier,
                   refs.ordinality, refs.value,
                   CASE WHEN refs.ordinality=1 THEN edge.from_entity_type ELSE edge.to_entity_type END AS entity_type,
                   CASE WHEN refs.ordinality=1 THEN edge.from_source_id ELSE edge.to_source_id END AS endpoint_source_id,
                   CASE WHEN refs.ordinality=1 THEN edge.from_identifier_type ELSE edge.to_identifier_type END AS identifier_type,
                   CASE WHEN refs.ordinality=1 THEN edge.from_source_identifier ELSE edge.to_source_identifier END AS endpoint_value
            FROM uec.graph_connection_edges edge
            CROSS JOIN LATERAL jsonb_array_elements(edge.supporting_source_refs)
                WITH ORDINALITY AS refs(value, ordinality)
            WHERE edge.connection_type='inferred'
              AND edge.from_source_id=%s AND edge.to_source_id=%s
              AND edge.storage_state='private' AND edge.publication_status='not_eligible'
              AND jsonb_array_length(edge.supporting_source_refs)=2
              AND refs.value->>'source_id'=%s
              AND refs.value ? 'source_record_id'
              AND refs.value->>'role'=CASE WHEN refs.ordinality=1 THEN 'from' ELSE 'to' END
        ), eligible_assertions AS MATERIALIZED (
            SELECT refs.*, binding.release_id, identifier.source_identifier AS native_value,
                   binding.facility_id
            FROM edge_refs refs
            JOIN uec.graph_record_release_bindings binding
              ON binding.private_source_record_id=(refs.value->>'source_record_id')::uuid
             AND binding.source_id=%s AND binding.artifact_id=%s
             AND binding.release_id=(SELECT release_id FROM selected_release)
            JOIN uec.releases release
              ON release.release_id=binding.release_id AND release.profile='official'
             AND release.status='promoted' AND release.test_only IS NOT TRUE
            JOIN uec.source_records private_record
              ON private_record.source_record_id=binding.private_source_record_id
             AND private_record.source_id=binding.source_id
             AND private_record.artifact_id=binding.artifact_id
            JOIN uec.source_records canonical_record
              ON canonical_record.source_record_id=binding.canonical_source_record_id
             AND canonical_record.source_id=binding.source_id
             AND canonical_record.artifact_id=binding.artifact_id
            JOIN uec.source_entity_identifiers identifier
              ON identifier.source_record_id=canonical_record.source_record_id
             AND identifier.source_id=binding.source_id
             AND identifier.entity_type='facility'
             AND identifier.facility_id=binding.facility_id
             AND identifier.identifier_type=refs.identifier_type
             AND regexp_replace(lower(btrim(identifier.source_identifier)), '[^a-z0-9]', '', 'g')
                 = regexp_replace(lower(btrim(refs.endpoint_value)), '[^a-z0-9]', '', 'g')
            WHERE refs.entity_type='facility' AND refs.endpoint_source_id=binding.source_id
        ), unique_endpoint AS MATERIALIZED (
            SELECT connection_edge_id, ordinality, min(native_value) AS native_value
            FROM eligible_assertions
            GROUP BY connection_edge_id, ordinality
            HAVING count(DISTINCT native_value)=1 AND count(DISTINCT facility_id)=1
        ), fully_mapped AS MATERIALIZED (
            SELECT refs.*, source.native_value AS native_from, target.native_value AS native_to
            FROM (SELECT DISTINCT ON (connection_edge_id) * FROM edge_refs
                  ORDER BY connection_edge_id, ordinality) refs
            JOIN unique_endpoint source ON source.connection_edge_id=refs.connection_edge_id AND source.ordinality=1
            JOIN unique_endpoint target ON target.connection_edge_id=refs.connection_edge_id AND target.ordinality=2
        )
        SELECT edge_key, relationship_type, connection_type, confidence, confidence_band,
               match_method, supporting_source_refs, signal_explanation, ruleset_version,
               observed_at, computed_at, conflicting, suppressed,
               from_entity_type, from_source_id, from_identifier_type, native_from,
               to_entity_type, to_source_id, to_identifier_type, native_to
        FROM fully_mapped
        WHERE from_source_identifier IS DISTINCT FROM native_from
           OR to_source_identifier IS DISTINCT FROM native_to
        """,
        (source_id, source_id, source_id, source_id, artifact_id),
    )
    rows = cursor.fetchall()
    repaired = []
    for row in rows:
        (old_key, relationship, connection_type, confidence, band, method, refs,
         explanation, ruleset, observed_at, computed_at, conflicting, suppressed,
         from_type, from_source, from_identifier_type, from_native,
         to_type, to_source, to_identifier_type, to_native) = row
        left = EntityRef(str(from_type), str(from_source), str(from_identifier_type), str(from_native))
        right = EntityRef(str(to_type), str(to_source), str(to_identifier_type), str(to_native))
        repaired.append({
            "edge_key": connection_edge_key(from_ref=left, to_ref=right,
                                             relationship_type=str(relationship),
                                             connection_type=str(connection_type),
                                             ruleset_version=str(ruleset)),
            "from": left.as_dict(), "to": right.as_dict(),
            "relationship_type": relationship, "connection_type": connection_type,
            "confidence": float(confidence), "confidence_band": band, "match_method": method,
            "supporting_source_refs": refs, "signal_explanation": explanation,
            "ruleset_version": ruleset, "observed_at": observed_at,
            "computed_at": computed_at, "conflicting": conflicting, "suppressed": suppressed,
            "storage_state": "private", "publication_status": "not_eligible",
        })
    _resolve_edge_support_ids(connection, repaired)
    counts = persist_connection_edges(connection, repaired) if repaired else {
        "inserted": 0, "updated": 0, "unchanged": 0,
        "skipped_exact": 0, "total": 0,
    }
    return {"repairable_legacy_inferred_edges": len(rows),
            "native_endpoint_repair_inserted": counts["inserted"],
            "native_endpoint_repair_updated": counts["updated"],
            "native_endpoint_repair_unchanged": counts["unchanged"],
            "native_endpoint_repair_skipped_exact": counts["skipped_exact"]}


def _repair_generic_facility_endpoint_types(connection: Any) -> dict[str, int]:
    """Append source-native endpoint types for retained inferred edges.

    The matcher historically persisted ``establishment_id`` for some mapped
    facility sources. Repair is deliberately narrower than rematching: both
    support refs must resolve by exact source/key/artifact to the current
    promoted release, and each generic endpoint must have one exact
    source-native identifier on that same canonical facility. Existing edge
    rows are never updated or deleted; the corrected endpoint types receive a
    new deterministic edge key.
    """
    registry = json.dumps([
        {"source_id": source_id, "identifier_type": identifier_type}
        for source_id, (identifier_type, _namespace) in sorted(FACILITY_IDENTIFIERS.items())
    ], separators=(",", ":"))
    cursor = connection.execute(
        """
        WITH selected_release AS MATERIALIZED (
            SELECT release_id FROM uec.releases
            WHERE status='promoted' AND test_only IS NOT TRUE AND profile='official'
            ORDER BY created_at DESC, release_id DESC LIMIT 1
        ), record_facility_candidates AS MATERIALIZED (
            SELECT DISTINCT model.source_record_id, model.facility_id
            FROM uec.map_facilities_public_discovery_read_model model
            WHERE model.release_id=(SELECT release_id FROM selected_release)
        ), ambiguous_record_facilities AS MATERIALIZED (
            SELECT source_record_id FROM record_facility_candidates
            GROUP BY source_record_id HAVING count(*)>1
        ), record_facilities AS MATERIALIZED (
            SELECT candidate.source_record_id, candidate.facility_id
            FROM record_facility_candidates candidate
            LEFT JOIN ambiguous_record_facilities ambiguous USING (source_record_id)
            WHERE ambiguous.source_record_id IS NULL
        ), edge_base AS MATERIALIZED (
            SELECT edge.connection_edge_id, edge.edge_key, edge.relationship_type,
                   edge.connection_type, edge.confidence, edge.confidence_band,
                   edge.match_method, edge.supporting_source_refs,
                   edge.signal_explanation, edge.ruleset_version, edge.observed_at,
                   edge.computed_at, edge.conflicting, edge.suppressed,
                   edge.from_entity_type, edge.from_source_id, edge.from_identifier_type,
                   edge.from_source_identifier, edge.to_entity_type, edge.to_source_id,
                   edge.to_identifier_type, edge.to_source_identifier
            FROM uec.graph_connection_edges edge
            WHERE edge.connection_type='inferred'
              AND edge.storage_state='private'
              AND edge.publication_status='not_eligible'
              AND (edge.from_identifier_type='establishment_id'
                   OR edge.to_identifier_type='establishment_id')
              AND jsonb_array_length(edge.supporting_source_refs)=2
        ), edge_refs AS MATERIALIZED (
            SELECT edge.connection_edge_id, refs.ordinality, refs.value,
                   CASE WHEN refs.ordinality=1 THEN edge.from_entity_type ELSE edge.to_entity_type END AS entity_type,
                   CASE WHEN refs.ordinality=1 THEN edge.from_source_id ELSE edge.to_source_id END AS endpoint_source_id,
                   CASE WHEN refs.ordinality=1 THEN edge.from_identifier_type ELSE edge.to_identifier_type END AS identifier_type,
                   CASE WHEN refs.ordinality=1 THEN edge.from_source_identifier ELSE edge.to_source_identifier END AS endpoint_value
            FROM edge_base edge
            CROSS JOIN LATERAL jsonb_array_elements(edge.supporting_source_refs)
                WITH ORDINALITY AS refs(value, ordinality)
            WHERE refs.value->>'role'=CASE WHEN refs.ordinality=1 THEN 'from' ELSE 'to' END
              AND refs.value->>'source_id'=CASE WHEN refs.ordinality=1
                    THEN edge.from_source_id ELSE edge.to_source_id END
              AND refs.value ? 'source_record_id'
              AND refs.value ? 'source_record_key'
              AND refs.value ? 'artifact_sha256'
        ), support_route_candidates AS MATERIALIZED (
            SELECT refs.connection_edge_id, refs.ordinality,
                   private_record.source_record_id AS support_record_id,
                   private_record.source_id, private_record.artifact_id,
                   private_record.source_record_id AS canonical_source_record_id,
                   direct.facility_id
            FROM edge_refs refs
            JOIN uec.raw_artifacts artifact
              ON lower(artifact.sha256)=lower(refs.value->>'artifact_sha256')
            JOIN uec.source_records private_record
              ON private_record.source_record_id=(refs.value->>'source_record_id')::uuid
             AND private_record.source_id=refs.endpoint_source_id
             AND private_record.source_record_key=refs.value->>'source_record_key'
             AND private_record.artifact_id=artifact.artifact_id
            JOIN record_facilities direct
              ON direct.source_record_id=private_record.source_record_id
            UNION
            SELECT refs.connection_edge_id, refs.ordinality,
                   private_record.source_record_id AS support_record_id,
                   private_record.source_id, private_record.artifact_id,
                   binding.canonical_source_record_id,
                   canonical.facility_id
            FROM edge_refs refs
            JOIN uec.raw_artifacts artifact
              ON lower(artifact.sha256)=lower(refs.value->>'artifact_sha256')
            JOIN uec.source_records private_record
              ON private_record.source_record_id=(refs.value->>'source_record_id')::uuid
             AND private_record.source_id=refs.endpoint_source_id
             AND private_record.source_record_key=refs.value->>'source_record_key'
             AND private_record.artifact_id=artifact.artifact_id
            JOIN uec.graph_record_release_bindings binding
              ON binding.private_source_record_id=private_record.source_record_id
             AND binding.source_id=private_record.source_id
             AND binding.artifact_id=private_record.artifact_id
             AND binding.release_id=(SELECT release_id FROM selected_release)
            JOIN uec.source_records canonical_record
              ON canonical_record.source_record_id=binding.canonical_source_record_id
             AND canonical_record.source_id=binding.source_id
             AND canonical_record.artifact_id=binding.artifact_id
            JOIN record_facilities canonical
              ON canonical.source_record_id=binding.canonical_source_record_id
             AND canonical.facility_id=binding.facility_id
        ), unique_support_routes AS MATERIALIZED (
            SELECT connection_edge_id, ordinality, support_record_id,
                   source_id, artifact_id,
                   (array_agg(DISTINCT canonical_source_record_id
                              ORDER BY canonical_source_record_id))[1] AS canonical_source_record_id,
                   (array_agg(DISTINCT facility_id ORDER BY facility_id))[1] AS facility_id
            FROM support_route_candidates
            GROUP BY connection_edge_id, ordinality, support_record_id, source_id, artifact_id
            HAVING count(DISTINCT canonical_source_record_id)=1
               AND count(DISTINCT facility_id)=1
        ), bound_refs AS MATERIALIZED (
            SELECT refs.*, route.facility_id,
                   registry.identifier_type AS mapped_identifier_type,
                   identifier.identifier_type AS exact_identifier_type
            FROM edge_refs refs
            JOIN unique_support_routes route
              ON route.connection_edge_id=refs.connection_edge_id
             AND route.ordinality=refs.ordinality
             AND route.support_record_id=(refs.value->>'source_record_id')::uuid
             AND route.source_id=refs.endpoint_source_id
            JOIN uec.source_records canonical_record
              ON canonical_record.source_record_id=route.canonical_source_record_id
             AND canonical_record.source_id=route.source_id
             AND canonical_record.artifact_id=route.artifact_id
            LEFT JOIN jsonb_to_recordset(%s::jsonb) AS registry(source_id text, identifier_type text)
              ON registry.source_id=refs.endpoint_source_id
            LEFT JOIN uec.source_entity_identifiers identifier
              ON refs.entity_type='facility'
             AND refs.identifier_type='establishment_id'
             AND registry.identifier_type IS NOT NULL
             AND identifier.source_record_id=canonical_record.source_record_id
             AND identifier.source_id=canonical_record.source_id
             AND identifier.facility_id=route.facility_id
             AND identifier.entity_type='facility'
             AND identifier.identifier_type=registry.identifier_type
             AND identifier.source_identifier=refs.endpoint_value
        ), resolved_endpoints AS MATERIALIZED (
            SELECT connection_edge_id, ordinality,
                   CASE WHEN identifier_type='establishment_id'
                        THEN min(exact_identifier_type) ELSE min(identifier_type) END AS resolved_identifier_type,
                   count(DISTINCT exact_identifier_type) AS exact_type_count,
                   count(DISTINCT facility_id) AS exact_facility_count
            FROM bound_refs
            GROUP BY connection_edge_id, ordinality, identifier_type
            HAVING count(DISTINCT facility_id)=1
               AND (identifier_type<>'establishment_id'
                    OR count(DISTINCT exact_identifier_type)=1)
        ), fully_resolved AS MATERIALIZED (
            SELECT edge.connection_edge_id,
                   from_endpoint.resolved_identifier_type AS from_identifier_type,
                   to_endpoint.resolved_identifier_type AS to_identifier_type
            FROM edge_base edge
            JOIN resolved_endpoints from_endpoint
              ON from_endpoint.connection_edge_id=edge.connection_edge_id
             AND from_endpoint.ordinality=1
            JOIN resolved_endpoints to_endpoint
              ON to_endpoint.connection_edge_id=edge.connection_edge_id
             AND to_endpoint.ordinality=2
        )
        SELECT edge.edge_key, edge.relationship_type, edge.connection_type,
               edge.confidence, edge.confidence_band, edge.match_method,
               edge.supporting_source_refs, edge.signal_explanation,
               edge.ruleset_version, edge.observed_at, edge.computed_at,
               edge.conflicting, edge.suppressed,
               edge.from_entity_type, edge.from_source_id,
               resolved.from_identifier_type, edge.from_source_identifier,
               edge.to_entity_type, edge.to_source_id,
               resolved.to_identifier_type, edge.to_source_identifier
        FROM edge_base edge
        JOIN fully_resolved resolved USING (connection_edge_id)
        WHERE edge.from_identifier_type IS DISTINCT FROM resolved.from_identifier_type
           OR edge.to_identifier_type IS DISTINCT FROM resolved.to_identifier_type
        """,
        (registry,),
    )
    rows = cursor.fetchall()
    repaired = []
    for row in rows:
        (old_key, relationship, connection_type, confidence, band, method, refs,
         explanation, ruleset, observed_at, computed_at, conflicting, suppressed,
         from_type, from_source, from_identifier_type, from_value,
         to_type, to_source, to_identifier_type, to_value) = row
        left = EntityRef(str(from_type), str(from_source), str(from_identifier_type), str(from_value))
        right = EntityRef(str(to_type), str(to_source), str(to_identifier_type), str(to_value))
        repaired.append({
            "edge_key": connection_edge_key(
                from_ref=left, to_ref=right,
                relationship_type=str(relationship),
                connection_type=str(connection_type),
                ruleset_version=str(ruleset),
            ),
            "from": left.as_dict(), "to": right.as_dict(),
            "relationship_type": relationship, "connection_type": connection_type,
            "confidence": float(confidence), "confidence_band": band,
            "match_method": method, "supporting_source_refs": refs,
            "signal_explanation": explanation, "ruleset_version": ruleset,
            "observed_at": observed_at, "computed_at": computed_at,
            "conflicting": conflicting, "suppressed": suppressed,
            "storage_state": "private", "publication_status": "not_eligible",
        })
    counts = persist_connection_edges(connection, repaired) if repaired else {
        "inserted": 0, "updated": 0, "unchanged": 0,
        "skipped_exact": 0, "total": 0,
    }
    return {"repairable_generic_facility_endpoint_edges": len(rows),
            "generic_facility_endpoint_repair_inserted": counts["inserted"],
            "generic_facility_endpoint_repair_updated": counts["updated"],
            "generic_facility_endpoint_repair_unchanged": counts["unchanged"],
            "generic_facility_endpoint_repair_skipped_exact": counts["skipped_exact"]}


def backfill_approved_graph_identifier_bindings(database_url: str, handoff_dir: str | Path, *,
                                                private_target: tuple[str, str]) -> dict[str, Any]:
    """Attach existing private Italy assertions to exact approved source rows.

    This append-only projection backfill writes only graph identifiers. It
    requires a completed source import, the identical source artifact, one
    current promoted official release, and one-to-one native recognition /
    activity mappings on both the candidate and release sides. It copies
    private evidence-state columns unchanged and never changes release or
    review decisions.
    """
    expected_database, purpose = private_target
    require_private_graph_target(database_url, expected_database=expected_database, purpose=purpose)
    manifest, handoff_digest, _item_count = inspect_graph_candidate_handoff(handoff_dir)
    source_id = str(manifest["source_id"])
    if source_id != "it.853-2004":
        raise GraphPersistenceError("canonical native binding is not configured for this source")
    artifact_sha = str(manifest.get("checksum_sha256") or manifest.get("source_artifact_sha256") or handoff_digest)
    if len(artifact_sha) != 64:
        artifact_sha = handoff_digest
    with psycopg.connect(database_url) as connection:
        _validate_private_graph_writer(connection, expected_database)
        run = connection.execute(
            "SELECT ingest_run_id,status FROM uec.graph_ingest_runs WHERE source_id=%s AND handoff_sha256=%s",
            (source_id, handoff_digest),
        ).fetchone()
        if not run or run[1] != "completed":
            raise GraphPersistenceError("canonical binding requires a completed private graph import")
        artifact = connection.execute("SELECT artifact_id FROM uec.raw_artifacts WHERE sha256=%s", (artifact_sha,)).fetchone()
        if not artifact:
            raise GraphPersistenceError("canonical binding source artifact is missing")
        run_id, artifact_id = run[0], artifact[0]
        connection.commit()
        with connection.transaction():
            summary = _italy_binding_summary(connection, run_id, source_id, artifact_id)
            inserted_counts = _insert_italy_canonical_identifier_bindings(connection, run_id, source_id, artifact_id)
            support_ref_rows_updated = _backfill_graph_edge_support_record_ids(
                connection, run_id, source_id, artifact_id)
            endpoint_repair_counts = _repair_inferred_native_endpoints(
                connection, source_id, artifact_id)
    return {"status": "completed", "source_id": source_id,
            "canonical_binding_counts": {**summary, **inserted_counts,
                                          "support_ref_rows_updated": support_ref_rows_updated,
                                          **endpoint_repair_counts}}


def _candidate_entity_maps(candidate: dict[str, Any], source_id: str) -> dict[str, EntityRef]:
    refs: dict[str, EntityRef] = {}
    for entity_type in ("facilities", "organizations"):
        expected = "facility" if entity_type == "facilities" else "organization"
        for entity in candidate.get(entity_type, ()):
            if not isinstance(entity, dict):
                raise GraphPersistenceError("graph candidate entities must be objects")
            local_ref = entity.get("local_ref")
            if not isinstance(local_ref, str) or not local_ref:
                raise GraphPersistenceError("graph candidate entity local_ref is required")
            identifier = entity.get("source_identifier")
            if not isinstance(identifier, dict):
                raise GraphPersistenceError("graph candidate entity source_identifier is required")
            # Do not infer an endpoint kind from arbitrary matcher payloads;
            # the handoff's typed collection is authoritative.
            refs[local_ref] = EntityRef(
                entity_type=expected,
                source_id=str(identifier.get("source_id") or source_id),
                identifier_type=str(identifier.get("identifier_type") or ""),
                source_identifier=str(identifier.get("value") or ""),
            )
    return refs


def _forbidden_evidence_facility_pair(left: EntityRef, right: EntityRef) -> bool:
    sources = {left.source_id, right.source_id}
    return bool(sources & _APHIS_FSIS_SOURCES) and bool(sources & _FSIS_SOURCES) and left.source_id != right.source_id


def _artifact_sha_for_manifest(manifest: dict[str, Any]) -> str | None:
    value = manifest.get("checksum_sha256") or manifest.get("source_artifact_sha256")
    if isinstance(value, str) and len(value) == 64:
        return value.lower()
    return None


def _lookup_source_record_id(source_record_ids: Mapping[Any, uuid.UUID | str] | None,
                             source_id: str, key: str, artifact_sha256: str | None) -> uuid.UUID | str | None:
    if not source_record_ids:
        return None
    if artifact_sha256:
        exact = source_record_ids.get((source_id, key, artifact_sha256.lower()))
        if exact:
            return exact
        return None
    return source_record_ids.get((source_id, key))


def _resolve_edge_support_ids(connection: Any, edges: list[dict[str, Any]]) -> None:
    """Resolve missing support IDs in one exact, batched source/key/SHA lookup."""
    refs = {
        (str(ref.get("source_id") or ""), str(ref.get("source_record_key") or ""),
         str(ref.get("artifact_sha256") or "").lower())
        for edge in edges for ref in edge.get("supporting_source_refs", [])
        if not ref.get("source_record_id") and ref.get("source_record_key")
        and isinstance(ref.get("artifact_sha256"), str)
        and len(ref["artifact_sha256"]) == 64
    }
    if not refs:
        return
    payload = json.dumps([
        {"source_id": source_id, "source_record_key": key, "artifact_sha256": sha}
        for source_id, key, sha in sorted(refs)
    ], separators=(",", ":"))
    rows = connection.execute(
        """SELECT requested.source_id, requested.source_record_key,
                  requested.artifact_sha256, record.source_record_id
             FROM jsonb_to_recordset(%s::jsonb) AS requested(
                 source_id text, source_record_key text, artifact_sha256 text)
             JOIN uec.raw_artifacts artifact
               ON lower(artifact.sha256)=requested.artifact_sha256
             JOIN uec.source_records record
               ON record.source_id=requested.source_id
              AND record.source_record_key=requested.source_record_key
              AND record.artifact_id=artifact.artifact_id""",
        (payload,),
    ).fetchall()
    resolved = {(str(source_id), str(key), str(sha).lower()): record_id
                for source_id, key, sha, record_id in rows}
    for edge in edges:
        for ref in edge.get("supporting_source_refs", []):
            if ref.get("source_record_id"):
                continue
            identity = (str(ref.get("source_id") or ""),
                        str(ref.get("source_record_key") or ""),
                        str(ref.get("artifact_sha256") or "").lower())
            record_id = resolved.get(identity)
            if record_id:
                ref["source_record_id"] = str(record_id)


def _source_refs(candidate: dict[str, Any], manifest: dict[str, Any], *,
                 source_record_ids: Mapping[Any, uuid.UUID | str] | None = None) -> list[SourceRef]:
    source_id = str(candidate.get("source_id") or manifest["source_id"])
    key = candidate.get("source_record_key") or candidate.get("source_observation_key")
    if not isinstance(key, str) or not key.strip():
        raise GraphPersistenceError("connection candidate requires source_record_key")
    artifact_sha = _artifact_sha_for_manifest(manifest)
    record_id = _lookup_source_record_id(source_record_ids, source_id, key, artifact_sha)
    return [SourceRef(source_id=source_id, source_record_key=key,
                      source_record_id=str(record_id) if record_id else None,
                      artifact_sha256=artifact_sha)]


def _matcher_edge(raw: dict[str, Any], candidate: dict[str, Any], manifest: dict[str, Any], *,
                  source_record_ids: Mapping[Any, uuid.UUID | str] | None = None) -> dict[str, Any] | None:
    """Adapt the matcher lane's result to the shared score/build contract.

    The matcher is deliberately not implemented here.  It may hand us an
    already-built edge, or endpoint refs plus signal mappings.  This adapter
    keeps persistence independent of matcher implementation details while
    making every persisted edge pass the same validation gate.
    """
    if not isinstance(raw, dict):
        raise GraphPersistenceError("matcher edge must be an object")
    if {"edge_key", "from", "to", "connection_type"}.issubset(raw):
        edge = dict(validate_connection_edge(raw))
        original_from = EntityRef(**{key: edge["from"][key] for key in
                                     ("entity_type", "source_id", "identifier_type", "source_identifier")})
        original_to = EntityRef(**{key: edge["to"][key] for key in
                                   ("entity_type", "source_id", "identifier_type", "source_identifier")})
        from_ref, to_ref = _native_matcher_endpoint(original_from), _native_matcher_endpoint(original_to)
        if from_ref != original_from or to_ref != original_to:
            edge["from"], edge["to"] = from_ref.as_dict(), to_ref.as_dict()
            # The typed endpoint is a new append-only edge representation;
            # the old key/payload remain untouched in persistence.
            edge["edge_key"] = connection_edge_key(
                from_ref=from_ref, to_ref=to_ref,
                relationship_type=str(edge["relationship_type"]),
                connection_type=str(edge["connection_type"]),
                ruleset_version=str(edge["ruleset_version"]),
            )
            edge = validate_connection_edge(edge)
        # Shared-name edges may only enter via the source-aware private matcher
        # below, which verifies FSIS endpoints and both source-record supports.
        if edge.get("relationship_type") == "shared_business_name":
            return None
        edge["supporting_source_refs"] = [dict(ref) for ref in edge["supporting_source_refs"]]
        for ref in edge["supporting_source_refs"]:
            key = ref.get("source_record_key")
            ref_source = str(ref.get("source_id") or "")
            record_id = _lookup_source_record_id(source_record_ids, ref_source, str(key or ""),
                                                 ref.get("artifact_sha256"))
            if record_id and not ref.get("source_record_id"):
                ref["source_record_id"] = str(record_id)
        if _forbidden_evidence_facility_pair(
            EntityRef(**{key: edge["from"][key] for key in ("entity_type", "source_id", "identifier_type", "source_identifier")}),
            EntityRef(**{key: edge["to"][key] for key in ("entity_type", "source_id", "identifier_type", "source_identifier")}),
        ):
            return None
        return edge

    # The indexed D6 matcher intentionally returns a compact candidate rather
    # than a database-shaped edge.  Adapt its source-qualified endpoints and
    # aggregate feature names to the shared scorer here.  This keeps matching
    # independent from persistence while ensuring every stored edge carries
    # the same explanation and provenance contract.
    matcher_endpoints = raw.get("endpoints")
    if isinstance(matcher_endpoints, list) and len(matcher_endpoints) == 2:
        left, right = matcher_endpoints
        if not all(isinstance(item, dict) for item in (left, right)):
            raise GraphPersistenceError("matcher candidate endpoints must be objects")
        left_ref = EntityRef(
            entity_type=str(left.get("entity_type") or ""),
            source_id=str(left.get("source_id") or ""),
            identifier_type=str(left.get("identifier_type") or ""),
            source_identifier=str(left.get("source_identifier") or ""),
        )
        right_ref = EntityRef(
            entity_type=str(right.get("entity_type") or ""),
            source_id=str(right.get("source_id") or ""),
            identifier_type=str(right.get("identifier_type") or ""),
            source_identifier=str(right.get("source_identifier") or ""),
        )
        left_ref, right_ref = _native_matcher_endpoint(left_ref), _native_matcher_endpoint(right_ref)
        if _forbidden_evidence_facility_pair(left_ref, right_ref):
            return None
        if raw.get("relationship_type") == "shared_business_name":
            provenance = raw.get("provenance")
            legacy_fsis = (
                raw.get("ruleset") == "d6-shared-business-name-v2"
                and raw.get("method") == "exact_fsis_alternate_name_equality"
                and left_ref.source_id == right_ref.source_id == "us.fsis"
            )
            current_declared_name = (
                raw.get("ruleset") == "d7-shared-business-name-v3"
                and raw.get("method") == "exact_declared_business_name_equality"
            )
            if (left_ref.entity_type != "facility" or right_ref.entity_type != "facility"
                    or not (legacy_fsis or current_declared_name)
                    or raw.get("contributing_features") != ["shared_business_name"]
                    or not isinstance(provenance, list) or len(provenance) != 2
                    or any(not isinstance(item, dict) or not item.get("source_id")
                           or not item.get("source_record_key") for item in provenance)
                    or provenance[0].get("source_record_key") == provenance[1].get("source_record_key")
                    or {str(item["source_id"]) for item in provenance}
                       != {left_ref.source_id, right_ref.source_id}):
                return None
        signal_names = {
            "name": "organization_name_normalized",
            "postal": "postal_match",
            "city": "city_match",
            "address": "address_match",
            "business_domain": "website_domain_match",
            "business_phone": "business_phone_match",
            "shared_business_name": "shared_business_name",
        }
        signals = []
        for name in raw.get("contributing_features", ()):
            if name not in signal_names:
                continue
            details = {"basis": "exact_declared_business_name_equality"} if name == "shared_business_name" else {"basis": "indexed_normalized_block"}
            if name == "shared_business_name":
                details["scope"] = "shared_business_name_only_not_ownership_operator_or_facility_identity"
            signals.append({"name": signal_names[name], "details": details})
        for contradiction in raw.get("contradictory_evidence", ()):
            if not isinstance(contradiction, dict):
                continue
            name = str(contradiction.get("signal") or "")
            if name in {"conflicting_identifier", "conflicting_address", "temporal_conflict"}:
                signals.append({"name": name, "details": {"basis": "indexed_normalized_block"}})
        scoring = score_connection(signals)
        if not scoring.eligible or scoring.connection_type != "inferred":
            return None
        provenance = raw.get("provenance")
        refs = []
        if isinstance(provenance, list):
            for index, item in enumerate(provenance):
                if isinstance(item, dict) and item.get("source_id") and item.get("source_record_key"):
                    source_id, source_key = str(item["source_id"]), str(item["source_record_key"])
                    record_id = _lookup_source_record_id(source_record_ids, source_id, source_key,
                                                         item.get("artifact_sha256"))
                    source_sha = item.get("artifact_sha256")
                    refs.append(SourceRef(source_id=source_id, source_record_key=source_key,
                                          source_record_id=str(record_id) if record_id else None,
                                          role="from" if index == 0 else "to",
                                          artifact_sha256=source_sha))
        if not refs:
            refs = _source_refs(candidate, manifest, source_record_ids=source_record_ids)
        return build_connection_edge(
            from_ref=left_ref,
            to_ref=right_ref,
            relationship_type=str(raw.get("relationship_type") or "related_facility"),
            scoring=scoring,
            supporting_source_refs=refs,
            observed_at=_observed_at(raw.get("observed_at") or candidate.get("observed_at"), manifest),
            conflicting=bool(raw.get("contradictory_evidence")),
            suppressed=bool(raw.get("suppressed")),
            computed_at=str(raw.get("computed_at") or manifest.get("retrieved_at_utc") or _timestamp(manifest)),
        )

    left = raw.get("from") or raw.get("from_ref") or raw.get("left")
    right = raw.get("to") or raw.get("to_ref") or raw.get("right")
    if isinstance(left, EntityRef):
        left_ref = left
    elif isinstance(left, dict):
        left_ref = EntityRef(
            entity_type=str(left.get("entity_type") or ""), source_id=str(left.get("source_id") or manifest["source_id"]),
            identifier_type=str(left.get("identifier_type") or left.get("source_identifier_type") or ""),
            source_identifier=str(left.get("source_identifier") or left.get("value") or ""),
        )
    else:
        raise GraphPersistenceError("matcher edge requires a from endpoint")
    if isinstance(right, EntityRef):
        right_ref = right
    elif isinstance(right, dict):
        right_ref = EntityRef(
            entity_type=str(right.get("entity_type") or ""), source_id=str(right.get("source_id") or manifest["source_id"]),
            identifier_type=str(right.get("identifier_type") or right.get("source_identifier_type") or ""),
            source_identifier=str(right.get("source_identifier") or right.get("value") or ""),
        )
    else:
        raise GraphPersistenceError("matcher edge requires a to endpoint")
    left_ref, right_ref = _native_matcher_endpoint(left_ref), _native_matcher_endpoint(right_ref)
    if _forbidden_evidence_facility_pair(left_ref, right_ref):
        return None
    signals = raw.get("signals") or raw.get("signal_bundle") or raw.get("match_signals")
    if not isinstance(signals, list):
        raise GraphPersistenceError("matcher edge requires a signal list")
    scoring = score_connection(signals)
    if not scoring.eligible:
        return None
    observed_at = _observed_at(raw.get("observed_at") or candidate.get("observed_at"), manifest)
    return build_connection_edge(
        from_ref=left_ref,
        to_ref=right_ref,
        relationship_type=str(raw.get("relationship_type") or "related_to"),
        scoring=scoring,
        supporting_source_refs=_source_refs(candidate, manifest, source_record_ids=source_record_ids),
        observed_at=observed_at,
        conflicting=bool(raw.get("conflicting") or raw.get("contradictory_evidence")),
        suppressed=bool(raw.get("suppressed")),
        # A retrieval timestamp makes a rerun byte/digest stable while still
        # preserving a distinct observed timestamp from the source row.
        computed_at=str(raw.get("computed_at") or manifest.get("retrieved_at_utc") or _timestamp(manifest)),
    )


def build_candidate_connection_edges(candidate: dict[str, Any], manifest: dict[str, Any], *,
                                     edge_builder: ConnectionEdgeBuilder | None = None,
                                     source_record_ids: Mapping[tuple[str, str], uuid.UUID | str] | None = None) -> list[dict[str, Any]]:
    """Build exact and matcher-supplied inferred edges for one facility row.

    Exact source assertions come from typed facility/organization references in
    the handoff.  Inferred candidates are accepted only through ``edge_builder``
    or the small endpoint/signal adapter above; no fuzzy matching is performed
    in the persistence layer.
    """
    refs = _candidate_entity_maps(candidate, str(manifest["source_id"]))
    built: list[dict[str, Any]] = []
    for relationship in candidate.get("relationships", ()):
        if not isinstance(relationship, dict) or relationship.get("assertion_status", "asserted") in {"unknown", "rejected"}:
            continue
        from_ref = refs.get(relationship.get("from_organization_ref"))
        target_ref = refs.get(relationship.get("target_facility_ref") or relationship.get("target_organization_ref"))
        if from_ref is None or target_ref is None or _forbidden_evidence_facility_pair(from_ref, target_ref):
            continue
        if relationship.get("connection_type") == "inferred":
            signal_bundle = relationship.get("signal_bundle") or relationship.get("signals")
            if not isinstance(signal_bundle, list):
                continue
            scoring = score_connection(signal_bundle)
            if scoring.connection_type != "inferred":
                continue
        else:
            scoring = score_connection([{"name": "source_assertion", "details": {"method": relationship.get("evidence_method") or "source_asserted_relationship"}}])
        built.append(build_connection_edge(
            from_ref=from_ref, to_ref=target_ref,
            relationship_type=str(relationship.get("relationship_type")), scoring=scoring,
            supporting_source_refs=_source_refs(candidate, manifest, source_record_ids=source_record_ids),
            observed_at=_observed_at(relationship.get("observed_at") or candidate.get("observed_at"), manifest),
            conflicting=relationship.get("assertion_status") in {"disputed", "rejected"},
            computed_at=str(manifest.get("retrieved_at_utc") or _timestamp(manifest)),
        ))

    # Matcher lanes can attach records without requiring a schema migration.
    # `connection_candidates` is the preferred name; the aliases keep this
    # boundary compatible with earlier private handoff prototypes.
    matcher_candidates = list(candidate.get("connection_candidates") or candidate.get("inferred_candidates") or candidate.get("edges") or ())
    if edge_builder is not None:
        matcher_candidates.extend(edge_builder(candidate, manifest))
    for raw in matcher_candidates:
        edge = _matcher_edge(raw, candidate, manifest, source_record_ids=source_record_ids)
        if edge is not None:
            built.append(edge)
    # Version inferred matches by ordered support artifact identity. Native
    # endpoint identity itself remains unchanged.
    for edge in built:
        if edge.get("connection_type") != "inferred":
            continue
        version_refs = [
            (str(ref.get("source_id") or ""), str(ref.get("source_record_key") or ""),
             str(ref.get("artifact_sha256") or "").lower())
            for ref in edge.get("supporting_source_refs", [])
        ]
        if version_refs and all(len(item[2]) == 64 for item in version_refs):
            suffix = hashlib.sha256(json.dumps(
                version_refs, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")).hexdigest()
            edge["edge_key"] = f"{edge['edge_key']}:support-v1:{suffix}"
    # A matcher may repeat an explicit edge while enriching its explanation.
    return list({edge["edge_key"]: edge for edge in built}.values())


def _persist_candidate(connection: Any, manifest: dict[str, Any], candidate: dict[str, Any],
                       artifact_id: uuid.UUID, handoff_digest: str,
                       *, edge_builder: ConnectionEdgeBuilder | None = None,
                       materialize_edges: bool = True,
                       require_approved_facility: bool = False,
                       approved_facility_map: dict[tuple[str, str, uuid.UUID], set[uuid.UUID]] | None = None,
                       mapping_diagnostics: dict[str, int] | None = None) -> dict[str, int]:
    source_record_key = candidate["source_record_key"]
    graph_context = {
        key: candidate[key]
        for key in ("normalized_values", "name_assertions", "location_role", "business_contacts")
        if key in candidate
    }
    identifier_namespaces = [
        {"entity_ref": entity.get("local_ref"),
         "entity_type": "facility" if entity_type == "facilities" else "organization",
         "identifier_type": (entity.get("source_identifier") or {}).get("identifier_type"),
         "id_namespace": (entity.get("source_identifier") or {}).get("id_namespace", "source_scoped")}
        for entity_type in ("facilities", "organizations")
        for entity in candidate.get(entity_type, ())
        if isinstance(entity, dict) and isinstance(entity.get("source_identifier"), dict)
    ]
    identifier_namespaces.extend(
        {"entity_type": "facility", "identifier_type": item.get("identifier_type"),
         "id_namespace": item.get("id_namespace", "source_scoped"),
         "identity_scope": item.get("identity_scope", "source_scoped")}
        for item in candidate.get("additional_source_identifiers", ())
        if isinstance(item, dict)
    )
    if identifier_namespaces:
        graph_context["source_identifier_namespaces"] = identifier_namespaces
    record_id = _ensure_record(connection, manifest, artifact_id, source_record_key,
                               candidate.get("source_values") or {}, handoff_digest,
                               graph_context=graph_context)
    facilities, organizations = _entity_maps(connection, manifest, candidate, record_id, artifact_id,
                                             require_approved_facility=require_approved_facility,
                                             approved_facility_map=approved_facility_map,
                                             mapping_diagnostics=mapping_diagnostics)
    for relationship in candidate.get("relationships", []):
        assertion = relationship.get("assertion_status", "asserted")
        if assertion == "unknown":
            sql = """INSERT INTO uec.organization_relationship_observations
                (source_id,source_record_id,target_facility_id,target_organization_id,assertion_status,unknown_reason,observed_at,confidence,review_state,storage_state,privacy_status,publication_status)
                VALUES (%s,%s,%s,%s,'unknown',%s,%s,%s,'review_required','private','pending','not_eligible')"""
            args = (manifest["source_id"], record_id,
                    _facility_id_for_identifier(connection, facilities[relationship["target_facility_ref"]]) if relationship.get("target_facility_ref") else None,
                    _organization_id_for_identifier(connection, organizations[relationship["target_organization_ref"]]) if relationship.get("target_organization_ref") else None,
                    relationship["unknown_reason"], _observed_at(relationship.get("observed_at"), manifest), relationship.get("confidence"))
        else:
            from_org = _organization_id_for_identifier(connection, organizations[relationship["from_organization_ref"]])
            target_facility = _facility_id_for_identifier(connection, facilities[relationship["target_facility_ref"]]) if relationship.get("target_facility_ref") else None
            target_org = _organization_id_for_identifier(connection, organizations[relationship["target_organization_ref"]]) if relationship.get("target_organization_ref") else None
            sql = """INSERT INTO uec.organization_relationship_observations
                (source_id,source_record_id,from_organization_id,target_facility_id,target_organization_id,relationship_type,assertion_status,valid_from,valid_to,observed_at,confidence,review_state,storage_state,privacy_status,publication_status,note)
                SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'review_required','private','pending','not_eligible',%s
                WHERE NOT EXISTS (SELECT 1 FROM uec.organization_relationship_observations WHERE source_id=%s AND source_record_id=%s AND from_organization_id=%s AND target_facility_id IS NOT DISTINCT FROM %s AND target_organization_id IS NOT DISTINCT FROM %s AND relationship_type=%s AND observed_at=%s)"""
            args = (manifest["source_id"], record_id, from_org, target_facility, target_org,
                    relationship["relationship_type"], assertion, _date(relationship.get("valid_from")), _date(relationship.get("valid_to")),
                    _observed_at(relationship.get("observed_at"), manifest), relationship.get("confidence"), relationship.get("evidence_method"),
                    manifest["source_id"], record_id, from_org, target_facility, target_org, relationship["relationship_type"], _observed_at(relationship.get("observed_at"), manifest))
        connection.execute(sql, args)
    for claim in candidate.get("claims", []):
        facility_id = _facility_id_for_identifier(connection, facilities[claim["facility_ref"]]) if claim.get("facility_ref") else None
        organization_id = _organization_id_for_identifier(connection, organizations[claim["organization_ref"]]) if claim.get("organization_ref") else None
        claim_row = connection.execute(
            """SELECT claim_id FROM uec.claims WHERE source_id=%s AND source_record_id=%s AND claim_domain=%s AND claim_kind=%s AND claim_value=%s::jsonb AND observed_at=%s""",
            (manifest["source_id"], record_id, claim["claim_domain"], claim["claim_kind"], json.dumps(claim.get("value")), _observed_at(claim.get("observed_at"), manifest)),
        ).fetchone()
        claim_id = claim_row[0] if claim_row else connection.execute(
            """INSERT INTO uec.claims
               (source_id,source_record_id,facility_id,organization_id,claim_domain,claim_kind,value_state,claim_value,unknown_reason,observed_at,confidence,review_state,storage_state,privacy_status,publication_status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'review_required','private','pending','not_eligible') RETURNING claim_id""",
            (manifest["source_id"], record_id, facility_id, organization_id, claim["claim_domain"], claim["claim_kind"],
             claim.get("value_state", "known"), json.dumps(claim.get("value")), claim.get("unknown_reason"),
             _observed_at(claim.get("observed_at"), manifest), claim.get("confidence")),
        ).fetchone()[0]
        for index, support in enumerate(claim.get("support", [])):
            support_record_id = record_id if support.get("source_record_key") == source_record_key else None
            support_artifact_id = artifact_id if support.get("artifact_sha256") else None
            if not support_record_id and not support_artifact_id:
                continue
            role = "primary" if index == 0 else "corroborating"
            connection.execute(
                """INSERT INTO uec.claim_support(claim_id,source_record_id,artifact_id,support_role,observed_at,storage_state)
                   SELECT %s,%s,%s,%s,%s,'private'
                   WHERE NOT EXISTS (SELECT 1 FROM uec.claim_support WHERE claim_id=%s AND source_record_id IS NOT DISTINCT FROM %s AND artifact_id IS NOT DISTINCT FROM %s)""",
                (claim_id, support_record_id, support_artifact_id, role, _observed_at(claim.get("observed_at"), manifest), claim_id, support_record_id, support_artifact_id),
            )
    ref_ids = {**facilities, **organizations}
    for crosswalk in candidate.get("crosswalks", []):
        left_id = ref_ids[crosswalk["left_ref"]]
        right_id = ref_ids[crosswalk["right_ref"]]
        connection.execute(
            """INSERT INTO uec.source_entity_crosswalks
               (left_identifier_id,right_identifier_id,source_id,source_record_id,assertion_status,match_method,confidence,review_state,storage_state,privacy_status,publication_status,observed_at,note)
               SELECT %s,%s,%s,%s,'review_required',%s,%s,'review_required','private','pending','not_eligible',%s,%s
               WHERE NOT EXISTS (SELECT 1 FROM uec.source_entity_crosswalks WHERE left_identifier_id=%s AND right_identifier_id=%s AND source_record_id=%s AND match_method=%s)""",
            (left_id, right_id, manifest["source_id"], record_id, crosswalk["match_method"], crosswalk.get("confidence"),
             _observed_at(candidate.get("observed_at"), manifest), crosswalk.get("note"), left_id, right_id, record_id, crosswalk["match_method"]),
        )
    connection_edges = build_candidate_connection_edges(
        candidate, manifest, edge_builder=edge_builder,
        source_record_ids={
            (str(manifest["source_id"]), str(source_record_key), _artifact_sha_for_manifest(manifest)): record_id
        } if _artifact_sha_for_manifest(manifest) else {
            (str(manifest["source_id"]), str(source_record_key)): record_id
        },
    ) if materialize_edges else []
    _resolve_edge_support_ids(connection, connection_edges)
    edge_counts = persist_connection_edges(connection, connection_edges) if connection_edges else {"inserted": 0, "updated": 0, "total": 0}
    return edge_counts


def _begin_run(connection: Any, manifest: dict[str, Any], source_kind: str, contract_version: str,
               digest: str, count: int) -> tuple[uuid.UUID, bool]:
    row = connection.execute(
        """SELECT ingest_run_id,status FROM uec.graph_ingest_runs WHERE source_id=%s AND handoff_sha256=%s""",
        (manifest["source_id"], digest),
    ).fetchone()
    if row:
        return row[0], row[1] == "completed"
    run_id = connection.execute(
        """INSERT INTO uec.graph_ingest_runs(source_id,source_kind,contract_version,handoff_sha256,item_count)
           VALUES (%s,%s,%s,%s,%s) RETURNING ingest_run_id""",
        (manifest["source_id"], source_kind, contract_version, digest, count),
    ).fetchone()[0]
    return run_id, False


def completed_edge_materialization(database_url: str, handoff_dir: str | Path, *,
                                   private_target: tuple[str, str], fingerprint: str) -> dict[str, Any] | None:
    """Return aggregate completion metadata before expensive matcher staging."""
    expected_database, purpose = private_target
    require_private_graph_target(database_url, expected_database=expected_database, purpose=purpose)
    manifest, _candidates, digest, item_count = iter_graph_candidate_handoff(handoff_dir)
    with psycopg.connect(database_url) as db:
        _validate_private_graph_writer(db, expected_database)
        row = db.execute(
            """SELECT materialization_run_id,status,edge_inserted_count,edge_updated_count,
                      edge_unchanged_count,edge_count,matcher_summary
                 FROM uec.graph_edge_materialization_runs
                WHERE source_id=%s AND handoff_sha256=%s AND materialization_fingerprint=%s""",
            (manifest["source_id"], digest, fingerprint),
        ).fetchone()
    if not row or row[1] != "completed":
        return None
    return {
        "status": "already_present", "source_id": manifest["source_id"],
        "item_count": item_count, "materialization_run_id": str(row[0]),
        "edge_inserted_count": int(row[2]), "edge_updated_count": int(row[3]),
        "edge_unchanged_count": int(row[4]), "edge_count": int(row[5]),
        "matcher": row[6] or {}, "staging_skipped": True,
    }


def _start_edge_materialization(connection: Any, source_id: str, handoff_sha256: str,
                                fingerprint: str) -> uuid.UUID:
    return connection.execute(
        """INSERT INTO uec.graph_edge_materialization_runs
             (source_id,handoff_sha256,materialization_fingerprint,status)
           VALUES (%s,%s,%s,'in_progress')
           ON CONFLICT (source_id,handoff_sha256,materialization_fingerprint)
           DO UPDATE SET status='in_progress',started_at=now(),completed_at=NULL
           RETURNING materialization_run_id""",
        (source_id, handoff_sha256, fingerprint),
    ).fetchone()[0]


def _complete_edge_materialization(connection: Any, materialization_run_id: uuid.UUID,
                                   counts: dict[str, int], matcher_summary: dict[str, Any] | None) -> None:
    connection.execute(
        """UPDATE uec.graph_edge_materialization_runs
              SET status='completed',edge_inserted_count=%s,edge_updated_count=%s,
                  edge_unchanged_count=%s,edge_count=%s,matcher_summary=%s,
                  completed_at=now(),error_category=NULL
            WHERE materialization_run_id=%s""",
        (counts.get("inserted", 0), counts.get("updated", 0), counts.get("unchanged", 0),
         counts.get("total", 0), json.dumps(matcher_summary or {}), materialization_run_id),
    )


def _fail_edge_materialization(connection: Any, materialization_run_id: uuid.UUID,
                               error: Exception) -> None:
    connection.execute(
        "UPDATE uec.graph_edge_materialization_runs SET status='failed',error_category=%s WHERE materialization_run_id=%s AND status<>'completed'",
        (error.__class__.__name__[:100], materialization_run_id),
    )


def _finalize_edge_materialization(connection: Any, materialization_run_id: uuid.UUID,
                                   counts: dict[str, int], matcher_summary: dict[str, Any] | None,
                                   finalize: Callable[[], Any]) -> Any:
    """Run required post-edge finalization before exposing a completed checkpoint."""
    try:
        result = finalize()
        with connection.transaction():
            _complete_edge_materialization(connection, materialization_run_id, counts, matcher_summary)
        return result
    except Exception as error:
        with connection.transaction():
            _fail_edge_materialization(connection, materialization_run_id, error)
        raise


def _mark_failed(connection: Any, run_id: uuid.UUID, error: Exception) -> None:
    # The run envelope is operational state (unlike the evidence rows) so a
    # failed process can be diagnosed and resumed without mutating evidence.
    connection.execute(
        "UPDATE uec.graph_ingest_runs SET status='failed', error_summary=%s WHERE ingest_run_id=%s AND status <> 'completed'",
        (f"{error.__class__.__name__}: {str(error)[:500]}", run_id),
    )


def import_graph_candidates(database_url: str, handoff_dir: str | Path, *,
                            disposable_db: bool = False, batch_size: int = DEFAULT_BATCH_SIZE,
                            on_batch_committed: BatchCommitObserver | None = None,
                            edge_builder: ConnectionEdgeBuilder | None = None,
                            private_target: tuple[str, str] | None = None,
                            materialization_fingerprint: str | None = None,
                            matcher_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Persist facility candidates in resumable private batches."""
    if private_target is None:
        require_disposable_graph_database(database_url, disposable_db)
    else:
        if disposable_db:
            raise GraphPersistenceError("choose either disposable or configured private target")
        require_private_graph_target(database_url, expected_database=private_target[0], purpose=private_target[1])
    if batch_size <= 0:
        raise GraphPersistenceError("batch size must be positive")
    manifest, candidates, digest, item_count = iter_graph_candidate_handoff(handoff_dir)
    started_at = time.perf_counter()
    with psycopg.connect(database_url) as db:
        if private_target is None:
            _verify_disposable_marker(db)
        else:
            dbname, _purpose = private_target
            _validate_private_graph_writer(db, dbname)
        db.commit()
        with db.transaction():
            _ensure_source_artifact(db, manifest, digest)
            run_id, completed = _begin_run(db, manifest, "facility_master", GRAPH_CONTRACT_VERSION, digest, item_count)
        artifact_sha = str(manifest.get("checksum_sha256") or manifest.get("source_artifact_sha256") or digest)
        artifact_id = db.execute("SELECT artifact_id FROM uec.raw_artifacts WHERE sha256=%s", (artifact_sha if len(artifact_sha) == 64 else digest,)).fetchone()[0]
        resume_offset = int(db.execute(
            "SELECT count(*) FROM uec.graph_ingest_items WHERE ingest_run_id=%s AND status='inserted'",
            (run_id,),
        ).fetchone()[0])
        base_import_complete = completed and resume_offset == item_count
        lineage_started_at = time.perf_counter()
        approved_facility_map = (
            _load_approved_facility_map(db, str(manifest["source_id"]), artifact_id)
            if private_target is not None and not base_import_complete and resume_offset < item_count else None
        )
        approved_lineage_seconds = round(time.perf_counter() - lineage_started_at, 6)
        # End psycopg's implicit transaction opened by the artifact/checkpoint
        # SELECTs above. Otherwise each explicit batch transaction below is a
        # savepoint and none of its writes become visible until the whole
        # import finishes, defeating resumable checkpoints for large handoffs.
        db.commit()
        inserted = 0 if base_import_complete else resume_offset
        already = item_count if base_import_complete else 0
        rejected = 0
        edge_inserted = edge_updated = edge_unchanged = edge_skipped_exact = 0
        source_assertion_rows = 0
        endpoint_mapping_diagnostics: dict[str, int] = {}
        try:
            if base_import_complete:
                # A completed run may predate context persistence. Revisit
                # only candidates that can append declared aliases or
                # organization-name assertions. Keep this separate from the
                # ingest loop so already_present_count and inserted_count
                # continue to describe the original completed run.
                context_batch: list[dict[str, Any]] = []
                for candidate in candidates:
                    if not _candidate_has_backfillable_context(str(manifest["source_id"]), candidate):
                        continue
                    context_batch.append(candidate)
                    if len(context_batch) >= batch_size:
                        with db.transaction():
                            for row_candidate in context_batch:
                                _backfill_existing_candidate_context(db, manifest, row_candidate, artifact_id)
                        context_batch = []
                if context_batch:
                    with db.transaction():
                        for row_candidate in context_batch:
                            _backfill_existing_candidate_context(db, manifest, row_candidate, artifact_id)
            batch: list[dict[str, Any]] = []
            offset = resume_offset
            batch_number = 0
            candidate_iterator = iter(()) if base_import_complete else iter(candidates)
            if not base_import_complete:
                for _ in range(resume_offset):
                    try:
                        next(candidate_iterator)
                    except StopIteration as exc:
                        raise GraphPersistenceError("handoff ended before the recorded ingest checkpoint") from exc
            for candidate in candidate_iterator:
                batch.append(candidate)
                if len(batch) < batch_size:
                    continue
                batch_number += 1
                batch_inserted = 0
                with db.transaction():
                    for candidate in batch:
                        item_digest = hashlib.sha256(canonical_json_bytes(candidate)).hexdigest()
                        existing = db.execute("SELECT 1 FROM uec.graph_ingest_items WHERE source_id=%s AND item_sha256=%s", (manifest["source_id"], item_digest)).fetchone()
                        if existing:
                            _backfill_existing_candidate_context(db, manifest, candidate, artifact_id)
                            already += 1
                            continue
                        _persist_candidate(db, manifest, candidate, artifact_id, digest,
                                           materialize_edges=edge_builder is None,
                                           require_approved_facility=private_target is not None,
                                           approved_facility_map=approved_facility_map,
                                           mapping_diagnostics=endpoint_mapping_diagnostics)
                        db.execute("INSERT INTO uec.graph_ingest_items(ingest_run_id,source_id,source_record_key,item_sha256,item_kind,status) VALUES (%s,%s,%s,%s,'facility_candidate','inserted')", (run_id, manifest["source_id"], candidate["source_record_key"], item_digest))
                        inserted += 1
                        batch_inserted += 1
                if on_batch_committed:
                    on_batch_committed(batch_number, offset, batch_inserted)
                offset += len(batch)
                batch = []
            if batch:
                batch_number += 1
                batch_inserted = 0
                with db.transaction():
                    for candidate in batch:
                        item_digest = hashlib.sha256(canonical_json_bytes(candidate)).hexdigest()
                        existing = db.execute("SELECT 1 FROM uec.graph_ingest_items WHERE source_id=%s AND item_sha256=%s", (manifest["source_id"], item_digest)).fetchone()
                        if existing:
                            _backfill_existing_candidate_context(db, manifest, candidate, artifact_id)
                            already += 1
                            continue
                        _persist_candidate(db, manifest, candidate, artifact_id, digest,
                                           materialize_edges=edge_builder is None,
                                           require_approved_facility=private_target is not None,
                                           approved_facility_map=approved_facility_map,
                                           mapping_diagnostics=endpoint_mapping_diagnostics)
                        db.execute("INSERT INTO uec.graph_ingest_items(ingest_run_id,source_id,source_record_key,item_sha256,item_kind,status) VALUES (%s,%s,%s,%s,'facility_candidate','inserted')", (run_id, manifest["source_id"], candidate["source_record_key"], item_digest))
                        inserted += 1
                        batch_inserted += 1
                if on_batch_committed:
                    on_batch_committed(batch_number, offset, batch_inserted)
        except Exception as error:
            with db.transaction():
                _mark_failed(db, run_id, error)
            raise
        if not base_import_complete:
            with db.transaction():
                db.execute("UPDATE uec.graph_ingest_runs SET status='completed', inserted_count=%s, already_present_count=%s, rejected_count=%s, error_summary=NULL, completed_at=now() WHERE ingest_run_id=%s", (inserted, already, rejected, run_id))
        materialization_run_id = None
        if edge_builder is not None or private_target is not None:
            if private_target is not None and materialization_fingerprint is not None:
                with db.transaction():
                    materialization_run_id = _start_edge_materialization(
                        db, str(manifest["source_id"]), digest, materialization_fingerprint)
            candidate_root, _ = _graph_candidate_root(handoff_dir)
            run_source_record_ids = _load_run_source_record_ids_for_edge_batches(
                db, run_id, artifact_id)
            edge_batch: list[dict[str, Any]] = []
            try:
                for candidate in _iter_candidate_payloads(candidate_root):
                    edge_batch.append(candidate)
                    if len(edge_batch) < batch_size:
                        continue
                    with db.transaction():
                        for row_candidate in edge_batch:
                            source_assertion_rows += sum(
                                1 for relationship in row_candidate.get("relationships", [])
                                if relationship.get("assertion_status", "asserted") == "asserted"
                            )
                            edges = build_candidate_connection_edges(
                                row_candidate, manifest, edge_builder=edge_builder,
                                source_record_ids=run_source_record_ids)
                            _resolve_edge_support_ids(db, edges)
                            counts = persist_connection_edges(db, edges)
                            edge_inserted += counts["inserted"]
                            edge_updated += counts["updated"]
                            edge_unchanged += counts.get("unchanged", 0)
                            edge_skipped_exact += counts["skipped_exact"]
                    edge_batch = []
                if edge_batch:
                    with db.transaction():
                        for row_candidate in edge_batch:
                            source_assertion_rows += sum(
                                1 for relationship in row_candidate.get("relationships", [])
                                if relationship.get("assertion_status", "asserted") == "asserted"
                            )
                            edges = build_candidate_connection_edges(
                                row_candidate, manifest, edge_builder=edge_builder,
                                source_record_ids=run_source_record_ids)
                            _resolve_edge_support_ids(db, edges)
                            counts = persist_connection_edges(db, edges)
                            edge_inserted += counts["inserted"]
                            edge_updated += counts["updated"]
                            edge_unchanged += counts.get("unchanged", 0)
                            edge_skipped_exact += counts["skipped_exact"]
            except Exception as error:
                if materialization_run_id is not None:
                    with db.transaction():
                        _fail_edge_materialization(db, materialization_run_id, error)
                raise
        canonical_binding_counts = None
        support_ref_rows_updated = 0

        def finalize_post_edge() -> dict[str, int]:
            nonlocal canonical_binding_counts, support_ref_rows_updated
            if private_target is not None:
                with db.transaction():
                    support_ref_rows_updated = _backfill_graph_edge_support_record_ids(
                        db, run_id, str(manifest["source_id"]), artifact_id)
            if private_target is not None and manifest["source_id"] == "it.853-2004":
                with db.transaction():
                    binding_summary = _italy_binding_summary(
                        db, run_id, str(manifest["source_id"]), artifact_id)
                    binding_inserted = _insert_italy_canonical_identifier_bindings(
                        db, run_id, str(manifest["source_id"]), artifact_id)
                canonical_binding_counts = {**binding_summary, **binding_inserted}
                canonical_binding_counts["support_ref_rows_updated"] = support_ref_rows_updated
            with db.transaction():
                persisted_edges = db.execute(
                    "SELECT connection_type,count(*) FROM uec.graph_connection_edges "
                    "WHERE from_source_id=%s OR to_source_id=%s GROUP BY connection_type",
                    (manifest["source_id"], manifest["source_id"]),
                ).fetchall()
            return {str(kind): int(count) for kind, count in persisted_edges}

        if materialization_run_id is not None:
            persisted_by_type = _finalize_edge_materialization(
                db, materialization_run_id,
                {"inserted": edge_inserted, "updated": edge_updated,
                 "unchanged": edge_unchanged,
                 "total": edge_inserted + edge_updated + edge_unchanged},
                matcher_summary, finalize_post_edge,
            )
        else:
            persisted_by_type = finalize_post_edge()
        return {"status": "already_present" if completed else "completed", "source_id": manifest["source_id"], "source_kind": "facility_master", "run_id": str(run_id), "item_count": item_count, "inserted_count": inserted, "already_present_count": already, "rejected_count": rejected, "source_assertion_rows": source_assertion_rows, "endpoint_mapping_diagnostics": endpoint_mapping_diagnostics, "canonical_binding_counts": canonical_binding_counts, "edge_inserted_count": edge_inserted, "edge_updated_count": edge_updated, "edge_unchanged_count": edge_unchanged, "edge_skipped_exact_count": edge_skipped_exact, "edge_count": edge_inserted + edge_updated + edge_unchanged, "persisted_edge_counts": persisted_by_type, "resume_offset": resume_offset, "public_rows": 0, "phase_timings_seconds": {"validation_and_staging": round(time.perf_counter() - started_at, 6), "approved_lineage_load": approved_lineage_seconds}, "peak_rss_bytes": _peak_rss_bytes()}


def _persist_evidence_event(connection: Any, manifest: dict[str, Any], row: dict[str, Any],
                            artifact_id: uuid.UUID, handoff_digest: str) -> tuple[uuid.UUID, str]:
    normalized = row["normalized"]
    key = row.get("source_record_key") or normalized.get("source_observation_key")
    record_id = _ensure_record(connection, manifest, artifact_id, key, row.get("source_values") or {}, handoff_digest)
    event_key = str(key)
    existing = connection.execute("SELECT evidence_event_id FROM uec.graph_evidence_events WHERE source_id=%s AND event_key=%s", (manifest["source_id"], event_key)).fetchone()
    if existing:
        return existing[0], "already_present"
    event_id = _stable_uuid("evidence-event", manifest["source_id"], event_key)
    connection.execute(
        """INSERT INTO uec.graph_evidence_events
           (evidence_event_id,source_id,source_record_id,source_record_key,event_key,event_type,event_date,event_period,event_payload,observed_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (event_id, manifest["source_id"], record_id, key, event_key, normalized.get("event_type") or normalized.get("evidence_type") or "unspecified",
         _date(normalized.get("event_date") or normalized.get("status_date")), normalized.get("event_period") or normalized.get("report_year"),
         json.dumps(normalized, ensure_ascii=False), normalized.get("event_date") or _timestamp(manifest)),
    )
    for link in normalized.get("linkage_candidates") or []:
        if not isinstance(link, dict) or not link.get("identifier_type") or not link.get("value"):
            continue
        target_source = link.get("target_source_id") or manifest["source_id"]
        connection.execute(
            """INSERT INTO uec.graph_evidence_links
               (evidence_event_id,target_source_id,target_identifier_type,target_source_identifier,match_method,confidence,assertion_status,evidence)
               VALUES (%s,%s,%s,%s,%s,%s,'candidate',%s)
               ON CONFLICT (evidence_event_id,target_source_id,target_identifier_type,target_source_identifier,match_method) DO NOTHING""",
            (event_id, target_source, link["identifier_type"], str(link["value"]), link.get("match_method") or "source-native-linkage-candidate", link.get("confidence"), json.dumps({"identity_scope": "source_scoped", "review_state": "review_required"})),
        )
    return event_id, "inserted"


def import_evidence_events(database_url: str, handoff_dir: str | Path, *,
                           disposable_db: bool = False, batch_size: int = DEFAULT_BATCH_SIZE,
                           private_target: tuple[str, str] | None = None,
                           on_batch_committed: BatchCommitObserver | None = None) -> dict[str, Any]:
    """Persist evidence events separately from facility graph candidates."""
    if private_target is None:
        require_disposable_graph_database(database_url, disposable_db)
    else:
        if disposable_db:
            raise GraphPersistenceError("refusing evidence import: choose either disposable_db or private_target")
        require_private_graph_target(database_url, expected_database=private_target[0], purpose=private_target[1])
    if batch_size <= 0:
        raise GraphPersistenceError("batch size must be positive")
    manifest, rows, digest = load_evidence_handoff(handoff_dir)
    with psycopg.connect(database_url) as db:
        if private_target is None:
            _verify_disposable_marker(db)
        else:
            _validate_private_graph_writer(db, private_target[0])
        db.commit()
        with db.transaction():
            _ensure_source_artifact(db, manifest, digest)
            run_id, completed = _begin_run(db, manifest, "evidence_event", EVIDENCE_HANDOFF_VERSION, digest, len(rows))
        if completed:
            return {"status": "already_present", "source_id": manifest["source_id"], "source_kind": "evidence_event", "run_id": str(run_id), "item_count": len(rows), "inserted_count": 0, "already_present_count": len(rows), "rejected_count": 0, "public_rows": 0, "facility_rows": 0}
        artifact_sha = str(manifest.get("checksum_sha256") or manifest.get("source_artifact_sha256") or digest)
        artifact_id = db.execute("SELECT artifact_id FROM uec.raw_artifacts WHERE sha256=%s", (artifact_sha if len(artifact_sha) == 64 else digest,)).fetchone()[0]
        inserted = already = 0
        try:
            for offset in range(0, len(rows), batch_size):
                batch_inserted = 0
                with db.transaction():
                    for row in rows[offset:offset + batch_size]:
                        key = row.get("source_record_key") or row["normalized"].get("source_observation_key")
                        item_digest = hashlib.sha256((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
                        existing = db.execute("SELECT 1 FROM uec.graph_ingest_items WHERE source_id=%s AND item_sha256=%s", (manifest["source_id"], item_digest)).fetchone()
                        if existing:
                            already += 1
                            continue
                        _, status = _persist_evidence_event(db, manifest, row, artifact_id, digest)
                        if status == "already_present":
                            already += 1
                            continue
                        db.execute("INSERT INTO uec.graph_ingest_items(ingest_run_id,source_id,source_record_key,item_sha256,item_kind,status) VALUES (%s,%s,%s,%s,'evidence_event','inserted')", (run_id, manifest["source_id"], key, item_digest))
                        inserted += 1
                        batch_inserted += 1
                if on_batch_committed:
                    on_batch_committed(offset // batch_size + 1, offset, batch_inserted)
        except Exception as error:
            with db.transaction():
                _mark_failed(db, run_id, error)
            raise
        with db.transaction():
            db.execute("UPDATE uec.graph_ingest_runs SET status='completed', inserted_count=%s, already_present_count=%s, completed_at=now() WHERE ingest_run_id=%s", (inserted, already, run_id))
        return {"status": "completed", "source_id": manifest["source_id"], "source_kind": "evidence_event", "run_id": str(run_id), "item_count": len(rows), "inserted_count": inserted, "already_present_count": already, "rejected_count": 0, "public_rows": 0, "facility_rows": 0}


__all__ = [
    "GraphPersistenceError", "load_graph_candidate_handoff", "inspect_graph_candidate_handoff", "iter_graph_candidate_handoff", "load_evidence_handoff",
    "import_graph_candidates", "import_evidence_events", "require_disposable_graph_database",
    "build_candidate_connection_edges", "ConnectionEdgeBuilder",
]
