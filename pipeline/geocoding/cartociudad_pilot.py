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
