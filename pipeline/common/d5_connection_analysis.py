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
import re
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
})
ORG_ID_KEYS = frozenset({
    "cvr", "cvr_number", "vat", "vat_number", "italian_vat",
    "fiscal_code", "italian_fiscal_code", "cod_fiscale", "p_iva",
    "operator_id", "operator_number", "customer_number", "abn", "acn",
})
NAME_KEYS = frozenset({"name", "trading_name", "operator_name", "account_name", "legal_name", "site_name"})
CITY_KEYS = frozenset({"city", "town", "municipality", "locality"})
POSTAL_KEYS = frozenset({"postal_code", "postcode", "zip", "postal", "postnummer"})
ADDRESS_KEYS = frozenset({"address", "street", "address_line_1", "address1", "address_lines"})
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
    provenance_complete: bool = False
    quarantined: bool = False
    suppressed: bool = False


def _source_kind(source_id: str, row: Mapping[str, Any]) -> str:
    value = _clean(row.get("source_kind"))
    if value in {"facility_master", "evidence_event"}:
        return value
    return "evidence_event" if source_id in EVIDENCE_SOURCE_IDS else "facility_master"


def _nested_values(row: Mapping[str, Any]) -> Iterable[tuple[str, Any]]:
    for container_name in ("normalized", "source_fields", "source_native_ids"):
        container = row.get(container_name)
        if isinstance(container, Mapping):
            for key, value in container.items():
                yield str(key).casefold(), value
    # A graph-candidate itself can carry identifiers in typed entities.
    for entity_key in ("facilities", "organizations"):
        entities = row.get(entity_key)
        if isinstance(entities, list):
            for entity in entities:
                if not isinstance(entity, Mapping):
                    continue
                identifier = entity.get("source_identifier")
                if isinstance(identifier, Mapping):
                    yield str(identifier.get("identifier_type", "")).casefold(), identifier.get("value")


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
    key = _clean(row.get("source_record_key")) or _clean(row.get("source_row_id")) or _clean(row.get("source_observation_key")) or "row-unknown"
    relationships = row.get("relationships")
    explicit_relationships = len(relationships) if isinstance(relationships, list) else 0
    source_values = row.get("source_values")
    provenance_complete = bool(
        _clean(row.get("source_record_key") or row.get("source_row_id"))
        and isinstance(source_values, Mapping)
        and (_clean(row.get("source_artifact_sha256")) or _clean(row.get("artifact_sha256")))
    )
    suppressed = bool(row.get("suppressed") or row.get("public_access_revoked"))
    return _Observed(source_id, kind, key, facility_ids, organization_ids, signals, dates,
                     explicit_relationships, provenance_complete, bool(row.get("quarantine_reason")), suppressed)


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


def _probabilistic_candidates(rows: list[_Observed], limit: int = 5000) -> tuple[list[dict[str, Any]], bool]:
    """Generate aggregate-only multi-signal candidates.

    Only facility rows participate.  Two compatible signals are required;
    exact source-native identifiers are handled by deterministic edges.
    """
    indexed: dict[tuple[str, str], list[_Observed]] = defaultdict(list)
    for row in rows:
        if row.source_kind != "facility_master" or not row.signals.get("name"):
            continue
        name = row.signals["name"]
        for signal in ("postal", "city", "address"):
            value = row.signals.get(signal)
            if value:
                indexed[(signal, name + "|" + value)].append(row)
    pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for group in indexed.values():
        unique = {(item.source_id, item.key): item for item in group}
        for left, right in combinations(unique.values(), 2):
            if left.source_id == right.source_id and left.key == right.key:
                continue
            methods = []
            common = set(left.signals).intersection(right.signals)
            if {"name", "postal"}.issubset(common):
                methods.append("normalized_name+postal")
            if {"name", "city"}.issubset(common):
                methods.append("normalized_name+city")
            if {"name", "address"}.issubset(common):
                methods.append("normalized_name+address")
            for method in methods:
                key = tuple(sorted((f"{left.source_id}:{left.key}", f"{right.source_id}:{right.key}")))
                pairs[key].add(method)
    candidates: list[dict[str, Any]] = []
    for (left_key, right_key), methods in sorted(pairs.items()):
        if len(candidates) >= limit:
            break
        common = sorted(methods)
        score = 0.82 if "normalized_name+postal" in methods else 0.74 if "normalized_name+address" in methods else 0.68
        band = "probable" if score >= 0.74 else "possible"
        candidates.append({
            "candidate_digest": _digest(left_key + "|" + right_key + "|" + RULESET_VERSION),
            "source_pair": sorted({left_key.split(":", 1)[0], right_key.split(":", 1)[0]}),
            "method": "multi_signal_intersection",
            "contributing_features": common,
            "contradictory_evidence": [],
            "confidence": score,
            "confidence_band": band,
            "review_state": "review_required",
            "automatic_merge": False,
            "transfers_claims": False,
            "disclaimer": "Possible source-record connection; not human verified and must not be treated as a canonical identity.",
            "ruleset": RULESET_VERSION,
        })
    return candidates, len(pairs) > limit


def analyze(*, manifests: Mapping[str, Mapping[str, Any]], rows: Iterable[_Observed] = (), sample_size: int = 50) -> dict[str, Any]:
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
        if row.facility_ids and row.organization_ids:
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

    collisions = sum(max(0, len(values) - 1) for values in source_identifier_values.values())
    orphan_rows = sum(1 for row in observations if row.source_kind == "facility_master" and not row.facility_ids)
    candidate_rows, candidate_capped = _probabilistic_candidates(observations)
    confidence_bands = Counter(item["confidence_band"] for item in candidate_rows)
    by_source_metrics = {}
    for source_id in sorted(set(manifests) | set(by_source)):
        by_source_metrics[source_id] = _source_metric(source_id, manifests.get(source_id), by_source.get(source_id, []))

    review_candidates = []
    for item in candidate_rows[:sample_size]:
        review_candidates.append({
            "candidate_digest": item["candidate_digest"],
            "source_pair": item["source_pair"],
            "confidence_band": item["confidence_band"],
            "method": item["method"],
            "ruleset": item["ruleset"],
        })
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
            "orphan_facility_rows": orphan_rows,
            "provenance_complete_rows": sum(row.provenance_complete for row in observations),
            "provenance_incomplete_rows": provenance_missing,
            "edge_claims_review_required": True,
        },
        "probabilistic_candidates": {
            "count": len(candidate_rows),
            "confidence_bands": dict(sorted(confidence_bands.items())),
            "candidate_generation_capped": candidate_capped,
            "ruleset": RULESET_VERSION,
            "automatic_merge_count": 0,
            "claim_transfer_count": 0,
            "review_required_count": len(candidate_rows),
            "disclaimer": "Observed candidate yield is not accuracy; no real precision/recall claim is made without human labels.",
        },
        "connectivity": {
            "nodes_observed": sum(bool(row.facility_ids or row.organization_ids) for row in observations),
            "rows_with_explicit_facility_organization_edge": sum(bool(row.facility_ids and row.organization_ids) for row in observations),
            "edge_counts_by_source": dict(sorted({source: sum(bool(row.facility_ids and row.organization_ids) or bool(row.explicit_relationships) for row in rows_for_source) for source, rows_for_source in by_source.items()}.items())),
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
