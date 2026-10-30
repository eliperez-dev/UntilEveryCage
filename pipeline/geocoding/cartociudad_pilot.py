"""Bounded Spanish government-address pilot; no database or release writes.

Source: https://github.com/IDEESpain/Cartociudad
Reuse: CC BY 4.0 www.scne.es/productos.html#CartoCiudad
Real address transfers require the maintainer's scoped authorization.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

from . import spanish_addresses as s

ENDPOINT = "https://www.cartociudad.es/geocoder/api/geocoder/candidates"
RULESET = "cartociudad-spanish-address-pilot-v1"
FIELDS = ("id", "type", "address", "tip_via", "portalNumber", "extension", "noNumber",
          "muni", "muniCode", "poblacion", "province", "provinceCode", "postalCode",
          "countryCode", "lat", "lng")


def parameters(context, *, query_style="full_context"):
    """Send only source address and authorized geographic context."""
    if (set(context) - {"address", "locality", "postcode", "province", "country_code"}
            or context.get("country_code") != "ES"
            or any(not isinstance(context.get(k), str) or not context[k].strip()
                   or len(context[k]) > 1200 for k in ("address", "locality", "province"))
            or context.get("postcode") is not None and not isinstance(context["postcode"], str)):
        raise ValueError("invalid_spanish_source_context")
    address = s.provider_address(context["address"])
    if query_style == "address_town":
        return {"q": f"{address} {context['locality']}", "countrycodes": "es", "limit": 33}
    if query_style == "geographic_filters":
        result = {"q": address, "municipio_filter": context["locality"],
                  "provincia_filter": context["province"], "countrycodes": "es", "limit": 33}
        if context.get("postcode"):
            result["cod_postal_filter"] = context["postcode"]
        return result
    if query_style != "full_context":
        raise ValueError("unknown_pilot_query_style")
    # Keep official municipality spelling in the query rather than applying a
    # strict server filter that could silently discard an article/alias variant.
    return {"q": ", ".join(filter(None, (address, context.get("postcode"),
                context["locality"], context["province"]))), "countrycodes": "es", "limit": 33}


def project(payload):
    if not isinstance(payload, list) or len(payload) > 33 or any(not isinstance(x, dict) for x in payload):
        raise ValueError("cartociudad_schema_changed")
    return [{k: v for k, v in row.items() if k in FIELDS
             and (isinstance(v, (str, int, float, bool)) or v is None)} for row in payload]


def checks(context, row):
    """Candidate rank is not acceptance; independently compare source components."""
    source_pairs = s.address_parts(context["address"])
    returned_pairs = s.address_parts(row.get("address", ""))
    number = s.house_key(row.get("portalNumber"))
    extension = s.text(row.get("extension"))
    if extension:
        number = s.house_key(f"{number}{extension}")
    # Some responses use a road-only address plus a separate portalNumber.
    roads = {s.road_key(row.get("address")),
             s.road_key(f"{row.get('tip_via') or ''} {row.get('address') or ''}")}
    matching_pairs = source_pairs & returned_pairs
    street_number = (bool(number) and any(house == number for _, house in matching_pairs)
                     or bool(number) and any((road, number) in source_pairs for road in roads))
    lat, lon = row.get("lat"), row.get("lng")
    point = (all(isinstance(v, (int, float)) and not isinstance(v, bool)
                 and math.isfinite(v) for v in (lat, lon))
             and 27 <= lat <= 44.5 and -19 <= lon <= 5)
    postcode = context.get("postcode")
    return {"numbered_portal": row.get("type") == "portal"
                and row.get("noNumber") in (False, "false") and bool(number),
            "street_and_number": bool(street_number),
            "town": bool(s.locality_key(context["locality"])) and any(
                s.locality_key(context["locality"]) == s.locality_key(row.get(k))
                for k in ("muni", "poblacion")),
            "province": bool(s.province_key(context["province"])) and
                s.province_key(context["province"]) == s.province_key(row.get("province")),
            "postcode": not postcode or s.text(postcode) == s.text(row.get("postalCode")),
            "country": row.get("countryCode") in ("011", "ES", "es"),
            "coordinates": bool(point)}


def evaluate(context, rows):
    comparisons = [checks(context, row) for row in rows]
    viable = [i for i, compared in enumerate(comparisons) if all(compared.values())]
    return {"status": "matched" if len(viable) == 1 else "ambiguous" if viable else "unmatched",
            "matching_indices": viable, "candidate_count": len(rows), "checks": comparisons}


class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        if urllib.parse.urlsplit(newurl)[:2] != ("https", "www.cartociudad.es"):
            raise ValueError("cartociudad_redirect_out_of_scope")
        return super().redirect_request(request, response, code, message, headers, newurl)


def fetch(context, *, query_style="full_context", opener=None):
    url = ENDPOINT + "?" + urllib.parse.urlencode(parameters(context, query_style=query_style))
    request = urllib.request.Request(url, headers={
        "User-Agent": "UntilEveryCage/2 bounded-address-pilot", "Accept": "application/json"})
    opener = opener or urllib.request.build_opener(_SameOriginRedirect()).open
    with opener(request, timeout=30) as response:
        if urllib.parse.urlsplit(response.geturl())[:2] != ("https", "www.cartociudad.es"):
            raise ValueError("cartociudad_redirect_out_of_scope")
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("cartociudad_response_too_large")
    rows = project(json.loads(raw))
    return rows, hashlib.sha256(raw).hexdigest()


def run(cases, output, *, approved_root, query_style="full_context",
        opener=None, sleep=time.sleep):
    """Checkpoint before each request; an interrupted call is never auto-retried."""
    output, root = Path(output).resolve(), Path(approved_root).resolve()
    if output == root or not output.is_relative_to(root) or not 1 <= len(cases) <= 24:
        raise ValueError("pilot_scope_invalid")
    for case in cases:
        parameters(case["context"], query_style=query_style)
    output.mkdir(parents=True, exist_ok=True)
    if any(path.is_symlink() for path in [output/"private-plan.json", output/"attempts.jsonl",
                                         *(output/f"result-{i:02d}.json" for i in range(len(cases)))]):
        raise ValueError("pilot_checkpoint_symlink_rejected")
    plan_value = cases if query_style == "full_context" else {"query_style": query_style, "cases": cases}
    serialized = json.dumps(plan_value, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    plan = output / "private-plan.json"
    if plan.exists():
        if plan.read_text(encoding="utf-8") != serialized:
            raise ValueError("pilot_plan_changed")
    else:
        with plan.open("x", encoding="utf-8") as stream:
            stream.write(serialized)
    attempts = output / "attempts.jsonl"
    started = set()
    if attempts.exists():
        for line in attempts.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event["plan_sha256"] != digest:
                raise ValueError("pilot_attempt_plan_changed")
            started.add(event["case"])
    counts = Counter()
    for index, case in enumerate(cases):
        path = output / f"result-{index:02d}.json"
        if path.exists():
            previous = json.loads(path.read_text(encoding="utf-8"))
            if previous.get("plan_sha256") != digest or previous.get("case") != index:
                raise ValueError("pilot_result_plan_changed")
            counts[previous["evaluation"]["status"]] += 1
            continue
        if index in started:
            counts["interrupted_request_not_retried"] += 1
            continue
        sleep(1)
        with attempts.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"case": index, "plan_sha256": digest,
                "request_parameters": parameters(case["context"], query_style=query_style),
                "address_format_version": s.RULESET,
                "started_at": datetime.now(timezone.utc).isoformat()}) + "\n")
        try:
            rows, response_hash = fetch(case["context"], query_style=query_style, opener=opener)
            result = {"response_sha256": response_hash, "candidates": rows,
                      "evaluation": evaluate(case["context"], rows)}
        except (OSError, ValueError, TimeoutError) as error:
            result = {"evaluation": {"status": "request_failed"}, "error_type": type(error).__name__}
            if isinstance(error, urllib.error.HTTPError):
                result["http_status"] = error.code
        result.update(retrieved_at=datetime.now(timezone.utc).isoformat(), ruleset=RULESET,
                      plan_sha256=digest, case=index, query_style=query_style)
        with path.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, sort_keys=True)
        counts[result["evaluation"]["status"]] += 1
        if result.get("error_type") == "HTTPError":
            # No retries or additional traffic after an access/quota/server error.
            break
    report = {"provider": "cartociudad", "ruleset": RULESET, "cases": len(cases),
              "outcomes": dict(counts), "database_writes": 0, "points_imported": 0,
              "automatic_bulk_expansion": False, "query_style": query_style}
    return report


def retained_attempts(folder):
    """Read immutable local checkpoints; never rerun the outbound lookup."""
    folder = Path(folder)
    raw = (folder/"private-plan.json").read_text(encoding="utf-8")
    digest = hashlib.sha256(raw.encode()).hexdigest()
    plan = json.loads(raw)
    cases = plan if isinstance(plan, list) else plan["cases"]
    style = "full_context" if isinstance(plan, list) else plan["query_style"]
    if not 1 <= len(cases) <= 24:
        raise ValueError("retained_pilot_scope_invalid")
    for line in (folder/"attempts.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event["plan_sha256"] != digest or type(event["case"]) is not int or not 0 <= event["case"] < len(cases):
            raise ValueError("retained_pilot_attempt_mismatch")
        index = event["case"]
        parameters(cases[index]["context"], query_style=style)
        result_path = folder/f"result-{index:02d}.json"
        result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else None
        if result and (result.get("plan_sha256") != digest or result.get("case") != index):
            raise ValueError("retained_pilot_result_mismatch")
        yield cases[index], style, event, result


def import_attempt_history(connection, folders):
    """Backfill existing job/result/events, without reservations or map points."""
    from .first_pass import DATABASE, structured_query
    if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
        raise ValueError("wrong_source_test_database")
    namespace = uuid.UUID("7c24e676-13ca-423c-969b-267c1e085c6b")
    added = 0
    for folder in folders:
        for case, style, event, result in retained_attempts(folder):
            bound = []
            for target in case["targets"]:
                row = connection.execute("""SELECT location.location_evidence,verified.municipality,
                    verified.province,artifact.artifact_id,run.retrieved_at
                    FROM real_preview.candidates candidate
                    JOIN real_preview.candidate_private_location_evidence location
                      USING(candidate_id,snapshot_sha256,source_id)
                    JOIN real_preview.source_preview_runs run USING(snapshot_sha256,source_id)
                    JOIN uec.raw_artifacts artifact ON artifact.sha256=run.source_artifact_sha256
                    JOIN LATERAL(SELECT municipality,province FROM real_preview.spain_verified_locality_evidence v
                        WHERE v.candidate_id=candidate.candidate_id AND v.snapshot_sha256=candidate.snapshot_sha256
                          AND v.source_id=candidate.source_id ORDER BY retrieved_at DESC,evidence_event_id DESC LIMIT 1)verified ON true
                    WHERE candidate.candidate_id=%s AND candidate.snapshot_sha256=%s
                      AND candidate.source_group_key=%s AND candidate.source_id='es.locations'
                      AND candidate.country_code='ES' AND candidate.default_map_scope
                      AND candidate.snapshot_sha256=(SELECT snapshot_sha256 FROM real_preview.source_preview_runs
                        WHERE source_id='es.locations' ORDER BY created_at DESC,run_id DESC LIMIT 1)
                      AND NOT EXISTS(SELECT 1 FROM real_preview.enrichment_state_events state
                        WHERE state.candidate_id=candidate.candidate_id AND state.state_code='restricted')
                      AND NOT EXISTS(SELECT 1 FROM real_preview.geocode_targets t JOIN uec.geocode_jobs j USING(job_id)
                        JOIN uec.public_access_restricted restricted USING(source_record_id)
                        WHERE t.candidate_id=candidate.candidate_id)""",
                    (target["candidate_id"], target["snapshot_sha256"], target["source_record_key"])).fetchone()
                context = case["context"]
                if (target["source_id"] != "es.locations" or not row
                        or row[0].get("address") != context["address"] or row[1] != context["locality"]
                        or s.province_key(row[2]) != s.province_key(context["province"])
                        or (row[0].get("postal_code") or row[0].get("postcode") or None) != context.get("postcode")):
                    raise ValueError("retained_pilot_source_context_mismatch")
                bound.append((target, row))
            if not bound:
                raise ValueError("retained_pilot_has_no_bound_targets")
            target, row = bound[0]
            projection = f"real-preview:{target['snapshot_sha256']}:{target['source_record_key']}"
            fields = json.dumps({"projection": "real_preview_private_geocode_target", "snapshot_sha256": target["snapshot_sha256"]})
            connection.execute("""INSERT INTO uec.source_records(source_id,source_record_key,artifact_id,raw_fields,parsed_at)
                VALUES('es.locations',%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING""", (projection,row[3],fields,row[4]))
            record = connection.execute("""SELECT source_record_id FROM uec.source_records
                WHERE source_id='es.locations' AND source_record_key=%s AND artifact_id=%s AND raw_fields=%s::jsonb""",
                (projection,row[3],fields)).fetchone()
            if not record:
                raise ValueError("retained_pilot_source_record_mismatch")
            query = structured_query("es.locations", row[0], municipality=row[1])
            if query is None:
                raise ValueError("retained_pilot_source_query_invalid")
            # One job per query style preserves physical request provenance
            # without pretending a retrospective import reserved quota first.
            job_query = json.dumps({"source_context": json.loads(query), "query_style": style}, sort_keys=True)
            connection.execute("""INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                VALUES(%s,'cartociudad',%s) ON CONFLICT DO NOTHING""", (record[0],job_query))
            job = connection.execute("""SELECT job_id FROM uec.geocode_jobs
                WHERE source_record_id=%s AND provider_id='cartociudad' AND query=%s""", (record[0],job_query)).fetchone()[0]
            for target, _ in bound:
                connection.execute("""INSERT INTO real_preview.geocode_targets(job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                    VALUES(%s,%s,%s,'es.locations',%s) ON CONFLICT DO NOTHING""",
                    (job,target["candidate_id"],target["snapshot_sha256"],target["source_record_key"]))
            identity = f"{event['plan_sha256']}:{event['case']}"
            started = uuid.uuid5(namespace, identity+":started")
            confirmed_response = bool(result and (result.get("response_sha256") or result.get("http_status")))
            details = {"processing_mode": "cartociudad_pilot_checkpoint_import", "outbound_request_recorded": confirmed_response,
                       "retrospective_import": True, "plan_sha256": event["plan_sha256"], "query_style": style}
            connection.execute("""INSERT INTO uec.geocode_job_events(event_id,job_id,event_type,details,occurred_at)
                VALUES(%s,%s,'started',%s::jsonb,%s) ON CONFLICT DO NOTHING""", (started,job,json.dumps(details),event["started_at"]))
            if result is None:
                continue
            status = "review_required" if result["evaluation"]["status"] == "matched" else "unresolved"
            result_id = uuid.uuid5(namespace, identity+":result")
            inserted = connection.execute("""INSERT INTO uec.geocode_results(geocode_result_id,source_record_id,
                provider_id,query,precision,match_method,status,response,queried_at)
                VALUES(%s,%s,'cartociudad',%s,'unresolved','cartociudad_pilot_candidates_v1',%s,%s::jsonb,%s)
                ON CONFLICT DO NOTHING RETURNING geocode_result_id""",
                (result_id,record[0],job_query,status,json.dumps(result),result["retrieved_at"])).fetchone()
            added += int(inserted is not None)
            connection.execute("""INSERT INTO uec.geocode_job_events(event_id,job_id,event_type,details,occurred_at)
                VALUES(%s,%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING""",
                (uuid.uuid5(namespace, identity+":outcome"),job,status,json.dumps(details),result["retrieved_at"]))
    return {"result_rows_appended": added, "provider_calls": 0, "quota_reservations_added": 0, "points_imported": 0}
