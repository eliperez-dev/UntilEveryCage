"""Small, versioned graph-connection engine for D6.

This module deliberately models connections, not canonical identities.  It
can emit an exact or inferred edge when there is enough evidence to be useful,
but it never creates a universal ID, merges endpoints, or transfers claims.
The scorer uses grouped contributions: repeated signals in one correlated
group have diminishing returns while independent groups compound.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Iterable, Mapping


RULESET_VERSION = "d6-signal-rules-v1"
ENTITY_TYPES = {"facility", "organization", "evidence_event"}
CONNECTION_TYPES = {"exact", "inferred"}
CONFIDENCE_BANDS = {"exact", "high", "probable", "possible", "low"}
_FORBIDDEN_ID_KEYS = {"canonical_id", "global_id", "universal_id", "universal_identity"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class EntityRef:
    """A source-qualified endpoint; it is never a universal identity."""

    entity_type: str
    source_id: str
    identifier_type: str
    source_identifier: str

    def __post_init__(self) -> None:
        if self.entity_type not in ENTITY_TYPES:
            raise ValueError("entity_type must be facility, organization, or evidence_event")
        for name in ("source_id", "identifier_type", "source_identifier"):
            _text(getattr(self, name), name)

    def as_dict(self) -> dict[str, str]:
        return {
            "entity_type": self.entity_type,
            "source_id": self.source_id,
            "identifier_type": self.identifier_type,
            "source_identifier": self.source_identifier,
            "identity_scope": "source_scoped",
        }

    def key(self) -> str:
        return _canonical(self.as_dict())


@dataclass(frozen=True)
class SourceRef:
    """A compact provenance pointer.  It intentionally carries no raw row."""

    source_id: str
    source_record_key: str | None = None
    source_record_id: str | None = None
    role: str = "supporting"

    def __post_init__(self) -> None:
        _text(self.source_id, "source_id")
        if not self.source_record_key and not self.source_record_id:
            raise ValueError("source reference needs source_record_key or source_record_id")
        _text(self.role, "role")

    def as_dict(self) -> dict[str, str]:
        value = {"source_id": self.source_id, "role": self.role}
        if self.source_record_key:
            value["source_record_key"] = self.source_record_key
        if self.source_record_id:
            value["source_record_id"] = self.source_record_id
        return value


@dataclass(frozen=True)
class Signal:
    """One observed matching signal.

    ``weight`` is a ruleset contribution, not a probability.  Multiple signals
    in the same group are discounted by the scorer.
    """

    name: str
    group: str
    weight: float
    value: bool = True
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.name, "signal name")
        _text(self.group, "signal group")
        if not isinstance(self.weight, (int, float)) or not math.isfinite(self.weight) or not 0 <= self.weight <= 1:
            raise ValueError("signal weight must be finite and between 0 and 1")
        if not isinstance(self.value, bool):
            raise ValueError("signal value must be boolean")
        if not isinstance(self.details, Mapping):
            raise ValueError("signal details must be an object")

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "group": self.group, "weight": round(float(self.weight), 8), "value": self.value, "details": dict(self.details)}


@dataclass(frozen=True)
class SignalDefinition:
    name: str
    group: str
    weight: float
    qualifies: bool = False
    contradiction: bool = False


class SignalRegistry:
    """Extensible signal definitions; adding a rule does not need a migration."""

    def __init__(self, *, version: str = RULESET_VERSION, definitions: Iterable[SignalDefinition] = ()) -> None:
        self.version = _text(version, "ruleset version")
        self._definitions: dict[str, SignalDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: SignalDefinition | None = None, *, name: str | None = None,
                 group: str | None = None, weight: float | None = None,
                 qualifies: bool = False, contradiction: bool = False) -> SignalDefinition:
        if definition is None:
            if name is None or group is None or weight is None:
                raise ValueError("name, group, and weight are required")
            definition = SignalDefinition(name, group, weight, qualifies, contradiction)
        if definition.name in self._definitions:
            raise ValueError(f"signal already registered: {definition.name}")
        self._definitions[definition.name] = definition
        return definition

    def signal(self, name: str, *, value: bool = True, details: Mapping[str, Any] | None = None,
               weight: float | None = None) -> Signal:
        definition = self._definitions.get(name)
        if definition is None:
            raise ValueError(f"unknown signal: {name}")
        return Signal(name, definition.group, definition.weight if weight is None else weight, value, details or {})

    def definition(self, name: str) -> SignalDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise ValueError(f"unknown signal: {name}") from exc

    def definitions(self) -> tuple[SignalDefinition, ...]:
        return tuple(self._definitions[name] for name in sorted(self._definitions))


def default_signal_registry(*, version: str = RULESET_VERSION) -> SignalRegistry:
    """Return the deliberately narrow first D6 ruleset."""
    registry = SignalRegistry(version=version)
    for definition in (
        SignalDefinition("authoritative_identifier", "source", 1.0, qualifies=True),
        SignalDefinition("source_assertion", "source", 1.0, qualifies=True),
        SignalDefinition("identifier_cooccurrence", "identity", 0.62, qualifies=True),
        SignalDefinition("organization_name_normalized", "identity", 0.34, qualifies=False),
        SignalDefinition("postal_match", "location", 0.18),
        SignalDefinition("city_match", "location", 0.10),
        SignalDefinition("address_match", "location", 0.22),
        SignalDefinition("business_phone_match", "contact", 0.11),
        SignalDefinition("website_domain_match", "contact", 0.11),
        SignalDefinition("repeated_independent_source", "source", 0.16, qualifies=True),
        SignalDefinition("temporal_compatibility", "temporal", 0.08),
        SignalDefinition("conflicting_identifier", "contradiction", 0.24, contradiction=True),
        SignalDefinition("conflicting_address", "contradiction", 0.14, contradiction=True),
        SignalDefinition("temporal_conflict", "contradiction", 0.16, contradiction=True),
        # Registered explicitly so the engine can explain that these do not
        # create an edge by themselves.
        SignalDefinition("name_only", "identity", 0.16),
        SignalDefinition("address_only", "location", 0.16),
        SignalDefinition("phone_only", "contact", 0.10),
        SignalDefinition("domain_only", "contact", 0.10),
        SignalDefinition("proximity_only", "location", 0.08),
        SignalDefinition("fuzzy_only", "identity", 0.12),
    ):
        registry.register(definition)
    return registry


@dataclass(frozen=True)
class ScoringResult:
    connection_type: str | None
    confidence: float
    confidence_band: str
    match_method: str
    signals: tuple[dict[str, Any], ...]
    contradictions: tuple[dict[str, Any], ...]
    eligible: bool
    explanation: dict[str, Any]
    ruleset_version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "connection_type": self.connection_type,
            "confidence": self.confidence,
            "confidence_band": self.confidence_band,
            "match_method": self.match_method,
            "signals": list(self.signals),
            "contradictions": list(self.contradictions),
            "eligible": self.eligible,
            "explanation": self.explanation,
            "ruleset_version": self.ruleset_version,
        }


def _coerce_signal(registry: SignalRegistry, value: Signal | Mapping[str, Any]) -> tuple[Signal, SignalDefinition]:
    if isinstance(value, Signal):
        signal = value
        definition = registry.definition(signal.name)
        return signal, definition
    if not isinstance(value, Mapping):
        raise ValueError("signals must contain Signal objects or mappings")
    name = _text(value.get("name"), "signal.name")
    definition = registry.definition(name)
    signal = Signal(name, str(value.get("group", definition.group)), float(value.get("weight", definition.weight)), bool(value.get("value", True)), value.get("details") or {})
    return signal, definition


def _band(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "probable"
    if score >= 0.40:
        return "possible"
    return "low"


def score_connection(signals: Iterable[Signal | Mapping[str, Any]], *, registry: SignalRegistry | None = None) -> ScoringResult:
    """Score a candidate deterministically under a versioned registry.

    An inferred edge requires an anchor rule.  Corroborating phone/domain
    signals and weak single signals therefore cannot create edges alone.
    """
    registry = registry or default_signal_registry()
    positive: list[tuple[Signal, SignalDefinition]] = []
    contradictions: list[tuple[Signal, SignalDefinition]] = []
    for raw in signals:
        signal, definition = _coerce_signal(registry, raw)
        if not signal.value:
            continue
        (contradictions if definition.contradiction else positive).append((signal, definition))
    exact = any(definition.name in {"authoritative_identifier", "source_assertion"} for _, definition in positive)
    positive_names = {definition.name for _, definition in positive}
    qualifying_names = {definition.name for _, definition in positive if definition.qualifies}
    name = "organization_name_normalized" in positive_names or "name_only" in positive_names
    postal = "postal_match" in positive_names
    city_address = positive_names.issuperset({"organization_name_normalized", "city_match", "address_match"})
    anchor = exact or bool(qualifying_names) or (name and postal) or city_address

    groups: dict[str, list[Signal]] = {}
    for signal, _ in positive:
        groups.setdefault(signal.group, []).append(signal)
    group_totals: dict[str, float] = {}
    for group, values in sorted(groups.items()):
        ordered = sorted(values, key=lambda item: (-item.weight, item.name, _canonical(item.details)))
        group_totals[group] = sum(float(signal.weight) * (0.68 ** index) for index, signal in enumerate(ordered))
    raw_positive = sum(group_totals.values())
    contradiction_values = sorted((float(signal.weight) for signal, _ in contradictions), reverse=True)
    contradiction_penalty = sum(value * (0.76 ** index) for index, value in enumerate(contradiction_values))
    score = max(0.0, min(1.0, raw_positive - contradiction_penalty))
    if exact:
        score = 1.0
        connection_type: str | None = "exact"
        band = "exact"
        method = "source_assertion" if any(d.name == "source_assertion" for _, d in positive) else "authoritative_identifier"
        eligible = True
    elif anchor:
        connection_type = "inferred"
        band = _band(score)
        method = "+".join(sorted(signal.name for signal, _ in positive))
        eligible = True
    else:
        connection_type = None
        band = _band(score)
        method = "insufficient_anchor"
        eligible = False
    signal_rows = tuple(signal.as_dict() for signal, _ in sorted(positive, key=lambda pair: (pair[0].group, pair[0].name, _canonical(pair[0].details))))
    contradiction_rows = tuple(signal.as_dict() for signal, _ in sorted(contradictions, key=lambda pair: (pair[0].group, pair[0].name, _canonical(pair[0].details))))
    explanation = {
        "ruleset_version": registry.version,
        "group_contributions": {key: round(value, 8) for key, value in sorted(group_totals.items())},
        "positive_contribution": round(raw_positive, 8),
        "contradiction_penalty": round(contradiction_penalty, 8),
        "anchor_present": anchor,
        "disclaimer": "Confidence is a deterministic ruleset estimate, not a measured probability.",
    }
    return ScoringResult(connection_type, round(score, 5), band, method, signal_rows, contradiction_rows, eligible, explanation, registry.version)


def build_connection_edge(*, from_ref: EntityRef, to_ref: EntityRef, relationship_type: str,
                          scoring: ScoringResult, supporting_source_refs: Iterable[SourceRef],
                          observed_at: str | datetime, conflicting: bool = False,
                          suppressed: bool = False, computed_at: str | datetime | None = None) -> dict[str, Any]:
    """Build a validated private read-model row from a scoring result."""
    _text(relationship_type, "relationship_type")
    if not scoring.eligible or scoring.connection_type not in CONNECTION_TYPES:
        raise ValueError("cannot build an edge without an exact or anchored inferred connection")
    observed = observed_at.isoformat() if isinstance(observed_at, datetime) else _text(observed_at, "observed_at")
    computed = (computed_at.isoformat() if isinstance(computed_at, datetime) else computed_at) if computed_at is not None else datetime.now(timezone.utc).isoformat()
    refs = [ref.as_dict() for ref in supporting_source_refs]
    endpoint_payload = {"from": from_ref.as_dict(), "to": to_ref.as_dict(), "relationship_type": relationship_type, "connection_type": scoring.connection_type, "ruleset_version": scoring.ruleset_version}
    edge_key = hashlib.sha256(_canonical(endpoint_payload).encode("utf-8")).hexdigest()
    row = {
        "edge_key": edge_key,
        "from": from_ref.as_dict(),
        "to": to_ref.as_dict(),
        "relationship_type": relationship_type,
        "connection_type": scoring.connection_type,
        "confidence": scoring.confidence,
        "confidence_band": scoring.confidence_band,
        "match_method": scoring.match_method,
        "supporting_source_refs": refs,
        "signal_explanation": {**scoring.explanation, "signals": list(scoring.signals), "contradictions": list(scoring.contradictions)},
        "ruleset_version": scoring.ruleset_version,
        "observed_at": observed,
        "computed_at": computed,
        "conflicting": bool(conflicting or scoring.contradictions),
        "suppressed": bool(suppressed),
        "storage_state": "private",
        "publication_status": "not_eligible",
    }
    validate_connection_edge(row)
    return row


def validate_connection_edge(edge: Mapping[str, Any]) -> dict[str, Any]:
    required = ("edge_key", "from", "to", "relationship_type", "connection_type", "confidence", "confidence_band", "match_method", "supporting_source_refs", "signal_explanation", "ruleset_version", "observed_at")
    for field_name in required:
        if field_name not in edge:
            raise ValueError(f"edge requires {field_name}")
    for endpoint_name in ("from", "to"):
        endpoint = edge[endpoint_name]
        if not isinstance(endpoint, Mapping):
            raise ValueError(f"{endpoint_name} endpoint must be an object")
        if set(endpoint) & _FORBIDDEN_ID_KEYS:
            raise ValueError("edge endpoints must not contain universal identity fields")
        EntityRef(str(endpoint.get("entity_type")), str(endpoint.get("source_id")), str(endpoint.get("identifier_type")), str(endpoint.get("source_identifier")))
    if edge["connection_type"] not in CONNECTION_TYPES:
        raise ValueError("connection_type must be exact or inferred")
    if not isinstance(edge["confidence"], (int, float)) or not 0 <= edge["confidence"] <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if edge["connection_type"] == "exact" and (edge["confidence"] != 1 or edge["confidence_band"] != "exact"):
        raise ValueError("exact edges must have confidence 1 and exact band")
    if edge["connection_type"] == "inferred" and edge["confidence_band"] == "exact":
        raise ValueError("inferred edges cannot use exact confidence band")
    if not isinstance(edge["supporting_source_refs"], list) or not isinstance(edge["signal_explanation"], Mapping):
        raise ValueError("supporting_source_refs must be a list and signal_explanation an object")
    if edge.get("storage_state", "private") != "private" or edge.get("publication_status", "not_eligible") != "not_eligible":
        raise ValueError("connection edges must remain private and not eligible")
    return dict(edge)


def persist_connection_edges(connection: Any, edges: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Idempotently upsert derived private edges using a DB-API connection."""
    inserted = updated = 0
    sql = """INSERT INTO uec.graph_connection_edges
        (edge_key,from_entity_type,from_source_id,from_identifier_type,from_source_identifier,
         to_entity_type,to_source_id,to_identifier_type,to_source_identifier,relationship_type,
         connection_type,confidence,confidence_band,match_method,supporting_source_refs,
         signal_explanation,ruleset_version,observed_at,computed_at,conflicting,suppressed,
         storage_state,publication_status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,'private','not_eligible')
        ON CONFLICT (edge_key) DO UPDATE SET
          confidence=EXCLUDED.confidence, confidence_band=EXCLUDED.confidence_band,
          match_method=EXCLUDED.match_method, supporting_source_refs=EXCLUDED.supporting_source_refs,
          signal_explanation=EXCLUDED.signal_explanation, ruleset_version=EXCLUDED.ruleset_version,
          observed_at=EXCLUDED.observed_at, computed_at=EXCLUDED.computed_at,
          conflicting=EXCLUDED.conflicting, suppressed=EXCLUDED.suppressed"""
    for raw in edges:
        edge = validate_connection_edge(raw)
        left, right = edge["from"], edge["to"]
        args = (edge["edge_key"], left["entity_type"], left["source_id"], left["identifier_type"], left["source_identifier"], right["entity_type"], right["source_id"], right["identifier_type"], right["source_identifier"], edge["relationship_type"], edge["connection_type"], edge["confidence"], edge["confidence_band"], edge["match_method"], _canonical(edge["supporting_source_refs"]), _canonical(edge["signal_explanation"]), edge["ruleset_version"], edge["observed_at"], edge.get("computed_at") or datetime.now(timezone.utc).isoformat(), edge.get("conflicting", False), edge.get("suppressed", False))
        cursor = connection.execute(sql, args)
        if getattr(cursor, "rowcount", 1) == 1:
            inserted += 1
        else:
            updated += 1
    return {"inserted": inserted, "updated": updated, "total": inserted + updated}


__all__ = [
    "RULESET_VERSION", "EntityRef", "SourceRef", "Signal", "SignalDefinition", "SignalRegistry", "ScoringResult",
    "default_signal_registry", "score_connection", "build_connection_edge", "validate_connection_edge", "persist_connection_edges",
]
