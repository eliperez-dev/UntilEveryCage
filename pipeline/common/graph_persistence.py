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
    persist_connection_edges,
    score_connection,
    validate_connection_edge,
)


DISPOSABLE_MARKER = "uec-e2e-disposable-v1"
EVIDENCE_HANDOFF_VERSION = "us-aphis-observation-handoff-v1"
DEFAULT_BATCH_SIZE = 250
_FORBIDDEN_IDENTITY_KEYS = {
    "canonical_id", "global_id", "universal_id", "universal_identity",
    "global_identity", "master_id", "entity_id",
}
BatchCommitObserver = Callable[[int, int, int], None]
ConnectionEdgeBuilder = Callable[[dict[str, Any], dict[str, Any]], Iterable[dict[str, Any]]]

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
    root = Path(path)
    if root.is_file():
        root = root.parent
    if (root / "graph-candidates" / "manifest.json").is_file():
        parent_root = root
        candidate_root = root / "graph-candidates"
        _, parent_manifest = _manifest_for(parent_root)
        _, graph_manifest = _manifest_for(candidate_root)
        manifest = {**parent_manifest, **graph_manifest}
    elif (root / "manifest.json").is_file():
        candidate_root = root
        _, manifest = _manifest_for(root)
    else:
        raise GraphPersistenceError("graph candidate handoff root is not recognizable")
    _private_manifest(manifest)
    if manifest.get("contract_version") not in {None, "private-graph-candidate-set-v1", "private-graph-candidate-batch-v1", GRAPH_CONTRACT_VERSION}:
        raise GraphPersistenceError("unsupported graph candidate handoff contract")
    source_id = manifest.get("source_id")
    records_path = candidate_root / "records.jsonl"
    candidates: list[dict[str, Any]]
    if records_path.is_file():
        candidates = _read_jsonl(records_path)
    else:
        candidates = []
        for candidate_path in sorted(candidate_root.glob("*/graph-candidate.json")):
            try:
                candidates.append(json.loads(candidate_path.read_text(encoding="utf-8")))
            except json.JSONDecodeError as exc:
                raise GraphPersistenceError(f"malformed graph candidate: {candidate_path}") from exc
    canonical_payload = bytearray()
    for candidate in candidates:
        _reject_global_identity(candidate)
        try:
            validate_graph_candidate(candidate)
        except ValueError as exc:
            raise GraphPersistenceError(str(exc)) from exc
        if source_id and candidate.get("source_id") != source_id:
            raise GraphPersistenceError("candidate source_id does not match handoff manifest")
        source_id = source_id or candidate["source_id"]
        canonical_payload.extend(canonical_json_bytes(candidate))
    if not source_id:
        raise GraphPersistenceError("graph handoff requires source_id")
    if manifest.get("source_kind", "facility_master") == "evidence_event":
        raise GraphPersistenceError("evidence-event handoffs must use the evidence importer")
    digest = hashlib.sha256(bytes(canonical_payload)).hexdigest()
    expected = manifest.get("records_sha256") or manifest.get("sha256")
    if expected and expected != digest:
        raise GraphPersistenceError("graph candidate handoff checksum mismatch")
    return {**manifest, "source_id": source_id, "source_kind": "facility_master"}, candidates, digest


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
                   source_record_key: str, source_values: dict[str, Any], digest: str) -> uuid.UUID:
    source_id = manifest["source_id"]
    record_id = _stable_uuid("record", source_id, source_record_key, str(artifact_id))
    connection.execute(
        """INSERT INTO uec.source_records(source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at)
           VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (source_id,source_record_key,artifact_id) DO NOTHING""",
        (record_id, source_id, source_record_key, artifact_id,
         json.dumps({"source_values": source_values, "handoff_sha256": digest}, ensure_ascii=False), _timestamp(manifest)),
    )
    row = connection.execute(
        "SELECT source_record_id FROM uec.source_records WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s",
        (source_id, source_record_key, artifact_id),
    ).fetchone()
    if not row:
        raise GraphPersistenceError("source record was not materialized")
    return row[0]


def _entity_maps(connection: Any, manifest: dict[str, Any], candidate: dict[str, Any],
                 record_id: uuid.UUID, artifact_id: uuid.UUID) -> tuple[dict[str, uuid.UUID], dict[str, uuid.UUID]]:
    facilities: dict[str, uuid.UUID] = {}
    organizations: dict[str, uuid.UUID] = {}
    country = _country(manifest)
    source_id = manifest["source_id"]
    source_values = candidate.get("source_values") or {}
    for item in candidate.get("facilities", []):
        ref = item["local_ref"]
        identifier = item["source_identifier"]
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
    for item in candidate.get("organizations", []):
        ref = item["local_ref"]
        identifier = item["source_identifier"]
        organization_id = _stable_uuid("organization", source_id, identifier["identifier_type"], identifier["value"])
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
    return facilities, organizations


