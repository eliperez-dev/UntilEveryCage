"""Recover missing locality context from hash-verified retained AESAN exports."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
from email.message import Message

import psycopg

from .cohort_acquisition import _eligible_representatives, _load_records, _processed_keys
from .location_enrichment import (
    FINDER_URL, SOURCE_ID, append_private_events, match_official_result,
    parse_official_results, registration_components,
)


def address_key(value: str) -> str:
    from pipeline.geocoding.geoapify import GeoapifyAdapter
    return GeoapifyAdapter._normalize(value)


def retained_index(directory: Path):
    """Validate artifact provenance before indexing bounded address-only rows."""
    index = defaultdict(dict)
    artifacts = 0
    for path in sorted(directory.glob("*.xls")):
        metadata_path = path.with_suffix(".json")
        if path.is_symlink() or metadata_path.is_symlink() or path.stat().st_size > 2*1024*1024:
            raise ValueError("retained_export_invalid")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        raw = path.read_bytes()
        if (metadata.get("source_id") != SOURCE_ID or metadata.get("source_url") != FINDER_URL
                or metadata.get("response_kind") not in {"official_excel_export", "explicit_empty_result_page"}
                or metadata.get("query_scope", {}).get("registration_number") != "blank"
                or hashlib.sha256(raw).hexdigest() != metadata.get("response_sha256")):
            raise ValueError("retained_export_provenance_mismatch")
        headers=Message();headers["Content-Type"]=metadata.get("content_type","")
        charset=headers.get_content_charset() or "iso-8859-1"
        for row in parse_official_results(raw.decode(charset, "strict")):
            key = registration_components(row["registration"])
            # Only exact duplicate location rows collapse across filter exports.
            # Different addresses or towns remain independent alternatives.
            index[key].setdefault(tuple(sorted(row.items())), (row, metadata))
        artifacts += 1
    return index, artifacts


def recover(database_url: str, records_path: Path, artifacts_path: Path, output_path: Path,
            *, connect=psycopg.connect):
    root = Path(os.environ["UEC_REAL_PREVIEW_RUNS_ROOT"]).resolve()
    if not output_path.resolve().is_relative_to(root):
        raise ValueError("event_output_must_be_under_UEC_REAL_PREVIEW_RUNS_ROOT")
    records, digest = _load_records(records_path)
    candidates = _eligible_representatives(database_url, digest, connect, missing_localities_only=True)
    processed = _processed_keys(output_path)
    index, artifacts = retained_index(artifacts_path)
    counts = Counter()
    events = []
    for registration, key in candidates:
        if key in processed:
            counts["already_checkpointed"] += 1
            continue
        record = records.get(key)
        if record is None or registration_components(record["normalized"]["establishment_id"]) != registration_components(registration):
            raise ValueError("source_record_binding_mismatch")
        matches = list(index.get(registration_components(registration), {}).values())
        if len(matches) != 1:
            counts["not_retained" if not matches else "ambiguous_retained_rows"] += 1
            continue
        result, metadata = matches[0]
        source_address = record["normalized"].get("address", "")
        if not address_key(source_address) or address_key(source_address) != address_key(result.get("address", "")):
            counts["retained_address_differs"] += 1
            continue
        event = match_official_result(record, [result], retrieved_at=metadata["retrieved_at_utc"],
            result_url="https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal_excel.jsp",
            request_url="https://rgsa-web-aesan.mscbs.es/rgsa/procesaBusquedaServlet")
        counts[event["outcome"]] += 1
        if event["outcome"] == "matched":
            event.update(bulk_export_response_sha256=metadata["response_sha256"],
                bulk_export_query_scope=metadata["query_scope"],
                replay_ruleset="aesan-province-field-labels-v2",
                retained_source_address_matched=True)
            events.append(event)
    if events:
        append_private_events(output_path, events)
    return {"source_id": SOURCE_ID, "retained_artifacts_checked": artifacts,
            "missing_locality_records_examined": len(candidates), "outcomes": dict(counts),
            "events_appended": len(events), "provider_calls": 0, "upstream_requests": 0}
