"""Read official CartoCiudad provincial archives for local first-pass matching.

No network calls or provider retries. Optional portal imports stay in the local
test database. Coordinates retain their native CRS and are transformed at import.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from decimal import Decimal
import hashlib
import math
from pathlib import Path
import re
import sqlite3
import struct
import tempfile
from urllib.parse import urlsplit, parse_qs
import zipfile

from . import spanish_addresses as s

MAX_ARCHIVE = 200 * 1024 * 1024
MAX_GPKG = 1024 * 1024 * 1024
MAX_POINTS = 3000000
FIELDS = ("id_porpk", "tipo", "tipo_vial", "nombre_via", "numero", "extension",
          "cod_postal", "municipio", "provincia", "fuente_datos", "fecha_modificacion", "geom")


def point_geometry(blob, srid):
    """Decode only standard, finite, nonempty 2D GeoPackage Point geometries."""
    if not isinstance(blob, bytes) or len(blob) < 29 or blob[:3] != b"GP\x00":
        raise ValueError("cartociudad_geometry_header")
    flags = blob[3]
    if flags & 0xE0 or flags & 0x10:
        raise ValueError("cartociudad_geometry_flags")
    envelope = (flags >> 1) & 7
    if envelope not in (0, 1):
        raise ValueError("cartociudad_geometry_dimensions")
    endian = "<" if flags & 1 else ">"
    if struct.unpack(endian + "i", blob[4:8])[0] != srid:
        raise ValueError("cartociudad_geometry_srid")
    offset = 8 + (32 if envelope else 0)
    if len(blob) != offset + 21 or blob[offset] not in (0, 1):
        raise ValueError("cartociudad_geometry_size")
    wkb_endian = "<" if blob[offset] == 1 else ">"
    if struct.unpack(wkb_endian + "I", blob[offset+1:offset+5])[0] != 1:
        raise ValueError("cartociudad_geometry_not_point")
    x, y = struct.unpack(wkb_endian + "dd", blob[offset+5:])
    if not math.isfinite(x) or not math.isfinite(y) or not -19 <= x <= 5 or not 27 <= y <= 44.5:
        raise ValueError("cartociudad_geometry_out_of_bounds")
    return x, y


def read_archive(archive, *, province, source_url, retrieved_at, expected_sha256,
                 municipalities=None, include_kilometres=False, matching_inputs=None):
    """Validate one bounded archive and preserve source identities privately."""
    url = urlsplit(source_url)
    if (url.scheme != "https" or url.netloc != "centrodedescargas.cnig.es"
            or url.path != "/CentroDescargas/detalleArchivo"
            or set(parse_qs(url.query)) != {"sec"}
            or len(parse_qs(url.query)["sec"]) != 1
            or not parse_qs(url.query)["sec"][0].isdigit()
            or not province or not retrieved_at):
        raise ValueError("cartociudad_provenance_invalid")
    wanted_towns = None if municipalities is None else {s.locality_key(v) for v in municipalities if v}
    if wanted_towns is not None and (len(wanted_towns) > 10000 or
            (not wanted_towns and matching_inputs != [])):
        raise ValueError("cartociudad_municipality_scope")
    portals, distances = {}, set()
    if matching_inputs is not None:
        if not 0 <= len(matching_inputs) <= 10000:
            raise ValueError("cartociudad_comparison_scope")
        for item in matching_inputs:
            context = item["context"]
            town = s.locality_key(context["locality"])
            if s.input_kind(context["address"]) not in {"explicit_no_number", "road_distance"}:
                for road, house in s.address_parts(context["address"]):
                    portals.setdefault((town, house), set()).add(road)
            distance = kilometre_address(context["address"])
            if distance:
                distances.add((town, *distance))
    archive = Path(archive)
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE:
        raise ValueError("cartociudad_archive_limit")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise ValueError("cartociudad_archive_digest")
    counts, references, seen = Counter(), [], set()
    with zipfile.ZipFile(archive) as bundle:
        packages = [i for i in bundle.infolist() if i.filename.lower().endswith(".gpkg")]
        if len(packages) != 1 or not 0 < packages[0].file_size <= MAX_GPKG:
            raise ValueError("cartociudad_package_limit")
        # Never extract a supplied member path or execute package SQL/extensions.
        with tempfile.TemporaryDirectory(prefix="uec-carto-") as scratch:
            target = Path(scratch) / "reference.gpkg"
            with bundle.open(packages[0]) as src, target.open("xb") as dst:
                total = 0
                while block := src.read(1024 * 1024):
                    total += len(block)
                    if total > MAX_GPKG or total > packages[0].file_size:
                        raise ValueError("cartociudad_expansion_limit")
                    dst.write(block)
            with closing(sqlite3.connect(target.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
                db.execute("PRAGMA trusted_schema=OFF")
                db.execute("PRAGMA query_only=ON")
                ticks = 0
                def bounded():
                    nonlocal ticks
                    ticks += 1
                    return int(ticks > 20000)
                db.set_progress_handler(bounded, 10000)
                geometry = db.execute("SELECT column_name,geometry_type_name,srs_id,z,m "
                    "FROM gpkg_geometry_columns WHERE table_name='portalpk_publi'").fetchall()
                if len(geometry) != 1 or geometry[0] not in (("geom", "POINT", 4258, 0, 0), ("geom", "POINT", 4081, 0, 0)):
                    raise ValueError("cartociudad_geometry_schema")
                srid = geometry[0][2]
                canary_province = s.province_key(province) in {"laspalmas", "santacruzdetenerife"}
                if (srid == 4081) != canary_province:
                    raise ValueError("cartociudad_crs_province_conflict")
                declared = db.execute("SELECT organization,organization_coordsys_id FROM gpkg_spatial_ref_sys WHERE srs_id=?", (srid,)).fetchall()
                if declared != [("EPSG", srid)]:
                    raise ValueError("cartociudad_crs_definition")
                columns = {r[1] for r in db.execute("PRAGMA table_info(portalpk_publi)")}
                if not set(FIELDS).issubset(columns):
                    raise ValueError("cartociudad_address_schema")
                for row in db.execute("SELECT " + ",".join(FIELDS) + " FROM portalpk_publi"):
                    counts["source_points"] += 1
                    if counts["source_points"] > MAX_POINTS:
                        raise ValueError("cartociudad_point_limit")
                    ident, kind, road_type, road, number, extension, postcode, town, prov, provider, date, blob = row
                    if not ident or ident in seen or s.province_key(prov) != s.province_key(province):
                        raise ValueError("cartociudad_identity_or_province")
                    seen.add(ident)
                    if kind == "PK de vía de servicio":
                        counts["service_road_kilometre_points_excluded"] += 1
                        continue
                    if kind not in {"Portal", "PK"}:
                        raise ValueError("cartociudad_unknown_point_type")
                    if kind == "PK" and not include_kilometres:
                        counts["kilometre_points_excluded"] += 1
                        continue
                    if wanted_towns is not None and s.locality_key(town) not in wanted_towns:
                        counts["other_municipality_portals"] += 1
                        continue
                    house = s.house_key(str(number or "") + str(extension or "")) if kind == "Portal" else None
                    km = kilometre_key(number) if kind == "PK" and not extension else None
                    if kind == "Portal" and (not house or int(re.match(r"[0-9]+", house)[0]) == 0):
                        counts["unnumbered_or_complex_portals"] += 1
                        continue
                    if kind == "PK" and km is None:
                        counts["complex_kilometre_points_excluded"] += 1
                        continue
                    if not road_type or not road or not town:
                        counts["incomplete_portals"] += 1
                        continue
                    if matching_inputs is not None:
                        road_key = s.road_key(str(road_type) + " " + str(road))
                        town_key = s.locality_key(town)
                        if kind == "Portal" and not any(s.road_keys_match(key, road_key)
                                for key in portals.get((town_key, house), ())):
                            counts["other_address_portals"] += 1
                            continue
                        if kind == "PK" and (town_key, road_key, km) not in distances:
                            counts["other_road_kilometre_points"] += 1
                            continue
                    x, y = point_geometry(blob, srid)
                    if srid == 4081 and not (-19 <= x <= -13 and 27 <= y <= 30):
                        raise ValueError("cartociudad_canary_geometry_out_of_bounds")
                    references.append({"reference_id": ["ES.SCNE.CARTOCIUDAD", str(ident)],
                        "street": str(road_type) + " " + str(road), "house": house,
                        "point_kind": "portal" if kind == "Portal" else "kilometre", "kilometre": km,
                        "municipality": town, "province": prov, "postcode": postcode,
                        "provider": provider, "source_date": date,
                        "longitude": x, "latitude": y, "crs": f"EPSG:{srid}"})
    return references, {**counts, "numbered_reference_points": sum(r["point_kind"] == "portal" for r in references),
        "kilometre_reference_points": sum(r["point_kind"] == "kilometre" for r in references),
        "archive_sha256": digest, "source_url": source_url, "retrieved_at": retrieved_at,
        "province": province, "crs": f"EPSG:{srid}", "provider_calls": 0,
        "address_normalization_ruleset": s.RULESET,
        "facility_addresses_sent": False, "points_imported": 0,
        "attribution": "Obra derivada de CartoCiudad CC-BY 4.0 scne.es"}


def kilometre_key(value):
    raw = str(value).strip() if isinstance(value, (str, int)) and not isinstance(value, bool) else ""
    if re.fullmatch(r"[0-9]{1,4}(?:[.,][0-9]{1,3})?", raw) is None:
        return None
    number = Decimal(raw.replace(",", "."))
    return format(number.normalize(), "f") if 0 <= number <= 3000 else None


def kilometre_address(source):
    """Read one explicit road/km pair; no interpolation or rounding."""
    if not isinstance(source, str) or len(source) > 1200:
        return None
    found = re.fullmatch(r"\s*(?:carretera|ctra\.?|cr\.?|ct\.?)\s+([^,;]+?)\s*[,;]?\s+"
        r"(?:km\.?|p\.?\s*k\.?|punto\s+kilom[eé]trico)\s*([0-9]{1,4}(?:[.,][0-9]{1,3})?)\s*", source, re.I)
    if not found or re.search(r"\b(?:km|kilometro|kilometrico|p k)\b", s.text(found[1])):
        return None
    km = kilometre_key(found[2])
    return (s.road_key("carretera " + found[1]), km) if km is not None else None


def kilometre_matches(primary, references):
    """Find unique source road/km references, always approximate facility locations."""
    index = {}
    for row in references:
        if row.get("point_kind") != "kilometre":
            continue
        key = (s.locality_key(row["municipality"]), s.province_key(row["province"]),
               s.road_key(row["street"]), row["kilometre"])
        index.setdefault(key, []).append(row)
    matches, eligible, ambiguous = {}, 0, 0
    for item in primary:
        context = item["context"]
        parsed = kilometre_address(context["address"])
        if parsed is None:
            continue
        eligible += 1
        rows = index.get((s.locality_key(context["locality"]), s.province_key(context["province"]), *parsed), [])
        rows = [r for r in rows if not context.get("postcode") or s.text(context["postcode"]) == s.text(r["postcode"])]
        if len(rows) == 1:
            matches[item["case_id"]] = {**rows[0], "match_precision": "approximate_road_kilometre_reference"}
        elif rows:
            ambiguous += 1
    return matches, {"checked": len(primary), "explicit_road_kilometre_pairs": eligible,
        "matched": len(matches), "ambiguous": ambiguous, "provider_calls": 0, "points_imported": 0}


def plan_comparison(connection, province):
    """Read current unattempted targets; retain source-bound province evidence.

    Commercial queries use a broader autonomous-community region. Do not treat
    that region as a province or invent one from a town-name guess.
    """
    import json
    from . import first_pass
    groups, _ = first_pass.plan(connection, ["es.locations"])
    provinces = {(str(candidate), str(snapshot).strip()): value for candidate, snapshot, value
        in connection.execute("""SELECT DISTINCT ON(candidate_id,snapshot_sha256)
            candidate_id,snapshot_sha256,province FROM real_preview.spain_verified_locality_evidence
            ORDER BY candidate_id,snapshot_sha256,retrieved_at DESC,evidence_event_id DESC""")}
    primary, missing = [], 0
    for group in groups:
        values = {provinces.get((str(row[0]), str(row[1]).strip())) for row in group["targets"]}
        if None in values or len(values) != 1:
            missing += 1
            continue
        value = next(iter(values))
        if s.province_key(value) != s.province_key(province):
            continue
        query = json.loads(group["query"])
        if not query.get("locality"):
            missing += 1
            continue
        primary.append({"case_id": hashlib.sha256((group["source"]+group["query"]).encode()).hexdigest(),
            "source": group["source"], "query": group["query"],
            "context": {"address": query["address"], "locality": query["locality"],
                        "province": value, "postcode": query.get("postcode")},
            "targets": [{"candidate_id": str(row[0]), "snapshot_sha256": str(row[1]).strip(),
                         "source_record_key": row[3], "source_record_id": str(row[6]) if row[6] else None}
                        for row in group["targets"]]})
    return primary, {"unattempted_groups_all_provinces": len(groups),
        "selected_province_groups": len(primary), "missing_verified_context_groups": missing}


def apply_portal_matches(connection, primary, matches, archive):
    """Append validated portal evidence using shared result/job tables only."""
    import json
    import uuid
    from .first_pass import DATABASE
    if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
        raise ValueError("wrong_source_test_database")
    connection.execute("SELECT pg_advisory_xact_lock(hashtext('country-first-pass-staging'))")
    current, _ = plan_comparison(connection, archive["province"])
    current = {item["case_id"]: item for item in current}
    inserted = projected = stale = 0
    for item in primary:
        reference = matches.get(item["case_id"])
        if reference is None:
            continue
        fresh = current.get(item["case_id"])
        if fresh is None:
            stale += 1
            continue
        if (fresh["query"] != item["query"] or reference.get("point_kind") != "portal"
                or any(target["source_record_id"] is None for target in fresh["targets"])):
            raise ValueError("cartociudad_source_binding_changed")
        record = fresh["targets"][0]["source_record_id"]
        job = connection.execute("""INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
            VALUES(%s,'cartociudad_local',%s) ON CONFLICT(source_record_id,provider_id,query)
            DO NOTHING RETURNING job_id""", (record, fresh["query"])).fetchone()
        if job is None:
            raise ValueError("cartociudad_job_already_exists")
        job = job[0]
        for target in fresh["targets"]:
            connection.execute("""INSERT INTO real_preview.geocode_targets(job_id,candidate_id,snapshot_sha256,
                source_id,source_record_key) VALUES(%s,%s,%s,'es.locations',%s)""",
                (job,target["candidate_id"],target["snapshot_sha256"],target["source_record_key"]))
        connection.execute("""INSERT INTO uec.geocode_job_events(job_id,event_type,retryable,details)
            VALUES(%s,'queued',false,'{"processing_mode":"cartociudad_local_portal_v1","outbound_request_sent":false}')""", (job,))
        result = uuid.uuid5(uuid.NAMESPACE_URL, f"cartociudad-local:{record}:{archive['archive_sha256']}:{fresh['query']}")
        response = {"ruleset":"cartociudad-local-portal-v1", "unique_reference_count":1,
                    "archive":archive,"selected":reference}
        srid = {"EPSG:4258":4258,"EPSG:4081":4081}[reference["crs"]]
        connection.execute("""INSERT INTO uec.geocode_results(geocode_result_id,source_record_id,
            provider_id,provider_version,query,provider_address_id,result,precision,match_method,
            status,attempt_number,retryable,response,queried_at)
            VALUES(%s,%s,'cartociudad_local','cartociudad-local-portal-v1',%s,%s,
            ST_Transform(ST_SetSRID(ST_MakePoint(%s,%s),%s),4326)::geography,
            'government_reference_address_point','cartociudad_local_portal_v1','accepted',1,false,%s::jsonb,now())""",
            (result,record,fresh["query"],reference["reference_id"][1],reference["longitude"],
             reference["latitude"],srid,json.dumps(response,ensure_ascii=False)))
        count = connection.execute("SELECT count(*) FROM real_preview.geocode_display_evidence WHERE geocode_result_id=%s", (result,)).fetchone()[0]
        if count != len(fresh["targets"]):
            raise ValueError("cartociudad_independent_projection_rejected")
        connection.execute("""INSERT INTO uec.geocode_job_events(job_id,event_type,retryable,details)
            VALUES(%s,'accepted',false,%s::jsonb)""", (job,json.dumps({"processing_mode":"cartociudad_local_portal_v1",
                "outbound_request_sent":False,"geocode_result_id":str(result),"first_pass_only":True})))
        inserted += 1
        projected += count
    return {"local_results_appended":inserted,"display_evidence_appended":projected,
            "stale_or_previously_completed_groups_skipped":stale,"provider_calls":0,
            "quota_reservations_created":0,"failed_addresses_retried":0}


def main():
    import argparse
    from datetime import datetime, timezone
    import json
    import os
    import psycopg
    from .spanish_address_reference import exact_matches
    from pipeline.scripts.release_baseline import load_contract, verify_connection
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--province", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply-portals", action="store_true",
                        help="Append validated numbered portals locally; kilometre matches remain research only")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((root/"data/staging").resolve()) or output.is_symlink() or output.exists():
        raise ValueError("cartociudad_private_output_invalid_or_exists")
    observed = datetime.fromisoformat(args.retrieved_at.replace("Z", "+00:00"))
    if observed.tzinfo is None or observed > datetime.now(timezone.utc):
        raise ValueError("cartociudad_retrieval_date_invalid")
    contract = load_contract(root/"pipeline/contracts/development-baseline.json")
    with psycopg.connect(os.environ["UEC_DATABASE_URL"], options="-c statement_timeout=90000") as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        verify_connection(connection, contract)
        primary, planned = plan_comparison(connection, args.province)
        references, captured = read_archive(args.archive, province=args.province, source_url=args.source_url,
            retrieved_at=args.retrieved_at, expected_sha256=args.sha256,
            municipalities={row["context"]["locality"] for row in primary}, include_kilometres=True,
            matching_inputs=primary)
        matches, compared = exact_matches(primary, references)
        distance_matches, distance_compared = kilometre_matches(primary, references)
        verify_connection(connection, contract)
    applied = {"local_results_appended":0,"display_evidence_appended":0}
    if args.apply_portals and matches:
        with psycopg.connect(os.environ["UEC_DATABASE_URL"], options="-c statement_timeout=90000") as connection:
            verify_connection(connection, contract)
            applied = apply_portal_matches(connection, primary, matches, captured)
            verify_connection(connection, contract)
    summary = {"plan": planned, "archive": captured, "comparison": compared, "kilometre_comparison": distance_compared,
        "matched_record_targets": sum(len(row["targets"]) for row in primary if row["case_id"] in matches),
        "v0_baseline": "verified_unchanged", "applied":applied,
        "queue_attempts_created": applied["local_results_appended"], "deployed": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"summary": summary, "primary": primary, "matches": matches,
                   "kilometre_matches": distance_matches}, stream, ensure_ascii=False)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Exception messages may contain source values. Aggregate errors only.
        import json
        print(json.dumps({"status": "blocked", "error_type": type(error).__name__,
                          "sqlstate": getattr(error, "sqlstate", None)}))
        raise SystemExit(1)
