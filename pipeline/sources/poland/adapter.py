"""GIW HTML sections: preserve approval observations and source-local identity."""
from __future__ import annotations

from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

SOURCE_ID = "pl.giw.approved-food"
SOURCE_URL = "https://zywnosc.wetgiw.gov.pl/spi/zatw/index.php"
ADAPTER_VERSION = "pl-giw-approved-food-v1"
SCHEMA_VERSION = "pl-giw-html-sections-v1"
COVERAGE = "GIW animal-origin food approvals, Sections 0-XVI; WNI-grouped establishments with separate section/activity/species observations"
SECTIONS = tuple(range(1, 18))
FIELDS = ("ordinal", "wni", "name", "address", "category", "species", "associated_activities", "remarks", "article_44")


def valid_approval_identifier(value):
    """Accept the register's observed WNI forms without rewriting their identity."""
    return isinstance(value, str) and re.fullmatch(r"(?:\d{8,9}|\d-\d{8})", value) is not None


def display_label(value):
    """Bound only the UI label; the complete name remains in source evidence."""
    if not isinstance(value, str): return None
    value = " ".join(value.split())
    return value[:200] if value and not any(ord(c) < 32 or ord(c) == 127 for c in value) else None


class RegisterPage(HTMLParser):
    """Read only spiMainTable, expanding rowspans without losing activities."""

    def __init__(self, content: bytes):
        super().__init__(convert_charrefs=True)
        self.table_depth = 0
        self.in_main = False
        self.physical_rows = []
        self.row = None
        self.cell = None
        self.spans = {}
        self.rows = []
        self.outside = []
        self.links = []
        self.selected_section = None
        self.section_options = {}
        self.select = None
        self.option = None
        try:
            self.feed(content.decode("utf-8-sig", errors="strict"))
        except UnicodeDecodeError:
            raise ValueError("GIW page is not UTF-8") from None
        self.close()
        for row in self.physical_rows:
            expanded = []
            column = 0
            pending = dict(self.spans)
            self.spans = {}
            def inherited():
                nonlocal column
                while column in pending:
                    text, remaining = pending.pop(column)
                    expanded.append(text)
                    if remaining > 1:
                        self.spans[column] = (text, remaining - 1)
                    column += 1
            for text, rowspan, colspan in row:
                inherited()
                for _ in range(colspan):
                    expanded.append(text)
                    if rowspan > 1:
                        self.spans[column] = (text, rowspan - 1)
                    column += 1
            inherited()
            if pending:
                raise ValueError("GIW table has an unresolved rowspan")
            self.rows.append(expanded)
        self.data = []
        self.headers = []
        width = len(self.rows[0]) if self.rows else 0
        keys = FIELDS[:width]
        for row in self.rows:
            if len(row) == width and row[0].isdigit():
                self.data.append({**dict.fromkeys(FIELDS, ""), **dict(zip(keys, row))})
            elif len(row) == width:
                self.headers.append(row)
            elif any(valid_approval_identifier(c) for c in row):
                raise ValueError("GIW approval row has an unexpected width")
        if (self.rows and (width not in {8,9} or len(self.headers) != 1
                          or self.headers[0][1] not in {"Appr.No.", "WNI"})):
            raise ValueError("GIW register header changed")
        counts = re.findall(r"(?:count|liczba)\s*:\s*([\d ]+)", " ".join(self.outside), flags=re.I)
        if not counts:
            raise ValueError("GIW register count is missing")
        values = {int(v.replace(" ", "")) for v in counts}
        if len(values) != 1:
            raise ValueError("GIW register counts disagree")
        self.count = values.pop()
        if not self.rows and self.count != 0:
            raise ValueError("GIW table is absent for a nonempty section")
        self.ordinals = {int(r["ordinal"]) for r in self.data}
        self.last_page = max([1] + [int(parse_qs(urlsplit(u).query)["pagenbr"][0])
                                   for u in self.links if parse_qs(urlsplit(u).query).get("pagenbr", [""])[0].isdigit()])

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            if attrs.get("id") == "spiMainTable":
                self.in_main = True
            if self.in_main:
                self.table_depth += 1
        if tag == "select":
            self.select = attrs.get("name")
        if tag == "option" and self.select == "sekcja":
            self.option = (attrs, [])
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        if not self.in_main:
            return
        if tag == "tr":
            self.row = []
        if tag in {"td", "th"} and self.row is not None:
            self.cell = ([], int(attrs.get("rowspan", 1)), int(attrs.get("colspan", 1)))
        if tag == "br" and self.cell:
            self.cell[0].append("\n")

    def handle_data(self, data):
        if self.option:
            self.option[1].append(data)
        if self.cell:
            self.cell[0].append(data)
        if not self.in_main:
            self.outside.append(data)

    def handle_endtag(self, tag):
        if tag == "option" and self.option:
            attrs, parts = self.option
            value = attrs.get("value", "")
            if value.isdigit():
                self.section_options[int(value)] = " ".join("".join(parts).split())
                if "selected" in attrs:
                    self.selected_section = int(value)
            self.option = None
        if tag == "select":
            self.select = None
        if tag in {"td", "th"} and self.cell is not None:
            parts, rowspan, colspan = self.cell
            self.row.append(("\n".join(" ".join(p.split()) for p in "".join(parts).splitlines()).strip(), rowspan, colspan))
            self.cell = None
        if tag == "tr" and self.in_main and self.row is not None:
            self.physical_rows.append(self.row)
            self.row = None
        if tag == "table" and self.in_main:
            self.table_depth -= 1
            if not self.table_depth:
                self.in_main = False