def _facility_id_for_identifier(connection: Any, identifier_id: uuid.UUID) -> uuid.UUID:
    return connection.execute("SELECT facility_id FROM uec.source_entity_identifiers WHERE identifier_id=%s", (identifier_id,)).fetchone()[0]


def _organization_id_for_identifier(connection: Any, identifier_id: uuid.UUID) -> uuid.UUID:
    return connection.execute("SELECT organization_id FROM uec.source_entity_identifiers WHERE identifier_id=%s", (identifier_id,)).fetchone()[0]


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


def _source_refs(candidate: dict[str, Any], manifest: dict[str, Any]) -> list[SourceRef]:
    source_id = str(candidate.get("source_id") or manifest["source_id"])
    key = candidate.get("source_record_key") or candidate.get("source_observation_key")
    if not isinstance(key, str) or not key.strip():
        raise GraphPersistenceError("connection candidate requires source_record_key")
    return [SourceRef(source_id=source_id, source_record_key=key)]


def _matcher_edge(raw: dict[str, Any], candidate: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any] | None:
    """Adapt the matcher lane's result to the shared score/build contract.

    The matcher is deliberately not implemented here.  It may hand us an
    already-built edge, or endpoint refs plus signal mappings.  This adapter
    keeps persistence independent of matcher implementation details while
    making every persisted edge pass the same validation gate.
    """
    if not isinstance(raw, dict):
        raise GraphPersistenceError("matcher edge must be an object")
    if {"edge_key", "from", "to", "connection_type"}.issubset(raw):
        edge = validate_connection_edge(raw)
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
        if _forbidden_evidence_facility_pair(left_ref, right_ref):
            return None
        signal_names = {
            "name": "organization_name_normalized",
            "postal": "postal_match",
            "city": "city_match",
            "address": "address_match",
        }
        signals = [
            {"name": signal_names[name], "details": {"basis": "indexed_normalized_block"}}
            for name in raw.get("contributing_features", ())
            if name in signal_names
        ]
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
            for item in provenance:
                if isinstance(item, dict) and item.get("source_id") and item.get("source_record_key"):
                    refs.append(SourceRef(source_id=str(item["source_id"]), source_record_key=str(item["source_record_key"])))
        if not refs:
            refs = _source_refs(candidate, manifest)
        return build_connection_edge(
            from_ref=left_ref,
            to_ref=right_ref,
            relationship_type=str(raw.get("relationship_type") or "related_facility"),
            scoring=scoring,
            supporting_source_refs=refs,
            observed_at=raw.get("observed_at") or candidate.get("observed_at") or _timestamp(manifest),
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
    if _forbidden_evidence_facility_pair(left_ref, right_ref):
        return None
    signals = raw.get("signals") or raw.get("signal_bundle") or raw.get("match_signals")
    if not isinstance(signals, list):
        raise GraphPersistenceError("matcher edge requires a signal list")
    scoring = score_connection(signals)
    if not scoring.eligible:
        return None
    observed_at = raw.get("observed_at") or candidate.get("observed_at") or _timestamp(manifest)
    return build_connection_edge(
        from_ref=left_ref,
        to_ref=right_ref,
        relationship_type=str(raw.get("relationship_type") or "related_to"),
        scoring=scoring,
        supporting_source_refs=_source_refs(candidate, manifest),
        observed_at=observed_at,
        conflicting=bool(raw.get("conflicting") or raw.get("contradictory_evidence")),
        suppressed=bool(raw.get("suppressed")),
        # A retrieval timestamp makes a rerun byte/digest stable while still
        # preserving a distinct observed timestamp from the source row.
        computed_at=str(raw.get("computed_at") or manifest.get("retrieved_at_utc") or _timestamp(manifest)),
    )


def build_candidate_connection_edges(candidate: dict[str, Any], manifest: dict[str, Any], *,
                                     edge_builder: ConnectionEdgeBuilder | None = None) -> list[dict[str, Any]]:
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
            supporting_source_refs=_source_refs(candidate, manifest),
            observed_at=relationship.get("observed_at") or candidate.get("observed_at") or _timestamp(manifest),
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
        edge = _matcher_edge(raw, candidate, manifest)
        if edge is not None:
            built.append(edge)
    # A matcher may repeat an explicit edge while enriching its explanation;
    # the deterministic edge key is the single source of truth for persistence.
    return list({edge["edge_key"]: edge for edge in built}.values())


def _persist_candidate(connection: Any, manifest: dict[str, Any], candidate: dict[str, Any],
                       artifact_id: uuid.UUID, handoff_digest: str,
                       *, edge_builder: ConnectionEdgeBuilder | None = None) -> dict[str, int]:
    source_record_key = candidate["source_record_key"]
    record_id = _ensure_record(connection, manifest, artifact_id, source_record_key,
                               candidate.get("source_values") or {}, handoff_digest)
    facilities, organizations = _entity_maps(connection, manifest, candidate, record_id, artifact_id)
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
    connection_edges = build_candidate_connection_edges(candidate, manifest, edge_builder=edge_builder)
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
                            edge_builder: ConnectionEdgeBuilder | None = None) -> dict[str, Any]:
    """Persist facility candidates in resumable private batches."""
    require_disposable_graph_database(database_url, disposable_db)
    if batch_size <= 0:
        raise GraphPersistenceError("batch size must be positive")
    manifest, candidates, digest = load_graph_candidate_handoff(handoff_dir)
    with psycopg.connect(database_url) as db:
        _verify_disposable_marker(db)
        db.commit()
        with db.transaction():
            _ensure_source_artifact(db, manifest, digest)
            run_id, completed = _begin_run(db, manifest, "facility_master", GRAPH_CONTRACT_VERSION, digest, len(candidates))
        if completed:
            return {"status": "already_present", "source_id": manifest["source_id"], "source_kind": "facility_master", "run_id": str(run_id), "item_count": len(candidates), "inserted_count": 0, "already_present_count": len(candidates), "rejected_count": 0, "edge_inserted_count": 0, "edge_updated_count": 0, "edge_count": 0, "public_rows": 0}
        artifact_sha = str(manifest.get("checksum_sha256") or manifest.get("source_artifact_sha256") or digest)
        artifact_id = db.execute("SELECT artifact_id FROM uec.raw_artifacts WHERE sha256=%s", (artifact_sha if len(artifact_sha) == 64 else digest,)).fetchone()[0]
        inserted = already = rejected = 0
        edge_inserted = edge_updated = 0
        try:
            for offset in range(0, len(candidates), batch_size):
                batch_inserted = 0
                with db.transaction():
                    for candidate in candidates[offset:offset + batch_size]:
                        item_digest = hashlib.sha256(canonical_json_bytes(candidate)).hexdigest()
                        existing = db.execute("SELECT 1 FROM uec.graph_ingest_items WHERE source_id=%s AND item_sha256=%s", (manifest["source_id"], item_digest)).fetchone()
                        if existing:
                            already += 1
                            continue
                        edge_counts = _persist_candidate(db, manifest, candidate, artifact_id, digest, edge_builder=edge_builder)
                        edge_inserted += edge_counts["inserted"]
                        edge_updated += edge_counts["updated"]
                        db.execute("INSERT INTO uec.graph_ingest_items(ingest_run_id,source_id,source_record_key,item_sha256,item_kind,status) VALUES (%s,%s,%s,%s,'facility_candidate','inserted')", (run_id, manifest["source_id"], candidate["source_record_key"], item_digest))
                        inserted += 1
                        batch_inserted += 1
                if on_batch_committed:
                    on_batch_committed(offset // batch_size + 1, offset, batch_inserted)
        except Exception as error:
            with db.transaction():
                _mark_failed(db, run_id, error)
            raise
        with db.transaction():
            db.execute("UPDATE uec.graph_ingest_runs SET status='completed', inserted_count=%s, already_present_count=%s, rejected_count=%s, completed_at=now() WHERE ingest_run_id=%s", (inserted, already, rejected, run_id))
        return {"status": "completed", "source_id": manifest["source_id"], "source_kind": "facility_master", "run_id": str(run_id), "item_count": len(candidates), "inserted_count": inserted, "already_present_count": already, "rejected_count": rejected, "edge_inserted_count": edge_inserted, "edge_updated_count": edge_updated, "edge_count": edge_inserted + edge_updated, "public_rows": 0}


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
                           on_batch_committed: BatchCommitObserver | None = None) -> dict[str, Any]:
    """Persist evidence events separately from facility graph candidates."""
    require_disposable_graph_database(database_url, disposable_db)
    if batch_size <= 0:
        raise GraphPersistenceError("batch size must be positive")
    manifest, rows, digest = load_evidence_handoff(handoff_dir)
    with psycopg.connect(database_url) as db:
        _verify_disposable_marker(db)
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
    "GraphPersistenceError", "load_graph_candidate_handoff", "load_evidence_handoff",
    "import_graph_candidates", "import_evidence_events", "require_disposable_graph_database",
    "build_candidate_connection_edges", "ConnectionEdgeBuilder",
]
