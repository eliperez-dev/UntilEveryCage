"""Bounded first-party FSA coordinate-reference research, not a source import."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import time
import urllib.parse
import urllib.request

from pipeline.geocoding.geoapify import GeoapifyAdapter

BASE = "https://api.ratings.food.gov.uk/"
SOURCE_ID = "uk.fsa.fhrs.coordinate-reference"


def project(item):
    """Do not retain contacts, ratings, replies, scores or unrelated fields."""
    if not isinstance(item, dict) or not isinstance(item.get("geocode"), dict): return None
    try:
        latitude=float(item["geocode"]["latitude"]);longitude=float(item["geocode"]["longitude"])
    except (KeyError, TypeError, ValueError): return None
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not (49.8<=latitude<=60.9 and -8.7<=longitude<=2.1): return None
    if (not isinstance(item.get("FHRSID"),int) or isinstance(item["FHRSID"],bool)
            or not isinstance(item.get("BusinessName"),str) or not isinstance(item.get("PostCode"),str)):
        return None
    lines=[item.get(f"AddressLine{i}","") for i in range(1,5)]
    if any(not isinstance(line,str) for line in lines): return None
    return {"source_id":SOURCE_ID,"reference_id":item["FHRSID"],"name":item["BusinessName"],
            "address_lines":[line.strip() for line in lines if line.strip()],"postcode":item["PostCode"],
            "latitude":latitude,"longitude":longitude,"method":"first_party_published_coordinate"}


def fetch_manufacturers(*, progress=None, page_sink=None, opener=urllib.request.urlopen, sleep=time.sleep):
    """Fetch at most 15,000 manufacturing references; requests contain no facility data."""
    headers={"User-Agent":"UntilEveryCage/2 source-reference-review","x-api-version":"2","Accept":"application/json"}
    metadata=[];rows={};seen=set();expected=None;duplicate_rows=0;conflicts=set();received=0;projections={}
    def fetch(path):
        request=urllib.request.Request(BASE+path,headers=headers)
        with opener(request,timeout=30) as response:
            if urllib.parse.urlsplit(response.geturl()).hostname!="api.ratings.food.gov.uk":
                raise ValueError("fsa_reference_redirect_out_of_scope")
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise ValueError("fsa_reference_page_over_limit")
        payload=json.loads(raw)
        metadata.append({"source_url":BASE+path,"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)})
        return payload
    types=fetch("BusinessTypes")
    candidates=[row for row in types.get("businessTypes",[]) if row.get("BusinessTypeName")=="Manufacturers/packers"]
    if len(candidates)!=1:raise ValueError("fsa_reference_category_changed")
    type_id=candidates[0]["BusinessTypeId"]
    for page in range(1,62):
        sleep(1)
        payload=fetch("Establishments?"+urllib.parse.urlencode({"businessTypeId":type_id,"pageSize":250,"pageNumber":page,"sortOptionKey":"alpha"}))
        meta=payload.get("meta",{});items=payload.get("establishments")
        if not isinstance(items,list) or len(items)>250:raise ValueError("fsa_reference_page_schema_changed")
        if expected is None:expected=meta.get("totalCount")
        if not isinstance(expected,int) or not 0<=expected<=15000 or meta.get("totalCount")!=expected:
            raise ValueError("fsa_reference_count_outside_bounds_or_changed")
        for item in items:
            ident=item.get("FHRSID")
            if not isinstance(ident,int) or isinstance(ident,bool):raise ValueError("fsa_reference_identifier_invalid")
            received+=1
            if ident in seen:duplicate_rows+=1
            seen.add(ident)
            row=project(item)
            if ident in projections and row!=projections[ident]:
                conflicts.add(ident);rows.pop(ident,None)
            projections[ident]=row
            if row and ident not in conflicts:rows[ident]=row
        if page_sink:
            page_sink(page,[row for item in items if (row:=project(item)) is not None],metadata[-1])
        if progress and page%10==0:progress({"pages":page,"source_records":len(seen),"usable_reference_points":len(rows)})
        total_pages=meta.get("totalPages")
        if not isinstance(total_pages,int) or total_pages>61:raise ValueError("fsa_reference_pages_outside_bounds")
        if page>=total_pages:break
    return list(rows.values()),{"source_id":SOURCE_ID,"retrieved_at":datetime.now(timezone.utc).isoformat(),
        "source_records":len(seen),"published_total_records":expected,"source_rows_received":received,
        "duplicate_rows":duplicate_rows,"conflicting_ids_excluded":len(conflicts),
        "unique_count_matches_published_total":len(seen)==expected,"snapshot_atomic":False,
        "usable_reference_points":len(rows),"request_count":len(metadata),
        "requests":metadata,"raw_response_retained":False,"projection":"bounded_name_address_coordinate_reference_only"}


def exact_matches(primary, references):
    """Require exact name, full postcode and full address; no identity merges."""
    normalize=GeoapifyAdapter._normalize
    postcode=lambda value:re.sub(r"\s+","",value or "").upper()
    index=defaultdict(list)
    for row in references:
        if not row.get("name") or not row.get("postcode") or not row.get("address_lines"):continue
        key=(normalize(row["name"]),postcode(row["postcode"]),normalize(" ".join(row["address_lines"])))
        index[key].append(row)
    result={};ambiguous=0
    for row in primary:
        if not row.get("name") or not row.get("postcode") or not row.get("address_lines"):continue
        addresses={normalize(" ".join(row["address_lines"])),
                   normalize(" ".join([*row["address_lines"],row.get("city") or ""]))}
        found={ref["reference_id"]:ref for address in addresses
            for ref in index.get((normalize(row["name"]),postcode(row["postcode"]),address),[])}
        if len(found)==1:result[row["candidate_id"]]=next(iter(found.values()))
        elif found:ambiguous+=1
    return result,{"exact_name_postcode_full_address_matches":len(result),"ambiguous_matches":ambiguous}
