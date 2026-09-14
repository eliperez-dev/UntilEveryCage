"""FSA approved-establishments adapter for synthetic and monthly source profiles."""
from __future__ import annotations
import csv, hashlib, json, os, re, tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT=Path(__file__).parent
CONFIG=json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
REQUIRED_COLUMNS=tuple(CONFIG["required_columns"])
ALLOWED_ACTIVITIES=frozenset(CONFIG["allowed_activities"])
ALLOWED_STATUSES=frozenset(CONFIG["allowed_statuses"])
AUTHORITY_BY_NATION=CONFIG["authority_by_nation"]
# Generic facility-building names such as "house", "home", and "lodge" are
# common in legitimate establishment addresses. Keep only terms that are
# stronger indicators of a residential, private, or intermediary address.
ADDRESS_RISK=re.compile(r"\b(flat|apartment|residential|c/o|care of|caravan)\b",re.I)
MONTHLY_REQUIRED=frozenset({"AppNo","TradingName","Country","CompetentAuthority","X","Y","AddressWithheld","All_Activities"})
MONTHLY_COUNTRIES=frozenset({"England","Wales"})

class FsaContractError(ValueError):
    """The artifact does not satisfy a supported source contract."""

@dataclass(frozen=True)
class ValidationResult:
    accepted: tuple[dict[str,Any],...]
    quarantined: tuple[dict[str,Any],...]
    source_sha256: str
    contract_version: str=CONFIG["contract_version"]
    release_allowed: bool=False
    profile: str="synthetic"
    schema_fingerprint: str=""
    coverage_counts: dict[str,int]|None=None
    anomaly_counts: dict[str,int]|None=None
    def as_dict(self): return asdict(self)

def _clean(v):
    if v is None:return None
    v=v.strip();return v or None
