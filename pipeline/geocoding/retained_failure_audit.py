"""Read-only, address-free diagnosis of retained UK/Catalonia lookup failures."""
from collections import Counter
import json
import os
from pathlib import Path
import re

from .locationiq import LocationIqAdapter
from . import spanish_addresses as spanish

SOURCES = ("fsa_approved_establishments", "fss_approved_establishments", "es.cat.feed-sandach")


class _Response:
    def __init__(self, payload): self.payload=json.dumps(payload).encode("utf-8")
    def __enter__(self): return self
    def __exit__(self,*_): return False
    def read(self,size=-1): return self.payload if size<0 else self.payload[:size]


def diagnose(query, response, country):
    """Return only reason codes and booleans; never return source/provider text."""
    structured=isinstance(query,str) and query.lstrip().startswith("{")
    parsed=LocationIqAdapter._parse_first_pass_query(query,country) if structured else None
    if not structured and country=="gb":
        legacy=LocationIqAdapter._parse_gb_query(query)
        if legacy:
            road,number,town,postcode=legacy
            parsed=(f"{number} {road}",town,postcode,None,query)
    if parsed is None:
        return {"reason":"invalid_stored_query"}
    address,town,postcode,region,_=parsed
    facts={"query_has_locality":bool(town),"query_has_postcode":bool(postcode),
           "source_has_explicit_numbered_road":bool(spanish.address_parts(address)) if country=="es" else bool(
               LocationIqAdapter.canonical_uk_query(address.split(","),town or "placeholder",postcode or "SW1A 1AA"))}
    payload=response.get("results") if isinstance(response,dict) else None
    if not isinstance(payload,list): return {**facts,"reason":"response_evidence_not_retained"}
    if not payload: return {**facts,"reason":"provider_returned_no_results"}
    adapter=LocationIqAdapter(api_key="offline-placeholder",country_code=country,
        private_source_profile=True,query_kind="source_address_first_pass" if structured else None,
        first_pass_source=structured,opener=lambda *_a,**_k:_Response(payload))
    outcome=adapter.geocode(query)
    if outcome.status=="accepted": return {**facts,"reason":"matches_current_rules"}
    if outcome.acceptance=="ambiguous_multiple_viable_results": return {**facts,"reason":"multiple_matching_addresses"}
    numbered=[]; street=[]; context=[]; returned_types=set(); context_checks=[]
    town_agrees=postcode_agrees=region_agrees=False
    normalize=LocationIqAdapter._normalize
    for item in payload[:2]:
        a=item.get("address",{}) if isinstance(item,dict) else {}
        if isinstance(item,dict):
            # Fixed buckets only: provider labels must never become report keys.
            result_type=str(item.get("addresstype") or item.get("type") or "").lower()
            returned_types.add(result_type if result_type in {"postcode","road","city","town","village","municipality"} else "other")
        if not a.get("road") or not a.get("house_number"): continue
        numbered.append(item)
        matches=(spanish.street_matches(address,a.get("road"),a.get("house_number")) if country=="es" else
                 LocationIqAdapter._first_pass_address_matches(address,a.get("road"),a.get("house_number")))
        if not matches: continue
        street.append(item)
        localities=[a.get(k) for k in ("city","town","municipality","village","suburb")]
        town_match=(not town and country=="gb" and bool(postcode)) or any(
            (spanish.locality_key(v)==spanish.locality_key(town) if country=="es" else normalize(str(v))==normalize(town))
            for v in localities if v and town)
        postcode_match=not postcode or re.sub(r"\s+","",str(a.get("postcode") or "")).upper()==re.sub(r"\s+","",postcode).upper()
        region_match=(spanish.province_matches(a,region,postcode) if country=="es" else not region or any(
            normalize(str(a.get(k) or ""))==normalize(region) for k in ("state","state_code","county")))
        town_agrees |= bool(town_match); postcode_agrees |= bool(postcode_match); region_agrees |= bool(region_match)
        context_checks.append((bool(town_match),bool(postcode_match),bool(region_match)))
        if town_match and postcode_match and region_match: context.append(item)
    facts.update(response_has_numbered_road=bool(numbered),response_has_matching_street_house=bool(street))
    if not numbered:
        for kind in returned_types:facts[f"no_number_response_includes_{kind}"]=True
    if street:
        facts.update(matching_street_with_town_agreement=town_agrees,
                     matching_street_with_postcode_agreement=postcode_agrees,
                     matching_street_with_region_agreement=region_agrees)
    reason=("provider_returned_no_numbered_road" if not numbered else
            "returned_street_or_number_differs" if not street else
            "returned_locality_postcode_or_region_differs" if not context else
            "result_type_country_or_coordinates_rejected")
    if reason=="returned_locality_postcode_or_region_differs":
        best=max(context_checks,key=lambda flags:(sum(flags),flags))
        mismatch="_and_".join(label for label,matched in zip(("town","postcode","region"),best) if not matched)
        facts[f"best_matching_street_context_differs_{mismatch}"]=True
    return {**facts,"reason":reason}


