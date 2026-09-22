"""Row-free analysis of real private graph handoffs.

The D5 connection lane consumes either checked-in aggregate manifests or a
path to restricted JSONL handoffs.  It never writes source rows to an output
report.  A handoff is inspected in memory and only counts, digests, and
source-scoped review tokens leave the private boundary.

This is an analysis tool, not a matcher of record: exact identifiers may
produce deterministic *review* edges, while multi-signal matches produce
probabilistic candidates.  Neither kind can merge identities, transfer
claims, or authorize publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping


REPORT_VERSION = "d5-real-graph-analysis-v1"
RULESET_VERSION = "d5-multi-signal-candidates-v1"
EVIDENCE_SOURCE_IDS = frozenset({"us.aphis", "us.inspections"})
FACILITY_ID_KEYS = frozenset({
    "establishment_id", "establishment_number", "approval_number",
    "plant_number", "plant_id", "facility_id", "recognition_number",
    "eu_recognition_number", "findsmiley_id", "source_establishment_id",
    "num_identificativo_produzione_commercializzazione",
})
ORG_ID_KEYS = frozenset({
    "cvr", "cvr_number", "vat", "vat_number", "italian_vat",
    "fiscal_code", "italian_fiscal_code", "cod_fiscale", "p_iva",
    "operator_id", "operator_number", "customer_number", "abn", "acn",
})
NAME_KEYS = frozenset({
    "name", "trading_name", "operator_name", "account_name", "legal_name", "site_name",
    "establishment_name", "ragione_sociale", "raison_sociale_enseigne_commerciale_name",
})
CITY_KEYS = frozenset({"city", "town", "municipality", "locality", "comune"})
POSTAL_KEYS = frozenset({"postal_code", "postcode", "zip", "postal", "postnummer", "code_postal_postal_code"})
ADDRESS_KEYS = frozenset({"address", "street", "address_line_1", "address1", "address_lines", "indirizzo"})
DATE_KEYS = frozenset({"observed_at", "effective_date", "observation_date", "event_date", "status_date", "valid_from", "valid_to"})


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _norm(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    return re.sub(r"[^a-z0-9]+", "", text.casefold()) or None


def _token(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.casefold(), flags=re.UNICODE)).strip() or None


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _row_free(value: Any, path: str = "report") -> None:
    """Reject accidental payload leakage from aggregate outputs."""
    forbidden = {
        "source_values", "raw_fields", "address", "street", "address_line_1",
        "address_lines", "coordinates", "latitude", "longitude", "phone",
        "email", "account_name", "legal_name", "trading_name", "operator_name",
    }
    if isinstance(value, dict):
        leaked = forbidden.intersection(value)
        if leaked:
            raise ValueError(f"row-free output contains restricted fields at {path}: {sorted(leaked)}")
        for key, child in value.items():
            _row_free(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _row_free(child, f"{path}[{index}]")


def _manifest_sources(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract source summaries from the known D5 aggregate manifest shapes."""
    sources = value.get("sources")
    if isinstance(sources, list):
        return [dict(item) for item in sources if isinstance(item, dict) and item.get("source_id")]
    if value.get("source_id"):
        return [dict(value)]
    return []


def read_aggregate_manifests(paths: Iterable[str | Path]) -> dict[str, dict[str, Any]]:
    """Load row-free manifests and keep the newest entry for each source."""
    selected: dict[str, dict[str, Any]] = {}
    for raw_path in paths:
        path = Path(raw_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"aggregate manifest must be an object: {path}")
        manifest_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        for source in _manifest_sources(payload):
            source = dict(source)
            source["manifest_digest"] = manifest_digest
            source["manifest_path_recorded_private"] = str(path)
            source_id = str(source["source_id"])
            previous = selected.get(source_id)
            stamp = str(source.get("retrieved_at_utc") or source.get("as_of_utc") or "")
            if previous is None or stamp >= str(previous.get("retrieved_at_utc") or previous.get("as_of_utc") or ""):
                selected[source_id] = source
    return dict(sorted(selected.items()))


@dataclass
class _Observed:
    source_id: str
    source_kind: str
    key: str
    facility_ids: dict[str, str]
    organization_ids: dict[str, str]
    signals: dict[str, str]
    dates: list[str]
    explicit_relationships: int = 0
    typed_entity_edge: bool = False
    provenance_complete: bool = False
    quarantined: bool = False
    suppressed: bool = False


def _source_kind(source_id: str, row: Mapping[str, Any]) -> str:
    value = _clean(row.get("source_kind"))
    if value in {"facility_master", "evidence_event"}:
        return value
    return "evidence_event" if source_id in EVIDENCE_SOURCE_IDS else "facility_master"