def _split(v): return tuple(x for x in (_clean(i) for i in (v or "").split(";")) if x)
def _atomic(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=f".{path.name}.",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as h:h.write(payload)
        os.replace(tmp,path)
    except Exception:
        try:os.unlink(tmp)
        except FileNotFoundError:pass
        raise
def _jsonl(path,rows):
    payload=b"".join((json.dumps(r,ensure_ascii=False,sort_keys=True,default=list)+"\n").encode() for r in rows);_atomic(path,payload);return hashlib.sha256(payload).hexdigest()
def _csv(content):
    for enc in ("utf-8-sig","cp1252"):
        try:
            rows=list(csv.reader(content.decode(enc).splitlines(),strict=True))
            if not rows or not rows[0]:raise FsaContractError("missing source header")
            return rows[0],rows[1:],enc
        except UnicodeDecodeError:continue
        except csv.Error as exc:raise FsaContractError("malformed CSV") from exc
    raise FsaContractError("unsupported CSV encoding")
def _synthetic_record(row,line):
    nation=_clean(row.get("nation"));return {"source_id":CONFIG["source_id"],"source_row":line,"source_values":dict(row),"normalized":{"establishment_id":_clean(row.get("establishment_id")),"trading_name":_clean(row.get("trading_name")),"address_lines":tuple(_clean(row.get(f"address_line_{n}")) for n in range(1,4)),"postcode":_clean(row.get("postcode")),"activities":_split(row.get("activities")),"species":_clean(row.get("species")),"competent_authority":_clean(row.get("competent_authority")),"nation":nation,"authority_nation_key":nation,"status":_clean(row.get("status")),"remarks":_clean(row.get("remarks")),"published_date":_clean(row.get("published_date")),"coordinates":None}}
def _coords(row):
    try:x,y=float(row.get("X","").strip()),float(row.get("Y","").strip())
    except ValueError:return None,None,"unresolved-nonnumeric"
    if not(-8.5<=x<=2.5 and 49.0<=y<=61.5):return None,None,"unresolved-out-of-range"
    return x,y,"source-x-lon-y-lat"
def _monthly_record(row,line):
    withheld=(_clean(row.get("AddressWithheld")) or "").lower()=="yes";x=y=None;status="withheld" if withheld else "unavailable"
    if not withheld:x,y,status=_coords(row)
    acts=tuple(x for x in (_clean(row.get("All_Activities")),_clean(row.get("Part_A__All_sections_")),_clean(row.get("Part B All sections "))) if x)
    return {"source_id":CONFIG["source_id"],"source_row":line,"source_values":dict(row),"normalized":{"establishment_id":_clean(row.get("AppNo")),"trading_name":_clean(row.get("TradingName")),"address_lines":None if withheld else tuple(_clean(row.get(k)) for k in ("Address1","Address2","Address3")),"postcode":_clean(row.get("Postcode")),"activities":acts,"species":_clean(row.get("Species")),"competent_authority":_clean(row.get("CompetentAuthority")),"nation":_clean(row.get("Country")),"authority_nation_key":_clean(row.get("Country")),"status":None,"remarks":_clean(row.get("Remarks")),"published_date":None,"coordinates":None if withheld else {"longitude":x,"latitude":y,"status":status},"privacy_gate":"restricted-withheld-address" if withheld else "pending-review","publication_gate":"blocked"}}

class FsaApprovedEstablishmentsAdapter:
    source_id=CONFIG["source_id"];schema_version=CONFIG["contract_version"];adapter_version=CONFIG["adapter_version"]
    def parse_bytes(self,content):
        digest=hashlib.sha256(content).hexdigest();headers,rows,_=_csv(content);fp=hashlib.sha256(json.dumps(headers,ensure_ascii=False,separators=(",",":")).encode()).hexdigest();synthetic=tuple(headers)==REQUIRED_COLUMNS;monthly=MONTHLY_REQUIRED.issubset(headers)
        if not synthetic and not monthly:raise FsaContractError("schema drift: unsupported FSA header profile")
        return self._synthetic(headers,rows,digest,fp) if synthetic else self._monthly(headers,rows,digest,fp)
    def _synthetic(self,headers,rows,digest,fp):
        accepted=[];quarantined=[];parsed=[];keys=[]
        for line,row in enumerate(rows,2):
            v={h:row[i] if i<len(row) else None for i,h in enumerate(headers)};parsed.append((line,v));keys.append((_clean(v.get("nation")),_clean(v.get("establishment_id"))))
        duplicates={k for k in keys if k[0] and k[1] and keys.count(k)>1}
        for line,v in parsed:
            reasons=[];nation,ident=_clean(v.get("nation")),_clean(v.get("establishment_id"))
            if len(v)!=len(headers) or any(x is None for x in v.values()):reasons.append("malformed_row")
            if not ident:reasons.append("missing_establishment_id")
            if (nation,ident) in duplicates:reasons.append("duplicate_id_within_nation")
            if nation not in CONFIG["covered_nations"]:reasons.append("unknown_nation")
            authority=_clean(v.get("competent_authority"))
            if nation in AUTHORITY_BY_NATION and authority!=AUTHORITY_BY_NATION[nation]:reasons.append("authority_nation_mismatch")
            acts=_split(v.get("activities"))
            if not acts:reasons.append("missing_activity")
            elif any(a not in ALLOWED_ACTIVITIES for a in acts):reasons.append("unknown_activity")
            status=_clean(v.get("status"))
            if status and status.lower() not in ALLOWED_STATUSES:reasons.append("unknown_status")
            if _clean(v.get("remarks")):reasons.append("remarks_present")
            if ADDRESS_RISK.search(" ".join(_clean(v.get(f"address_line_{n}")) or "" for n in range(1,4))):reasons.append("address_privacy_risk")
            record=_synthetic_record(v,line);(quarantined if reasons else accepted).append({"reasons":tuple(dict.fromkeys(reasons)),"record":record} if reasons else record)
        return ValidationResult(tuple(accepted),tuple(quarantined),digest,profile="synthetic",schema_fingerprint=fp)
    def _monthly(self,headers,rows,digest,fp):
        accepted=[];quarantined=[];parsed=[];keys=[];coverage={};anomalies={}
        for line,row in enumerate(rows,2):
            v={h:row[i] if i<len(row) else None for i,h in enumerate(headers)};reasons=[]
            if len(row)!=len(headers) or any(x is None for x in v.values()):reasons.append("malformed_row")
            parsed.append((line,v,reasons));keys.append((_clean(v.get("Country")),_clean(v.get("AppNo"))))
        duplicates={k for k in keys if k[0] and k[1] and keys.count(k)>1}
        for line,v,reasons in parsed:
            country,ident=_clean(v.get("Country")),_clean(v.get("AppNo"));coverage[country or ""]=coverage.get(country or "",0)+1
            if not ident:reasons.append("missing_establishment_id")
            if (country,ident) in duplicates:reasons.append("duplicate_id_within_nation")
            if country not in MONTHLY_COUNTRIES:reasons.append("unknown_nation")
            if not any(_clean(v.get(k)) for k in ("All_Activities","Part_A__All_sections_","Part B All sections ")):reasons.append("missing_activity")
            if _clean(v.get("Remarks")):reasons.append("remarks_present")
            withheld=(_clean(v.get("AddressWithheld")) or "").lower()=="yes"
            if not withheld and ADDRESS_RISK.search(" ".join(_clean(v.get(k)) or "" for k in ("Address1","Address2","Address3","Town","Postcode"))):reasons.append("address_privacy_risk")
            record=_monthly_record(v,line)
            if reasons:
                for reason in reasons:anomalies[reason]=anomalies.get(reason,0)+1
                quarantined.append({"reasons":tuple(dict.fromkeys(reasons)),"record":record})
            else:accepted.append(record)
        return ValidationResult(tuple(accepted),tuple(quarantined),digest,profile="monthly",schema_fingerprint=fp,coverage_counts=coverage,anomaly_counts=anomalies)
    def parse_file(self,path):return self.parse_bytes(Path(path).read_bytes())
    def run(self,raw_path,run_dir,artifact=None):
        if artifact is None:raise FsaContractError("SourceArtifact metadata is required")
        required={"source_url","retrieved_at_utc","checksum_sha256","byte_size"};missing=sorted(required-set(artifact))
        if missing:raise FsaContractError(f"missing SourceArtifact fields: {', '.join(missing)}")
        raw=Path(raw_path).read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if digest!=artifact["checksum_sha256"] or len(raw)!=int(artifact["byte_size"]):raise FsaContractError("source checksum or byte size mismatch")
        result=self.parse_bytes(raw);accepted=list(result.accepted);quarantined=list(result.quarantined);root=Path(run_dir);parsed=accepted+[x["record"] for x in quarantined]
        normalized_sha=_jsonl(root/"normalized"/"records.jsonl",accepted);_jsonl(root/"parsed"/"records.jsonl",parsed);_jsonl(root/"quarantined"/"records.jsonl",quarantined);(root/"released").mkdir(parents=True,exist_ok=True)
        manifest={**artifact,"source_id":self.source_id,"adapter_version":self.adapter_version,"schema_version":self.schema_version,"checksum_sha256":digest,"byte_size":len(raw),"input_rows":len(parsed),"normalized_rows":len(accepted),"normalized_sha256":normalized_sha,"quarantined_rows":len(quarantined),"profile":result.profile,"schema_fingerprint":result.schema_fingerprint,"coverage_counts":result.coverage_counts or {},"anomaly_counts":result.anomaly_counts or {},"geocoding":"disabled","release_state":"not-created","publication_state":"private-candidate"}
        _atomic(root/"manifest.json",(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2,default=list)+"\n").encode());return manifest

def run_registered(raw_path,run_dir,config):return FsaApprovedEstablishmentsAdapter().run(raw_path,run_dir,config)
