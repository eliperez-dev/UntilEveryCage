"""Bounded IGN municipality address references for local comparison only.

Requests contain a municipality and optional province, never facility addresses.
Reference files are private research inputs, not a new public source or import.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

from . import spanish_addresses as s

ENDPOINT = "https://api-features.idee.es/collections/address/items"
LICENCE = "https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf"
FIELDS = ("inspireId_localId", "inspireId_namespace", "component_ThoroughfareName",
          "locator_designator_addressNumber", "locator_designator_addressNumberExtension",
          "component_PostalDescriptor", "component_AddressAreaName",
          "component_AdminUnitName_4", "component_AdminUnitName_3",
          "beginLifespanVersion", "dataProvider")


class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        if urllib.parse.urlsplit(newurl)[:2] != ("https", "api-features.idee.es"):
            raise ValueError("ign_reference_redirect_out_of_scope")
        return super().redirect_request(request, response, code, message, headers, newurl)


def feature_identity(feature):
    props = feature["properties"]
    # OGC API serializes its configured identifier as top-level GeoJSON id,
    # omitting the same property even when explicitly requested.
    ident = props.get("inspireId_localId") or feature.get("id")
    if (not isinstance(ident, (str, int)) or isinstance(ident, bool) or not str(ident).strip()
            or not isinstance(props.get("inspireId_namespace"), str) or not props["inspireId_namespace"]):
        raise ValueError("ign_reference_identity_missing")
    return props["inspireId_namespace"], str(ident)


def project(feature):
    """Retain only the numbered address reference and its provenance."""
    if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
        raise ValueError("ign_reference_feature_invalid")
    props, geometry = feature["properties"], feature.get("geometry")
    for key in FIELDS:
        if props.get(key) is not None and not isinstance(props[key], str):
            raise ValueError("ign_reference_property_type_changed")
    identity = feature_identity(feature)
    if any(not props.get(key) for key in ("component_AdminUnitName_4", "component_AdminUnitName_3")):
        raise ValueError("ign_reference_identity_missing")
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        return None
    xy = geometry.get("coordinates")
    if (not isinstance(xy, list) or len(xy) != 2
            or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in xy)
            or not -19 <= xy[0] <= 5 or not 27 <= xy[1] <= 44.5):
        return None
    house = s.house_key((props.get("locator_designator_addressNumber") or "")
                        + (props.get("locator_designator_addressNumberExtension") or ""))
    if not house or int(re.match(r"[0-9]+", house)[0]) == 0 or not props.get("component_ThoroughfareName"):
        return None
    return {"reference_id": list(identity),
            "street": props["component_ThoroughfareName"], "house": house,
            "municipality": props["component_AdminUnitName_4"],
            "province": props["component_AdminUnitName_3"],
            "postcode": props.get("component_PostalDescriptor"),
            "provider": props.get("dataProvider"), "source_date": props.get("beginLifespanVersion"),
            "longitude": xy[0], "latitude": xy[1]}


def fetch_municipality(municipality, output, *, approved_root, province=None,
                       max_records=10000, page_size=1000, opener=None, sleep=time.sleep):
    """Checkpoint bounded pages. Reuse them without issuing duplicate requests."""
    if (not isinstance(municipality, str) or not municipality.strip() or len(municipality) > 160
            or province is not None and (not isinstance(province, str) or not province.strip() or len(province) > 160)
            or not 1 <= max_records <= 10000 or not 1 <= page_size <= 1000):
        raise ValueError("ign_reference_scope_invalid")
    output, root = Path(output).resolve(), Path(approved_root).resolve()
    if output == root or not output.is_relative_to(root):
        raise ValueError("ign_reference_output_out_of_scope")
    output.mkdir(parents=True, exist_ok=True)
    plan = {"municipality": municipality, "province": province,
            "max_records": max_records, "page_size": page_size}
    serialized = json.dumps(plan, ensure_ascii=False, sort_keys=True)
    plan_path = output / "private-plan.json"
    if plan_path.is_symlink():
        raise ValueError("ign_reference_checkpoint_symlink_rejected")
    if plan_path.exists():
        if plan_path.read_text(encoding="utf-8") != serialized:
            raise ValueError("ign_reference_plan_changed")
    else:
        with plan_path.open("x", encoding="utf-8") as stream:
            stream.write(serialized)
    opener = opener or urllib.request.build_opener(_SameOriginRedirect()).open
    expected = None
    references, seen, requests = {}, set(), []
    for page in range(12):
        offset = page * page_size
        params = {"f": "json", "limit": page_size, "offset": offset,
                  "component_AdminUnitName_4": municipality, "sortby": "inspireId_localId",
                  "properties": ",".join(FIELDS)}
        if province:
            params["component_AdminUnitName_3"] = province
        url = ENDPOINT + "?" + urllib.parse.urlencode(params)
        path = output / f"page-{offset:05d}.json"
        if path.is_symlink():
            raise ValueError("ign_reference_checkpoint_symlink_rejected")
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("source_url") != url:
                raise ValueError("ign_reference_checkpoint_query_changed")
            payload = saved["payload"]
            canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
            if saved.get("payload_sha256") != hashlib.sha256(canonical).hexdigest():
                raise ValueError("ign_reference_checkpoint_content_changed")
        else:
            sleep(1)
            request = urllib.request.Request(url, headers={"Accept": "application/geo+json",
                "User-Agent": "UntilEveryCage/2 bounded-municipality-reference"})
            with opener(request, timeout=45) as response:
                if urllib.parse.urlsplit(response.geturl())[:2] != ("https", "api-features.idee.es"):
                    raise ValueError("ign_reference_redirect_out_of_scope")
                raw = response.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise ValueError("ign_reference_page_over_limit")
            payload = json.loads(raw)
            saved = {"source_url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                     "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "payload": payload,
                     "payload_sha256": hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
            with path.open("x", encoding="utf-8") as stream:
                json.dump(saved, stream, ensure_ascii=False, sort_keys=True)
        requests.append({k: saved[k] for k in ("source_url", "retrieved_at", "sha256", "bytes")})
        count = payload.get("numberMatched")
        if type(count) is not int or not 0 <= count <= max_records:
            raise ValueError("ign_reference_count_outside_bounds")
        if expected is None:
            expected = count
        if count != expected:
            raise ValueError("ign_reference_count_changed")
        features = payload.get("features")
        if (not isinstance(features, list) or len(features) > page_size
                or payload.get("numberReturned") != len(features)):
            raise ValueError("ign_reference_page_schema_changed")
        for feature in features:
            row = project(feature)
            props = feature["properties"]
            identity = feature_identity(feature)
            if identity in seen:
                raise ValueError("ign_reference_duplicate_id")
            seen.add(identity)
            if (s.locality_key(props["component_AdminUnitName_4"]) != s.locality_key(municipality)
                    or province and s.province_key(props["component_AdminUnitName_3"]) != s.province_key(province)):
                raise ValueError("ign_reference_geographic_filter_ignored")
            if row:
                references[identity] = row
        if len(seen) == expected:
            break
        if not features or len(seen) > expected:
            raise ValueError("ign_reference_pagination_incomplete")
    if len(seen) != expected:
        raise ValueError("ign_reference_pagination_incomplete")
    return list(references.values()), {"source_records": len(seen), "numbered_reference_points": len(references),
        "pages": len(requests), "requests": requests, "snapshot_atomic": False, "licence": LICENCE,
        "facility_addresses_sent": False, "points_imported": 0}


def exact_matches(primary, references):
    """Local unique street/house/town/province matching; no geometry writes."""
    index = defaultdict(list)
    for row in references:
        index[(s.locality_key(row["municipality"]), s.province_key(row["province"]), row["house"])].append(row)
    matches, ambiguous = {}, 0
    for item in primary:
        context = item["context"]
        if s.input_kind(context["address"]) in {"explicit_no_number", "road_distance"}:
            continue
        found = {}
        for road, house in s.address_parts(context["address"]):
            key = (s.locality_key(context["locality"]), s.province_key(context["province"]), house)
            for row in index.get(key, []):
                if not s.road_keys_match(road, s.road_key(row["street"])):
                    continue
                if context.get("postcode") and s.text(context["postcode"]) != s.text(row.get("postcode")):
                    continue
                found[tuple(row["reference_id"])] = row
        if len(found) == 1:
            matches[item["case_id"]] = next(iter(found.values()))
        elif found:
            ambiguous += 1
    return matches, {"checked": len(primary), "matched": len(matches), "ambiguous": ambiguous,
                     "provider_calls": 0, "points_imported": 0}