def _nested_values(row: Mapping[str, Any]) -> Iterable[tuple[str, Any]]:
    for container_name in ("normalized", "source_fields", "source_native_ids", "source_values"):
        container = row.get(container_name)
        if isinstance(container, Mapping):
            for key, value in container.items():
                yield str(key).casefold(), value
    # A graph-candidate itself can carry identifiers in typed entities.  Keep
    # the declared identifier type as the key; yielding the literal wrapper
    # key (``identifier_type``) loses the source-native semantics needed by
    # the real-corpus audit.
    for entity_key in ("facilities", "organizations"):
        entities = row.get(entity_key)
        if isinstance(entities, list):
            for entity in entities:
                if not isinstance(entity, Mapping):
                    continue
                identifier = entity.get("source_identifier")
                if isinstance(identifier, Mapping):
                    identifier_type = identifier.get("identifier_type")
                    if identifier_type:
                        yield str(identifier_type).casefold(), identifier.get("value")


def _observed_from_row(row: Mapping[str, Any], fallback_source: str | None = None) -> _Observed:
    source_id = _clean(row.get("source_id")) or fallback_source
    if not source_id:
        raise ValueError("row requires source_id or an explicit source mapping")
    kind = _source_kind(source_id, row)
    values = list(_nested_values(row))
    facility_ids: dict[str, str] = {}
    organization_ids: dict[str, str] = {}
    signals: dict[str, str] = {}
    dates: list[str] = []
    for raw_key, value in values:
        key = re.sub(r"[^a-z0-9]+", "_", raw_key).strip("_")
        normalized_value = _norm(value)
        if key in FACILITY_ID_KEYS and normalized_value and kind == "facility_master":
            facility_ids.setdefault(key, normalized_value)
        if key in ORG_ID_KEYS and normalized_value:
            organization_ids.setdefault(key, normalized_value)
        if key in NAME_KEYS and (token := _token(value)):
            signals.setdefault("name", token)
        if key in CITY_KEYS and (token := _token(value)):
            signals.setdefault("city", token)
        if key in POSTAL_KEYS and (token := _norm(value)):
            signals.setdefault("postal", token)
        if key in ADDRESS_KEYS and (token := _token(value)):
            signals.setdefault("address", token)
        if key in DATE_KEYS and (date := _clean(value)):
            dates.append(date[:32])
    # Graph handoffs already type their source-native identifiers.  Preserve
    # every typed facility/organization identifier, including adapter-specific
    # types such as ``permit`` that are intentionally not in the generic key
    # allow-list above.
    for entity_key, target in (("facilities", facility_ids), ("organizations", organization_ids)):
        entities = row.get(entity_key)
        if not isinstance(entities, list):
            continue
        for entity in entities:
            if not isinstance(entity, Mapping) or not isinstance(entity.get("source_identifier"), Mapping):
                continue
            identifier = entity["source_identifier"]
            identifier_type = _norm(identifier.get("identifier_type"))
            identifier_value = _norm(identifier.get("value") or identifier.get("source_identifier"))
            if identifier_type and identifier_value:
                target.setdefault(identifier_type, identifier_value)
    key = _clean(row.get("source_record_key")) or _clean(row.get("source_row_id")) or _clean(row.get("source_observation_key")) or "row-unknown"
    relationships = row.get("relationships")
    explicit_relationships = len(relationships) if isinstance(relationships, list) else 0
    typed_entity_edge = bool(row.get("facilities")) and bool(row.get("organizations"))
    source_values = row.get("source_values")
    provenance_complete = bool(
        _clean(row.get("source_record_key") or row.get("source_row_id"))
        and isinstance(source_values, Mapping)
        and (_clean(row.get("source_artifact_sha256")) or _clean(row.get("artifact_sha256")))
    )
    suppressed = bool(row.get("suppressed") or row.get("public_access_revoked"))
    return _Observed(source_id, kind, key, facility_ids, organization_ids, signals, dates,
                     explicit_relationships, typed_entity_edge, provenance_complete,
                     bool(row.get("quarantine_reason")), suppressed)


