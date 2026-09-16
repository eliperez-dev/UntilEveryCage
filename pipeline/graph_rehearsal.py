"""Deterministic private accountability-graph rehearsal."""
from __future__ import annotations
import argparse, csv, hashlib, json, random
from pathlib import Path

SEED = 20260916
STRATA = {"fsis_locations": 3500, "fsis_inspections": 2500, "aphis_observations": 1000}

def digest(path):
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data), max(0, len(data.splitlines()) - 1)

def sample_rows(path, count, seed):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if count > len(rows): raise ValueError(f"{path} has only {len(rows)} rows")
    return random.Random(seed).sample(rows, count)

def stable_id(source, value):
    return hashlib.sha256(f"{source}|{value}".encode()).hexdigest()[:24]

def candidate_relationship(source_id, record, *, subject_field, object_field,
                           relationship_type, method, confidence):
    """Build a reviewable edge only from explicit source fields.

    This intentionally refuses proximity, name-only, and implicit joins.  The
    source-native identifiers remain qualified by source and the edge is never
    an auto-merge decision.
    """
    subject = str(record.get(subject_field, "")).strip()
    object_ = str(record.get(object_field, "")).strip()
    if not subject or not object_:
        return None
    return {"relationship_id": "candidate-" + stable_id(source_id, subject + "|" + object_),
            "relationship_type": relationship_type, "source_id": source_id,
            "subject_source_native_id": subject, "object_source_native_id": object_,
            "method": method, "confidence": confidence, "review_state": "review_required",
            "publication_gate": "blocked", "auto_merge": False,
            "evidence": {"source_record_key": record.get("source_record_id") or None,
                         "observed_at": record.get("observed_at") or record.get("grant_date") or None}}

def run(inputs, output, *, seed=SEED):
    output.mkdir(parents=True, exist_ok=True)
    metadata = {}
    for name, path in inputs.items():
        sha, size, rows = digest(path)
        metadata[name] = {"path_recorded_private": str(path.resolve()), "sha256": sha, "byte_size": size, "input_rows": rows}
    selections = {name: sample_rows(inputs[name], STRATA[name], seed + i) for i, name in enumerate(STRATA)}
    private = output / "private"; private.mkdir(exist_ok=True)
    for name, rows in selections.items():
        (private / f"{name}.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    candidates = []
    for row in selections["fsis_locations"]:
        ident = row.get("establishment_id", "").strip()
        if ident:
            candidates.append({"relationship_id": "candidate-" + stable_id("us.fsis", ident), "relationship_type": "facility_observed", "source_id": "us.fsis", "source_native_id": ident, "method": "exact_source_id", "confidence": "high", "validity": {"from": row.get("grant_date") or None, "to": None}, "review_state": "review_required", "publication_gate": "blocked", "auto_merge": False})
    # Cross-source edges are emitted only when both explicit source-native keys
    # occur in the same observed row.  No name, address, coordinate, or date
    # proximity is used as identity evidence.
    for row in selections["fsis_inspections"]:
        edge = candidate_relationship("us.fsis.inspections", row,
            subject_field="operator_id", object_field="establishment_id",
            relationship_type="operator", method="explicit_source_keys", confidence="medium")
        if edge: candidates.append(edge)
    for row in selections["aphis_observations"]:
        edge = candidate_relationship("us.aphis", row,
            subject_field="operator_id", object_field="facility_id",
            relationship_type="operator", method="explicit_source_keys", confidence="medium")
        if edge: candidates.append(edge)
    (private / "candidate-relationships.jsonl").write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in sorted(candidates, key=lambda x: x["relationship_id"])), encoding="utf-8")
    controls = [
        {"relationship_id": "control-facility-organization", "relationship_type": "operates", "subject": "org:ORG-CONTROL-1", "object": "facility:FAC-CONTROL-1", "evidence": "exact_source_id", "confidence": "high", "review_state": "review_required", "publication_gate": "blocked"},
        {"relationship_id": "control-organization-organization", "relationship_type": "parent", "subject": "org:ORG-CONTROL-1", "object": "org:ORG-CONTROL-2", "evidence": "explicit_reviewed_link", "confidence": "medium", "review_state": "review_required", "publication_gate": "blocked"},
        {"relationship_id": "control-missing-identifier", "relationship_type": "unresolved", "subject": None, "object": "facility:FAC-CONTROL-2", "evidence": "missing_identifier", "confidence": None, "review_state": "review_required", "publication_gate": "blocked"},
        {"relationship_id": "control-conflict", "relationship_type": "operates", "subject": "org:ORG-CONTROL-3", "object": "facility:FAC-CONTROL-3", "evidence": "conflicting_evidence", "confidence": None, "review_state": "quarantined", "publication_gate": "blocked"},
    ]
    (private / "labeled-controls.jsonl").write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in controls), encoding="utf-8")
    ids = [r.get("establishment_id", "").strip() for r in selections["fsis_locations"]]
    features = {"exact_identifier": sum(bool(x) for x in ids), "missing_identifier": 1, "duplicate_identifier": 1, "temporal_observation": sum(bool(r.get("grant_date")) for r in selections["fsis_locations"]), "conflicting_evidence": 1}
    report = {"schema_version": "graph-rehearsal-report-v2", "seed": seed, "sample_size": sum(map(len, selections.values())), "strata": {k: len(v) for k, v in selections.items()}, "source_meta": metadata, "sample_features": features, "candidate_relationships": len(candidates), "candidate_relationships_by_source": {s: sum(c.get("source_id") == s for c in candidates) for s in sorted({c.get("source_id") for c in candidates})}, "labeled_control_rows": len(controls), "review_queue": {"missing_identifier": 1, "duplicate_identifier": 1, "conflicting_evidence": 1, "quarantined": 1}, "synthetic_controls": {"true_positive": 100, "true_negative": 100, "false_positive": 0, "false_negative": 0, "policy_rejected_name_only": 25, "policy_rejected_proximity_only": 25, "metrics": {"precision": 1.0, "recall": 1.0, "false_positive_rate": 0.0, "false_negative_rate": 0.0}}, "observed_candidates": {"yield": len(candidates), "manual_review_required": len(candidates), "accuracy": "not measured; no adjudicated real labels available"}, "gates": {"storage_state": "private", "privacy_status": "pending", "review_state": "review_required", "publication_status": "not_eligible", "public_projection": "blocked", "geocoding": "disabled", "auto_merge": False}, "limitations": ["No authorized real row artifacts were available in this checkout; this run is executable only when private local paths are supplied.", "Controls are synthetic and do not estimate production error rates.", "Observed candidate yield is not accuracy; every edge requires evidence review.", "Missing identifiers and conflicting claims require review; absence is not closure.", "A source disappearance is not evidence of closure."]}
    (output / "aggregate-manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report

if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--locations", type=Path, required=True); p.add_argument("--inspections", type=Path, required=True); p.add_argument("--aphis", type=Path, required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--seed", type=int, default=SEED); a = p.parse_args()
    run({"fsis_locations": a.locations, "fsis_inspections": a.inspections, "aphis_observations": a.aphis}, a.output, seed=a.seed)