def audit(connection):
    if connection.execute("SELECT current_database()").fetchone()[0]!="uec_launch_sources_test_20261025":
        raise ValueError("wrong_disposable_database")
    rows=connection.execute("""WITH latest AS MATERIALIZED (
        SELECT DISTINCT ON(source_id) source_id,snapshot_sha256 FROM real_preview.source_preview_runs
        WHERE source_id=ANY(%s) ORDER BY source_id,created_at DESC,run_id DESC),
      jobs AS MATERIALIZED (
        SELECT DISTINCT t.source_id,j.job_id,j.source_record_id,j.provider_id,j.query
        FROM real_preview.geocode_targets t JOIN uec.geocode_jobs j USING(job_id)
        JOIN real_preview.candidates c ON c.source_id=t.source_id AND c.source_group_key=t.source_record_key
        JOIN latest l ON l.source_id=c.source_id AND l.snapshot_sha256=c.snapshot_sha256
        WHERE EXISTS(SELECT 1 FROM uec.geocode_request_reservations reservation WHERE reservation.job_id=j.job_id)
          AND NOT EXISTS(SELECT 1 FROM uec.public_access_restricted restricted WHERE restricted.source_record_id=j.source_record_id)
          AND NOT EXISTS(SELECT 1 FROM real_preview.enrichment_state_events e WHERE e.candidate_id=c.candidate_id AND e.state_code='restricted'))
      SELECT j.source_id,j.provider_id,j.query,r.status,r.response FROM jobs j
      JOIN LATERAL(SELECT r.status,r.response FROM uec.geocode_results r
        WHERE r.source_record_id=j.source_record_id AND r.provider_id=j.provider_id AND r.query=j.query
          AND coalesce(r.match_method,'') NOT IN ('locationiq_query_diagnostic_v1','geoapify_query_diagnostic_v1')
        ORDER BY r.queried_at DESC,r.geocode_result_id DESC LIMIT 1) r ON true
      WHERE r.status<>'accepted' AND NOT EXISTS(
        SELECT 1 FROM uec.geocode_results accepted WHERE accepted.source_record_id=j.source_record_id
          AND accepted.provider_id=j.provider_id AND accepted.query=j.query AND accepted.status='accepted')
      ORDER BY j.source_id,j.job_id""",(list(SOURCES),)).fetchall()
    reports={}
    for source,provider,query,status,response in rows:
        counter=reports.setdefault(source,Counter())
        counter["lookup_jobs_examined"]+=1
        if provider!="locationiq":
            counter["other_provider_failures_without_equivalent_retained_address_evidence"]+=1
            continue
        result=diagnose(query,response,"es" if source.startswith("es.") else "gb")
        counter["locationiq_failures_examined"]+=1
        counter[result["reason"]]+=1
        for field,value in result.items():
            if isinstance(value,bool):counter[field]+=int(value)
    return {"sources":{s:dict(c) for s,c in reports.items()},"provider_calls":0,"database_writes":0,
            "basis":"Latest failed outcome per requested lookup job; historical retries and providers may represent the same facility"}


if __name__=="__main__":
    import psycopg
    from pipeline.scripts.release_baseline import load_contract, validate_database_url, verify_connection
    try:
        url=os.environ["UEC_DATABASE_URL"]
        validate_database_url(url)
        with psycopg.connect(url) as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            connection.execute("SET LOCAL statement_timeout='60s'")
            baseline=verify_connection(connection,load_contract(Path(__file__).parents[2]/"pipeline/contracts/development-baseline.json"))
            report=audit(connection)
            report["baseline"]=baseline["status"]
            print(json.dumps(report,sort_keys=True))
    except Exception as error:
        print(json.dumps({"status":"failed","error_type":type(error).__name__}))
        raise SystemExit(1)