def classify_collision_observations(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Classify source identity anomalies without calling fan-out a collision.

    A repeated source observation is not a collision, and one organization
    appearing across many facilities is an expected fan-out.  Only one
    source-scoped facility identifier resolving to multiple organization
    identifiers is counted as a true conflict/collision.  The function accepts
    compact ``_Observed``-shaped mappings as well as raw adapter-shaped rows;
    no input values are returned.
    """
    repeated: dict[tuple[str, str, tuple[str, ...], tuple[str, ...]], int] = defaultdict(int)
    facility_to_orgs: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    org_to_facilities: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    repeated_rows = malformed = missing = 0
    for raw in rows:
        source_id = _clean(raw.get("source_id")) or "unknown-source"
        if isinstance(raw.get("facility_ids"), Mapping):
            facility_ids = {str(key): _clean(value) for key, value in raw["facility_ids"].items()}
            organization_ids = {str(key): _clean(value) for key, value in (raw.get("organization_ids") or {}).items()}
        else:
            values = list(_nested_values(raw))
            facility_ids = {}
            organization_ids = {}
            for key, value in values:
                normalized_key = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
                normalized_value = _norm(value)
                if normalized_key in FACILITY_ID_KEYS:
                    if _clean(value) and not normalized_value:
                        malformed += 1
                    elif normalized_value:
                        facility_ids.setdefault(normalized_key, normalized_value)
                if normalized_key in ORG_ID_KEYS:
                    if _clean(value) and not normalized_value:
                        malformed += 1
                    elif normalized_value:
                        organization_ids.setdefault(normalized_key, normalized_value)
        facility_values = tuple(sorted(value for value in facility_ids.values() if value))
        organization_values = tuple(sorted(value for value in organization_ids.values() if value))
        if not facility_values and not organization_values:
            missing += 1
        key = _clean(raw.get("source_record_key")) or _clean(raw.get("source_row_id")) or "row-unknown"
        # For identified rows, a different source-row key does not make the
        # same source-native identity a new facility. Missing rows retain the
        # row key so unrelated empty observations are not collapsed together.
        signature = ((source_id, facility_values, organization_values)
                     if facility_values or organization_values
                     else (source_id, key, facility_values, organization_values))
        repeated[signature] += 1
        for facility_type, facility in facility_ids.items():
            if not facility:
                continue
            for organization_type, organization in organization_ids.items():
                if organization:
                    facility_to_orgs[(source_id, facility_type, facility)].add(organization)
                    org_to_facilities[(source_id, organization_type, organization)].add(facility)
    repeated_rows = sum(max(0, count - 1) for count in repeated.values())
    true_conflicts = sum(max(0, len(values) - 1) for values in facility_to_orgs.values())
    expected_fanout = sum(len(values) > 1 for values in org_to_facilities.values())
    return {
        "repeated_observations": repeated_rows,
        "expected_org_many_facility_fanout": expected_fanout,
        "true_conflicts": true_conflicts,
        "collision_count": true_conflicts,
        "malformed": malformed,
        "missing": missing,
    }


def load_private_rows(mapping: Mapping[str, str | Path]) -> list[_Observed]:
    """Read restricted JSONL handoffs; only compact observations are retained."""
    observations: list[_Observed] = []
    for source_id, raw_path in sorted(mapping.items()):
        path = Path(raw_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"JSONL row is not an object: {path}:{line_number}")
                observations.append(_observed_from_row(row, source_id))
    return observations


def _source_metric(source_id: str, manifest: Mapping[str, Any] | None, rows: list[_Observed]) -> dict[str, Any]:
    manifest = manifest or {}
    input_rows = manifest.get("input_rows")
    normalized_rows = manifest.get("normalized_rows")
    quarantined_rows = manifest.get("quarantined_rows")
    if not isinstance(input_rows, int):
        input_rows = len(rows)
    if not isinstance(normalized_rows, int):
        normalized_rows = sum(not row.quarantined for row in rows) if rows else None
    if not isinstance(quarantined_rows, int):
        quarantined_rows = sum(row.quarantined for row in rows) if rows else None
    return {
        "input_rows": input_rows,
        "normalized_rows": normalized_rows,
        "quarantined_rows": quarantined_rows,
        "private_rows_supplied": len(rows),
        "facility_nodes_observed": sum(bool(row.facility_ids) for row in rows),
        "organization_ids_observed": sum(bool(row.organization_ids) for row in rows),
        "evidence_rows": sum(row.source_kind == "evidence_event" for row in rows),
        "source_kind": "evidence_event" if source_id in EVIDENCE_SOURCE_IDS else "facility_master",
        "publication_blocked": True,
    }


def _candidate_key(left: _Observed, right: _Observed, method: str) -> str:
    return _digest("|".join((left.source_id, left.key, right.source_id, right.key, method)))


_BLOCK_SIGNALS = ("postal", "city", "address")
_SIGNAL_WEIGHTS = {"name": 0.34, "postal": 0.18, "city": 0.10, "address": 0.22}
_BLOCK_DEFAULT_MAX = 1000


def _endpoint_ref(row: _Observed) -> dict[str, str] | None:
    """Return a source-qualified facility endpoint, never a synthetic placeholder."""
    if not row.facility_ids:
        return None
    identifier_type, identifier = sorted(row.facility_ids.items())[0]
    return {
        "entity_type": "facility",
        "source_id": row.source_id,
        "identifier_type": identifier_type,
        "source_identifier": identifier,
        "source_record_key": row.key,
        "identity_scope": "source_scoped",
    }


def _pair_identity(left: _Observed, right: _Observed) -> tuple[str, str]:
    """Stable pair key independent of input order."""
    values = (f"{left.source_id}:{left.key}", f"{right.source_id}:{right.key}")
    return tuple(sorted(values))  # type: ignore[return-value]


def _exact_equivalent(left: _Observed, right: _Observed) -> bool:
    """Rows repeating one source-native facility are not inferred matches."""
    if left.source_id != right.source_id:
        return False
    if left.key == right.key:
        return True
    left_ids = set(left.facility_ids.values())
    right_ids = set(right.facility_ids.values())
    return bool(left_ids and right_ids and left_ids.intersection(right_ids))


def _match_features(left: _Observed, right: _Observed) -> tuple[list[str], list[dict[str, Any]]]:
    common = [signal for signal in ("name", "postal", "city", "address")
              if left.signals.get(signal) and left.signals.get(signal) == right.signals.get(signal)]
    contradictions: list[dict[str, Any]] = []
    if left.organization_ids and right.organization_ids and not set(left.organization_ids.values()).intersection(right.organization_ids.values()):
        contradictions.append({"signal": "conflicting_identifier", "group": "contradiction", "reason": "organization identifiers disagree"})
    if left.signals.get("address") and right.signals.get("address") and left.signals["address"] != right.signals["address"]:
        contradictions.append({"signal": "conflicting_address", "group": "contradiction", "reason": "normalized addresses disagree"})
    if left.dates and right.dates and not set(left.dates).intersection(right.dates):
        # Dates are observations, not identity.  Keep the contradiction as a
        # review cue while allowing an otherwise anchored candidate through.
        contradictions.append({"signal": "temporal_conflict", "group": "contradiction", "reason": "observation dates do not overlap"})
    return common, contradictions


def _score_match(features: list[str], contradictions: list[dict[str, Any]]) -> tuple[float, str, dict[str, Any]]:
    groups = {"identity": [feature for feature in features if feature == "name"],
              "location": [feature for feature in features if feature in {"postal", "city", "address"}]}
    group_contributions: dict[str, float] = {}
    for group, values in sorted(groups.items()):
        ordered = sorted(values, key=lambda value: (-_SIGNAL_WEIGHTS[value], value))
        group_contributions[group] = sum(_SIGNAL_WEIGHTS[value] * (0.68 ** index) for index, value in enumerate(ordered))
    positive = sum(group_contributions.values())
    contradiction_weights = {"conflicting_identifier": 0.24, "conflicting_address": 0.14, "temporal_conflict": 0.16}
    penalty_values = sorted((contradiction_weights.get(item.get("signal", ""), 0.14) for item in contradictions), reverse=True)
    penalty = sum(value * (0.76 ** index) for index, value in enumerate(penalty_values))
    score = round(max(0.0, min(1.0, positive - penalty)), 5)
    if score >= 0.85:
        band = "high"
    elif score >= 0.65:
        band = "probable"
    elif score >= 0.40:
        band = "possible"
    else:
        band = "low"
    return score, band, {"group_contributions": {key: round(value, 8) for key, value in sorted(group_contributions.items())},
                         "positive_contribution": round(positive, 8), "contradiction_penalty": round(penalty, 8),
                         "anchor_present": "name" in features and ("postal" in features or ("city" in features and "address" in features))}


def _observed_json(row: _Observed) -> str:
    return json.dumps({
        "source_id": row.source_id, "source_kind": row.source_kind, "key": row.key,
        "facility_ids": row.facility_ids, "organization_ids": row.organization_ids,
        "signals": row.signals, "dates": row.dates,
        "explicit_relationships": row.explicit_relationships,
        "typed_entity_edge": row.typed_entity_edge,
        "provenance_complete": row.provenance_complete,
        "quarantined": row.quarantined, "suppressed": row.suppressed,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _observed_from_json(value: str) -> _Observed:
    payload = json.loads(value)
    return _Observed(
        str(payload["source_id"]), str(payload["source_kind"]), str(payload["key"]),
        {str(key): str(item) for key, item in (payload.get("facility_ids") or {}).items()},
        {str(key): str(item) for key, item in (payload.get("organization_ids") or {}).items()},
        {str(key): str(item) for key, item in (payload.get("signals") or {}).items()},
        [str(item) for item in payload.get("dates") or []],
        int(payload.get("explicit_relationships") or 0), bool(payload.get("typed_entity_edge")),
        bool(payload.get("provenance_complete")), bool(payload.get("quarantined")), bool(payload.get("suppressed")),
    )


def _iter_probabilistic_candidates(rows: Iterable[_Observed], *, start_after: str | None = None,
                                   max_block_size: int = _BLOCK_DEFAULT_MAX) -> tuple[Iterable[dict[str, Any]], dict[str, int]]:
    """Build deterministic indexed blocks in a disk-backed SQLite stage.

    Blocks are keyed by name+postal, name+city, or name+address.  A large
    block is ambiguous rather than truncated and is accounted for explicitly.
    The stage keeps one bounded block in memory and stores observations and
    candidate pairs on disk, so neither all rows nor all candidates are
    materialized in the process. ``start_after`` is a digest cursor.
    """
    if max_block_size < 2:
        raise ValueError("max_block_size must be at least 2")
    counters = {"rows_staged": 0, "blocks_indexed": 0, "blocks_ambiguous": 0,
                "rows_in_ambiguous_blocks": 0, "pairs_considered": 0,
                "pairs_exact_equivalent": 0, "pairs_emitted": 0,
                "pairs_deduplicated": 0, "pair_rows_staged": 0}

    def generate() -> Iterable[dict[str, Any]]:
        stage_parent = Path.cwd() / ".tmp"
        try:
            stage_parent.mkdir(parents=True, exist_ok=True)
            stage_parent_arg = str(stage_parent)
        except OSError:
            stage_parent_arg = None
        stage_fd, stage_name = tempfile.mkstemp(prefix="uec-d6-match-", suffix=".sqlite3", dir=stage_parent_arg)
        os.close(stage_fd)
        stage_path = Path(stage_name)
        db = sqlite3.connect(stage_path)
        try:
                db.execute("PRAGMA journal_mode=DELETE")
                db.execute("PRAGMA synchronous=OFF")
                db.executescript("""
                    CREATE TABLE observed (row_id INTEGER PRIMARY KEY, source_id TEXT NOT NULL,
                        source_record_key TEXT NOT NULL, payload TEXT NOT NULL);
                    CREATE TABLE blocks (signal TEXT NOT NULL, block_value TEXT NOT NULL, row_id INTEGER NOT NULL);
                    CREATE INDEX blocks_order ON blocks(signal, block_value, row_id);
                    CREATE TABLE pairs (pair_key TEXT PRIMARY KEY, left_row_id INTEGER NOT NULL,
                        right_row_id INTEGER NOT NULL, methods TEXT NOT NULL, candidate_digest TEXT NOT NULL);
                    CREATE TABLE excluded (pair_key TEXT PRIMARY KEY);
                """)
                for row in rows:
                    if row.source_kind != "facility_master" or not row.signals.get("name") or not row.facility_ids:
                        continue
                    cursor = db.execute("INSERT INTO observed(source_id,source_record_key,payload) VALUES (?,?,?)",
                                        (row.source_id, row.key, _observed_json(row)))
                    row_id = int(cursor.lastrowid)
                    counters["rows_staged"] += 1
                    name = row.signals["name"]
                    for signal in _BLOCK_SIGNALS:
                        value = row.signals.get(signal)
                        if value:
                            db.execute("INSERT INTO blocks(signal,block_value,row_id) VALUES (?,?,?)",
                                       (signal, name + "|" + value, row_id))
                db.commit()
                counters["blocks_indexed"] = int(db.execute("SELECT count(*) FROM (SELECT 1 FROM blocks GROUP BY signal, block_value)").fetchone()[0])
                block_rows = db.execute("SELECT signal, block_value FROM blocks GROUP BY signal, block_value ORDER BY signal, block_value")
                for signal, block_value in block_rows:
                    size = int(db.execute("SELECT count(*) FROM blocks WHERE signal=? AND block_value=?", (signal, block_value)).fetchone()[0])
                    if size > max_block_size:
                        counters["blocks_ambiguous"] += 1
                        counters["rows_in_ambiguous_blocks"] += size
                        continue
                    staged_group = list(db.execute(
                        "SELECT observed.row_id, observed.payload FROM blocks JOIN observed ON observed.row_id=blocks.row_id "
                        "WHERE blocks.signal=? AND blocks.block_value=? ORDER BY observed.source_id, observed.source_record_key, observed.row_id",
                        (signal, block_value),
                    ))
                    group = [
                        _observed_from_json(payload)
                        for _, payload in staged_group
                    ]
                    row_ids = {
                        (row.source_id, row.key): int(row_id)
                        for (row_id, _), row in zip(staged_group, group)
                    }
                    for left, right in combinations(group, 2):
                        counters["pairs_considered"] += 1
                        pair_key = _pair_identity(left, right)
                        if _exact_equivalent(left, right):
                            if db.execute("INSERT OR IGNORE INTO excluded(pair_key) VALUES (?)", ("|".join(pair_key),)).rowcount:
                                counters["pairs_exact_equivalent"] += 1
                            db.execute("DELETE FROM pairs WHERE pair_key=?", ("|".join(pair_key),))
                            continue
                        features, _ = _match_features(left, right)
                        if "name" not in features or not ("postal" in features or "city" in features or "address" in features):
                            continue
                        key = "|".join(pair_key)
                        if db.execute("SELECT 1 FROM excluded WHERE pair_key=?", (key,)).fetchone():
                            continue
                        existing = db.execute("SELECT methods FROM pairs WHERE pair_key=?", (key,)).fetchone()
                        method = f"normalized_name+{signal}"
                        if existing:
                            methods = set(json.loads(existing[0]))
                            if method not in methods:
                                methods.add(method)
                                db.execute("UPDATE pairs SET methods=? WHERE pair_key=?", (json.dumps(sorted(methods)), key))
                            counters["pairs_deduplicated"] += 1
                        else:
                            digest = _digest(pair_key[0] + "|" + pair_key[1] + "|" + RULESET_VERSION)
                            left_id = row_ids[(left.source_id, left.key)]
                            right_id = row_ids[(right.source_id, right.key)]
                            db.execute("INSERT INTO pairs(pair_key,left_row_id,right_row_id,methods,candidate_digest) VALUES (?,?,?,?,?)",
                                       (key, left_id, right_id, json.dumps([method]), digest))
                            counters["pair_rows_staged"] += 1
                db.commit()
                final_rows = db.execute(
                    "SELECT pairs.pair_key,pairs.methods,pairs.candidate_digest,left.payload,right.payload "
                    "FROM pairs JOIN observed AS left ON left.row_id=pairs.left_row_id "
                    "JOIN observed AS right ON right.row_id=pairs.right_row_id "
                    "WHERE pairs.pair_key NOT IN (SELECT pair_key FROM excluded) ORDER BY pairs.candidate_digest"
                )
                for pair_key, raw_methods, digest, left_payload, right_payload in final_rows:
                    left = _observed_from_json(left_payload)
                    right = _observed_from_json(right_payload)
                    methods = set(json.loads(raw_methods))
                    features, contradictions = _match_features(left, right)
                    score, band, explanation = _score_match(features, contradictions)
                    if not explanation["anchor_present"]:
                        continue
                    left_endpoint = _endpoint_ref(left)
                    right_endpoint = _endpoint_ref(right)
                    if left_endpoint is None or right_endpoint is None:
                        continue
                    if start_after and digest <= start_after:
                        continue
                    counters["pairs_emitted"] += 1
                    yield {
                        "candidate_digest": digest,
                        "source_pair": sorted({left.source_id, right.source_id}),
                        "endpoints": [left_endpoint, right_endpoint],
                        "left_endpoint": left_endpoint,
                        "right_endpoint": right_endpoint,
                        "provenance": [{"source_id": left.source_id, "source_record_key": left.key},
                                        {"source_id": right.source_id, "source_record_key": right.key}],
                        "observed_at": min(left.dates + right.dates) if left.dates or right.dates else "",
                        "method": "multi_signal_intersection",
                        "contributing_features": sorted(features),
                        "blocking_methods": sorted(methods),
                        "contradictory_evidence": contradictions,
                        "confidence": score,
                        "confidence_band": band,
                        "score_explanation": explanation,
                        "review_state": "review_required",
                        "automatic_merge": False,
                        "transfers_claims": False,
                        "disclaimer": "Possible source-record connection; not human verified and must not be treated as a canonical identity.",
                        "ruleset": RULESET_VERSION,
                    }
        finally:
            db.close()
            for suffix in ("", "-journal", "-wal", "-shm"):
                try:
                    stage_path.with_name(stage_path.name + suffix).unlink()
                except OSError:
                    pass
    return generate(), counters


def iter_probabilistic_candidates(rows: Iterable[_Observed], *, start_after: str | None = None,
                                  max_block_size: int = _BLOCK_DEFAULT_MAX) -> Iterable[dict[str, Any]]:
    """Yield all inferred candidates in deterministic digest order.

    This is the resumable matcher API.  It has no global result cap; callers
    can stop after a page and pass the last ``candidate_digest`` as a cursor.
    """
    iterator, _ = _iter_probabilistic_candidates(rows, start_after=start_after, max_block_size=max_block_size)
    yield from iterator


def iter_candidate_batches(rows: Iterable[_Observed], *, batch_size: int = 500,
                           start_after: str | None = None, max_block_size: int = _BLOCK_DEFAULT_MAX) -> Iterable[list[dict[str, Any]]]:
    """Yield deterministic candidate pages without imposing a total cap."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    batch: list[dict[str, Any]] = []
    for candidate in iter_probabilistic_candidates(rows, start_after=start_after, max_block_size=max_block_size):
        batch.append(candidate)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _probabilistic_candidates(rows: list[_Observed], limit: int | None = None) -> tuple[list[dict[str, Any]], bool]:
    """Compatibility wrapper; ``limit`` is an explicit caller page, never a global cap."""
    candidates = list(iter_probabilistic_candidates(rows))
    if limit is not None:
        candidates = candidates[:limit]
    return candidates, False


def analyze(*, manifests: Mapping[str, Mapping[str, Any]], rows: Iterable[_Observed] = (), sample_size: int = 50,
            max_block_size: int = _BLOCK_DEFAULT_MAX) -> dict[str, Any]:
    observations = list(rows)
    by_source: dict[str, list[_Observed]] = defaultdict(list)
    for row in observations:
        by_source[row.source_id].append(row)

    deterministic = Counter()
    identifiers = Counter()
    source_identifier_values: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    facility_org_targets: dict[tuple[str, str], set[str]] = defaultdict(set)
    temporal_inconsistencies = 0
    provenance_missing = 0
    suppressed = 0
    quarantined = 0
    for row in observations:
        source = row.source_id
        for kind, values in (("facility", row.facility_ids), ("organization", row.organization_ids)):
            for identifier_type, value in values.items():
                identifiers[kind] += 1
                source_identifier_values[(source, kind, identifier_type)].add(value)
        if row.facility_ids and row.organization_ids and row.typed_entity_edge:
            for facility in row.facility_ids.values():
                for organization in row.organization_ids.values():
                    facility_org_targets[(source, organization)].add(facility)
                    deterministic["facility_organization_explicit_id"] += 1
        if row.explicit_relationships:
            deterministic[f"explicit_graph_relationships:{source}"] += row.explicit_relationships
        if source == "us.fsis" and row.facility_ids:
            deterministic["fsis_observation_to_establishment_exact_id"] += 1
        if source in EVIDENCE_SOURCE_IDS and row.organization_ids:
            deterministic[f"aphis_exact_source_id:{source}"] += 1
        if source == "dk.smiley" and any(key.startswith("cvr") for key in row.organization_ids):
            deterministic["denmark_cvr_facility_organization"] += 1
        if source == "it.853-2004" and any(key in {"vat", "vat_number", "italian_vat", "fiscal_code", "italian_fiscal_code", "cod_fiscale", "p_iva"} for key in row.organization_ids):
            deterministic["italy_vat_or_fiscal_organization"] += 1
        if not row.provenance_complete:
            provenance_missing += 1
        suppressed += row.suppressed
        quarantined += row.quarantined
        if len({value[:10] for value in row.dates if len(value) >= 10}) > 1:
            temporal_inconsistencies += 1

    collision_classification = classify_collision_observations([
        {
            "source_id": row.source_id,
            "source_record_key": row.key,
            "facility_ids": row.facility_ids,
            "organization_ids": row.organization_ids,
        }
        for row in observations
    ])
    collisions = collision_classification["true_conflicts"]
    orphan_rows = sum(1 for row in observations if row.source_kind == "facility_master" and not row.facility_ids)
    candidate_iterator, candidate_generation = _iter_probabilistic_candidates(observations, max_block_size=max_block_size)
    candidate_count = 0
    confidence_bands: Counter[str] = Counter()
    review_candidates: list[dict[str, Any]] = []
    for item in candidate_iterator:
        candidate_count += 1
        confidence_bands[item["confidence_band"]] += 1
        if len(review_candidates) < sample_size:
            review_candidates.append({
                "candidate_digest": item["candidate_digest"],
                "source_pair": item["source_pair"],
                "endpoints": item["endpoints"],
                "provenance": item["provenance"],
                "confidence_band": item["confidence_band"],
                "method": item["method"],
                "ruleset": item["ruleset"],
            })
    candidate_generation["ambiguous_blocks_skipped"] = candidate_generation["blocks_ambiguous"]
    candidate_generation["ambiguous_rows_skipped"] = candidate_generation["rows_in_ambiguous_blocks"]
    candidate_generation["exact_equivalent_pairs_excluded"] = candidate_generation["pairs_exact_equivalent"]
    # The iterator is intentionally unbounded at the product layer.  The
    # only skipped work is an explicitly counted ambiguous block, never a
    # global first-N truncation.
    candidate_capped = False
    by_source_metrics = {}
    for source_id in sorted(set(manifests) | set(by_source)):
        by_source_metrics[source_id] = _source_metric(source_id, manifests.get(source_id), by_source.get(source_id, []))

    for source_id in sorted(by_source):
        source_rows = sorted(by_source[source_id], key=lambda row: row.key)
        for row in source_rows[: max(0, sample_size // max(1, len(by_source)))]:
            review_candidates.append({
                "candidate_digest": _digest(source_id + "|" + row.key + "|" + RULESET_VERSION),
                "source_id": source_id,
                "candidate_type": "deterministic_source_local", 
                "review_state": "review_required",
                "ruleset": RULESET_VERSION,
            })

    report = {
        "schema_version": REPORT_VERSION,
        "scope": {
            "manifest_sources": sorted(manifests),
            "private_row_sources": sorted(by_source),
            "row_payloads_in_report": False,
            "execution": "offline_private_analysis",
        },
        "source_metrics": by_source_metrics,
        "deterministic_connections": {
            "counts": dict(sorted(deterministic.items())),
            "source_scoped_identifier_observations": sum(identifiers.values()),
            "distinct_identifier_values": sum(len(values) for values in source_identifier_values.values()),
            "collision_count": collisions,
            "collision_classification": collision_classification,
            "orphan_facility_rows": orphan_rows,
            "provenance_complete_rows": sum(row.provenance_complete for row in observations),
            "provenance_incomplete_rows": provenance_missing,
            "edge_claims_review_required": True,
        },
        "probabilistic_candidates": {
            "count": candidate_count,
            "confidence_bands": dict(sorted(confidence_bands.items())),
            "candidate_generation_capped": candidate_capped,
            "candidate_generation": candidate_generation,
            "ordering": "candidate_digest_ascending",
            "resumable": True,
            "ruleset": RULESET_VERSION,
            "automatic_merge_count": 0,
            "claim_transfer_count": 0,
            "review_required_count": candidate_count,
            "disclaimer": "Observed candidate yield is not accuracy; no real precision/recall claim is made without human labels.",
        },
        "connectivity": {
            "nodes_observed": sum(bool(row.facility_ids or row.organization_ids) for row in observations),
            "rows_with_explicit_facility_organization_edge": sum(row.typed_entity_edge for row in observations),
            "edge_counts_by_source": dict(sorted({source: sum(row.typed_entity_edge or bool(row.explicit_relationships) for row in rows_for_source) for source, rows_for_source in by_source.items()}.items())),
            "aphis_fsis_automatic_links": 0,
            "aphis_fsis_review_candidates": 0,
            "aphis_fsis_policy": "evidence and FSIS facility identities remain separate; no automatic cross-source link",
        },
        "quality_metrics": {
            "temporal_inconsistency_rows": temporal_inconsistencies,
            "quarantined_rows_observed": quarantined,
            "suppressed_rows_observed": suppressed,
            "unresolved_rows": orphan_rows + sum(not row.facility_ids and row.source_kind == "evidence_event" for row in observations),
            "precision": "unmeasured",
            "recall": "unmeasured",
            "human_adjudication": "not performed",
        },
        "review_packet": {
            "schema_version": "d5-private-review-sample-v1",
            "sample_size_requested": sample_size,
            "sample_entries": review_candidates[:sample_size],
            "raw_rows": "restricted external handoff only",
            "deterministic_selection": f"sha256(source_id|source_record_key|{RULESET_VERSION}) sorted by digest",
            "review_state": "review_required",
            "publication_status": "not_eligible",
        },
        "gates": {
            "storage_state": "private",
            "privacy_status": "pending",
            "public_projection": "blocked",
            "publication": "blocked",
            "geocoding": "disabled",
            "automatic_merge": False,
        },
        "limitations": [
            "Real row artifacts are supplied only through restricted local JSONL paths; checked-in manifests are aggregate-only.",
            "Deterministic edges are source evidence candidates and remain review-required.",
            "Probabilistic candidates use documented multi-signal rules and never merge identities or transfer claims.",
            "No authorized human adjudication was available; precision and recall remain unmeasured.",
            "A source disappearance is not inferred as closure.",
        ],
    }
    _row_free(report)
    return report


def write_report(path: str | Path, report: Mapping[str, Any]) -> None:
    _row_free(report)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_rows(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        source_id, separator, path = value.partition("=")
        if not separator or not source_id or not path:
            raise ValueError("--rows must use SOURCE_ID=PATH")
        parsed[source_id] = path
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="row-free D5 analysis of private graph connections")
    parser.add_argument("--manifest", action="append", required=True, help="aggregate manifest; may be repeated")
    parser.add_argument("--rows", action="append", default=[], metavar="SOURCE_ID=PATH", help="restricted JSONL handoff; may be repeated")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=50)
    args = parser.parse_args(argv)
    if args.sample_size < 0 or args.sample_size > 1000:
        parser.error("--sample-size must be between 0 and 1000")
    manifests = read_aggregate_manifests(args.manifest)
    observations = load_private_rows(_parse_rows(args.rows)) if args.rows else []
    write_report(args.output, analyze(manifests=manifests, rows=observations, sample_size=args.sample_size))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