def bundle_digest(root: Path):
    digest = hashlib.sha256()
    total = 0
    for p in sorted(root.glob("section-*-page-*.html")):
        name, raw = p.name.encode(), p.read_bytes()
        digest.update(len(name).to_bytes(8, "big")); digest.update(name)
        digest.update(len(raw).to_bytes(8, "big")); digest.update(raw)
        total += len(raw)
    return digest.hexdigest(), total


def address_parts(value: str):
    """Split the source address at its explicit Polish postcode; never invent a town."""
    lines = [" ".join(v.split()) for v in value.splitlines() if v.strip()]
    match = re.search(r"\b(\d{2}-\d{3})\s+([^\n]+)", value)
    postcode, city = (match.group(1), match.group(2).strip(" ,;")) if match else (None, None)
    streets = [line for line in lines if not re.search(r"\b\d{2}-\d{3}\b", line)]
    if city and not streets:
        split = re.split(r",\s*|\s+(?=(?:ul\.|ulica\b|al\.|os\.))", city, maxsplit=1, flags=re.I)
        if len(split) == 2:
            city, street = split
            streets = [street]
        else:
            rural = re.fullmatch(r"(.+?)\s+(\d+[A-Za-z]?(?:/\w+)?)", city)
            if rural:
                city = rural.group(1)
                streets = [rural.group(0)]
            elif any(c.isdigit() for c in city):
                city = None
    # The native address remains verbatim in source_values. This derived
    # projection puts the street first for the shared provider/matcher seam.
    streets = [re.sub(r"^(?:ul\.|ulica)\s*", "", line, flags=re.I).strip() for line in streets]
    return {"address_lines": streets or lines, "address": " ".join(streets or lines), "postal_code": postcode,
            "city": city, "country_code": "PL"}


def approval_group_facts(rows):
    """Complete activity/species summary per WNI; native rows stay separate."""
    groups = {}
    for row in rows:
        groups.setdefault(row["normalized"]["establishment_id"], []).append(row)
    result = {}
    for identity, members in groups.items():
        details = []
        addresses = set()
        for row in members:
            native = row["source_values"]
            detail = {key: native[key] for key in ("section", "section_label", "category", "species", "associated_activities", "remarks", "article_44")}
            if detail not in details:
                details.append(detail)
            location = address_parts(native["address"])
            addresses.add(json.dumps(location, ensure_ascii=False, sort_keys=True).casefold())
        result[identity] = {"source_approval_details": details,
                            "source_scope_eligibility": "ambiguous_source_address" if len(addresses) > 1 else "eligible"}
    return result


class GiwApprovedFoodAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION
    source_kind = "facility_master"

    def parse(self, path):
        accepted, quarantined, seen = [], [], set()
        input_rows = 0
        for p in sorted(Path(path).glob("section-*-page-*.html")):
            section = int(p.name.split("-")[1])
            page = RegisterPage(p.read_bytes())
            if section not in SECTIONS or page.selected_section != section:
                raise ValueError("GIW section identity changed")
            for values in page.data:
                input_rows += 1
                native = {**values, "section": section, "section_label": page.section_options[section]}
                identity = hashlib.sha256(json.dumps({k:v for k,v in native.items() if k != "ordinal"}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                key = f"approval:{values['wni']}:section:{section}:{identity}"
                row = {"source_id": SOURCE_ID, "source_row": input_rows, "source_record_key": key,
                       "source_values": native, "normalized": {}}
                reasons = []
                if not valid_approval_identifier(values["wni"]): reasons.append("invalid_wni")
                if not values["name"]: reasons.append("missing_name")
                if key in seen: reasons.append("duplicate_approval_observation")
                seen.add(key)
                if reasons:
                    quarantined.append({"source_row": input_rows, "reasons": reasons, "record": row})
                    continue
                row["normalized"] = {"establishment_id": values["wni"], "trading_name": values["name"],
                    "country_code": "PL", "nation": "Poland", "source_section": section,
                    "source_section_label": native["section_label"], "source_activity_codes": re.findall(r"[A-Z][A-Z0-9_-]*", values["category"]),
                    "source_species_scope": values["species"], "source_associated_activities": values["associated_activities"],
                    "source_regulatory_notes": values["remarks"], "source_article_44": values["article_44"],
                    "private_location_evidence": address_parts(values["address"]),
                    "privacy_gate": "pending-review", "publication_gate": "blocked", "coordinates": None}
                accepted.append(row)
        if not input_rows: raise ValueError("GIW page bundle has no approval observations")
        summaries = approval_group_facts(accepted)
        for row in accepted:
            row["normalized"].update(summaries[row["normalized"]["establishment_id"]])
        return {"accepted": accepted, "quarantined": quarantined, "input_rows": input_rows}

    def run(self, raw_path, run_dir, artifact):
        if bundle_digest(Path(raw_path)) != (artifact.sha256, artifact.byte_size):
            raise ValueError("GIW source bundle provenance mismatch")
        parsed = self.parse(raw_path)
        root = Path(run_dir)
        _, parsed_hash, _ = atomic_jsonl(root / "parsed/records.jsonl", parsed["accepted"] + [r["record"] for r in parsed["quarantined"]])
        _, normalized_hash, _ = atomic_jsonl(root / "normalized/records.jsonl", parsed["accepted"])
        atomic_jsonl(root / "quarantined/records.jsonl", parsed["quarantined"])
        reasons = Counter(reason for q in parsed["quarantined"] for reason in q["reasons"])
        manifest = private_manifest(source_id=SOURCE_ID, adapter_version=ADAPTER_VERSION,
            schema_version=SCHEMA_VERSION, artifact=artifact, input_rows=parsed["input_rows"],
            normalized_rows=len(parsed["accepted"]), quarantined_rows=len(parsed["quarantined"]),
            normalized_sha256=normalized_hash, parsed_sha256=parsed_hash, anomaly_counts=dict(reasons))
        manifest["source_qualified_establishments"] = len({r["normalized"]["establishment_id"] for r in parsed["accepted"]})
        manifest["geocoding"] = "separate-private-profile"
        manifest["schema_fingerprint"] = hashlib.sha256(json.dumps(FIELDS).encode()).hexdigest()
        atomic_json(root / "manifest.json", manifest)
        return manifest

    def write_candidate_handoff(self, run_dir, artifact, accepted):
        return write_handoff(run_dir, accepted, artifact, source_id=SOURCE_ID, emit_graph_candidates=False)
